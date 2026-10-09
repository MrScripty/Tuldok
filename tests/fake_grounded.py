"""Controlled Pumas model/chat fixture. No real model quality is asserted."""
import json
import select
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def start(catalog_entered=None):
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def reply(self, body, status=200, encoding='utf-8', missing_bytes=0):
            data=json.dumps(body,ensure_ascii=False).encode(encoding)
            self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)+missing_bytes));self.end_headers()
            try:self.wfile.write(data)
            except (BrokenPipeError,ConnectionResetError):pass
        def do_GET(self):
            if self.path!='/v1/models':return self.reply({},404)
            if catalog_entered is not None:
                catalog_entered.set()
                ready,_,_=select.select([self.connection],[],[],15)
                if ready and not self.connection.recv(1):return
            self.reply({'data':[{'id':'grounded-text-test','owned_by':'pumas'},
                                {'id':'image-only','owned_by':'pumas','capabilities':['image_generation']}]})
        def do_POST(self):
            if self.path!='/v1/chat/completions':return self.reply({},404)
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            observed={'path':self.path,'body':body,'cancelled':False};requests.append(observed)
            brief=json.loads(body['messages'][1]['content']);mode=brief['variation'];source=brief['source']
            if mode=='slow':
                end=time.monotonic()+15
                while time.monotonic()<end:
                    ready,_,_=select.select([self.connection],[],[],.05)
                    if ready and not self.connection.recv(1):observed['cancelled']=True;return
            if mode=='provider_error':return self.reply({'error':'simulated provider failure'},503)
            candidates=[{'text':f'{source} (variant {i+1})','label':brief['source_class'],
                         'evidence':[{'start':0,'end':len(source),'quote':source}]} for i in range(brief['number_of_candidates'])]
            if mode=='invalid_quote':candidates[0]['evidence'][0]['quote']='fabricated'
            if mode=='wrong_label':candidates[0]['label']='other'
            if mode=='duplicate':candidates[0]['text']=source
            content=json.dumps({'candidates':candidates},ensure_ascii=False)
            if mode=='oversized':content+=' '*270000
            self.reply({'model':body['model'],'choices':[{'finish_reason':'length' if mode=='truncated' else 'stop','message':{'content':content}}]},
                       encoding='utf-16' if mode=='utf16' else 'utf-8',
                       missing_bytes=10 if mode=='short_http_body' else 0)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    return server, f'http://127.0.0.1:{server.server_port}', requests
