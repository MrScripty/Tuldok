import contextlib, hashlib, io, json, os, pathlib, subprocess, sys, time, unittest
import psycopg
from psycopg.conninfo import make_conninfo

repo = pathlib.Path('/workspace/Tuldok-study-restore-independent-20261021')
out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=False, mode=0o700)
container = json.loads(subprocess.check_output(['docker', 'inspect', 'tuldok-qa-20261020']))[0]
env = dict(item.split('=', 1) for item in container['Config']['Env'] if '=' in item)
dsn = make_conninfo(host='127.0.0.1', port=55432, user=env.get('POSTGRES_USER', 'postgres'),
                   dbname=env.get('POSTGRES_DB', 'postgres'), password=env['POSTGRES_PASSWORD'])
os.environ['TULDOK_DATABASE_URL'] = dsn
os.environ['TULDOK_STUDY_RESTORE_ACCEPTANCE_REPORT'] = str(out/'domain.json')
os.chdir(repo); sys.path[:0] = [str(repo/'tests'), str(repo)]
def git(*args): return subprocess.check_output(['git', *args]).decode().strip()
def resources():
    with psycopg.connect(dsn, autocommit=True) as db:
        return {'schemas': [r[0] for r in db.execute("SELECT nspname FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' AND nspname NOT IN ('public','information_schema') ORDER BY nspname")],
                'databases': [r[0] for r in db.execute('SELECT datname FROM pg_database ORDER BY datname')]}
before = resources(); assert not before['schemas'], before
source = {'head': git('rev-parse','HEAD'), 'tree': git('rev-parse','HEAD^{tree}'),
          'status': git('status','--porcelain=v1'), 'test_sha256': hashlib.sha256((repo/'tests/test_run_publication_recovery.py').read_bytes()).hexdigest()}
assert not source['status'], source
with (out/'unittest.log').open('x') as log:
    start = time.perf_counter()
    with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        suite = unittest.defaultTestLoader.loadTestsFromName('test_run_publication_recovery.PublicationRecoveryTests.test_existing_study_reservation_and_conservative_charge_survive_recovery')
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    elapsed = time.perf_counter()-start
after = resources()
receipt = {'format':'independent_study_restore_qualification_v1', 'source':source,
    'seconds':elapsed, 'tests_run':result.testsRun, 'failures':len(result.failures),
    'errors':len(result.errors), 'skips':len(result.skipped), 'successful':result.wasSuccessful(),
    'resources_before':before, 'resources_after':after, 'final_status':git('status','--porcelain=v1'),
    'log_sha256':hashlib.sha256((out/'unittest.log').read_bytes()).hexdigest()}
if (out/'domain.json').exists():
    domain = json.loads((out/'domain.json').read_text())
    assert len(domain['table_summaries']) == 43
    assert domain['counts_before'] == domain['counts_after'] == dict(workspace_runs=1, access_execution_grants=1, access_execution_consumptions=1, model_attempt_reservations=1)
    assert domain['charged_before'] == domain['charged_after'] == domain['original_envelope']
    assert domain['actual_attempt_launch_calls'] == 1 and domain['restore_and_consumer_replay_calls'] == 0
    with psycopg.connect(dsn, autocommit=True) as db:
        absent = {'source_schema': db.execute('SELECT 1 FROM pg_namespace WHERE nspname=%s', (domain['cleanup']['source_schema_removed'],)).fetchone() is None,
                  'restored_database': db.execute('SELECT 1 FROM pg_database WHERE datname=%s', (domain['cleanup']['restored_database_removed'],)).fetchone() is None}
    assert all(absent.values()), absent
    receipt['independent_exact_cleanup_queries'] = absent
    receipt['domain_sha256'] = hashlib.sha256((out/'domain.json').read_bytes()).hexdigest()
(out/'result.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
assert before==after, receipt
assert not receipt['final_status'], receipt
raise SystemExit(0 if result.wasSuccessful() and result.testsRun==1 and not result.skipped else 1)
