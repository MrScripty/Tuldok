"""Explicit, report-first extraction of a stopped legacy catalog.

Preview creates no domain supervisors and writes no source files. Only the
currently owned controller can stop and hand over a live stopped-source lease.
The private backup remains a legacy backup, never a portable authority dump.
"""
import copy
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import threading
import time
import uuid
import weakref

import psycopg
from psycopg import sql

from metadata import Metadata, SCHEMA_VERSION, row_factory, _key
from project_store import (DIR_FLAGS, FILE_FLAGS, ProjectStore,
                           _rename_noreplace, _encode)
from project_artifacts import ProjectArtifacts, validate_declaration
from workbench import WorkbenchError, timestamp

UUID=re.compile(r'^[a-f0-9]{32}$')
SHA=re.compile(r'^[a-f0-9]{64}$')
ALIAS=re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$')
ROOT_FAMILIES={
    'records':'workbench_record','responses':'workbench_response','preferences':'workbench_preference',
    'selections':'saved_selection','searches':'saved_search','graphs':'pipeline_graph',
    'recipe_drafts':'recipe_definition','model_definitions':'model_definition','studies':'study_history',
    'runs':'run_history','releases':'dataset_release','exposures':'dataset_exposure',
    'model_materials':'model_material','recipe_materials':'recipe_material','runtime_materials':'runtime_material'}
NAMESPACED={'pipeline_graph','recipe_definition','model_definition','study_history','trial_history',
    'run_history','candidate_history','model_material','recipe_material','runtime_material','project_snapshot',
    'generation_history','grounded_history','caption_proposal_history','text_proposal_history'}
PRODUCERS={'generation':'generation_history','grounded':'grounded_history',
           'caption':'caption_proposal_history','text_proposal':'text_proposal_history'}
RUNTIME_NAMES=('generation_jobs','grounded_jobs','caption_proposals','text_classification_proposals','workspace_runs')
_LEASE_TOKEN=object()
_ISSUED_STOPPED=weakref.WeakSet()
MAX_SOURCE_FILE=40*1024*1024


def fail(message,code='invalid',status=400):raise WorkbenchError(message,code,status)
def closed(value,fields,label):
    if type(value) is not dict or set(value)!=set(fields):fail('Invalid '+label+' fields.')
def digest(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):return _encode(value)
def sha(value):
    if type(value) is not str or not SHA.fullmatch(value):fail('Invalid extraction digest.')
def identity(value):
    if type(value) is not str or not UUID.fullmatch(value):fail('Invalid extraction identity.')
def leaf(value):
    if type(value) is not str or not 1<=len(value)<=200 or value in ('.','..') or any(c in value for c in '/\\') or any(ord(c)<32 for c in value):fail('Choose one exact destination directory name.')
    return value

def parts(value):
    if type(value) is not str or len(value)>512 or '\\' in value or any(ord(c)<32 for c in value):fail('Invalid source-relative path.')
    result=value.split('/')
    if not 1<=len(result)<=16 or any(p in ('','.','..') for p in result):fail('Source reference must remain inside its configured root.')
    return result


def _fd_identity(fd):
    value=os.fstat(fd)
    return value.st_dev,value.st_ino


@contextmanager
def _file(root,relative,maximum):
    path=parts(relative);parent=os.dup(root);descriptor=None
    try:
        for name in path[:-1]:
            child=os.open(name,DIR_FLAGS,dir_fd=parent);os.close(parent);parent=child
        descriptor=os.open(path[-1],FILE_FLAGS,dir_fd=parent)
        before=os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or before.st_size>maximum:fail('Source payload is unsafe or exceeds its owner bound.','unavailable',409)
        yield descriptor,before
        after=os.fstat(descriptor);current=os.stat(path[-1],dir_fd=parent,follow_symlinks=False)
        key=lambda v:(v.st_dev,v.st_ino,v.st_mode,v.st_nlink,v.st_size,v.st_mtime_ns,v.st_ctime_ns)
        if key(before)!=key(after) or key(after)!=key(current):fail('Source payload changed during capture.','stale_source',409)
    except OSError:fail('Source payload is missing or unsafe.','unavailable',409)
    finally:
        if descriptor is not None:os.close(descriptor)
        os.close(parent)


def _read(root,relative,maximum):
    with _file(root,relative,maximum) as (fd,info):
        chunks=[];remaining=maximum+1
        while remaining:
            raw=os.read(fd,min(65536,remaining))
            if not raw:break
            chunks.append(raw);remaining-=len(raw)
        result=b''.join(chunks)
        if len(result)!=info.st_size or len(result)>maximum:fail('Source payload changed or exceeds its owner bound.','unavailable',409)
        return result


class ReadonlyCatalog:
    """The exact schema proof, without Metadata construction or source writes."""
    _signature=Metadata._signature
    validate_schema=Metadata.validate_schema
    def __init__(self,dsn,schema,catalog_id,path,*,exclude_peers=False):
        identity(catalog_id)
        if schema!='catalog_'+catalog_id:fail('Only a current legacy catalog can be extracted.','unsupported',409)
        self.dsn,self.schema,self.dataset_id,self.path=dsn,schema,catalog_id,Path(path)
        self.schema_version=SCHEMA_VERSION;self.lock=threading.RLock()
        self.connection=psycopg.connect(dsn,autocommit=True,row_factory=row_factory)
        try:
            self.connection.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
            self.connection.execute("SET statement_timeout='60000'")
            self.connection.execute("SET lock_timeout='1000'")
            if exclude_peers:
                for key in [_key(schema),*(_key(schema+':worker:'+name) for name in RUNTIME_NAMES)]:
                    if not self.connection.execute('SELECT pg_try_advisory_lock(%s)',(key,)).fetchone()[0]:
                        fail('A peer acquired legacy catalog ownership after stop.','busy',409)
            self.connection.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
            self.validate_schema()
        except BaseException:self.connection.close();raise
    def execute(self,query,parameters=None):
        # PostgreSQL READ ONLY is the enforcement boundary, including CTEs.
        return self.connection.execute(query,parameters)
    @property
    def tables(self):
        from metadata import tables_for_version
        return tables_for_version(self.schema_version)
    def close(self):self.connection.close()


