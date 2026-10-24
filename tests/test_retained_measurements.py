"""Source-bound scalar, complete-denominator and closed-query decisions."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from retained_measurements import MeasurementTable, decode, digest, encode
from workbench import WorkbenchError


def source(identity,value,kind='json'):
    raw=encode(value) if kind=='json' else value
    return {'id':identity,'label':identity,'kind':kind,'bytes':len(raw),
            'sha256':hashlib.sha256(raw).hexdigest(),'data_base64':base64.b64encode(raw).decode('ascii')}


def ref(pointer,hashed=None):
    result={'source_id':'context','pointer':pointer}
    if hashed is not None:result['sha256']=digest(hashed)
    return result


def fixture():
    scope={'id':'consumed','label':'Retained consumed diagnostics','population':'consumed',
           'task':'Fixture measurements, not scientific acceptance'}
    metrics=[{'id':'error','label':'Declared error ratio','units':'1','description':'Exact retained scalar'},
             {'id':'latency','label':'Complete-call latency','units':'ms','description':'No qualified timing available'}]
    context={'scope':scope,'metrics':metrics,'values':[1e-17,2e-15,0.01,0.02],'latency_claim':False}
    doc={'format':'retained_measurements_v1','schema_version':1,'title':'Finite comparison fixture',
         'scope':{k:scope[k] for k in ('id','label','population')},
         'dimensions':[{'id':'cpm','label':'Cells per metre','type':'number','units':'cells/m','scope':'case'},
                       {'id':'grid_x','label':'Domain X cells','type':'integer','units':'cells','scope':'case'},
                       {'id':'device','label':'Device','type':'string','units':None,'scope':'subject'},
                       {'id':'passes','label':'Actual work','type':'integer','units':'passes','scope':'observation'}],
         'subjects':[{'id':i,'label':i,'dimensions':{'device':'GPU' if i=='a' else 'CPU'},'reference':ref('')} for i in ('a','b')],
         'cases':[{'id':'case1','dimensions':{'cpm':16,'grid_x':8},'reference':ref('')},
                  {'id':'case2','dimensions':{'cpm':8,'grid_x':16},'reference':ref('')}],
         'metrics':[{**{k:m[k] for k in ('id','label','units')},'definition':ref('/metrics/'+str(i),m)} for i,m in enumerate(metrics)],
         'observations':[],'sources':[source('context',context),source('failure',b'Original failed timing attempt','opaque')]}
    doc['scope']['definition']=ref('/scope',scope)
    index=0
    for subject in ('a','b'):
        for case in ('case1','case2'):
            doc['observations'].append({'id':subject+'-'+case+'-error','subject_id':subject,'case_id':case,'metric_id':'error',
                'state':'measured','value':context['values'][index],'reason':None,'dimensions':{'passes':1 if subject=='a' else 2},'reference':ref('/values/'+str(index))})
            failed=subject=='b' and case=='case2'
            doc['observations'].append({'id':subject+'-'+case+'-latency','subject_id':subject,'case_id':case,'metric_id':'latency',
                'state':'failed' if failed else 'unavailable','value':None,
                'reason':'Retained failure' if failed else 'No qualified timing',
                'dimensions':{'passes':1 if subject=='a' else 2},
                'reference':{'source_id':'failure','pointer':None} if failed else ref('/latency_claim')})
            index+=1
    return doc


class RetainedMeasurementTests(unittest.TestCase):
    def test_exact_tiny_values_density_and_grid_filters_and_detached_results(self):
        doc=fixture();table=MeasurementTable(encode(doc));query=table.query('error')
        self.assertEqual(query['total'],4);self.assertEqual(query['sampling'],'none')
        self.assertEqual([r['maximum']['value'] for r in query['summary']],[2e-15,0.02])
        row=table.inspect('a-case1-error')
        self.assertEqual(struct.pack('!d',row['observation']['value']),struct.pack('!d',1e-17))
        self.assertEqual(table.query('error',filters={'cpm':16})['rows'][0]['dimensions']['grid_x'],8)
        self.assertEqual(table.query('error',filters={'grid_x':16})['rows'][0]['dimensions']['cpm'],8)
        self.assertEqual(table.query('error',filters={'device':'CPU'})['total'],2)
        self.assertEqual(table.query('error',filters={'passes':1})['summary'][1]['count'],0)
        query['rows'][0]['value']=999;row['subject']['label']='wrong'
        self.assertEqual(table.inspect('a-case1-error')['observation']['value'],1e-17)
        self.assertEqual(table.subjects()['items'][0]['label'],'a')
        self.assertEqual(table.subjects(offset=1,limit=1)['items'][0]['id'],'b')
        self.assertEqual(table.subjects(offset=2)['items'],[])
        self.assertEqual(table.metadata()['subject_count'],2)

    def test_missing_and_failed_timings_are_explicit_not_zero_or_dropped(self):
        table=MeasurementTable(encode(fixture()));query=table.query('latency',offset=1,limit=2)
        self.assertEqual(query['total'],4);self.assertEqual(len(query['rows']),2)
        self.assertTrue(all(v['maximum'] is None and v['count']==2 for v in query['summary']))
        self.assertEqual(query['summary'][1]['states'],{'measured':0,'failed':1,'unsupported':0,'unavailable':1})
        self.assertEqual(table.inspect('b-case2-latency')['source']['kind'],'opaque')

    def test_missing_duplicate_and_unresolved_matrix_members_are_refused(self):
        for mutation in ('missing','duplicate','unknown','malformed'):
            doc=fixture()
            if mutation=='missing':doc['observations'].pop()
            if mutation=='duplicate':doc['observations'][-1]=copy.deepcopy(doc['observations'][0]);doc['observations'][-1]['id']='new-id'
            if mutation=='unknown':doc['observations'][0]['case_id']='outside'
            if mutation=='malformed':doc['observations'][0]['case_id']=[]
            with self.subTest(mutation=mutation),self.assertRaises(WorkbenchError):MeasurementTable(encode(doc))

    def test_measured_value_source_hash_and_definition_changes_are_refused(self):
        for mutation in ('value','hash','definition','units','pointer','source-type','boolean','huge-integer'):
            doc=fixture()
            if mutation=='value':doc['observations'][0]['value']=0.5
            if mutation=='hash':doc['sources'][0]['sha256']='f'*64
            if mutation=='definition':doc['metrics'][0]['definition']['sha256']='f'*64
            if mutation=='units':doc['metrics'][0]['units']='s'
            if mutation=='pointer':doc['observations'][0]['reference']['pointer']='/values/099'
            if mutation=='source-type':doc['observations'][0]['reference']['source_id']=[]
            if mutation=='boolean':doc['observations'][0]['value']=True
            if mutation=='huge-integer':doc['observations'][0]['value']=10**400
            with self.subTest(mutation=mutation),self.assertRaises(WorkbenchError):MeasurementTable(encode(doc))

    def test_null_status_reason_and_dimension_contracts_are_not_inferred(self):
        for mutation in ('null-measured','non-null-missing','empty-reason','boolean-dimension','extra-dimension'):
            doc=fixture()
            if mutation=='null-measured':doc['observations'][0]['value']=None
            if mutation=='non-null-missing':doc['observations'][1]['value']=0
            if mutation=='empty-reason':doc['observations'][1]['reason']=''
            if mutation=='boolean-dimension':doc['cases'][0]['dimensions']['grid_x']=True
            if mutation=='extra-dimension':doc['cases'][0]['dimensions']['unexpected']=1
            with self.subTest(mutation=mutation),self.assertRaises(WorkbenchError):MeasurementTable(encode(doc))

    def test_nonfinite_underflow_duplicate_keys_and_unicode_are_refused(self):
        for raw in (b'{"a":1,"a":2}',b'{"a":NaN}',b'{"a":1e999}',b'{"a":1e-999}',b'{"a":"\\ud800"}'):
            with self.subTest(raw=raw),self.assertRaises(WorkbenchError):decode(raw)
        self.assertEqual(struct.pack('!d',decode(b'{"a":5e-324}')['a']),struct.pack('!d',5e-324))

    def test_query_rejects_unknown_selectors_and_never_executes_expressions(self):
        table=MeasurementTable(encode(fixture()))
        for args in ({'metric_id':[]},{'metric_id':'outside'},{'metric_id':'error','filters':{'grid_x':True}},
                     {'metric_id':'error','filters':{'expression':'a > 0'}},{'metric_id':'error','subject_ids':['a','a']},
                     {'metric_id':'error','offset':True},{'metric_id':'error','limit':101}):
            with self.subTest(args=args),self.assertRaises(WorkbenchError):table.query(**args)
        with self.assertRaises(WorkbenchError):table.inspect([])

    def test_source_scalar_sign_and_pointer_escape_are_exact(self):
        doc=fixture();original=json.loads(base64.b64decode(doc['sources'][0]['data_base64']))
        original['a/b~c']=-0.0;doc['sources'][0]=source('context',original)
        doc['observations'][0]['value']=-0.0;doc['observations'][0]['reference']=ref('/a~1b~0c')
        table=MeasurementTable(encode(doc))
        self.assertEqual(struct.pack('!d',table.inspect('a-case1-error')['observation']['value']),struct.pack('!d',-0.0))
        doc['observations'][0]['value']=0.0
        with self.assertRaisesRegex(WorkbenchError,'scalar'):MeasurementTable(encode(doc))

    def test_source_and_complete_matrix_limits_refuse_before_expansion(self):
        doc=fixture();doc['sources'][0]['bytes']=8*1024*1024+1
        with self.assertRaises(WorkbenchError) as error:MeasurementTable(encode(doc))
        self.assertEqual(error.exception.status,413)
        doc=fixture();base=doc['subjects'][0]
        doc['subjects']=[dict(copy.deepcopy(base),id='s'+str(i)) for i in range(128)]
        base=doc['cases'][0];doc['cases']=[dict(copy.deepcopy(base),id='c'+str(i)) for i in range(1000)]
        with self.assertRaises(WorkbenchError) as error:MeasurementTable(encode(doc))
        self.assertEqual(error.exception.status,413)


if __name__=='__main__':unittest.main()
