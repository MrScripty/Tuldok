"""Closed scalar selections and exact thin-client response correlation."""
import copy
import unittest
from unittest.mock import patch

import agent_api as api
from retained_measurements import MeasurementTable, MeasurementComparison, encode
from test_project_files_clients import BINDING, PROJECT, CHECKPOINT, OTHER, bound, client
from test_retained_measurements import fixture
from tuldok_client import ProjectFilesClient


class MeasurementContracts(unittest.TestCase):
    def setUp(self):
        self.table=MeasurementTable(encode(fixture()))
        self.source=dict(format='project_measurement_source_v1',origin_catalog_id=PROJECT,
            id=self.table.sha256,title=self.table.metadata()['title'],blob=dict(sha256=self.table.sha256,bytes=len(encode(fixture()))),
            source=dict(origin_catalog_id=PROJECT,project_id='a'*32,manifest_sha256=OTHER,
                reference_id='measurements',path='measurements.json',measured_sha256=self.table.sha256),
            actor_id='d'*32,imported_at='2026-10-23T00:00:00+00:00')
        self.args=dict(binding=BINDING,checkpoint=CHECKPOINT,origin_catalog_id=PROJECT,packet_sha256=self.table.sha256)

    def sdk(self,value):
        return ProjectFilesClient(client({'status':200,'result':dict(binding=BINDING,project_id=PROJECT,
            checkpoint=CHECKPOINT,value=value)}))

    def test_comparison_capacity_is_versioned_without_changing_packet_headers(self):
        from retained_measurements import MAX_COMPARISON_ROWS,MAX_ROWS
        self.assertEqual(api.measurement_comparison_row_limit(1),100000)
        self.assertEqual(api.measurement_comparison_row_limit(2),250000)
        self.assertEqual(api.measurement_comparison_row_limit(2),MAX_COMPARISON_ROWS)
        self.assertEqual(MAX_ROWS,100000)
        self.assertEqual(api._MEASUREMENT_HEADER['properties']['observation_count']['maximum'],100000)
        self.assertNotEqual(api.contract('project_files.measurement_compare',1)['sha256'],
                            api.contract('project_files.measurement_compare',2)['sha256'])

    def test_group_comparison_header_and_query_correlate_every_original_source(self):
        locator=dict(origin_catalog_id=PROJECT,packet_sha256=self.table.sha256)
        comparison=MeasurementComparison([(locator,self.table)])
        args=dict(binding=BINDING,checkpoint=CHECKPOINT,sources=[locator])
        page=dict(sources=[self.source],value=comparison.read())
        self.assertEqual(self.sdk(page).measurement_compare(**args)['value'],page)
        query=dict(sources=[self.source],value=comparison.read('error',offset=1,limit=1))
        request=dict(args,metric_id='error',offset=1,limit=1)
        self.assertEqual(self.sdk(query).measurement_compare(**request)['value'],query)
        for mutate in (lambda p:p['sources'][0].update(id=OTHER),
                       lambda p:p['value']['query'].update(offset=0),
                       lambda p:p['value']['query']['summary'][0]['states'].update(measured=99),
                       lambda p:p['value']['query']['rows'][0]['source'].update(packet_sha256=OTHER),
                       lambda p:p['value']['subjects'][0]['source'].update(origin_catalog_id='f'*32)):
            bad=copy.deepcopy(query);mutate(bad)
            with self.assertRaises(api.AgentAPIError):self.sdk(bad).measurement_compare(**request)

    def test_capability_bound_applies_to_the_actual_advertised_profile(self):
        sizes={profile:len(api.capabilities(PROJECT,profile=profile)['operations']) for profile in ('catalog','project')}
        maximum=max(sizes.values())
        with patch.object(api,'MAX_OPERATIONS',maximum):
            for profile in sizes:
                manifest=api.capabilities(PROJECT,profile=profile)
                self.assertLess(len(api.encoded(manifest)),api.CAPABILITIES_LIMIT)
                self.assertEqual(len(manifest['operations']),sizes[profile])
        with patch.object(api,'MAX_OPERATIONS',maximum-1),self.assertRaises(api.AgentAPIError) as caught:
            api.capabilities(PROJECT,profile=max(sizes,key=sizes.get))
        self.assertEqual(caught.exception.code,'registry_invalid')

    def test_typed_read_routes_pin_packet_selection_and_never_accept_execution(self):
        arguments=dict(self.args,metric_id='error',filters={'cpm':16},subject_ids=['a'],limit=2)
        method,path,body=api.project_request('project_files.measurement_query',arguments)
        self.assertEqual(method,'POST')
        self.assertEqual(body['filters'],{'cpm':16})
        self.assertIn(self.table.sha256,path)
        self.assertFalse(api.operation('project_files.measurement_query')['side_effects'])
        for change in ({'script':'never.py'},{'execute':True},{'packet_sha256':'not-a-hash'},{'limit':101}):
            with self.subTest(change=change),self.assertRaises(api.AgentAPIError):
                api.validate_arguments('project_files.measurement_query',dict(arguments,**change))
        for missing in ('origin_catalog_id','packet_sha256','binding','checkpoint','metric_id'):
            with self.subTest(missing=missing),self.assertRaises(api.AgentAPIError):
                api.validate_arguments('project_files.measurement_query',{k:v for k,v in arguments.items() if k!=missing})

    def test_exact_query_and_inspection_reply_is_accepted_and_changed_selection_refused(self):
        query=self.table.query('error',subject_ids=['a'],filters={'cpm':16},limit=2)
        value=dict(source=self.source,value=query)
        args=dict(self.args,metric_id='error',subject_ids=['a'],filters={'cpm':16},limit=2)
        self.assertEqual(self.sdk(value).measurement_query(**args)['value'],value)
        for key,replacement in (('packet_sha256',OTHER),('filters',{}),('offset',1),('subject_ids',['b'])):
            changed=copy.deepcopy(value);changed['value'][key]=replacement
            with self.subTest(key=key),self.assertRaises(api.AgentAPIError):
                self.sdk(changed).measurement_query(**args)
        changed=copy.deepcopy(value);changed['source']['origin_catalog_id']='f'*32
        with self.assertRaises(api.AgentAPIError):self.sdk(changed).measurement_query(**args)
        row=dict(source=self.source,value=self.table.inspect('a-case1-error'))
        self.assertEqual(self.sdk(row).measurement_inspect(**self.args,observation_id='a-case1-error')['value'],row)
        with self.assertRaises(api.AgentAPIError):
            self.sdk(row).measurement_inspect(**self.args,observation_id='a-case2-error')

    def test_header_subject_and_source_pages_and_import_keep_exact_identity(self):
        header=dict(source=self.source,value=self.table.metadata())
        self.assertEqual(self.sdk(header).measurement_metadata(**self.args)['value'],header)
        header['value']['title']='Different retained title'
        with self.assertRaises(api.AgentAPIError):self.sdk(header).measurement_metadata(**self.args)
        subjects=dict(source=self.source,value=self.table.subjects(offset=1,limit=1))
        self.assertEqual(self.sdk(subjects).measurement_subjects(**self.args,offset=1,limit=1)['value'],subjects)
        with self.assertRaises(api.AgentAPIError):self.sdk(subjects).measurement_subjects(**self.args,offset=0,limit=1)
        availability=dict(state='unverified',expected_sha256=self.table.sha256,expected_bytes=self.source['blob']['bytes'],
            observed_sha256=None,observed_bytes=self.source['blob']['bytes'])
        page=dict(items=[dict(self.source,availability=availability)],offset=0,limit=40,total=1)
        self.assertEqual(self.sdk(page).measurement_sources(binding=BINDING,checkpoint=CHECKPOINT)['value'],page)
        request=dict(bound(),snapshot={k:self.source['source'][k] for k in ('origin_catalog_id','project_id','manifest_sha256')},
            reference_id='measurements',expected_sha256=self.table.sha256)
        self.assertEqual(self.sdk(self.source).measurement_import(**request)['value'],self.source)
        with self.assertRaises(api.AgentAPIError):
            self.sdk(dict(self.source,id=OTHER)).measurement_import(**request)


if __name__=='__main__':unittest.main()
