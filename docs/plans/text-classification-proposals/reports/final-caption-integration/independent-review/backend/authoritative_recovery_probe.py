"""Independent authoritative recovery checks; temporary SQLite and loopback fixture only."""
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path
sys.path[:0]=['/workspace/Tuldok','/workspace/Tuldok/tests']
from app import Dataset,make_handler
from fake_classification_model import start
from workbench import WorkbenchError

class AuthoritativeRecovery(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.data=Dataset(self.tmp.name);self.addCleanup(lambda:self.data.close())
  self.model,self.url,self.requests=start();self.addCleanup(self.model.server_close);self.addCleanup(self.model.shutdown)
  self.row=self.data.workbench.import_asset(dict(kind='text',text='Independent durable admission source',groups=['synthetic-author']))
  self.owner=self.data.text_classification_proposals
  self.body=dict(request_id=uuid.uuid4().hex,source_id=self.row['id'],revision=self.row['revision'],source_revision=self.row['source_revision'],server_url=self.url+'/v1/',model='classification-fixture',instruction='original exact intent',seed=7,labels=['Keep','keep'])
  self.http=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.data));threading.Thread(target=self.http.serve_forever,daemon=True).start();self.addCleanup(self.http.server_close);self.addCleanup(self.http.shutdown)
  self.base='http://127.0.0.1:'+str(self.http.server_port)+'/api/workbench/text-classification-proposals'
 def api(self,suffix='',body=None):
  req=urllib.request.Request(self.base+suffix,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
  with urllib.request.urlopen(req) as response:return response.status,json.load(response)
 def generate(self):
  self.api(body=self.body);self.owner.worker.join(4);self.assertFalse(self.owner.worker.is_alive());job=self.api('/'+self.body['request_id'])[1];self.assertEqual(job['status'],'completed',job['error']);return job
 def test_every_changed_intent_conflicts_including_equivalent_normalized_transport(self):
  job=self.generate()
  for key,value in [('server_url',self.url),('model',' classification-fixture '),('instruction','original exact intent '),('seed',8),('labels',['keep','Keep']),('source_id',uuid.uuid4().hex),('revision',2),('source_revision',2)]:
   with self.subTest(key=key),self.assertRaises(urllib.error.HTTPError) as rejected:self.api(body=dict(self.body,**{key:value}))
   self.assertEqual(rejected.exception.code,409)
  self.assertEqual(self.api('/'+job['id'])[1],job);self.assertEqual(len(self.requests),1)
 def test_exact_replay_survives_changed_or_deleted_source_without_second_completion(self):
  job=self.generate()
  self.data.workbench.save(self.row['id'],dict(self.row,annotation={'label':'author target'},review='draft'))
  state=[tuple(row) for row in self.data.db.execute('SELECT * FROM workbench_history ORDER BY rowid')]
  self.assertEqual(self.api(body=self.body)[1],job)
  self.assertEqual([tuple(row) for row in self.data.db.execute('SELECT * FROM workbench_history ORDER BY rowid')],state)
  with self.data.lock,self.data.db:self.data.db.execute('DELETE FROM workbench_records WHERE id=?',(self.row['id'],))
  self.assertEqual(self.api('/'+job['id'])[1],job);self.assertEqual(self.api(body=self.body)[1],job);self.assertEqual(len(self.requests),1)
 def test_exact_id_remains_authoritative_when_outside_latest_fifty(self):
  job=self.generate()
  with self.data.lock,self.data.db:
   for index in range(51):self.owner._save(dict(job,id=uuid.uuid4().hex,error='synthetic later envelope '+str(index)))
  summary=self.api()[1]['jobs'];self.assertEqual(len(summary),50);self.assertNotIn(job['id'],[row['id'] for row in summary])
  self.assertEqual(self.api('/'+job['id'])[1],job);self.assertEqual(self.api(body=self.body)[1],job);self.assertEqual(len(self.requests),1)
 def test_concurrent_exact_replays_share_one_admission_and_response(self):
  accepted=[];errors=[]
  def post():
   try:accepted.append(self.api(body=self.body)[1])
   except Exception as error:errors.append(error)
  workers=[threading.Thread(target=post) for _ in range(4)]
  for worker in workers:worker.start()
  for worker in workers:worker.join(4);self.assertFalse(worker.is_alive())
  self.assertEqual(errors,[]);self.assertEqual({row['id'] for row in accepted},{self.body['request_id']})
  self.owner.worker.join(4);self.assertEqual(len(self.requests),1);self.assertEqual(self.owner.get(self.body['request_id'])['status'],'completed')
 def test_early_missing_and_restart_do_not_authorize_automatic_inference(self):
  with self.assertRaises(urllib.error.HTTPError) as missing:self.api('/'+self.body['request_id'])
  self.assertEqual(missing.exception.code,404);self.assertEqual(self.requests,[])
  job=self.generate()
  with self.data.lock,self.data.db:job['status']='generating';self.owner._save(job)
  # The handler closes over the old dataset; restart owner/database then use direct exact owner reads.
  self.data.close();self.data=Dataset(self.tmp.name);self.owner=self.data.text_classification_proposals
  interrupted=self.owner.get(job['id']);self.assertEqual(interrupted['status'],'interrupted')
  self.assertEqual(self.owner.start(self.body),interrupted);self.assertEqual(len(self.requests),1)

if __name__=='__main__':unittest.main(verbosity=2)
