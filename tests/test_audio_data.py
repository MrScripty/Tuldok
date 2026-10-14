"""Source-frame WAV semantics and real PostgreSQL/filesystem review/export path."""
from auth_helpers import bind_owner
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import wave
import zipfile

from app import Dataset
import audio_assets
from backup_metadata import backup_catalog, restore_catalog
import psycopg
from psycopg import sql
from metadata import CommitOutcomeUnknown, connection_info
from postgres_helpers import drop_failure_trigger, install_failure_trigger
from workbench import WorkbenchError

FIXTURE = Path(__file__).parent / 'fixtures/workspaces/audio/stereo-impulses.wav'


def body(raw=None, **options):
    return dict(wav=base64.b64encode(FIXTURE.read_bytes() if raw is None else raw).decode(), name='Authored stereo impulses',
                rights='Authored mathematical fixture; no acquired audio', **options)


def segment(**options):
    return dict(dict(start_frame=4000, end_frame=8001, channel=1, transcript='', label='impulse', speaker=''), **options)


def riff_chunk(raw, tag=b'JUNK', value=b'note'):
    chunk = struct.pack('<4sI', tag, len(value)) + value + (b'\0' if len(value) % 2 else b'')
    result = raw[:12] + chunk + raw[12:]
    return result[:4] + struct.pack('<I', len(result) - 8) + result[8:]


class AudioParsing(unittest.TestCase):
    def test_known_stereo_source_frames_and_independent_ffmpeg_reader(self):
        raw = FIXTURE.read_bytes()
        meta, pcm = audio_assets.parse_wav(raw)
        self.assertEqual((meta['sample_rate_hz'], meta['channels'], meta['frame_count'], meta['duration_seconds']), (8000, 2, 16000, 2))
        self.assertEqual(len(pcm), 64000)
        samples = list(struct.iter_unpack('<hh', pcm))
        self.assertEqual([(i, pair) for i, pair in enumerate(samples) if any(pair)],
                         [(0,(16384,0)), (4000,(0,24576)), (8000,(-16384,0)), (12000,(0,-24576)), (15999,(8192,-8192))])
        self.assertEqual([row[1] for row in samples[4000:8001] if row[1]], [24576])
        self.assertEqual(samples[15999:16000], [(8192,-8192)])
        # FFmpeg is a separately implemented consumer, not the production wave parser.
        probe = json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(FIXTURE)]))['streams'][0]
        self.assertEqual((probe['codec_name'], probe['sample_rate'], probe['channels'], probe['duration_ts']), ('pcm_s16le','8000',2,16000))
        decoded = subprocess.check_output(['ffmpeg','-v','error','-i',str(FIXTURE),'-f','s16le','-acodec','pcm_s16le','-'])
        self.assertEqual(decoded, pcm)

    def test_reject_encoding_size_duration_chunk_rate_and_partial_frame(self):
        raw = FIXTURE.read_bytes()
        examples = [(raw[:40], 'complete WAV'), (raw + b'x', 'RIFF byte count'), (b'RF64' + raw[4:], 'little-endian RIFF'), (riff_chunk(raw, b'data', b'\0\0\0\0'), 'duplicate format or data'), (b'\0' * (audio_assets.MAX_WAV_BYTES + 1), 'complete WAV')]
        for offset, fmt, value in [(20,'H',3), (22,'H',3), (24,'I',7999), (28,'I',123), (32,'H',2), (34,'H',8), (40,'I',63999)]:
            changed = bytearray(raw); struct.pack_into('<' + fmt, changed, offset, value)
            message = 'complete nonempty interleaved sample frames' if offset == 40 else 'frame alignment disagree' if offset in (28,32) else 'supported WAV is PCM'
            examples.append((bytes(changed),message))
        for value, message in examples:
            with self.subTest(size=len(value), header=value[:44]):
                with self.assertRaisesRegex(WorkbenchError,message): audio_assets.parse_wav(value)
        stream = io.BytesIO()
        with wave.open(stream,'wb') as writer:
            writer.setparams((1,2,8000,0,'NONE','not compressed')); writer.writeframes(b'\0\0' * (8000 * 120 + 1))
        with self.assertRaisesRegex(WorkbenchError, '120 seconds'): audio_assets.parse_wav(stream.getvalue())

    def test_half_open_annotation_bounds_closed_shape_and_no_automatic_transcript(self):
        meta, _ = audio_assets.parse_wav(FIXTURE.read_bytes()); record = {'audio':meta}
        valid = {'segments':[segment(), segment(start_frame=15999, end_frame=16000, channel=0, label='', transcript='Human note')]}
        self.assertEqual(audio_assets.validate_annotation(valid, record), valid)
        cases = [dict(start_frame=True), dict(start_frame=-1), dict(start_frame=4000.0), dict(end_frame=16001), dict(end_frame=4000),
                 dict(channel=2), dict(channel=True), dict(transcript='',label=''), dict(extra='ignored')]
        for change in cases:
            with self.subTest(change=change), self.assertRaises(WorkbenchError):
                audio_assets.validate_annotation({'segments':[segment(**change)]}, record)
        for value in ({'segments':[]}, {'segments':[segment(),segment()]}, {'segments':[segment()],'timing':'seconds'}):
            with self.assertRaises(WorkbenchError): audio_assets.validate_annotation(value, record)
        self.assertEqual(audio_assets.parse_wav(riff_chunk(FIXTURE.read_bytes()))[1], audio_assets.parse_wav(FIXTURE.read_bytes())[1])


