"""Opt-in stopped A/B retention; production backup/restore, no replay.

Select --selection JSON exactly {format: extension_ab_retention_selection_v1,
catalog_id, a: {source,selection,model,material,run,package,package_run,verifier_run},
b: {source,selection,model,material,run}, unrelated_completed_run_ids: []}.
Every named document is an exact reviewed {path: absolute-path, sha256} reference.
A source is the passed canonical qualifier receipt; B source is the passed
extension_author_operator_qualification_v1 receipt. Selection is each real
sdk-selection.json; model/material/run are actual public fetch documents, either
raw or the existing closed {status,result} / {operation,status,result} HTTP wrapper. A package is the real
p5_field_charged_qualification_v1 receipt, with its actual package/verifier Run
fetches. Failed/pre-admission attempts cannot be selected. Additional catalog
Runs must be explicitly reviewed as unrelated completed IDs.

No source catalog/Project/root is changed. Authentication and the explicit new
B disabled/removed snapshots are confined to the disposable restored catalog.
A train@16/32/48/64 and B raw/corrected@32/64 are inspected side by side; their
metrics are never treated as comparable. Actual execution remains opt-in and
requires all exact successful receipts; unit tests supply no acceptance pass.
"""
import argparse
import copy
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from unittest.mock import patch
import uuid

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import agent_api
import backup_metadata as transfer
import extension_evidence as evidence
from qualify_extension_author import regular
from qualify_extension_retention import require,serve,stop
from qualify_scientific_restore import compare,compact,raw_restored,save_private,snapshot,verify_backup

ID=re.compile('[a-f0-9]{32}')
SHA=re.compile('[a-f0-9]{64}')
DOCUMENT_BYTES=2*1024**2
ROLE_KEYS={'a':{'source','selection','model','material','run','package','package_run','verifier_run'},
           'b':{'source','selection','model','material','run'}}


def closed(value,keys,label):
    require(type(value) is dict and set(value)==set(keys),label+' fields differ.')


def reviewed(reference,role=None):
    closed(reference,{'path','sha256'},'Reviewed document reference')
    require(type(reference['path']) is str and Path(reference['path']).is_absolute() and
            type(reference['sha256']) is str and SHA.fullmatch(reference['sha256']),'Exact absolute reviewed reference required.')
    raw=regular(Path(reference['path']),DOCUMENT_BYTES)
    require(hashlib.sha256(raw).hexdigest()==reference['sha256'],'Reviewed receipt identity changed.')
    value=evidence.decode(raw,DOCUMENT_BYTES)
    if type(value) is dict and set(value) in ({'status','result'},{'operation','status','result'}):
        if 'operation' in value:
            operations={'model':{'models.publish','models.material'},'material':{'recipes.material'},
                        'run':{'runs.get'},'package_run':{'runs.get'},'verifier_run':{'runs.get'}}
            require(value['operation'] in operations.get(role,set()),'Reviewed HTTP operation differs from its selected role.')
        require(type(value['status']) is int and 200<=value['status']<300,'Reviewed public fetch was not successful.')
        value=value['result']
    return value


def artifact_index(run):
    require(type(run) is dict and type(run.get('id')) is str and ID.fullmatch(run['id']) and
            run.get('state')=='completed' and run.get('custody_phase')=='drained','Reviewed completed/drained Run required.')
    rows=run.get('artifacts');require(type(rows) is list and 1<=len(rows)<=128,'Reviewed artifact inventory must be bounded/nonempty.')
    result={}
    for item in rows:
        name=item.get('name')
        require(type(name) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,119}',name) and name not in result and
                type(item.get('bytes')) is int and 0<item['bytes']<=64*1024**2 and
                type(item.get('sha256')) is str and SHA.fullmatch(item['sha256']),'Reviewed artifact identity differs.')
        result[name]={key:item[key] for key in ('name','bytes','sha256')}
    require(sum(row['bytes'] for row in result.values())<=64*1024**2,'Reviewed artifact aggregate exceeds 64 MiB.')
    return result


