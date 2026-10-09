import tempfile,threading,json,uuid
from unittest.mock import patch
from app import Dataset
trace={}
with tempfile.TemporaryDirectory() as folder:
 data=Dataset(folder);owner=data.caption_proposals
 try:
  old=[dict(id=uuid.uuid4().hex,revision=1,status='completed',source={'id':'a'*32},input_image_base64='fixture-image',raw_response_base64='fixture-response',extension={'input_image_base64':'nested retained metadata'}) for _ in range(2)]
  with owner.lock,owner.db:
   for job in old:owner._save(job)
  old=[owner.get(job['id']) for job in reversed(old)]
  changed=[dict(job,revision=job['revision']+1,status='rejected') for job in old]
  writes=[(json.dumps(job),job['id']) for job in changed]
  decoder=json.loads;entered=False;errors=[];writer=None
  def write():
   try:
    with data.lock,data.db:data.db.executemany('UPDATE caption_proposals SET data=? WHERE id=?',writes)
   except BaseException as error:errors.append(str(error))
  def decode_projection(text,*args,**kwargs):
   global entered,writer
   decoded=decoder(text,*args,**kwargs)
   assert 'input_image_base64' not in decoded and 'raw_response_base64' not in decoded
   assert decoded['extension']['input_image_base64']=='nested retained metadata'
   if not entered:
    entered=True;writer=threading.Thread(target=write);writer.start();writer.join(2)
    assert not writer.is_alive(),'Shared lock blocked writer during Python decoding'
    assert not errors,errors
    trace['writer_completed_before_first_decode_return']=True
   return decoded
  with patch('caption_proposals.json.loads',side_effect=decode_projection):current=owner.snapshot()['jobs']
  summary=lambda row:{k:v for k,v in row.items() if k not in ('input_image_base64','raw_response_base64')}
  assert current==[summary(row) for row in old]
  following=owner.snapshot()['jobs'];assert following==[summary(row) for row in changed]
  for row in changed:assert owner.get(row['id'])==row
  trace.update(captured_statuses=[r['status'] for r in current],following_statuses=[r['status'] for r in following],capture_rows=len(current),exact_GET_payload_retained=True,nested_metadata_preserved=True)
  print(json.dumps({'result':'PASS','trace':trace}))
 finally:data.close()
