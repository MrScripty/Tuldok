"""Exact retained-source assembly; native history remains the proof oracle."""
import copy
import hashlib
import unittest
from unittest.mock import patch

from project_composition import ProjectCompositionError, merge_retained_sources
from project_history import capture_run, declarations, decode_records
from project_store import _encode
from test_project_history import ORIGIN, legacy_run


def snapshot(identity, records):
    return dict(project_id=identity*32, name='Source '+identity, checkpoint=identity*64, records=records)


def approved_history():
    run=legacy_run();run['approval_id']='9'*32
    grant=dict(id=run['approval_id'],catalog_id=ORIGIN,approver_actor_id='a'*32,approver_credential_id='b'*32,
               consumer_actor_id='5'*32,material_sha256='f'*64,created_at=1,expires_at=100,revoked_at=None)
    consumption=dict(grant_id=grant['id'],run_id=run['id'],admission_id=run['admission_id'],
                     consumer_credential_id='6'*32,request_sha256=run['request_sha256'],consumed_at=2)
    effects={'pipeline.inspect_release':[run['release_id']],'dataset_releases.locate':[run['release_id']],
             'pipeline.probe':['image_classification'],'pipeline.probe_native':['image_classification'],
             'pipeline.definition_identity':['image_classification'],'pipeline.exposures':[None],'runs.update':[run['id']]}
    admission=dict(id=run['admission_id'],catalog_id=ORIGIN,actor_id='5'*32,credential_id='6'*32,
                   kind='runs',job_id=run['id'],request_digest=run['request_sha256'],effects=effects,created_at=1)
    record=capture_run(run,admission_proof=dict(grant=grant,consumption=consumption,admission=admission),payloads=[])
    records=[record,*declarations(record)]
    decode_records(records)
    return records


class RetainedCompositionTests(unittest.TestCase):
    def test_exact_duplicate_is_shared_and_each_source_membership_is_retained(self):
        records=approved_history();left=snapshot('1',records);right=snapshot('2',copy.deepcopy(records))
        result=merge_retained_sources([left,right])
        self.assertEqual(result['records'],sorted(records,key=lambda item:(item['family'],item['id'])))
        self.assertEqual(len(result['sources']),2)
        for source in result['sources']:
            for record in records:
                expected=hashlib.sha256(_encode(record)).hexdigest()
                self.assertEqual(source['records'][record['family']][record['id']],expected)
            self.assertEqual(source['run_observations'],{})

    def test_alternate_grant_is_exact_native_observation_without_duplicate_run(self):
        original=approved_history();alternate=copy.deepcopy(original)
        alternate[0]['document']['admission_proof']['grant']['revoked_at']=3
        alternate[0]['document']['admission_proof']['consumption']['consumed_at']=3
        decode_records(alternate)
        with patch('os.open',side_effect=AssertionError('Pure construction has no filesystem access')):
            result=merge_retained_sources([snapshot('1',original),snapshot('2',alternate),snapshot('3',copy.deepcopy(alternate))])
        facts=decode_records(result['records'])
        self.assertEqual(len(facts.runs),1)
        self.assertEqual(len(facts.observations),1)
        base=next(r for r in result['records'] if r['family']=='run_history')
        observation=next(r for r in result['records'] if r['family']=='run_observation')
        self.assertEqual(_encode(base),_encode(original[0]))
        self.assertEqual(_encode(observation['document']['observation']),_encode(alternate[0]['document']))
        expected=hashlib.sha256(_encode(alternate[0]['document'])).hexdigest()
        self.assertEqual(observation['id'],expected)
        for source in result['sources'][1:]:
            self.assertEqual(source['run_observations'],{original[0]['id']:expected})
        self.assertFalse(result['sources'][0]['run_observations'])

    def test_broader_run_conflicts_are_rejected_at_the_named_conflict_boundary(self):
        original=approved_history()
        for field in ('metrics','population','admission'):
            alternate=copy.deepcopy(original)
            if field=='metrics':alternate[0]['document']['run']['metrics']={'accuracy':0.5}
            elif field=='population':alternate[0]['document']['payloads'][0]['population']='test'
            else:alternate[0]['document']['admission_proof']['admission']['created_at']=2
            decode_records(alternate)
            with self.subTest(field=field),self.assertRaises(ProjectCompositionError) as caught:
                merge_retained_sources([snapshot('1',original),snapshot('2',alternate)])
            self.assertEqual(caught.exception.code,'conflict')
            self.assertIn('run_history/'+original[0]['id'],str(caught.exception))

    def test_equal_python_numbers_do_not_hide_different_canonical_bytes(self):
        original=approved_history();original[0]['document']['run']['parameters']={'scale':1}
        alternate=copy.deepcopy(original);alternate[0]['document']['run']['parameters']['scale']=1.0
        self.assertEqual(original,alternate)
        decode_records(original);decode_records(alternate)
        with self.assertRaises(ProjectCompositionError) as caught:
            merge_retained_sources([snapshot('1',original),snapshot('2',alternate)])
        self.assertEqual(caught.exception.code,'conflict')

    def test_other_family_conflict_and_repeated_source_project_are_rejected(self):
        original=approved_history();alternate=copy.deepcopy(original)
        alternate[1]['document']['bytes']+=1
        with self.assertRaises(ProjectCompositionError) as caught:
            merge_retained_sources([snapshot('1',original),snapshot('2',alternate)])
        self.assertEqual(caught.exception.code,'conflict')
        self.assertIn('project_artifact/',str(caught.exception))
        with self.assertRaises(ProjectCompositionError) as repeated:
            merge_retained_sources([snapshot('1',original),snapshot('1',original)])
        self.assertEqual(repeated.exception.code,'conflict')
        self.assertIn('source project identity repeats',str(repeated.exception))

    def test_source_snapshots_can_be_loaded_lazily(self):
        records=approved_history()
        def sources():
            yield snapshot('1',records)
            yield snapshot('2',copy.deepcopy(records))
        self.assertEqual(len(merge_retained_sources(sources())['sources']),2)
        with self.assertRaises(ProjectCompositionError) as caught:
            merge_retained_sources(iter([snapshot('1',records)]))
        self.assertEqual(caught.exception.code,'invalid')
        self.assertIn('at least two',str(caught.exception))

    def test_output_owns_its_documents_and_does_not_mutate_sources(self):
        original=approved_history();before=copy.deepcopy(original)
        result=merge_retained_sources([snapshot('1',original),snapshot('2',copy.deepcopy(original))])
        result['records'][0]['document']['bytes']=123
        self.assertEqual(original,before)
        original[0]['document']['run']['metrics']={'accuracy':0.25}
        retained=next(r for r in result['records'] if r['family']=='run_history')
        self.assertIsNone(retained['document']['run']['metrics'])


if __name__=='__main__':unittest.main()
