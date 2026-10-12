"""Bounded original PCM WAV assets; Workbench owns records, revisions and review."""
import base64
import hashlib
import io
import os
import struct
import uuid
import wave

from metadata import CommitOutcomeUnknown
from workbench import WorkbenchError, encode, strings, text_value, timestamp

MAX_WAV_BYTES = 8 * 1024 * 1024
MAX_DURATION_SECONDS = 120
MAX_SEGMENTS = 200
WAVEFORM_BINS = 600
TASK = 'audio_timed'


def invalid(message, code='invalid', status=400):
    raise WorkbenchError('Audio: ' + message, code, status)


def parse_wav(raw):
    """Validate a closed PCM16 RIFF/WAVE profile before the standard WAV reader."""
    if not isinstance(raw, bytes) or not 44 <= len(raw) <= MAX_WAV_BYTES:
        invalid('choose a complete WAV file, at most 8 MiB.')
    if raw[:4] != b'RIFF' or raw[8:12] != b'WAVE':
        invalid('only little-endian RIFF/WAVE PCM is supported.', 'unsupported')
    if struct.unpack_from('<I', raw, 4)[0] + 8 != len(raw):
        invalid('RIFF byte count does not match the complete file.')
    chunks, position = {}, 12
    while position < len(raw):
        if position + 8 > len(raw):
            invalid('truncated WAV chunk header.')
        tag, size = struct.unpack_from('<4sI', raw, position)
        start, end = position + 8, position + 8 + size
        position = end + (size % 2)
        if position > len(raw):
            invalid('WAV chunk size exceeds the supplied bytes.')
        if tag in (b'fmt ', b'data'):
            if tag in chunks:
                invalid('duplicate format or data chunk.')
            chunks[tag] = raw[start:end]
    if b'fmt ' not in chunks or b'data' not in chunks:
        invalid('WAV requires one format and one data chunk.')
    fmt = chunks[b'fmt ']
    if len(fmt) != 16:
        invalid('only the 16-byte PCM format is supported; extensible/compressed WAV is unavailable.', 'unsupported')
    encoding, channels, rate, byte_rate, align, bits = struct.unpack('<HHIIHH', fmt)
    if encoding != 1 or bits != 16 or channels not in (1, 2) or not 8000 <= rate <= 96000:
        invalid('supported WAV is PCM signed 16-bit, mono/stereo, 8,000–96,000 Hz.', 'unsupported')
    if align != channels * 2 or byte_rate != rate * align:
        invalid('sample rate, byte rate and frame alignment disagree.')
    pcm = chunks[b'data']
    if not pcm or len(pcm) % align:
        invalid('data must contain complete nonempty interleaved sample frames.')
    frames = len(pcm) // align
    if frames > rate * MAX_DURATION_SECONDS:
        invalid('duration exceeds 120 seconds.')
    try:
        with wave.open(io.BytesIO(raw), 'rb') as reader:
            if reader.getparams()[:4] != (channels, 2, rate, frames) or reader.readframes(frames) != pcm:
                invalid('standard WAV reader disagrees with the declared sample frames.')
    except (wave.Error, EOFError) as error:
        invalid('standard WAV reader rejected the file: ' + str(error))
    metadata = dict(schema_version=1, encoding='pcm_s16le', sample_rate_hz=rate,
                    channels=channels, frame_count=frames, duration_seconds=frames / rate,
                    source_bytes=len(raw), pcm_sha256=hashlib.sha256(pcm).hexdigest())
    return metadata, pcm


def validate_annotation(value, record):
    if not isinstance(value, dict) or set(value) != {'segments'} or not isinstance(value['segments'], list) or not 1 <= len(value['segments']) <= MAX_SEGMENTS:
        invalid('provide 1–200 timed segments. Each segment needs a transcript or class label.')
    result = []
    meta = record['audio']
    for segment in value['segments']:
        if not isinstance(segment, dict) or set(segment) != {'start_frame', 'end_frame', 'channel', 'transcript', 'label', 'speaker'}:
            invalid('segment fields must be start_frame, end_frame, channel, transcript, label and speaker.')
        start, end, channel = (segment[key] for key in ('start_frame', 'end_frame', 'channel'))
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= meta['frame_count']:
            invalid('intervals use integer source frames: 0 ≤ start < end ≤ frame count; end is exclusive.')
        if type(channel) is not int or not 0 <= channel < meta['channels']:
            invalid('channel is a zero-based source channel index.')
        fields = {key: text_value(segment[key], key.title(), maximum, empty=True)
                  for key, maximum in (('transcript', 4000), ('label', 80), ('speaker', 120))}
        if not fields['transcript'] and not fields['label']:
            invalid('each segment needs a human transcript or class label.')
        result.append(dict(start_frame=start, end_frame=end, channel=channel, **fields))
    if len({encode(item) for item in result}) != len(result):
        invalid('duplicate timed segments are not allowed.')
    return {'segments': result}


