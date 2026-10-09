"""Owned native SDK fixture when explicitly supplied; otherwise truthful refusal UI."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app

process=None
out=None
def interrupt(*_):raise KeyboardInterrupt
signal.signal(signal.SIGTERM,interrupt)
try:
    bridge=os.environ.get('TULDOK_PUMAS_NATIVE_BRIDGE')
    fixture=os.environ.get('TULDOK_PUMAS_OWNER_FIXTURE')
    if bool(bridge)!=bool(fixture):raise RuntimeError('Both explicitly installed native fixture and bridge are required; no fallback.')
    if bridge:
        out=Path(tempfile.mkdtemp(prefix='tuldok-owned-pumas-'))
        log=(out/'fixture.log').open('wb')
        process=subprocess.Popen([fixture,str(out/'owner')],stdout=log,stderr=subprocess.STDOUT)
        ready=out/'owner/ready.json';deadline=time.monotonic()+20
        while not ready.exists():
            if process.poll() is not None or time.monotonic()>deadline:raise RuntimeError('Original SDK fixture did not become ready; no replacement owner.')
            time.sleep(.02)
        metadata=json.loads(ready.read_text())
        import hashlib
        sys.argv += ['--pumas-local-bridge',bridge,'--pumas-local-bridge-sha256',hashlib.sha256(Path(bridge).read_bytes()).hexdigest(),'--pumas-registry',metadata['registry']]
        print('OWNER_FIXTURE='+str(out/'owner'),flush=True)
        print('OWNER_SELECTED='+json.dumps(metadata['selected']),flush=True)
        print('OWNER_ENDPOINT='+metadata['endpoint'],flush=True)
        print('OWNER_SCOPE='+metadata['scope'],flush=True)
    else:print('OWNER_SCOPE=Unconfigured installed SDK bridge; real application unsupported-operation refusal only',flush=True)
    app.main()
finally:
    if process is not None:
        (out/'owner/mode').write_text('');(out/'owner/stop').write_text('stop')
        try:process.wait(timeout=20)
        except subprocess.TimeoutExpired:process.kill();process.wait();raise RuntimeError('Owned fixture cleanup failed')
        log.close()
        if process.returncode!=0:raise RuntimeError('Owned SDK fixture exited unsuccessfully')
