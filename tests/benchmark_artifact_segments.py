"""Same-head, same-inventory sequential-vs-batch neutral collection pairs.

No cache, training or science. Three fresh processes with two warm pairs each;
arm order alternates. Zero terminal history has no eligible artifact and is
recorded unavailable rather than inventing a successful zero-history read.
"""
import argparse
import base64
import copy
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch

from benchmark_lab_workflow import (Fixture, Metrics, canonical, counts, distribution,
    environment, negative_and_recovery, save, server, sha, stop_server)

ROOT=Path(__file__).resolve().parents[1]
BASE='2d8b7d79110f210896dcdda8df08f6385cabf2d3'
SCOPE='Neutral deterministic byte-copy collection; no training, CUDA or numerical acceptance.'


def attribution():
    value=environment()
    value['production_base']=BASE
    value['paired_harness_sha256']=sha(Path(__file__).read_bytes())
    value['comparison']='Alternating individual/batch arms on the same candidate checkout, catalog and inventory.'
    return value


def collect_batch(client, source, expected):
    import agent_api
    request={'items':[{'key':str(index),'source':source,'name':item['name'],
        'expected_sha256':item['sha256'],'offset':0,'max_bytes':max(1,item['bytes'])}
        for index,item in enumerate(expected)]}
    envelope=client.call('runs.artifact_segments',request)
    if envelope['status']!=200:raise AssertionError('Batch service refused: '+str(envelope['status']))
    value=agent_api.validate_artifact_segments(envelope['result'],request)
    receipts=[]
    for item,outcome in zip(expected,value['items']):
        if outcome['status']!=200:raise AssertionError('Unexpected batch item refusal: '+outcome['error']['code'])
        raw=base64.b64decode(outcome['result']['data_base64'],validate=True)
        if not outcome['result']['eof'] or len(raw)!=item['bytes'] or sha(raw)!=item['sha256']:
            raise AssertionError('Reassembled batch whole artifact differs.')
        receipts.append({'name':item['name'],'bytes':len(raw),'sha256':sha(raw)})
    return receipts


def collect_individual(client, source, expected):
    import agent_api
    receipts=[]
    for item in expected:
        if source['kind']=='run':
            result=agent_api.verify_artifact(client,source['run_id'],item['name'],item['sha256'],chunk_bytes=max(1,item['bytes']))
        else:
            result=agent_api.verify_publication_artifact(client,source['ref'],item['name'],item['sha256'],chunk_bytes=max(1,item['bytes']))
        receipts.append({'name':item['name'],'bytes':result['bytes'],'sha256':result['sha256']})
    return receipts


def worker(config,destination,repeats):
    metrics=Metrics();metrics.labels={'artifacts':config['artifacts'],'terminal_history':config['history'],
        'condition':'fresh_process','source_kind':config['source']['kind'] if config['source'] else 'unavailable'}
    Dataset=metrics.observe('process.import_application',lambda:importlib.import_module('app').Dataset)
    import agent_api
    with patch('recipe_process.launch',side_effect=AssertionError('Collection pair replayed compute')):
        dataset=metrics.observe('catalog.cold_reopen',lambda:Dataset(config['catalog'],project_roots={'fixture':Path(config['project'])}))
        http=None
        try:
            before=counts(dataset);pairs=[]
            if not config['source']:
                assert before['workspace_runs']==0
                save(destination,{'scope':SCOPE,'availability':'no_eligible_target_in_empty_history','state_before':before,
                    'state_after':counts(dataset),'rows':metrics.rows,'pairs':[]})
                return
            http,thread,endpoint=server(dataset,metrics)
            client=agent_api.AgentClient(endpoint,config['agent_token'],dataset.db.dataset_id)
            metrics.observe('client.bootstrap',client.bootstrap)
            run_id=config['source'].get('run_id') or config['source']['ref']['run_id']
            with dataset.access.bind(config['owner_token']): events=copy.deepcopy(dataset.runs._load(run_id)['events'])
            for cycle in range(repeats+1):
                order=['individual','batch'] if (config['sample']+cycle)%2==0 else ['batch','individual']
                metrics.labels={'artifacts':config['artifacts'],'terminal_history':config['history'],
                    'condition':'first_pair_fresh_process' if cycle==0 else 'warm_pair_same_process',
                    'cycle':cycle,'source_kind':config['source']['kind'],'sample':config['sample'],'order':order}
                results={};walls={}
                for arm in order:
                    function=collect_individual if arm=='individual' else collect_batch
                    results[arm]=metrics.observe('collection.'+config['source']['kind']+'.'+arm,
                        lambda function=function:function(client,config['source'],config['expected']))
                    walls[arm]=metrics.rows[-1]['wall_ns']
                    metrics.rows[-1]['detail']={'whole_sha256_receipts':results[arm]}
                if results['individual']!=results['batch']:raise AssertionError('Paired whole artifact identities differ.')
                pairs.append({'cycle':cycle,'order':order,'individual_wall_ns':walls['individual'],
                    'batch_wall_ns':walls['batch'],'batch_over_individual':walls['batch']/walls['individual'],
                    'whole_artifacts_equal':True})
            after=counts(dataset)
            if before!=after:raise AssertionError('Paired collection changed admission/accounting counts.')
            with dataset.access.bind(config['owner_token']):
                if dataset.runs._load(run_id)['events']!=events:raise AssertionError('Paired collection changed original Run events.')
            save(destination,{'scope':SCOPE,'availability':'eligible_exact_inventory','source':config['source'],
                'expected_artifacts':config['expected'],'state_before':before,'state_after':after,
                'no_replay':True,'whole_artifacts_equal':True,'events_unchanged':True,'rows':metrics.rows,'pairs':pairs})
        finally:
            if http is not None:stop_server(http,thread)
            dataset.close()


