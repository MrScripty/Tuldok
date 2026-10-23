"""Explicit current source bindings, separate from portable snapshot facts.

Opening a project never restores workspace_projects. Only an authenticated owner
registering an anchored current manifest can create that disposable binding.
Canonical receipts describe retained facts; they are not filesystem capabilities.
"""
import copy
from datetime import datetime
import hashlib
import os

from project_material import decode_records as material_records
from project_session import ProjectSessionError, REQUEST_KEY
from projects import (DATA_LIMIT, ID, INSPECTION_LIMIT, MANIFEST_LIMIT, NAME, SHA, decode,
                      decode_retained_snapshot, manifest, relative_path, text)
from workbench import WorkbenchError, encode, timestamp

RESULT_FIELDS = frozenset(('origin_catalog_id','project_id','manifest_sha256','name',
                           'schema_version','actor_id','registered_at'))


def _closed(value, fields):
    if type(value) is not dict or set(value)!=set(fields):
        raise WorkbenchError('Invalid explicit source operation fields.')


def _identity(value, pattern, label):
    if type(value) is not str or not pattern.fullmatch(value):
        raise WorkbenchError('Invalid source '+label+'.')
    return value


def _summary(saved, origin):
    return dict(origin_catalog_id=origin,project_id=saved['id'],
                manifest_sha256=saved['manifest_sha256'],name=saved['name'],
                schema_version=saved['manifest']['schema_version'])


def validate_operation_result(operation,result,records=None):
    """Validate the fixed source receipt against its exact retained snapshot."""
    if operation!='source.register':return False
    try:
        _closed(result,RESULT_FIELDS)
        for key in ('origin_catalog_id','project_id','actor_id'):_identity(result[key],ID,key)
        _identity(result['manifest_sha256'],SHA,'manifest SHA256')
        text(result['name'],'Source project name',120)
        if type(result['schema_version']) is not int or result['schema_version'] not in (1,2):
            raise WorkbenchError('Unsupported source registration schema.','unsupported',400)
        if type(result['registered_at']) is not str or len(result['registered_at'])>80:
            raise WorkbenchError('Source registration requires an attributed timestamp.')
        if datetime.fromisoformat(result['registered_at']).utcoffset() is None:
            raise WorkbenchError('Source registration timestamp requires an offset.')
        if records is not None:
            document=material_records(records).get(('project_snapshot',result['origin_catalog_id']+'.'+result['manifest_sha256']))
            expected={key:result[key] for key in ('origin_catalog_id','project_id','manifest_sha256','name','schema_version')}
            if document is None or _summary(document['value'],document['origin_catalog_id'])!=expected:
                raise WorkbenchError('Source receipt differs from its exact retained snapshot.')
        return True
    except WorkbenchError:raise
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError):
        raise WorkbenchError('Malformed retained source operation result.') from None


