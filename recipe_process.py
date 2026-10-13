"""Linux per-attempt child custody. Runs owns admission, scheduling and publication.

Trusted reviewed recipes share the local UID. Subreaping is lifecycle ownership,
not filesystem/network confinement. A missing drain receipt never proves cessation.
"""
import base64
import ctypes
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import selectors
import signal
import socket
import stat
import subprocess
import time

READY_SECONDS = 10
GRACE_SECONDS = 3
CLEANUP_SECONDS = 10
STREAM_LIMIT = 1024 * 1024
OUTPUT_LIMIT = 64 * 1024 * 1024
SPEC_LIMIT = 4 * 1024 * 1024
SOURCE = Path(__file__).read_bytes()
HASH = re.compile(r'^[a-f0-9]{64}$')
ID = re.compile(r'^[a-f0-9]{32}$')
# Linux UAPI values: some supported Python builds omit the symbolic constants.
F_ADD_SEALS = getattr(fcntl, 'F_ADD_SEALS', 1033)
IMMUTABLE_SEALS = 0x0001 | 0x0002 | 0x0004 | 0x0008


class ProcessError(ValueError):
    def __init__(self, message, code='invalid'):
        super().__init__(message)
        self.code = code


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate key')
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ProcessError('Invalid custody JSON.') from error


def text(value, maximum=4096):
    return type(value) is str and 0 < len(value) <= maximum and not any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in value)


def absolute(value):
    return text(value) and Path(value).is_absolute() and '..' not in Path(value).parts


def validate_spec(value):
    keys = {'schema_version','attempt_id','request_sha256','argv','env','cwd','stdin_base64',
            'wall_seconds','executable_sha256','max_output_bytes','output_dir','captured_files','runtime_files','trusted_install_owner_uid'}
    if type(value) is not dict or set(value) != keys or type(value['schema_version']) is not int or value['schema_version'] != 1:
        raise ProcessError('Unsupported custody spec.')
    if not isinstance(value['attempt_id'], str) or not ID.fullmatch(value['attempt_id']):
        raise ProcessError('Invalid attempt identity.')
    for key in ('request_sha256','executable_sha256'):
        if type(value[key]) is not str or not HASH.fullmatch(value[key]):
            raise ProcessError('Invalid custody hash.')
    argv, env = value['argv'], value['env']
    if type(argv) is not list or not 1 <= len(argv) <= 64 or not all(text(arg) for arg in argv) or not absolute(argv[0]):
        raise ProcessError('Invalid captured argument vector.')
    if type(env) is not dict or len(env) > 32 or any(not re.fullmatch('[A-Z_][A-Z0-9_]{0,63}', key) or type(val) is not str or len(val) > 4096 or '\0' in val for key,val in env.items()):
        raise ProcessError('Invalid explicit environment.')
    if not absolute(value['cwd']) or not absolute(value['output_dir']):
        raise ProcessError('Captured working/output directories must be absolute.')
    if type(value['wall_seconds']) is not int or not 1 <= value['wall_seconds'] <= 600:
        raise ProcessError('Wall budget must be 1 through 600 seconds.')
    if type(value['max_output_bytes']) is not int or not 1 <= value['max_output_bytes'] <= OUTPUT_LIMIT:
        raise ProcessError('Invalid output byte budget.')
    try:
        if type(value['stdin_base64']) is not str or len(value['stdin_base64']) > 87384:
            raise ValueError()
        if len(base64.b64decode(value['stdin_base64'], validate=True)) > 65536:
            raise ValueError()
    except ValueError as error:
        raise ProcessError('Stdin exceeds its 64 KiB bound or is invalid base64.') from error
    if type(value['trusted_install_owner_uid']) is not int or value['trusted_install_owner_uid'] == os.getuid() or value['trusted_install_owner_uid'] < 0:
        raise ProcessError('Runtime owner must be an explicitly distinct trusted installation identity.')
    runtime = value['runtime_files']
    if type(runtime) is not list or len(runtime)>10000:
        raise ProcessError('Invalid runtime inventory.')
    files = value['captured_files']
    if type(files) is not list or len(files) > 128:
        raise ProcessError('Invalid captured file inventory.')
    seen = set()
    for item in files+runtime:
        if type(item) is not dict or set(item) != {'path','sha256','bytes'} or not absolute(item['path']):
            raise ProcessError('Invalid captured file reference.')
        if item['path'] in seen or type(item['sha256']) is not str or not HASH.fullmatch(item['sha256']):
            raise ProcessError('Duplicate capture or invalid hash.')
        seen.add(item['path'])
        if type(item['bytes']) is not int or not 0 <= item['bytes'] <= OUTPUT_LIMIT:
            raise ProcessError('Invalid captured file size.')
    if sum(item['bytes'] for item in files)>64*1024*1024 or sum(item['bytes'] for item in runtime)>512*1024*1024:
        raise ProcessError('Runtime/source closure exceeds its byte bound.')
    if len(encoded(value)) > SPEC_LIMIT:
        raise ProcessError('Custody specification exceeds its bound.')
    return decode(encoded(value))