class CapturedArtifacts:
    """Private verified evidence custody; no preview file publication."""
    def __init__(self):self.payloads={};self.declarations={}
    def publish_bytes(self,raw,declaration,*,maximum_bytes=None):
        declaration=validate_declaration(declaration)
        if type(raw) is not bytes or len(raw)!=declaration['bytes'] or digest(raw)!=declaration['sha256']:fail('Captured source bytes differ from their declaration.')
        if maximum_bytes is not None and len(raw)>maximum_bytes:fail('Captured source exceeds its owner bound.','too_large',413)
        self._add(declaration,raw);return copy.deepcopy(declaration)
    def publish_fd(self,descriptor,declaration,*,maximum_bytes=None):
        declaration=validate_declaration(declaration);info=os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size!=declaration['bytes'] or maximum_bytes is not None and info.st_size>maximum_bytes:fail('Captured source descriptor differs.')
        hasher=hashlib.sha256();offset=0
        while offset<info.st_size:
            raw=os.pread(descriptor,min(1024*1024,info.st_size-offset),offset)
            if not raw:fail('Captured source descriptor was truncated.')
            hasher.update(raw);offset+=len(raw)
        after=os.fstat(descriptor)
        if hasher.hexdigest()!=declaration['sha256'] or (info.st_size,info.st_mtime_ns,info.st_ctime_ns)!=(after.st_size,after.st_mtime_ns,after.st_ctime_ns):fail('Captured source descriptor changed.')
        old=self.payloads.get(declaration['sha256'])
        if old is None:self._add(declaration,os.dup(descriptor))
        return copy.deepcopy(declaration)
    def _add(self,declaration,payload):
        key=declaration['sha256'];prior=self.declarations.get(key)
        if prior is not None and prior!=declaration:fail('Captured payload declarations conflict.')
        if key not in self.payloads:self.payloads[key]=payload
        self.declarations[key]=copy.deepcopy(declaration)
    def read_blob(self,declaration,*,maximum_bytes=MAX_SOURCE_FILE):
        key=declaration['sha256'];value=self.declarations.get(key)
        if value is None or value['bytes']!=declaration['bytes'] or value['bytes']>maximum_bytes:fail('Captured source bytes are unavailable.','unavailable',409)
        payload=self.payloads[key]
        raw=payload if type(payload) is bytes else os.pread(payload,value['bytes'],0)
        if len(raw)!=value['bytes'] or digest(raw)!=key:fail('Captured source changed.','stale_source',409)
        return raw
    def status(self,declaration):
        value=validate_declaration(declaration);actual=self.declarations.get(value['sha256']);present=value['sha256'] in self.payloads
        state='missing' if not present else 'verified' if actual==value else 'corrupt'
        return dict(state=state,expected_sha256=value['sha256'],expected_bytes=value['bytes'],observed_sha256=actual['sha256'] if present else None,observed_bytes=actual['bytes'] if present else None)
    inspect=status
    @contextmanager
    def open_verified(self,declaration,*,maximum_bytes=None):
        value=validate_declaration(declaration);payload=self.payloads.get(value['sha256'])
        if payload is None or self.declarations.get(value['sha256'])!=value:fail('Unique source payload is missing or differs.','unavailable',409)
        if maximum_bytes is not None and value['bytes']>maximum_bytes:fail('Captured payload exceeds its owner bound.','too_large',413)
        if type(payload) is bytes:
            import tempfile
            with tempfile.TemporaryFile() as temporary:
                temporary.write(payload);temporary.flush();temporary.seek(0)
                yield temporary.fileno()
        else:
            self.publish_fd(payload,value,maximum_bytes=maximum_bytes)
            duplicate=os.dup(payload)
            try:yield duplicate
            finally:os.close(duplicate)
    def close(self):
        for value in self.payloads.values():
            if type(value) is int:os.close(value)
        self.payloads.clear()


class SourceView:
    def __init__(self,db,root_fd,root_path,roots,*,actor_id,captured_at=None):
        self.db,self.root_fd,self.root_path=db,root_fd,Path(root_path)
        self.roots=roots;self.actor_id=actor_id;self.captured_at=captured_at or timestamp()
        self.artifacts=CapturedArtifacts();self._closed=False;self._payload_locations={};self._authorize=None
        self.snapshot=dict(project_id=db.dataset_id,checkpoint='0'*64,records=[])
        self.fingerprint=None;self.backup_receipt=None;self.external_inventory=[];self._observed_roots={}
    def require(self):
        if self._authorize is not None:self._authorize()
        if self._closed or self.db.connection.closed:fail('Source snapshot lease is closed.','unavailable',409)
        current=os.open(self.root_path,DIR_FLAGS)
        try:
            if _fd_identity(current)!=_fd_identity(self.root_fd):fail('Source catalog root changed.','stale_source',409)
        finally:os.close(current)
    def read_catalog(self,relative,maximum_bytes=MAX_SOURCE_FILE):
        self.require();return _read(self.root_fd,relative,maximum_bytes)
    def read_root(self,alias,relative,maximum_bytes=MAX_SOURCE_FILE):
        self.require();entry=self.roots.get(alias)
        if entry is None:fail('An explicit source root binding is required.','unavailable',409)
        raw=_read(entry[0],relative,maximum_bytes)
        key=(alias,relative);observation=(len(raw),digest(raw))
        if key in self._observed_roots and self._observed_roots[key]!=observation:fail('External source bytes changed after capture.','stale_source',409)
        self._observed_roots[key]=observation
        fact=dict(root=alias,relative=relative,sha256=observation[1],bytes=observation[0])
        if fact not in self.external_inventory:self.external_inventory.append(fact)
        return raw
    def resolve_payload(self,sha256,size):
        sha(sha256)
        if sha256 in self.artifacts.declarations:return self.artifacts.read_blob(dict(sha256=sha256,bytes=size))
        location=self._payload_locations.get(sha256)
        if location is None or location['bytes']!=size:fail('An explicit external payload inventory binding is required.','unavailable',409)
        raw=self.read_root(location['root'],location['relative'],MAX_SOURCE_FILE)
        if len(raw)!=size or digest(raw)!=sha256:fail('External source payload differs from its declaration.')
        return raw
    @contextmanager
    def payload_fd(self,sha256,size):
        sha(sha256)
        location=self._payload_locations.get(sha256)
        if location is None or location['bytes']!=size:fail('An explicit payload descriptor binding is required.','unavailable',409)
        with _file(self.roots[location['root']][0],location['relative'],size) as (fd,info):
            declaration=dict(format='project_artifact_v1',sha256=sha256,bytes=size)
            self.artifacts.publish_fd(fd,declaration,maximum_bytes=size)
            yield fd

    def bind_payload(self,sha256,size,root,relative):
        # Internal capability owner call, never inferred from a historical path.
        self.require();sha(sha256)
        if type(size) is not int or not 0<=size<=2**63-1 or root not in self.roots:fail('Invalid external payload binding.')
        with _file(self.roots[root][0],relative,max(size,1)) as (fd,info):
            if info.st_size!=size:fail('External payload binding differs.')
            self.artifacts.publish_fd(fd,dict(format='project_artifact_v1',sha256=sha256,bytes=size),maximum_bytes=size)
        self._observed_roots[(root,relative)]=(size,sha256)
        self._payload_locations[sha256]=dict(root=root,relative=relative,bytes=size)
        fact=dict(root=root,relative=relative,sha256=sha256,bytes=size)
        if fact not in self.external_inventory:self.external_inventory.append(fact)
    def close(self):
        if self._closed:return
        self._closed=True;self.artifacts.close();self.db.close();os.close(self.root_fd)
        for fd,_ in self.roots.values():os.close(fd)
        self.roots.clear()
    def __enter__(self):self.require();return self
    def __exit__(self,*exc):self.close()


