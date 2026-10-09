"""Fresh limited validation process; no application/numerical import before caps."""
import json
from pathlib import Path
import sys
import time

if sys.platform != "linux":
    print(json.dumps({"error":"Bounded binary mesh validation requires the qualified Linux resource worker."}))
    sys.exit(1)
import resource

resource.setrlimit(resource.RLIMIT_AS, (256*1024*1024,256*1024*1024))
resource.setrlimit(resource.RLIMIT_CPU, (30,30))
resource.setrlimit(resource.RLIMIT_CORE, (0,0))

from binary_mesh_core import BUNDLE_BYTES, RESULT_BYTES, validate_bundle


def main():
    started=time.monotonic()
    path=Path(sys.argv[1])
    with path.open('rb') as stream:raw=stream.read(BUNDLE_BYTES+1)
    result=validate_bundle(raw)
    result['resource_measurement']={'wall_seconds':time.monotonic()-started,
        'cpu_seconds':resource.getrusage(resource.RUSAGE_SELF).ru_utime+resource.getrusage(resource.RUSAGE_SELF).ru_stime,
        'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
        'address_space_limit_bytes':resource.getrlimit(resource.RLIMIT_AS)[0],
        'cpu_limit_seconds':resource.getrlimit(resource.RLIMIT_CPU)[0]}
    output=json.dumps(result,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
    if len(output)>RESULT_BYTES:raise ValueError('Validation IPC exceeds256KiB')
    sys.stdout.buffer.write(output)


if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'error':str(error)[:1500]}))
        sys.exit(1)
