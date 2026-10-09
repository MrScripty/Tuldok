"""Explicit trusted-SDK observations; no owner admission, acquisition or inference."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import threading
import time
from datetime import datetime, timezone
import pumas_gateway_descriptor as descriptor
import pumas_model_selection as selection

SOURCE = 'ab9890fe3248ed7c435b958cded0b131b0700a35'
SOURCE_STATUS = 'PR51 merged into PR48 draft branch; PR48 unmerged; not a v0.8 release or typed-stack integration'
MAX_REQUEST = 128 * 1024
MAX_STDOUT = 1024 * 1024
MAX_STDERR = 64 * 1024
WALL_SECONDS = 15
MAX_LIBRARIES = 32
MAX_MODELS = 64
SCOPE = 'authenticated observation at selection; no lifetime lease, owner startup, acquisition or model readiness'

def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()

def _pairs(pairs):
    value = {}
    for k,v in pairs:
        if k in value:raise ValueError('Duplicate observation field.')
        value[k] = v
    return value

def _constant(_):raise ValueError('Nonfinite observation value.')

def parse(raw):
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs, parse_constant=_constant)
        canonical(value)
        return value
    except (UnicodeError, RecursionError, OverflowError) as error:
        raise ValueError('Invalid observation encoding or nesting.') from error

def _keys(value, keys):
    if type(value) is not dict or set(value) != set(keys):raise ValueError('Unsupported local Pumas operation or fields.')

def _text(value, limit=4096):
    if type(value) is not str or not value or len(value) > limit or '\0' in value:
        raise ValueError('Invalid selected library identity.')
    value.encode('utf-8')

def _private(value):
    if type(value) is dict:
        if {'connection_token','metadata_json'} & set(value):raise ValueError('Bridge exposed private registry fields.')
        for item in value.values():_private(item)
    elif type(value) is list:
        for item in value:_private(item)

class Service:
    def __init__(self, bridge=None, registry=None, bridge_sha256=None):
        self.bridge = Path(bridge).resolve() if bridge is not None else None
        self.registry = Path(registry).resolve() if registry is not None else None
        self.bridge_sha256 = bridge_sha256
        self.secret = secrets.token_bytes(32)
        self.lock = threading.Lock()

    def _context(self, deadline=None):
        deadline = deadline if deadline is not None else time.monotonic()+WALL_SECONDS
        if self.bridge is None or self.registry is None or not isinstance(self.bridge_sha256,str) or not re.fullmatch('[a-f0-9]{64}',self.bridge_sha256):
            raise ValueError('No trusted local Pumas bridge configured. Select an installed pinned bridge and registry at application startup; automatic installation/startup is unsupported.')
        digest = hashlib.sha256()
        if not self.bridge.is_file():raise ValueError('Trusted bridge is unavailable.')
        total = 0
        with self.bridge.open('rb') as stream:
            while chunk := stream.read(65536):
                total += len(chunk)
                if total > 768*1024*1024 or time.monotonic() >= deadline:raise ValueError('Trusted bridge identity check exceeds its bounded size/time.')
                digest.update(chunk)
        if digest.hexdigest() != self.bridge_sha256:
            raise ValueError('Trusted bridge bytes changed or are unavailable; no alternate helper is started.')
        if not self.registry.is_file():raise ValueError('Selected registry is unavailable; no empty snapshot or owner startup is inferred.')
        st = self.registry.stat()
        # App-local lookup context only; never a producer/physical-library identity.
        return hashlib.sha256(canonical([str(self.registry),st.st_dev,st.st_ino])).hexdigest()

    def _retire(self, process, readers):
        """Return custody only after the child and every pipe actor retire."""
        settled = True
        try:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        except OSError:settled = False
        deadline = time.monotonic()+3
        try:process.wait(timeout=max(.001,deadline-time.monotonic()))
        except (subprocess.TimeoutExpired,OSError):settled = False
        for thread in readers:thread.join(timeout=max(0,deadline-time.monotonic()))
        if any(t.is_alive() for t in readers):return False
        if process.stdin and not process.stdin.closed:process.stdin.close()
        return settled and process.poll() is not None

    def _invoke(self, operation, selected=None, deadline=None):
        if not self.lock.acquire(blocking=False):raise ValueError('A local Pumas observation is running. Wait for it to finish.')
        process = None
        readers = []
        try:
            deadline = deadline if deadline is not None else time.monotonic()+WALL_SECONDS
            context = self._context(deadline)
            request = canonical({'operation':operation,'registry':str(self.registry),'selected':selected})
            if len(request) > 16384:raise ValueError('Selected bridge request exceeds16KiB.')
            process = subprocess.Popen([str(self.bridge)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, start_new_session=True)
            output = [bytearray(),bytearray()]
            exceeded = threading.Event()
            def read(index, stream, limit):
                try:
                    while True:
                        chunk = stream.read1(8192)
                        if not chunk:break
                        if len(output[index])+len(chunk) > limit:
                            exceeded.set();break
                        output[index].extend(chunk)
                finally:stream.close()
            for i,(stream,limit) in enumerate([(process.stdout,MAX_STDOUT),(process.stderr,MAX_STDERR)]):
                thread = threading.Thread(target=read,args=(i,stream,limit),daemon=True)
                thread.start();readers.append(thread)
            write_failed = threading.Event()
            def write():
                try:process.stdin.write(request);process.stdin.close()
                except OSError:write_failed.set()
            writer = threading.Thread(target=write,daemon=True)
            writer.start();readers.append(writer)
            while process.poll() is None or any(t.is_alive() for t in readers):
                if exceeded.is_set():raise ValueError('Local Pumas bridge exceeded its bounded output; attachment remains unresolved.')
                if time.monotonic() >= deadline:raise ValueError('Local Pumas observation timed out; attachment remains unresolved. No owner is started.')
                time.sleep(.005)
            if exceeded.is_set():raise ValueError('Local Pumas bridge exceeded its bounded output.')
            if write_failed.is_set():raise ValueError('Local Pumas bridge did not accept the selected observation.')
            if process.returncode != 0:raise ValueError('Selected Pumas library could not be observed/authenticated; no owner startup, takeover or acquisition fallback.')
            if context != self._context(deadline):raise ValueError('Configured registry context changed during observation.')
            value = parse(bytes(output[0]))
            _keys(value,('bridge_schema','producer_commit','operation','data'))
            if type(value['bridge_schema']) is not int or value['bridge_schema'] != 1 or value['producer_commit'] != SOURCE or value['operation'] != operation:
                raise ValueError('Unsupported bridge/producer source contract.')
            _private(value)
            return value['data'],context
        except (BrokenPipeError, OSError) as error:
            raise ValueError('Trusted local Pumas bridge is unavailable; no fallback or owner startup.') from error
        finally:
            if process is not None:
                # Unresolved custody retains the slot and reports a typed refusal.
                if not self._retire(process,readers):
                    raise ValueError('Local Pumas cleanup custody unresolved; observation slot retained. No replacement owner or fallback.')
            self.lock.release()

    def libraries(self, body):
        _keys(body,())
        data,context = self._invoke('list')
        _keys(data,('registered_libraries','tracked_instances','local_models'))
        for name in data:
            if type(data[name]) is not list or len(data[name]) > MAX_LIBRARIES:raise ValueError('Local library observations exceed32contexts.')
        identities = {}
        for row in data['registered_libraries']:
            _keys(row,('id','name','root','version'));_text(row['id'],128);_text(row['root']);_text(row['name'])
            if not Path(row['root']).is_absolute() or row['id'] in identities or row['root'] in identities.values():raise ValueError('Ambiguous registered library context.')
            identities[row['id']] = row['root']
        for row in data['tracked_instances']:
            _keys(row,('root','generation','status'));_text(row['root']);_text(row['generation'],128)
            if row['status'] not in ('claiming','ready'):raise ValueError('Unsupported tracked owner state.')
        seen = set()
        for row in data['local_models']:
            if type(row) is not dict or row.get('registry_library_id') not in identities or identities[row['registry_library_id']] != row.get('library_root') or row['registry_library_id'] in seen:
                raise ValueError('Local model context changed or is ambiguous.')
            seen.add(row['registry_library_id'])
            if row.get('observation') == 'unavailable':_keys(row,('observation','registry_library_id','library_root'))
            elif row.get('observation') == 'snapshot':
                _keys(row,('observation','registry_library_id','library_root','snapshot'))
                snap = row['snapshot']
                if (type(snap) is not dict or type(snap.get('rows',[])) is not list
                        or type(snap.get('total_count')) is not int or not 0 <= snap['total_count'] <= MAX_MODELS
                        or snap['total_count'] != len(snap.get('rows',[]))):
                    raise ValueError('Local model snapshot exceeds64rows per library or is incomplete/inconsistent; pagination is unsupported.')
            else:raise ValueError('Unsupported local model observation.')
        if seen != set(identities):raise ValueError('Incomplete library model observations.')
        return dict(data,registry_context=context,producer_commit=SOURCE,producer_status=SOURCE_STATUS,
                    scope='read-only registry/local-index observations; tracked rows and model references do not prove live readiness',
                    observed_sha256=hashlib.sha256(canonical(data)).hexdigest())

    def _observe(self, selected, deadline=None):
        _keys(selected,('id','root'));_text(selected['id'],128);_text(selected['root'])
        if not Path(selected['root']).is_absolute():raise ValueError('Select an exact registered library root.')
        data,context = self._invoke('borrow',selected,deadline)
        _keys(data,('service',))
        service = descriptor.decode(canonical(data['service']))['advertisement']
        if service['instance']['registry_library_id'] != selected['id'] or service['instance']['library_root'] != selected['root']:
            raise ValueError('Authenticated selected library changed.')
        observation = {'schema':1,'producer_commit':SOURCE,'producer_status':SOURCE_STATUS,'bridge_sha256':self.bridge_sha256,
                       'registry_context':context,'selected':selected,'service':service,'scope':SCOPE,
                       'authenticated_at':datetime.now(timezone.utc).isoformat()}
        raw = canonical(observation)
        return {'observation':observation,'proof':hmac.new(self.secret,raw,hashlib.sha256).hexdigest(),
                'observation_sha256':hashlib.sha256(raw).hexdigest(),'server_url':descriptor.endpoint(service['endpoint'])}

    def observe(self, body):
        _keys(body,('selected',))
        return self._observe(body['selected'])

    def use(self, body):
        _keys(body,('receipt','protocol'))
        if body['protocol'] != 'legacy':raise ValueError('Authenticated discovery and typed-v1 are separate producer stacks; typed composition is unsupported here. Choose the compatible API explicitly.')
        return self._fresh(body['receipt'],time.monotonic()+WALL_SECONDS)

    def _fresh(self, receipt, deadline):
        _keys(receipt,('observation','proof','observation_sha256','server_url'))
        raw = canonical(receipt['observation'])
        if type(receipt['proof']) is not str or not hmac.compare_digest(hmac.new(self.secret,raw,hashlib.sha256).hexdigest(),receipt['proof']):
            raise ValueError('Observation receipt changed or belongs to another application lifetime. Authenticate again.')
        observation = receipt['observation']
        if observation['registry_context'] != self._context(deadline) or observation['producer_commit'] != SOURCE or observation['bridge_sha256'] != self.bridge_sha256:
            raise ValueError('Observation registry/source context changed.')
        if receipt['observation_sha256'] != hashlib.sha256(raw).hexdigest() or receipt['server_url'] != descriptor.endpoint(observation['service']['endpoint']):
            raise ValueError('Observation receipt association changed.')
        fresh = self._observe(observation['selected'],deadline)
        if fresh['observation']['service'] != observation['service'] or fresh['observation']['registry_context'] != observation['registry_context']:
            raise ValueError('Selected core/HTTP owner observation changed. List/authenticate again; no fallback.')
        return fresh

    def typed_models(self, body):
        _keys(body,('receipt',))
        deadline=time.monotonic()+WALL_SECONDS
        before=self._fresh(body['receipt'],deadline)
        result=selection.catalog(before['server_url'],deadline)
        after=self._fresh(before,deadline)
        return self._typed_inspection(after,result,'catalog')

    def typed_selection(self, body):
        _keys(body,('receipt','model','profile','purpose'))
        deadline=time.monotonic()+WALL_SECONDS
        before=self._fresh(body['receipt'],deadline)
        result=selection.selection(dict(server_url=before['server_url'],model=body['model'],profile=body['profile'],purpose=body['purpose']),deadline)
        after=self._fresh(before,deadline)
        return self._typed_inspection(after,result,'capability')

    def _typed_inspection(self, receipt, result, kind):
        return {'receipt':receipt,'inspection':result,'kind':kind,'discovery_contract_source':SOURCE,
                'typed_contract_source':selection.typed.SOURCE_COMMIT,'inference_admitted':False,
                'configuration_apply_supported':False,'joint_producer_qualified':False,
                'scope':'Bracketed authenticated owner/capability observations only. Separate public producer stacks have no qualified joint owner or typed admission generation condition; owner-bound configuration/inference disabled.'}
