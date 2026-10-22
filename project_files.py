"""Project-owned scripts and notes: inert working files, explicit adoption.

Captured UTF-8 text is immutable checkpoint history. Inspecting a working tree
never rewrites it, restores a missing file, executes a script, or installs tools.
"""
import copy
from datetime import datetime
import errno
import hashlib
import os
import stat

from project_store import DIR_FLAGS
from workbench import WorkbenchError, timestamp

FAMILY='project_file'
FORMAT='project_file_v1'
MAX_FILE_BYTES=1024*1024
MAX_FILES=1000
KINDS={'script':'scripts','note':'notes'}
VERSION_FIELDS={'revision','sha256','bytes','text','adopted_at','actor_id'}
RESULT_FIELDS={'id','project_id','kind','path','revision','sha256','bytes','adopted_at','changed'}


def fail(message,code='invalid',status=400):
    raise WorkbenchError(message,code,status)


def closed(value,fields,label):
    if type(value) is not dict or set(value)!=fields:fail('Invalid '+label+' fields.')


def digest(raw):return hashlib.sha256(raw).hexdigest()


def sha(value):
    if type(value) is not str or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):fail('Invalid working-file digest.')


def _path(kind,path):
    if type(kind) is not str or kind not in KINDS or type(path) is not str or len(path)>512 or '\\' in path or any(ord(c)<32 for c in path):
        fail('Choose a bounded relative script or note path.')
    try:path.encode('utf-8')
    except UnicodeEncodeError:fail('Working-file path must be strict UTF-8.')
    parts=path.split('/')
    if not 2<=len(parts)<=16 or parts[0]!=KINDS[kind] or any(part in ('','.','..') or len(part.encode('utf-8'))>255 for part in parts):
        fail('Working-file path must remain inside its scripts or notes root.')
    return parts


def _project_id(value):
    if type(value) is not str or len(value)!=32 or any(c not in '0123456789abcdef' for c in value):fail('Invalid working-file project identity.')


def file_id(project_id,kind,path):
    _project_id(project_id)
    _path(kind,path)
    return digest((project_id+'\0'+kind+'\0'+path).encode('utf-8'))


def _date(value):
    try:
        if type(value) is not str or len(value)>80:raise ValueError()
        parsed=datetime.fromisoformat(value)
        if parsed.utcoffset() is None:raise ValueError()
        return parsed
    except (ValueError,TypeError):fail('Invalid adoption timestamp.')


def _version(value):
    closed(value,VERSION_FIELDS,'adopted working-file revision')
    if type(value['revision']) is not int or not 1<=value['revision']<=2**53-1:fail('Invalid adoption revision.')
    if type(value['text']) is not str:fail('Adopted source must be UTF-8 text.')
    try:raw=value['text'].encode('utf-8')
    except UnicodeEncodeError:fail('Adopted source must be strict UTF-8.')
    sha(value['sha256'])
    if type(value['bytes']) is not int or value['bytes']!=len(raw) or len(raw)>MAX_FILE_BYTES or digest(raw)!=value['sha256']:
        fail('Adopted text bytes differ from their exact identity.')
    if type(value['actor_id']) is not str or len(value['actor_id'])!=32 or any(c not in '0123456789abcdef' for c in value['actor_id']):fail('Invalid historical adoption actor.')
    _date(value['adopted_at'])


def decode_records(records):
    if type(records) is not list:fail('Working-file inventory must be a list.')
    owned=[];seen=set()
    for envelope in records:
        if type(envelope) is not dict:fail('Invalid working-file envelope.')
        if envelope.get('family')!=FAMILY:continue
        closed(envelope,{'family','id','document'},'working-file envelope')
        doc=envelope['document']
        if type(doc) is not dict or doc.get('format')!=FORMAT:fail('Unsupported working-file format.','unsupported',409)
        closed(doc,{'format','project_id','kind','path','current','history','origin'},'working-file document')
        expected=file_id(doc['project_id'],doc['kind'],doc['path'])
        if envelope['id']!=expected or expected in seen:fail('Duplicate or mismatched working-file identity.')
        seen.add(expected)
        if type(doc['history']) is not list or not doc['history']:fail('Working-file history is missing.')
        previous=None
        for revision,value in enumerate(doc['history'],1):
            _version(value)
            if value['revision']!=revision or previous is not None and _date(value['adopted_at'])<previous:fail('Working-file history revisions or time differ.')
            previous=_date(value['adopted_at'])
        if doc['current']!=doc['history'][-1]:fail('Working-file current revision differs from its history.')
        owned.append(copy.deepcopy(envelope))
    counts={}
    for envelope in owned:
        project=envelope['document']['project_id'];counts[project]=counts.get(project,0)+1
    if any(count>MAX_FILES for count in counts.values()):fail('Project tracks more than 1,000 working files.','too_large',413)
    _validate_forks(owned,records)
    return owned