def load_selection(path):
    value=evidence.decode(regular(path,DOCUMENT_BYTES),DOCUMENT_BYTES)
    closed(value,{'format','catalog_id','a','b','unrelated_completed_run_ids'},'A/B retention selection')
    require(value['format']=='extension_ab_retention_selection_v1' and type(value['catalog_id']) is str and
            ID.fullmatch(value['catalog_id']),'Select explicit A/B retention version and catalog.')
    normalized={'catalog_id':value['catalog_id'],'references':copy.deepcopy(value)}
    for label,keys in ROLE_KEYS.items():
        closed(value[label],keys,'Selected '+label.upper())
        docs={key:reviewed(ref,key) for key,ref in value[label].items()}
        source=docs['source'];selection=docs['selection'];run=docs['run'];model=docs['model'];material=docs['material']
        if label=='a':
            require(source.get('state')=='canonical_sdk_source_numerical_cold_passed' and source.get('sdk',{}).get('state')=='passed',
                    'Select successful actual canonical A02+ source; pre-admission failures are unsupported.')
            require(source['model']==model['ref'] and source['material']==material['ref'],'A source/preparation identities differ.')
        else:
            require(source.get('format')=='extension_author_operator_qualification_v1' and source.get('state')=='passed' and
                    source['selection']==selection,'Select actual passed independent B source receipt.')
        require(selection.get('format')=='extension_sdk_conformance_selection_v1' and selection['catalog_id']==value['catalog_id'] and
                source['run_id']==run['id'] and run['study_membership']=={'study_id':selection['study_id'],'trial_id':selection['trial_id']} and
                all(run[key]==selection[key] for key in ('actor_id','approval_id','request_key')),
                'Source selection/Run/Study differs.')
        expected=selection['expected'];inventory=artifact_index(run)
        require('execution-context.json' in inventory and run['approval_material_sha256']==expected['material_sha256'] and
                material['ref']['sha256']==expected['material_sha256'] and model['ref']['sha256']==expected['model_sha256'] and
                model['material']['task']['sha256']==expected['task_sha256'] and
                material['material']['evaluation_profile']['sha256']==expected['profile_definition_sha256'] and
                material['material']['runtime']['sha256']==expected['runtime_sha256'] and
                material['material']['recipe_id']==expected['graph_id'] and material['material']['recipe_revision']==expected['graph_revision'],
                'Exact Task/profile/Model/composition/runtime/graph identity differs.')
        if label=='b':
            require(sorted(source['artifacts'],key=lambda row:row['name'])==sorted(inventory.values(),key=lambda row:row['name']) and
                    source['custody_context']['sha256']==inventory['execution-context.json']['sha256'],'B reviewed artifact/context receipt differs.')
        normalized[label]=docs
    package=normalized['a']['package'];a=normalized['a'];b=normalized['b']
    require(package.get('format')=='p5_field_charged_qualification_v1' and package['source_run_id']==a['run']['id'] and
            package['study_id']==a['selection']['study_id'] and package['runtime_snapshot']['catalog_id']==value['catalog_id'] and
            package['package_run_id']==a['package_run']['id'] and package['verifier_run_id']==a['verifier_run']['id'],
            'Select exact actual canonical A source/package/verifier linkage.')
    artifact_index(a['package_run']);artifact_index(a['verifier_run'])
    require(artifact_index(a['package_run']).get('package.zip',{}).get('sha256')==package['package_sha256'] and
            package['fresh_verification'].get('verified') is True,'Actual whole package/fresh verification required.')
    identities=[a[key]['id'] for key in ('run','package_run','verifier_run')]+[b['run']['id']]
    require(len(set(identities))==4 and a['selection']['study_id']!=b['selection']['study_id'],'Four distinct reviewed Runs/two Studies required.')
    extras=value['unrelated_completed_run_ids']
    require(type(extras) is list and len(extras)<=64 and all(type(x) is str and ID.fullmatch(x) for x in extras) and
            len(set(extras))==len(extras) and not set(extras)&set(identities),'Explicit unrelated completed Run IDs required.')
    normalized['run_ids']=identities;normalized['all_run_ids']=identities+extras
    return normalized


def check_run_set(base,selected):
    require(base['dataset_id']==selected['catalog_id'],'Selected catalog identity differs.')
    require(base['run_states']=={identity:'completed' for identity in selected['all_run_ids']},
            'Catalog Run set differs from explicitly reviewed completed workflows.')


