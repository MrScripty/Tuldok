"""Pure driver contract fixtures only; no actual Run or retention acceptance.

The optional receipt-only test consumes a separately reviewed successful actual
selection. No test invokes backup, restore, admission, replay or a live catalog.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import qualify_extension_ab_retention as driver


class ABRetentionDriverTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name);self.catalog='1'*32
        self.selection={'format':'extension_ab_retention_selection_v1','catalog_id':self.catalog,
                        'a':{},'b':{},'unrelated_completed_run_ids':[]}
        self.docs={}
        for label,prefix in [('a',2),('b',6)]:
            run_id=str(prefix)*32;study_id=str(prefix+1)*32;trial_id=str(prefix+2)*32
            expected={key:character*64 for key,character in [('material_sha256','a'),('model_sha256','b'),
                ('task_sha256','c'),('profile_definition_sha256','d'),('runtime_sha256','e')]}
            expected.update(graph_id='f'*32,graph_revision=1)
            selection={'format':'extension_sdk_conformance_selection_v1','catalog_id':self.catalog,
                'study_id':study_id,'trial_id':trial_id,'actor_id':'a'*32,'approval_id':'b'*32,'request_key':'contract-fixture-only','expected':expected}
            run={'id':run_id,'state':'completed','custody_phase':'drained','study_membership':{'study_id':study_id,'trial_id':trial_id},
                 'actor_id':'a'*32,'approval_id':'b'*32,'request_key':driver.source_run_key(selection),'approval_material_sha256':'a'*64,'artifacts':[{'name':'execution-context.json','bytes':100,'sha256':'f'*64}]}
            model={'ref':{'sha256':'b'*64},'material':{'task':{'sha256':'c'*64}}}
            material={'ref':{'sha256':'a'*64},'material':{'evaluation_profile':{'sha256':'d'*64},'runtime':{'sha256':'e'*64},
                'recipe_id':'f'*32,'recipe_revision':1}}
            source={'run_id':run_id,'charged':{'attempt_slots':1}}
            if label=='a':source.update(state='canonical_sdk_source_numerical_cold_passed',sdk={'state':'passed'},model=copy.deepcopy(model['ref']),material=copy.deepcopy(material['ref']))
            else:source.update(format='extension_author_operator_qualification_v1',state='passed',selection=selection,
                artifacts=run['artifacts'],custody_context={'sha256':'f'*64})
            docs={'source':source,'selection':selection,'model':model,'material':material,'run':run}
            if label=='a':
                package_run={'id':'4'*32,'state':'completed','custody_phase':'drained',
                    'artifacts':[{'name':'package.zip','bytes':200,'sha256':'7'*64}]}
                verifier_run={'id':'5'*32,'state':'completed','custody_phase':'drained',
                    'artifacts':[{'name':'verification.json','bytes':300,'sha256':'8'*64}]}
                docs.update(package_run=package_run,verifier_run=verifier_run,package={
                    'format':'p5_field_charged_qualification_v1','source_run_id':run_id,'study_id':study_id,
                    'runtime_snapshot':{'catalog_id':self.catalog},'package_run_id':'4'*32,'verifier_run_id':'5'*32,
                    'package_sha256':'7'*64,'fresh_verification':{'verified':True},'charged':{'attempt_slots':3}})
            self.docs[label]=docs
        self.path=self.root/'selection.json';self.write()

    def write(self):
        for label,docs in self.docs.items():
            for name,value in docs.items():
                path=self.root/(label+'-'+name+'.json');raw=json.dumps(value).encode();path.write_bytes(raw)
                self.selection[label][name]={'path':str(path),'sha256':hashlib.sha256(raw).hexdigest()}
        self.path.write_text(json.dumps(self.selection))

    def test_known_receipt_formats_bind_four_ids_without_global_three_run_assumption(self):
        self.selection['unrelated_completed_run_ids']=['9'*32];self.write()
        selected=driver.load_selection(self.path)
        self.assertEqual(len(selected['run_ids']),4)
        driver.check_run_set({'dataset_id':self.catalog,'run_states':{identity:'completed' for identity in selected['all_run_ids']}},selected)
        for invalid in ({identity:'completed' for identity in selected['run_ids']},
                        dict.fromkeys(selected['all_run_ids']+['a'*32],'completed'),
                        dict.fromkeys(selected['all_run_ids'],'unknown')):
            with self.subTest(states=invalid),self.assertRaises(RuntimeError):
                driver.check_run_set({'dataset_id':self.catalog,'run_states':invalid},selected)

    def test_sdk_and_internal_study_run_keys_are_separate_exact_identities(self):
        self.assertNotEqual(self.docs['b']['run']['request_key'],self.docs['b']['selection']['request_key'])
        driver.load_selection(self.path)
        self.docs['b']['run']['request_key']=self.docs['b']['selection']['request_key'];self.write()
        with self.assertRaisesRegex(RuntimeError,'selection/Run/Study'):driver.load_selection(self.path)

    def test_failed_A01_or_uncompleted_receipts_cannot_enter_selection(self):
        self.docs['a']['source']['state']='failed';self.write()
        with self.assertRaisesRegex(RuntimeError,'successful actual canonical'):driver.load_selection(self.path)
        self.docs['a']['source']['state']='canonical_sdk_source_numerical_cold_passed'
        self.docs['b']['run']['state']='running';self.write()
        with self.assertRaisesRegex(RuntimeError,'completed/drained'):driver.load_selection(self.path)

    def test_current_review_hash_and_known_HTTP_wrapper_are_exact(self):
        path=Path(self.selection['b']['model']['path']);path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaisesRegex(RuntimeError,'identity changed'):driver.load_selection(self.path)
        self.write();self.docs['b']['model']={'status':200,'result':self.docs['b']['model']};self.write()
        self.assertEqual(driver.load_selection(self.path)['b']['model']['ref']['sha256'],'b'*64)
        self.docs['b']['model']['operation']='models.publish';self.write()
        self.assertEqual(driver.load_selection(self.path)['b']['model']['ref']['sha256'],'b'*64)
        self.docs['b']['model']['operation']='studies.admit';self.write()
        with self.assertRaisesRegex(RuntimeError,'operation differs'):driver.load_selection(self.path)
        self.docs['b']['model']['operation']='models.material'
        self.docs['b']['model']['status']=True;self.write()
        with self.assertRaisesRegex(RuntimeError,'not successful'):driver.load_selection(self.path)

    def test_cross_task_model_profile_context_and_package_ids_cannot_drift(self):
        for label,name,key in [('b','model','ref'),('a','material','ref')]:
            original=copy.deepcopy(self.docs[label][name]);self.docs[label][name][key]['sha256']='0'*64;self.write()
            with self.subTest(label=label),self.assertRaises(RuntimeError):driver.load_selection(self.path)
            self.docs[label][name]=original
        self.docs['b']['source']['custody_context']['sha256']='0'*64;self.write()
        with self.assertRaisesRegex(RuntimeError,'context receipt'):driver.load_selection(self.path)
        self.docs['b']['source']['custody_context']['sha256']='f'*64
        self.docs['a']['package']['package_run_id']='0'*32;self.write()
        with self.assertRaisesRegex(RuntimeError,'linkage'):driver.load_selection(self.path)

    def test_duplicate_or_implicit_unrelated_runs_refuse(self):
        self.selection['unrelated_completed_run_ids']=['2'*32];self.write()
        with self.assertRaisesRegex(RuntimeError,'unrelated completed'):driver.load_selection(self.path)
        self.selection['unrelated_completed_run_ids']=['9'*32,'9'*32];self.write()
        with self.assertRaises(RuntimeError):driver.load_selection(self.path)
        self.selection['unrelated_completed_run_ids']=[]
        self.docs['b']['run']['id']=self.docs['a']['run']['id'];self.docs['b']['source']['run_id']=self.docs['a']['run']['id'];self.write()
        with self.assertRaisesRegex(RuntimeError,'Four distinct'):driver.load_selection(self.path)

    def test_per_study_charges_require_only_exact_settled_reservations(self):
        charged={'attempt_slots':3,'admitted_wall_seconds':60,'retained_bytes':1000,'peak_staging_bytes':2000}
        state={'charged':charged,'reservations':[{'run_id':identity,'state':'settled'} for identity in ('a','b','c')]}
        driver.check_study(state,['a','b','c'],charged)
        for mutate in (lambda v:v['reservations'].append({'run_id':'other','state':'settled'}),
                       lambda v:v['reservations'][0].update(state='active'),
                       lambda v:v['charged'].update(retained_bytes=999)):
            invalid=copy.deepcopy(state);mutate(invalid)
            with self.assertRaises(RuntimeError):driver.check_study(invalid,['a','b','c'],charged)

    def test_artifact_inventory_rejects_duplicates_bool_bytes_and_escaping_paths(self):
        run=copy.deepcopy(self.docs['b']['run'])
        for mutate in (lambda v:v['artifacts'].append(copy.deepcopy(v['artifacts'][0])),
                       lambda v:v['artifacts'][0].update(bytes=True),
                       lambda v:v['artifacts'][0].update(name='../outside')):
            invalid=copy.deepcopy(run);mutate(invalid)
            with self.assertRaises(RuntimeError):driver.artifact_index(invalid)

    def test_disabled_snapshots_add_only_two_rows_and_preserve_every_original_row(self):
        original={'historical':'exact original bytes'}
        current=dict(original,disabled='new selection',removed='new selection')
        driver.check_project_rows(original,current,{'disabled','removed'})
        for invalid in (dict(current,historical='changed bytes'),dict(current,unreviewed='extra'),
                        {key:value for key,value in current.items() if key!='historical'}):
            with self.assertRaises(RuntimeError):driver.check_project_rows(original,invalid,{'disabled','removed'})

    def recovery_fixture(self):
        """Data-only contract stand-ins; these are never actual Run evidence."""
        def linked(name,value):
            raw=value if type(value) is bytes else json.dumps(value).encode()
            path=self.root/('recovery-'+name);path.write_bytes(raw)
            return {'path':str(path),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
        source=copy.deepcopy(self.docs['b']['source']);selection=source['selection'];counts={'workspace_runs':2}
        prepared=linked('prepared.json',{'selection':selection,'reviewed_inventory_sha256':'0'*64})
        failure=linked('failure.json',{'state':'failed'});stderr=linked('stderr.txt',b'missing held sibling')
        source.update(mode='completed_run_verification_only',cold_whole_downloads_verified=True,
            domain_counts_before=counts,domain_counts_after=counts,oracle={'state':'valid'},
            recovery={'original_prepared_sha256':prepared['sha256'],'initial_review_sha256':'0'*64,
                'oracle_dependencies':{name:'a'*64 for name in ('cold_oracle.py','fixture.json','oracle-freeze.json')},
                'preserved_original_evidence':{'failure.json':failure['sha256'],'oracle-diagnostic-stderr.txt':stderr['sha256']}})
        sdk=linked('sdk.json',{'format':'extension_sdk_conformance_v1','state':'passed','run_id':source['run_id'],
            **{key:selection[key] for key in ('study_id','trial_id','request_key')},'material_sha256':selection['expected']['material_sha256'],
            'operations':['studies.admit'],'artifacts':source['artifacts']})
        settlement=linked('settlement.json',{'state':'passed','no_admission_or_sdk':True,'additional_charge':False,
            'action':'one_existing_completed_run_accounting_reconciliation','run_id':source['run_id'],'study_id':selection['study_id'],
            'before':{'counts':counts,'study':{'charged':source['charged']}},'after':{'counts':counts,'study':{'charged':source['charged']}}})
        summary={'format':'extension_author_existing_run_recovery_v1','state':'passed','no_admission_or_sdk_retry':True,
            'source_sdk_admissions':1,'all_sdk_current_and_cold_whole_hashes_verified':True,'domain_counts_before':counts,'domain_counts_after':counts,
            'successful_verification':linked('final.json',source),'source_prepared':prepared,'source_sdk':sdk,'settlement':settlement,
            'original_failure':failure,'original_diagnostic_stderr':stderr,'first_recovery_failure':linked('first.json',{'state':'failed'}),
            'first_recovery_diagnostic':linked('diagnostic.json',{'diagnostic':'original omitted dependency'}),
            'run_id':source['run_id'],'catalog_id':self.catalog,'study_id':selection['study_id'],'trial_id':selection['trial_id'],
            'artifact_count':len(source['artifacts']),'charged':source['charged'],'oracle':source['oracle']}
        return summary,source,linked('summary.json',summary)

    def test_recovered_B_accepts_summary_or_explicit_summary_link_and_preserves_evidence(self):
        summary,source,ref=self.recovery_fixture()
        self.assertEqual(driver.recovered_b(summary),source)
        self.selection['b']['source']={key:ref[key] for key in ('path','sha256')};self.path.write_text(json.dumps(self.selection))
        self.assertEqual(driver.load_selection(self.path)['b']['source'],source)
        self.selection['b']['source']={key:summary['successful_verification'][key] for key in ('path','sha256')}
        self.selection['b']['recovery_summary']={key:ref[key] for key in ('path','sha256')};self.path.write_text(json.dumps(self.selection))
        self.assertEqual(driver.load_selection(self.path)['b']['source'],source)
        self.selection['b'].pop('recovery_summary');self.path.write_text(json.dumps(self.selection))
        with self.assertRaisesRegex(RuntimeError,'explicit linked recovery'):driver.load_selection(self.path)

    def test_recovered_B_rejects_retry_changed_original_docs_or_failed_settlement(self):
        summary,source,_=self.recovery_fixture()
        for mutate in (lambda v:v.update(source_sdk_admissions=True),lambda v:v.update(no_admission_or_sdk_retry=False),
                       lambda v:v.update(artifact_count=999),lambda v:v['charged'].update(attempt_slots=2)):
            invalid=copy.deepcopy(summary);mutate(invalid)
            with self.assertRaises(RuntimeError):driver.recovered_b(invalid)
        Path(summary['source_prepared']['path']).write_bytes(b'changed')
        with self.assertRaisesRegex(RuntimeError,'selected regular file|identity changed'):driver.recovered_b(summary)

    def test_exact_current_roots_are_data_only_and_bounded(self):
        path=self.root/'roots.json';raw=json.dumps({'extension-a':'/reviewed/a','author-b':'/reviewed/b'}).encode();path.write_bytes(raw)
        self.selection['current_roots']={'path':str(path),'sha256':hashlib.sha256(raw).hexdigest()};self.path.write_text(json.dumps(self.selection))
        self.assertEqual(driver.load_selection(self.path)['current_roots']['author-b'],'/reviewed/b')
        raw=json.dumps({'author-b':'relative/root'}).encode();path.write_bytes(raw)
        self.selection['current_roots']['sha256']=hashlib.sha256(raw).hexdigest();self.path.write_text(json.dumps(self.selection))
        with self.assertRaisesRegex(RuntimeError,'bounded current root map'):driver.load_selection(self.path)

    @unittest.skipUnless(os.environ.get('TULDOK_AB_B_RECOVERY_SUMMARY'),'Requires separately reviewed actual B recovery summary')
    def test_actual_B_recovery_links_load_read_only(self):
        summary=json.loads(Path(os.environ['TULDOK_AB_B_RECOVERY_SUMMARY']).read_bytes())
        with patch('app.Dataset',side_effect=AssertionError('Receipt-only validation must not open a catalog')):
            source=driver.recovered_b(summary)
        self.assertEqual(source['run_id'],summary['run_id']);self.assertEqual(len(source['artifacts']),summary['artifact_count'])

    def test_no_explicit_quiescence_cannot_read_selection_or_create_output(self):
        output=self.root/'absent-output';args=SimpleNamespace(quiesced=False,output=output)
        with patch.object(driver,'load_selection',side_effect=AssertionError('No selection read')),self.assertRaisesRegex(RuntimeError,'quiesced'):
            driver.main(args)
        self.assertFalse(output.exists())

    @unittest.skipUnless(os.environ.get('TULDOK_AB_RETENTION_SELECTION'),'Requires separately reviewed completed A/B receipt selection')
    def test_actual_reviewed_receipts_load_without_catalog_mutation(self):
        selected=driver.load_selection(Path(os.environ['TULDOK_AB_RETENTION_SELECTION']))
        self.assertEqual(len(selected['run_ids']),4)