class AudioData(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'catalog'
        self.dataset = Dataset(self.path); self.actor = bind_owner(self, self.dataset)
        self.addCleanup(self.drop_schema)
        self.addCleanup(lambda: self.dataset.close())
        self.w = self.dataset.workbench

    def drop_schema(self):
        with psycopg.connect(connection_info(), autocommit=True) as connection:
            connection.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(self.dataset.db.schema)))

    def review(self, row, **changes):
        request = dict(revision=row['revision'], source_revision=row['source_revision'], task='audio_timed',
                       annotation={'segments':[segment()]}, groups=row['groups'], review='human_reviewed')
        request.update(changes)
        return self.w.save(row['id'], request)

    def selection(self, rows):
        return [dict((key,row[key]) for key in ('id','revision','source_revision')) for row in rows]

    def release_body(self, rows):
        return dict(format='canonical_v1', items=self.selection(rows), ratios=dict(train=100,validation=0,test=0), seed=42)

    def test_import_review_history_rights_query_reload_export_and_independent_reader(self):
        row = self.w.audio.admit(body(groups=['recording-session']))
        self.assertEqual((row['kind'], row['task'], row['review'], row['annotation']), ('audio','audio_timed','draft',None))
        self.assertEqual(self.w.query({'kind':'audio','task':'audio_timed'})['total'], 1)
        self.assertFalse(self.dataset.releases.preview(self.release_body([row]))['eligible'])
        with self.assertRaises(WorkbenchError): self.dataset.releases.create(self.release_body([row]))
        saved = self.review(row)
        self.assertEqual(self.w.query({'label':'impulse'})['total'], 1)
        with self.assertRaisesRegex(WorkbenchError,'changed'): self.review(row)
        corrected = self.w.correct_rights_note(saved['id'],dict(revision=2,source_revision=1,note='Fixture author reviewed rights'))['record']
        self.assertEqual((corrected['revision'],corrected['review']), (3,'human_reviewed'))
        self.assertEqual(len(self.w.history(row['id'])),3)
        release = self.dataset.releases.create(self.release_body([corrected])); frozen = self.dataset.releases.locate(release['id']).read_bytes()
        with zipfile.ZipFile(io.BytesIO(frozen)) as archive:
            manifest = json.loads(archive.read('manifest.json')); projected = manifest['records'][0]
            self.assertEqual(projected['audio_target_schema_version'],1)
            self.assertEqual(projected['annotation']['segments'],[segment()])
            self.assertEqual(projected['provenance']['rights_note_correction']['note'],'Fixture author reviewed rights')
            original = archive.read(projected['asset']); self.assertEqual(original,FIXTURE.read_bytes())
            self.assertEqual(json.loads(archive.read('train/records.jsonl')),projected)
            self.assertEqual(hashlib.sha256(original).hexdigest(),projected['asset_sha256'])
            with wave.open(io.BytesIO(original)) as reader:
                reader.setpos(4000); samples = list(struct.iter_unpack('<hh',reader.readframes(4001)))
                self.assertEqual(samples[0],(0,24576)); self.assertEqual(samples[-1],(-16384,0))
        self.dataset.close(); self.dataset = Dataset(self.path); self.actor = bind_owner(self, self.dataset); self.w = self.dataset.workbench
        reloaded = self.w.get(row['id']); self.assertEqual(reloaded,corrected)
        self.assertEqual(self.w.asset(row['id']), (FIXTURE.read_bytes(),'audio/wav'))
        self.review(reloaded,annotation={'segments':[segment(label='new label')]},review='draft')
        self.assertEqual(self.dataset.releases.locate(release['id']).read_bytes(),frozen)

    def test_source_channel_peaks_family_protection_drafts_and_unsupported_requests(self):
        first = self.w.audio.admit(body())
        with self.assertRaisesRegex(WorkbenchError,'already exists'): self.w.audio.admit(body())
        changed_header = self.w.audio.admit(body(riff_chunk(FIXTURE.read_bytes()), groups=['other-session']))
        self.assertEqual(first['audio']['protected_groups'][1],changed_header['audio']['protected_groups'][1])
        inspected = self.w.audio.inspect(first['id'])
        self.assertEqual((len(inspected['peaks']),len(inspected['peaks'][0])),(2,600))
        self.assertEqual(inspected['peaks'][0][0],0.5)
        self.assertEqual(inspected['peaks'][1][150],0.75)
        self.assertEqual(inspected['peaks'][0][-1],0.25)
        for changes in (dict(groups=['removed-source-family']),dict(review='programmatically_verified')):
            with self.assertRaises(WorkbenchError): self.review(first,**changes)
        one,two = self.review(first),self.review(changed_header)
        request = self.release_body([one,two]); request['ratios']=dict(train=50,validation=50,test=0)
        preview = self.dataset.releases.preview(request)
        self.assertFalse(preview['eligible']); self.assertIn('Too few independent source groups',str(preview['blockers']))
        request['ratios'] = dict(train=100,validation=0,test=0)
        preview = self.dataset.releases.preview(request)
        self.assertTrue(preview['eligible']); self.assertEqual(len(set(preview['assignments'].values())),1)
        with self.assertRaises(WorkbenchError): self.w.audio.admit(dict(body(), crop=[0,100]))
        with self.assertRaises(WorkbenchError): self.w.audio.admit(dict(body(), wav='!!!'))

    def test_missing_tampered_source_and_oversized_selection_fail_closed(self):
        row = self.w.audio.admit(body()); self.review(row)
        asset = self.path / 'audio' / row['id'] / 'source.wav'
        asset.write_bytes(FIXTURE.read_bytes()[:-4] + b'xxxx')
        with self.assertRaisesRegex(WorkbenchError,'changed outside'): self.w.asset(row['id'])
        with self.assertRaises(WorkbenchError): self.review(self.w.get(row['id']))
        asset.unlink()
        self.assertFalse(self.w.get(row['id'])['source_available'])
        self.assertFalse(self.dataset.releases.preview(self.release_body([self.w.get(row['id'])]))['eligible'])
        from immutable_assets import check_selection
        with self.assertRaisesRegex(WorkbenchError,'40 MiB'):
            check_selection([dict(kind='audio',audio=dict(source_bytes=8*1024*1024))] * 6)

    def test_confirmed_outer_rollback_removes_files_from_successful_nested_import(self):
        with self.assertRaisesRegex(ValueError, 'authored outer rollback'):
            with self.dataset.db.transaction():
                row = self.w.audio.admit(body())
                self.assertTrue((self.path/'audio'/row['id']/'source.wav').is_file())
                raise ValueError('authored outer rollback')
        self.assertEqual(list((self.path/'audio').iterdir()),[])
        self.assertEqual(self.w.query({'kind':'audio'})['total'],0)

    def test_failed_metadata_publication_removes_unreferenced_files(self):
        install_failure_trigger(self.dataset.db,'workbench_history','audio_failure','authored publication failure')
        try:
            with self.assertRaisesRegex(Exception,'authored publication failure'): self.w.audio.admit(body())
        finally:
            drop_failure_trigger(self.dataset.db,'workbench_history','audio_failure')
        self.assertEqual(self.w.query({'kind':'audio'})['total'],0)
        self.assertEqual(list((self.path/'audio').iterdir()),[])

    def test_unknown_commit_retains_original_bytes_for_catalog_reconciliation(self):
        # Real commit happens, then the receipt is lost; retained original bytes must survive.
        from contextlib import contextmanager
        real = self.dataset.db.transaction
        @contextmanager
        def lost_receipt():
            with real(): yield
            raise CommitOutcomeUnknown('authored lost commit acknowledgement')
        with patch.object(self.dataset.db,'transaction',lost_receipt):
            with self.assertRaises(CommitOutcomeUnknown): self.w.audio.admit(body())
        row = self.w.query({'kind':'audio'})['items'][0]
        self.assertEqual(self.w.asset(row['id'])[0],FIXTURE.read_bytes())
        self.assertEqual(len(self.w.history(row['id'])),1)

    def test_quiesced_metadata_and_audio_artifact_backup_restores_exact_history(self):
        row = self.review(self.w.audio.admit(body()))
        self.dataset.close()
        backup = Path(self.tmp.name)/'backup'; restored = Path(self.tmp.name)/'restored'
        receipt = backup_catalog(self.path,backup,quiesced=True)
        key='audio/'+row['id']+'/source.wav'
        self.assertEqual(receipt['files'][key]['sha256'],row['content_hash'])
        self.drop_schema()  # Restore contract requires an absent disposable catalog schema.
        restore_catalog(backup,restored)
        other = Dataset(restored)
        try:
            self.assertEqual(other.workbench.get(row['id']),row)
            self.assertEqual(len(other.workbench.history(row['id'])),2)
            self.assertEqual(other.workbench.asset(row['id'])[0],FIXTURE.read_bytes())
        finally: other.close()


if __name__ == '__main__': unittest.main()
