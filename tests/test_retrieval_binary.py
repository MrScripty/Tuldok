"""Authored three-state transport/ownership controls; never ranking truth."""
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from app import Dataset
import retrieval_binary as r
from workbench import WorkbenchError, encode


def ref(row):
    return {k: row[k] for k in ('id', 'revision', 'source_revision')}


def save(w, row, annotation=None, review='human_reviewed', task=r.TASK, groups=None):
    return w.save(row['id'], dict(ref(row), task=task, annotation=annotation or row['annotation'],
        groups=row['groups'] if groups is None else groups, review=review))


def fixture(d):
    rows = []; w = d.workbench
    for family in ('orchard', 'river'):
        docs = []
        for index in range(3):
            row = w.import_asset(dict(kind='text', text=f'  {family} document{index}: Cafe\u0301 水.\r\n  ',
                name=f'{family} document{index}', groups=[family], rights='Authored QA'))
            doc = save(w, row, {'role': 'document', 'note': 'Authored document inspection'})
            docs.append(doc); rows.append(doc)
        values = [{'document': ref(doc), 'relevance': state} for doc, state in zip(docs, r.STATES)]
        raw = r.import_query(w, dict(name=family+' query', text=family+' question?\n', groups=[family], rights='unknown', judgments=values))
        rows.append(save(w, raw, {'role': 'query', 'note': 'Authored binary judgment inspection', 'judgments': values}))
    return rows


def body(rows):
    return dict(format=r.FORMAT, items=[ref(x) for x in rows], ratios={'train': 50, 'validation': 50, 'test': 0}, seed=42)


def freeze(d, rows):
    request = body(rows); preview = d.releases.preview(request)
    assert preview['eligible'], preview
    release = d.releases.create(dict(request, preview_token=preview['preview_token']))
    return d.releases.locate(release['id']).read_bytes(), release['id'], preview


def packet(raw):
    return {'archive': base64.b64encode(raw).decode(), 'sha256': hashlib.sha256(raw).hexdigest()}


def rewrite(raw, mutation):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        files = {n: archive.read(n) for n in archive.namelist()}
    mutation(files)
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, data in files.items(): archive.writestr(name, data)
    return out.getvalue()


