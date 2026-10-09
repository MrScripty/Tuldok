"""Human targets on retained recorded fee7b4a bytes; separate synthetic v2, no run."""
import copy
import hashlib
import io
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from app import Dataset, make_handler
from fixtures.rheon_synthetic_v2 import fixture as v2_fixture
from test_producer_v2_controls import body as v2_body
from test_sequences import body as import_body, fixture as synthetic_fixture
import rheon_sequences
import sequence_temporal_labels as temporal
from workbench import WorkbenchError, encode, labels, validate_annotation

ACTUAL=Path(__file__).parent/'fixtures/rheon_actual_fee7b4a'


def target(record, label='Human observed transition', start=0, end=8, note='Authored visual judgment; no solver truth claimed.'):
    return dict(label=label,start_frame=start,end_frame=end,note=note,
                start=temporal.anchor(record,start),end=temporal.anchor(record,end))


def annotation(record, entries=None, note='Human temporal review rationale.'):
    return {'note':note,'temporal_labels':{'version':1,'origin':temporal.ORIGIN,
        'frame_semantics':temporal.FRAME_SEMANTICS,'source':temporal.source(record),
        'ranges':[target(record)] if entries is None else entries}}


class TemporalLabels(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.d=Dataset(self.tmp.name);self.addCleanup(lambda:self.d.close());self.w=self.d.workbench
        self.run=(ACTUAL/'run.json').read_bytes();self.frames=(ACTUAL/'frames.jsonl').read_bytes()
        self.row=rheon_sequences.admit(self.w,import_body(self.run,self.frames,name='Recorded trajectory',groups=['actual-source']))

    def state(self):return tuple(self.d.db.iterdump())
    def save(self,row,value,review='draft',**changes):
        body=dict(revision=row['revision'],source_revision=row['source_revision'],task='sequence_transport',annotation=value,groups=row['groups'],review=review);body.update(changes)
        return self.w.save(row['id'],body)
    def selection(self,row):return {'items':[{'id':row['id'],'revision':row['revision'],'source_revision':row['source_revision']}],'ratios':{'train':100,'validation':0,'test':0},'seed':42}

    def test_recorded_human_range_roundtrip_legacy_notes_all_endpoints_search_and_history(self):
        raw=self.w.asset(self.row['id'])[0];provenance=copy.deepcopy(self.row['provenance'])
        legacy=self.save(self.row,{'note':' Legacy note '});self.assertEqual(legacy['annotation'],{'note':'Legacy note'})
        entries=[target(legacy,f'frame-{k}',k,k) for k in range(9)]
        entries.append(target(legacy,'Span judgment',0,8))
        a=annotation(legacy,entries);a['temporal_labels']['ranges'][0]['start']['time_s']=0
        a['temporal_labels']['ranges'][0]['end']['time_s']=0
        a['temporal_labels']['ranges'][0]['label']='\u0085 frame-0\u001c';a['temporal_labels']['ranges'][0]['note']=' Rationale '
        saved=self.save(legacy,a);self.assertEqual(saved['review'],'draft');self.assertEqual(saved['revision'],3)
        stored=saved['annotation']['temporal_labels'];self.assertEqual(stored['ranges'][0]['label'],'frame-0');self.assertEqual(stored['ranges'][0]['note'],'Rationale')
        self.assertIs(type(stored['ranges'][0]['start']['time_s']),float);self.assertEqual(stored['ranges'][0]['start']['time_s'],0.0)
        for entry in stored['ranges']:
            for end,key in [('start',entry['start_frame']),('end',entry['end_frame'])]:self.assertEqual(entry[end],temporal.anchor(self.row,key))
        self.assertEqual(labels(saved),[f'frame-{k}' for k in range(9)]+['Span judgment'])
        result=self.w.query({'label':'Span judgment'});self.assertEqual(result['total'],1);self.assertEqual(result['analysis']['labels']['Span judgment'],1)
        self.assertEqual(self.w.query({'q':'frame-8'})['total'],1)
        self.assertEqual(saved['provenance'],provenance);self.assertEqual(saved['sequence'],self.row['sequence']);self.assertEqual(self.w.asset(self.row['id'])[0],raw)
        self.assertEqual(len(self.w.history(self.row['id'])),3)
        self.d.close();self.d=Dataset(self.tmp.name);self.w=self.d.workbench
        self.assertEqual(self.w.get(self.row['id']),saved)
        note_only=self.save(saved,{'note':'Explicit complete-target replacement by legacy client.'})
        self.assertNotIn('temporal_labels',note_only['annotation']);self.assertEqual(self.w.history(self.row['id'])[1]['annotation'],saved['annotation'])

    def test_exact_keys_bounds_duplicates_unicode_numeric_source_and_endpoint_rejections_atomic(self):
        original=annotation(self.row);before=self.state();cases=[]
        def changed(path,value):
            a=copy.deepcopy(original);v=a
            for key in path[:-1]:v=v[key]
            v[path[-1]]=value;return a
        for path,value in [(['extra'],1),(['note'],'x'*4001),(['note'],'\ud800'),
            (['temporal_labels','version'],True),(['temporal_labels','version'],1.0),(['temporal_labels','origin'],'producer_emitted'),
            (['temporal_labels','frame_semantics'],'continuous interval truth'),(['temporal_labels','source','content_hash'],'0'*64),
            (['temporal_labels','source','frames_sha256'],False),(['temporal_labels','ranges'],False),
            (['temporal_labels','ranges',0,'start_frame'],True),(['temporal_labels','ranges',0,'start_frame'],0.0),
            (['temporal_labels','ranges',0,'end_frame'],9),(['temporal_labels','ranges',0,'start_frame'],8),
            (['temporal_labels','ranges',0,'label'],' '*80),(['temporal_labels','ranges',0,'label'],'x'*81),
            (['temporal_labels','ranges',0,'note'],''),(['temporal_labels','ranges',0,'note'],'🦋'*501),
            (['temporal_labels','ranges',0,'label'],'\ud800'),(['temporal_labels','ranges',0,'start','frame'],False),
            (['temporal_labels','ranges',0,'start','frame'],0.0),(['temporal_labels','ranges',0,'start','time_s'],True),
            (['temporal_labels','ranges',0,'start','time_s'],10**400),(['temporal_labels','ranges',0,'start','time_s'],float('nan')),(['temporal_labels','ranges',0,'start','time_s'],0.1),
            (['temporal_labels','ranges',0,'end','sha256'],'f'*64),(['temporal_labels','ranges',0,'end','liquid_stamp','version'],'08')]:
            cases.append(changed(path,value))
        # start8/end8 with old constructor anchor remains a wrong association.
        cases.append(annotation(self.row,[target(self.row,'Duplicate'),target(self.row,' Duplicate ')]))
        cases.append(annotation(self.row,[target(self.row,f'label-{k}') for k in range(17)]))
        cases.append(annotation(self.row,[target(self.row,f'label-{k}',note='\x00'*500) for k in range(16)],note='\x00'*4000))
        cases.append(annotation(self.row,[dict(target(self.row),end_frame=0,start_frame=1)]))
        for a in cases:
            with self.subTest(a=str(a)[:100]):
                with patch.object(self.w.sequences,'asset',side_effect=AssertionError('malformed target preflights before raw load')):
                    with self.assertRaises(WorkbenchError):self.save(self.row,a)
                self.assertEqual(self.state(),before)
        for key in ['carrier_stamp','liquid_stamp']:
            a=copy.deepcopy(original);a['temporal_labels']['ranges'][0]['start'][key]['version']=0
            with self.assertRaises(WorkbenchError):self.save(self.row,a)
        self.assertEqual(self.state(),before)

    def test_overlap_sixteen_and_empty_are_human_targets_not_physical_negatives(self):
        a=annotation(self.row,[target(self.row,f'Human taxonomy {k}',k%9,8) for k in range(16)])
        saved=self.save(self.row,a);self.assertEqual(len(saved['annotation']['temporal_labels']['ranges']),16)
        empty=self.save(saved,annotation(saved,[]));self.assertEqual(empty['review'],'draft');self.assertEqual(labels(empty),[])
        self.assertEqual(empty['annotation']['temporal_labels']['origin'],'human_defined_annotation')
        with self.assertRaises(WorkbenchError):self.save(empty,annotation(empty,[]),'programmatically_verified')
        self.assertEqual(self.w.get(empty['id']),empty)

    def test_cas_rights_revision_source_conflict_raw_metadata_corruption_and_atomic_history_failure(self):
        a=annotation(self.row);before=self.state()
        for key,value in [('revision',0),('revision',True),('source_revision',2)]:
            with patch.object(self.w.sequences,'asset',side_effect=AssertionError('CAS before raw')):
                with self.assertRaises(WorkbenchError) as error:self.save(self.row,a,**{key:value})
                self.assertEqual(error.exception.status,409)
            self.assertEqual(self.state(),before)
        with patch.object(self.w,'_history',side_effect=RuntimeError('injected history failure')):
            with self.assertRaises(RuntimeError):self.save(self.row,a)
        self.assertEqual(self.state(),before)
        corrected=self.w.correct_rights_note(self.row['id'],{'revision':1,'source_revision':1,'note':'Human declared permission note'})['record']
        with self.assertRaises(WorkbenchError) as error:self.save(self.row,a)
        self.assertEqual(error.exception.status,409)
        saved=self.save(corrected,annotation(corrected));before=self.state()
        with self.assertRaises(WorkbenchError):self.save(saved,annotation(saved),groups=['removed-family'])
        self.assertEqual(self.state(),before)
        # Forge both request and stored endpoint metadata, but not original raw frames.
        metadata=copy.deepcopy(saved['sequence']);metadata.pop('bundle_bytes');metadata['frame_index'][0]['time_s']=0.01
        self.d.db.execute('UPDATE workbench_sequence_assets SET metadata_json=?',(encode(metadata),));self.d.db.commit()
        corrupted=self.w._get(saved['id']);before=self.state();raw=self.w.asset(saved['id'])[0]
        with self.assertRaises(WorkbenchError):self.save(corrupted,annotation(corrupted))
        self.assertEqual(self.state(),before);self.assertEqual(self.w.asset(saved['id'])[0],raw)

    def test_canonical_export_alignment_reopen_old_frozen_immutability_and_unselected_family(self):
        saved=self.save(self.row,annotation(self.row,[target(self.row,'Human transition',0,1),target(self.row,'Human late regime',2,8)]))
        self.assertFalse(self.d.releases.preview(self.selection(saved))['eligible'])
        reviewed=self.save(saved,saved['annotation'],'human_reviewed')
        run,frames=synthetic_fixture();relative=rheon_sequences.admit(self.w,import_body(run,frames,name='Explicit synthetic unselected relative'))
        self.assertEqual(relative['sequence']['protected_groups'][1],reviewed['sequence']['protected_groups'][1])
        preview=self.d.releases.preview(self.selection(reviewed));self.assertTrue(preview['eligible']);self.assertEqual(set(preview['lineage'][0]['member_ids']),{reviewed['id'],relative['id']})
        release=self.d.releases.create(dict(self.selection(reviewed),preview_token=preview['preview_token']))
        path=self.d.releases.path/(release['id']+'.zip');frozen=path.read_bytes()
        with zipfile.ZipFile(io.BytesIO(frozen)) as z:
            manifest=json.loads(z.read('manifest.json'));row=manifest['records'][0];rows=[json.loads(line) for line in z.read('train/records.jsonl').splitlines()]
            self.assertEqual(rows,[row]);self.assertEqual(row['annotation'],reviewed['annotation']);self.assertEqual(len(manifest['records']),1)
            bundle=z.read(row['asset']);self.assertEqual(bundle,self.w.asset(reviewed['id'])[0])
            with zipfile.ZipFile(io.BytesIO(bundle)) as inner:
                self.assertEqual(inner.read('run.json'),self.run);self.assertEqual(inner.read('frames.jsonl'),self.frames)
            raw_lines=self.frames.splitlines(keepends=True);frames=[json.loads(line) for line in raw_lines]
            for entry in row['annotation']['temporal_labels']['ranges']:
                for key in ['start','end']:
                    anchor=entry[key];index=anchor['frame'];self.assertEqual(anchor['sha256'],hashlib.sha256(raw_lines[index]).hexdigest())
                    self.assertEqual(anchor['time_s'],frames[index]['time_s']);self.assertEqual(anchor['liquid_stamp'],frames[index]['liquid_stamp'])
            self.assertEqual(row['content_hash'],hashlib.sha256(bundle).hexdigest())
        changed=self.save(reviewed,annotation(reviewed,[target(reviewed,'Changed judgment',1,1)]));self.assertEqual(changed['review'],'draft')
        self.assertEqual(path.read_bytes(),frozen);self.assertEqual(self.w.history(reviewed['id'])[1]['annotation'],reviewed['annotation'])
        self.d.close();self.d=Dataset(self.tmp.name);self.w=self.d.workbench;self.assertEqual(path.read_bytes(),frozen);self.assertEqual(self.w.get(changed['id']),changed)

    def test_persisted_noncanonical_time_binding_and_raw_metadata_fail_preview_freeze_readonly(self):
        reviewed=self.save(self.row,annotation(self.row),'human_reviewed');original=reviewed['annotation'];original_meta=copy.deepcopy(reviewed['sequence']);original_meta.pop('bundle_bytes')
        for mutation in ['integer-time','huge-target-time','huge-metadata-time','unstripped-label','source-hash','endpoint-hash','metadata']:
            a=copy.deepcopy(original)
            if mutation=='integer-time':a['temporal_labels']['ranges'][0]['start']['time_s']=0
            elif mutation=='huge-target-time':a['temporal_labels']['ranges'][0]['start']['time_s']=10**400
            elif mutation=='huge-metadata-time':
                m=copy.deepcopy(original_meta);m['frame_index'][0]['time_s']=10**400;a['temporal_labels']['ranges'][0]['start']['time_s']=10**400
                self.d.db.execute('UPDATE workbench_sequence_assets SET metadata_json=?',(encode(m),))
            elif mutation=='unstripped-label':a['temporal_labels']['ranges'][0]['label']=' '+a['temporal_labels']['ranges'][0]['label']
            elif mutation=='source-hash':a['temporal_labels']['source']['frames_sha256']='0'*64
            elif mutation=='endpoint-hash':a['temporal_labels']['ranges'][0]['start']['sha256']='0'*64
            else:
                m=copy.deepcopy(original_meta);m['frame_index'][0]['sha256']='0'*64;a['temporal_labels']['ranges'][0]['start']['sha256']='0'*64
                self.d.db.execute('UPDATE workbench_sequence_assets SET metadata_json=?',(encode(m),))
            self.d.db.execute('UPDATE workbench_records SET annotation_json=? WHERE id=?',(encode(a),reviewed['id']));self.d.db.commit();before=self.state()
            preview=self.d.releases.preview(self.selection(reviewed));self.assertFalse(preview['eligible']);self.assertTrue(preview['blockers'])
            with self.assertRaises(WorkbenchError):self.d.releases.create(self.selection(reviewed))
            self.assertEqual(self.state(),before);self.assertEqual(list(self.d.releases.path.glob('*.zip')),[])
            self.d.db.execute('UPDATE workbench_sequence_assets SET metadata_json=?',(encode(original_meta),));self.d.db.commit()
        for malformed in [None,False,{'ranges':False},{'ranges':[False,{}, {'label':True}]}]:
            row=dict(reviewed,annotation={'note':'safe','temporal_labels':malformed});self.assertEqual(labels(row),[])
        self.assertEqual(len(labels(dict(reviewed,annotation={'temporal_labels':{'ranges':[{'label':'x'}]*100}}))),16)

    def test_synthetic_v2_temporal_labels_do_not_modify_original_controls_or_provenance(self):
        files=v2_fixture();row=rheon_sequences.admit(self.w,v2_body(files));bundle=self.w.asset(row['id'])[0]
        saved=self.save(row,annotation(row,[target(row,'Human single accepted state',8,8)]),'human_reviewed')
        self.assertEqual(saved['provenance'],row['provenance']);self.assertEqual(saved['sequence'],row['sequence']);self.assertEqual(self.w.asset(row['id'])[0],bundle)
        with zipfile.ZipFile(io.BytesIO(bundle)) as z:self.assertEqual(z.read('controls.json'),files[2])
        self.assertEqual(saved['annotation']['temporal_labels']['origin'],'human_defined_annotation')

    def test_actual_http_numeric_zero_normalization_save_reopen_and_conflicting_revision(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.d));self.addCleanup(server.server_close)
        threading.Thread(target=server.serve_forever,daemon=True).start();self.addCleanup(server.shutdown)
        url=f'http://127.0.0.1:{server.server_port}/api/workbench/records/{self.row["id"]}'
        a=annotation(self.row);a['temporal_labels']['ranges'][0]['start']['time_s']=0
        body={'revision':1,'source_revision':1,'task':'sequence_transport','annotation':a,'groups':self.row['groups'],'review':'draft'}
        request=lambda:urllib.request.Request(url,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
        before=self.state();body['annotation']['temporal_labels']['ranges'][0]['start']['time_s']=10**400
        with self.assertRaises(urllib.error.HTTPError) as huge:urllib.request.urlopen(request())
        self.assertEqual(huge.exception.code,400);self.assertIn('endpoint time',json.load(huge.exception)['error']);self.assertEqual(self.state(),before)
        body['annotation']['temporal_labels']['ranges'][0]['start']['time_s']=0
        with urllib.request.urlopen(request()) as response:saved=json.load(response)
        self.assertIs(type(saved['annotation']['temporal_labels']['ranges'][0]['start']['time_s']),float)
        with urllib.request.urlopen(url) as response:self.assertEqual(json.load(response),saved)
        with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(request())
        self.assertEqual(error.exception.code,409);self.assertEqual(len(self.w.history(self.row['id'])),2)
