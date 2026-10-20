import unittest,sys,os,json,time,hashlib,subprocess,pathlib,psycopg
from psycopg import sql
root=pathlib.Path('/workspace/Tuldok');sys.path[:0]=[str(root),str(root/'tests')]
output=pathlib.Path('/workspace/tuldok-transfer/current-qualification')
with psycopg.connect(os.environ['TULDOK_DATABASE_URL'],autocommit=True) as c:
 before={r[0] for r in c.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'catalog_%'")}
assert not before, before
import test_workflow_client_http as subject
suite=unittest.TestSuite()
for cls in (subject.WorkflowHTTPTests,subject.RetainedWorkflowHTTPTests):
 for name in unittest.defaultTestLoader.getTestCaseNames(cls):
  if name!='test_actual_classifier_exact_operands_compare_through_http_and_clean_cli':suite.addTest(cls(name))
print('SUBJECT',subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),flush=True)
print('SCOPE: Existing12 neutral HTTP/CLI cases; classifier comparison excluded because no selected qualified local CPU training runtime.',flush=True)
start=time.monotonic(); result=unittest.TextTestRunner(verbosity=2).run(suite)
with psycopg.connect(os.environ['TULDOK_DATABASE_URL'],autocommit=True) as c:
 after={r[0] for r in c.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'catalog_%'")}
 for name in sorted(after-before): c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(name)))
 remaining={r[0] for r in c.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'catalog_%'")}
assert remaining==before
receipt=dict(head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),seconds=time.monotonic()-start,scope='current12 neutral HTTP/CLI; explicit classifier exclusion',schemas_before=sorted(before),owned_schemas_removed=sorted(after-before),schemas_after=sorted(remaining))
(output/'current-m5-result.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt),flush=True)
sys.exit(not result.wasSuccessful() or bool(result.skipped))