def check_study(state,run_ids,charged):
    require(state['charged']==charged and {row['run_id'] for row in state['reservations']}==set(run_ids) and
            len(state['reservations'])==len(run_ids) and all(row['state']=='settled' for row in state['reservations']),
            'Per-Study finite charges/settled reviewed reservations differ.')


def selected_reads(dataset,selected):
    require(dataset.projects.roots=={},'A/B retained reads require absent roots.')
    result={'runs':{},'sources':{},'studies':{},'artifacts':[]}
    for label in ('a','b'):
        docs=selected[label];reviewed_run=docs['run'];run_id=reviewed_run['id']
        run=dataset.runs.get(run_id)
        require(run==reviewed_run,'Current complete source summary differs from reviewed receipt.')
        model=dataset.models.material(docs['model']['ref'],verify=True)
        material=dataset.pipelines.recipe_material(docs['material']['ref'],verify=True)
        require(model==docs['model'] and material==docs['material'],'Retained source/Model/composition changed.')
        sources={item['import_path']:dataset.models.read_blob(model['ref'],item['blob']) for item in model['material']['source_closure']}
        require(all(hashlib.sha256(sources[item['import_path']]).hexdigest()==item['blob']['sha256'] for item in model['material']['source_closure']),
                'Retained complete source byte identity differs.')
        context,_=dataset.runs.artifact(run_id,'execution-context.json');context=evidence.decode(context)
        require(context['run_id']==run_id and context['static']['model']==model['ref'] and context['composition']==material['ref'] and
                context['static']['task']==model['material']['task'],'Retained context/Task/Model/composition differs.')
        public=dataset.runs.model_evidence(run_id,{},contract_version=2)
        require(public['state']=='verified','Current rootless scientific evidence unavailable.')
        entries=public['checkpoint_index']['entries'];clocks=[16,32,48,64] if label=='a' else [32,64]
        require([row['clocks']['optimizer_update'] for row in entries]==clocks and all(row['clocks'][key] is None for row in entries
                for key in ('epoch','fit_pass','physical_time')),'Reviewed actual checkpoint clocks differ.')
        fields=[]
        for entry in entries:
            for field_id,stage in ([('raw','train')] if label=='a' else [('raw','raw_inference'),('corrected','boundary_enforcement')]):
                query=dict(checkpoint_sha256=entry['checkpoint']['sha256'],member_ordinal=0,field_id=field_id,axis='z',index=2)
                field=dataset.runs.model_evidence(run_id,query,contract_version=2)
                require(field['field']['stage']==stage and field['field']['shape_zyx']==[4,4,4] and field['field']['time_units']=='not_applicable',
                        'Retained explicit field stage/native geometry/time differs.')
                fields.append({'query':query,'result':field})
        study=dataset.studies.get(docs['selection']['study_id'])
        ids=[selected['a'][key]['id'] for key in ('run','package_run','verifier_run')] if label=='a' else [run_id]
        check_study(study,ids,selected['a']['package']['charged'] if label=='a' else docs['source']['charged'])
        result['studies'][label]=study
        result['sources'][label]=dict(model=model,material=material,context=context,public=public,fields=fields,
                                     source_hashes={path:hashlib.sha256(raw).hexdigest() for path,raw in sources.items()})
    runs=[selected['a'][key] for key in ('run','package_run','verifier_run')]+[selected['b']['run']]
    for reviewed_run in runs:
        run=dataset.runs.get(reviewed_run['id']);require(run==reviewed_run,'Full reviewed Run summary/artifact inventory differs.')
        result['runs'][run['id']]=run
        for item in run['artifacts']:
            with dataset.runs.open_artifact(run['id'],item['name']) as (stream,metadata):
                checksum=hashlib.sha256();count=0
                while chunk:=stream.read(1024**2):checksum.update(chunk);count+=len(chunk)
            require(count==metadata['bytes']==item['bytes'] and checksum.hexdigest()==item['sha256'],'Whole artifact bytes differ.')
            result['artifacts'].append(dict(run_id=run['id'],name=item['name'],bytes=count,sha256=checksum.hexdigest()))
    package=dataset.studies.package_state(selected['a']['package']['candidate_id']);receipt=selected['a']['package']
    require(package['state']=='fresh_verified' and any(row['run_id']==receipt['package_run_id'] and row['sha256']==receipt['package_sha256'] for row in package['packages']) and
            any(row['run_id']==receipt['verifier_run_id'] and row['receipt']==receipt['fresh_verification'] for row in package['verifications']),
            'Exact retained canonical A package/fresh verifier differs.')
    require(receipt['fresh_verification']['checkpoint_sha256'] in [row['checkpoint']['sha256'] for row in result['sources']['a']['public']['checkpoint_index']['entries']],
            'Package selected checkpoint differs.')
    result['package']=package
    require(dataset.runs._thread is None,'Retained reads started scheduler.')
    return result


