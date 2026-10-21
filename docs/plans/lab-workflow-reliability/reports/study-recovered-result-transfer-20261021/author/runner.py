import contextlib
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import unittest

import psycopg
from psycopg.conninfo import make_conninfo

REPO = Path('/workspace/Tuldok-study-restore-20261021')
EXPECTED = '55fe1c6e6c214f71b00d00ea3cdd80030a6751da'
OUT = Path(__file__).parent/'attempt01'
def git(*arguments):
    return subprocess.check_output(['git', *arguments], cwd=REPO, text=True).strip()
assert git('rev-parse', 'HEAD') == EXPECTED
assert not git('status', '--porcelain=v1')
OUT.mkdir(exist_ok=False, mode=0o700)
container = json.loads(subprocess.check_output(['docker', 'inspect', 'tuldok-qa-20261020']))[0]
assert container['State']['Running']
settings = dict(item.split('=', 1) for item in container['Config']['Env'] if '=' in item)
dsn = make_conninfo(host='127.0.0.1', port=55432,
    dbname=settings.get('POSTGRES_DB', 'postgres'), user=settings.get('POSTGRES_USER', 'postgres'),
    password=settings['POSTGRES_PASSWORD'])
os.environ['TULDOK_DATABASE_URL'] = dsn
os.environ['TULDOK_STUDY_RESTORE_ACCEPTANCE_REPORT'] = str(OUT/'domain.json')

def resources():
    with psycopg.connect(dsn, autocommit=True) as db:
        return {'schemas': [r[0] for r in db.execute("SELECT nspname FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' AND nspname NOT IN ('public','information_schema') ORDER BY nspname")],
            'databases': [r[0] for r in db.execute('SELECT datname FROM pg_database ORDER BY datname')],
            'server_version': db.execute('SHOW server_version').fetchone()[0]}

source = {'commit': git('rev-parse','HEAD'), 'tree': git('rev-parse','HEAD^{tree}'),
    'parents': git('show','-s','--format=%P','HEAD').split(), 'status': git('status','--porcelain=v1'),
    'test_sha256': hashlib.sha256((REPO/'tests/test_run_publication_recovery.py').read_bytes()).hexdigest()}
environment = {'python': platform.python_version(), 'platform': platform.platform(),
    'machine': platform.machine(), 'executable': sys.executable,
    'packages': {name: version(name) for name in ('psycopg','jsonschema','Pillow')},
    'container_image': container['Config']['Image'], 'container_image_id': container['Image']}
before = resources(); assert before['schemas'] == [], before
os.chdir(REPO); sys.path[:0] = [str(REPO/'tests'), str(REPO)]
case = 'test_run_publication_recovery.PublicationRecoveryTests.test_existing_study_reservation_and_conservative_charge_survive_recovery'
with (OUT/'unittest.log').open('x') as stream:
    start = time.perf_counter()
    with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
        suite = unittest.defaultTestLoader.loadTestsFromName(case)
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    seconds = time.perf_counter()-start
after = resources()
record = {'format':'study_publication_restore_focused_run_v1', 'case':case,
    'source':source, 'environment':environment, 'wrapper_seconds':seconds,
    'tests_run':result.testsRun, 'successful':result.wasSuccessful(),
    'failures':len(result.failures), 'errors':len(result.errors), 'skips':len(result.skipped),
    'resources_before':before, 'resources_after':after,
    'source_unchanged':git('rev-parse','HEAD')==EXPECTED and not git('status','--porcelain=v1'),
    'log_sha256':hashlib.sha256((OUT/'unittest.log').read_bytes()).hexdigest()}
if (OUT/'domain.json').exists():
    domain = json.loads((OUT/'domain.json').read_text())
    record['domain_sha256'] = hashlib.sha256((OUT/'domain.json').read_bytes()).hexdigest()
    names = domain['cleanup']
    with psycopg.connect(dsn, autocommit=True) as db:
        record['exact_cleanup_queries'] = {
            'source_schema_absent': db.execute('SELECT 1 FROM pg_namespace WHERE nspname=%s', (names['source_schema_removed'],)).fetchone() is None,
            'restored_database_absent': db.execute('SELECT 1 FROM pg_database WHERE datname=%s', (names['restored_database_removed'],)).fetchone() is None}
with (OUT/'result.json').open('x') as stream:
    json.dump(record, stream, indent=2); stream.write('\n')
print(json.dumps(record))
assert before==after
assert record['source_unchanged']
assert result.testsRun==1 and result.wasSuccessful() and not result.skipped
assert record['exact_cleanup_queries']=={'source_schema_absent':True,'restored_database_absent':True}
