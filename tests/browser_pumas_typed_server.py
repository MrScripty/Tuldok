"""Existing app composition; source-derived fixture or external actual gateway."""
import json
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from fake_pumas_typed import start
receipt=os.environ.get('PUMAS_TYPED_GATEWAY_RECEIPT')
server=None
if receipt:
 gateway=json.loads(Path(receipt).read_text()); url=gateway['gateway_url']
 control=Path(receipt).parent/'text-worker/control.json'
 def configure(value):
  old=json.loads(control.read_text());old.update(text_response=value['content'],text_mode='success');control.write_text(json.dumps(old))
 origin='actual pinned native gateway with controlled backend; no model inference'
 configure({'content':'{"label":"positive"}'})
else:
 server,url,state=start()
 def configure(value):state['content']=value['content'];state['mode']='success'
 origin='source-derived HTTP fixture; not native Pumas'
original=app.make_handler

def make_handler(dataset):
 class Handler(original(dataset)):
  def do_POST(self):
   if self.path=='/test/pumas-control':
    body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));configure(body);return self.reply({'configured':True})
   return super().do_POST()
 return Handler
app.make_handler=make_handler
print('TYPED_GATEWAY='+url,flush=True);print('TYPED_ORIGIN='+origin,flush=True)
try:app.main()
finally:
 if server:server.shutdown();server.server_close()