class BinaryRetrieval(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.d = Dataset(Path(self.tmp.name)/'first'); self.addCleanup(self.d.close)
        self.w = self.d.workbench

    def second(self):
        d = Dataset(Path(self.tmp.name)/'second'); self.addCleanup(d.close); return d

    def state(self, d=None):
        return tuple((d or self.d).db.iterdump())

    def test_actual_three_state_export_and_second_owner_roundtrip(self):
        rows = fixture(self.d); raw, sha, preview = freeze(self.d, rows)
        manifest, families = r.inspect_archive(raw, sha)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            grades = [int(line.split()[3]) for line in archive.read('qrels.txt').decode().splitlines()]
            self.assertEqual(grades.count(1), 2); self.assertEqual(grades.count(0), 2); self.assertEqual(grades.count(-1), 2)
            self.assertNotIn('train_pairs.jsonl', archive.namelist())
            self.assertEqual(archive.read('assets/'+rows[0]['id']+'.txt'), rows[0]['text'].encode())
        d = self.second(); result = r.import_release(d.workbench, packet(raw)); imported = result['records']
        self.assertTrue(set(result['id_map'].values()).isdisjoint({x['id'] for x in rows}))
        self.assertTrue(all(x['review']=='draft' and x['revision']==1 and x['provenance']['rights']=='unknown' for x in imported))
        for x in imported:
            upstream = x['provenance']['acquisition']['upstream_record']
            self.assertEqual(x['source_split'], preview['assignments'][upstream['id']])
            self.assertEqual(d.workbench.history(x['id']), [x])
        reviewed = {}
        for x in imported:
            if x['annotation']['role']=='document': reviewed[x['id']] = save(d.workbench, x)
        for x in imported:
            if x['annotation']['role']=='query':
                with self.assertRaises(WorkbenchError): save(d.workbench, x)
                a = copy.deepcopy(x['annotation'])
                for item in a['judgments']: item['document'] = ref(reviewed[item['document']['id']])
                draft = save(d.workbench, x, a, 'draft'); reopened = d.workbench.get(draft['id'])
                reviewed[x['id']] = save(d.workbench, reopened)
        out, out_sha, p = freeze(d, list(reviewed.values())); second, _ = r.inspect_archive(out, out_sha)
        self.assertEqual(second['retrieval_counts'], manifest['retrieval_counts'])
        self.assertEqual({x['text'] for x in second['records']}, {x['text'] for x in rows})
        self.assertEqual(self.d.releases.locate(sha).read_bytes(), raw)

    def test_all_unjudged_and_zero_positive_query(self):
        rows=fixture(self.d); q=next(x for x in rows if x['annotation']['role']=='query')
        a=copy.deepcopy(q['annotation'])
        for item in a['judgments']: item['relevance']='unjudged'
        updated=save(self.w,q,a); rows=[updated if x['id']==q['id'] else x for x in rows]
        raw, sha, _=freeze(self.d,rows); m,_=r.inspect_archive(raw,sha)
        self.assertEqual(sum(x['judgments']['unjudged'] for x in m['retrieval_counts'].values()),4)

    def test_schema_grades_duplicates_and_parent_validation_are_atomic(self):
        rows=fixture(self.d); q=next(x for x in rows if x['annotation']['role']=='query'); before=self.state()
        for state in [True,False,0,1,-1,2,'negative','graded',None]:
            a=copy.deepcopy(q['annotation']);a['judgments'][0]['relevance']=state
            with self.assertRaises(WorkbenchError): save(self.w,q,a)
        for value in [[], q['annotation']['judgments']*11, q['annotation']['judgments'][:1]*2]:
            a=copy.deepcopy(q['annotation']);a['judgments']=value
            with self.assertRaises(WorkbenchError): save(self.w,q,a)
        other=next(x for x in rows if x['annotation']['role']=='document' and x['id'] not in q['parents'])
        a=copy.deepcopy(q['annotation']);a['judgments'][0]['document']=ref(other)
        with self.assertRaises(WorkbenchError): save(self.w,q,a)
        self.assertEqual(self.state(),before)

    def test_stale_reference_save_preview_publication_and_frozen_bytes(self):
        rows=fixture(self.d); raw,sha,p=freeze(self.d,rows); request=body(rows)
        q=next(x for x in rows if x['annotation']['role']=='query'); target=q['annotation']['judgments'][0]['document']['id']
        doc=self.w.get(target); updated=save(self.w,doc,{'role':'document','note':'Changed review note'})
        before=self.state()
        with self.assertRaises(WorkbenchError): save(self.w,q)
        request['items']=[ref(updated) if x['id']==target else ref(x) for x in rows]
        self.assertFalse(self.d.releases.preview(request)['eligible'])
        with self.assertRaises(WorkbenchError): self.d.releases.create(dict(request,preview_token=p['preview_token']))
        self.assertEqual(self.state(),before);self.assertEqual(self.d.releases.locate(sha).read_bytes(),raw)

    def test_deleted_reference_refusal_keeps_lineage_bridge(self):
        rows=fixture(self.d); raw,sha,prior=freeze(self.d,rows)
        q=next(x for x in rows if x['annotation']['role']=='query'); target=q['annotation']['judgments'][-1]['document']['id']
        self.d.db.execute('INSERT INTO workbench_deleted_text VALUES (?)',(target,));self.d.db.commit()
        with self.assertRaises(WorkbenchError): save(self.w,q)
        p=self.d.releases.preview(body(rows));self.assertFalse(p['eligible'])
        with self.assertRaises(WorkbenchError): self.d.releases.create(dict(body(rows),preview_token=prior['preview_token']))
        self.assertEqual(self.d.releases.locate(sha).read_bytes(),raw)
        self.assertTrue(self.w.get(target)['source_lineage_known'])

    def test_unselected_former_parent_bridge_cannot_split(self):
        rows=fixture(self.d); qs=[x for x in rows if x['annotation']['role']=='query']; first=qs[0]
        a=copy.deepcopy(first['annotation']);a['judgments']=a['judgments'][:1]
        first=save(self.w,first,a);self.assertEqual(first['parents'],qs[0]['parents'])
        # An unselected bridge joins both families; fixed selection cannot evade it.
        self.w.import_asset(dict(kind='text',name='bridge',text='Unique bridge source',groups=['bridge'],parents=[qs[0]['id'],qs[1]['id']]))
        rows=[first if x['id']==first['id'] else x for x in rows]
        p=self.d.releases.preview(body(rows));self.assertFalse(p['eligible']);self.assertIn('Too few',p['blockers'][0]['message'])

    def test_every_referenced_document_must_be_selected_even_unjudged(self):
        rows=fixture(self.d); q=next(x for x in rows if x['annotation']['role']=='query'); unjudged=q['annotation']['judgments'][-1]['document']['id']
        p=self.d.releases.preview(body([x for x in rows if x['id']!=unjudged]));self.assertFalse(p['eligible'])
        self.assertIn('unjudged',p['blockers'][0]['message'])

    def test_import_fixed_bindings_cannot_be_removed_or_task_bypassed(self):
        raw,sha,_=freeze(self.d,fixture(self.d));d=self.second();rows=r.import_release(d.workbench,packet(raw))['records'];x=rows[0]
        with self.assertRaises(WorkbenchError): save(d.workbench,x,{'label':'class'},task='text_classification',groups=['new'])
        converted=save(d.workbench,x,{'label':'class'},task='text_classification',review='draft')
        self.assertEqual(converted['source_split'],x['source_split'])
        converted=d.workbench.save(converted['id'],dict(ref(converted),task='text_classification',annotation={'label':'class'},groups=converted['groups'],review='programmatically_verified'),verified_provenance={'method':'QA-owned-verifier'})
        self.assertEqual(converted['provenance']['acquisition'],x['provenance']['acquisition'])
        d.db.execute('INSERT INTO workbench_deleted_text VALUES (?)',(x['id'],));d.db.commit()
        deleted=d.workbench.get(x['id']);self.assertFalse(deleted['source_available']);self.assertEqual(deleted['source_split'],x['source_split'])
        # Missing binding does not silently forget source split in related allocation.
        d.db.execute('DELETE FROM retrieval_binary_sources WHERE id=?',(x['id'],));d.db.commit()
        self.assertFalse(d.workbench.get(x['id'])['source_lineage_known'])

    def test_stable_origin_anchors_across_changed_family_membership(self):
        rows=fixture(self.d);raw,sha,_=freeze(self.d,rows);first,_=r.inspect_archive(raw,sha)
        family=next(iter(first['protected_components']));prior=set(r.origin_groups(first['protected_components'][family]))
        group=first['protected_components'][family][0]['groups'][0]
        self.w.import_asset(dict(kind='text',text='Another retained unselected source',groups=[group]))
        raw2,sha2,_=freeze(self.d,rows);second,_=r.inspect_archive(raw2,sha2)
        members=next(v for v in second['protected_components'].values() if any(s['id']==first['protected_components'][family][0]['id'] for s in v))
        self.assertTrue(prior<=set(r.origin_groups(members)))

    def test_invalid_archives_hashes_and_typed_numbers_publish_nothing(self):
        raw,sha,_=freeze(self.d,fixture(self.d));d=self.second();before=self.state(d)
        with self.assertRaises(WorkbenchError): r.import_release(d.workbench,dict(packet(raw),sha256='0'*64))
        mutations=[lambda f:f.update({'qrels.txt':b'bad'}),lambda f:f.update({'alien.txt':b'bad'}),lambda f:f.pop('queries.jsonl'),lambda f:f.update({'manifest.json':b'{"format":1,"format":2}'}),lambda f:f.update({'manifest.json':b'{"x":NaN}'})]
        for mutate in mutations:
            with self.assertRaises(WorkbenchError): r.import_release(d.workbench,packet(rewrite(raw,mutate)))
            self.assertEqual(self.state(d),before)
        def boolean_count(files):
            m=json.loads(files['manifest.json']);m['retrieval_counts']['train']['families']=True;files['manifest.json']=encode(m).encode()
        with self.assertRaises(WorkbenchError): r.import_release(d.workbench,packet(rewrite(raw,boolean_count)))
        for value in [raw[:-1],b'',raw+b'junk']:
            with self.assertRaises(WorkbenchError): r.import_release(d.workbench,packet(value))
        self.assertEqual(self.state(d),before)

    def test_atomic_records_bindings_and_initial_history_failure(self):
        raw,sha,_=freeze(self.d,fixture(self.d));d=self.second();before=self.state(d)
        for table in ['workbench_records','retrieval_binary_sources','workbench_history']:
            d.db.execute(f"CREATE TRIGGER fail_binary BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT,'QA failure'); END")
            trigger_before=self.state(d)
            with self.assertRaises(sqlite3.IntegrityError):r.import_release(d.workbench,packet(raw))
            self.assertEqual(self.state(d),trigger_before);d.db.execute('DROP TRIGGER fail_binary');d.db.commit()
        r.import_release(d.workbench,packet(raw));before=self.state(d)
        with self.assertRaises(WorkbenchError):r.import_release(d.workbench,packet(raw))
        self.assertEqual(self.state(d),before)

    def test_release_file_atomic_failure_removes_partial(self):
        rows=fixture(self.d);request=body(rows);p=self.d.releases.preview(request)
        with patch('dataset_releases.os.replace',side_effect=OSError('QA publication failed')):
            with self.assertRaises(OSError):self.d.releases.create(dict(request,preview_token=p['preview_token']))
        self.assertEqual(list(self.d.releases.path.glob('*')),[])

    def test_bounds_json_and_complete_origin_budget(self):
        with self.assertRaises(WorkbenchError):r.decode(b'{"x":"\\ud800"}')
        for raw in [b'{"x":1e999}',b'{"x":-1e999}']:
            with self.assertRaises(WorkbenchError):r.decode(raw)
        with self.assertRaises(WorkbenchError):r.decode(('['*65+'0'+']'*65).encode())
        self.assertEqual(r.decode(b'{"x":0}'),{'x':0})
        members=[{'id':f'{i:032x}','parents':[],'groups':['g']} for i in range(30)]
        with self.assertRaises(WorkbenchError):r.origin_groups(members)
        before=self.state()
        with self.assertRaises(WorkbenchError):r.import_release(self.w,{'archive':'x'*(r.MAX_PHYSICAL*4//3+5),'sha256':'0'*64})
        self.assertEqual(self.state(),before)
        old = r.origin_groups([{'id':'1'*32,'parents':[],'groups':['original']}])
        propagated = r.origin_groups([{'id':'2'*32,'parents':[],'groups':old}])
        self.assertTrue(set(old) <= set(propagated))

    def test_legacy_positive_schema_and_program_verification_remain_separate(self):
        rows=fixture(self.d);q=next(x for x in rows if x['annotation']['role']=='query')
        with self.assertRaises(WorkbenchError):save(self.w,q,task='text_retrieval')
        with self.assertRaises(WorkbenchError):self.w.save(q['id'],dict(ref(q),task=r.TASK,annotation=q['annotation'],groups=q['groups'],review='programmatically_verified'),verified_provenance={'method':'owned_verifier'})
        from native_sequence_dataset import source_identity
        snapshot={k:rows[0][k] for k in r.SNAPSHOT_KEYS};snapshot['source_split']='train';source_identity(snapshot)
        snapshot['source_available']=False;source_identity(snapshot)


if __name__ == '__main__': unittest.main()
