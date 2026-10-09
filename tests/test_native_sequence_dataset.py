"""Retained actual v1 plus explicitly source-derived compatibility packets; no physics."""
import copy
import base64
import hashlib
import io
import json
import struct
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import zipfile

import numpy as np
from PIL import Image
from app import Dataset
from fixtures.rheon_synthetic_v2 import fixture as v2_fixture
from fixtures.rheon_source_derived import synthetic_frames
from test_sequences import fixture as v1_fixture
from test_sequence_temporal_labels import annotation, target
import rheon_sequences
import native_sequence_dataset as native
from workbench import encode

ACTUAL = Path(__file__).parent / 'fixtures/rheon_actual_fee7b4a'


def packet(path, *, v2=False, signed_zero=False, ranges=True, deleted_image=False, unselected_sequence=False):
    """Current owners export retained actual/source-derived sequences, one family."""
    d = Dataset(str(path))
    try:
        bridge = d.workbench.import_asset({'kind': 'text', 'text': 'Unselected declared parent bridge.', 'groups': ['consumer-fixture']})
        if deleted_image:
            png=io.BytesIO(); Image.new('RGB',(2,2),'blue').save(png,'PNG')
            image=d.workbench.import_asset({'kind':'image','image':base64.b64encode(png.getvalue()).decode(),
                'name':'Authored graph-only image bridge','groups':['consumer-fixture']},source_split='train')
            d.delete(image['id'],{'revision':image['source_revision']})
        sources = [((ACTUAL/'run.json').read_bytes(), (ACTUAL/'frames.jsonl').read_bytes(), None)]
        if v2:
            sources = [v2_fixture()]
        elif signed_zero:
            frames = synthetic_frames()
            for frame in frames: frame['fields']['velocity_y'][0] = -0.0
            run, raw = v1_fixture(frames=frames)
            sources = [(run, raw, None)]
        else:
            run, raw = v1_fixture(); sources.append((run, raw, None))
        rows = []
        for n, (run, raw, controls) in enumerate(sources):
            row = d.workbench.sequences.admit(rheon_sequences.prepare(run, raw, controls),
                {'name': 'Retained actual' if n == 0 and not (v2 or signed_zero) else 'Clearly source-derived synthetic',
                 'groups': ['consumer-fixture'], 'parents': [bridge['id']]})
            targets = [target(row, 'Human early', 0, 1), target(row, 'Human late', 2, 8), target(row, 'Ω human overlap', 1, 3)]
            value = annotation(row, targets) if ranges else {'note': 'Human whole trajectory note only.'}
            row = d.workbench.save(row['id'], dict(row, annotation=value, review='draft'))
            row = d.workbench.save(row['id'], dict(row, review='human_reviewed'))
            rows.append(row)
        if unselected_sequence:
            run, raw, controls = sources[-1]; assert controls is None
            manifest=json.loads(run);manifest['provenance']['command'].append('synthetic-unselected-family-context')
            d.workbench.sequences.admit(rheon_sequences.prepare(json.dumps(manifest).encode(),raw),
                {'name':'Unselected source-derived provenance variant, same raw frames/family','groups':['consumer-fixture'],'parents':[bridge['id']]})
        body = {'items': [{k: r[k] for k in ('id', 'revision', 'source_revision')} for r in rows],
            'ratios': {'train': 100, 'validation': 0, 'test': 0}, 'seed': 42}
        preview = d.releases.preview(body)
        assert preview['eligible'], preview
        released = d.releases.create(dict(body, preview_token=preview['preview_token']))
        return d.releases.locate(released['id']).read_bytes()
    finally:
        d.close()


