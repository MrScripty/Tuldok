"""Private original-host custody index; never part of a portable project.

Only fixed Run and producer facts are recorded. These files can fence a local
physical projection and identify its exact receipts; they never grant execution,
select a PID to signal, or restore a Run/admission from project history.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import threading
import uuid
from run_capacity import MAX_ATTEMPTS

NATIVE_PHASE_LIMIT=3*MAX_ATTEMPTS+1

import agent_api
from workbench import WorkbenchError

LIMIT = 1024 * 1024
ID = re.compile(r'^[a-f0-9]{32}$')
SHA = re.compile(r'^[a-f0-9]{64}$')
PRODUCERS = frozenset(('generation_history','grounded_history','caption_proposal_history','text_proposal_history'))
PHASES = ('admitted','launch_intent','launched','ready','go_intent','drained')
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC


def _fail(message, code='local_custody_unavailable'):
    raise WorkbenchError(message, code, 409)


def _id(value):
    if type(value) is not str or not ID.fullmatch(value):_fail('Invalid local custody identity.')
    return value


def _sha(value):
    if type(value) is not str or not SHA.fullmatch(value):_fail('Invalid local custody digest.')
    return value


def _shape(value, fields):
    if type(value) is not dict or set(value) != set(fields):_fail('Unclassified local custody fields.')


def records_sha256(records):
    return hashlib.sha256(agent_api.encoded(records)).hexdigest()


def validate(value):
    version=value.get('format') if type(value) is dict else None
    fields=('format','host_catalog_id','project_id','root_identity','projection_id',
            'project_name','selected_checkpoint','attempted','runs','producers','runtime_effects','package_effects')
    _shape(value,(*fields,*(['native_phases'] if version in ('project_local_custody_v2','project_local_custody_v3') else []),
                        *(['native_admissions'] if version=='project_local_custody_v3' else [])))
    if version not in ('project_local_custody_v1','project_local_custody_v2','project_local_custody_v3'):_fail('Unsupported local custody format.')
    for key in ('host_catalog_id','project_id','projection_id'):_id(value[key])
    if type(value['project_name']) is not str or not value['project_name'].strip() or len(value['project_name'])>200:
        _fail('Invalid retained local project name.')
    root=value['root_identity']
    if type(root) is not list or len(root)!=2 or any(type(n) is not int or n<0 for n in root):
        _fail('Invalid local project physical identity.')
    _sha(value['selected_checkpoint'])
    if value['attempted'] is not None:
        attempt=value['attempted'];_shape(attempt,('records_sha256','request_key','input_sha256'))
        _sha(attempt['records_sha256']);_sha(attempt['input_sha256'])
        if type(attempt['request_key']) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}',attempt['request_key']):
            _fail('Invalid local canonical publication request.')
    if type(value['runs']) is not list or len(value['runs'])>16:_fail('Too many unresolved local Runs.')
    seen=set()
    for run in value['runs']:
        _shape(run,('run_id','admission_id','request_sha256','spec_sha256','phase','custody_identity','receipt_sha256'))
        _id(run['run_id']);_id(run['admission_id']);_sha(run['request_sha256']);_sha(run['spec_sha256'])
        if run['run_id'] in seen or run['phase'] not in PHASES:_fail('Invalid or duplicate local Run custody.')
        seen.add(run['run_id'])
        identity=run['custody_identity']
        if identity is not None:
            _shape(identity,('attempt_id','request_sha256','spec_sha256','helper'))
            from recipe_process import valid_identity
            if (identity['attempt_id']!=run['run_id'] or identity['request_sha256']!=run['request_sha256']
                    or identity['spec_sha256']!=run['spec_sha256'] or not valid_identity(identity['helper'])):
                _fail('Local helper identity differs from its admitted specification.')
        if run['phase'] in ('launched','ready','go_intent','drained') and identity is None:
            _fail('Local launched Run requires its observed helper identity.')
        if run['receipt_sha256'] is not None:_sha(run['receipt_sha256'])
        if run['receipt_sha256'] is not None and run['phase']!='drained':_fail('Drain receipt precedes drainage.')
    if type(value['producers']) is not list or len(value['producers'])>16:_fail('Too many unresolved local producers.')
    seen=set()
    for producer in value['producers']:
        _shape(producer,('family','producer_id','admission_id','request_sha256','phase','provider_outcome','worker_drained'))
        if producer['family'] not in PRODUCERS:_fail('Unsupported local producer custody family.')
        for key in ('producer_id','admission_id'):_id(producer[key])
        _sha(producer['request_sha256'])
        identity=producer['family'],producer['producer_id']
        if identity in seen or producer['phase'] not in ('admitted','effect_intent','unknown'):
            _fail('Invalid or duplicate current producer custody.')
        seen.add(identity)
        if producer['provider_outcome'] not in ('not_admitted','unknown','result_received') or type(producer['worker_drained']) is not bool:
            _fail('Invalid current producer outcome.')
    for family,identity_field in (('runtime_effects','manifest_sha256'),('package_effects','material_sha256')):
        entries=value[family]
        if type(entries) is not list or len(entries)>8:_fail('Too many unresolved local file writers.')
        seen=set()
        for entry in entries:
            _shape(entry,('request_key','input_sha256',identity_field))
            key=entry['request_key']
            if type(key) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}',key) or key in seen:
                _fail('Invalid local file writer request.')
            seen.add(key)
            for field in ('input_sha256',identity_field):
                if entry[field] is not None:_sha(entry[field])
    native=value.get('native_phases',[])
    if type(native) is not list or len(native)>(NATIVE_PHASE_LIMIT if version=='project_local_custody_v3' else 16):_fail('Too many unresolved native phases.')
    seen=set()
    for phase in native:
        _shape(phase,('phase_id','phase','run_id','request_sha256','spec_sha256','state','helper','receipt_sha256'))
        _id(phase['phase_id']);_sha(phase['request_sha256']);_sha(phase['spec_sha256'])
        if phase['phase_id'] in seen or phase['phase'] not in ('probe','train','verify'):
            _fail('Invalid or duplicate native phase custody.')
        seen.add(phase['phase_id'])
        if phase['phase']!='probe' and phase['run_id'] is None:_fail('Native phase Run association differs.')
        if phase['run_id'] is not None:_id(phase['run_id'])
        if phase['state'] not in ('prepared','launch_intent','launched','ready','go_intent','completed','failed','unknown'):
            _fail('Unclassified native custody state.')
        from recipe_process import valid_identity
        if phase['helper'] is not None and not valid_identity(phase['helper']):_fail('Invalid native helper observation.')
        if phase['state'] in ('launched','ready','go_intent','completed') and phase['helper'] is None:
            _fail('Native launched custody lacks its actual helper identity.')
        if phase['receipt_sha256'] is not None:
            _sha(phase['receipt_sha256'])
            if phase['state'] not in ('completed','failed') or phase['helper'] is None:
                _fail('Native terminal receipt lacks exact helper drainage.')
        if phase['state']=='completed' and phase['receipt_sha256'] is None:_fail('Native completion requires drainage proof.')
    admissions=value.get('native_admissions',[])
    if type(admissions) is not list or len(admissions)>16:_fail('Too many unresolved native admissions.')
    seen=set()
    for admission in admissions:
        _shape(admission,('run_id','admission_id','request_sha256','graph_sha256','release_sha256','runtime_sha256','phase_started'))
        for key in ('run_id','admission_id'):_id(admission[key])
        for key in ('request_sha256','graph_sha256','release_sha256','runtime_sha256'):_sha(admission[key])
        if admission['run_id'] in seen or type(admission['phase_started']) is not bool:
            _fail('Invalid or duplicate native admission custody.')
        seen.add(admission['run_id'])
    return copy.deepcopy(value)


def _read(directory, name):
    try:descriptor=os.open(name,FILE_FLAGS,dir_fd=directory)
    except FileNotFoundError:return None
    except OSError:_fail('Local custody index is not an anchored ordinary file.')
    try:
        before=os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid!=os.getuid() or before.st_nlink!=1
                or before.st_mode & 0o077 or before.st_size>LIMIT):_fail('Unsafe local custody index file.')
        chunks=[];size=0
        while size<=LIMIT:
            chunk=os.read(descriptor,min(65536,LIMIT+1-size))
            if not chunk:break
            chunks.append(chunk);size+=len(chunk)
        raw=b''.join(chunks);after=os.fstat(descriptor)
        if len(raw)>LIMIT or (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(
                after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):_fail('Local custody changed while reading.')
        def pairs(items):
            result={}
            for key,item in items:
                if key in result:_fail('Duplicate local custody JSON field.')
                result[key]=item
            return result
        return validate(json.loads(raw,object_pairs_hook=pairs))
    except (OSError,UnicodeError,ValueError,RecursionError):
        _fail('Local custody index cannot be read safely.')
    finally:os.close(descriptor)


class ProjectCustody:
    """Original host's private index, using only configured control directory."""
    def __init__(self, control_path, host_catalog_id):
        self.path=Path(control_path);self.host_catalog_id=_id(host_catalog_id)
        self.lock=threading.RLock()

    def _directory(self, create=False):
        parent=os.open(self.path,DIR_FLAGS)
        try:
            if create:
                try:os.mkdir('.project-custody',0o700,dir_fd=parent);os.fsync(parent)
                except FileExistsError:pass
            try:directory=os.open('.project-custody',DIR_FLAGS,dir_fd=parent)
            except FileNotFoundError:return None
            info=os.fstat(directory)
            if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077:
                os.close(directory);_fail('Unsafe original-host custody directory.')
            return directory
        finally:os.close(parent)

    def _binding(self, store, projection_id):
        snapshot=store.snapshot()
        with store.root_directory() as descriptor:
            info=os.fstat(descriptor)
        return dict(host_catalog_id=self.host_catalog_id,project_id=snapshot['project_id'],
                    root_identity=[info.st_dev,info.st_ino],projection_id=_id(projection_id))

    @staticmethod
    def _name(binding):
        return binding['host_catalog_id']+'.'+binding['project_id']+'.'+binding['projection_id']+'.json'

    def for_projection(self, store, projection_id):
        return CustodyJournal(self,store,self._binding(store,projection_id))

    def pending(self, store):
        """Read only; no SQL owner, directory creation or worker recovery."""
        binding=self._binding(store,'0'*32);directory=self._directory()
        if directory is None:return []
        result=[]
        try:
            names=os.listdir(directory)
            if len(names)>10000:_fail('Original-host custody index requires explicit maintenance.')
            # Local custody belongs to the physical root. A different valid
            # project UUID at that same inode cannot erase an unresolved effect.
            prefix=self.host_catalog_id+'.'
            for name in sorted(names):
                if not name.startswith(prefix):continue
                if not re.fullmatch(r'[a-f0-9]{32}\.[a-f0-9]{32}\.[a-f0-9]{32}\.json',name):
                    _fail('Unclassified original-host custody index filename.')
                value=_read(directory,name)
                if value is None:continue
                if self._name(value)!=name or value['host_catalog_id']!=self.host_catalog_id:
                    _fail('Local custody filename differs from its host binding.')
                if value['root_identity']!=binding['root_identity']:continue
                if value['runs'] or value['producers'] or value['runtime_effects'] or value['package_effects'] or value.get('native_phases') or value.get('native_admissions'):
                    result.append({key:copy.deepcopy(value[key]) for key in ('host_catalog_id','project_id','root_identity','projection_id')})
            return result
        finally:os.close(directory)