class StoppedSourceLease(SourceView):
    def __init__(self,*args,_token=None,**kwargs):
        if _token is not _LEASE_TOKEN:fail('A stopped source must be issued by its current trusted owner.','forbidden',403)
        super().__init__(*args,**kwargs)
    def require(self):
        super().require()
        if self not in _ISSUED_STOPPED or self.backup_receipt is None:fail('Verified stopped backup is unavailable.','unavailable',409)


def preview_source(dataset):
    """Read a currently opened source without constructing or stopping owners."""
    actor=dataset.access.require('inspect','project_transfer.preview')
    root=os.open(dataset.path,DIR_FLAGS);roots={}
    try:
        for alias,(fd,value) in dataset.projects.roots.items():roots[alias]=(os.dup(fd),list(value))
        view=ReadonlyCatalog(dataset.db.dsn,dataset.db.schema,dataset.db.dataset_id,dataset.path)
        source=SourceView(view,root,dataset.path,roots,actor_id=actor.actor_id)
        source._authorize=lambda:dataset.access.require('inspect','project_transfer.preview')
        return source
    except BaseException:
        os.close(root)
        for fd,_ in roots.values():os.close(fd)
        raise


def _snapshot(view):
    from backup_metadata import read_catalog,read_sequences,summaries
    tables=read_catalog(view.db);sequences=read_sequences(view.db)
    return tables,sequences,digest(canonical(dict(tables=summaries(tables),sequences=sequences)))


def _verified_backup(source,parent_fd,directory):
    from backup_metadata import tree_manifest,copy_tree,tree_modes,summaries
    leaf(directory)
    from project_fork import _inside
    if _inside(parent_fd,source.root_fd):fail('Backup cannot overlap its source.','conflict',409)
    stage='.tuldok-extraction-backup-'+uuid.uuid4().hex
    os.mkdir(stage,0o700,dir_fd=parent_fd)
    path=Path('/proc/self/fd')/str(parent_fd)/stage
    tables,sequences,fingerprint=_snapshot(source)
    before=tree_manifest(source.root_path)
    copy_tree(source.root_path,path/'catalog',before)
    metadata=dict(format_version=1,schema_version=source.db.schema_version,dataset_id=source.db.dataset_id,tables=tables,sequences=sequences)
    from backup_metadata import write_json,file_hash
    write_json(path/'metadata.json',metadata)
    receipt=dict(format_version=1,kind='postgresql',schema_version=source.db.schema_version,dataset_id=source.db.dataset_id,
        postgresql_server_version=source.db.connection.info.server_version,driver='psycopg '+psycopg.__version__,
        restore_privileges='CONNECT and CREATE on a new PostgreSQL database; catalog schema must be absent',
        metadata_sha256=file_hash(path/'metadata.json'),files=before,tables=summaries(tables),sequences=sequences)
    write_json(path/'backup-receipt.json',receipt)
    source.require()
    if before!=tree_manifest(source.root_path) or before!=tree_manifest(path/'catalog') or tree_modes(source.root_path,before)!=tree_modes(path/'catalog',before):fail('Source changed while capturing its stopped backup.','stale_source',409)
    directory_fd=os.open(stage,DIR_FLAGS,dir_fd=parent_fd)
    try:os.fsync(directory_fd)
    finally:os.close(directory_fd)
    _rename_noreplace(parent_fd,stage,directory);os.fsync(parent_fd)
    return receipt,fingerprint


