"""Production app plus explicit native receipt or source-derived typed fixture."""
import json,os,sys,hashlib,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from fake_pumas_typed import start
receipt=os.environ.get('TULDOK_PUMAS_TEXT_SELECTION_GATEWAY_RECEIPT');server=None
if receipt:
    metadata=json.loads(Path(receipt).read_text())
    if metadata['producer_commit']!='40c5cbfed67a6f0e862a1197bb5105363d67bdb1' or not metadata['compiled_without_cfg_test'] or not metadata['controlled_no_models'] or metadata['image_worker_started']:raise RuntimeError('Unsupported native text receipt; no fallback')
    url=metadata['gateway_url'];origin='Original pinned typed HTTP modules; authored external text backend, no models or authenticated discovery'
else:
    server,url,state=start();origin='Source-derived typed HTTP fixture; not native Pumas'
# Qualification instrumentation records original transport calls/raw hashes;
# it does not substitute or synthesize gateway responses.
import gateway_discovery
log=os.environ.get('TULDOK_PUMAS_SELECTION_READ_LOG')
if log:
    original_read=gateway_discovery.get_json;lock=threading.Lock()
    def recorded(host,port,path,deadline,payload=None,**kwargs):
        value={'method':'POST' if payload is not None else 'GET','host':host,'port':port,'path':path,'scope':'Consumer transport-call instrumentation; not gateway-side logging'}
        decode=kwargs.pop('decode',json.loads)
        def observed(raw):
            value.update(response_sha256=hashlib.sha256(raw).hexdigest(),response_bytes=len(raw));return decode(raw)
        try:
            result=original_read(host,port,path,deadline,payload=payload,decode=observed,**kwargs);value['completed']=True;return result
        finally:
            with lock:
                with Path(log).open('a') as out:out.write(json.dumps(value)+'\n')
    gateway_discovery.get_json=recorded
print('TYPED_GATEWAY='+url,flush=True);print('TYPED_ORIGIN='+origin,flush=True)
try:app.main()
finally:
    if server:server.shutdown();server.server_close()
