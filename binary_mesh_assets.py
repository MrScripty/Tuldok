"""Bounded staging and dispatch into existing immutable mesh ownership."""
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
import subprocess
import sys
import tempfile
import threading
import time
import weakref

import binary_mesh_core as core
from immutable_assets import ImmutableAssets
from workbench import WorkbenchError, encode, strings, text_value

CHUNK_BYTES=64*1024
MAX_REQUEST=128*1024
EXPIRY_SECONDS=600
_workers=threading.Lock()
_upload_slot=threading.Lock()
_managers=weakref.WeakKeyDictionary()
_manager_lock=threading.Lock()


class Stage:
    """One dataset-owned, flock-guarded staging directory; safe crash recovery."""
    MARKER=b'Tuldok source-bound binary mesh staging v1\n'

    def __init__(self,dataset_path):
        if sys.platform!='linux':raise WorkbenchError('Bounded binary mesh acquisition requires the qualified Linux resource worker.','unsupported')
        import fcntl
        root=Path(dataset_path)/'.tuldok-binary-mesh-staging-v1'
        try:root.mkdir(mode=0o700);created=True
        except FileExistsError:created=False
        if root.is_symlink() or not root.is_dir():invalid('staging ownership directory changed.')
        marker=root/'owner'
        if created:
            with marker.open('xb') as stream:stream.write(self.MARKER)
        if marker.is_symlink() or not marker.is_file() or marker.stat().st_size!=len(self.MARKER) or marker.read_bytes()!=self.MARKER:
            invalid('staging ownership marker missing or changed; no cleanup attempted.')
        self.fd=os.open(root/'lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600);self.directory=None
        try:
            lock_info=os.fstat(self.fd)
            if not stat.S_ISREG(lock_info.st_mode) or lock_info.st_nlink!=1:
                invalid('staging lock must be a private regular file; no cleanup attempted.')
            try:fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as error:raise WorkbenchError('Another process owns this dataset binary upload.','conflict',409) from error
            # Exact private shape only. Never follow links or remove foreign files.
            stale=[]
            for child in root.iterdir():
                if child.name in ('owner','lock'):continue
                if not core.re.fullmatch(r'upload-[a-f0-9]{64}',child.name) or child.is_symlink() or not child.is_dir():
                    invalid('unexpected staging entry; no recovery cleanup attempted.')
                entries=list(child.iterdir())
                if entries and (len(entries)!=1 or entries[0].name!='input.zip' or entries[0].is_symlink() or not entries[0].is_file()):
                    invalid('unexpected staging contents; no recovery cleanup attempted.')
                stale.append(child)
            for child in stale:(child/'input.zip').unlink(missing_ok=True);child.rmdir()
            self.directory=root/('upload-'+secrets.token_hex(32));self.directory.mkdir(mode=0o700)
            self.path=self.directory/'input.zip';self.path.touch(mode=0o600)
        except BaseException:
            if self.directory:
                (self.directory/'input.zip').unlink(missing_ok=True);self.directory.rmdir();self.directory=None
            os.close(self.fd);self.fd=None;raise

    def cleanup(self):
        try:
            if self.directory:
                self.path.unlink(missing_ok=True);self.directory.rmdir();self.directory=None
        finally:
            if self.fd is not None:os.close(self.fd);self.fd=None


def invalid(message):
    raise WorkbenchError('Invalid binary mesh acquisition: '+message)


def is_binary(record):
    metadata=record.get('mesh')
    return isinstance(metadata,dict) and isinstance(metadata.get('manifest'),dict) and metadata['manifest'].get('format')==core.FORMAT


def validate_path(path):
    if sys.platform!='linux':raise WorkbenchError('Bounded binary mesh acquisition requires the qualified Linux resource worker.','unsupported')
    if not _workers.acquire(blocking=False):raise WorkbenchError('Binary mesh validator is busy. Retry deliberately after it finishes.','conflict',409)
    try:
        with tempfile.TemporaryFile() as output:
            try:
                process=subprocess.run([sys.executable,str(Path(__file__).with_name('binary_mesh_worker.py')),str(path)],
                    stdout=output,stderr=subprocess.PIPE,timeout=core.WORKER_WALL_SECONDS,env=None)
            except subprocess.TimeoutExpired as error:
                raise WorkbenchError('Binary mesh validation exceeded the45second wall limit.') from error
            output.seek(0);raw=output.read(core.RESULT_BYTES+1)
            if not 0<len(raw)<=core.RESULT_BYTES:invalid('worker output exceeded its bound or worker failed.')
            try:result=core.strict_json(raw,core.RESULT_BYTES)
            except (ValueError,UnicodeError) as error:raise WorkbenchError('Binary mesh validation worker failed.') from error
            if process.returncode or 'error' in result:invalid(result.get('error','validator resource limit reached.'))
            return result
    finally:_workers.release()


def validate_bytes(raw):
    if not 0<len(raw)<=core.BUNDLE_BYTES:invalid('complete bundle exceeds12MiB.')
    with tempfile.TemporaryDirectory(prefix='tuldok-binary-validation-') as directory:
        path=Path(directory)/'input.zip';path.write_bytes(raw)
        result=validate_path(path)
    if result['bundle_bytes']!=len(raw) or result['bundle_sha256']!=core.sha(raw):invalid('worker source association changed.')
    return result


class BinaryMeshAssets(ImmutableAssets):
    def __init__(self,workbench):
        super().__init__(workbench,kind='mesh',task='mesh_geometry',maximum=core.BUNDLE_BYTES,default_name='Source-bound binary mesh')

    def admit(self,raw,result,body):
        if result['bundle_sha256']!=core.sha(raw) or result['bundle_bytes']!=len(raw):invalid('validated bundle changed.')
        return super().admit({'bundle':raw,'metadata':result['metadata']},body,
            {'method':'binary_mesh_import','format':core.FORMAT,'geometry_sha256':result['metadata']['manifest']['geometry_sha256'],
             'authoritative_source':result['metadata']['manifest']['source']})

    def checked(self,record):
        raw,mime=super().asset(record)
        result=validate_bytes(raw)
        if encode(result['metadata'])!=encode({key:value for key,value in record['mesh'].items() if key!='bundle_bytes'}):
            raise WorkbenchError('Binary mesh immutable source or metadata changed.','conflict',409)
        return raw,mime,result

    def asset(self,record):
        raw,mime,_=self.checked(record);return raw,mime

    def inspect(self,record_id):
        with self.workbench.lock:record=self.workbench._get(record_id)
        _,_,result=self.checked(record);meta=result['metadata']
        return {'id':record_id,'content_hash':record['content_hash'],'bounds':meta['bounds'],
            'units':meta['manifest']['units'],'coordinate_system':meta['manifest']['coordinate_system'],
            'triangle_count':meta['triangle_count'],'sample_count':len(result['triangles']),'triangles':result['triangles']}


class UploadManager:
    def __init__(self,workbench):
        self.workbench=weakref.ref(workbench);self.lock=threading.Lock();self.session=None

    def _clear(self):
        if self.session:
            self.session['timer'].cancel()
            try:self.session['directory'].cleanup()
            finally:self.session=None;_upload_slot.release()

    def _timer_expire(self,token):
        with self.lock:
            if self.session and self.session['token']==token:self._clear()

    def _expire(self):
        if self.session and time.monotonic()-self.session['started']>=EXPIRY_SECONDS:self._clear()

    def close(self):
        with self.lock:self._clear()

    def _session(self,body,keys):
        core.exact(body,keys,'upload request');self._expire()
        if not self.session or not secrets.compare_digest(str(body.get('token')),self.session['token']):
            raise WorkbenchError('Binary mesh upload expired or unavailable. Inspect the collection before restarting.','unavailable',404)
        return self.session

    def start(self,body):
        core.require(type(body) is dict and not set(body)-{'bytes','sha256','name','groups','parents','rights'},'upload fields mismatch')
        core.integer(body.get('bytes'),1,core.BUNDLE_BYTES,'upload size')
        core.require(type(body.get('sha256')) is str and core.HASH.fullmatch(body['sha256']),'upload SHA256 required')
        options={'name':text_value(body.get('name','Source-bound binary mesh'),'Name'),
            'rights':text_value(body.get('rights','unknown'),'Rights / permission note',1000),
            'groups':strings(body.get('groups',[]),'Protected groups'), 'parents':strings(body.get('parents',[]),'Parent IDs')}
        with self.lock:
            self._expire()
            if self.session:raise WorkbenchError('One binary mesh upload is already active; finish or cancel it first.','conflict',409)
            if not _upload_slot.acquire(blocking=False):raise WorkbenchError('Binary mesh upload budget is busy.','conflict',409)
            try:
                directory=Stage(self.workbench().dataset.path);path=directory.path
                token=secrets.token_hex(32);timer=threading.Timer(EXPIRY_SECONDS,self._timer_expire,args=(token,));timer.daemon=True
                self.session={'directory':directory,'path':path,'token':token,'bytes':body['bytes'],
                    'sha256':body['sha256'],'offset':0,'hash':hashlib.sha256(),'started':time.monotonic(),'options':options,'timer':timer}
                timer.start()
            except BaseException:
                if self.session:self._clear()
                else:_upload_slot.release()
                raise
            return {'token':self.session['token'],'offset':0,'chunk_bytes':CHUNK_BYTES,'expires_seconds':EXPIRY_SECONDS}

    def chunk(self,body):
        with self.lock:
            session=self._session(body,('token','offset','data'))
            try:
                core.require(type(body['offset']) is int and body['offset']==session['offset'],'chunk offset mismatch')
                core.require(type(body['data']) is str and len(body['data'])<=(CHUNK_BYTES+2)//3*4,'chunk size exceeded')
                data=base64.b64decode(body['data'],validate=True)
                core.require(0<len(data)<=CHUNK_BYTES and session['offset']+len(data)<=session['bytes'],'chunk bounds mismatch')
                with session['path'].open('ab') as output:output.write(data)
                session['hash'].update(data);session['offset']+=len(data)
                return {'token':session['token'],'offset':session['offset']}
            except BaseException:self._clear();raise

    def cancel(self,body):
        with self.lock:
            self._session(body,('token',));self._clear();return {'cancelled':True}

    def finish(self,body):
        with self.lock:
            session=self._session(body,('token',))
            try:
                core.require(session['offset']==session['bytes'] and session['hash'].hexdigest()==session['sha256'],'complete upload size/hash mismatch')
                result=validate_path(session['path'])
                with session['path'].open('rb') as stream:raw=stream.read(core.BUNDLE_BYTES+1)
                if len(raw)!=session['bytes'] or core.sha(raw)!=session['sha256']:invalid('staged bundle changed after validation.')
                workbench=self.workbench()
                if workbench is None:invalid('dataset owner unavailable.')
                return BinaryMeshAssets(workbench).admit(raw,result,session['options'])
            finally:self._clear()


def manager(workbench):
    with _manager_lock:
        if workbench not in _managers:_managers[workbench]=UploadManager(workbench)
        return _managers[workbench]


def close(workbench):
    with _manager_lock:owner=_managers.get(workbench)
    if owner:owner.close()


def route(workbench,action,body):
    try:return getattr(manager(workbench),action)(body)
    except core.BinaryMeshError as error:raise WorkbenchError(str(error)) from error