def stop_source(dataset,*,backup_parent_fd,backup_directory,external_roots=None,controller_guard):
    """Only the already running, explicitly gated owner may mint this lease."""
    from app import Dataset, _LegacyExtractionGuard
    if not isinstance(dataset,Dataset) or type(controller_guard) is not _LegacyExtractionGuard or dataset._extraction_guard is not controller_guard:
        fail('An exclusive current-controller stop guard is required.','forbidden',403)
    controller_guard.require(dataset)
    actor=dataset.access.require('admin','project_transfer.stop_source',owner_only=True)
    leaf(backup_directory)
    if not stat.S_ISDIR(os.fstat(backup_parent_fd).st_mode):fail('A backup parent capability is required.')
    try:os.stat(backup_directory,dir_fd=backup_parent_fd,follow_symlinks=False)
    except FileNotFoundError:pass
    else:fail('Stopped backup destination already exists.','conflict',409)
    if any(not dataset.db.runtime_owned(name) for name in RUNTIME_NAMES):fail('A peer owns a legacy runtime; stop its actual owner first.','busy',409)
    if dataset.runs._blocked or dataset.runs._external_blocked:fail('Legacy worker cessation remains unknown.','unknown',409)
    root=os.open(dataset.path,DIR_FLAGS);roots={};source=None
    dsn,schema,catalog_id=dataset.db.dsn,dataset.db.schema,dataset.db.dataset_id
    try:
        for alias,(fd,value) in (external_roots if external_roots is not None else dataset.projects.roots).items():
            if type(alias) is not str or not ALIAS.fullmatch(alias) or list(_fd_identity(fd))!=list(value):fail('Invalid explicit external root capability.')
            roots[alias]=(os.dup(fd),list(value))
        with dataset.image_requests.lock:pending=list(dataset.image_requests.active.items())
        for request_id,operation in pending:operation.cancel()
        deadline=time.monotonic()+60
        for request_id,operation in pending:
            if not operation.done.wait(max(0,deadline-time.monotonic())):fail('An owned image request did not drain.','unknown',409)
        controller_guard.require(dataset)
        # Existing owner close may change lifecycle observations. The preservation
        # baseline is captured afterwards, never before this explicit stop.
        dataset.close_for_project_extraction(deadline=deadline)
        for owner in (dataset.generation_jobs,dataset.grounded,dataset.caption_proposals,dataset.text_classification_proposals):
            worker=getattr(owner,'worker',None)
            if worker is not None and worker.is_alive():fail('A legacy producer did not drain.','unknown',409)
        if dataset.runs._blocked or dataset.runs._external_blocked:fail('Legacy process cessation is unknown.','unknown',409)
        with dataset.image_requests.lock:
            if dataset.image_requests.active:fail('An image request remains active.','unknown',409)
        controller_guard.require(dataset)
        db=ReadonlyCatalog(dsn,schema,catalog_id,dataset.path,exclude_peers=True)
        # Base view permits backup verification before the stopped lease is minted.
        source=SourceView(db,root,dataset.path,roots,actor_id=actor.actor_id)
        import recipe_process
        for row in db.execute('SELECT document FROM workspace_runs'):
            run=json.loads(row[0]);custody=run.get('custody_identity')
            if custody is None:continue
            if run.get('state')=='completed':
                raw=source.read_catalog('workspace-runs/'+run['id']+'/custody-receipt.json',16384)
                receipt=recipe_process.validate_receipt(raw,custody)
            else:receipt=dataset.runs._external_drain_receipt(run)
            if receipt is None or not receipt['drained']:fail('An external custodian has no exact drained receipt.','unknown',409)
        receipt,fingerprint=_verified_backup(source,backup_parent_fd,backup_directory)
        source.backup_receipt=receipt;source.fingerprint=fingerprint;source.snapshot['checkpoint']=fingerprint
        source.__class__=StoppedSourceLease
        _ISSUED_STOPPED.add(source)
        source.require()
        return source
    except BaseException:
        if source is not None:source.close()
        else:
            os.close(root)
            for fd,_ in roots.values():os.close(fd)
        raise


def normalize_selection(selection):
    closed(selection,{'project_snapshot','roots','decisions'},'extraction selection')
    snapshot=selection['project_snapshot'];closed(snapshot,{'id','manifest_sha256'},'selected project snapshot')
    identity(snapshot['id']);sha(snapshot['manifest_sha256'])
    roots=selection['roots'];known=set(ROOT_FAMILIES)|{'producer_jobs','working_files'}
    if type(roots) is not dict or set(roots)-known:fail('Unsupported extraction root family.')
    normalized={}
    for name in ROOT_FAMILIES:
        values=roots.get(name,[])
        if type(values) is not list or len(values)>10000 or any(type(v) is not str for v in values) or len(set(values))!=len(values):fail('Extraction roots must be bounded unique identifiers.')
        for value in values:
            sha(value) if name in ('releases','model_materials','recipe_materials','runtime_materials') else identity(value)
        normalized[name]=sorted(values)
    jobs=roots.get('producer_jobs',[])
    if type(jobs) is not list or len(jobs)>10000:fail('Invalid producer selection.')
    seen=set();normalized_jobs=[]
    for value in jobs:
        closed(value,{'kind','id'},'producer selection');identity(value['id'])
        if value['kind'] not in PRODUCERS or (value['kind'],value['id']) in seen:fail('Unsupported or duplicate producer root.')
        seen.add((value['kind'],value['id']));normalized_jobs.append(copy.deepcopy(value))
    normalized['producer_jobs']=sorted(normalized_jobs,key=lambda v:(v['kind'],v['id']))
    files=roots.get('working_files',[])
    if type(files) is not list or len(files)>1000:fail('Invalid working-file selection.')
    from project_files import _path
    seen=set();normalized_files=[]
    for value in files:
        closed(value,{'kind','path'},'working-file selection');_path(value['kind'],value['path'])
        if (value['kind'],value['path']) in seen:fail('Duplicate working-file selection.')
        seen.add((value['kind'],value['path']));normalized_files.append(copy.deepcopy(value))
    normalized['working_files']=sorted(normalized_files,key=lambda v:(v['kind'],v['path']))
    decisions=selection['decisions']
    if type(decisions) is not list or len(decisions)>10000:fail('Invalid ownership decisions.')
    allowed=set(ROOT_FAMILIES.values())|NAMESPACED|{'project_artifact','project_file','trial_history','candidate_history'}
    fixed=[];seen=set()
    for value in decisions:
        closed(value,{'family','id','include','reason'},'ownership decision')
        if value['family'] not in allowed or type(value['id']) is not str or not 1<=len(value['id'])<=128 or type(value['include']) is not bool or type(value['reason']) is not str or not 1<=len(value['reason'])<=1000 or (value['family'],value['id']) in seen:fail('Invalid explicit ownership decision.')
        seen.add((value['family'],value['id']));fixed.append(copy.deepcopy(value))
    return dict(project_snapshot=copy.deepcopy(snapshot),roots=normalized,decisions=sorted(fixed,key=lambda v:(v['family'],v['id'])))