def _result(envelope,changed):
    doc=envelope['document'];value=doc['current']
    return dict(id=envelope['id'],project_id=doc['project_id'],kind=doc['kind'],path=doc['path'],changed=changed,
                **{key:value[key] for key in ('revision','sha256','bytes','adopted_at')})


def validate_operation_result(operation,result,records=None):
    if operation!='files.adopt':return False
    closed(result,RESULT_FIELDS,'adoption result')
    if result['id']!=file_id(result['project_id'],result['kind'],result['path']) or type(result['changed']) is not bool:fail('Invalid adoption result identity.')
    sha(result['sha256']);_date(result['adopted_at'])
    if type(result['revision']) is not int or not 1<=result['revision']<=2**53-1 or type(result['bytes']) is not int or not 0<=result['bytes']<=MAX_FILE_BYTES:fail('Invalid adoption result bounds.')
    if records is not None:
        owned=decode_records(records)
        envelope=next((r for r in owned if r['id']==result['id']),None)
        if envelope is None or not any(all(value[key]==result[key] for key in ('revision','sha256','bytes','adopted_at')) for value in envelope['document']['history']):
            fail('Adoption result is not an exact retained working-file revision.')
    return True


class _WorkingError(Exception):
    def __init__(self,state):self.state=state


def _read(root,parts):
    parent=os.dup(root);descriptor=None
    try:
        for part in parts[:-1]:
            child=os.open(part,DIR_FLAGS,dir_fd=parent);os.close(parent);parent=child
        descriptor=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK,dir_fd=parent)
        before=os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1:raise _WorkingError('unsafe_path')
        if before.st_size>MAX_FILE_BYTES:raise _WorkingError('too_large')
        chunks=[];total=0
        while True:
            block=os.read(descriptor,min(65536,MAX_FILE_BYTES+1-total))
            if not block:break
            chunks.append(block);total+=len(block)
            if total>MAX_FILE_BYTES:raise _WorkingError('too_large')
        after=os.fstat(descriptor);entry=os.stat(parts[-1],dir_fd=parent,follow_symlinks=False)
        fields=lambda value:(value.st_dev,value.st_ino,value.st_mode,value.st_nlink,value.st_size,value.st_mtime_ns,value.st_ctime_ns)
        if fields(before)!=fields(after) or fields(after)!=fields(entry):raise _WorkingError('unstable')
        current=os.dup(root)
        try:
            for part in parts[:-1]:
                child=os.open(part,DIR_FLAGS,dir_fd=current);os.close(current);current=child
            if (os.fstat(current).st_dev,os.fstat(current).st_ino)!=(os.fstat(parent).st_dev,os.fstat(parent).st_ino):
                raise _WorkingError('unstable')
        finally:os.close(current)
        raw=b''.join(chunks)
        try:text=raw.decode('utf-8')
        except UnicodeDecodeError:raise _WorkingError('invalid_utf8') from None
        return text,digest(raw),len(raw)
    except OSError as error:
        state='missing' if error.errno==errno.ENOENT else 'unsafe_path' if error.errno in (errno.ELOOP,errno.ENOTDIR) else 'unreadable'
        raise _WorkingError(state) from None
    finally:
        if descriptor is not None:os.close(descriptor)
        os.close(parent)


