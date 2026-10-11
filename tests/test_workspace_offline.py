"""Test-only libc transport qualification; no adversarial sandbox claim.

Linux and cc are required for this qualification gate. The canary calls an
external TEST-NET address; EACCES is raised by the injection before real libc
transport. Successful TCP/UDP loopback and Unix round trips prove local services
remain usable. Then run the actual app/browser/trainer with the same LD_PRELOAD.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'tests' / 'fixtures' / 'workspaces' / 'offline_loopback.c'

CANARY = r'''
import errno,json,socket,tempfile
from pathlib import Path
observed = []
for family,address in ((socket.AF_INET,('192.0.2.1',443)),
                       (socket.AF_INET6,('2001:db8::1',443))):
    with socket.socket(family,socket.SOCK_STREAM) as client:
        client.settimeout(1)
        try: client.connect(address)
        except OSError as error:
            assert error.errno == errno.EACCES, (address,error)
            observed.append('connect denied '+address[0])
        else: raise AssertionError('external connect unexpectedly accepted')
    with socket.socket(family,socket.SOCK_DGRAM) as client:
        try: client.sendto(b'not sent',address)
        except OSError as error:
            assert error.errno == errno.EACCES, (address,error)
            observed.append('sendto denied '+address[0])
        else: raise AssertionError('external datagram unexpectedly accepted')
for name in ('192.0.2.1','2001:db8::1','external-test.invalid'):
    try: socket.getaddrinfo(name,443)
    except socket.gaierror as error:
        assert error.errno == socket.EAI_NONAME, (name,error)
        observed.append('resolution denied '+name)
    else: raise AssertionError('external resolution unexpectedly accepted')
assert socket.getaddrinfo('localhost',80)
for family,address in ((socket.AF_INET,('127.0.0.1',0)),(socket.AF_INET6,('::1',0))):
    with socket.socket(family,socket.SOCK_STREAM) as server, socket.socket(family,socket.SOCK_STREAM) as client:
        server.bind(address);server.listen();client.settimeout(2)
        client.connect(server.getsockname())
        peer,_=server.accept()
        with peer:
            client.sendall(b'local');assert peer.recv(5)==b'local'
        observed.append('tcp local '+address[0])
    with socket.socket(family,socket.SOCK_DGRAM) as server, socket.socket(family,socket.SOCK_DGRAM) as client:
        server.bind(address);server.settimeout(2)
        client.sendto(b'local',server.getsockname());assert server.recvfrom(5)[0]==b'local'
        observed.append('udp local '+address[0])
with tempfile.TemporaryDirectory() as directory:
    path=str(Path(directory)/'local.sock')
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as server, socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
        server.bind(path);server.listen();client.connect(path)
        peer,_=server.accept()
        with peer:
            client.sendall(b'local');assert peer.recv(5)==b'local'
    observed.append('unix local')
print(json.dumps({'qualification':'ordinary libc loopback-only transport','checks':observed}))
'''


class OfflineTransportTests(unittest.TestCase):
    def test_compiled_injection_denies_external_canaries_and_preserves_local_roundtrips(self):
        self.assertEqual(sys.platform, 'linux', 'Offline transport qualification requires Linux.')
        with tempfile.TemporaryDirectory(prefix='tuldok-offline-') as directory:
            library = Path(directory) / 'offline_loopback.so'
            compile_result = subprocess.run(['cc', '-shared', '-fPIC', '-O2', '-Wall', '-Wextra', '-Werror',
                '-o', str(library), str(SOURCE), '-ldl'], capture_output=True, text=True, timeout=30)
            self.assertEqual(compile_result.returncode, 0, compile_result.stdout + compile_result.stderr)
            result = subprocess.run([sys.executable, '-c', CANARY], capture_output=True, text=True, timeout=20,
                                    env=dict(os.environ, LD_PRELOAD=str(library)))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            receipt = json.loads(result.stdout)
            self.assertEqual(len(receipt['checks']), 12)
            self.assertIn('unix local', receipt['checks'])
            self.assertIn('connect denied 192.0.2.1', receipt['checks'])
            self.assertIn('sendto denied 2001:db8::1', receipt['checks'])


if __name__ == '__main__':
    unittest.main()