def _seeds(selection,catalog_id):
    selected={('project_snapshot',catalog_id+'.'+selection['project_snapshot']['manifest_sha256'])}
    for root,family in ROOT_FAMILIES.items():
        for value in selection['roots'][root]:selected.add((family,catalog_id+'.'+value if family in NAMESPACED else value))
    for value in selection['roots']['producer_jobs']:selected.add((PRODUCERS[value['kind']],catalog_id+'.'+value['id']))
    from project_files import file_id
    for value in selection['roots']['working_files']:selected.add(('project_file',file_id(catalog_id,value['kind'],value['path'])))
    for value in selection['decisions']:
        if value['include']:selected.add((value['family'],value['id']))
    return selected


def _capture(source,selection):
    from project_extraction import capture_legacy
    captured=capture_legacy(source,selection)
    closed(captured,{'records','inventory','dependencies','blockers','working_files','warnings'},'legacy capture')
    for field in captured:
        if type(captured[field]) is not list:fail('Legacy capture fields must be finite lists.')
    return captured


def _validate_candidate(records,project_id,artifacts):
    from project_projection import ProjectProjection
    from types import SimpleNamespace
    ProjectProjection.validate_records(SimpleNamespace(project_id=project_id,artifacts=artifacts),records,project_id=project_id)


class ProjectTransfer:
    def __init__(self,source):
        if not isinstance(source,SourceView):fail('A pinned read-only source capability is required.','forbidden',403)
        self.source=source;self._reports={};self.lock=threading.RLock()

    def extract(self,selection,expected_report_sha256,destination_parent_fd,directory,name,request_key,*,opened_store=None):
        with self.lock:return _extract(self,selection,expected_report_sha256,destination_parent_fd,directory,name,request_key,opened_store=opened_store)

    def preview(self,selection):
        with self.lock:return self._preview(selection)

    def _preview(self,selection):
        source=self.source;source.require();selection=normalize_selection(selection)
        if source.fingerprint is None:
            _,_,source.fingerprint=_snapshot(source);source.snapshot['checkpoint']=source.fingerprint
        captured=_capture(source,selection)
        inventory={}
        for item in captured['inventory']:
            closed(item,{'family','id','revision'},'legacy inventory item')
            key=item['family'],item['id']
            if key in inventory:fail('Legacy inventory repeats an identity.')
            inventory[key]=item
        required=_seeds(selection,source.db.dataset_id);direct=set(required);edges={}
        for edge in captured['dependencies']:
            closed(edge,{'source','target','reason'},'legacy dependency')
            for field in ('source','target'):closed(edge[field],{'family','id'},'dependency locator')
            edges.setdefault((edge['source']['family'],edge['source']['id']),[]).append((edge['target']['family'],edge['target']['id']))
        pending=list(required)
        while pending:
            for key in edges.get(pending.pop(),[]):
                if key not in required:required.add(key);pending.append(key)
        excluded={(v['family'],v['id']) for v in selection['decisions'] if not v['include']}
        blockers=[copy.deepcopy(v) for v in captured['blockers'] if (v['family'],v['id']) in required]
        for family,record_id in sorted(required-inventory.keys()):blockers.append(dict(family=family,id=record_id,code='missing_dependency',detail='Selected or required source fact is unavailable.'))
        for family,record_id in sorted(required&excluded):blockers.append(dict(family=family,id=record_id,code='required_dependency_excluded',detail='Required closure cannot be excluded.'))
        declared={(r['family'],r['id']):r for r in captured['records']}
        records=[copy.deepcopy(declared[k]) for k in sorted(required) if k in declared]
        artifact_report=[]
        artifact_policies={}
        for edge in captured['dependencies']:
            target=(edge['target']['family'],edge['target']['id'])
            parent=(edge['source']['family'],edge['source']['id'])
            if parent in required and target[0]=='project_artifact':
                policy='regenerable' if edge['reason'].startswith('regenerable:') else 'unique'
                if artifact_policies.get(target[1])!='unique':artifact_policies[target[1]]=policy
        for record in records:
            if record['family']=='project_artifact':
                state=source.artifacts.status(record['document'])['state']
                preservation=artifact_policies.get(record['id'],'unique')
                artifact_report.append(dict(sha256=record['id'],bytes=record['document']['bytes'],preservation=preservation,state=state))
                if state!='verified' and preservation=='unique':blockers.append(dict(family='project_artifact',id=record['id'],code='missing_unique_payload',detail='Original required bytes cannot be regenerated during extraction.'))
        file_observations=[]
        from project_files import file_id
        for value in captured['working_files']:
            closed(value,{'kind','path','sha256','bytes','text'},'observed working file')
            if ('project_file',file_id(source.db.dataset_id,value['kind'],value['path'])) in required:file_observations.append(copy.deepcopy(value))
        if not isinstance(source,StoppedSourceLease):blockers.append(dict(family='source',id=source.db.dataset_id,code='cessation_proof_unavailable',detail='The current trusted owner must explicitly stop and capture this source.'))
        if not blockers:
            try:_validate_candidate(records,source.db.dataset_id,source.artifacts)
            except WorkbenchError as error:blockers.append(dict(family='closure',id=source.db.dataset_id,code=getattr(error,'code','invalid'),detail=str(error)))
        report=dict(format='project_transfer_report_v1',source=dict(catalog_id=source.db.dataset_id,schema_version=source.db.schema_version,
            catalog_signature=source.db._signature(),snapshot_sha256=source.fingerprint,
            backup_receipt_sha256=digest(canonical(source.backup_receipt)) if source.backup_receipt is not None else None,
            external_inventory_sha256=digest(canonical(sorted(source.external_inventory,key=lambda v:(v['root'],v['relative']))))),
            selection=selection,included=[copy.deepcopy(inventory[k]) for k in sorted(required&inventory.keys())],
            required=[dict(family=f,id=i) for f,i in sorted(required-direct)],
            unassigned=[copy.deepcopy(inventory[k]) for k in sorted(inventory.keys()-required-excluded)],
            excluded=[dict(family=f,id=i) for f,i in sorted(excluded)],blockers=blockers,
            warnings=[copy.deepcopy(v) for v in captured['warnings'] if (v['family'],v['id']) in required],
            artifacts=artifact_report,working_files=[{k:v[k] for k in ('kind','path','sha256','bytes')} for v in file_observations],can_extract=not blockers)
        report_hash=digest(canonical(report));report['report_sha256']=report_hash
        self._reports[report_hash]=dict(report=copy.deepcopy(report),records=records,working_files=file_observations)
        source.require();return report