class ProjectFiles:
    def __init__(self,session):
        self.session,self.access,self.db,self.store=session,session.access,session.db,session.store

    def inspect(self):
        with self.access.lock,self.session.lock,self.db.lock:
            self.access.require('inspect','files.inspect');snapshot=self.session.check()
            owned=[r for r in decode_records(snapshot['records']) if r['document']['project_id']==snapshot['project_id']];items=[]
            with self.store.root_directory() as root:
                for envelope in sorted(owned,key=lambda r:r['document']['path']):
                    doc=envelope['document'];value=doc['current']
                    observation=dict(id=envelope['id'],kind=doc['kind'],path=doc['path'],revision=value['revision'],
                        expected_sha256=value['sha256'],expected_bytes=value['bytes'],observed_sha256=None,observed_bytes=None,state='missing',reason=None)
                    try:
                        _,observed,size=_read(root,_path(doc['kind'],doc['path']))
                        observation.update(observed_sha256=observed,observed_bytes=size,state='unchanged' if observed==value['sha256'] else 'changed')
                    except _WorkingError as error:
                        observation.update(state='missing' if error.state=='missing' else 'invalid',reason=error.state)
                    items.append(observation)
            self.session.check()
            return dict(items=items,project_id=snapshot['project_id'],checkpoint=snapshot['checkpoint'])

    def read(self,record_id,revision=None):
        with self.access.lock,self.session.lock,self.db.lock:
            self.access.require('inspect','files.read',record_id);snapshot=self.session.check()
            envelope=next((r for r in decode_records(snapshot['records']) if r['id']==record_id),None)
            if envelope is None:fail('Adopted working file is unavailable.','unavailable',404)
            values=envelope['document']['history']
            if revision is None:value=values[-1]
            elif type(revision) is int and 1<=revision<=len(values):value=values[revision-1]
            else:fail('Adopted working-file revision is unavailable.','unavailable',404)
            return dict(id=record_id,project_id=envelope['document']['project_id'],kind=envelope['document']['kind'],path=envelope['document']['path'],version=copy.deepcopy(value))

    def history(self,record_id):
        with self.access.lock,self.session.lock,self.db.lock:
            self.access.require('inspect','files.history',record_id);snapshot=self.session.check()
            envelope=next((r for r in decode_records(snapshot['records']) if r['id']==record_id),None)
            if envelope is None:fail('Adopted working file is unavailable.','unavailable',404)
            return copy.deepcopy(envelope['document']['history'])

    def require_clean(self):
        """Save As must not silently discard unadopted or missing source files."""
        report=self.inspect()
        if any(item['state']!='unchanged' for item in report['items']):
            error=WorkbenchError('Adopt or restore changed, missing or invalid working files before Save As.','working_files_changed',409)
            error.report=report
            raise error
        return report

    @staticmethod
    def materialize_captured(records,project_id,root_fd):
        return materialize_captured(records,project_id,root_fd)

    def adopt(self,body,expected_checkpoint,key):
        closed(body,{'kind','path','expected_revision','expected_sha256'},'working-file adoption')
        parts=_path(body['kind'],body['path']);project_id=self.session.snapshot['project_id'];record_id=file_id(project_id,body['kind'],body['path']);sha(body['expected_sha256'])
        if type(body['expected_revision']) is not int or not 0<=body['expected_revision']<=2**53-1:fail('Invalid expected adoption revision.')
        pending=[]
        with self.access.lock:
            self.access.require('edit','files.adopt',record_id)
            def invoke():
                snapshot=self.session.snapshot;owned=[r for r in decode_records(snapshot['records']) if r['document']['project_id']==project_id]
                prior=next((r for r in owned if r['id']==record_id),None)
                revision=prior['document']['current']['revision'] if prior else 0
                if revision!=body['expected_revision']:fail('Working-file adoption revision changed.','conflict',409)
                if prior is None and len(owned)>=MAX_FILES:fail('Project already tracks 1,000 working files.','too_large',413)
                with self.store.root_directory() as root:
                    try:text,observed,size=_read(root,parts)
                    except _WorkingError as error:fail('Working file is '+error.state+'.','unavailable' if error.state=='missing' else 'invalid',404 if error.state=='missing' else 400)
                if observed!=body['expected_sha256']:fail('Working file changed after review.','conflict',409)
                if prior is not None and observed==prior['document']['current']['sha256']:return _result(prior,False)
                actor=self.access.require('edit','files.adopt',record_id)
                value=dict(revision=revision+1,sha256=observed,bytes=size,text=text,adopted_at=timestamp(),actor_id=actor.actor_id)
                history=copy.deepcopy(prior['document']['history']) if prior else [];history.append(value)
                envelope=dict(family=FAMILY,id=record_id,document=dict(format=FORMAT,project_id=project_id,kind=body['kind'],path=body['path'],current=copy.deepcopy(value),history=history,origin=copy.deepcopy(prior['document']['origin']) if prior else None))
                decode_records([r for r in snapshot['records'] if not (r['family']==FAMILY and r['id']==record_id)]+[envelope]);pending.append(envelope)
                return _result(envelope,True)
            return self.session.mutate('files.adopt',record_id,body,expected_checkpoint,key,invoke,
                lambda result,before:dict(records=copy.deepcopy(pending),result=copy.deepcopy(result)))


def _validate_forks(owned,records):
    indexed={r['id']:r for r in owned}
    overlays=[r['document'] for r in records if r.get('family')=='project_fork']
    if overlays:
        from project_fork import decode_fork
        decode_fork(records)
    for envelope in owned:
        doc=envelope['document'];origin=doc['origin']
        if origin is None:continue
        closed(origin,{'project_id','checkpoint','id','revision'},'working-file fork origin')
        _project_id(origin['project_id']);sha(origin['checkpoint']);sha(origin['id'])
        if type(origin['revision']) is not int or not 1<=origin['revision']<=2**53-1:fail('Invalid original working-file revision.')
        original=indexed.get(origin['id'])
        if original is None:fail('Working-file fork original is unavailable.')
        source=original['document']
        if source['project_id']!=origin['project_id'] or source['kind']!=doc['kind'] or source['path']!=doc['path'] or source['current']['revision']!=origin['revision']:
            fail('Working-file fork origin differs from its exact archived source.')
        mapping=dict(family=FAMILY,source_id=origin['id'],source_revision=origin['revision'],destination_id=envelope['id'])
        matches=[o for o in overlays if o['source']==dict(project_id=origin['project_id'],checkpoint=origin['checkpoint']) and o['destination_project_id']==doc['project_id'] and mapping in o['mapping']]
        if len(matches)!=1 or doc['history'][:origin['revision']]!=source['history']:
            fail('Working-file fork requires its exact archived history and origin mapping.')


