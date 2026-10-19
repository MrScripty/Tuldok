"""T5 baseline only: real neutral custody and bounded owner/HTTP measurements.

No optimization, scientific producer, installed-runtime mutation or OS-cache flush.
Run with the documented task-owned disposable PostgreSQL DSN; all new catalogs
and their exact schemas belong to this harness and are closed/dropped explicitly.
"""
import argparse
import copy
from collections import Counter, defaultdict
from contextlib import ExitStack
import hashlib
from http.server import ThreadingHTTPServer
import importlib
import json
import math
import os
from pathlib import Path
import platform
import resource
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_BASE = '96c2adebc3a46b9fe92b179097474e08474689c3'
SCOPE = 'Neutral deterministic byte-copy baseline; no training, CUDA, numerical or scientific acceptance.'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    path = Path(path)
    with path.open('xb') as stream:
        stream.write(canonical(value)+b'\n')


def usage():
    """Process/thread aggregate; high-water RSS is lifetime, never a phase peak."""
    own = resource.getrusage(resource.RUSAGE_SELF)
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    io = {}
    for line in Path('/proc/self/io').read_text().splitlines():
        key, value = line.split(':'); io[key] = int(value)
    rss = {}
    for line in Path('/proc/self/status').read_text().splitlines():
        if line.startswith(('VmRSS:', 'VmHWM:')):
            key, value, _unit = line.split(); rss[key[:-1]] = int(value)
    return {'cpu_user_s': own.ru_utime, 'cpu_system_s': own.ru_stime,
        'children_user_s': children.ru_utime, 'children_system_s': children.ru_stime,
        'self_inblock':own.ru_inblock,'self_oublock':own.ru_oublock,
        'children_inblock':children.ru_inblock,'children_oublock':children.ru_oublock,
        'maxrss_kib': own.ru_maxrss, 'children_maxrss_kib': children.ru_maxrss,
        'rss_kib': rss.get('VmRSS'), 'hwm_kib': rss.get('VmHWM'), 'io': io}


class Metrics:
    def __init__(self):
        self.rows = []
        self.counts = Counter()
        self.requests = []
        self.stages = []
        self.lock = threading.RLock()
        self.labels = {}

    def request(self, row):
        with self.lock: self.requests.append(row)

    def observe(self, name, function, *, allow_error=False, detail=None):
        before = usage(); counter = self.counts.copy(); request = len(self.requests); stages = len(self.stages)
        start = time.perf_counter_ns(); error = None; result = None
        try:
            result = function()
        except Exception as caught:
            error = caught
        wall = time.perf_counter_ns()-start; after = usage()
        row = dict(self.labels, operation=name, wall_ns=wall,
            cpu={key: after[key]-before[key] for key in ('cpu_user_s','cpu_system_s','children_user_s','children_system_s')},
            rss={'before_kib':before['rss_kib'],'after_kib':after['rss_kib'],
                 'lifetime_hwm_before_kib':before['hwm_kib'],'lifetime_hwm_after_kib':after['hwm_kib'],
                 'children_lifetime_maxrss_kib':after['children_maxrss_kib']},
            proc_io_delta={key:after['io'][key]-before['io'][key] for key in before['io']},
            resource_io_blocks_delta={key:after[key]-before[key] for key in ('self_inblock','self_oublock','children_inblock','children_oublock')},
            counts=dict(self.counts-counter), http=self.requests[request:],
            owner_stages=self.stages[stages:], outcome='error' if error else 'ok', detail=detail or {})
        if isinstance(result,dict) and type(result.get('status')) is int and 'result' in result:
            row['envelope_status']=result['status']
            if result['status']>=400: row['outcome']='refused'
        if error:
            row['error']={'type':type(error).__name__,'code':getattr(error,'code',None),
                          'status':getattr(error,'status',None),'message':str(error)[:240]}
        self.rows.append(row)
        if error is not None and not allow_error: raise error
        return result

    def instrumentation(self, dataset):
        """Counters/timers delegate unchanged arguments/results; no result reuse."""
        import recipe_contract
        stack = ExitStack()
        original = recipe_contract.file_digest
        def hashed(raw):
            self.counts['recipe_contract.file_digest.calls'] += 1
            self.counts['recipe_contract.file_digest.bytes'] += len(raw)
            return original(raw)
        stack.enter_context(patch.object(recipe_contract, 'file_digest', hashed))
        def wrap(owner, attribute, label):
            original_method = getattr(owner, attribute)
            def measured(*args, **kwargs):
                start = time.perf_counter_ns()
                self.counts[label+'.calls'] += 1
                try: return original_method(*args, **kwargs)
                finally:
                    self.stages.append({'owner':label,'inclusive_wall_ns':time.perf_counter_ns()-start})
            stack.enter_context(patch.object(owner, attribute, measured))
        for attribute in ('runtime_identity','prepare','capture','verify_outputs'):
            wrap(recipe_contract,attribute,'recipe_contract.'+attribute)
        for attribute in ('_retain_external_publication_source','_publish_external'):
            wrap(dataset.runs,attribute,'runs.'+attribute)
        import run_publication
        for attribute in ('_source','_verify_source','_publish'):
            wrap(run_publication,attribute,'run_publication.'+attribute)
        return stack


