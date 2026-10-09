"""Authored Unicode passages and atomic source/review/family lifecycles."""
import copy
import hashlib
import json
import tempfile
import unittest
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from app import Dataset
import grounded_instructions as g
from workbench import WorkbenchError


class GroundedInstructionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.d = Dataset(self.temp.name); self.addCleanup(lambda: self.d.close())
        self.w, self.r = self.d.workbench, self.d.releases
        self.sources = [self.w.import_asset(dict(kind='text', name=name, text=text, groups=[name], rights='Authored local fixture')) for name, text in [('north', ' Header 😀\r\nNorth holds 7 e\u0301 cups.\n '), ('south', 'South holds 5 cups.\n Footer')]]

    def body(self):
        return dict(request_id=uuid.uuid4().hex, name='Compare sources', question=' How many cups together?\r\n ', contexts=[g.reference(source, 1, len(source['text'])-1) for source in self.sources])

    def prompt(self):
        return g.admit(self.w, self.body())['record']

    def answer(self, parent, answer=None, review='human_reviewed', completion=' 12 cups.\r\n😀 e\u0301 '):
        return self.w.save_response(dict(id=answer['id'] if answer else uuid.uuid4().hex, prompt_id=parent['id'], revision=answer['revision'] if answer else 0, parent_revision=parent['revision'], source_revision=parent['source_revision'], completion=completion, review=review))['response']

    def release_body(self, parent, answer):
        return dict(format='text_instruction_v1', items=[dict(id=answer['id'], revision=answer['revision'], prompt_id=parent['id'], parent_revision=parent['revision'], source_revision=parent['source_revision'])], ratios=dict(train=100, validation=0, test=0), seed=42)

    def edit_source(self, index=0):
        source=self.w.get(self.sources[index]['id'])
        self.sources[index] = self.w.correct_rights_note(source['id'], dict(revision=source['revision'], source_revision=source['source_revision'], note='Updated permission statement'))['record']

    def repair(self, parent):
        refs=[g.reference(self.w.get(item['ref']['id']), item['ref']['start'], item['ref']['end']) for item in parent['grounded_context_binding']]
        return g.reinspect(self.w, parent['id'], dict(revision=parent['revision'], source_revision=parent['source_revision'], contexts=refs))['record']

    def test_repeat_concurrent_admission_is_single_atomic_draft_and_immutable_creation(self):
        body=self.body()
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(lambda _:g.admit(self.w,body),range(2)))
        self.assertEqual(sum(result['created'] for result in results),1)
        parent=results[0]['record'];self.assertEqual(parent,results[1]['record'])
        self.assertEqual(parent['review'],'draft');self.assertEqual(parent['annotation'],None)
        self.assertEqual(parent['parents'],[source['id'] for source in self.sources]);self.assertEqual(self.w.responses(parent['id'])['responses'],[])
        self.assertEqual(parent['text'],g.compose(body['question'].replace('\r\n','\n'),body['contexts']))
        self.edit_source();self.assertEqual(g.admit(self.w,body)['record'],parent)
        with self.assertRaises(WorkbenchError):g.admit(self.w,dict(body,question='Different'))
        self.assertEqual(len(self.w.history(parent['id'])),1)
        self.d.close();self.d=Dataset(self.temp.name);self.w,self.r=self.d.workbench,self.d.releases
        self.assertEqual(g.admit(self.w,body)['record'],parent)

    def test_malformed_refs_resource_bounds_and_atomic_history_refusal(self):
        original=self.body();before=len(self.w._all())
        for change in [dict(revision=True),dict(revision=999),dict(source_revision=True),dict(content_hash='0'*64),dict(start=True),dict(end=999999),dict(quote='invented'),dict(start=-1),dict(end=0),dict(extra='field')]:
            body=copy.deepcopy(original);body['contexts'][0].update(change)
            with self.subTest(change=change),self.assertRaises(WorkbenchError):g.admit(self.w,body)
        for body in [dict(original,contexts=original['contexts'][:1]),dict(original,contexts=original['contexts']*2),dict(original,question='x'*4001),dict(original,question='\u0344'*4000),dict(original,question='\ud800'),dict(original,verified=True)]:
            with self.assertRaises(WorkbenchError):g.admit(self.w,body)
        with patch.object(g,'MAX_REQUEST',10),self.assertRaises(WorkbenchError):g.admit(self.w,original)
        self.assertEqual(len(self.w._all()),before)
        self.d.db.execute("CREATE TRIGGER fail_composed_history BEFORE INSERT ON workbench_history BEGIN SELECT RAISE(ABORT,'fixture'); END")
        with self.assertRaises(Exception):g.admit(self.w,original)
        self.assertEqual(len(self.w._all()),before);self.assertEqual(self.d.db.execute('SELECT count(*) FROM instruction_compositions').fetchone()[0],0)
        for raw in [b'{"request_id":1,"request_id":2}',b'{"x":NaN}',b'{',b'\xff']:
            with self.assertRaises(WorkbenchError):g.parse(raw)

    def test_current_context_changes_block_noop_save_export_and_deliberate_repair_resets_all_answers(self):
        parent=self.prompt();a=self.answer(parent);b=self.answer(parent,review='draft',completion='Other draft')
        body=self.release_body(parent,a);self.assertTrue(self.r.preview(body)['eligible'])
        creation=parent['provenance'];origin=a['provenance'];self.edit_source()
        self.assertFalse(g.inspect(self.w,parent['id'])['current']);self.assertFalse(self.r.preview(body)['eligible'])
        with self.assertRaises(WorkbenchError):self.answer(parent,a,completion=a['completion'])
        repaired=self.repair(parent);self.assertEqual(repaired['provenance'],creation);self.assertEqual(repaired['revision'],2)
        answers=self.w.responses(parent['id'])['responses'];self.assertEqual({r['review'] for r in answers},{'draft'});self.assertEqual({r['revision'] for r in answers},{2})
        self.assertEqual(self.w._response(a['id'])['provenance'],origin);self.assertEqual(self.w.response_history(a['id'])['history'][0]['response'],a)
        current=self.w._response(a['id']);reviewed=self.answer(repaired,current,completion=current['completion'])
        self.assertNotEqual(reviewed['grounded_binding_sha256'],a['grounded_binding_sha256']);self.assertEqual(reviewed['provenance'],origin)
        self.assertTrue(self.r.preview(self.release_body(repaired,reviewed))['eligible']);self.assertFalse(self.r.preview(body)['eligible'])
        noop=g.reinspect(self.w,repaired['id'],dict(revision=repaired['revision'],source_revision=1,contexts=[item['ref'] for item in repaired['grounded_context_binding']]))
        self.assertFalse(noop['changed']);self.assertEqual(self.w._response(reviewed['id']),reviewed)

    def test_generic_prompt_metadata_edit_cannot_carry_unchanged_answer_approval(self):
        parent=self.prompt();a=self.answer(parent)
        changed=self.w.correct_rights_note(parent['id'],dict(revision=1,source_revision=1,note='Question rights clarified'))['record']
        body=self.release_body(changed,a);self.assertFalse(self.r.preview(body)['eligible'])
        reviewed=self.answer(changed,a,completion=a['completion']);self.assertEqual(reviewed['revision'],2)
        self.assertTrue(self.r.preview(self.release_body(changed,reviewed))['eligible'])
        for completion in ['x'*20001,'\ud800',' ']:
            with self.assertRaises(WorkbenchError):self.answer(changed,completion=completion)
        self.assertEqual(len(self.answer(changed,completion='x'*20000)['completion']),20000)

    def test_repair_history_failure_resets_nothing_and_preserves_old_binding(self):
        parent=self.prompt();a=self.answer(parent);self.edit_source()
        self.d.db.execute("CREATE TRIGGER fail_repair_history BEFORE INSERT ON workbench_response_history BEGIN SELECT RAISE(ABORT,'fixture'); END")
        with self.assertRaises(Exception):self.repair(parent)
        self.assertEqual(self.w.get(parent['id']),parent);self.assertEqual(self.w._response(a['id']),a)
        self.assertEqual(len(self.w.history(parent['id'])),1)

    def test_tombstone_blocks_generic_and_grounded_use_keeps_family_and_frozen_bytes(self):
        parent=self.prompt();a=self.answer(parent);body=self.release_body(parent,a);proof=self.r.preview(body)
        release=self.r.create(dict(body,preview_token=proof['preview_token']));path=self.r.locate(release['id']);frozen=path.read_bytes()
        source=self.sources[0];self.w.save(source['id'],dict(source,task='text_corpus',annotation=dict(note='Authored'),review='human_reviewed'))
        source=self.w.get(source['id']);self.w.delete_text(source['id'],dict(revision=source['revision'],source_revision=1))
        deleted=self.w.get(source['id']);self.assertFalse(deleted['source_available']);self.assertTrue(deleted['source_lineage_known'])
        self.assertEqual(deleted['parents'],source['parents']);self.assertEqual(deleted['groups'],source['groups']);self.assertEqual(deleted['text'],source['text'])
        self.assertFalse(self.r.preview(body)['eligible']);self.assertEqual(path.read_bytes(),frozen)
        with self.assertRaises(WorkbenchError):self.w.asset(source['id'])
        with self.assertRaises(WorkbenchError):self.w.save(source['id'],dict(deleted,task='text_corpus',annotation=dict(note='No'),review='human_reviewed'))
        with self.assertRaises(WorkbenchError):self.answer(deleted)
        with self.assertRaises(WorkbenchError):self.repair(parent)
        for format_name in ['canonical_v1','text_corpus_v1','text_retrieval_v1']:
            p=self.r.preview(dict(format=format_name,items=[dict(id=deleted['id'],revision=deleted['revision'],source_revision=1)],ratios=dict(train=100,validation=0,test=0),seed=42))
            self.assertFalse(p['eligible'],p)
        from dataset_releases import family_context
        roots,_,_,lineage=family_context([parent],self.w._all());self.assertEqual(roots[parent['id']],roots[deleted['id']]);self.assertIn(deleted['id'],lineage[0]['deleted_ids'])

    def test_export_full_source_offsets_bindings_families_and_atomic_publisher(self):
        parent=self.prompt();a=self.answer(parent);body=self.release_body(parent,a);preview=self.r.preview(body)
        release=self.r.create(dict(body,preview_token=preview['preview_token']));path=self.r.locate(release['id']);before=path.read_bytes()
        with zipfile.ZipFile(path) as z:
            manifest=json.loads(z.read('manifest.json'));sources={s['id']:s for s in manifest['grounded_sources']}
            self.assertEqual(set(sources),set(parent['parents']))
            for ref in [item['ref'] for item in parent['grounded_context_binding']]:
                raw=z.read('contexts/'+ref['id']+'.txt');self.assertEqual(hashlib.sha256(raw).hexdigest(),ref['content_hash']);self.assertEqual(raw.decode()[ref['start']:ref['end']],ref['quote'])
            rows=[json.loads(line) for line in z.read('train/data.jsonl').splitlines()];self.assertEqual(rows,[dict(prompt=parent['text'],completion=a['completion'])])
            self.assertEqual(sum(info.file_size for info in z.infolist()),preview['artifact_bytes'])
            self.assertEqual(len(preview['lineage']),1);self.assertEqual(set(preview['lineage'][0]['member_ids']),set(parent['parents']+[parent['id']]))
        with patch('dataset_releases.os.replace',side_effect=OSError('fixture')):
            with self.assertRaises(OSError):self.r.create(dict(body,preview_token=preview['preview_token']))
        self.assertEqual(path.read_bytes(),before);self.assertEqual(len(list(self.r.path.iterdir())),1)

    def test_fixed_split_conflicting_unselected_ancestors_refuse_admission_and_deleted_bridges_remain(self):
        from PIL import Image
        import base64,io
        images=[]
        for index,split in enumerate(['train','test']):
            stream=io.BytesIO();Image.new('RGB',(4,4),(index*100,20,30)).save(stream,format='PNG')
            images.append(self.w.import_asset(dict(kind='image',image=base64.b64encode(stream.getvalue()).decode(),name=split,groups=[split],rights='Authored'),source_split=split))
            self.sources[index]=self.w.import_asset(dict(kind='text',name='Fixed '+split,text='Fixed context '+split,groups=['fixed-'+split],parents=[images[-1]['id']],rights='Authored'))
        self.d.delete(images[1]['id'],dict(revision=images[1]['source_revision']))
        before=len(self.w._all())
        with self.assertRaises(WorkbenchError) as caught:g.admit(self.w,self.body())
        self.assertIn('conflicting fixed',str(caught.exception));self.assertEqual(len(self.w._all()),before)
        self.assertEqual(self.d.db.execute('SELECT count(*) FROM instruction_compositions').fetchone()[0],0)

    def test_prospective_group_bridge_fixed_split_conflict_is_atomic(self):
        from PIL import Image
        import base64,io
        request=self.body()
        for index,split in enumerate(['train','test']):
            stream=io.BytesIO();Image.new('RGB',(4,4),(index*100,20,40)).save(stream,format='PNG')
            image=self.w.import_asset(dict(kind='image',image=base64.b64encode(stream.getvalue()).decode(),name=split,groups=[split],rights='Authored'),source_split=split)
            if index==0:
                self.sources[0]=self.w.import_asset(dict(kind='text',name='Train source',text='Source tied to train',groups=['train-source'],parents=[image['id']],rights='Authored'))
                request['contexts'][0]=g.reference(self.sources[0],0,len(self.sources[0]['text']))
            else:
                self.w.import_asset(dict(kind='text',name='Prospective group bridge',text='Existing unrelated group bridge',groups=['grounded:'+request['request_id']],parents=[image['id']],rights='Authored'))
        before=len(self.w._all())
        with self.assertRaises(WorkbenchError) as caught:g.admit(self.w,request)
        self.assertIn('conflicting fixed',str(caught.exception));self.assertEqual(len(self.w._all()),before)
        self.assertEqual(self.d.db.execute('SELECT count(*) FROM instruction_compositions').fetchone()[0],0)

    def test_creation_family_members_survive_group_edit_and_deleted_bridge(self):
        sibling=self.w.import_asset(dict(kind='text',name='Original north family sibling',text='Other north family data',groups=['north'],rights='Authored'))
        parent=self.prompt();a=self.answer(parent)
        source=self.sources[0]
        self.sources[0]=self.w.save(source['id'],dict(source,groups=['replacement-group'],task='text_corpus',annotation=dict(note='Changed groups'),review='draft'))
        repaired=self.repair(parent)
        from dataset_releases import connected_components
        roots=connected_components(self.w._all());self.assertEqual(roots[parent['id']],roots[sibling['id']])
        self.w.delete_text(sibling['id'],dict(revision=sibling['revision'],source_revision=1))
        current=self.w._response(a['id']);reviewed=self.answer(repaired,current,completion=current['completion'])
        preview=self.r.preview(self.release_body(repaired,reviewed));self.assertTrue(preview['eligible'],preview)
        self.assertIn(sibling['id'],preview['lineage'][0]['deleted_ids'])

    def test_preference_review_cannot_bypass_stale_contexts_and_freezes_exact_evidence(self):
        from preferences import SELECTION_FIELDS
        parent=self.prompt();a=self.answer(parent);b=self.answer(parent,completion='Other independently authored answer')
        body=dict(id=uuid.uuid4().hex,revision=0,prompt_id=parent['id'],parent_revision=parent['revision'],source_revision=1,left_id=a['id'],left_revision=a['revision'],right_id=b['id'],right_revision=b['revision'],outcome='left',rationale='Human compares against both sources',review='human_reviewed')
        judgment=self.w.preferences.save(body)['judgment']
        release_body=dict(format='text_preference_v1',items=[{k:judgment[k] for k in SELECTION_FIELDS}],ratios=dict(train=100,validation=0,test=0),seed=42)
        preview=self.r.preview(release_body);self.assertTrue(preview['eligible'],preview)
        release=self.r.create(dict(release_body,preview_token=preview['preview_token']));frozen=self.r.locate(release['id']).read_bytes()
        with zipfile.ZipFile(self.r.locate(release['id'])) as z:
            manifest=json.loads(z.read('manifest.json'));self.assertEqual({s['id'] for s in manifest['grounded_sources']},set(parent['parents']))
            for source in manifest['grounded_sources']:self.assertEqual(z.read('contexts/'+source['id']+'.txt'),source['text'].encode())
        self.edit_source();self.assertFalse(self.r.preview(release_body)['eligible'])
        with self.assertRaises(WorkbenchError):self.w.preferences.save(dict(body,revision=1))
        source=self.sources[0];self.w.delete_text(source['id'],dict(revision=source['revision'],source_revision=1))
        self.assertFalse(self.r.preview(release_body)['eligible']);self.assertEqual(self.r.locate(release['id']).read_bytes(),frozen)

    def test_canonical_question_expansion_boundary_is_measured_after_nfc(self):
        request=self.body();request['question']='\u0344'*2000
        parent=g.admit(self.w,request)['record'];self.assertEqual(len(parent['provenance']['grounded_instruction']['question']),4000)

    def test_reader_independently_refuses_family_split_snapshot_and_graph_mismatches(self):
        import importlib.util
        from pathlib import Path
        spec=importlib.util.spec_from_file_location('instruction_checker',Path(__file__).with_name('check_instruction_consumer.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        parent=self.prompt();a=self.answer(parent);b=self.answer(parent,completion='Second reviewed answer')
        body=self.release_body(parent,a);body['items'].append(self.release_body(parent,b)['items'][0])
        preview=self.r.preview(body);release=self.r.create(dict(body,preview_token=preview['preview_token']))
        with zipfile.ZipFile(self.r.locate(release['id'])) as z:
            manifest=json.loads(z.read('manifest.json'));mapping=[json.loads(line) for line in z.read('rows.jsonl').splitlines()]
        module.check_families(manifest,mapping)
        bad=copy.deepcopy(mapping);bad[1]['split']='validation'
        with self.assertRaises(AssertionError):module.check_families(manifest,bad)
        bad=copy.deepcopy(manifest);bad['grounded_sources'][0]['revision']+=1
        with self.assertRaises(AssertionError):module.check_families(bad,mapping)
        bad=copy.deepcopy(manifest);family=mapping[0]['family'];member=copy.deepcopy(bad['protected_components'][family][0]);member.update(id=uuid.uuid4().hex,groups=['disconnected'],parents=[],content_hash='7'*64);bad['protected_components'][family].append(member)
        with self.assertRaises(AssertionError):module.check_families(bad,mapping)

    def test_http_duplicate_fields_and_nonfinite_requests_refuse_without_delete(self):
        from http.server import ThreadingHTTPServer
        import threading,urllib.request,urllib.error
        from app import make_handler
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.d));threading.Thread(target=server.serve_forever,daemon=True).start();self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        source=self.sources[0]
        for route,raw in [('text-delete/'+source['id'],b'{"revision":1,"revision":1,"source_revision":1}'),('text-delete/'+source['id'],b'{"revision":NaN,"source_revision":1}'),('instruction-compose',b'{"request_id":"a","request_id":"b"}')]:
            req=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/workbench/'+route,data=raw,headers={'Content-Type':'application/json'})
            with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(req)
            self.assertEqual(caught.exception.code,400)
        self.assertTrue(self.w.get(source['id'])['source_available']);self.assertEqual(len(self.w._all()),2)

    def test_tombstone_history_failure_rolls_back_availability(self):
        source=self.sources[0]
        self.d.db.execute("CREATE TRIGGER fail_tombstone_history BEFORE INSERT ON workbench_history BEGIN SELECT RAISE(ABORT,'fixture'); END")
        with self.assertRaises(Exception):self.w.delete_text(source['id'],dict(revision=1,source_revision=1))
        self.assertEqual(self.w.get(source['id']),source);self.assertEqual(self.w.asset(source['id'])[0],source['text'].encode())
