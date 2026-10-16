"""Execute restored-only B disable/removal after actual public grant refusal.

The rootless E4 report stays immutable and explicitly pending. This separate
witness proves only its restored selection phase, leaving classifier, native
browser and supported-client results to their own receipts.
"""
import argparse
import hashlib
import os
from pathlib import Path
from unittest.mock import patch

from psycopg.conninfo import make_conninfo

from app import Dataset
from auth_helpers import ExplicitOwnerFixture
import backup_metadata as transfer
import qualify_extension_ab_retention as retention
from qualify_extension_restored_classifier import read_report
from qualify_scientific_restore import compare,read_private,save_private,snapshot


def main(args):
    report,destination,database,report_sha=read_report(args.retention_report)
    retention.require(report_sha==args.retention_report_sha256,'Reviewed restore report differs.')
    selected=retention.load_selection(args.selection)
    retention.require(transfer.file_hash(args.selection)==report['selection_sha256'],'Qualified selection differs.')
    control=retention.reviewed({'path':str(args.cross_grant_report.resolve()),'sha256':args.cross_grant_report_sha256})
    retention.require(control.get('format')=='extension_ab_public_cross_material_refusal_v1' and
        control.get('state')=='refused_without_execution' and control.get('admission_request_state')=='refused_403' and
        control.get('approval_unconsumed') is True and control.get('roots_removed_and_historical_reads_verified') is True and
        control['historical_materials']=={label:selected[label]['material']['ref'] for label in ('a','b')},
        'Require the actual same-actor unspent A-grant/B-material public refusal.')
    source_proof=retention.evidence.decode(retention.regular(args.cross_grant_report.parent/'source-unchanged.json',65536))
    retention.require(source_proof.get('state')=='passed' and source_proof.get('source_unchanged') is True and
        source_proof['retention_report_sha256']==report_sha and source_proof['selection_sha256']==report['selection_sha256'],
        'Cross-grant source bookend differs.')
    output=Path(report['output']);witness=output/'disabled-selection.json'
    retention.require(not witness.exists() and not (output/'restored-only-b-source').exists(),
                      'Preserve any earlier restored selection attempt; never overwrite it.')
    connection=os.environ['TULDOK_DATABASE_URL'];restored_connection=make_conninfo(connection,dbname=database)
    baseline=read_private(output/'baseline.private.json')
    compare(snapshot(Path(report['source']),connection),baseline)
    original_projects=retention.project_rows(destination,restored_connection)
    dataset=None
    try:
        with patch('subprocess.Popen',side_effect=AssertionError('Retained reads must not execute')),\
                patch('runs.Runs._start',side_effect=AssertionError('Retained reads must not schedule')):
            dataset=Dataset(destination,dsn=restored_connection,project_roots={})
            owner=ExplicitOwnerFixture.bootstrap(dataset)
            with owner.bound(dataset):expected=retention.selected_reads(dataset,selected)
            dataset.close();dataset=None
            refusals=retention.disabled_b_copy(destination,restored_connection,selected,output,expected)
            current=retention.project_rows(destination,restored_connection)
            retention.check_project_rows(original_projects,current,{row['project_id'] for row in refusals})
            dataset=Dataset(destination,dsn=restored_connection,project_roots={})
            owner=ExplicitOwnerFixture.bootstrap(dataset)
            with owner.bound(dataset):
                retention.require(retention.selected_reads(dataset,selected)==expected,
                                  'Historical A/B source/package identity changed after B disable/removal.')
                dataset.access.logout()
    finally:
        if dataset is not None:dataset.close()
    compare(snapshot(Path(report['source']),connection),baseline)
    save_private(witness,{'format':'extension_ab_restored_disable_refusal_v1','state':'passed',
        'retention_report_sha256':report_sha,'selection_sha256':report['selection_sha256'],
        'cross_grant_report_sha256':args.cross_grant_report_sha256,
        'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'restored_catalog_path':str(destination),'restored_database':database,
        'new_selection_refusals':refusals,'original_project_rows_unchanged':True,
        'historical_A_B_package_unchanged':True,'source_unchanged':True,'process_and_scheduler_blocked':True,
        'scope':'Actual restored-only disabled/removed B selections; classifier/native/interfaces are separate gates.'})
    print('PASS restored-only B disable/removal '+str(witness),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('retention-report','selection','cross-grant-report'):parser.add_argument('--'+name,type=Path,required=True)
    for name in ('retention-report-sha256','cross-grant-report-sha256'):parser.add_argument('--'+name,required=True)
    main(parser.parse_args())
