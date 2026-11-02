"""Real native HTTP source import, atomic comparison and scalar inspection."""
import hashlib
import json
import os
import unittest
from unittest.mock import patch

import agent_api
from workbench import WorkbenchError

import test_project_files_http as m1
import test_project_files_m2_http as m2
from retained_measurements import encode
from test_measurement_comparison import partition


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires disposable PostgreSQL')
class ComparisonHTTP(unittest.TestCase):
    cleanup_owned=m1.ProjectFilesHTTP.cleanup_owned
    select_host=m1.ProjectFilesHTTP.select_host
    request=m1.ProjectFilesHTTP.request
    state=m1.ProjectFilesHTTP.state
    envelope=m1.ProjectFilesHTTP.envelope
    action=m1.ProjectFilesHTTP.action
    create=m1.ProjectFilesHTTP.create
    arguments=m2.ProjectFilesM2HTTP.arguments
    transport=m2.ProjectFilesM2HTTP.transport
    call=m2.ProjectFilesM2HTTP.call
    def setUp(self):
        self.operations=[]
        m1.ProjectFilesHTTP.setUp(self)

    def test_two_original_sources_compare_and_inspect_through_real_HTTP(self):
        self.create()
        sources=[]
        for subject, identity in [('a','b'*32),('b','c'*32)]:
            raw=encode(partition(subject));digest=hashlib.sha256(raw).hexdigest()
            filename=subject+'-measurements.json';manifest_name=subject+'-source.json'
            (self.external/filename).write_bytes(raw)
            manifest=dict(schema_version=1,id=identity,name='Original '+subject,
                data=[dict(id='scalars',label='Retained scalars',path=filename,sha256=digest)],
                recipes=[],evidence=[],requirements=[])
            (self.external/manifest_name).write_text(json.dumps(manifest))
            registered=self.call('source_register',root='fixture',manifest_path=manifest_name)
            snapshot={key:registered[key] for key in ('origin_catalog_id','project_id','manifest_sha256')}
            admitted=self.call('measurement_import',snapshot=snapshot,reference_id='scalars',expected_sha256=digest)
            sources.append(dict(origin_catalog_id=admitted['origin_catalog_id'],packet_sha256=digest))
        before=self.workspace._projection.session.snapshot
        metadata=self.call('measurement_compare',sources=sources)['value']
        self.assertEqual([s['id'] for s in metadata['subjects']],['a','b'])
        self.assertIsNone(metadata['query'])
        query=self.call('measurement_compare',sources=sources,metric_id='error',offset=1,limit=2)['value']['query']
        self.assertEqual(query['total'],4)
        self.assertEqual([s['maximum']['value'] for s in query['summary']],[2e-15,.02])
        self.assertEqual([r['subject_id'] for r in query['rows']],['a','b'])
        maximum=query['summary'][1]
        inspected=self.call('measurement_inspect',**maximum['source'],observation_id=maximum['maximum']['id'])['value']
        self.assertEqual(inspected['scalar_evidence']['value'],.02)
        self.assertEqual(inspected['case']['dimensions']['cpm'],8)
        missing=self.call('measurement_compare',sources=sources,metric_id='latency')['value']['query']
        self.assertTrue(all(s['maximum'] is None for s in missing['summary']))
        self.assertEqual(self.workspace._projection.session.snapshot,before)
        # Exercise version-specific admission at the real workspace/SQL owner
        # with small declared fixture budgets; no partial comparison escapes.
        arguments=self.arguments('measurement_compare',sources=sources)
        with self.owner.bound(self.workspace),patch.object(agent_api,'measurement_comparison_row_limit',
                side_effect=lambda version:7 if version==1 else 8):
            with self.assertRaises(WorkbenchError) as error:
                self.workspace.dispatch('project_files.measurement_compare',arguments,selected_version=1)
            self.assertEqual(error.exception.code,'too_large')
            value=self.workspace.dispatch('project_files.measurement_compare',arguments,selected_version=2)
            self.assertEqual(value['value']['value']['observation_count'],8)
        self.assertEqual(self.workspace._projection.session.snapshot,before)