def probe_targets(selected,expected):
    result=[]
    for label in ('a','b'):
        run=selected[label]['run'];entries=expected['sources'][label]['public']['checkpoint_index']['entries']
        checkpoint=entries[-1]['checkpoint']['name']
        result.extend([(run['id'],'model-evidence.json'),(run['id'],checkpoint)])
    result.extend([(selected['a']['package_run']['id'],'package.zip'),(selected['a']['verifier_run']['id'],'verification.json')])
    return [(identity,artifact_index(expected['runs'][identity])[name]) for identity,name in result]


def current_access_checks(dataset,selected,expected,owner,reader,report):
    from access import AccessError
    from agent_api import AgentClient,verify_artifact
    from urllib.error import HTTPError
    from urllib.request import Request,urlopen
    from workbench import WorkbenchError
    server=thread=None
    targets=probe_targets(selected,expected)
    unentered=[dataset.runs.open_artifact(identity,item['name']) for identity,item in targets]
    try:
        server,thread,endpoint=serve(dataset);client=AgentClient(endpoint,reader['token'],dataset.db.dataset_id)
        require(client.selected_contracts()['runs.model_evidence']==2,'Field API2 was not negotiated.')
        for label in ('a','b'):
            field=expected['sources'][label]['fields'][-1]
            require(client.call('runs.model_evidence',dict(run_id=selected[label]['run']['id'],**field['query']))['result']==field['result'],
                    'Negotiated current A/B selected field differs.')
        report['downloads']=[]
        for identity,item in targets:
            raw,_=dataset.runs.artifact(identity,item['name'])
            captured,receipt=dataset.runs.capture_artifact(identity,item['name'],item['sha256'])
            require(raw==captured and receipt['measured_sha256']==item['sha256'],'Current capture/whole identity differs.')
            proof=verify_artifact(client,identity,item['name'],item['sha256'],chunk_bytes=4096)
            require(proof['bytes']==item['bytes'],'Whole-hash HTTP segment identity differs.')
            request=Request(endpoint+f"/api/workspace/runs/{identity}/artifacts/{item['name']}",headers={'Authorization':'Bearer '+reader['token']})
            with urlopen(request,timeout=60) as response:whole=response.read(item['bytes']+1)
            require(len(whole)==item['bytes'] and hashlib.sha256(whole).hexdigest()==item['sha256'],'Whole HTTP identity differs.')
            report['downloads'].append(dict(run_id=identity,name=item['name'],**proof))
        for label in ('a','b'):
            try:dataset.runs.model_evidence(selected[label]['run']['id'],{'split':'test'},contract_version=2)
            except WorkbenchError as error:require(error.code in ('invalid','unsupported'),'Unexpected test refusal.')
            else:raise RuntimeError('Retained test selector accepted.')
        with owner.bound(dataset):dataset.access.revoke(reader['identity']['credential_id'])
        denied=[]
        reads={}
        for identity,item in targets:
            prefix=identity+'/'+item['name']
            reads[prefix+'/summary']=lambda identity=identity:dataset.runs.get(identity)
            reads[prefix+'/whole']=lambda identity=identity,item=item:dataset.runs.artifact(identity,item['name'])
            reads[prefix+'/segment']=lambda identity=identity,item=item:dataset.runs.artifact_segment(identity,item['name'],
                dict(expected_sha256=item['sha256'],offset=0,max_bytes=4096))
            reads[prefix+'/capture']=lambda identity=identity,item=item:dataset.runs.capture_artifact(identity,item['name'],item['sha256'])
        for label in ('a','b'):
            data=expected['sources'][label];identity=selected[label]['run']['id']
            reads[label+'/field']=lambda data=data,identity=identity:dataset.runs.model_evidence(identity,data['fields'][-1]['query'],contract_version=2)
            reads[label+'/model']=lambda data=data:dataset.models.material(data['model']['ref'],verify=True)
            reads[label+'/recipe']=lambda data=data:dataset.pipelines.recipe_material(data['material']['ref'],verify=True)
            blob=data['model']['material']['source_closure'][0]['blob']
            reads[label+'/source']=lambda data=data,blob=blob:dataset.models.read_blob(data['model']['ref'],blob)
        reads['run_list']=dataset.runs.list
        reads['package_state']=lambda:dataset.studies.package_state(selected['a']['package']['candidate_id'])
        for name,action in reads.items():
            try:action()
            except AccessError as error:require((error.code,error.status)==('unauthenticated',401),'Wrong current revoked refusal.');denied.append(name)
            else:raise RuntimeError('Revoked current read accepted: '+name)
        for context in unentered:
            try:
                with context:raise RuntimeError('Revoked unentered stream accepted.')
            except AccessError as error:require(error.status==401,'Wrong stream refusal.')
        for label in ('a','b'):
            require(client.call('runs.model_evidence',{'run_id':selected[label]['run']['id']})['status']==401,'Revoked HTTP field summary accepted.')
        require(client.call('studies.package_state',{'candidate_id':selected['a']['package']['candidate_id']})['status']==401,'Revoked HTTP package summary accepted.')
        identity,item=targets[0]
        require(client.call('runs.artifact_chunk',dict(run_id=identity,name=item['name'],expected_sha256=item['sha256'],offset=0,max_bytes=4096))['status']==401,
                'Revoked HTTP segment accepted.')
        try:urlopen(request,timeout=30)
        except HTTPError as error:require(error.code==401,'Wrong revoked HTTP whole refusal.');error.close()
        else:raise RuntimeError('Revoked HTTP whole accepted.')
        report.update(revoked=denied,unentered_revoked=len(unentered),test_selectors='refused')
    finally:
        if server is not None:stop(server,thread)