def fork_records(records,source_project_id,source_checkpoint,destination_project_id):
    """Independent file identity; preserve actual historical adoptions exactly."""
    _project_id(source_project_id);_project_id(destination_project_id);sha(source_checkpoint)
    if source_project_id==destination_project_id:fail('An independent working-file fork needs a new project.')
    decoded=decode_records(records)
    from project_fork import active_records
    active={(r['family'],r['id']) for r in active_records(records,project_id=source_project_id)}
    owned=[r for r in decoded if (r['family'],r['id']) in active]
    made=[];mapping=[]
    for envelope in owned:
        doc=envelope['document']
        if doc['project_id']!=source_project_id:fail('Current working-file scope differs from the selected project.')
        new_id=file_id(destination_project_id,doc['kind'],doc['path'])
        if any(r['family']==FAMILY and r['id']==new_id for r in records):fail('Working-file destination identity already exists.')
        fresh=copy.deepcopy(envelope);fresh['id']=new_id
        fresh['document'].update(project_id=destination_project_id,origin=dict(project_id=source_project_id,checkpoint=source_checkpoint,id=envelope['id'],revision=doc['current']['revision']))
        made.append(fresh);mapping.append(dict(family=FAMILY,source_id=envelope['id'],source_revision=doc['current']['revision'],destination_id=new_id))
    made.sort(key=lambda r:r['id']);mapping.sort(key=lambda m:(m['family'],m['source_id'],m['source_revision'],m['destination_id']))
    return dict(records=made,mapping=mapping)


def materialize_captured(records,project_id,root_fd):
    """Write exact declared text only into the caller's new staging capability.

    The fork owner verifies destination non-overlap and owns all staging cleanup
    and publication. O_EXCL never replaces an existing working file. A partial
    failed staging tree is not a published fork and must not be acknowledged.
    """
    _project_id(project_id)
    if type(root_fd) is not int or not stat.S_ISDIR(os.fstat(root_fd).st_mode):fail('A staging directory capability is required.')
    owned=[r for r in decode_records(records) if r['document']['project_id']==project_id]
    copied=[]
    try:
        for envelope in sorted(owned,key=lambda r:r['document']['path']):
            doc=envelope['document'];value=doc['current'];parts=_path(doc['kind'],doc['path'])
            parent=os.dup(root_fd);descriptor=None
            try:
                for part in parts[:-1]:
                    try:os.mkdir(part,0o700,dir_fd=parent);os.fsync(parent)
                    except FileExistsError:pass
                    child=os.open(part,DIR_FLAGS,dir_fd=parent);os.close(parent);parent=child
                descriptor=os.open(parts[-1],os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=parent)
                captured=os.fstat(descriptor)
                if not stat.S_ISREG(captured.st_mode) or captured.st_nlink!=1:fail('Unsafe staging working file.')
                raw=value['text'].encode('utf-8');remaining=memoryview(raw)
                while remaining:
                    count=os.write(descriptor,remaining)
                    if count<=0:raise OSError(errno.EIO,'Working-file staging write failed')
                    remaining=remaining[count:]
                os.fsync(descriptor)
                entry=os.stat(parts[-1],dir_fd=parent,follow_symlinks=False)
                after=os.fstat(descriptor)
                if (entry.st_dev,entry.st_ino,entry.st_nlink,entry.st_size)!=(captured.st_dev,captured.st_ino,1,len(raw)) or after.st_size!=len(raw):fail('Working-file staging entry changed.','stale_project',409)
                check=os.dup(root_fd)
                try:
                    for part in parts[:-1]:
                        child=os.open(part,DIR_FLAGS,dir_fd=check);os.close(check);check=child
                    if (os.fstat(check).st_dev,os.fstat(check).st_ino)!=(os.fstat(parent).st_dev,os.fstat(parent).st_ino):fail('Working-file staging directory changed.','stale_project',409)
                finally:os.close(check)
                os.fsync(parent)
                copied.append(dict(id=envelope['id'],path=doc['path'],sha256=value['sha256'],bytes=value['bytes']))
            finally:
                if descriptor is not None:os.close(descriptor)
                os.close(parent)
        os.fsync(root_fd)
    except OSError:
        fail('Working-file staging failed; no complete fork was published.','storage',500)
    return copied
