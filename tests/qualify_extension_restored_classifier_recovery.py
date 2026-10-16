"""Read-only completion of the exact already-trained E4 classifier witness.

Never admit, resume, reconcile or train. Preserve the original failed driver
receipt: its final outer-manifest capture was outside the payload contract.
The outer manifest receives whole/stream verification; only its declared,
currently unlocked payloads receive publication captures.
"""
import argparse
import hashlib
import os
from pathlib import Path
import stat
from unittest.mock import patch

from psycopg.conninfo import make_conninfo

from app import Dataset
from auth_helpers import ExplicitOwnerFixture
import backup_metadata as transfer
import qualify_extension_ab_retention as retention
from qualify_extension_restored_classifier import guard_output, read_report, require
from qualify_scientific_restore import compare, read_private, save_private, snapshot
from workbench import WorkbenchError


DOCUMENTS=('failure','before-admission','prepared','admission','run','evidence','study')


def sources(path, expected_sha):
    value=retention.reviewed({'path':str(path.resolve()),'sha256':expected_sha})
    retention.closed(value,{'format','failed_output','documents','retention_report',
        'disabled_selection_report','selection','original_driver','root_baseline'},'Recovery source inventory')
    require(value['format']=='extension_restored_classifier_recovery_source_v1','Wrong recovery source format.')
    directory=Path(value['failed_output'])
    require(directory.is_absolute() and directory.is_dir(),'Select the existing failed source output.')
    retention.closed(value['documents'],DOCUMENTS,'Held completed classifier documents')
    docs={}
    for name,reference in value['documents'].items():
        require(Path(reference['path'])==directory/(name+'.json'),'Held source role/path differs.')
        docs[name]=retention.reviewed(reference)
    original=value['original_driver']
    retention.closed(original,{'path','sha256'},'Original driver reference')
    raw=retention.regular(Path(original['path']),128*1024)
    require(hashlib.sha256(raw).hexdigest()==original['sha256']==docs['failure']['driver_sha256'],
            'Original failed driver source differs.')
    return value,docs,directory


def bind_completed(docs,report,destination,database,report_sha,disabled_sha,selected):
    failed=docs['failure'];prepared=docs['prepared'];run=docs['run'];study=docs['study']
    trial=prepared['trial'];reservation=docs['admission']['reservation']
    require(failed['format']=='extension_restored_classifier_continuity_v1' and failed['state']=='failed' and
        failed['failure_type']=='WorkbenchError' and failed['failure']=='Classifier publication source differs.' and
        failed['admission_state']=='admitted' and docs['before-admission']['admission_state']=='may_have_been_sent',
        'Only the preserved known post-completion outer-manifest failure may recover.')
    require(failed['retention_report_sha256']==report_sha and failed['disabled_selection_report_sha256']==disabled_sha and
        failed['selection_sha256']==report['selection_sha256'] and failed['catalog_path']==str(destination) and
        failed['database_name']==database and failed['catalog_id']==selected['catalog_id'],
        'Completed source does not belong to this qualified restore.')
    require(run['id']==failed['run_id']==docs['admission']['run']['id']==reservation['run_id'] and
        run['state']=='completed' and run['graph']==prepared['graph'] and run['release_id']==prepared['release']['id'] and
        run['study_membership']=={'study_id':trial['study_id'],'trial_id':trial['id']} and
        run['approval_material_sha256']==trial['material']['sha256']==reservation['material_sha256'] and
        reservation['study_id']==trial['study_id']==prepared['study']['id']==study['study']['id'] and
        reservation['trial_id']==trial['id'] and trial['material']['catalog_id']==selected['catalog_id'],
        'Held admission/Run/Model/graph/release/Study/material identities differ.')
    require(study['charged']['attempt_slots']==1 and len(study['reservations'])==1 and
        study['reservations'][0]['state']=='settled' and study['reservations'][0]['run_id']==run['id'] and
        study['reservations'][0]['id']==reservation['id'],'Require exactly one already settled actual attempt.')
    entries=docs['evidence']['checkpoint_index']['entries']
    require(docs['evidence']['state']=='verified' and len(entries)==1 and entries[0]['clocks']['epoch']==1,
        'Require the held actual one-epoch evidence.')


def guard_recovery_output(report,destination,selected,failed_output,output):
    require(not output.exists(),'Choose an absent recovery output; never overwrite an attempt.')
    guard_output(report,destination,selected,output)
    for protected in (Path(report['output']),failed_output):transfer.separate_paths(protected,output)


