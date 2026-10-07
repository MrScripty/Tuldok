"""Real loopback classification admission refusal with no provider request."""
import json,pathlib,sys,tempfile,threading,urllib.request,urllib.error
from http.server import ThreadingHTTPServer
sys.path.insert(0,'/workspace/Tuldok')
from app import Dataset,make_handler
body=json.load(sys.stdin)
with tempfile.TemporaryDirectory(prefix='classification-invalid-url-') as tmp:
    data=Dataset(tmp);server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(data));threading.Thread(target=server.serve_forever,daemon=True).start()
    url=f'http://127.0.0.1:{server.server_port}/api/workbench/caption-proposals'
    def call(path='',body=None):
        req=urllib.request.Request(url+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=5) as r:return dict(status=r.status,body=json.load(r))
        except urllib.error.HTTPError as r:return dict(status=r.code,body=json.load(r))
    try:
        first=call(body=body);exact=call('/'+body['request_id']);repeat=call(body=body)
        assert first['status']==400 and repeat['status']==400 and exact['status']==404
        count=data.db.execute('SELECT count(*) FROM caption_proposals').fetchone()[0]
        assert count==0 and data.caption_proposals.worker is None
        print(json.dumps(dict(first=first,exact=exact,repeat=repeat,jobs=count,worker_started=False)))
    finally:server.shutdown();server.server_close();data.close()
