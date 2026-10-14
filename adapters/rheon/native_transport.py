"""Launch-only replacement for the captured lab's subprocess dependency."""
import io
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import sys

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

    def __init__(self, binary, policy_raw, *, allowed_seeds=(900, 901, 902, 903), capture_diagnostics=False, evaluation_mode=False, capture_hook=None):
        if type(allowed_seeds) is not tuple or allowed_seeds not in ((900, 901, 902, 903), (500, 501)):
            raise ValueError('Unsupported reviewed native seed scope.')
        if type(capture_diagnostics) is not bool:
            raise ValueError('Invalid diagnostic capture flag.')
        if type(evaluation_mode) is not bool or (capture_hook is not None and not callable(capture_hook)):
            raise ValueError('Invalid evaluation capture hook.')
        if (evaluation_mode and allowed_seeds != (900, 901, 902, 903)) or (capture_hook is not None and not evaluation_mode):
            raise ValueError('Evaluation capture requires the closed evaluation seed scope.')
        self.evaluation_mode = evaluation_mode
        self.capture_hook = capture_hook
        self.capture_diagnostics = capture_diagnostics
        self.diagnostics = []
        self.allowed_seeds = tuple(str(seed) for seed in allowed_seeds)
        self.binary = str(Path(binary))
        self.native, _ = generate.capture(binary, 8 * 1024 * 1024)
        self.policy, self.observed = generate.native_policy(policy_raw, self.native)
        self.evidence = []

    def Popen(self, args, **kwargs):
        if (type(args) is not list or len(args) != 4 or args[0] != self.binary
                or args[1] != '32' or args[2] not in ('jacobi', 'sgs', 'learned')
                or args[3] not in getattr(self, 'allowed_seeds', ('900', '901', '902', '903'))
                or kwargs != {'stdin': subprocess.PIPE, 'stdout': subprocess.PIPE}):
            raise ValueError('Native launch differs from admitted CPU comparison.')
        if os.path.lexists('/etc/ld.so.preload'):
            raise ValueError('System preload is unsupported.')
        native_fd = generate.seal('rheon-cpu-native', self.native)
        loader_fd = None
        process = None
        diagnostic = None
        try:
            loader_fd = generate.seal('rheon-cpu-loader', self.observed[self.policy['loader']['path']][0])
            command = [f'/proc/self/fd/{loader_fd}', *self.policy['loader_arguments'],
                       f'/proc/self/fd/{native_fd}', *args[1:]]
            if self.capture_diagnostics:
                diagnostic = tempfile.TemporaryFile()
                kwargs = dict(kwargs, stderr=diagnostic)
            process = subprocess.Popen(command, pass_fds=(native_fd, loader_fd), **kwargs)
            if diagnostic is not None:
                original_wait = process.wait
                stream = diagnostic
                captured = False
                def wait_with_diagnostics(*wait_args, **wait_kwargs):
                    nonlocal captured
                    code = original_wait(*wait_args, **wait_kwargs)
                    if not captured:
                        captured = True
                        stream.seek(0)
                        raw = stream.read(65537)
                        stream.close()
                        if len(raw) > 65536:
                            raise ValueError('Native diagnostics exceed bound.')
                        self.diagnostics.append({'seed': int(args[3]), 'method': args[2],
                                                 'exit_code': code, 'stderr_hex': raw.hex(),
                                                 'stderr_sha256': generate.sha(raw)})
                        if raw:
                            sys.stderr.buffer.write(raw)
                            sys.stderr.buffer.flush()
                    return code
                process.wait = wait_with_diagnostics
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
            if len(self.evidence) >= (72 if getattr(self, 'evaluation_mode', False) else 64):
                raise ValueError('Native launch count exceeds admitted comparison.')
            self.evidence.append({'method': args[2], 'seed': int(args[3]), 'ready': ready, 'mappings': maps})
            process.stdout = PrefixReader(header + raw, process.stdout)
            if getattr(self, 'capture_hook', None) is not None:
                process.stdout = self.capture_hook(args, process.stdout)
            return process
        except BaseException:
            if process is not None:
                process.kill()
                process.wait(timeout=3)
                process.stdin.close()
                process.stdout.close()
            raise
        finally:
            if diagnostic is not None and process is None:
                diagnostic.close()
            os.close(native_fd)
            if loader_fd is not None:
                os.close(loader_fd)