def inspect_restored(destination,connection,selected,report):
    from access import AccessError
    from app import Dataset
    from auth_helpers import ExplicitOwnerFixture
    from runtime_snapshots import RuntimeSnapshots
    dataset=None
    with patch('subprocess.Popen',side_effect=AssertionError('Retention must not execute')),\
            patch('runs.Runs._start',side_effect=AssertionError('Retention must not schedule')):
        try:
            dataset=Dataset(destination,dsn=connection,project_roots={})
            owner=ExplicitOwnerFixture.bootstrap(dataset)
            with owner.bound(dataset):
                reader=dataset.access.issue({'label':'Restored A/B current reader','scopes':['inspect']})
                successor=dataset.access.issue({'label':'Restored independent cold reader','scopes':['inspect']})
            with dataset.access.bind(reader['token']):
                expected=selected_reads(dataset,selected)
                descriptor=selected['a']['package']['runtime_snapshot']
                runtime=RuntimeSnapshots(dataset.db,dataset.access,dataset.path).get(descriptor['manifest_sha256'],verify=True)
                require(runtime==dict(descriptor,root=str(dataset.path/'runtime-snapshots'/descriptor['manifest_sha256'])),
                        'Restored whole CPU runtime changed beyond catalog root.')
                current_access_checks(dataset,selected,expected,owner,reader,report)
            dataset.close();dataset=Dataset(destination,dsn=connection,project_roots={})
            try:
                with dataset.access.bind(reader['token']):raise RuntimeError('Revoked credential rebound cold.')
            except AccessError as error:require(error.status==401,'Wrong cold revoked refusal.')
            with dataset.access.bind(successor['token']):
                require(selected_reads(dataset,selected)==expected,'Cold rootless retained A/B meaning changed.')
            report.update(rootless_warm=True,rootless_cold=True,execution_blocked=True,
                side_by_side={label:{'context_sha256':artifact_index(selected[label]['run'])['execution-context.json']['sha256'],
                    'model':expected['sources'][label]['model']['ref'],'task':expected['sources'][label]['model']['material']['task'],
                    'profile':expected['sources'][label]['material']['material']['evaluation_profile'],
                    'source_hashes':expected['sources'][label]['source_hashes'],
                    'fields':[{'query':row['query'],'projection_sha256':transfer.digest(row['result'])} for row in expected['sources'][label]['fields']],
                    'charged':expected['studies'][label]['charged']} for label in ('a','b')},
                artifact_inventory=expected['artifacts'],comparison='Side by side only; no cross-Task metric ranking/comparability claimed.')
        finally:
            if dataset is not None:dataset.close()
    return expected