def root_state(roots):
    result={}
    for alias,value in roots.items():
        root=Path(value);rows={}
        for path in [root,*sorted(root.rglob('*'))]:
            info=path.lstat();regular=stat.S_ISREG(info.st_mode)
            require(regular or stat.S_ISDIR(info.st_mode),'Original root contains an unsupported file type.')
            rows[str(path.relative_to(root))]=dict(dev=info.st_dev,inode=info.st_ino,mode=info.st_mode,
                bytes=info.st_size if regular else None,
                sha256=hashlib.sha256(retention.regular(path,retention.DOCUMENT_BYTES)).hexdigest() if regular else None)
        result[alias]=rows
    return result


def domain_state(dataset):
    with dataset.lock,dataset.db.transaction():
        tables=transfer.summaries(transfer.read_catalog(dataset.db))
    return {'tables':{name:row for name,row in tables.items() if name not in
                     ('access_actors','access_credentials','access_audit')},
            'run_directories':sorted(path.name for path in dataset.runs.path.iterdir())}


def main(args):
    source,docs,failed_output=sources(args.source_inventory,args.source_inventory_sha256)
    report,destination,database,report_sha=read_report(Path(source['retention_report']['path']))
    require(report_sha==source['retention_report']['sha256'],'Qualified core report differs.')
    selected=retention.load_selection(Path(source['selection']['path']))
    require(transfer.file_hash(Path(source['selection']['path']))==source['selection']['sha256']==report['selection_sha256'] and
        selected['references'].get('current_roots')==report['reviewed_references'].get('current_roots'),
        'Select the exact qualified original selection/root reference.')
    disabled=retention.reviewed(source['disabled_selection_report']);disabled_sha=source['disabled_selection_report']['sha256']
    require(disabled['format']=='extension_ab_restored_disable_refusal_v1' and disabled['state']=='passed' and
        disabled['retention_report_sha256']==report_sha and disabled['restored_catalog_path']==str(destination) and
        {row['mode'] for row in disabled['new_selection_refusals']}=={'disabled','removed'},'Exact actual B refusals required.')
    bind_completed(docs,report,destination,database,report_sha,disabled_sha,selected)
    original_roots=retention.reviewed(source['root_baseline'])
    require(root_state(selected['current_roots'])==original_roots,'Original root inode/byte baseline differs.')
    output=args.output.resolve();guard_recovery_output(report,destination,selected,failed_output,output)
    output.mkdir(mode=0o700,parents=True)
    original_connection=os.environ['TULDOK_DATABASE_URL'];connection=make_conninfo(original_connection,dbname=database)
    baseline=read_private(Path(report['output'])/'baseline.private.json')
    compare(snapshot(Path(report['source']),original_connection),baseline)
    roots={'retention-b':str(Path(report['output'])/'restored-only-b-source')}
    dataset=owner=None
    try:
        with patch('subprocess.Popen',side_effect=AssertionError('Recovery must not execute')),\
                patch('runs.Runs._start',side_effect=AssertionError('Recovery must not schedule')),\
                patch('experiments.Experiments.admit',side_effect=AssertionError('Recovery must not admit')),\
                patch('runs.Runs.submit',side_effect=AssertionError('Recovery must not submit a built-in')),\
                patch('runs.Runs.submit_external',side_effect=AssertionError('Recovery must not submit external work')):
            dataset=Dataset(destination,dsn=connection,project_roots=roots)
            require(dataset.db.connection.info.dbname==database and dataset.db.dataset_id==selected['catalog_id'],
                    'Restored connection/catalog differs.')
            owner=ExplicitOwnerFixture.bootstrap(dataset)
            with owner.bound(dataset):
                before=domain_state(dataset)
                run=docs['run'];prepared=docs['prepared'];model=prepared['model'];trial=prepared['trial'];study=docs['study']
                require(dataset.runs.get(run['id'])==run and dataset.models.material(model['ref'],verify=True)==model and
                    dataset.studies.get(study['study']['id'])==study and dataset.runs.model_evidence(run['id'])==docs['evidence'],
                    'Cold actual completed Run/Model/Study/evidence differs.')
                material=dataset.pipelines.recipe_material(trial['material'],verify=True)
                require(material['ref']==trial['material'],'Cold exact material identity differs.')
                manifest_raw,_=dataset.runs.artifact(run['id'],'artifact-manifest.json')
                manifest=retention.evidence.decode(manifest_raw)
                payloads={row['name'] for row in manifest['artifacts']}
                require(len(payloads)==len(manifest['artifacts']) and
                    payloads=={row['name'] for row in run['artifacts']}-{'artifact-manifest.json'},
                    'Publication payload inventory differs from the held Run.')
                cold=[];locked=[];captures=[]
                for item in run['artifacts']:
                    if item['locked']:
                        try:dataset.runs.artifact(run['id'],item['name'])
                        except WorkbenchError as error:
                            require((error.code,error.status)==('conflict',409),'Wrong protected test refusal.')
                            locked.append(item['name']);continue
                        raise RuntimeError('Protected classifier test output disclosed.')
                    raw,_=dataset.runs.artifact(run['id'],item['name'])
                    with dataset.runs.open_artifact(run['id'],item['name']) as (stream,metadata):
                        checksum=hashlib.sha256();count=0
                        while piece:=stream.read(1024**2):checksum.update(piece);count+=len(piece)
                    require(len(raw)==count==metadata['bytes']==item['bytes'] and
                        hashlib.sha256(raw).hexdigest()==checksum.hexdigest()==item['sha256'],'Cold whole/stream identity differs.')
                    if item['name'] in payloads:
                        captured,capture=dataset.runs.capture_artifact(run['id'],item['name'],item['sha256'])
                        require(raw==captured and capture['measured_sha256']==item['sha256'],'Declared payload capture differs.')
                        captures.append(item['name'])
                    cold.append({key:item[key] for key in ('name','bytes','sha256')})
                save_private(output/'cold-custody.json',{'state':'passed','whole_stream':cold,'captured_payloads':captures,
                    'outer_manifest':'whole_and_stream_only; excluded by builtin publication-source contract',
                    'protected_locked':locked,'process_and_scheduler_blocked':True})
                dataset.projects.roots={}
                historical=retention.selected_reads(dataset,selected)
                for label in ('a','b'):
                    held=report['side_by_side'][label]['fields'];actual=historical['sources'][label]['fields']
                    require([{'query':row['query'],'projection_sha256':transfer.digest(row['result'])} for row in actual]==held,
                            'Historical held exact field projections differ.')
                releasedoc=next(row for row in dataset.pipelines.releases() if row['id']==prepared['release']['id'])
                require(dataset.runs._thread is None,'Recovery started a supervisor.')
                after=domain_state(dataset)
                require(before==after,'Read-only recovery changed domain rows or Run directories.')
                dataset.access.logout()
        dataset.close();dataset=None
        compare(snapshot(Path(report['source']),original_connection),baseline)
        require(root_state(selected['current_roots'])==original_roots,'Original roots changed during recovery.')
        require(sources(args.source_inventory,args.source_inventory_sha256)[0]==source,'Held recovery sources changed.')
        checks=dict(disposable_restored_catalog=True,refusals=[dict(mode=row['mode'],project_id=row['project_id'],
            recipe_id=selected['b']['model']['material']['source_selector']['recipe_id']) for row in disabled['new_selection_refusals']],
            retained_runs=[dict(label='a',run_id=selected['a']['run']['id'],expected_fields=[dict(field_id='raw',stage='train')]),
                dict(label='b',run_id=selected['b']['run']['id'],expected_fields=[dict(field_id='raw',stage='raw_inference'),
                    dict(field_id='corrected',stage='boundary_enforcement')])],unrelated_run_id=run['id'],
            unrelated_graph_id=prepared['graph']['id'],unrelated_release_id=prepared['release']['id'],
            unrelated_recipe_choices=releasedoc['allowed_recipes'])
        for row in checks['retained_runs']:
            save_private(output/('native-'+row['label']+'-source.json'),dict(catalog_path=str(destination),run_id=row['run_id'],
                project_roots=roots,expected_fields=row['expected_fields'],restored_checks=checks))
        save_private(output/'receipt.json',dict(format='extension_restored_classifier_recovery_v1',state='passed',
            source_inventory_sha256=args.source_inventory_sha256,retention_report_sha256=report_sha,
            disabled_selection_report_sha256=disabled_sha,selection_sha256=report['selection_sha256'],
            driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),run_id=run['id'],
            study_id=study['study']['id'],trial_id=trial['id'],model=model['ref'],material=material['ref'],
            charged=study['charged'],built_in_epoch=1,cold_exact_objects=True,cold_whole_stream_count=len(cold),
            declared_payload_capture_count=len(captures),protected_locked=locked,original_failure_preserved=True,
            additional_admission=False,additional_training=False,process_and_scheduler_blocked=True,
            domain_before=before,domain_after=after,
            historical_A_B_package_unchanged=True,source_unchanged=True,original_root_inodes_bytes_unchanged=True,native_checks=checks,
            scope='Same completed one-epoch private diagnostic fixture; native browser remains a separate gate.'))
        print('PASS same completed classifier read-only recovery '+run['id'],flush=True)
    except BaseException as error:
        save_private(output/'failure.json',dict(format='extension_restored_classifier_recovery_v1',state='failed',
            source_inventory_sha256=args.source_inventory_sha256,run_id=docs['run']['id'],
            additional_admission=False,additional_training=False,failure_type=type(error).__name__,failure=str(error)))
        raise
    finally:
        if dataset is not None:dataset.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-inventory',type=Path,required=True)
    parser.add_argument('--source-inventory-sha256',required=True)
    parser.add_argument('--output',type=Path,required=True)
    main(parser.parse_args())
