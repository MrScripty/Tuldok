"""Local model fixtures; never contact a paid provider."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RESULT = dict(book_present=True,crop_suitable=True,corner_reference='book',corners=[
    dict(name=name,visibility='visible',x=x,y=y) for name,(x,y) in zip(
        ['top_left','top_right','bottom_right','bottom_left'],
        [(0.12,0.14),(0.88,0.14),(0.88,0.86),(0.12,0.86)])])


def start():
    requests=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            requests.append((self.path,None,dict(self.headers)))
            data={'data':[{'id':'corners-test','name':'Corner test','architecture':{'input_modalities':['image'],'output_modalities':['text']},'supported_parameters':['structured_outputs']},
                          {'id':'text-only','architecture':{'input_modalities':['text'],'output_modalities':['text']},'supported_parameters':['structured_outputs']}]}
            encoded=json.dumps(data).encode();self.send_response(200);self.send_header('Content-Length',str(len(encoded)));self.end_headers();self.wfile.write(encoded)
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append((self.path,body,dict(self.headers)))
            value=json.loads(json.dumps(RESULT))
            if body['model']=='invalid-corners':value['corners'][0]['x']=1.5
            if body['model']=='no-book':value.update(book_present=False,crop_suitable=False,corners=[])
            reason='length' if body['model']=='truncated' else 'stop'
            raw=json.dumps(value)
            self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
            for part in [raw[:60],raw[60:]]:
                self.wfile.write(('data: '+json.dumps({'choices':[{'delta':{'content':part},'finish_reason':None}]})+'\n\n').encode());self.wfile.flush()
            self.wfile.write(('data: '+json.dumps({'choices':[{'delta':{},'finish_reason':reason}]})+'\n\ndata: [DONE]\n\n').encode())
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    return server,'http://127.0.0.1:'+str(server.server_port),requests
