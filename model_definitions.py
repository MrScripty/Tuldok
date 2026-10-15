"""Inert model definitions and exact retained inference-policy/source material.

Pipeline owns execution configuration; Runs owns fitted values and weights.
Publication never imports project code, loads a model or starts a process.
"""
from access import authorized
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import uuid

import agent_api
from metadata import _sync_directory
from pipeline import closed, digest, identifier
from workbench import WorkbenchError, encode

MAX_INTEGER = 2**53-1
MAX_DOCUMENT = 256*1024
MAX_SOURCE_BYTES = 8*1024*1024
MAX_SOURCE_FILES = 64
SHA = re.compile('[a-f0-9]{64}')


def natural(value, name, minimum=0, maximum=MAX_INTEGER):
    if type(value) is not int or not minimum <= value <= maximum:
        raise WorkbenchError(name+' must be an integer within its declared bounds.')
    return value


def text(value, name, maximum=120):
    if (type(value) is not str or not value.strip() or len(value)>maximum or
            any(ord(c)<32 or ord(c)==127 or 0xD800<=ord(c)<=0xDFFF for c in value)):
        raise WorkbenchError(name+' must be bounded nonempty text without controls.')
    return value


def checked_json(value, maximum=MAX_DOCUMENT):
    try:
        raw=agent_api.encoded(value)
        if len(raw)>maximum:
            raise WorkbenchError('Model-development document exceeds its byte bound.')
        return agent_api.decode(raw)
    except (agent_api.AgentAPIError, ValueError, TypeError, RecursionError):
        raise WorkbenchError('Model-development document must be bounded strict JSON.') from None


def retained_json(raw, maximum=MAX_DOCUMENT):
    try:
        if type(raw) is not str or len(raw.encode('utf-8'))>maximum:
            raise ValueError()
        return agent_api.decode(raw)
    except (agent_api.AgentAPIError,ValueError,UnicodeError):
        raise WorkbenchError('Stored model-development JSON is invalid.','unavailable',409) from None


def reference(value, kind, catalog_id):
    revision=kind in ('task','trainer','profile','selection_policy','model')
    closed(value,('kind','catalog_id','id','sha256',*(['revision'] if revision else [])))
    if value['kind']!=kind or value['catalog_id']!=catalog_id:
        raise WorkbenchError('Reference kind or catalog differs.')
    if type(value['sha256']) is not str or not SHA.fullmatch(value['sha256']):
        raise WorkbenchError('Reference requires an exact SHA256.')
    if kind in ('recipe_material','release','runtime'):
        if value['id']!=value['sha256']:
            raise WorkbenchError('Content-addressed reference identity differs.')
    elif kind in ('model','trial','candidate','evidence'):
        identifier(value['id'])
    else:
        text(value['id'],'Definition ID',64)
    if revision:natural(value['revision'],'Reference revision',1)
    return copy.deepcopy(value)


def blob(raw, name, media_type='application/json'):
    return {'name':name,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'media_type':media_type}


def blob_identity(value):
    return (value.st_dev,value.st_ino,value.st_mode,value.st_nlink,value.st_uid,
            value.st_gid,value.st_size,value.st_mtime_ns,value.st_ctime_ns)


def owned_inventory(root, material_sha256, names):
    """Lightweight identity proof for previously hashed flat owner files."""
    root_fd=child=None
    try:
        root_fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        child=os.open(material_sha256,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=root_fd)
        if set(os.listdir(child))!=set(names):raise WorkbenchError('Retained inventory changed.','unavailable',409)
        result={}
        for name in names:
            if type(name) is not str or not re.fullmatch(r'[a-z][a-z0-9_.-]{0,79}',name):
                raise WorkbenchError('Invalid retained filename.')
            value=os.stat(name,dir_fd=child,follow_symlinks=False)
            if not stat.S_ISREG(value.st_mode) or value.st_nlink!=1:
                raise WorkbenchError('Retained file custody changed.','unavailable',409)
            result[name]=blob_identity(value)
        return {'directory':blob_identity(os.fstat(child)),'files':result}
    except OSError:
        raise WorkbenchError('Retained inventory is unavailable.','unavailable',409) from None
    finally:
        if child is not None:os.close(child)
        if root_fd is not None:os.close(root_fd)


