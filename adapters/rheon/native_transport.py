"""Launch-only replacement for the captured lab's subprocess dependency."""
import io
import os
from pathlib import Path
import struct
import subprocess

if __package__:
    from . import generate
else:
    import generate


class PrefixReader:
    def __init__(self, prefix, stream):
        self.prefix = io.BytesIO(prefix)
        self.stream = stream

    def read(self, size=-1):
        if size < 0:
            raise ValueError('Native reads must be bounded.')
        head = self.prefix.read(size)
        return head + self.stream.read(size - len(head)) if len(head) < size else head

    def close(self):
        self.prefix.close()
        self.stream.close()


def exact(stream, size):
    raw = bytearray()
    while len(raw) < size:
        part = stream.read(size - len(raw))
        if not part:
            raise ValueError('Truncated native READY.')
        raw.extend(part)
    return bytes(raw)


class Transport:
    PIPE = subprocess.PIPE

    def __init__(self, binary, policy_raw):
        self.binary = str(Path(binary))
        self.native, _ = generate.capture(binary, 8 * 1024 * 1024)
        self.policy, self.observed = generate.native_policy(policy_raw, self.native)
        self.evidence = []

    def Popen(self, args, **kwargs):
        if (type(args) is not list or len(args) != 4 or args[0] != self.binary
                or args[1] != '32' or args[2] not in ('jacobi', 'sgs', 'learned')
                or args[3] not in ('900', '901', '902', '903')
                or kwargs != {'stdin': subprocess.PIPE, 'stdout': subprocess.PIPE}):
            raise ValueError('Native launch differs from admitted CPU comparison.')
        if os.path.lexists('/etc/ld.so.preload'):
            raise ValueError('System preload is unsupported.')
        native_fd = generate.seal('rheon-cpu-native', self.native)
        loader_fd = None
        process = None
        try:
            loader_fd = generate.seal('rheon-cpu-loader', self.observed[self.policy['loader']['path']][0])
            command = [f'/proc/self/fd/{loader_fd}', *self.policy['loader_arguments'],
                       f'/proc/self/fd/{native_fd}', *args[1:]]
            process = subprocess.Popen(command, pass_fds=(native_fd, loader_fd), **kwargs)
            header = exact(process.stdout, 4)
            length, = struct.unpack('<I', header)
            if length > 65536:
                raise ValueError('Oversized native READY.')
            raw = exact(process.stdout, length)
            ready = generate.decode(raw)
            if (type(ready) is not dict or ready.get('schema') != 'rheon-trajectory-v1'
                    or ready.get('n') != 32 or ready.get('method') != args[2]
                    or ready.get('seed') != int(args[3]) or ready.get('dt') != 1/60
                    or ready.get('density') != 1.25 or ready.get('spacing') != [1/32]*3
                    or ready.get('face_lengths') != [33*32*32]*3):
                raise ValueError('Native READY differs from requested controls.')
            maps = generate.mapping_evidence(process.pid, self.observed, native_fd, loader_fd)
            if len(self.evidence) >= 64:
                raise ValueError('Native launch count exceeds admitted comparison.')
            self.evidence.append({'method': args[2], 'seed': int(args[3]), 'ready': ready, 'mappings': maps})
            process.stdout = PrefixReader(header + raw, process.stdout)
            return process
        except BaseException:
            if process is not None:
                process.kill()
                process.wait(timeout=3)
                process.stdin.close()
                process.stdout.close()
            raise
        finally:
            os.close(native_fd)
            if loader_fd is not None:
                os.close(loader_fd)