FAMILY='project_extraction'
FORMAT='project_extraction_v1'
SOURCE_FIELDS={'catalog_id','schema_version','catalog_signature','backup_receipt_sha256','external_inventory_sha256','snapshot_sha256'}


def decode_records(records):
    from project_store import SUPPORTED_FORMATS
    from project_files import file_id
    indexed={(r['family'],r['id']):r for r in records}
    counts={}
    for r in records:counts[r['family']]=counts.get(r['family'],0)+1
    seen=set();result=[]
    for envelope in records:
        if envelope.get('family')!=FAMILY:continue
        closed(envelope,{'family','id','document'},'extraction envelope');doc=envelope['document']
        closed(doc,{'format','source','selection','report_sha256','request_key','input_sha256','destination_project_id','working_files','counts','artifacts'},'extraction manifest')
        if doc['format']!=FORMAT:fail('Unsupported extraction manifest format.','unsupported',409)
        identity(envelope['id']);identity(doc['destination_project_id'])
        if envelope['id']!=doc['destination_project_id'] or envelope['id'] in seen:fail('Duplicate or mismatched extraction identity.')
        seen.add(envelope['id']);source=doc['source'];closed(source,SOURCE_FIELDS,'extraction source')
        identity(source['catalog_id'])
        if source['catalog_id']==doc['destination_project_id'] or type(source['schema_version']) is not int or source['schema_version']!=SCHEMA_VERSION:fail('Extraction source namespace or schema differs.')
        for field in SOURCE_FIELDS-{'catalog_id','schema_version'}:sha(source[field])
        sha(doc['report_sha256']);sha(doc['input_sha256'])
        overlay=indexed.get(('project_fork',doc['destination_project_id']))
        if overlay is None:fail('Extraction lacks its independent identity overlay.')
        overlay=overlay['document']
        if overlay['source']!=dict(project_id=source['catalog_id'],checkpoint=source['snapshot_sha256']) or overlay['request_key']!=doc['request_key'] or overlay['artifacts']!=doc['artifacts']:fail('Extraction manifest differs from its retained identity transition.')
        if digest(canonical(_input(source,doc['selection'],doc['report_sha256'],overlay['directory'],overlay['name'],doc['request_key'])))!=doc['input_sha256']:fail('Extraction input digest differs from its exact publication request.')
        registered=indexed.get(('project_snapshot',source['catalog_id']+'.'+doc['selection']['project_snapshot']['manifest_sha256']))
        if registered is None or registered['document']['value']['id']!=doc['selection']['project_snapshot']['id']:fail('Extraction lacks its exact selected registered snapshot.')
        if normalize_selection(doc['selection'])!=doc['selection']:fail('Extraction selection is not normalized.')
        from project_store import REQUEST_KEY
        if type(doc['request_key']) is not str or not REQUEST_KEY.fullmatch(doc['request_key']):fail('Invalid extraction request key.')
        if type(doc['counts']) is not dict or any(f not in SUPPORTED_FORMATS or type(n) is not int or n<1 or counts.get(f,0)<n for f,n in doc['counts'].items()):fail('Extraction population counts differ from retained facts.')
        if any(doc['counts'].get(f,0)<1 for f in (FAMILY,'project_fork','project_snapshot')):fail('Extraction population lacks its required source and publication facts.')
        closed(doc['artifacts'],{'copied','missing_regenerable'},'extraction artifact report')
        listed=set()
        for field in ('copied','missing_regenerable'):
            values=doc['artifacts'][field]
            if type(values) is not list or values!=sorted(set(values)):fail('Invalid extraction artifact inventory.')
            for value in values:
                sha(value)
                if value in listed or ('project_artifact',value) not in indexed:fail('Extraction artifact lacks its intrinsic declaration.')
                listed.add(value)
        if type(doc['working_files']) is not list:fail('Invalid extracted working-file observations.')
        paths=set()
        for value in doc['working_files']:
            closed(value,{'kind','path','sha256','bytes','source_catalog_id','source_snapshot_sha256','destination_id','adopted_at','actor_id'},'extracted working-file observation')
            if value['source_catalog_id']!=source['catalog_id'] or value['source_snapshot_sha256']!=source['snapshot_sha256']:fail('Working-file source observation differs.')
            sha(value['sha256']);sha(value['destination_id']);identity(value['actor_id'])
            if value['destination_id']!=file_id(doc['destination_project_id'],value['kind'],value['path']) or (value['kind'],value['path']) in paths:fail('Extracted working-file identity differs.')
            paths.add((value['kind'],value['path']))
            target=indexed.get(('project_file',value['destination_id']))
            if target is None:fail('Extracted working-file adoption is missing.')
            initial=target['document']['history'][0]
            if target['document']['origin'] is not None or initial['revision']!=1 or any(initial[k]!=value[k] for k in ('sha256','bytes','adopted_at','actor_id')):
                fail('Extracted working file is not its exact authorized first adoption.')
        result.append(copy.deepcopy(envelope))
    return result


