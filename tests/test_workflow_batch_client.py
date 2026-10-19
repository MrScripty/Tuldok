"""Explicit bounded batch consumer; controlled bytes do not qualify a producer."""
import base64
import copy
from contextlib import contextmanager
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import tempfile
import threading
import unittest
from unittest.mock import patch

import agent_api
from agent_api import AgentAPIError
import project_cli
from tuldok_client import WorkflowClient, _digest, MAX_BATCH_BYTES

CATALOG, RUN = 'a'*32, 'b'*32


def ref():
    return {'kind':'recovered_publication_result','schema_version':1,'catalog_id':CATALOG,'run_id':RUN,
            **{key:'c'*64 for key in ('material_sha256','inventory_sha256','custody_receipt_sha256','sha256')}}


class BatchFixture:
    catalog_id = CATALOG

    def __init__(self, count=3):
        self.raw={f'item-{index:02}.bin':b'neutral exact bytes '+str(index).encode() for index in range(count)}
        self.raw['item-00.bin']=b''
        self.requests=[];self.negotiations=0;self.contract=1;self.transform=None;self.failure=None;self.after_batch=None
        self.declared={}

    def selected_contracts(self):
        self.negotiations+=1
        return {} if self.contract is None else {'runs.artifact_segments':self.contract,'runs.artifact_chunk':1}

    @contextmanager
    def read_budget(self, deadline=None, cancelled=None):
        if cancelled is not None and cancelled.is_set():raise AgentAPIError('Stopped','stopped',409)
        yield self

    def inventory(self):
        return [{'name':name,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':self.declared.get(name,len(raw))}
                for name,raw in sorted(self.raw.items())]

    def segment(self, selected):
        raw=self.raw[selected['name']];offset=selected['offset'];piece=raw[offset:offset+selected['max_bytes']]
        result={'run_id':RUN,'name':selected['name'],'expected_sha256':selected['expected_sha256'],
            'total_bytes':len(raw),'media_type':'application/octet-stream','offset':offset,'bytes':len(piece),
            'next_offset':offset+len(piece),'eof':offset+len(piece)==len(raw),
            'segment_sha256':hashlib.sha256(piece).hexdigest(),'data_base64':base64.b64encode(piece).decode(),
            'verification':'segment_read_whole_hash_unverified'}
        source=selected.get('source')
        if source and source['kind']=='publication':result['result_ref']=copy.deepcopy(source['ref'])
        elif 'ref' in selected:result['result_ref']=copy.deepcopy(selected['ref'])
        return result

    def call(self, operation, arguments):
        self.requests.append((operation,copy.deepcopy(arguments)))
        if operation=='runs.get':return {'status':200,'result':{'id':RUN,'dataset_id':CATALOG,'state':'completed','artifacts':self.inventory()}}
        if operation=='runs.publication_result':return {'status':200,'result':{'result_ref':copy.deepcopy(arguments['ref']),
            'catalog_id':CATALOG,'artifacts':self.inventory()}}
        if operation=='runs.artifact_segments':
            if self.failure is not None:raise self.failure
            value={'format':'artifact_segments_v1','items':[{'key':item['key'],'source':copy.deepcopy(item['source']),
                'status':200,'result':self.segment(item)} for item in arguments['items']]}
            if self.transform is not None:self.transform(value)
            if self.after_batch is not None:self.after_batch()
            return {'status':200,'result':value}
        if operation in ('runs.artifact_chunk','runs.publication_artifact_chunk'):
            return {'status':200,'result':self.segment(arguments)}
        raise AssertionError(operation)


class BatchWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.directory=Path(self.temp.name)
        self.client=BatchFixture();self.workflow=WorkflowClient(self.client)
        self.manifest=self.workflow.collection_manifest(run_id=RUN,names=list(self.client.raw));self.client.requests.clear()

    def collect(self, **kwargs):return self.workflow.collect_batch(self.manifest,self.directory,**kwargs)

    def no_outputs(self):self.assertEqual(list(self.directory.iterdir()),[])

    def assert_one_batch(self):
        self.assertEqual([operation for operation,_ in self.client.requests],['runs.get','runs.artifact_segments'])

    def test_twenty_whole_files_and_empty_item_publish_private_exact_outputs_in_one_batch(self):
        self.client=BatchFixture(20);self.workflow=WorkflowClient(self.client)
        self.manifest=self.workflow.collection_manifest(run_id=RUN,names=list(self.client.raw));self.client.requests.clear()
        with patch('tuldok_client.os.fsync',wraps=os.fsync) as synced:receipt=self.collect()
        self.assertEqual(receipt['state'],'complete');self.assertEqual(len(receipt['items']),20);self.assert_one_batch()
        self.assertEqual(synced.call_count,20)
        for item in receipt['items']:
            path=self.directory/item['name'];expected=self.client.raw[item['name']]
            self.assertEqual(path.read_bytes(),expected);self.assertEqual(path.stat().st_mode&0o777,0o600)
            self.assertEqual(item['receipt']['sha256'],hashlib.sha256(expected).hexdigest())
            self.assertEqual(item['receipt']['verification'],'whole_sha256_verified')
        self.assertFalse(list(self.directory.glob('.tuldok-*')))

    def test_known_oversize_refuses_before_negotiation_or_any_dispatch_and_exact_cap_is_allowed(self):
        manifest=copy.deepcopy(self.manifest);manifest['items'][1]['bytes']=MAX_BATCH_BYTES+1
        manifest['sha256']=_digest({key:value for key,value in manifest.items() if key!='sha256'})
        with self.assertRaises(AgentAPIError) as caught:self.workflow.collect_batch(manifest,self.directory)
        self.assertEqual((caught.exception.code,caught.exception.status),('too_large',413));self.assertEqual(self.client.negotiations,0)
        self.assertEqual(self.client.requests,[]);self.no_outputs()
        names=list(self.client.raw);self.client.declared[names[1]]=MAX_BATCH_BYTES-1-len(self.client.raw[names[2]])
        manifest=self.workflow.collection_manifest(run_id=RUN,names=names);self.client.requests.clear()
        self.client.failure=AgentAPIError('Stop after cap validation','fixture_after_cap',409)
        with self.assertRaises(AgentAPIError) as caught:self.workflow.collect_batch(manifest,self.directory)
        self.assertEqual(caught.exception.code,'fixture_after_cap');self.assert_one_batch()
        self.assertEqual(sum(item['max_bytes'] for item in self.client.requests[-1][1]['items']),MAX_BATCH_BYTES)

    def test_missing_or_unknown_batch_contract_never_falls_back_to_individual_collection(self):
        for contract in (None,2):
            self.client.contract=contract;self.client.requests.clear()
            with self.subTest(contract=contract),self.assertRaises(AgentAPIError) as caught:self.collect()
            self.assertEqual(caught.exception.code,'operation_unsupported');self.assertEqual(self.client.requests,[]);self.no_outputs()

    def test_service_auth_and_transport_errors_never_retry_or_publish(self):
        for code,status in [('unauthenticated',401),('forbidden',403),('unavailable',503),('transport',502)]:
            self.client.requests.clear();self.client.failure=AgentAPIError('Authored '+code,code,status)
            with self.subTest(code=code),self.assertRaises(AgentAPIError) as caught:self.collect()
            self.assertEqual((caught.exception.code,caught.exception.status),(code,status));self.assert_one_batch();self.no_outputs()

    def test_request_aware_decoder_rejects_order_source_and_segment_identity_before_any_write(self):
        mutations=[lambda value:value['items'].reverse(),
            lambda value:value['items'][0]['source'].update(run_id='d'*32),
            lambda value:value['items'][1]['result'].update(name='different.bin'),
            lambda value:value['items'][1]['result'].update(expected_sha256='f'*64)]
        for mutate in mutations:
            self.client.requests.clear();self.client.transform=mutate
            with self.subTest(mutation=mutate),self.assertRaises(AgentAPIError):self.collect()
            self.assert_one_batch();self.no_outputs()

    def test_item_failure_returns_partial_receipt_and_stops_writes_without_fallback(self):
        def fail(value):
            value['items'][1]={'key':value['items'][1]['key'],'source':value['items'][1]['source'],
                'status':409,'error':{'code':'conflict','message':'Exact selected whole hash changed'}}
        self.client.transform=fail;receipt=self.collect();self.assert_one_batch()
        self.assertEqual(receipt['state'],'partial');self.assertEqual([row['state'] for row in receipt['items']],['verified','refused','outstanding'])
        self.assertEqual(receipt['items'][1]['error'],{'code':'conflict','error':'Exact selected whole hash changed','status':409})
        self.assertEqual([path.name for path in self.directory.iterdir()],['item-00.bin'])
        # Explicit ordinary collect uses the same receipt and reauthorizes local
        # successes, then restarts missing files. No automatic retry occurs above.
        self.client.transform=None;self.client.requests.clear()
        resumed=self.workflow.collect(self.manifest,self.directory,resume=json.loads(json.dumps(receipt)))
        self.assertEqual(resumed['state'],'complete');self.assertTrue(all(path.read_bytes()==self.client.raw[path.name] for path in self.directory.iterdir()))
        self.assertEqual([op for op,_ in self.client.requests],['runs.get']+['runs.artifact_chunk']*3)

    def test_valid_segment_hash_is_not_mistaken_for_the_selected_whole_hash(self):
        def corrupt(value):
            segment=value['items'][1]['result'];raw=b'x'*segment['bytes']
            segment.update(data_base64=base64.b64encode(raw).decode(),segment_sha256=hashlib.sha256(raw).hexdigest())
        self.client.transform=corrupt;receipt=self.collect();self.assert_one_batch()
        self.assertEqual([row['state'] for row in receipt['items']],['verified','refused','outstanding'])
        self.assertEqual(receipt['items'][1]['error']['code'],'artifact_mismatch');self.assertFalse((self.directory/'item-01.bin').exists())

    def test_whole_length_and_eof_are_required_and_no_segment_followup_is_dispatched(self):
        def short(value):
            segment=value['items'][1]['result'];raw=self.client.raw['item-01.bin'][:3]
            segment.update(bytes=3,next_offset=3,eof=False,data_base64=base64.b64encode(raw).decode(),segment_sha256=hashlib.sha256(raw).hexdigest())
        self.client.transform=short;receipt=self.collect();self.assert_one_batch()
        self.assertEqual(receipt['items'][1]['error']['code'],'artifact_mismatch')
        self.assertEqual(receipt['items'][2]['state'],'outstanding')

    def test_preexisting_and_racing_destinations_are_never_clobbered(self):
        path=self.directory/'item-01.bin';path.write_bytes(b'original')
        receipt=self.collect();self.assertEqual(self.client.requests,[]);self.assertEqual(path.read_bytes(),b'original')
        self.assertEqual([row['state'] for row in receipt['items']],['outstanding','refused','outstanding'])
        path.unlink();link=os.link
        def race(source,destination,**kwargs):
            if Path(destination).name=='item-01.bin':Path(destination).write_bytes(b'racing owner file')
            return link(source,destination,**kwargs)
        with patch('tuldok_client.os.link',side_effect=race):receipt=self.collect()
        self.assert_one_batch();self.assertEqual(path.read_bytes(),b'racing owner file')
        self.assertEqual([row['state'] for row in receipt['items']],['verified','refused','outstanding'])
        self.assertFalse(list(self.directory.glob('.tuldok-*')))

    def test_fsync_failure_discards_provisional_and_does_not_publish_following_items(self):
        with patch('tuldok_client.os.fsync',side_effect=OSError('Authored disk fault')):receipt=self.collect()
        self.assert_one_batch();self.assertEqual(receipt['items'][0]['error']['code'],'unavailable');self.no_outputs()

    def test_pre_cancel_and_cancel_after_reply_leave_every_item_outstanding(self):
        stop=threading.Event();stop.set();receipt=self.collect(cancelled=stop)
        self.assertEqual(receipt['state'],'stopped');self.assertEqual(self.client.requests,[]);self.assertEqual(self.client.negotiations,0)
        stop.clear();self.client.after_batch=stop.set;receipt=self.collect(cancelled=stop)
        self.assertEqual(receipt['state'],'stopped');self.assert_one_batch();self.no_outputs()

    def test_cancel_after_fsync_and_after_one_published_file_are_fenced(self):
        stop=threading.Event();sync=os.fsync
        def cancelled_sync(fd):sync(fd);stop.set()
        with patch('tuldok_client.os.fsync',side_effect=cancelled_sync):receipt=self.collect(cancelled=stop)
        self.assertEqual(receipt['state'],'stopped');self.no_outputs()
        stop.clear();self.client.requests.clear();link=os.link
        def cancelled_link(source,destination,**kwargs):
            result=link(source,destination,**kwargs);stop.set();return result
        with patch('tuldok_client.os.link',side_effect=cancelled_link):receipt=self.collect(cancelled=stop)
        self.assertEqual(receipt['state'],'stopped');self.assertEqual([row['state'] for row in receipt['items']],['verified','outstanding','outstanding'])
        self.assert_one_batch();self.assertFalse(list(self.directory.glob('.tuldok-*')))

    def test_publication_uses_exact_attached_ref_and_preserves_it_in_each_whole_receipt(self):
        self.manifest=self.workflow.collection_manifest(result_ref=ref(),names=list(self.client.raw));self.client.requests.clear()
        receipt=self.collect();self.assertEqual(receipt['state'],'complete')
        self.assertEqual([op for op,_ in self.client.requests],['runs.publication_result','runs.artifact_segments'])
        self.assertTrue(all(item['receipt']['result_ref']==ref() for item in receipt['items']))
        self.assertTrue(all(item['source']=={'kind':'publication','ref':ref()} for item in self.client.requests[-1][1]['items']))

    def test_cli_selects_batch_explicitly_and_does_not_advertise_batch_resume(self):
        manifest=self.directory/'manifest.json';manifest.write_text(json.dumps(self.manifest))
        output=self.directory/'outputs';output.mkdir();stdout,stderr=io.StringIO(),io.StringIO();before=signal.getsignal(signal.SIGINT)
        with patch.object(project_cli.AgentClient,'from_config',return_value=self.client),patch('sys.stdout',stdout),patch('sys.stderr',stderr):
            status=project_cli.main(['--config','/not-read/private.json','collect-batch','--manifest',str(manifest),'--directory',str(output)])
        self.assertEqual(status,0,stderr.getvalue());self.assertEqual(json.loads(stdout.getvalue())['state'],'complete');self.assert_one_batch()
        self.assertIs(signal.getsignal(signal.SIGINT),before)
        parser=project_cli.parser()
        with patch('sys.stderr',io.StringIO()),self.assertRaises(SystemExit):
            parser.parse_args(['--config','/not-read/private.json','collect-batch','--manifest',str(manifest),'--directory',str(output),'--resume',str(manifest)])


if __name__=='__main__':unittest.main()