class SourceAdapter:
    def __init__(self,projection):
        self.projection=projection
        self.session=projection.session
        self.db,self.access=self.session.db,self.session.access
        self.sources,self.materials,self.data=projection.sources,projection.materials,projection.data

    @staticmethod
    def _mutation_identity(expected_checkpoint,key):
        _identity(expected_checkpoint,SHA,'expected checkpoint')
        _identity(key,REQUEST_KEY,'request key')

    @staticmethod
    def _snapshot_reference(snapshot):
        _closed(snapshot,('origin_catalog_id','project_id','manifest_sha256'))
        for field in ('origin_catalog_id','project_id'):_identity(snapshot[field],ID,field)
        _identity(snapshot['manifest_sha256'],SHA,'manifest SHA256')
        return snapshot

    def _read_registration(self,body):
        _closed(body,('root','manifest_path'))
        root=_identity(body['root'],NAME,'root alias');path=relative_path(body['manifest_path'])
        entry=self.sources.roots.get(root)
        if entry is None:raise WorkbenchError('Choose a currently configured source root.','unavailable',409)
        self.access.require('inspect','projects.open')
        try:
            actual=os.fstat(entry[0]);identity=[actual.st_dev,actual.st_ino]
            if identity!=entry[1]:raise WorkbenchError('Configured source root identity changed.','stale',409)
            # Reuse Projects' anchored before/after identity and no-follow read.
            raw=self.sources._read_snapshot_file(dict(root=root,root_identity=identity),path,MANIFEST_LIMIT)
        except OSError:
            raise WorkbenchError('Current source manifest is unavailable.','unavailable',409) from None
        value=manifest(decode(raw))
        saved=dict(id=value['id'],name=value['name'],root=root,root_identity=identity,
                   manifest_path=path,manifest_sha256=hashlib.sha256(raw).hexdigest(),manifest=value)
        return decode_retained_snapshot(saved),raw

    def _bind(self,saved,raw):
        if not self.db.in_transaction:raise RuntimeError('Source binding requires its outer SQL transaction.')
        if self.sources._read_snapshot_file(saved,saved['manifest_path'],MANIFEST_LIMIT)!=raw:
            raise WorkbenchError('Source manifest changed before current registration.','stale',409)
        row=self.db.execute('SELECT document FROM workspace_projects WHERE id=%s',(saved['id'],)).fetchone()
        if row is not None:
            prior=decode_retained_snapshot(decode(row[0].encode()))
            if prior['manifest_sha256']!=saved['manifest_sha256']:
                raise WorkbenchError('This source ID already names a different current snapshot.','conflict',409)
            if prior==saved:return
            # Explicit same-manifest registration can renew a moved root. The
            # original canonical registration facts are never rewritten.
            self.db.execute('UPDATE workspace_projects SET document=%s WHERE id=%s',(encode(saved),saved['id']))
        else:self.db.execute('INSERT INTO workspace_projects VALUES(%s,%s)',(saved['id'],encode(saved)))

    def register(self,body,expected_checkpoint,key):
        self._mutation_identity(expected_checkpoint,key)
        with self.access.lock,self.session.lock,self.db.lock:
            actor=self.access.require('edit','source.register',owner_only=True)
            self.session.check()
            saved,raw=self._read_registration(body)
            origin=self.session.snapshot['project_id'];invoked=False
            def invoke():
                nonlocal invoked
                invoked=True;self._bind(saved,raw)
                return dict(_summary(saved,origin),actor_id=actor.actor_id,registered_at=timestamp())
            def capture(result,before):
                record=self.materials.capture_snapshot(saved,raw,catalog_id=origin)
                return dict(records=[*self.materials.declarations(record),record],result=result)
            result=self.session.mutate('source.register',saved['id'],copy.deepcopy(body),expected_checkpoint,key,invoke,capture)
            if any(result[field]!=value for field,value in _summary(saved,origin).items()):
                raise WorkbenchError('Current source manifest differs from the acknowledged registration.','stale',409)
            if not invoked:
                # Replay itself does not run invoke. This explicit owner action
                # may renew a verified current binding after a cold Open; it is
                # not a new historical registration event or canonical write.
                try:
                    with self.db.transaction():self._bind(saved,raw)
                except WorkbenchError:raise
                except BaseException as error:
                    self.session.available=False
                    failure=ProjectSessionError('Source registration was acknowledged; reopen before binding its current root.',
                                                'projection_unavailable',503)
                    snapshot=self.session.snapshot
                    failure.receipt=dict(committed=True,selected=True,project_id=snapshot['project_id'],
                                         checkpoint=snapshot['checkpoint'],request_key=key)
                    raise failure from error
            return result

    def references(self,snapshotref,offset=0,limit=40):
        snapshot=self._snapshot_reference(snapshotref)
        if type(offset) is not int or not 0<=offset<=2**53-1 or type(limit) is not int or not 1<=limit<=40:
            raise WorkbenchError('Invalid bounded source reference page.')
        with self.access.lock,self.session.lock,self.db.lock:
            self.access.require('inspect','source.references',snapshot['project_id'])
            self.session.check()
            historical=self.materials.snapshot_ref(snapshot['project_id'],snapshot['manifest_sha256'],
                catalog_id=snapshot['origin_catalog_id'])
            try:current=self.sources._saved(snapshot['project_id'],extensions=True)
            except WorkbenchError as error:
                if error.code=='not_found':
                    raise WorkbenchError('Explicitly register a current source root before inspecting its references.','unavailable',409) from None
                raise
            # Check current binding and exact retained selection before reading
            # even the live manifest. Historical root/path fields grant nothing.
            if not self.sources._bound(current):
                raise WorkbenchError('The selected source has no current root binding.','unavailable',409)
            if current['manifest_sha256']!=snapshot['manifest_sha256'] or current['manifest']!=historical['manifest']:
                raise WorkbenchError('Current source registration differs from the selected snapshot.','stale',409)
            self.sources.read_snapshot_manifest(snapshot['project_id'],snapshot['manifest_sha256'])
            selected=current['manifest']['data'][offset:offset+limit];budget=[INSPECTION_LIMIT]
            items=[self.sources._inspect(current['root'],copy.deepcopy(ref),budget,DATA_LIMIT) for ref in selected]
            self.sources.read_snapshot_manifest(snapshot['project_id'],snapshot['manifest_sha256'])
            self.session.check();self.access.require('inspect','source.references',snapshot['project_id'])
            return dict(items=items,total=len(current['manifest']['data']),offset=offset,limit=limit)

    def import_scientific(self,body,expected_checkpoint,key):
        self._mutation_identity(expected_checkpoint,key)
        _closed(body,('snapshot','reference_id','expected_sha256','document'))
        snapshot=self._snapshot_reference(body['snapshot'])
        _identity(body['reference_id'],NAME,'data reference')
        _identity(body['expected_sha256'],SHA,'data SHA256')
        if type(body['document']) is not dict:raise WorkbenchError('Scientific import metadata must be an object.')
        with self.access.lock,self.session.lock,self.db.lock:
            self.access.require('edit','source.import_scientific',snapshot['project_id'])
            self.session.check()
            historical=self.materials.snapshot_ref(snapshot['project_id'],snapshot['manifest_sha256'],
                catalog_id=snapshot['origin_catalog_id'])
            current,_raw=self.sources.read_snapshot_manifest(snapshot['project_id'],snapshot['manifest_sha256'])
            if current['manifest']!=historical['manifest']:
                raise WorkbenchError('Current source differs from the selected retained snapshot.','stale',409)
            raw,source=self.sources.read_snapshot_data_reference(snapshot['project_id'],body['reference_id'],
                                                               body['expected_sha256'],DATA_LIMIT)
            if source['manifest_sha256']!=snapshot['manifest_sha256']:
                raise WorkbenchError('Current source snapshot changed during capture.','stale',409)
            # ProjectData owns the one canonical mutation and native parser;
            # current rooted reads above never become an imported capability.
            return self.data.import_scientific(raw,copy.deepcopy(body['document']),source,expected_checkpoint,key)