def read_regular(path, maximum):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
            raise ProcessError('Expected a bounded regular captured file.', 'unavailable')
        raw = handle.read(maximum + 1)
        after = os.fstat(handle.fileno())
        if len(raw) > maximum or (before.st_size,before.st_mtime_ns,before.st_ctime_ns) != (after.st_size,after.st_mtime_ns,after.st_ctime_ns):
            raise ProcessError('Captured file changed during observation.', 'stale')
        return raw


def verify_captures(spec):
    for item in spec['captured_files']+spec['runtime_files']:
        raw = read_regular(item['path'], item['bytes'])
        if len(raw) != item['bytes'] or digest(raw) != item['sha256']:
            raise ProcessError('Captured input/source identity changed.', 'stale')


def identity(pid):
    fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
    return {'pid':pid, 'start_ticks':fields[19], 'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip()}


def valid_identity(value):
    return (type(value) is dict and set(value)=={'pid','start_ticks','boot_id'} and
            type(value['pid']) is int and value['pid']>0 and type(value['start_ticks']) is str and value['start_ticks'].isdigit() and
            type(value['boot_id']) is str and re.fullmatch('[a-f0-9-]{36}',value['boot_id']) is not None)


def sealed(name, raw):
    fd = os.memfd_create(name, os.MFD_ALLOW_SEALING)
    try:
        with os.fdopen(os.dup(fd), 'wb') as handle:
            handle.write(raw); handle.flush()
        os.lseek(fd, 0, os.SEEK_SET)
        fcntl.fcntl(fd, F_ADD_SEALS, IMMUTABLE_SEALS)
        return fd
    except BaseException:
        os.close(fd)
        raise


def _trusted_python(owner_uid):
    path = Path('/usr/bin/python3').resolve(strict=True)
    if '/usr' not in str(path) or not str(path).startswith('/usr/'):
        raise ProcessError('Trusted system Python is unavailable.', 'unavailable')
    for item in (path,*path.parents):
        info = item.stat()
        if info.st_uid != owner_uid or info.st_mode & 0o022 or os.access(item,os.W_OK):
            raise ProcessError('System Python installation is writable.', 'unavailable')
    return str(path)


def _packet(channel, value):
    raw = encoded(value)
    if len(raw) > 4096:
        raise ProcessError('Custodian message exceeds its bound.')
    channel.send(raw)


def _receive(channel):
    raw, _ancillary, flags, _address = channel.recvmsg(4096)
    if not raw:
        return None
    if flags & socket.MSG_TRUNC:
        raise ProcessError('Truncated custodian message.')
    return decode(raw)


class Handle:
    def __init__(self, process, channel, spec, directory):
        self.process, self.channel, self.spec, self.directory = process, channel, spec, directory
        self.ready = None
        self.sent_go = self.terminal = self.lost = self.sent_cancel = False
        self.started = time.monotonic()
        self.spec_sha256 = digest(encoded(spec))

    @property
    def expected_identity(self):
        return {'attempt_id':self.spec['attempt_id'],'request_sha256':self.spec['request_sha256'],
                'spec_sha256':self.spec_sha256,'helper':self.ready}

    def poll(self):
        events = []
        if self.channel is None:
            if not self.terminal and not self.lost:
                self.lost = True
                events.append({'type':'lost','reason':'custodian_channel_closed'})
            return events
        while True:
            try:
                event = _receive(self.channel)
            except BlockingIOError:
                break
            except (OSError, ProcessError):
                event = None
            if event is None:
                if not self.terminal and not self.lost:
                    self.lost = True
                    events.append({'type':'lost','reason':'custodian_channel_closed'})
                self.close_control(wait=False)
                break
            common = {'schema_version':1,'attempt_id':self.spec['attempt_id'],'request_sha256':self.spec['request_sha256'],'spec_sha256':self.spec_sha256}
            kind = event.get('type') if type(event) is dict else None
            fields = {'ready':{'helper'},'started':{'leader'},'terminal':{'receipt_sha256','drained','outcome'}}
            if kind not in fields or set(event) != set(common)|{'type'}|fields[kind] or any(event[key] != val for key,val in common.items()):
                self.cancel('protocol_error'); raise ProcessError('Invalid custodian event.')
            if kind == 'ready':
                if self.ready is not None or not valid_identity(event['helper']) or event['helper'] != identity(self.process.pid):
                    self.cancel('protocol_error'); raise ProcessError('Invalid custodian READY identity.')
                self.ready = event['helper']
            elif kind == 'started':
                if not self.sent_go or not valid_identity(event['leader']):
                    self.cancel('protocol_error'); raise ProcessError('Invalid recipe STARTED identity.')
            else:
                receipt = load_receipt(self.directory/'receipt.json', self.expected_identity)
                if digest(encoded(receipt)) != event['receipt_sha256'] or receipt['drained'] != event['drained'] or receipt['outcome'] != event['outcome']:
                    raise ProcessError('Terminal receipt differs from custodian event.')
                self.terminal = True
            events.append(event)
        if self.ready is None and not self.lost and time.monotonic()-self.started > READY_SECONDS:
            self.close_control(wait=False)
            raise ProcessError('Custodian readiness deadline exceeded.', 'unavailable')
        self.process.poll()
        return events

    def go(self, expected_ready_identity):
        if self.ready is None or expected_ready_identity != self.ready or self.sent_go or self.terminal or self.channel is None:
            raise ProcessError('GO requires the exact READY identity once.')
        _packet(self.channel, {'type':'go','attempt_id':self.spec['attempt_id'],'request_sha256':self.spec['request_sha256'],'helper':self.ready})
        self.sent_go = True

    def cancel(self, reason='cancelled'):
        if reason not in ('cancelled','shutdown','protocol_error'):
            raise ProcessError('Unsupported cancellation reason.')
        if self.channel is not None and not self.sent_cancel:
            self.sent_cancel = True
            try: _packet(self.channel, {'type':'cancel','reason':reason})
            except (OSError, ProcessError): self.close_control(wait=False)

    def close_control(self, *, wait=True):
        if self.channel is not None:
            self.channel.close(); self.channel = None
        if not wait:
            return None
        try:
            self.process.wait(timeout=CLEANUP_SECONDS + 2)
        except subprocess.TimeoutExpired as error:
            raise ProcessError('Custodian did not finish drainage within its cleanup budget.', 'unknown') from error
        if self.ready is None:
            return {'drained':False,'outcome':'unknown','reason':'no_ready_identity'}
        try:
            return load_receipt(self.directory/'receipt.json',self.expected_identity)
        except (OSError,ProcessError):
            return {'drained':False,'outcome':'unknown','reason':'missing_drain_receipt'}


def launch(spec, custody_dir):
    spec = validate_spec(spec)
    verify_captures(spec)
    executable = read_regular(spec['argv'][0], 128*1024*1024)
    if digest(executable) != spec['executable_sha256']:
        raise ProcessError('Executable identity changed.', 'stale')
    directory = Path(custody_dir)
    directory.mkdir(mode=0o700, parents=False, exist_ok=False)
    parent = child = None
    descriptors = []
    try:
        parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        for name, raw in (('tuldok-custodian',SOURCE),('tuldok-spec',encoded(spec)),('tuldok-executable',executable)):
            descriptors.append(sealed(name,raw))
        directory_fd = os.open(directory, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        descriptors.append(directory_fd)
        command = [_trusted_python(spec['trusted_install_owner_uid']),'-I','-B',f'/proc/self/fd/{descriptors[0]}','--helper',str(child.fileno()),*(str(fd) for fd in descriptors[1:])]
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
            pass_fds=(child.fileno(),*descriptors),close_fds=True,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'})
        parent.setblocking(False)
        return Handle(process,parent,spec,directory)
    except BaseException:
        if parent is not None: parent.close()
        raise
    finally:
        if child is not None: child.close()
        for fd in descriptors: os.close(fd)


def load_receipt(path, expected_identity):
    if type(expected_identity) is not dict or set(expected_identity) != {'attempt_id','request_sha256','spec_sha256','helper'} or not valid_identity(expected_identity['helper']):
        raise ProcessError('An exact READY identity is required to read a receipt.')
    raw = read_regular(path,16384)
    value = decode(raw)
    fields = {'schema_version','attempt_id','request_sha256','spec_sha256','helper','go_received','spawn_closed',
              'drained','echild','outcome','reason','leader_returncode','streams'}
    if type(value) is not dict or set(value)!=fields or type(value['schema_version']) is not int or value['schema_version']!=1 or any(value.get(k)!=v for k,v in expected_identity.items()):
        raise ProcessError('Invalid retained custody receipt.')
    if not valid_identity(value['helper']) or any(type(value[k]) is not bool for k in ('go_received','spawn_closed','drained','echild')):
        raise ProcessError('Invalid receipt custody evidence.')
    if not value['spawn_closed'] or value['drained'] != value['echild'] or value['outcome'] not in ('completed','failed','cancelled','unknown'):
        raise ProcessError('Receipt cannot establish its claimed drainage.')
    if not value['drained'] and value['outcome']!='unknown':
        raise ProcessError('Unconfirmed drainage must remain unknown.')
    if value['leader_returncode'] is not None and type(value['leader_returncode']) is not int:
        raise ProcessError('Invalid leader exit status.')
    if value['outcome']=='completed' and (not value['go_received'] or value['leader_returncode']!=0):
        raise ProcessError('Completion requires successful execution.')
    if not text(value['reason'],100) or type(value['streams']) is not dict or set(value['streams'])!={'stdout','stderr'}:
        raise ProcessError('Invalid retained diagnostics.')
    for row in value['streams'].values():
        if type(row) is not dict or set(row)!={'bytes','sha256'} or type(row['bytes']) is not int or not 0<=row['bytes']<=STREAM_LIMIT or type(row['sha256']) is not str or not HASH.fullmatch(row['sha256']):
            raise ProcessError('Invalid stream receipt.')
    return value


def _children():
    # /proc/.../children is not exposed on every supported host. PPID is the
    # admitted canonical observation; ECHILD, never this scan, proves drainage.
    result = []
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        try:
            fields = (path/'stat').read_text().rsplit(')',1)[1].split()
            if int(fields[1]) == os.getpid():
                result.append(int(path.name))
        except FileNotFoundError:
            continue
        if len(result)>4096:
            raise ProcessError('Child inventory exceeds custody bound.', 'unknown')
    return result


def _signal_children(number):
    for pid in _children():
        try:
            fd = os.pidfd_open(pid)
            try: signal.pidfd_send_signal(fd,number)
            finally: os.close(fd)
        except ProcessLookupError:
            pass


def _outputs(spec):
    root=Path(spec['output_dir']); total=count=0
    if root.is_symlink() or not root.is_dir():
        raise ProcessError('Output directory changed.')
    for path in root.iterdir():
        info=path.lstat();count+=1;total+=info.st_size
        if count>128 or not stat.S_ISREG(info.st_mode) or total>spec['max_output_bytes']:
            raise ProcessError('Output inventory exceeded its admitted bound.')


def _helper(control_fd,spec_fd,exe_fd,directory_fd):
    channel=socket.socket(fileno=control_fd);channel.setblocking(False)
    spec=validate_spec(decode(os.pread(spec_fd,SPEC_LIMIT+1,0)))
    libc=ctypes.CDLL(None,use_errno=True)
    if libc.prctl(36,1,0,0,0): raise OSError(ctypes.get_errno(),'subreaper unavailable')
    who=identity(os.getpid());common={'schema_version':1,'attempt_id':spec['attempt_id'],'request_sha256':spec['request_sha256'],'spec_sha256':digest(encoded(spec))}
    logs={};hashes={name:hashlib.sha256() for name in ('stdout','stderr')};sizes={name:0 for name in hashes}
    for name in hashes: logs[name]=os.open(name+'.log',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600,dir_fd=directory_fd)
    selector=selectors.DefaultSelector();selector.register(channel,selectors.EVENT_READ,'control')
    leader=None;code=None;go=False;stopping=None;reason='not_started';drained=False
    started=time.monotonic();deadline=started+READY_SECONDS
    def stop(why):
        nonlocal stopping,reason
        if stopping is None: stopping=time.monotonic();reason=why
    try:
        verify_captures(spec)
        _packet(channel,dict(common,type='ready',helper=who))
        while True:
            now=time.monotonic()
            if stopping is None and now>=deadline:stop('wall_timeout' if go else 'ready_timeout')
            if go and stopping is None:
                try:_outputs(spec)
                except (OSError,ProcessError):stop('output_limit')
            if stopping is not None:
                try:_signal_children(signal.SIGKILL if now-stopping>=GRACE_SECONDS else signal.SIGTERM)
                except (OSError,ProcessError):reason='child_observation_failed';break
            for _ in range(256):
                try:
                    pid,status=os.waitpid(-1,os.WNOHANG)
                except ChildProcessError:
                    if stopping is not None or go:drained=True
                    break
                if pid==0:break
                if pid==leader:code=os.waitstatus_to_exitcode(status)
            if go and code is not None and stopping is None:stop('exited' if code==0 else 'nonzero_exit')
            streams_open=any(key.data!='control' for key in selector.get_map().values())
            if drained and not streams_open:break
            if stopping is not None and now-stopping>=CLEANUP_SECONDS:
                if streams_open:drained=False;reason='stream_cessation_unknown'
                break
            for key,_mask in selector.select(.05):
                if key.data=='control':
                    try:message=_receive(channel)
                    except (OSError,ProcessError):message=None
                    if message is None:
                        selector.unregister(channel);stop('controller_lost');continue
                    if type(message) is dict and set(message)=={'type','reason'} and message['type']=='cancel' and message['reason'] in ('cancelled','shutdown','protocol_error'):
                        stop(message['reason']);continue
                    expected={'type':'go','attempt_id':spec['attempt_id'],'request_sha256':spec['request_sha256'],'helper':who}
                    if message!=expected or go or stopping is not None:stop('protocol_error');continue
                    verify_captures(spec)
                    go=True;deadline=time.monotonic()+spec['wall_seconds']
                    input_fd=sealed('tuldok-stdin',base64.b64decode(spec['stdin_base64']))
                    pipes={name:os.pipe() for name in hashes}
                    leader=os.fork()
                    if leader==0:
                        try:
                            os.setsid();os.chdir(spec['cwd'])
                            os.dup2(input_fd,0);os.dup2(pipes['stdout'][1],1);os.dup2(pipes['stderr'][1],2)
                            for entry in os.listdir('/proc/self/fd'):
                                fd=int(entry)
                                if fd>2 and fd!=exe_fd:
                                    try:os.close(fd)
                                    except OSError:pass
                            resource.setrlimit(resource.RLIMIT_FSIZE,(spec['max_output_bytes'],spec['max_output_bytes']))
                            os.execve(exe_fd,spec['argv'],spec['env'])
                        except BaseException:os._exit(126)
                    os.close(input_fd)
                    for name,(read_fd,write_fd) in pipes.items():
                        os.close(write_fd);os.set_blocking(read_fd,False);selector.register(read_fd,selectors.EVENT_READ,name)
                    _packet(channel,dict(common,type='started',leader=identity(leader)))
                else:
                    data=os.read(key.fd,65536)
                    if not data:selector.unregister(key.fd);os.close(key.fd);continue
                    name=key.data;kept=data[:max(0,STREAM_LIMIT-sizes[name])]
                    pending=memoryview(kept)
                    while pending:
                        written=os.write(logs[name],pending)
                        if not written:raise OSError('Diagnostic write made no progress')
                        pending=pending[written:]
                    hashes[name].update(kept);sizes[name]+=len(kept)
                    if len(kept)!=len(data):stop('stream_limit')
    except BaseException:
        stop('custodian_error')
        deadline=time.monotonic()+CLEANUP_SECONDS
        while time.monotonic()<deadline:
            try:
                _signal_children(signal.SIGKILL)
                for _ in range(256):
                    if not os.waitpid(-1,os.WNOHANG)[0]:break
            except ChildProcessError:drained=True;break
            except (OSError,ProcessError):break
            time.sleep(.02)
    finally:
        for key in list(selector.get_map().values()):
            if key.data!='control':
                try:os.close(key.fd)
                except OSError:pass
        selector.close()
    outcome='unknown' if not drained else 'completed' if go and code==0 and reason=='exited' else 'cancelled' if reason in ('cancelled','shutdown','controller_lost') else 'failed'
    receipt=dict(common,helper=who,go_received=go,spawn_closed=True,drained=drained,echild=drained,outcome=outcome,reason=reason,
        leader_returncode=code,streams={name:{'bytes':sizes[name],'sha256':hashes[name].hexdigest()} for name in hashes})
    for fd in logs.values():os.fsync(fd);os.close(fd)
    fd=os.open('receipt.tmp',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600,dir_fd=directory_fd)
    with os.fdopen(fd,'wb') as handle:handle.write(encoded(receipt));handle.flush();os.fsync(handle.fileno())
    os.rename('receipt.tmp','receipt.json',src_dir_fd=directory_fd,dst_dir_fd=directory_fd);os.fsync(directory_fd)
    try:_packet(channel,dict(common,type='terminal',receipt_sha256=digest(encoded(receipt)),drained=drained,outcome=outcome))
    except OSError:pass
    channel.close()


if __name__=='__main__':
    import sys
    if len(sys.argv)!=6 or sys.argv[1]!='--helper':raise SystemExit(2)
    _helper(*(int(value) for value in sys.argv[2:]))