def server(dataset, metrics):
    from app import make_handler
    base = make_handler(dataset)
    class Counted(base):
        def send_response(self, code, message=None):
            self.benchmark_status=code; self.benchmark_length=0
            return super().send_response(code,message)
        def send_header(self, keyword, value):
            if keyword.lower()=='content-length': self.benchmark_length=int(value)
            return super().send_header(keyword,value)
        def end_headers(self):
            super().end_headers()
            selected=self.headers.get('Tuldok-Operation-Contract','')
            metrics.request({'method':self.command,'path':self.path,
                'operation':selected.split('/')[0] if selected else None,
                'status':self.benchmark_status,'request_body_bytes':int(self.headers.get('Content-Length','0')),
                'response_body_bytes':self.benchmark_length})
        def log_message(self,*_args): pass
    http = ThreadingHTTPServer(('127.0.0.1',0),Counted)
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    return http,thread,'http://127.0.0.1:'+str(http.server_port)


def stop_server(http, thread):
    http.shutdown();http.server_close();thread.join(5)
    if thread.is_alive(): raise RuntimeError('Owned HTTP server did not close.')


def counts(dataset):
    with dataset.lock:
        result={table:dataset.db.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in
            ('workspace_runs','access_execution_grants','access_execution_consumptions','model_attempt_reservations')}
        states=dataset.db.execute("SELECT document::jsonb->>'state' AS state,count(*) FROM workspace_runs GROUP BY 1").fetchall()
    result['states']={row[0]:row[1] for row in states}
    return result


def inventory_identity(items, *, name_key='path'):
    """Order is filesystem-dependent; duplicates or differing bytes still fail."""
    result = {}
    for item in items:
        name = item[name_key]
        if name in result:
            raise AssertionError('Duplicate artifact path.')
        result[name] = {'bytes': item['bytes'], 'sha256': item['sha256']}
    return result


def distribution(rows):
    grouped=defaultdict(list)
    for row in rows:
        grouped[(row.get('artifacts'),row.get('terminal_history'),row.get('condition'),row['operation'],row['outcome'])].append(row)
    result=[]
    for (artifacts,history,condition,operation,outcome),samples in sorted(grouped.items(),key=lambda item:str(item[0])):
        values=sorted(row['wall_ns']/1e6 for row in samples)
        result.append({'artifacts':artifacts,'terminal_history':history,'condition':condition,
            'operation':operation,'outcome':outcome,'n':len(values), 'wall_ms':{'min':values[0],
                'median':statistics.median(values),'p90_nearest_rank':values[math.ceil(.9*len(values))-1],
                'max':values[-1]},'cpu_total_s_median':statistics.median(sum(row['cpu'].values()) for row in samples),
            'http_requests_median':statistics.median(len(row['http']) for row in samples),
            'response_body_bytes_median':statistics.median(sum(call['response_body_bytes'] for call in row['http']) for row in samples),
            'rss_after_kib_median':statistics.median(row['rss']['after_kib'] for row in samples),
            'physical_read_bytes_median':statistics.median(row['proc_io_delta']['read_bytes'] for row in samples),
            'logical_read_chars_median':statistics.median(row['proc_io_delta']['rchar'] for row in samples)})
    return result