def disabled_b_copy(destination,connection,selected,output,expected):
    """Add two explicit selection snapshots on the restored disposable copy only."""
    from app import Dataset
    from auth_helpers import ExplicitOwnerFixture
    from workbench import WorkbenchError
    root=output/'restored-only-b-source';root.mkdir(mode=0o700)
    dataset=None;result=[]
    with patch('subprocess.Popen',side_effect=AssertionError('Selection refusal must not execute')),\
            patch('runs.Runs._start',side_effect=AssertionError('Selection refusal must not schedule')):
        try:
            dataset=Dataset(destination,dsn=connection,project_roots={'retention-b':root})
            owner=ExplicitOwnerFixture.bootstrap(dataset)
            with owner.bound(dataset):
                model=selected['b']['model']
                for item in model['material']['source_closure']:
                    name=item['import_path'];path=root/name
                    require(not Path(name).is_absolute() and '..' not in Path(name).parts,'Captured path escaped private restored root.')
                    path.parent.mkdir(parents=True,exist_ok=True)
                    path.write_bytes(dataset.models.read_blob(model['ref'],item['blob']))
                manifests=[path for path in root.rglob('*.json') if path.name=='project.json']
                require(len(manifests)==1,'Expected one exact retained B Project manifest.')
                original=evidence.decode(regular(manifests[0],DOCUMENT_BYTES),DOCUMENT_BYTES)
                require(original['schema_version']==2 and len(original['recipes'])==1 and original['extensions'],'Expected actual B provider selection.')
                def counts():return {name:dataset.db.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in
                    ('workspace_runs','access_execution_grants','access_execution_consumptions','model_attempt_reservations','workspace_recipe_materials')}
                baseline=counts()
                for mode in ('disabled','removed'):
                    manifest=copy.deepcopy(original);manifest['id']=uuid.uuid4().hex;manifest['name']='Restored-only B '+mode
                    if mode=='disabled':manifest['extensions']=[]
                    else:
                        for provider in manifest['extensions']:(root/provider['path']).unlink()
                    filename=mode+'-project.json';(root/filename).write_bytes(evidence.canonical(manifest))
                    dataset.projects.open_snapshot({'root':'retention-b','manifest_path':filename})
                    recipe=manifest['recipes'][0]
                    try:dataset.pipelines.inspect_external_recipe(manifest['id'],recipe['id'],recipe['sha256'],contract_version=2)
                    except WorkbenchError as error:
                        require(error.code in ('unavailable','unsupported','invalid'),'Unexpected disabled/removed provider refusal.')
                        result.append({'mode':mode,'project_id':manifest['id'],'code':error.code})
                    else:raise RuntimeError('Disabled/removed B provider allowed new selection.')
                    require(counts()==baseline,'New disabled/removed selection created execution/material effects.')
                # Existing retained history still uses original captured bytes.
                require(dataset.models.material(model['ref'],verify=True)==model,'B historical Model changed after disable/removal.')
                require(dataset.pipelines.recipe_material(selected['b']['material']['ref'],verify=True)==selected['b']['material'],
                        'B historical composition changed after disable/removal.')
                for row in expected['sources']['b']['fields']:
                    require(dataset.runs.model_evidence(selected['b']['run']['id'],row['query'],contract_version=2)==row['result'],
                            'B historical fields changed after new selection refusal.')
        finally:
            if dataset is not None:dataset.close()
    return result


def project_rows(path,connection):
    from metadata import Metadata
    metadata=Metadata(path,dsn=connection,create=False,schema_version=None)
    try:return {row['id']:row['document'] for row in metadata.execute('SELECT id,document FROM workspace_projects ORDER BY id')}
    finally:metadata.close()