def _assert_unchanged(source):
    source.require()
    from backup_metadata import tree_manifest
    if source.backup_receipt is not None and tree_manifest(source.root_path)!=source.backup_receipt['files']:fail('Stopped source files changed after the backup baseline.','stale_source',409)
    for (alias,relative),(size,expected_sha) in source._observed_roots.items():
        try:
            with _file(source.roots[alias][0],relative,max(size,1)) as (fd,info):
                hasher=hashlib.sha256();offset=0
                while offset<info.st_size:
                    block=os.pread(fd,min(1024*1024,info.st_size-offset),offset)
                    if not block:fail('External source bytes changed after capture.','stale_source',409)
                    hasher.update(block);offset+=len(block)
                if info.st_size!=size or hasher.hexdigest()!=expected_sha:fail('External source bytes changed after capture.','stale_source',409)
        except WorkbenchError:fail('External source bytes changed after capture.','stale_source',409)
    fresh=ReadonlyCatalog(source.db.dsn,source.db.schema,source.db.dataset_id,source.root_path)
    try:
        from types import SimpleNamespace
        _,_,actual=_snapshot(SimpleNamespace(db=fresh))
    finally:fresh.close()
    if actual!=source.fingerprint:fail('Stopped source SQL changed after its backup baseline.','stale_source',409)


class _VerificationAccess:
    """Ephemeral read-only verification authority from the explicit stop lease."""
    def __init__(self,source):self.source=source;self.lock=threading.RLock()
    def require(self,scope,action,target=None,**kw):
        self.source.require()
        if scope!='inspect':fail('Cold extraction verification cannot admit mutations.','forbidden',403)
        from types import SimpleNamespace
        return SimpleNamespace(actor_id=self.source.actor_id)
    def identity(self):return dict(actor_id=self.source.actor_id,kind='verification')
    def denial(self,*args,**kw):pass


def _cold_verify(store,source):
    """Fresh physical SQL projection and all fixed domain decoders, no jobs."""
    from metadata import Metadata
    from project_session import ProjectSession
    from project_data import ProjectData
    from project_material import ProjectMaterial
    from project_history import ProjectHistory
    from project_producers import ProjectProducers
    snapshot=store.snapshot();path=store.path/'.tuldok-local'/('extraction-verify-'+uuid.uuid4().hex)
    db=Metadata(path,dsn=source.db.dsn,dataset_id=snapshot['project_id'],projection_id=uuid.uuid4().hex)
    artifacts=ProjectArtifacts(store)
    try:
        authority=_VerificationAccess(source)
        session=ProjectSession(store,db,authority,artifacts,validate_records=lambda records:_validate_candidate(records,snapshot['project_id'],artifacts))
        producers=ProjectProducers(session);producers.restore(snapshot)
        data=ProjectData(session,generation_entries=producers.generation_jobs);data.restore()
        materials=ProjectMaterial(session);materials.restore()
        history=ProjectHistory(session,materials=materials)
        history._facts()
        from project_fork import active_records
        active=active_records(snapshot['records'],project_id=snapshot['project_id'])
        expected=sum(r['family'] in ('workbench_record','workbench_text') for r in active)
        actual=db.execute('SELECT count(*) FROM workbench_records').fetchone()[0]
        if actual!=expected:fail('Fresh data reconstruction lost active membership.')
        if store.snapshot()!=snapshot:fail('Cold reconstruction changed canonical extraction facts.')
        return dict(checkpoint=snapshot['checkpoint'],active_data_records=actual)
    finally:
        db.close();artifacts.close()
        # Only this task-created disposable projection is removed; canonical
        # files and the stopped legacy schema are never cleanup targets.
        with psycopg.connect(source.db.dsn,autocommit=True) as cleanup:
            cleanup.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(db.schema)))


def _input(source,selection,report_sha,directory,name,key):
    return dict(source=source,selection=selection,report_sha256=report_sha,directory=directory,name=name,request_key=key)


def _receipt(snapshot,manifest,verification,*,replayed=False):
    return dict(format='project_extraction_receipt_v1',project_id=snapshot['project_id'],checkpoint=snapshot['checkpoint'],
        request_key=manifest['request_key'],input_sha256=manifest['input_sha256'],report_sha256=manifest['report_sha256'],
        source=copy.deepcopy(manifest['source']),artifacts=copy.deepcopy(manifest['artifacts']),verification=copy.deepcopy(verification),
        committed=True,selected=False,replayed=replayed)