class Fixture:
    def __init__(self, pieces, total):
        from app import Dataset
        from auth_helpers import ExplicitOwnerFixture
        self.directory=tempfile.TemporaryDirectory(prefix='tuldok-m4-owned-')
        self.path=Path(self.directory.name); self.project=self.path/'project';self.project.mkdir()
        self.metrics=Metrics(); self.metrics.labels={'artifacts':pieces,'terminal_history':0,'condition':'fresh_catalog_setup'}; self.pieces=pieces; self.total=total; self.dataset=None;self.http=None
        if total % pieces: raise ValueError('Aggregate payload must divide exactly across artifacts.')
        size=total//pieces
        self.payload=b''.join((hashlib.sha256(('neutral-'+str(i)).encode()).digest()*((size+31)//32))[:size] for i in range(pieces))
        source=("from pathlib import Path\nimport sys\nraw=Path(sys.argv[1]).read_bytes()\n"
            "out=Path(sys.argv[2]);count=int(sys.argv[3]);size=len(raw)//count\n"
            "for i in range(count): (out/('piece-%02d.bin'%i)).write_bytes(raw[i*size:(i+1)*size])\n"
            "print('Neutral exact byte-copy fixture; no numerical or training claim')\n").encode()
        self.expected=[{'name':f'piece-{i:02}.bin','bytes':size,'sha256':sha(self.payload[i*size:(i+1)*size])} for i in range(pieces)]
        definition={'schema_version':1,'format':'external_recipe_v1','id':'neutral','name':'Neutral T5 byte-copy baseline',
            'version':1,'runtime':'system_python','sources':[{'path':'recipe.py','sha256':sha(source)}],
            'entrypoint':'recipe.py','arguments':[{'input':'sample'},{'output_dir':True},{'parameter':'pieces'}],
            'parameters':{'pieces':{'type':'integer','default':pieces,'min':1,'max':32}},
            'inputs':{'sample':{'max_bytes':total}},'outputs':[{'path':item['name'],'role':'result','max_bytes':size,'required':True} for item in self.expected],
            'environment':{},'resources':{'wall_seconds':20,'max_output_bytes':total}}
        raw=canonical(definition)
        self.manifest={'schema_version':1,'id':uuid.uuid4().hex,'name':SCOPE,
            'data':[{'id':'sample','label':'Neutral bytes','path':'input.bin','sha256':sha(self.payload)}],
            'recipes':[{'id':'neutral','label':'Neutral copier','path':'recipe.json','sha256':sha(raw)}],
            'evidence':[],'requirements':[]}
        for name,data in {'recipe.py':source,'input.bin':self.payload,'recipe.json':raw,'project.json':canonical(self.manifest)}.items():
            (self.project/name).write_bytes(data)
        self.dataset=self.metrics.observe('catalog.create',lambda:Dataset(self.path/'catalog',project_roots={'fixture':self.project}))
        self.schema,self.dsn=self.dataset.db.schema,self.dataset.db.dsn
        self.owner=ExplicitOwnerFixture.bootstrap(self.dataset)
        with self.owner.bound(self.dataset):
            self.dataset.projects.open({'root':'fixture','manifest_path':'project.json'})
            self.agent=self.dataset.access.issue({'label':'T5 disposable submitter','scopes':['inspect','execute']})
            self.graph=self.dataset.pipelines.create_external({'name':'Neutral T5','project_id':self.manifest['id'],
                'recipe_id':'neutral','expected_sha256':sha(raw), 'inputs':{'sample':{'reference_id':'sample','expected_sha256':sha(self.payload)}}})
        self.target=None;self.material=None

    def open(self):
        if self.dataset is None:
            from app import Dataset
            self.dataset=Dataset(self.path/'catalog',project_roots={'fixture':self.project})

    def close(self):
        if self.http:
            stop_server(self.http,self.thread);self.http=None
        if self.dataset is not None:
            self.dataset.close();self.dataset=None

    def cleanup(self):
        # Only this fresh catalog's recorded exact schema; never infer old names.
        self.close()
        import psycopg
        from psycopg import sql
        with psycopg.connect(self.dsn,autocommit=True) as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
            if connection.execute('SELECT to_regnamespace(%s)',(self.schema,)).fetchone()[0] is not None:
                raise AssertionError('Owned schema cleanup did not complete.')
        self.directory.cleanup()
        return {'schema':self.schema,'dropped':True,'owned_temporary_directory_removed':not self.path.exists()}

    def start(self):
        import agent_api
        self.open()
        if not self.http:
            self.http,self.thread,self.endpoint=server(self.dataset,self.metrics)
            self.client=agent_api.AgentClient(self.endpoint,self.agent['token'],self.dataset.db.dataset_id)
            self.metrics.observe('agent.bootstrap_for_workflow',self.client.bootstrap)

    def populate_one(self, *, full_workflow=False):
        import agent_api
        self.start();dataset=self.dataset
        self.metrics.labels={'artifacts':self.pieces,'terminal_history':counts(dataset)['workspace_runs'],'condition':'history_population' if not full_workflow else 'supported_workflow'}
        def workflow():
            if self.material is None or full_workflow:
                preflight=self.client.call('graphs.preflight_external',{'graph_id':self.graph['id'],'revision':1})
                if preflight['status']!=200: raise RuntimeError('Preflight refused: '+str(preflight))
                self.material=preflight['result']['material_sha256']
            with self.owner.bound(dataset):
                grant=dataset.access.grant_execution(self.material,self.agent['identity']['actor_id'])
            body={'graph_id':self.graph['id'],'graph_revision':1,'expected_digest':self.material,
                'request_key':'baseline-'+uuid.uuid4().hex,'approval_id':grant['id']}
            result=self.client.call('runs.submit_external',body)
            if result['status']!=201: raise RuntimeError('Submission refused: '+str(result))
            run_id=result['result']['id'];deadline=time.monotonic()+60
            while True:
                current=self.client.call('runs.get',{'run_id':run_id})
                if current['status']!=200: raise RuntimeError('Run read refused.')
                if current['result']['state'] not in ('queued','running','cancelling'): break
                if time.monotonic()>=deadline: raise RuntimeError('Real neutral queue did not complete.')
                time.sleep(.05)
            if current['result']['state']!='completed': raise RuntimeError('Neutral Run did not complete: '+str(current['result']['state']))
            if full_workflow:
                for item in self.expected:
                    checked=agent_api.verify_artifact(self.client,run_id,item['name'],item['sha256'])
                    if checked['bytes']!=item['bytes']: raise AssertionError('Whole collection bytes differ.')
            return run_id
        with self.metrics.instrumentation(dataset):
            run_id=self.metrics.observe('workflow.preflight_grant_submit_complete_collect' if full_workflow else 'setup.real_run',workflow)
        self.target=self.target or run_id

    def state(self):
        return {'catalog':str(self.path/'catalog'),'project':str(self.project),'graph':self.graph,
            'owner_token':self.owner.token,'agent_token':self.agent['token'],'expected':self.expected,
            'target':self.target,'material':self.material,'artifacts':self.pieces,'scope':SCOPE}


def worker(config, output, repeats):
    metrics=Metrics()
    def imports():
        global agent_api, recipe_contract, run_publication
        agent_api=importlib.import_module('agent_api');recipe_contract=importlib.import_module('recipe_contract')
        run_publication=importlib.import_module('run_publication')
        return importlib.import_module('app').Dataset
    metrics.labels={'artifacts':config['artifacts'],'terminal_history':config['history'],'condition':'fresh_process'}
    Dataset=metrics.observe('process.import_application',imports)
    # Read-only measurements must never dispatch a recipe on reopen or reads.
    with patch('recipe_process.launch',side_effect=AssertionError('Read baseline attempted compute replay')):
        dataset=metrics.observe('catalog.cold_reopen',lambda:Dataset(config['catalog'],project_roots={'fixture':Path(config['project'])}))
        http=thread=None
        try:
            http,thread,endpoint=server(dataset,metrics)
            client=agent_api.AgentClient(endpoint,config['agent_token'],dataset.db.dataset_id)
            metrics.observe('agent.cold_bootstrap',client.bootstrap)
            metrics.observe('instrumentation.noop_calibration',lambda:None)
            before=counts(dataset);identity=dataset.db.dataset_id
            with metrics.instrumentation(dataset):
                for cycle in range(repeats+1):
                    metrics.labels={'artifacts':config['artifacts'],'terminal_history':config['history'],
                        'condition':'first_call_fresh_process' if cycle==0 else 'warm_same_process_reverification','cycle':cycle}
                    with dataset.access.bind(config['owner_token']):
                        graph=dataset.pipelines.get(config['graph']['id'])
                        prepared,captured=metrics.observe('owner.recipe_prepare',lambda:recipe_contract.prepare(dataset.projects,graph,
                            importlib.import_module('pipeline').execution_digest(graph),releases=dataset.releases,runs=dataset.runs))
                        preflight=metrics.observe('owner.preflight_v3',lambda:dataset.pipelines.preflight_external(graph['id'],1,contract_version=3))
                        if prepared['material_sha256']!=preflight['material_sha256'] or config['material'] is not None and prepared['material_sha256']!=config['material']:
                            raise AssertionError('Repeated prepared material changed.')
                        for name,fn in (
                            ('owner.capture_full',lambda path:dataset.pipelines.capture_external(graph['id'],1,prepared['material_sha256'],path)),
                            ('owner.capture_held_prepared',lambda path:recipe_contract.capture(prepared,captured,path))):
                            staging=dataset.runs.path/('.baseline-'+uuid.uuid4().hex)
                            try:
                                result=metrics.observe(name,lambda:fn(staging))
                                if result['material']!=prepared['material']: raise AssertionError('Capture material differs.')
                                for relative,item in prepared['material']['captures'].items():
                                    raw=(staging/relative).read_bytes()
                                    if len(raw)!=item['bytes'] or sha(raw)!=item['sha256']: raise AssertionError('Captured bytes differ.')
                            finally:
                                if staging.exists(): shutil.rmtree(staging)
                        direct=metrics.observe('owner.runs_list',dataset.runs.list)
                        if len(direct)!=config['history']: raise AssertionError('History size differs.')
                        if config['target']:
                            run=metrics.observe('owner.run_get',lambda:dataset.runs.get(config['target']))
                            if run['state']!='completed': raise AssertionError('Read changed original Run state.')
                            retained=dataset.runs._load(config['target'])
                            proof=metrics.observe('owner.publication_source_proof_read',lambda:run_publication._source(dataset.runs,retained,retained['publication_source']))
                            if inventory_identity(proof['inventory']) != inventory_identity(config['expected'],name_key='name'):
                                raise AssertionError('Retained inventory differs.')
                    metrics.observe('http.runs_list',lambda:client.call('runs.list',{}))
                    if config['target']:
                        got=metrics.observe('http.run_metadata',lambda:client.call('runs.get',{'run_id':config['target']}))
                        if got['status']!=200: raise AssertionError('Run metadata refused.')
                        for label,chunk in (('http.whole_verified_individual_collection',8*1024**2),('http.segmented_verified_individual_collection',16384)):
                            def collect():
                                receipts=[]
                                for item in config['expected']:
                                    checked=agent_api.verify_artifact(client,config['target'],item['name'],item['sha256'],chunk_bytes=chunk)
                                    if checked['bytes']!=item['bytes']: raise AssertionError('Collection size differs.')
                                    receipts.append(checked)
                                return receipts
                            receipts=metrics.observe(label,collect)
                            metrics.rows[-1]['detail']['whole_sha256_receipts']=receipts
            after=counts(dataset)
            if before!=after: raise AssertionError('Read/preparation changed Run, grant, consumption or reservation counts.')
            identities={'material_sha256':prepared['material_sha256'],'expected_artifacts':config['expected'],
                'input_sha256':prepared['material']['captures']['input/sample']['sha256'],
                'runtime_closure_sha256':prepared['material']['runtime']['closure_sha256'],
                'runtime_files':len(prepared['material']['runtime']['files']),
                'runtime_bytes':sum(item['bytes'] for item in prepared['material']['runtime']['files'].values()),
                'host_files':prepared['material']['host_files']}
            save(output,{'scope':SCOPE,'identities':identities,'pid':os.getpid(),'catalog_id':identity,'state_before':before,'state_after':after,
                'integrity':{'material_equal':True,'captures_equal':True,'inventory_equal':True,'whole_artifacts_equal':bool(config['target']),
                             'no_replay':True,'no_admission_effect':True},'rows':metrics.rows})
        finally:
            if http is not None: stop_server(http,thread)
            dataset.close()


def negative_and_recovery(fixture, repeats):
    """Actual owned fixture refusals and same-Run copy recovery, outside history cells."""
    import agent_api
    import recipe_contract
    import recipe_process
    fixture.start(); dataset=fixture.dataset; runs=dataset.runs; metrics=fixture.metrics
    if fixture.target is None: fixture.populate_one(full_workflow=True)
    with fixture.owner.bound(dataset): original=runs._load(fixture.target)
    before=counts(dataset); original_events=copy.deepcopy(original['events'])
    metrics.labels={'artifacts':fixture.pieces,'terminal_history':before['workspace_runs'],'condition':'negative_integrity'}
    def require_error(operation, function, *, expected=None):
        metrics.observe(operation,function,allow_error=True)
        row=metrics.rows[-1]
        if row['outcome']!='error' or row['error']['code'] is None:
            raise AssertionError('Expected an owned typed refusal: '+operation)
        if expected is not None and row['error']['code']!=expected:
            raise AssertionError('Unexpected refusal code: '+str(row['error']))
    with metrics.instrumentation(dataset):
        source=fixture.project/'input.bin'; saved=source.read_bytes()
        try:
            source.write_bytes(bytes([saved[0]^1])+saved[1:])
            with fixture.owner.bound(dataset):
                require_error('refusal.changed_project_input',lambda:dataset.pipelines.preflight_external(fixture.graph['id'],1,contract_version=3))
        finally: source.write_bytes(saved)
        with fixture.owner.bound(dataset):
            restored=dataset.pipelines.preflight_external(fixture.graph['id'],1,contract_version=3)
            if restored['material_sha256']!=fixture.material: raise AssertionError('Restored input changed material.')
        # Do not mutate an installed runtime. A deliberately mismatched expected
        # inventory tests the existing verifier; actual installation mutation is unavailable.
        spec=copy.deepcopy(original['spec']);spec['runtime_files'][0]['sha256']='f'*64
        require_error('refusal.runtime_expected_inventory_mismatch',lambda:recipe_process.verify_captures(spec))
        metrics.rows[-1]['detail']['scope']='Expected-inventory mismatch only; installed runtime bytes were not changed.'
        def collect(items):
            complete=[]
            for item in items:
                complete.append(agent_api.verify_artifact(fixture.client,fixture.target,item['name'],item['sha256']))
            return complete
        if fixture.pieces>1:
            mixed=copy.deepcopy(fixture.expected);mixed[1]['sha256']='f'*64
            require_error('refusal.partial_failed_selection',lambda:collect(mixed))
            metrics.rows[-1]['detail']['first_item_whole_sha_verified_before_failure']=True
        payload=runs.path/fixture.target/fixture.expected[-1]['name'];retained=payload.read_bytes()
        try:
            payload.write_bytes(retained[:-1]+bytes([retained[-1]^1]))
            require_error('refusal.changed_published_payload',lambda:collect(fixture.expected),expected='artifact_mismatch')
        finally: payload.write_bytes(retained)
        metrics.observe('integrity.restored_whole_collection',lambda:collect(fixture.expected))
        with fixture.owner.bound(dataset): revoked=dataset.access.issue({'label':'T5 disposable revocation witness','scopes':['inspect']})
        denied=agent_api.AgentClient(fixture.endpoint,revoked['token'],dataset.db.dataset_id);denied.bootstrap()
        with fixture.owner.bound(dataset): dataset.access.revoke(revoked['identity']['credential_id'])
        refused=metrics.observe('refusal.revoked_inspection',lambda:denied.call('runs.get',{'run_id':fixture.target}))
        if refused['status']!=401: raise AssertionError('Revoked fixture inspection was not refused.')
    if counts(dataset)!=before: raise AssertionError('Negative reads changed admission counts.')
    with fixture.owner.bound(dataset):
        unchanged=runs._load(fixture.target)
        if unchanged['state']!='completed' or unchanged['events']!=original_events: raise AssertionError('Negative reads changed original state/events.')
    # A separate fresh admission generates a real successful-compute/copy fault.
    # It is excluded from the already completed fixed-history measurements.
    metrics.labels={'artifacts':fixture.pieces,'terminal_history':before['workspace_runs'],'condition':'same_run_publication_recovery'}
    with fixture.owner.bound(dataset): grant=dataset.access.grant_execution(fixture.material,fixture.agent['identity']['actor_id'])
    body={'request_key':'baseline-fault-'+uuid.uuid4().hex,'graph_id':fixture.graph['id'],'graph_revision':1,
        'expected_digest':fixture.material,'approval_id':grant['id']}
    with dataset.access.bind(fixture.agent['token']), patch.object(runs,'_start'):
        admitted=runs.submit_external(body)
    run=runs._load(admitted['id']);copy_verified=runs._copy_verified
    def interrupted(directory,name,item,output=None,**kwargs):
        if output is not None: raise OSError('Authored baseline publication copy fault')
        return copy_verified(directory,name,item,output,**kwargs)
    with metrics.instrumentation(dataset),patch.object(runs,'_copy_verified',interrupted):
        metrics.observe('workflow.real_compute_copy_fault',lambda:runs._run_attempt(run,(runs._capacity.cores[0],),runs._capacity.claim(run)))
    with fixture.owner.bound(dataset): failed=runs._load(run['id'])
    if failed.get('publication_fault') is None or failed['state'] not in ('failed','interrupted'):
        raise AssertionError('Original successful compute/copy fault was not retained.')
    recovery={'run_id':run['id'],'source_ref':failed['publication_source'],'request_key':'baseline-recovery-'+uuid.uuid4().hex}
    count_before=counts(dataset);events=copy.deepcopy(failed['events'])
    with fixture.owner.bound(dataset),metrics.instrumentation(dataset),patch('recipe_process.launch',side_effect=AssertionError('Recovery replayed compute')):
        recovered=metrics.observe('owner.publication_recovery',lambda:runs.recover_publication(recovery))
        if recovered['state']!='published': raise AssertionError('Recovery did not attach result.')
        for cycle in range(repeats+1):
            metrics.labels=dict(metrics.labels,cycle=cycle)
            result=metrics.observe('owner.recovered_result_read',lambda:runs.publication_result(recovered['result_ref']))
            if result['result_ref']!=recovered['result_ref']: raise AssertionError('Result identity differs.')
            proof=metrics.observe('owner.idempotent_recovery_verification',lambda:runs.recover_publication(recovery))
            if proof['result_ref']!=recovered['result_ref']: raise AssertionError('Idempotent result differs.')
        after=runs._load(run['id'])
        if after['state']!=failed['state'] or after['events']!=events or counts(dataset)!=count_before:
            raise AssertionError('Recovery changed original outcome, events or accounting.')
    for item in fixture.expected:
        receipt=metrics.observe('http.recovered_whole_collection',lambda:agent_api.verify_publication_artifact(
            fixture.client,recovered['result_ref'],item['name'],item['sha256']))
        if receipt['bytes']!=item['bytes']: raise AssertionError('Recovered bytes differ.')
    return {'negative_reads_preserved_counts_state_events':True,'same_run_no_replay':True,
        'original_state':failed['state'],'recovered_result_ref':recovered['result_ref'],
        'recovery_preserved_counts':count_before==counts(dataset),
        'installed_runtime_mutation':'unavailable under read-only installation constraint; expected-inventory mismatch exercised instead'}


def environment():
    names=('app.py','pipeline.py','runs.py','recipe_contract.py','recipe_process.py','run_publication.py','metadata.py','agent_api.py')
    return {'production_base':PRODUCTION_BASE,'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'source_sha256':{name:sha((ROOT/name).read_bytes()) for name in names},
        'harness_sha256':sha(Path(__file__).read_bytes()),'python':sys.version,'executable':sys.executable,
        'platform':platform.platform(),'machine':platform.machine(),'cpu_affinity':sorted(os.sched_getaffinity(0)),
        'loadavg':list(os.getloadavg()),'workspace_free_bytes':shutil.disk_usage(ROOT).free,
        'tmp_free_bytes':shutil.disk_usage(tempfile.gettempdir()).free,
        'cgroup_cpu_max':Path('/sys/fs/cgroup/cpu.max').read_text().strip(),
        'cgroup_memory_max':Path('/sys/fs/cgroup/memory.max').read_text().strip()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--history-sizes',default='0,8,55')
    parser.add_argument('--artifact-counts',default='1,20')
    parser.add_argument('--aggregate-bytes',type=int,default=320*1024)
    parser.add_argument('--process-samples',type=int,default=3)
    parser.add_argument('--warm-repeats',type=int,default=2)
    parser.add_argument('--workflow-samples',type=int,default=3)
    parser.add_argument('--worker',type=Path)
    args=parser.parse_args()
    if args.worker:
        config=json.loads(args.worker.read_bytes());worker(config,args.out,args.warm_repeats);return
    histories=sorted(set(map(int,args.history_sizes.split(','))));pieces=list(map(int,args.artifact_counts.split(',')))
    if (not histories or any(not 0<=number<=55 for number in histories) or any(not 1<=number<=32 for number in pieces)
            or not 1<=args.process_samples<=7 or not 1<=args.workflow_samples<=7 or not 0<=args.warm_repeats<=5 or not 1<=args.aggregate_bytes<=1024**2):
        parser.error('Use bounded history0..55, artifacts1..32, samples1..7, warm0..5, aggregate1..1MiB.')
    if not os.environ.get('TULDOK_DATABASE_URL'): parser.error('Requires an explicitly selected disposable PostgreSQL database.')
    args.out.mkdir(parents=True,exist_ok=False);raw=args.out/'raw';raw.mkdir()
    start=environment();save(args.out/'environment-start.json',start);all_rows=[];results=[];integrity=[];cleanup=[]
    try:
        for number in pieces:
            fixture=Fixture.__new__(Fixture)
            try:
                fixture.__init__(number,args.aggregate_bytes)
                material_identity=None
                for history in histories:
                    fixture.open()
                    current=counts(fixture.dataset)['workspace_runs']
                    while current<history:
                        fixture.populate_one(full_workflow=current==0);current+=1
                        print(json.dumps({'progress':'real_history','artifacts':number,'completed':current,'target':history}),flush=True)
                    fixture.close()
                    state=fixture.state();state['history']=history
                    private=fixture.path/'worker.json';private.write_bytes(canonical(state));private.chmod(0o600)
                    for sample in range(args.process_samples):
                        destination=raw/f'artifacts-{number}-history-{history}-process-{sample}.json'
                        command=[sys.executable,str(Path(__file__).resolve()),'--worker',str(private),'--out',str(destination),
                                 '--warm-repeats',str(args.warm_repeats)]
                        subprocess.run(command,cwd=ROOT,check=True,timeout=600)
                        result=json.loads(destination.read_bytes())
                        observed=result['identities']['material_sha256']
                        if material_identity is not None and material_identity!=observed:
                            raise AssertionError('Material differs across process/history samples.')
                        material_identity=observed
                        all_rows.extend(result['rows']);results.append(str(destination.relative_to(args.out)))
                        print(json.dumps({'progress':'measured','artifacts':number,'terminal_history':history,'process_sample':sample}),flush=True)
                integrity.append(negative_and_recovery(fixture,args.warm_repeats))
                all_rows.extend(fixture.metrics.rows)
                save(raw/f'artifacts-{number}-real-history-population.json',{'scope':SCOPE,'rows':fixture.metrics.rows,'integrity':integrity[-1]})
            finally:
                if hasattr(fixture,'schema'): cleanup.append(fixture.cleanup())
        for number in pieces:
            for sample in range(args.workflow_samples):
                fresh=Fixture.__new__(Fixture)
                try:
                    fresh.__init__(number,args.aggregate_bytes)
                    fresh.populate_one(full_workflow=True)
                    all_rows.extend(fresh.metrics.rows)
                    save(raw/f'artifacts-{number}-fresh-workflow-{sample}.json',{'scope':SCOPE,'rows':fresh.metrics.rows,
                        'expected_artifacts':fresh.expected,'counts':counts(fresh.dataset)})
                    print(json.dumps({'progress':'fresh_supported_workflow','artifacts':number,'sample':sample}),flush=True)
                finally:
                    if hasattr(fresh,'schema'):cleanup.append(fresh.cleanup())
        finish=environment()
        if start['source_sha256']!=finish['source_sha256'] or start['harness_sha256']!=finish['harness_sha256']:
            raise AssertionError('Measured source or harness changed during the run.')
        save(args.out/'summary.json',{'scope':SCOPE,'kind':'baseline_only','source':start,'environment_finish':finish,
            'matrix':{'histories':histories,'artifacts':pieces,'aggregate_bytes':args.aggregate_bytes,
                'fresh_process_samples':args.process_samples,'warm_repeats':args.warm_repeats,'fresh_catalog_workflow_samples':args.workflow_samples},
            'cache_policy':'No cache implementation or reuse optimization. Fresh process then repeated complete reverification; OS/PG page caches not flushed.',
            'metrics_limits':['CPU is this co-resident application+HTTP+client process and waited children, not PostgreSQL server CPU.',
                'RSS/HWM are process snapshots and lifetime high-water values, not phase-local peaks.',
                'proc IO counters include instrumentation reads; read_bytes is kernel physical accounting; rchar is logical bytes.',
                'Owner stage times are inclusive/overlapping; never sum them into total workflow time.',
                'HTTP byte counters are declared body bytes, excluding headers; no Authorization values are recorded.',
                'No candidate exists, no paired improvement, budget, OS-cold cache, managed Torch or science claim.'],
            'cleanup':cleanup,'raw_files':sorted(str(path.relative_to(args.out)) for path in raw.glob('*.json')),'integrity_witnesses':integrity,'distributions':distribution(all_rows)})
    except BaseException as error:
        save(args.out/'failure.json',{'type':type(error).__name__,'message':str(error)[:1000],'environment':environment()})
        raise


if __name__=='__main__': main()