def read_owned_blob(root, material_sha256, item, maximum, *, with_identity=False):
    """Read a flat owner inventory without following links or trusting row sizes."""
    closed(item, ('name','sha256','bytes','media_type'))
    natural(item['bytes'],'Blob bytes',0,maximum)
    if (type(material_sha256) is not str or not SHA.fullmatch(material_sha256) or
            type(item['name']) is not str or not re.fullmatch(r'[a-z][a-z0-9_.-]{0,79}',item['name']) or
            type(item['sha256']) is not str or not SHA.fullmatch(item['sha256'])):
        raise WorkbenchError('Invalid retained blob identity.')
    directory=None;child=None
    try:
        directory=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        child=os.open(material_sha256,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory)
        fd=os.open(item['name'],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=child)
        with os.fdopen(fd,'rb') as source:
            before=os.fstat(source.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size!=item['bytes'] or before.st_nlink!=1:
                raise WorkbenchError('Retained blob is not an owned bounded regular file.','unavailable',409)
            raw=source.read(item['bytes']+1);after=os.fstat(source.fileno())
            if blob_identity(before)!=blob_identity(after) or len(raw)!=item['bytes'] or hashlib.sha256(raw).hexdigest()!=item['sha256']:
                raise WorkbenchError('Retained blob identity differs.','unavailable',409)
            return (raw,blob_identity(after)) if with_identity else raw
    except OSError:
        raise WorkbenchError('Retained blob is unavailable.','unavailable',409) from None
    finally:
        if child is not None:os.close(child)
        if directory is not None:os.close(directory)


class ModelDefinitions:
    def __init__(self,dataset):
        self.dataset=dataset;self.access=dataset.access;self.db=dataset.db;self.lock=dataset.lock
        self.path=dataset.path/'model-materials';self.path.mkdir(mode=0o700,exist_ok=True)

    def _draft(self,value):
        value=checked_json(value)
        closed(value,('format','id','revision','name','task','kind','specification','source_selector',
                      'preprocessing_policy','output_policy'))
        if value['format']!='model_draft_v1' or value['kind'] not in ('template','captured_source'):
            raise WorkbenchError('Unsupported model definition.','unsupported',400)
        identifier(value['id']);natural(value['revision'],'Model revision',1);text(value['name'],'Model name')
        reference(value['task'],'task',self.db.dataset_id)
        for key in ('specification','preprocessing_policy','output_policy'):
            if type(value[key]) is not dict:raise WorkbenchError(key+' must be an object.')
        if value['kind']=='captured_source':
            selector=value['source_selector'];closed(selector,('project_id','recipe_id','expected_sha256'))
            identifier(selector['project_id']);text(selector['recipe_id'],'Recipe ID',64)
            if type(selector['expected_sha256']) is not str or not SHA.fullmatch(selector['expected_sha256']):
                raise WorkbenchError('Source selector requires the exact declared recipe SHA256.')
        elif value['source_selector'] is not None:
            raise WorkbenchError('A template does not select external project source.')
        return value

    def _get(self,model_id):
        identifier(model_id)
        row=self.db.execute('SELECT revision,document FROM model_definition_drafts WHERE id=%s',(model_id,)).fetchone()
        if row is None:raise WorkbenchError('Model definition not found.','not_found',404)
        result=self._draft(retained_json(row['document']))
        if result['id']!=model_id or result['revision']!=row['revision']:
            raise WorkbenchError('Stored model identity differs.','unavailable',409)
        return result

    @authorized('inspect','models.get')
    def get(self,model_id):
        with self.lock:return self._get(model_id)

    @authorized('inspect','models.list')
    def list(self,*,cursor=None,limit=20):
        natural(limit,'Page limit',1,20)
        if cursor is not None:identifier(cursor)
        with self.lock:
            rows=self.db.execute('SELECT id FROM model_definition_drafts WHERE id>%s ORDER BY id LIMIT %s',
                                 (cursor or '',limit+1)).fetchall()
            return {'models':[self._get(row[0]) for row in rows[:limit]],'limit':limit,
                    'next_cursor':rows[limit-1][0] if len(rows)>limit else None}

    @authorized('edit','models.create')
    def create(self,body):
        closed(body,('name','task','kind','specification','source_selector','preprocessing_policy','output_policy'))
        value=self._draft(dict(body,format='model_draft_v1',id=uuid.uuid4().hex,revision=1))
        with self.lock,self.db.transaction():
            self.access.require('edit','models.create')
            self.db.execute('INSERT INTO model_definition_drafts VALUES(%s,%s,%s)',(value['id'],1,encode(value)))
            self.access.audit('models.create',value['id'],{'revision':1,'document_sha256':digest(value)})
        return value

    @authorized('edit','models.save')
    def save(self,model_id,body):
        closed(body,('revision','document'));natural(body['revision'],'Model revision',1)
        value=self._draft(body['document'])
        if value['id']!=model_id or value['revision']!=body['revision']:
            raise WorkbenchError('Model identity/revision differs.')
        with self.lock,self.db.transaction():
            self.access.require('edit','models.save',model_id)
            current=self._get(model_id)
            if current['revision']!=body['revision']:raise WorkbenchError('Model changed. Reload.','stale',409)
            value['revision']=natural(value['revision']+1,'Model revision',1)
            self.db.execute('UPDATE model_definition_drafts SET revision=%s,document=%s WHERE id=%s',
                            (value['revision'],encode(value),model_id))
            self.access.audit('models.save',model_id,{'revision':value['revision'],'document_sha256':digest(value)})
        return value

    def _sources(self,draft):
        if draft['kind']=='template':
            # New template integrations must supply an owned, inert qualification seam.
            resolve=getattr(self.dataset.pipelines,'model_template',None)
            if resolve is None:
                raise WorkbenchError('Model template is not yet qualified by its trainer.','unsupported',409)
            return resolve(draft)
        selector=draft['source_selector']
        import recipe_contract
        inspected=recipe_contract.inspect_recipe(self.dataset.projects,selector['project_id'],
                                                 selector['recipe_id'],selector['expected_sha256'])
        sources=self.dataset.projects.read_recipe_sources(selector['project_id'],inspected['definition']['sources'])
        raw,receipt=self.dataset.projects.read_recipe_reference(selector['project_id'],selector['recipe_id'],
                                                                selector['expected_sha256'])
        sources[receipt['path']]=raw
        if not 1<=len(sources)<=MAX_SOURCE_FILES or sum(map(len,sources.values()))>MAX_SOURCE_BYTES:
            raise WorkbenchError('Model source closure exceeds64 files/8MiB including its definition.')
        return inspected['definition']['entrypoint'],sources

    @authorized('edit','models.publish')
    def publish(self,model_id,body):
        closed(body,('revision',),('reconcile_capture',));natural(body['revision'],'Model revision',1)
        reconcile=body.get('reconcile_capture',False)
        if type(reconcile) is not bool:raise WorkbenchError('Capture reconciliation must be boolean.')
        if reconcile:self.access.require('edit','models.reconcile_capture',model_id,owner_only=True)
        identifier(model_id)
        with self.lock:
            prior=self.db.execute('SELECT document FROM model_materials WHERE id=%s AND revision=%s',
                                  (model_id,body['revision'])).fetchone()
        if prior:
            return self.material(retained_json(prior[0])['ref'],verify=True)
        draft=self.get(model_id)
        if draft['revision']!=body['revision']:raise WorkbenchError('Model changed. Reload.','stale',409)
        entrypoint,sources=self._sources(draft)
        payloads={};material={'format':'model_material_v1','catalog_id':self.db.dataset_id,
            'model_definition_id':model_id,'model_definition_revision':draft['revision'],'task':draft['task'],
            'kind':draft['kind'],'entrypoint':entrypoint,'source_selector':draft['source_selector'],'source_closure':[]}
        for key in ('specification','preprocessing_policy','output_policy'):
            raw=agent_api.encoded(draft[key]);name=key+'.json';payloads[name]=raw;material[key]=blob(raw,name)
        for number,(import_path,raw) in enumerate(sorted(sources.items())):
            name=f'source-{number:04d}.bin';payloads[name]=raw
            material['source_closure'].append({'import_path':import_path,'blob':blob(raw,name,'application/octet-stream')})
        material=checked_json(material);sha=digest(material)
        retained={'ref':{'kind':'model','catalog_id':self.db.dataset_id,'id':model_id,
                         'revision':draft['revision'],'sha256':sha},'material':material}
        staging=Path(tempfile.mkdtemp(prefix='.model-',dir=self.path));target=self.path/sha
        published=False
        try:
            for name,raw in payloads.items():
                with (staging/name).open('xb') as handle:
                    handle.write(raw);handle.flush();os.fchmod(handle.fileno(),0o400);os.fsync(handle.fileno())
            _sync_directory(staging)
            orphan=None
            if reconcile and target.exists():
                files={name:self._read_blob(retained['ref'],blob(raw,name),with_identity=True)[1] for name,raw in payloads.items()}
                orphan=owned_inventory(self.path,sha,payloads)
                if orphan['files']!=files:raise WorkbenchError('Orphan capture changed after hashing.','unavailable',409)
            with self.lock,self.db.transaction():
                if self._get(model_id)!=draft:raise WorkbenchError('Model changed during capture.','stale',409)
                prior=self.db.execute('SELECT document FROM model_materials WHERE id=%s AND revision=%s',
                                      (model_id,draft['revision'])).fetchone()
                if prior:
                    if retained_json(prior[0])!=retained:raise WorkbenchError('Published model source changed.','stale',409)
                    return retained
                self.access.require('edit','models.publish',model_id,owner_only=reconcile)
                if target.exists():
                    if not reconcile:
                        raise WorkbenchError('Unreferenced model capture requires owner reconciliation.','unavailable',409)
                    if orphan!=owned_inventory(self.path,sha,payloads):
                        raise WorkbenchError('Orphan capture changed during reconciliation.','unavailable',409)
                else:
                    os.rename(staging,target);published=True;_sync_directory(self.path)
                    self.db.on_rollback(lambda:shutil.rmtree(target,ignore_errors=True))
                self.db.execute('INSERT INTO model_materials VALUES(%s,%s,%s,%s)',
                    (model_id,draft['revision'],sha,encode(retained)))
                self.access.audit('models.publish',model_id,{'revision':draft['revision'],'material_sha256':sha})
            return retained
        finally:
            # Unknown commit retains the published closure; only private unowned staging is removed.
            if not published:shutil.rmtree(staging,ignore_errors=True)

    @authorized('inspect','models.material')
    def material(self,ref,*,verify=False):
        ref=reference(ref,'model',self.db.dataset_id)
        with self.lock:
            row=self.db.execute('SELECT document FROM model_materials WHERE id=%s AND revision=%s AND sha256=%s',
                                (ref['id'],ref['revision'],ref['sha256'])).fetchone()
        if row is None:raise WorkbenchError('Published model material not found.','not_found',404)
        value=checked_json(retained_json(row[0]));closed(value,('ref','material'))
        if value['ref']!=ref or digest(value['material'])!=ref['sha256']:
            raise WorkbenchError('Published model identity differs.','unavailable',409)
        material=value['material']
        closed(material,('format','catalog_id','model_definition_id','model_definition_revision','task','kind',
                         'entrypoint','source_selector','source_closure','specification','preprocessing_policy','output_policy'))
        if (material['format']!='model_material_v1' or material['catalog_id']!=self.db.dataset_id or
                material['model_definition_id']!=ref['id'] or material['model_definition_revision']!=ref['revision'] or
                material['kind'] not in ('template','captured_source')):
            raise WorkbenchError('Published model definition differs.','unavailable',409)
        reference(material['task'],'task',self.db.dataset_id)
        self._draft({'format':'model_draft_v1','id':material['model_definition_id'],
            'revision':material['model_definition_revision'],'name':'Retained model','task':material['task'],
            'kind':material['kind'],'specification':{},'source_selector':material['source_selector'],
            'preprocessing_policy':{},'output_policy':{}})
        from projects import relative_path
        relative_path(material['entrypoint'])
        if type(material['source_closure']) is not list or not 1<=len(material['source_closure'])<=MAX_SOURCE_FILES:
            raise WorkbenchError('Published model source inventory is invalid.','unavailable',409)
        paths=[];names=[]
        for item in material['source_closure']:
            closed(item,('import_path','blob'));relative_path(item['import_path']);paths.append(item['import_path'])
            self._blob(item['blob']);names.append(item['blob']['name'])
        for key in ('specification','preprocessing_policy','output_policy'):
            self._blob(material[key]);names.append(material[key]['name'])
            if material[key]['name']!=key+'.json':raise WorkbenchError('Model policy blob name differs.','unavailable',409)
        if len(set(paths))!=len(paths) or len(set(names))!=len(names) or material['entrypoint'] not in paths:
            raise WorkbenchError('Model source mapping differs.','unavailable',409)
        if sum(item['blob']['bytes'] for item in material['source_closure'])>MAX_SOURCE_BYTES:
            raise WorkbenchError('Published source closure exceeds its byte bound.','unavailable',409)
        if verify:
            for item in [*(value['material'][key] for key in ('specification','preprocessing_policy','output_policy')),
                         *(source['blob'] for source in value['material']['source_closure'])]:
                self._read_blob(ref,item)
        return value

    @staticmethod
    def _blob(item):
        closed(item,('name','sha256','bytes','media_type'))
        natural(item['bytes'],'Blob bytes',0,MAX_SOURCE_BYTES);text(item['media_type'],'Media type',80)
        if (type(item['name']) is not str or not re.fullmatch(
                r'(?:source-\d{4}\.bin|specification\.json|preprocessing_policy\.json|output_policy\.json)',item['name']) or
                type(item['sha256']) is not str or not SHA.fullmatch(item['sha256'])):
            raise WorkbenchError('Invalid model blob identity.')

    @authorized('inspect','models.read_blob')
    def read_blob(self,ref,item):
        retained=self.material(ref)
        inventory=[*(retained['material'][key] for key in ('specification','preprocessing_policy','output_policy')),
                   *(source['blob'] for source in retained['material']['source_closure'])]
        if item not in inventory:
            raise WorkbenchError('Model blob is absent from the retained inventory.','not_found',404)
        return self._read_blob(ref,item)

    def _read_blob(self,ref,item,*,with_identity=False):
        reference(ref,'model',self.db.dataset_id)
        self._blob(item)
        return read_owned_blob(self.path,ref['sha256'],item,MAX_SOURCE_BYTES,with_identity=with_identity)