def entries(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        return {name: z.read(name) for name in z.namelist()}


def pack(values, compression=zipfile.ZIP_STORED):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', compression=compression) as z:
        for name, raw in values.items(): z.writestr(name, raw)
    return out.getvalue()


def rewrite(raw, change, *, synchronize=True):
    values = entries(raw); manifest = json.loads(values['manifest.json'])
    change(manifest, values)
    values['manifest.json'] = encode(manifest).encode()
    if synchronize:
        for split in native.SPLITS:
            values[split+'/records.jsonl'] = b''.join((encode(r)+'\n').encode() for r in manifest['records'] if r['split'] == split)
    return pack(values)


def legacy(raw):
    def edit(m, _):
        m.pop('protected_components')
        for row in m['records']: row.pop('export_group')
    return rewrite(raw, edit)


class NativeSequenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.raw = packet(self.root/'data')
        self.path = self.root/'release.zip'; self.path.write_bytes(self.raw)

    def load(self, raw=None, **kw):
        if raw is not None: self.path.write_bytes(raw)
        return native.NativeSequenceDataset(self.path, sha256=native.sha(self.path.read_bytes()), split='train', **kw)

    def invalid(self, raw):
        with self.assertRaises(native.NativeSequenceError): self.load(raw)

    def test_actual_all_values_axes_bits_time_and_human_masks(self):
        ds = self.load(); self.assertEqual(len(ds), 2)
        sample = next(s for s in ds if s['metadata']['record']['name'] == 'Retained actual')
        fields = [json.loads(line) for line in (ACTUAL/'frames.jsonl').read_bytes().splitlines()]
        for name, kind in native.contract.FIELD_TYPES.items():
            shape = tuple(native.contract.GEOMETRY['field_shapes'][name]); a = sample['fields'][name]
            self.assertEqual(a.shape, (9, *shape)); self.assertEqual(a.dtype, np.dtype('<f4' if kind == 'f32' else '<f8'))
            for k in range(9):
                expected = b''.join(struct.pack('<f' if kind == 'f32' else '<d', value) for value in fields[k]['fields'][name])
                self.assertEqual(a[k].tobytes(order='F'), expected)
                i, j, z = (n - 1 for n in shape)
                value = fields[k]['fields'][name][i+shape[0]*(j+shape[1]*z)]
                expected_value = struct.unpack('<f', struct.pack('<f', value))[0] if kind == 'f32' else value
                self.assertEqual(a[k, i, j, z], expected_value)
        np.testing.assert_array_equal(sample['time_s'], [f['time_s'] for f in fields])
        np.testing.assert_array_equal(sample['frame_indices'], range(9))
        np.testing.assert_array_equal(sample['range_frame_mask'], [[True, True]+[False]*7, [False]*2+[True]*7, [False, True, True, True]+[False]*5])
        meta = sample['metadata']; self.assertIsNone(meta['accepted_intervals'][0]); self.assertIsNone(meta['declared_controls'])
        self.assertEqual(len(meta['declared_family_context']), 3)
        for k in range(1, 9):
            interval = meta['accepted_intervals'][k]
            self.assertEqual((interval['start_frame'], interval['end_frame']), (k-1, k))
            self.assertEqual(interval['carrier_before'], fields[k-1]['carrier_stamp'])
        self.assertEqual(meta['record']['review'], 'human_reviewed')
        self.assertEqual(len(list(ds)), 2)

    def test_all_contiguous_windows_keep_global_anchors_and_overlap(self):
        for width in range(1, 10):
            ds = self.load(window_frames=width); self.assertEqual(len(ds), 2*(10-width))
            for start in range(10-width):
                s = ds[start]; np.testing.assert_array_equal(s['frame_indices'], range(start, start+width))
                self.assertEqual(s['metadata']['window'], {'start_frame':start, 'end_frame':start+width-1})
                for n, r in enumerate(s['metadata']['record']['annotation']['temporal_labels']['ranges']):
                    np.testing.assert_array_equal(s['range_frame_mask'][n], [r['start_frame'] <= k <= r['end_frame'] for k in range(start,start+width)])
                if start: self.assertEqual(s['metadata']['accepted_intervals'][0]['start_frame'], start-1)
                self.assertEqual(s['metadata']['frame_index'][-1]['frame'], start+width-1)

    def test_source_derived_v2_controls_are_declarations_at_global_interval(self):
        ds = self.load(packet(self.root/'v2', v2=True), window_frames=2)
        first = ds[0]['metadata']['declared_controls']; self.assertIsNone(first['intervals'][0])
        s = ds[3]; self.assertEqual(s['metadata']['declared_controls']['intervals'][0]['start_frame'], 2)
        self.assertIn('synthetic', first['provenance']['author'])
        self.assertEqual(s['metadata']['accepted_intervals'][0]['end_frame'], 3)

    def test_legacy_train_only_empty_requested_split_and_note_only_coverage(self):
        raw = legacy(self.raw); ds = self.load(raw)
        self.assertTrue(any('Legacy single-split' in x for x in ds[0]['metadata']['limitations']))
        empty = native.NativeSequenceDataset(self.path, sha256=native.sha(raw), split='test')
        self.assertEqual(len(empty), 0)
        with self.assertRaises(native.NativeSequenceError): empty.write_npz(self.root/'empty.npz')
        ds = self.load(packet(self.root/'notes', ranges=False)); self.assertEqual(ds[0]['range_frame_mask'].shape, (0,9))
        def split(m, _): m['records'][1]['split'] = 'test'
        self.invalid(rewrite(raw, split))

    def test_strict_split_hash_window_index_and_empty_ranges(self):
        for width in [False, 0, 10, 3.0, '3']:
            with self.assertRaises(native.NativeSequenceError): self.load(window_frames=width)
        for split in [False, 'val', None]:
            with self.assertRaises(native.NativeSequenceError): native.NativeSequenceDataset(self.path, sha256=native.sha(self.raw), split=split)
        for h in [False, '0'*64, native.sha(self.raw).upper()]:
            with self.assertRaises(native.NativeSequenceError): native.NativeSequenceDataset(self.path, sha256=h, split='train')
        ds = self.load()
        for index in [False, -1, len(ds), 0.0]:
            with self.assertRaises(native.NativeSequenceError): ds[index]
        raw = rewrite(self.raw, lambda m,v: [r['annotation']['temporal_labels'].update(ranges=[]) for r in m['records']])
        self.assertEqual(self.load(raw)[0]['range_frame_mask'].shape, (0,9))

    def test_native_signed_zero_and_caller_path_mutation_isolation(self):
        ds = self.load(packet(self.root/'zero', signed_zero=True)); sample = ds[0]
        self.assertTrue(np.signbit(sample['fields']['velocity_y'][0,0,0,0]))
        sample['fields']['velocity_y'].fill(100); sample['metadata']['record']['annotation']['note'] = 'caller edit'
        self.path.write_bytes(b'path replaced after admission')
        fresh = ds[0]; self.assertTrue(np.signbit(fresh['fields']['velocity_y'][0,0,0,0]))
        self.assertNotEqual(fresh['metadata']['record']['annotation']['note'], 'caller edit')

    def test_npz_actual_reader_closed_numeric_keys_atomic_failures_and_aliases(self):
        ds = self.load(window_frames=3); out = self.root/'sample.npz'; ds.write_npz(out, 1)
        original = out.read_bytes()
        with np.load(out, allow_pickle=False) as z:
            self.assertEqual(set(z.files), native.NPZ_KEYS)
            self.assertEqual(z['metadata_utf8'].dtype, np.uint8)
            self.assertEqual(json.loads(z['metadata_utf8'].tobytes())['window']['start_frame'], 1)
            np.testing.assert_array_equal(z['velocity_x'], ds[1]['fields']['velocity_x'])
            self.assertTrue(all(z[k].dtype.kind != 'O' for k in z.files))
        def partial(handle, **_): handle.write(b'partial'); raise OSError('Injected writer failure')
        for failure in [patch.object(native.np, 'savez', side_effect=partial), patch.object(native.os, 'replace', side_effect=OSError('Injected publication failure')), patch.object(native, 'MAX_NPZ_BYTES', 16)]:
            with failure:
                with self.assertRaises((OSError,native.NativeSequenceError)): ds.write_npz(out)
            self.assertEqual(out.read_bytes(), original); self.assertEqual(list(self.root.glob('.native-sample-*')), [])
        alias = self.root/'alias.zip'; alias.hardlink_to(self.path)
        for path in [self.path, alias]:
            with self.assertRaises(native.NativeSequenceError): ds.write_npz(path)
        self.assertEqual(self.path.read_bytes(), self.raw)
        replacement = self.root/'replacement.zip'; replacement.write_bytes(b'path replaced')
        replacement.replace(self.path)
        with self.assertRaises(native.NativeSequenceError): ds.write_npz(alias)
        self.assertEqual(alias.read_bytes(), self.raw)

    def test_mixed_and_nonsequence_canonical_contracts_remain_exact(self):
        d = Dataset(str(self.root/'data'))
        try:
            rows = d.workbench._all(); bridge = next(r for r in rows if r['kind']=='text')
            bridge = d.workbench.save(bridge['id'],dict(bridge,annotation={'label':'Context'},review='human_reviewed'))
            for selected in [[bridge], [bridge]+[r for r in rows if r['kind']=='sequence']]:
                body={'items':[{k:r[k] for k in ('id','revision','source_revision')} for r in selected],
                    'ratios':{'train':100,'validation':0,'test':0},'seed':42}
                preview=d.releases.preview(body); self.assertTrue(preview['eligible'])
                result=d.releases.create(dict(body,preview_token=preview['preview_token']))
                raw=d.releases.locate(result['id']).read_bytes(); m=json.loads(entries(raw)['manifest.json'])
                self.assertEqual(set(m),native.MANIFEST_KEYS)
                self.assertTrue(all('export_group' not in row for row in m['records']))
                self.invalid(raw)
        finally:d.close()

    def test_truncated_duplicate_unsafe_compressed_json_and_eocd_preflight(self):
        self.invalid(self.raw[:-1])
        self.invalid(pack(entries(self.raw), zipfile.ZIP_DEFLATED))
        values = entries(self.raw); values['../evil'] = b'x'; self.invalid(pack(values))
        values = entries(self.raw); values['manifest.json'] = b'{"schema_version":1,' + values['manifest.json'][1:]; self.invalid(pack(values))
        out = io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:
            z.writestr('manifest.json',b'{}'); z.writestr('manifest.json',b'{}')
        self.invalid(out.getvalue())
        raw = bytearray(self.raw); struct.pack_into('<HH',raw,len(raw)-14,73,73)
        with patch.object(native.zipfile,'ZipFile',side_effect=AssertionError('Count must preflight before ZipFile')):
            self.invalid(bytes(raw))
        with patch.object(native,'MAX_RELEASE_BYTES',len(self.raw)-1): self.invalid(self.raw)
        for filename in ['train/records.jsonl','manifest.json']:
            values=entries(self.raw); values[filename]=values[filename][:-1]; self.invalid(pack(values))

    def test_snapshot_bridges_fixed_deleted_components_and_source_derived_groups(self):
        def family(m): return next(iter(m['protected_components'].values()))
        def remove_bridge(m,_):
            members=[x for x in family(m) if x['kind']=='sequence']; key='component:'+native.sha(encode(sorted(x['id'] for x in members)).encode())
            m['protected_components']={key:members}
            for r in m['records']:r['export_group']=key
        cases=[remove_bridge,
            lambda m,v:family(m).append(copy.deepcopy(family(m)[0])),
            lambda m,v:next(x for x in family(m) if x['id']==m['records'][0]['id']).update(revision=99),
            lambda m,v:next(x for x in family(m) if x['kind']=='text').update(source_split='test'),
            lambda m,v:next(x for x in family(m) if x['kind']=='text').update(source_available=False,source_lineage_known=False),
            lambda m,v:m['records'][1].update(split='test'),
            lambda m,v:m['records'][0].update(groups=['forged-initial-family']),
            lambda m,v:m['records'][0]['annotation']['temporal_labels']['ranges'][0]['start'].update(time_s=1),
            lambda m,v:m['records'][0]['annotation']['temporal_labels']['ranges'][0].update(label=' Human early ')]
        for case in cases:
            with self.subTest(case=case): self.invalid(rewrite(self.raw,case))
        raw=packet(self.root/'deleted',deleted_image=True)
        ds=self.load(raw); deleted=next(x for x in ds[0]['metadata']['declared_family_context'] if x['kind']=='image')
        self.assertFalse(deleted['source_available']);self.assertTrue(deleted['source_lineage_known']);self.assertIsNone(deleted['source_revision'])
        self.invalid(rewrite(raw,lambda m,v:next(x for x in family(m) if x['kind']=='image').update(source_split='test')))

    def test_reviewer_symlink_outer_nested_and_context_source_identity_cases(self):
        def symlink(raw,name):
            values=entries(raw);out=io.BytesIO()
            with zipfile.ZipFile(out,'w') as z:
                for filename,value in values.items():
                    info=zipfile.ZipInfo(filename)
                    if filename==name:info.external_attr=(stat.S_IFLNK|0o777)<<16
                    z.writestr(info,value)
            return out.getvalue()
        self.invalid(symlink(self.raw,'manifest.json'))
        def nested(m,values):
            row=m['records'][0];values[row['asset']]=symlink(values[row['asset']],'run.json')
            digest=native.sha(values[row['asset']]);row.update(content_hash=digest,asset_sha256=digest,source_sha256=digest)
        self.invalid(rewrite(self.raw,nested))
        # Existing unselected text context receives no raw frame interpretation.
        def member(m):return next(x for x in next(iter(m['protected_components'].values())) if x['kind']=='text')
        for change in [{'content_hash':'not-a-SHA256'},{'source_sha256':'not-a-SHA256'},{'source_revision':99},{'book_id':'fake book'},
                       {'pixel_hash':'f'*64},{'source_available':False,'source_lineage_known':False},{'kind':'sequence','source_sha256':'not-a-SHA256'}]:
            self.invalid(rewrite(self.raw,lambda m,v:member(m).update(change)))
        # Binary imports retain immutable text identity/split after deletion.
        # Availability does not grant a bridge target or permit unknown lineage.
        known=copy.deepcopy(member(json.loads(entries(self.raw)['manifest.json'])))
        known.update(source_available=False,source_split='train')
        native.source_identity(known)
        raw=packet(self.root/'unselected-sequence',unselected_sequence=True)
        def unselected(m):
            ids={r['id'] for r in m['records']}
            return next(x for x in next(iter(m['protected_components'].values())) if x['kind']=='sequence' and x['id'] not in ids)
        for change in [{'content_hash':'not-a-SHA256'},{'source_sha256':'not-a-SHA256','source_revision':99},{'source_revision':True},{'source_split':'test'},{'source_sha256':'f'*64}]:
            self.invalid(rewrite(raw,lambda m,v:unselected(m).update(change)))

    def test_rehashed_wrong_axis_stamp_nonfinite_truncated_and_bad_raw_hash(self):
        def malformed(change):
            def edit(m,values):
                row=m['records'][0];parts=entries(values[row['asset']]);run=json.loads(parts['run.json']);frames=[json.loads(x) for x in parts['frames.jsonl'].splitlines()]
                change(run,frames)
                raw=b''.join(json.dumps(f,allow_nan=True).encode()+b'\n' for f in frames)
                run.update(frames_sha256=native.sha(raw),frames_bytes=len(raw));parts.update({'run.json':json.dumps(run).encode(),'frames.jsonl':raw})
                bundle=pack(parts);values[row['asset']]=bundle;row.update(content_hash=native.sha(bundle),asset_sha256=native.sha(bundle),source_sha256=native.sha(bundle))
            return rewrite(self.raw,edit)
        for change in [lambda run,f:run['geometry'].update(axis_order=['z','y','x']),lambda run,f:f[1]['carrier_stamp'].update(version='0'),lambda run,f:f[1]['fields']['pressure'].__setitem__(0,float('nan')),lambda run,f:f.pop()]:
            self.invalid(malformed(change))
        values=entries(self.raw);name=next(n for n in values if n.startswith('assets/'));values[name]=values[name][:-1];self.invalid(pack(values))
        self.invalid(rewrite(self.raw,lambda m,v:m['records'][0]['sequence']['frame_index'][1].update(byte_offset=1)))


if __name__ == '__main__': unittest.main()