def _extract(self,selection,expected_report_sha256,destination_parent_fd,directory,name,request_key,*,opened_store=None):
    source=self.source
    if type(source) is not StoppedSourceLease:fail('Extraction requires its opaque trusted stopped-source lease.','forbidden',403)
    source.require();selection=normalize_selection(selection);sha(expected_report_sha256);leaf(directory)
    from project_store import REQUEST_KEY
    if type(request_key) is not str or not REQUEST_KEY.fullmatch(request_key) or type(name) is not str or not name.strip() or len(name)>200:fail('Invalid extraction request identity.')
    report=self.preview(selection)
    if report['report_sha256']!=expected_report_sha256:fail('The extraction report changed; review the exact source closure again.','stale_source',409)
    if not report['can_extract']:
        error=WorkbenchError('Selected legacy project has unresolved extraction blockers.','extraction_blocked',409);error.report=report;raise error
    cache=self._reports[expected_report_sha256];records=copy.deepcopy(cache['records'])
    _assert_unchanged(source)
    source_ref=report['source'];request_digest=digest(canonical(_input(source_ref,selection,expected_report_sha256,directory,name,request_key)))
    from project_fork import (_inside,ARCHIVE_FAMILIES,_digest as fork_digest,_input as fork_input)
    if _inside(destination_parent_fd,source.root_fd):fail('Extraction destination cannot overlap its source.','conflict',409)
    root_path=Path(os.readlink('/proc/self/fd/'+str(destination_parent_fd)))
    try:existing=os.stat(directory,dir_fd=destination_parent_fd,follow_symlinks=False)
    except FileNotFoundError:existing=None
    def replay(opened):
        snapshot=opened.reconcile(request_key,request_digest)
        if snapshot is None:fail('Extraction destination belongs to another request.','conflict',409)
        manifest=next((r['document'] for r in snapshot['records'] if r['family']==FAMILY and r['id']==snapshot['project_id']),None)
        if manifest is None or manifest['input_sha256']!=request_digest:fail('Extraction receipt is unavailable or differs.')
        with ProjectArtifacts(opened) as current_artifacts:
            _validate_candidate(snapshot['records'],snapshot['project_id'],current_artifacts)
        verification=_cold_verify(opened,source);_assert_unchanged(source)
        return _receipt(snapshot,manifest,verification,replayed=True)
    if opened_store is not None:
        # Trusted controller-only capability. Its caller pins workspace,
        # authority, selected session and SQL ownership through this replay.
        if not isinstance(opened_store,ProjectStore) or existing is None:
            fail('Current selected destination is unavailable.','stale',409)
        with opened_store.root_directory() as owned_fd:
            try:target_fd=os.open(directory,DIR_FLAGS,dir_fd=destination_parent_fd)
            except OSError:fail('Selected destination binding changed.','stale',409)
            try:
                if _fd_identity(target_fd)!=_fd_identity(owned_fd):fail('Selected store differs from the extraction destination.','conflict',409)
            finally:os.close(target_fd)
            return replay(opened_store)
    if existing is not None:
        with ProjectStore.open_at(destination_parent_fd,directory,root_path=root_path) as opened:
            return replay(opened)
    stage_name='.tuldok-extraction-'+uuid.uuid4().hex
    store=None;artifacts=None;committed=None;published=False;stage_identity=None
    try:
        store=ProjectStore.create_at(destination_parent_fd,stage_name,name,'extraction-stage.'+digest(request_key.encode())[:32],request_digest,root_path=root_path)
        with store.root_directory() as owned_fd:stage_identity=_fd_identity(owned_fd)
        destination=store.snapshot()['project_id'];created_at=timestamp()
        from project_data_fork import fork_records as fork_data
        from project_material_fork import fork_records as fork_material
        original=copy.deepcopy(records);mappings=[]
        allocator=lambda *args:uuid.uuid4().hex
        for builder in (fork_data,fork_material):
            made=builder(original,source.db.dataset_id,source.fingerprint,destination,id_factory=allocator,created_at=created_at)
            records.extend(made['records']);mappings.extend(made['mapping'])
        working=[]
        from project_files import file_id,materialize_captured
        for observed in cache['working_files']:
            file_identity=file_id(destination,observed['kind'],observed['path'])
            version=dict(revision=1,sha256=observed['sha256'],bytes=observed['bytes'],text=observed['text'],adopted_at=created_at,actor_id=source.actor_id)
            records.append(dict(family='project_file',id=file_identity,document=dict(format='project_file_v1',project_id=destination,kind=observed['kind'],path=observed['path'],current=copy.deepcopy(version),history=[version],origin=None)))
            working.append(dict(kind=observed['kind'],path=observed['path'],sha256=observed['sha256'],bytes=observed['bytes'],source_catalog_id=source.db.dataset_id,source_snapshot_sha256=source.fingerprint,destination_id=file_identity,adopted_at=created_at,actor_id=source.actor_id))
        declarations={r['id']:r['document'] for r in records if r['family']=='project_artifact'}
        copied=sorted(v['sha256'] for v in report['artifacts'] if v['state']=='verified')
        missing_regenerable=sorted(v['sha256'] for v in report['artifacts'] if v['state']!='verified' and v['preservation']=='regenerable')
        fork_source=dict(project_id=source.db.dataset_id,checkpoint=source.fingerprint)
        overlay=dict(format='project_fork_v1',source=fork_source,destination_project_id=destination,
            request_key=request_key,request_sha256=fork_digest(fork_input(fork_source,directory,name,request_key)),directory=directory,name=name,
            mapping=sorted(mappings,key=lambda m:(m['family'],m['source_id'],m['source_revision'] or 0,m['destination_id'])),
            archived=sorted([dict(family=r['family'],id=r['id']) for r in original if r['family'] in ARCHIVE_FAMILIES],key=lambda v:(v['family'],v['id'])),
            artifacts=dict(copied=copied,missing_regenerable=missing_regenerable))
        records.append(dict(family='project_fork',id=destination,document=overlay))
        counts={FAMILY:1}
        for r in records:counts[r['family']]=counts.get(r['family'],0)+1
        manifest=dict(format=FORMAT,source=copy.deepcopy(source_ref),selection=selection,report_sha256=expected_report_sha256,request_key=request_key,input_sha256=request_digest,destination_project_id=destination,working_files=working,counts=counts,artifacts=dict(copied=copied,missing_regenerable=missing_regenerable))
        records.append(dict(family=FAMILY,id=destination,document=manifest))
        artifacts=ProjectArtifacts(store)
        for value in declarations.values():
            if value['sha256'] in missing_regenerable:continue
            with source.artifacts.open_verified(value,maximum_bytes=value['bytes']) as fd:artifacts.publish_fd(fd,value,maximum_bytes=value['bytes'])
        with store.root_directory() as fd:materialize_captured(records,destination,fd)
        _validate_candidate(records,destination,artifacts)
        committed=store.commit(records,store.snapshot()['checkpoint'],request_key,request_digest)
        verification=_cold_verify(store,source)
        store.save(committed['checkpoint']);_assert_unchanged(source)
        _rename_noreplace(destination_parent_fd,stage_name,directory);published=True;os.fsync(destination_parent_fd)
        _assert_unchanged(source)
        return _receipt(committed,manifest,verification)
    except BaseException as error:
        if not published and store is not None and committed is not None:
            try:
                final=os.stat(directory,dir_fd=destination_parent_fd,follow_symlinks=False)
                published=(final.st_dev,final.st_ino)==stage_identity
            except FileNotFoundError:pass
            except OSError:
                failure=WorkbenchError('Extraction publication outcome cannot be inspected.','unknown',503)
                failure.staging_directory=stage_name
                raise failure from error
        if published:
            failure=WorkbenchError('Extraction was published; acknowledgement requires reconciliation.','unknown',503)
            failure.receipt=dict(committed=True,selected=False,project_id=committed['project_id'],checkpoint=committed['checkpoint'],request_key=request_key,directory=directory)
            raise failure from error
        error.staging_directory=stage_name
        raise
    finally:
        if artifacts is not None:artifacts.close()
        if store is not None:store.close()