def _sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class AudioAssets:
    def __init__(self, workbench):
        self.workbench = workbench
        self.path = workbench.dataset.path / 'audio'

    def admit(self, body):
        if type(body) is not dict or set(body) - {'wav', 'name', 'rights', 'groups', 'parents'}:
            invalid('import expects wav, name, rights, groups and optional parents.')
        encoded = body.get('wav')
        try:
            if not isinstance(encoded, str) or len(encoded) > ((MAX_WAV_BYTES + 2) // 3) * 4:
                raise ValueError()
            raw = base64.b64decode(encoded, validate=True)
        except ValueError:
            invalid('wav must be a bounded complete base64 file.')
        meta, _ = parse_wav(raw)
        name = text_value(body.get('name', 'Audio recording'), 'Name')
        rights = text_value(body.get('rights', 'unknown'), 'Rights / permission note', 1000)
        groups = strings(body.get('groups', []), 'Protected groups', maximum=28)
        parents = strings(body.get('parents', []), 'Parent IDs')
        digest = hashlib.sha256(raw).hexdigest()
        # Equal decoded PCM at the same rate/channels stays in one split even when headers differ.
        family = hashlib.sha256(encode([meta['sample_rate_hz'], meta['channels'], meta['pcm_sha256']]).encode()).hexdigest()
        protected = ['audio-source:' + digest, 'audio-family:' + family]
        meta['protected_groups'] = protected
        groups = list(dict.fromkeys(groups + protected))
        origin = {'method': 'import', 'rights': rights, 'audio': meta, 'source_sha256': digest,
                  'transform': 'none; original interleaved PCM WAV bytes preserved'}
        record_id, created = uuid.uuid4().hex, timestamp()
        folder = self.path / record_id
        w = self.workbench
        def discard():
            if folder.exists():
                (folder / 'source.wav').unlink(missing_ok=True)
                folder.rmdir()
        try:
            with w.lock, w.db.transaction():
                for parent in parents:
                    w._get(parent)
                if w.db.execute("SELECT 1 FROM workbench_records WHERE kind='audio' AND content_hash=%s", (digest,)).fetchone():
                    invalid('this original WAV already exists; open its existing record.', 'conflict', 409)
                self.path.mkdir(exist_ok=True)
                folder.mkdir()
                # Successful savepoints pass custody to their outer transaction.
                w.db.on_rollback(discard)
                with (folder / 'source.wav').open('xb') as target:
                    target.write(raw); target.flush(); os.fsync(target.fileno())
                _sync_directory(folder); _sync_directory(self.path); _sync_directory(self.path.parent)
                w.db.execute('INSERT INTO workbench_records VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                             (record_id, 'audio', name, None, None, digest, None, encode(groups), encode(parents),
                              encode(origin), TASK, None, 'draft', 1, created, created))
                record = w._get(record_id)
                w._history(record)
        except CommitOutcomeUnknown:
            # A lost PostgreSQL commit acknowledgement may already have published this reference.
            # Retain its bytes; the existing catalog reconciliation owns the next action.
            raise
        except Exception:
            discard()
            raise
        return record

    def metadata(self, record_id, provenance):
        meta = provenance.get('audio')
        if not isinstance(meta, dict) or meta.get('schema_version') != 1:
            invalid('stored source metadata is unavailable.', 'unavailable', 409)
        return dict(meta), (self.path / record_id / 'source.wav').is_file()

    def asset(self, record):
        path = self.path / record['id'] / 'source.wav'
        try:
            with path.open('rb') as source:
                raw = source.read(MAX_WAV_BYTES + 1)
        except OSError:
            invalid('original WAV is unavailable. Restore it from the catalog backup.', 'unavailable', 404)
        if hashlib.sha256(raw).hexdigest() != record['content_hash']:
            invalid('original WAV changed outside Tuldok. Restore the original bytes.', 'conflict', 409)
        meta, _ = parse_wav(raw)
        retained = dict(record['audio']); retained.pop('protected_groups', None)
        if meta != retained:
            invalid('retained source metadata does not match the original WAV.', 'conflict', 409)
        return raw, 'audio/wav'

    def inspect(self, record_id):
        w = self.workbench
        with w.lock:
            record = w.get(record_id)
            if record['kind'] != 'audio':
                invalid('inspection requires an audio record.')
            raw, _ = self.asset(record)
        meta, pcm = parse_wav(raw)
        frames, channels = meta['frame_count'], meta['channels']
        bins = min(frames, WAVEFORM_BINS)
        # Exact source-frame bins; amplitudes are display summaries, never timing authority.
        peaks = []
        for channel in range(channels):
            values = []
            for index in range(bins):
                start, end = index * frames // bins, (index + 1) * frames // bins
                samples = (struct.unpack_from('<h', pcm, (frame * channels + channel) * 2)[0]
                           for frame in range(start, end))
                values.append(max(abs(value) for value in samples) / 32768)
            peaks.append(values)
        return dict(id=record_id, content_hash=record['content_hash'], frame_count=frames,
                    sample_rate_hz=meta['sample_rate_hz'], channels=channels, bins=bins, peaks=peaks)