def run_processes(fixture,source,history,raw,samples,repeats):
    fixture.close();state=fixture.state();state.update(source=source,history=history)
    private=fixture.path/'pair-worker.json'
    outputs=[]
    for sample in range(samples):
        state['sample']=sample;private.write_bytes(canonical(state));private.chmod(0o600)
        kind=source['kind'] if source else 'unavailable'
        destination=raw/f'{kind}-artifacts-{fixture.pieces}-history-{history}-process-{sample}.json'
        subprocess.run([sys.executable,str(Path(__file__).resolve()),'--worker',str(private),'--out',str(destination),
            '--warm-repeats',str(repeats)],cwd=ROOT,check=True,timeout=600)
        outputs.append(json.loads(destination.read_bytes()))
        print(json.dumps({'progress':'paired','source':kind,'artifacts':fixture.pieces,'history':history,'process':sample}),flush=True)
    return outputs


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True);parser.add_argument('--worker',type=Path)
    parser.add_argument('--history-sizes',default='0,8,55');parser.add_argument('--artifact-counts',default='1,20')
    parser.add_argument('--process-samples',type=int,default=3);parser.add_argument('--warm-repeats',type=int,default=2)
    parser.add_argument('--aggregate-bytes',type=int,default=327680)
    args=parser.parse_args()
    if args.worker:worker(json.loads(args.worker.read_bytes()),args.out,args.warm_repeats);return
    if not os.environ.get('TULDOK_DATABASE_URL'):parser.error('Select an explicitly disposable PostgreSQL database.')
    histories=sorted(set(map(int,args.history_sizes.split(','))));artifacts=list(map(int,args.artifact_counts.split(',')))
    if (not histories or any(not 0<=h<=55 for h in histories) or any(not 1<=a<=20 for a in artifacts)
            or not 1<=args.process_samples<=7 or not 0<=args.warm_repeats<=5 or not 1<=args.aggregate_bytes<=8*1024**2):
        parser.error('Bound histories0..55/artifacts1..20/samples1..7/warm0..5/aggregate<=8MiB.')
    args.out.mkdir(parents=True,exist_ok=False);raw=args.out/'raw';raw.mkdir()
    start=attribution();save(args.out/'environment-start.json',start)
    rows=[];pairs=[];cleanup=[];availability=[];integrity=[]
    try:
        for number in artifacts:
            fixture=Fixture.__new__(Fixture)
            try:
                fixture.__init__(number,args.aggregate_bytes)
                for history in histories:
                    fixture.open();current=counts(fixture.dataset)['workspace_runs']
                    while current<history:
                        fixture.populate_one();current+=1
                        print(json.dumps({'progress':'real_history','artifacts':number,'completed':current,'target':history}),flush=True)
                    source={'kind':'run','run_id':fixture.target} if fixture.target else None
                    for result in run_processes(fixture,source,history,raw,args.process_samples,args.warm_repeats):
                        rows.extend(result['rows']);pairs.extend(result['pairs']);availability.append(result['availability'])
                integrity.append(negative_and_recovery(fixture,0))
                ref=integrity[-1]['recovered_result_ref'];history=counts(fixture.dataset)['workspace_runs']
                for result in run_processes(fixture,{'kind':'publication','ref':ref},history,raw,args.process_samples,args.warm_repeats):
                    rows.extend(result['rows']);pairs.extend(result['pairs']);availability.append(result['availability'])
                save(raw/f'artifacts-{number}-setup-integrity.json',{'scope':SCOPE,'rows':fixture.metrics.rows,'integrity':integrity[-1]})
            finally:
                if hasattr(fixture,'schema'):cleanup.append(fixture.cleanup())
        finish=attribution()
        if any(start[key]!=finish[key] for key in ('head','source_sha256','harness_sha256','paired_harness_sha256')):
            raise AssertionError('Candidate source/harness changed during paired measurement.')
        save(args.out/'summary.json',{'scope':SCOPE,'kind':'paired_same_candidate','source':start,'environment_finish':finish,
            'matrix':{'histories':histories,'artifacts':artifacts,'aggregate_bytes':args.aggregate_bytes,
                'process_samples':args.process_samples,'warm_repeats':args.warm_repeats,
                'publication_history_note':'Additional attachedRef pairs use the same inventory after a real copy fault; total history includes one interrupted original Run.'},
            'distributions':distribution(rows),'pairs':pairs,'availability':availability,'cleanup':cleanup,'integrity':integrity,
            'limits':['No OS/PG cache flush or cache implementation.','First pair alternates order; its second arm follows the first in the same process.',
                'CPU covers app/HTTP/client/waitedchildren, not PostgreSQL backend CPU.','RSS/HWM are snapshots/lifetime values.',
                'Observer I/O and inclusive owner timings are not additive phase peaks.','Whole hashes match; no science acceptance.']})
    except BaseException as error:
        save(args.out/'failure.json',{'type':type(error).__name__,'message':str(error)[:1000],'environment':attribution()})
        raise


if __name__=='__main__':main()
