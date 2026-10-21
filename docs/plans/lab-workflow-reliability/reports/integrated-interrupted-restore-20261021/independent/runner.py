import contextlib
import hashlib
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

ROOT = Path('/workspace/Tuldok-interrupted-restore-20261021')
EXPECTED_HEAD = 'd02f034aa1bba6cd55dfd47ae44ebcb7014200a5'
OUT = Path(__file__).parent/'reproduction-d02f034'

def git(*arguments):
    return subprocess.check_output(['git', *arguments], cwd=ROOT, text=True).strip()

assert git('rev-parse', 'HEAD') == EXPECTED_HEAD
assert not git('status', '--porcelain=v1')
OUT.mkdir(mode=0o700, exist_ok=False)
container = json.loads(subprocess.check_output(['docker', 'inspect', 'tuldok-qa-20261020']))[0]
assert container['State']['Running']
settings = dict(value.split('=', 1) for value in container['Config']['Env'] if '=' in value)
dsn = make_conninfo(host='127.0.0.1', port=55432,
    dbname=settings.get('POSTGRES_DB', 'postgres'),
    user=settings.get('POSTGRES_USER', 'postgres'), password=settings['POSTGRES_PASSWORD'])
os.environ['TULDOK_DATABASE_URL'] = dsn
os.environ['TULDOK_RETENTION_ACCEPTANCE_REPORT'] = str(OUT/'domain.json')

def inventory():
    with psycopg.connect(dsn, autocommit=True) as connection:
        return {
            'schemas': [row[0] for row in connection.execute("SELECT nspname FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' AND nspname NOT IN ('public','information_schema') ORDER BY nspname")],
            'databases': [row[0] for row in connection.execute('SELECT datname FROM pg_database ORDER BY datname')],
            'server_version': connection.execute('SHOW server_version').fetchone()[0]}

before = inventory()
assert before['schemas'] == [], before
source = {'commit': git('rev-parse', 'HEAD'), 'tree': git('rev-parse', 'HEAD^{tree}'),
    'test_sha256': hashlib.sha256((ROOT/'tests/test_integrated_retention_restore.py').read_bytes()).hexdigest(),
    'python': platform.python_version(), 'psycopg': psycopg.__version__}
sys.path[:0] = [str(ROOT/'tests'), str(ROOT)]
os.chdir(ROOT)
with (OUT/'unittest.log').open('x') as stream:
    with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
        suite = unittest.defaultTestLoader.loadTestsFromName('test_integrated_retention_restore.IntegratedRetentionRestoreTests.test_stopped_transfer_retains_recovery_timing_and_exact_publication_consumers')
        start = time.perf_counter()
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
        seconds = time.perf_counter()-start
after = inventory()
record = {'format': 'independent_interrupted_restore_reproduction_v1', 'source': source,
    'tests_run': result.testsRun, 'successful': result.wasSuccessful(),
    'failures': len(result.failures), 'errors': len(result.errors), 'skips': len(result.skipped),
    'unittest_runner_seconds': seconds, 'resources_before': before, 'resources_after': after,
    'source_unchanged': git('rev-parse', 'HEAD') == EXPECTED_HEAD and not git('status', '--porcelain=v1'),
    'log_sha256': hashlib.sha256((OUT/'unittest.log').read_bytes()).hexdigest()}
if (OUT/'domain.json').exists():
    domain = json.loads((OUT/'domain.json').read_bytes())
    record['domain_sha256'] = hashlib.sha256((OUT/'domain.json').read_bytes()).hexdigest()
    names = domain.get('cleanup', {})
    with psycopg.connect(dsn, autocommit=True) as connection:
        record['independent_exact_cleanup_query'] = {
            'source_schema_absent': connection.execute('SELECT 1 FROM pg_namespace WHERE nspname=%s', (names.get('source_schema_removed'),)).fetchone() is None,
            'restored_database_absent': connection.execute('SELECT 1 FROM pg_database WHERE datname=%s', (names.get('restored_database_removed'),)).fetchone() is None}
with (OUT/'result.json').open('x') as stream:
    json.dump(record, stream, indent=2)
    stream.write('\n')
print(json.dumps(record))
assert before == after
assert record['source_unchanged']
assert result.testsRun == 1 and result.wasSuccessful() and not result.skipped
assert record['independent_exact_cleanup_query'] == {'source_schema_absent': True, 'restored_database_absent': True}