class CustodyJournal:
    def __init__(self, owner, store, binding):
        self.owner,self.store,self.binding=owner,store,binding
        self.name=owner._name(binding);self.lock=threading.RLock()
        directory=owner._directory()
        try:value=_read(directory,self.name) if directory is not None else None
        finally:
            if directory is not None:os.close(directory)
        persisted=value is not None
        if value is None:
            value=dict(format='project_local_custody_v1',**binding,
                       project_name=store.snapshot()['name'],selected_checkpoint=store.snapshot()['checkpoint'],
                       attempted=None,runs=[],producers=[],runtime_effects=[],package_effects=[])
        if any(value[key]!=item for key,item in binding.items()):_fail('Original physical custody binding differs.')
        self.value=validate(value)
        self._persisted=persisted

    @property
    def has_pending(self):
        with self.lock:return bool(self.value['runs'] or self.value['producers'] or self.value['runtime_effects'] or self.value['package_effects'] or self.value.get('native_phases') or self.value.get('native_admissions'))

    def snapshot(self):
        with self.lock:return copy.deepcopy(self.value)

    def refresh(self):
        """Read this exact private binding after an uncertain journal ACK.

        This neither reads a canonical checkout nor clears an effect. The
        execution owner separately proves selection and current authority.
        """
        with self.owner.lock,self.lock:
            directory=self.owner._directory()
            try:current=_read(directory,self.name) if directory is not None else None
            finally:
                if directory is not None:os.close(directory)
            if current is None:
                if self._persisted:_fail('Original physical custody index is missing.')
                return self.snapshot()
            if any(current[key]!=value for key,value in self.binding.items()):
                _fail('Original physical custody binding changed.')
            self.value=current;self._persisted=True
            return self.snapshot()

    def _write(self, value):
        value=validate(value);raw=agent_api.encoded(value)
        if len(raw)>LIMIT:_fail('Local custody exceeds its bounded format.')
        directory=self.owner._directory(create=True);temporary='.custody-'+uuid.uuid4().hex
        try:
            descriptor=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=directory)
            try:
                os.fchmod(descriptor,0o600);view=memoryview(raw)
                while view:
                    count=os.write(descriptor,view)
                    if not count:raise OSError('Short local custody write')
                    view=view[count:]
                os.fsync(descriptor)
            finally:os.close(descriptor)
            os.replace(temporary,self.name,src_dir_fd=directory,dst_dir_fd=directory);os.fsync(directory)
            self.value=value
            self._persisted=True
        except OSError as error:
            raise WorkbenchError('Local custody publication outcome is uncertain. Execution remains fenced.','outcome_unknown',409) from error
        finally:
            try:os.unlink(temporary,dir_fd=directory)
            except OSError:pass
            os.close(directory)

    def _change(self, change):
        with self.owner.lock,self.lock:
            directory=self.owner._directory()
            try:current=_read(directory,self.name) if directory is not None else None
            finally:
                if directory is not None:os.close(directory)
            if current is not None and current!=self.value or current is None and self._persisted:
                _fail('Original-host custody changed; refuse to replace another writer.','outcome_unknown')
            value=copy.deepcopy(self.value);change(value);self._write(value)

    def expect_publication(self, before, records, key, sha):
        if not self.has_pending:return
        def change(value):
            value['selected_checkpoint']=before['checkpoint']
            value['attempted']=dict(records_sha256=records_sha256(records),request_key=key,input_sha256=sha)
        self._change(change)

    def acknowledge(self, snapshot):
        def change(value):value.update(selected_checkpoint=snapshot['checkpoint'],attempted=None)
        self._change(change)

    def validate_selection(self, snapshot):
        value=self.snapshot();attempt=value['attempted']
        if snapshot['project_id']!=value['project_id'] or snapshot['name']!=value['project_name']:
            _fail('Current canonical project differs from local custody.')
        if snapshot['checkpoint']==value['selected_checkpoint']:return
        if (attempt is not None and records_sha256(snapshot['records'])==attempt['records_sha256']
                and self.store.reconcile(attempt['request_key'],attempt['input_sha256']) is not None):return
        _fail('Canonical checkout differs from this original-host custody outcome.','stale_project')

    def observe_run(self, run, *, receipt_sha256=None):
        from recipe_process import encoded
        spec_sha=hashlib.sha256(encoded(run['spec'])).hexdigest()
        def change(value):
            old=next((item for item in value['runs'] if item['run_id']==run['id']),None)
            immutable=dict(run_id=run['id'],admission_id=run['admission_id'],request_sha256=run['request_sha256'],spec_sha256=spec_sha)
            if old is None:
                old=dict(**immutable,phase='admitted',custody_identity=None,receipt_sha256=None);value['runs'].append(old)
            if any(old[key]!=item for key,item in immutable.items()):_fail('Current Run differs from its local admission journal.')
            phase={'prepared':'admitted','barrier_ready':'ready','go_intent':'go_intent','drained':'drained'}[run['custody_phase']]
            if PHASES.index(phase)>PHASES.index(old['phase']):old['phase']=phase
            identity=run.get('custody_identity')
            if identity is not None:
                if old['custody_identity'] is not None and old['custody_identity']!=identity:_fail('Current helper identity changed.')
                old['custody_identity']=copy.deepcopy(identity)
            if receipt_sha256 is not None:old['receipt_sha256']=receipt_sha256
            value['runs'].sort(key=lambda item:item['run_id'])
        self._change(change)

    def launch_intent(self, run_id):
        def change(value):
            run=next((item for item in value['runs'] if item['run_id']==run_id),None)
            if run is None or run['phase']!='admitted':_fail('Launch requires its acknowledged current admission.')
            run['phase']='launch_intent'
        self._change(change)

    def launched(self, run_id, helper):
        from recipe_process import valid_identity
        if not valid_identity(helper):_fail('Current spawned custodian identity is unavailable.')
        def change(value):
            run=next((item for item in value['runs'] if item['run_id']==run_id),None)
            if run is None or run['phase']!='launch_intent':_fail('Custodian has no current launch intent.')
            run['phase']='launched'
            run['custody_identity']=dict(attempt_id=run_id,request_sha256=run['request_sha256'],spec_sha256=run['spec_sha256'],helper=copy.deepcopy(helper))
        self._change(change)

    def settle_run(self, run_id):
        def change(value):value['runs']=[item for item in value['runs'] if item['run_id']!=run_id]
        self._change(change)

    def observe_native_admission(self,run):
        """Original physical admission intent; never a replay/GO capability."""
        from pipeline import digest
        entry=dict(run_id=run['id'],admission_id=run['admission_id'],request_sha256=run['request_sha256'],
            graph_sha256=run['graph_sha256'],release_sha256=run['release_sha256'],runtime_sha256=digest(run['runtime']))
        def change(value):
            value['format']='project_local_custody_v3';value.setdefault('native_phases',[])
            rows=value.setdefault('native_admissions',[])
            old=next((item for item in rows if item['run_id']==run['id']),None)
            if old is None:rows.append(dict(entry,phase_started=False))
            elif any(old[key]!=item for key,item in entry.items()):_fail('Native admission differs from its original physical intent.')
            rows.sort(key=lambda row:row['run_id'])
        self._change(change)

    def settle_native_admission(self,run_id):
        def change(value):
            if any(row['run_id']==run_id for row in value.get('native_phases',[])):
                _fail('Native admission still has unresolved phase custody.')
            value['native_admissions']=[row for row in value.get('native_admissions',[]) if row['run_id']!=run_id]
        self._change(change)

    def native_prepared(self, phase):
        """Fence one acknowledged, current native phase on this physical host."""
        from recipe_process import encoded
        entry=dict(phase_id=phase['phase_id'],phase=phase['phase'],run_id=phase['run_id'],
            request_sha256=phase['request_sha256'],spec_sha256=hashlib.sha256(encoded(phase['spec'])).hexdigest(),
            state='prepared',helper=None,receipt_sha256=None)
        def change(value):
            if value['format']=='project_local_custody_v1':value['format']='project_local_custody_v2'
            value.setdefault('native_phases',[])
            if entry['run_id'] is not None:
                admission=next((row for row in value.get('native_admissions',[]) if row['run_id']==entry['run_id']),None)
                if admission is None:_fail('A current native Run phase requires its original physical admission.')
                admission['phase_started']=True
            old=next((row for row in value['native_phases'] if row['phase_id']==entry['phase_id']),None)
            if old is not None:_fail('A native phase cannot register another current launch.')
            value['native_phases'].append(entry);value['native_phases'].sort(key=lambda row:row['phase_id'])
        self._change(change)

    def native_launch_intent(self, phase_id):
        def change(value):
            row=next((row for row in value.get('native_phases',[]) if row['phase_id']==phase_id),None)
            if row is None or row['state']!='prepared':_fail('Native launch requires its current acknowledged specification.')
            row['state']='launch_intent'
        self._change(change)

    def native_launched(self, phase_id, helper):
        def change(value):
            row=next((row for row in value.get('native_phases',[]) if row['phase_id']==phase_id),None)
            if row is None or row['state']!='launch_intent':_fail('Native helper has no current launch intent.')
            row.update(state='launched',helper=copy.deepcopy(helper))
        self._change(change)

    def native_observed(self, phase):
        from recipe_process import encoded
        def change(value):
            row=next((row for row in value.get('native_phases',[]) if row['phase_id']==phase['phase_id']),None)
            if row is None:_fail('Native observation has no original local phase.')
            event=phase['events'][-1]
            if (row['request_sha256']!=phase['request_sha256'] or row['phase']!=phase['phase']
                    or row['run_id']!=phase['run_id'] or event['helper']!=row['helper']
                    or row['spec_sha256']!=hashlib.sha256(encoded(phase['spec'])).hexdigest()):
                _fail('Native observation differs from original local custody.')
            transitions={'prepared':('failed',),'launch_intent':('failed',),
                         'launched':('ready','failed','unknown'),'ready':('go_intent','failed','unknown'),
                         'go_intent':('completed','failed','unknown')}
            if event['state'] not in transitions.get(row['state'],()):
                _fail('Native custody observation cannot skip or replay its acknowledged phase.')
            row.update(state=event['state'],receipt_sha256=event['receipt_sha256'])
        self._change(change)

    def native_confirmed(self, phase_id):
        def change(value):
            row=next((row for row in value.get('native_phases',[]) if row['phase_id']==phase_id),None)
            if row is None or row['state'] not in ('completed','failed') or row['receipt_sha256'] is None:
                _fail('Native phase cannot settle without acknowledged terminal drainage.')
            value['native_phases']=[item for item in value['native_phases'] if item['phase_id']!=phase_id]
        self._change(change)

    def native_not_launched(self,phase_id):
        """Settle only the caller's proven never-entered launch boundary."""
        def change(value):
            row=next((item for item in value.get('native_phases',[]) if item['phase_id']==phase_id),None)
            if row is None or row['state']!='failed' or row['helper'] is not None or row['receipt_sha256'] is not None:
                _fail('Never-launched native settlement requires its acknowledged failed non-process fact.')
            value['native_phases']=[item for item in value['native_phases'] if item['phase_id']!=phase_id]
            if row['run_id'] is not None and not any(item['run_id']==row['run_id'] for item in value['native_phases']):
                admission=next((item for item in value.get('native_admissions',[]) if item['run_id']==row['run_id']),None)
                if admission is not None:admission['phase_started']=False
        self._change(change)

    def register_producer(self, family, producer_id, admission_id, request_digest):
        def change(value):
            item=dict(family=family,producer_id=producer_id,admission_id=admission_id,request_sha256=request_digest,
                      phase='admitted',provider_outcome='not_admitted',worker_drained=False)
            previous=next((row for row in value['producers'] if (row['family'],row['producer_id'])==(family,producer_id)),None)
            if previous is not None:
                if any(previous[key]!=item[key] for key in ('family','producer_id','admission_id','request_sha256')):_fail('Producer admission changed.')
            else:value['producers'].append(item)
        self._change(change)

    def producer_effect_intent(self, family, producer_id):
        def change(value):
            item=next((row for row in value['producers'] if (row['family'],row['producer_id'])==(family,producer_id)),None)
            if item is None:_fail('Provider request has no current admission journal.')
            item.update(phase='effect_intent',provider_outcome='unknown',worker_drained=False)
        self._change(change)

    def producer_outcome(self, family, producer_id, provider_outcome, worker_drained):
        def change(value):
            item=next((row for row in value['producers'] if (row['family'],row['producer_id'])==(family,producer_id)),None)
            if item is None:_fail('Provider result has no current admission journal.')
            item.update(provider_outcome=provider_outcome,worker_drained=worker_drained)
            if provider_outcome=='unknown':item['phase']='unknown'
            elif worker_drained:value['producers'].remove(item)
        self._change(change)

    def runtime_started(self, key, input_sha256=None, manifest_sha256=None):
        self._file_started('runtime_effects',dict(request_key=key,input_sha256=input_sha256,manifest_sha256=manifest_sha256))

    def package_started(self, key, input_sha256=None, material_sha256=None):
        self._file_started('package_effects',dict(request_key=key,input_sha256=input_sha256,material_sha256=material_sha256))

    def _file_started(self, family, entry):
        def change(value):
            previous=next((item for item in value[family] if item['request_key']==entry['request_key']),None)
            if previous is not None and previous!=entry:_fail('File writer key has different retained input.','conflict')
            if previous is None:value[family].append(entry)
        self._change(change)

    def runtime_confirmed(self, key):self._file_confirmed('runtime_effects',key)
    def package_confirmed(self, key):self._file_confirmed('package_effects',key)

    def _file_confirmed(self, family, key):
        def change(value):value[family]=[item for item in value[family] if item['request_key']!=key]
        self._change(change)
