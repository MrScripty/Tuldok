"""Bounded non-scientific process fixture. Never a scientific/model acceptance."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

mode=sys.argv[1]
if mode=='complete':
    source=Path(sys.argv[2]).read_bytes()
    child=subprocess.Popen(['/usr/bin/python3','-c','print("child complete")'])
    child.wait(timeout=3)
    Path(sys.argv[3],'result.txt').write_bytes(source)
    print(json.dumps({'stage':'done','bytes':len(source)}),flush=True)
elif mode=='escape':
    leader=os.fork()
    if leader==0:
        os.setsid()
        child=os.fork()
        if child:os._exit(0)
        os.setsid();signal.signal(signal.SIGTERM,signal.SIG_IGN)
        Path(sys.argv[2]).write_text(str(os.getpid()))
        time.sleep(30);os._exit(0)
    os.waitpid(leader,0)
    time.sleep(30)
elif mode=='flood':
    os.write(1,b'x'*(2*1024*1024))
elif mode=='sleep':
    time.sleep(30)
elif mode=='nonzero':
    raise SystemExit(7)
elif mode=='outputs':
    Path(sys.argv[2],'large').write_bytes(b'x'*4096)
else:
    raise SystemExit(2)
