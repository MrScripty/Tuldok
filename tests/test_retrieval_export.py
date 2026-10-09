"""Authored retrieval judgments, exact frozen bytes, unchanged consumer shapes."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import threading
import urllib.request
import urllib.error
import http.client
import io
import base64
from PIL import Image
from http.server import ThreadingHTTPServer
from app import make_handler
from app import Dataset
from dataset_releases import connected_components
import dataset_releases
import retrieval_export as r
from workbench import WorkbenchError, encode


def ref(row): return {k:row[k] for k in ('id','revision','source_revision')}


class Retrieval(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.d=Dataset(self.tmp.name);self.addCleanup(self.d.close);self.w=self.d.workbench

    def save(self,row,annotation,review='human_reviewed',**options):
        return self.w.save(row['id'],dict(revision=row['revision'],source_revision=row['source_revision'],
            task='text_retrieval',annotation=annotation,groups=row['groups'],review=review),**options)

    def document(self,text,group):
        row=self.w.import_asset(dict(kind='text',text=text,groups=[group],rights='Authored fixture'))
        return self.save(row,{'role':'document','note':'Explicit document review'})

    def query(self,text,docs,group):
        row=r.import_query(self.w,dict(name='Query',text=text,groups=[group],rights='Authored fixture',positive_refs=[ref(d) for d in docs]))
        return self.save(row,{'role':'query','note':'Explicit positive relevance review','positive_refs':[ref(d) for d in docs]})

    def fixture(self):
        rows=[]
        for g in ['orchard','garden','river']:
            for i in range(2):
                doc=self.document(f'{g} recipe {i}: café, water and sunlight.\n',g);rows.append(doc)
                rows.append(self.query(f'How to {g} recipe {i}?\n',[doc],g))
        return rows

    def body(self,rows):return dict(format=r.FORMAT,items=[ref(row) for row in rows],ratios={'train':34,'validation':33,'test':33},seed=42)
    def state(self):return tuple(self.d.db.iterdump())

    def test_raw_query_is_separate_draft_with_declared_refs_and_no_review_grant(self):
        doc=self.document('Café source text','source');body=dict(name='Query',text='Find café source?',groups=['query-source'],rights='unknown',positive_refs=[ref(doc)])
        row=r.import_query(self.w,body)
        self.assertEqual((row['review'],row['annotation'],row['task']),('draft',None,'text_classification'))
        self.assertEqual(row['parents'],[doc['id']]);self.assertEqual(row['provenance']['acquisition']['declared_positive_refs'],[ref(doc)])
        before=self.state()
        for change in ({'positive_refs':[dict(ref(doc),revision=1)]},{'positive_refs':[dict(ref(doc),revision=True)]},{'review':'human_reviewed'}):
            with self.assertRaises(WorkbenchError):r.import_query(self.w,dict(body,**change))
            self.assertEqual(self.state(),before)

    def test_closed_annotation_human_only_stale_refs_and_parent_boundaries(self):
        d=self.document('Document one','one');other=self.document('Other document','other');q=self.query('Question one?',[d],'one');before=self.state()
        for a in [{'role':'document','note':'x','positive_refs':[]},{'role':'query','note':'x','positive_refs':[]},
            {'role':'query','note':'x','positive_refs':[ref(d),ref(d)]},
            {'role':'query','note':'x','positive_refs':[ref(other)]},
            {'role':'query','note':'x','positive_refs':[dict(ref(d),source_revision=True)]}]:
            with self.assertRaises(WorkbenchError):self.save(q,a)
            self.assertEqual(self.state(),before)
        with self.assertRaises(WorkbenchError):self.save(q,q['annotation'],review='programmatically_verified',verified_provenance={'method':'test verifier'})
        d=self.save(d,{'role':'document','note':'New explicit document review'})
        with self.assertRaises(WorkbenchError):self.save(q,q['annotation'])
        fixed=self.save(q,dict(q['annotation'],positive_refs=[ref(d)]));self.assertEqual(fixed['review'],'human_reviewed')
        self.assertEqual(len(self.w.history(q['id'])),3)

    def test_frozen_exact_projection_files_review_family_mapping_and_persistence(self):
        rows=self.fixture();body=self.body(rows);before=self.state();p=self.d.releases.preview(body)
        self.assertTrue(p['eligible'],p);self.assertEqual(self.state(),before)
        self.assertEqual(p['retrieval_counts']['train']['distinct_positive_documents'],2)
        out=self.d.releases.create(dict(body,preview_token=p['preview_token']));z=zipfile.ZipFile(self.d.releases.locate(out['id']))
        m=json.loads(z.read('manifest.json'));self.assertEqual(m['records'],sorted(rows,key=lambda row:row['id']))
        files={n:[json.loads(line) for line in z.read(n).splitlines()] for n in r.STREAM_FILES};docs={d['doc_id']:d for d in files['corpus.jsonl']}
        self.assertEqual(len(docs),6);self.assertEqual(len(files['queries.jsonl']),6);self.assertEqual(len(files['train_pairs.jsonl']),2)
        for d in docs.values():self.assertEqual(set(d),{'doc_id','text','group','split'})
        for q in files['queries.jsonl']:
            self.assertEqual(set(q),{'query_id','text','relevant_doc_ids','split'})
            for ident in q['relevant_doc_ids']:self.assertEqual(docs[ident]['split'],q['split'])
        for pair in files['train_pairs.jsonl']:
            self.assertEqual(set(pair),{'query','positive','doc_id','group'});self.assertEqual(pair['positive'],docs[pair['doc_id']]['text']);self.assertEqual(docs[pair['doc_id']]['split'],'train')
        for row in rows:
            self.assertEqual(z.read('assets/'+row['id']+'.txt'),row['text'].encode())
        for n,proof in m['files'].items():self.assertEqual(proof,{'bytes':len(z.read(n)),'sha256':hashlib.sha256(z.read(n)).hexdigest()})
        raw=self.d.releases.locate(out['id']).read_bytes();self.save(rows[0],{'role':'document','note':'Later human review'})
        self.assertEqual(self.d.releases.locate(out['id']).read_bytes(),raw)
        self.assertFalse(self.d.releases.preview(body)['eligible'])

    def test_stale_positive_requires_deliberate_ref_repair_and_old_token_never_publishes(self):
        rows=self.fixture();body=self.body(rows);p=self.d.releases.preview(body);d=rows[0];q=rows[1]
        updated=self.w.correct_rights_note(d['id'],dict(revision=d['revision'],source_revision=1,note='Corrected authorship'))['record']
        rows[0]=updated;stale=self.d.releases.preview(self.body(rows));self.assertFalse(stale['eligible']);self.assertEqual(stale['blockers'][0]['code'],'conflict')
        with self.assertRaises(WorkbenchError):self.d.releases.create(dict(body,preview_token=p['preview_token']))
        rows[1]=self.save(q,dict(q['annotation'],positive_refs=[ref(updated)]));fresh=self.d.releases.preview(self.body(rows));self.assertTrue(fresh['eligible'])
        with self.assertRaises(WorkbenchError):self.d.releases.create(dict(self.body(rows),preview_token=p['preview_token']))

    def test_missing_unreviewed_positives_and_multi_positive_train_are_not_silently_repaired(self):
        rows=self.fixture();p=self.d.releases.preview(self.body(rows))
        training=[i for i,row in enumerate(rows) if p['assignments'][row['id']]=='train'];d1,d2=[rows[i] for i in training if rows[i]['annotation']['role']=='document']
        extra=self.query('A multi positive training question',[d1,d2],d1['groups'][0]);selected=rows+[extra]
        bad=self.d.releases.preview(self.body(selected));self.assertFalse(bad['eligible']);self.assertIn('exactly one',bad['blockers'][0]['message'])
        missing=self.d.releases.preview(self.body([row for row in rows if row['id']!=d1['id']]));self.assertFalse(missing['eligible'])

    def test_formatted_anchor_collision_and_family_bridge_fail_closed(self):
        rows=self.fixture();d=rows[0];q=rows[1];alias=self.query(q['text'].strip(),[d],d['groups'][0])
        p=self.d.releases.preview(self.body(rows+[alias]));self.assertFalse(p['eligible']);self.assertIn('anchors repeat',p['blockers'][0]['message'])
        self.w.import_asset(dict(kind='text',text='Unselected bridge',groups=['orchard','garden']))
        p=self.d.releases.preview(self.body(rows));self.assertFalse(p['eligible']);self.assertIn('Too few independent',p['blockers'][0]['message'])

    def test_complete_byte_bound_and_atomic_failure_remove_partial_release(self):
        rows=self.fixture();body=self.body(rows);p=self.d.releases.preview(body)
        with patch.object(r,'MAX_SELECTED_TEXT_BYTES',100):
            self.assertFalse(self.d.releases.preview(body)['eligible'])
        before=self.state();files=list(self.d.releases.path.iterdir())
        with patch.object(dataset_releases.os,'replace',side_effect=OSError('controlled atomic failure')):
            with self.assertRaises(OSError):self.d.releases.create(dict(body,preview_token=p['preview_token']))
        self.assertEqual(self.state(),before);self.assertEqual(list(self.d.releases.path.iterdir()),files)

    def test_preview_rollback_even_lazy_enrollment(self):
        rows=self.fixture();body=self.body(rows);original=self.w._all;before=self.state()
        def lazy():
            self.d.db.execute("UPDATE workbench_records SET name='must rollback'")
            return original()
        with patch.object(self.w,'_all',side_effect=lazy):self.assertTrue(self.d.releases.preview(body)['eligible'])
        self.assertEqual(self.state(),before)

    def test_actual_http_strict_query_cap_invalid_ref_atomic_then_valid(self):
        doc=self.document('HTTP document fixture','http-source')
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.d));self.addCleanup(server.server_close)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();self.addCleanup(server.shutdown)
        url=f'http://127.0.0.1:{server.server_port}/api/workbench/retrieval-query';before=self.state()
        body=dict(name='Query',text='Find HTTP fixture?',groups=['http-query'],rights='unknown',positive_refs=[ref(doc)])
        connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
        self.addCleanup(connection.close)
        connection.putrequest('POST','/api/workbench/retrieval-query')
        connection.putheader('Content-Type','application/json')
        connection.putheader('Content-Length',str(r.MAX_REQUEST+1));connection.endheaders()
        response=connection.getresponse();self.assertEqual(response.status,400);response.read()
        self.assertEqual(self.state(),before)
        raws=[b'{"name":1,"name":2}',b'{"name":NaN}',encode(dict(body,positive_refs=[dict(ref(doc),revision=1)])).encode()]
        for raw in raws:
            with self.assertRaises(urllib.error.HTTPError) as c:
                urllib.request.urlopen(urllib.request.Request(url,data=raw,headers={'Content-Type':'application/json'}))
            self.assertIn(c.exception.code,(400,409));self.assertEqual(self.state(),before)
        with urllib.request.urlopen(urllib.request.Request(url,data=encode(body).encode(),headers={'Content-Type':'application/json'})) as response:
            row=json.load(response);self.assertEqual(response.status,201);self.assertEqual(row['parents'],[doc['id']]);self.assertIsNone(row['annotation'])

    def test_canonical_archival_export_rechecks_relevance_authority_and_stale_refs(self):
        doc=self.document('Canonical relevance document','canonical');q=self.query('Canonical question?',[doc],'canonical')
        body=dict(items=[ref(q)],ratios={'train':100,'validation':0,'test':0},seed=42)
        self.assertTrue(self.d.releases.preview(body)['eligible'])
        updated=self.save(doc,{'role':'document','note':'Revised review'})
        self.assertFalse(self.d.releases.preview(body)['eligible'])
        with self.assertRaises(WorkbenchError):self.d.releases.create(body)
        q=self.save(q,dict(q['annotation'],positive_refs=[ref(updated)]));body['items']=[ref(q)]
        self.assertTrue(self.d.releases.preview(body)['eligible'])
        self.save(updated,{'role':'document','note':'Draft revision'},review='draft')
        self.assertFalse(self.d.releases.preview(body)['eligible'])

    def test_former_positive_parent_is_retained_even_after_judgment_changes(self):
        d1=self.document('First independent document','first');d2=self.document('Former independent document','former')
        image=io.BytesIO();Image.new('RGB',(2,2),'red').save(image,'PNG')
        bridge=self.w.import_asset(dict(kind='image',image=base64.b64encode(image.getvalue()).decode(),groups=['former'],rights='Authored'),source_split='validation')
        self.d.delete(bridge['id'],{'revision':bridge['source_revision']})
        q=self.query('Question initially relevant to both',[d1,d2],'separate-query')
        q=self.save(q,dict(q['annotation'],positive_refs=[ref(d1)]))
        self.assertEqual(q['parents'],[d1['id'],d2['id']]);self.assertEqual(q['annotation']['positive_refs'],[ref(d1)])
        roots=connected_components(self.w._all());self.assertEqual(roots[q['id']],roots[d2['id']])
        rows=[d1,q]
        for group in ['independent-other','independent-last']:
            for i in range(2):
                doc=self.document(f'{group} document {i}',group);rows.extend([doc,self.query(f'{group} question {i}?',[doc],group)])
        preview=self.d.releases.preview(self.body(rows));self.assertTrue(preview['eligible'],preview)
        family=next(f for f in preview['lineage'] if q['id'] in f['selected_ids'])
        self.assertIn(d2['id'],family['member_ids']);self.assertNotIn(d2['id'],family['selected_ids'])
        self.assertEqual(family['deleted_ids'],[bridge['id']]);self.assertEqual(family['fixed_splits'],['validation'])
        self.assertEqual(preview['assignments'][q['id']],'validation');self.assertEqual(preview['assignments'][d1['id']],'validation')
        prepared=r.prepare(self.d.releases,self.body(rows))
        self.assertIn(bridge['id'],{pin['id'] for pins in prepared['snapshots'].values() for pin in pins})
        d3=self.document('Another evaluation positive','first')
        multi=self.query('Reviewed multiple evaluation positives',[d1,d3],'first');rows.extend([d3,multi])
        prepared=r.prepare(self.d.releases,self.body(rows));self.assertTrue(prepared['preview']['eligible'],prepared['preview'])
        emitted=next(row for row in r.projection(prepared,'queries.jsonl') if row['query_id']==multi['id'])
        self.assertEqual(emitted['split'],'val');self.assertEqual(emitted['relevant_doc_ids'],[d1['id'],d3['id']])
        self.assertEqual(len(list(r.projection(prepared,'train_pairs.jsonl'))),2)


    def test_positive_only_scope_token_and_unjudged_documents(self):
        rows=self.fixture()
        unused=self.document('Selected document with no relevance judgment','orchard')
        rows.append(unused)
        raw=r.import_query(self.w,dict(name='Unselected draft',text='Unselected unjudged question?',groups=['orchard'],rights='unknown',positive_refs=[ref(rows[0])]))
        self.assertEqual(raw['review'],'draft');self.assertIsNone(raw['annotation'])
        body=self.body(rows);p=self.d.releases.preview(body)
        self.assertTrue(p['eligible'],p);self.assertEqual(p['judgment_scope'],r.JUDGMENT_SCOPE)
        self.assertEqual(p['judgment_scope']['unlisted_relationships'],'unjudged')
        self.assertFalse(p['judgment_scope']['negative_judgments_supported'])
        with patch.dict(r.JUDGMENT_SCOPE,consumer_execution='Changed scope'):
            altered=self.d.releases.preview(body)
            self.assertNotEqual(altered['preview_token'],p['preview_token'])
        out=self.d.releases.create(dict(body,preview_token=p['preview_token']))
        with zipfile.ZipFile(self.d.releases.locate(out['id'])) as z:
            m=json.loads(z.read('manifest.json'));self.assertEqual(m['judgment_scope'],r.JUDGMENT_SCOPE)
            queries=[json.loads(line) for line in z.read('queries.jsonl').splitlines()]
            self.assertTrue(all(unused['id'] not in q['relevant_doc_ids'] for q in queries))
            self.assertNotIn(raw['id'],{row['id'] for row in m['records']})
            self.assertIn('UNJUDGED',z.read('README.txt').decode())
            self.assertTrue(all(set(q)=={'query_id','text','relevant_doc_ids','split'} for q in queries))

    def test_reference_bounds_wrong_roles_and_draft_documents_are_atomic(self):
        doc=self.document('Bounded available source','bounds');body=dict(name='Q',text='Bounded query?',groups=['bounds'],rights='unknown',positive_refs=[ref(doc)])
        before=self.state()
        for value in ([],[ref(doc)]*31,[dict(ref(doc),revision=2**63)],[dict(ref(doc),source_revision=0)],[dict(ref(doc),id='A'*32)]):
            with self.assertRaises(WorkbenchError):r.import_query(self.w,dict(body,positive_refs=value))
            self.assertEqual(self.state(),before)
        draft=self.save(doc,doc['annotation'],review='draft')
        before=self.state()
        with self.assertRaises(WorkbenchError):r.import_query(self.w,dict(body,positive_refs=[ref(draft)]))
        self.assertEqual(self.state(),before)
