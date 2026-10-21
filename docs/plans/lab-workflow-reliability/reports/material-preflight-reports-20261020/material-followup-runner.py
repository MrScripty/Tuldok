from pathlib import Path
import datetime,json,os,sys,unittest
from unittest.mock import patch
import psycopg
from psycopg import sql
root=Path('/workspace/Tuldok-material-preflight-reports-20261020');sys.path[:0]=[str(root/'tests'),str(root)]
out=Path('/tmp/tuldok-material-preflight-reports-20261020')
import test_extension_bindings as bindings
import test_large_recipe_contract as large
import test_agent_project_snapshots as snapshots
import test_external_runs as external
import test_experiments as studies
owned=set()
with psycopg.connect(os.environ['TULDOK_DATABASE_URL'],autocommit=True) as connection:
 before={r[0]for r in connection.execute("select nspname from pg_namespace where nspname like 'catalog_%'")}
 def tracked(original):
  def setup(case):
   original(case);schema=case.dataset.db.schema;assert schema not in before
   owned.add(schema);print(json.dumps({'fixture_owner':type(case).__name__,'new_schema':schema}),flush=True)
  return setup
 loader=unittest.TestLoader();suite=unittest.TestSuite()
 suite.addTests(loader.loadTestsFromName('test_material_preflight_reports'))
 started=datetime.datetime.now(datetime.timezone.utc).isoformat()
 try:
  with patch.object(external.ExternalCase,'setUp',tracked(external.ExternalCase.setUp)), \
       patch.object(bindings.BoundExtensionRecipeTests,'setUp',tracked(bindings.BoundExtensionRecipeTests.setUp)), \
       patch.object(large.LargeRecipeContract,'setUp',tracked(large.LargeRecipeContract.setUp)):
   result=unittest.TextTestRunner(verbosity=2).run(suite)
 finally:
  for schema in sorted(owned):
   assert schema not in before
   connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
   assert connection.execute('select 1 from pg_namespace where nspname=%s',(schema,)).fetchone()is None
   print(json.dumps({'removed_exact_owned_schema':schema}),flush=True)
 receipt={'started_utc':started,'completed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
  'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
  'owned_schemas_removed':sorted(owned),'no_constructor_or_domain_substitution':'Testfixture setUp wrappers only record exact fresh schema after unchanged setup; no production constructor or result patched.',
  'source_tree':'uncommitted isolated dependent branch from1442f184; exactsourcehashmanifest retained separately'}
 (out/'material-followup-result.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt),flush=True)
raise SystemExit(not result.wasSuccessful())