def check_project_rows(original,current,added):
    require(set(current)==set(original)|set(added) and len(set(added))==2 and
            not set(original)&set(added) and all(current[key]==raw for key,raw in original.items()),
            'Restored-only selection replaced or changed an existing Project row.')


def main(args):
    require(args.quiesced,'Explicit --quiesced released catalog/stopped-writers assertion required.')
    selected=load_selection(args.selection)
    source=args.source.resolve();output=args.output.resolve();transfer.separate_paths(source,output)
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    connection=os.environ['TULDOK_DATABASE_URL'];database='tuldok_ab_retention_'+uuid.uuid4().hex;created=False
    report=dict(format='extension_ab_retention_qualification_v1',state='in_progress',source=str(source),output=str(output),
        selection_sha256=transfer.file_hash(args.selection),reviewed_references=selected['references'],
        driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        host_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),started_unix=time.time())
    try:
        base=snapshot(source,connection);check_run_set(base,selected);save_private(output/'baseline.private.json',base)
        report['baseline']=compact(base)
        require(shutil.disk_usage(output).free>2*sum(row.get('bytes',0) for row in base['files'].values())+1024**3,
                'Keep backup/restore plus 1 GiB reserve.')
        backup=output/'stopped-backup';transfer.backup_catalog(source,backup,dsn=connection,quiesced=True)
        report['backup']=verify_backup(backup,base)
        with psycopg.connect(connection,autocommit=True) as admin:admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
        created=True;restored_connection=make_conninfo(connection,dbname=database);destination=output/'restored-catalog'
        transfer.restore_catalog(backup,destination,dsn=restored_connection)
        _,raw=raw_restored(backup,destination,base,restored_connection);report['raw_restore']=compact(raw)
        expected=inspect_restored(destination,restored_connection,selected,report)
        exclude=tuple(path.name for path in destination.glob('.restore-receipt-*.json'))
        after_reads=snapshot(destination,restored_connection,exclude=exclude)
        immutable=[name for name in base['tables'] if name not in ('access_actors','access_credentials','access_audit')]
        require(all(after_reads['tables'][name]==base['tables'][name] for name in immutable),
                'Rootless retained reads changed domain/grant/reservation/consumption rows.')
        require(after_reads['files']==base['files'] and after_reads['modes']==base['modes'] and after_reads['custody']==base['custody'],
                'Rootless retained files/modes/custody changed.')
        report['read_only_table_parity']=immutable
        original_projects=project_rows(destination,restored_connection)
        report['new_selection_refusals']=disabled_b_copy(destination,restored_connection,selected,output,expected)
        current_projects=project_rows(destination,restored_connection)
        added={row['project_id'] for row in report['new_selection_refusals']}
        check_project_rows(original_projects,current_projects,added)
        report['original_project_rows_unchanged']=True
        final=snapshot(destination,restored_connection,exclude=exclude)
        require(all(final['tables'][name]==base['tables'][name] for name in immutable if name!='workspace_projects') and
                final['files']==base['files'] and final['modes']==base['modes'] and final['custody']==base['custody'],
                'Restored-only selection exercise changed historical/execution state.')
        compare(snapshot(source,connection),base)
        # Re-read every review ref so a coordinated external edit cannot retarget
        # the final receipt after successful inspection.
        require(load_selection(args.selection)==selected,'Reviewed retention selection changed during execution.')
        require(hashlib.sha256(Path(__file__).read_bytes()).hexdigest()==report['driver_sha256'],'Retention driver changed during execution.')
        report.update(state='passed',source_unchanged=True,restored_database=database,restored_database_retained=True,
                      finished_unix=time.time(),scope='Actual stopped A/B retention and current access; no replay or physical/comparable-metric claim.')
        save_private(output/'report.json',report)
        print('PASS actual A/B retention '+str(output),flush=True)
    except BaseException as error:
        report.update(state='failed',error_type=type(error).__name__,failure=str(error),restored_database=database if created else None)
        save_private(output/'failure.json',report);raise


def parser():
    result=argparse.ArgumentParser(description=__doc__)
    result.add_argument('--source',type=Path,required=True)
    result.add_argument('--selection',type=Path,required=True)
    result.add_argument('--output',type=Path,required=True)
    result.add_argument('--quiesced',action='store_true')
    return result


if __name__=='__main__':main(parser().parse_args())
