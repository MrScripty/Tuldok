"""Portable model/source/recipe facts, using their existing semantic owners.

Open decodes inert metadata. Only explicit publication reads projection-local
captures and snapshots their exact bytes before Session publishes a checkpoint.
No runtime is provisioned, captured source imported, or model state loaded here.
"""
import copy
import hashlib
import os
import re
import shutil
import tempfile
from functools import wraps
from datetime import datetime
from pathlib import Path

from workbench import WorkbenchError, timestamp, encode
from model_definitions import (decode_model_draft, decode_model_material, verify_model_closure,
                               reference, natural, retained_json, MAX_SOURCE_BYTES)
from pipeline import decode_graph, decode_recipe_draft, decode_recipe_material, verify_recipe_closure, digest, execution_digest
from project_store import ProjectStoreError

FAMILIES = {
    'model_definition': 'model_definition_history_v1',
    'pipeline_graph': 'pipeline_graph_history_v1',
    'recipe_definition': 'recipe_definition_history_v1',
    'model_material': 'retained_model_material_v1',
    'recipe_material': 'retained_recipe_material_v1',
    'project_snapshot': 'retained_project_snapshot_v1',
    'runtime_material': 'retained_runtime_material_v1',
}
EDITABLE = ('model_definition', 'pipeline_graph', 'recipe_definition')
ID = re.compile(r'^[a-f0-9]{32}$')
SHA = re.compile(r'^[a-f0-9]{64}$')
AUDIT_FIELDS = {'action','target','details','result','actor_id','occurred_at'}
AUDIT_DETAILS = {
    'models.create':('revision','document_sha256'),
    'models.save':('revision','document_sha256'),
    'models.publish':('revision','material_sha256'),
    'pipeline.create':('revision','document_sha256','execution_sha256'),
    'pipeline.create_external':('revision','document_sha256','execution_sha256'),
    'pipeline.save':('revision','document_sha256','execution_sha256'),
    'pipeline.clone':('source_graph_id','revision','document_sha256','execution_sha256'),
    'pipeline.clone_retained':('id','revision','material'),
    'recipes.create':('revision','document_sha256'),
    'recipes.save':('revision','document_sha256'),
    'recipes.material':('recipe_id','revision'),
}
AUDIT_ACTIONS = frozenset(AUDIT_DETAILS)


def _boundary(function):
    @wraps(function)
    def checked(*args, **kwargs):
        try:return function(*args, **kwargs)
        except (WorkbenchError,ProjectStoreError):raise
        except ImportError:
            raise WorkbenchError('Retained material validator is unavailable.','unavailable',409) from None
        except (KeyError, TypeError, ValueError, AttributeError, OverflowError, RecursionError, UnicodeError):
            raise WorkbenchError('Malformed retained material document.','invalid',400) from None
    return checked


def _closed(value, fields, label):
    if type(value) is not dict or set(value) != set(fields):
        raise WorkbenchError('Invalid retained ' + label + ' fields.')


def _catalog(value):
    if type(value) is not str or not ID.fullmatch(value):
        raise WorkbenchError('Invalid retained origin catalog.')
    return value


def _intrinsic(item):
    return {'sha256': item['sha256'], 'bytes': item['bytes']}


def _declaration(item):
    return dict(format='project_artifact_v1', **_intrinsic(item))


def _edges(items, family):
    required = 'execution' if family == 'runtime_material' else 'snapshot_verification' if family == 'project_snapshot' else 'material_verification' if family == 'model_material' else 'composition_verification'
    result=[]
    for item in items:
        runtime_file=family=='runtime_material' and item['name']!='manifest.json'
        role='runtime_file' if runtime_file else 'runtime_manifest' if family=='runtime_material' else 'project_manifest' if family=='project_snapshot' else 'model_source' if family=='model_material' and item['name'].startswith('source-') else 'model_policy' if family=='model_material' else 'recipe_capture' if item['name'].startswith('capture-') else 'recipe_document'
        result.append(dict(name=item['name'],blob=_intrinsic(item),role=role,
                           preservation='regenerable' if runtime_file else 'unique',required_for=[required]))
    return result


def _inventory(family, value):
    if family == 'model_material':
        material = value['material']
        return [*(material[key] for key in ('specification', 'preprocessing_policy', 'output_policy')),
                *(item['blob'] for item in material['source_closure'])]
    if family == 'recipe_material':
        material = value['material']
        return [material['recipe_document'], material['resolved_profile'], *material['captures']]
    return []


def _definition(family, value, catalog_id):
    if family == 'model_definition': return decode_model_draft(value, catalog_id=catalog_id)
    if family == 'recipe_definition': return decode_recipe_draft(value, catalog_id=catalog_id)
    if family == 'pipeline_graph': return copy.deepcopy(decode_graph(value))
    raise WorkbenchError('Unsupported material definition family.', 'unsupported', 409)


def _audit(value):
    _closed(value,AUDIT_FIELDS,'material audit')
    if (value['action'] not in AUDIT_ACTIONS or value['result']!='success' or
            type(value['target']) is not str or not 1<=len(value['target'])<=128 or
            value['actor_id'] is not None and (type(value['actor_id']) is not str or not ID.fullmatch(value['actor_id'])) or
            type(value['occurred_at']) is not str or len(value['occurred_at'])>80):
        raise WorkbenchError('Invalid material audit fact.')
    target_pattern=SHA if value['action']=='recipes.material' else ID
    if not target_pattern.fullmatch(value['target']):raise WorkbenchError('Invalid material audit target.')
    details=value['details'];_closed(details,AUDIT_DETAILS[value['action']],'material action details')
    natural(details['revision'],'Audit revision',1)
    for key,item in details.items():
        if key.endswith('_sha256') and (type(item) is not str or not SHA.fullmatch(item)):
            raise WorkbenchError('Invalid material audit digest.')
        if key in ('id','recipe_id','source_graph_id') and (type(item) is not str or not ID.fullmatch(item)):
            raise WorkbenchError('Invalid material audit source identity.')
    if 'material' in details:
        _catalog(details['material']['catalog_id'])
        reference(details['material'],'recipe_material',details['material']['catalog_id'])
    instant=datetime.fromisoformat(value['occurred_at'])
    if instant.utcoffset() is None:raise WorkbenchError('Material audit requires an offset timestamp.')


def _definition_audit(family,value,audit,catalog_id):
    _audit(audit)
    actions={'model_definition':('models.create','models.save'),
        'recipe_definition':('recipes.create','recipes.save'),
        'pipeline_graph':('pipeline.create','pipeline.create_external','pipeline.save','pipeline.clone','pipeline.clone_retained')}
    if audit['action'] not in actions[family] or audit['target']!=value['id']:
        raise WorkbenchError('Definition audit action or identity differs.')
    details=audit['details']
    if audit['action']=='pipeline.clone_retained':
        _closed(details,('id','revision','material'),'retained clone audit')
        if not ID.fullmatch(details['id']) or value['revision']!=1:
            raise WorkbenchError('Retained clone audit identity differs.')
        natural(details['revision'],'Source recipe revision',1)
        reference(details['material'],'recipe_material',catalog_id)
    elif details.get('revision')!=value['revision']:
        raise WorkbenchError('Definition audit revision differs.')
    if audit['action'].endswith(('.create','.create_external','.clone','.clone_retained')) and value['revision']!=1:
        raise WorkbenchError('Created definition audit must identify its initial revision.')
    if audit['action'].endswith('.save') and value['revision']<2:
        raise WorkbenchError('Saved definition audit requires a successor revision.')
    if 'document_sha256' in details and details['document_sha256']!=digest(value):
        raise WorkbenchError('Definition audit document hash differs.')
    if 'execution_sha256' in details and details['execution_sha256']!=execution_digest(value):
        raise WorkbenchError('Definition audit execution hash differs.')


class _MaterialAccess:
    """Host authorization plus transaction-scoped inert scientific audit facts."""
    def __init__(self,session):self.session=session;self.host=session.access;self.facts=[];self.registered=False
    def require(self,*args,**kwargs):return self.host.require(*args,**kwargs)
    def denial(self,*args,**kwargs):return self.host.denial(*args,**kwargs)
    def _context(self):return self.host._context()
    @property
    def lock(self):return self.host.lock
    def audit(self,action,target=None,details=None,result='success'):
        if action not in AUDIT_ACTIONS or result!='success' or not self.session.db.in_transaction:
            raise WorkbenchError('Material audit must share its canonical mutation.','unavailable',409)
        actor=self.host.require('edit',action,target)
        fact=dict(action=action,target=target,details=copy.deepcopy(details or {}),result=result,
                  actor_id=actor.actor_id,occurred_at=timestamp())
        _audit(fact)
        if not self.registered:
            self.registered=True
            def clear():self.facts.clear();self.registered=False
            self.session.db.on_commit(clear);self.session.db.on_rollback(clear)
        self.facts.append(fact)


@_boundary
def decode_records(records):
    """Closed family-local metadata checks; missing payloads do not erase facts."""
    result = {}
    for envelope in records:
        if envelope.get('family') not in FAMILIES:
            continue
        _closed(envelope, ('family', 'id', 'document'), 'material envelope')
        family, doc = envelope['family'], envelope['document']
        if family in EDITABLE:
            _closed(doc, ('format', 'origin_catalog_id', 'current', 'revisions', 'audit'), 'definition history')
        else:
            _closed(doc, ('format', 'origin_catalog_id', 'value', 'artifacts','audit'), 'immutable material')
        if doc['format'] != FAMILIES[family]:
            raise WorkbenchError('Unsupported material document format.', 'unsupported', 409)
        catalog_id = _catalog(doc['origin_catalog_id'])
        if family in EDITABLE:
            revisions = doc['revisions']
            if type(revisions) is not list or not revisions or type(doc['audit']) is not list or len(doc['audit']) != len(revisions):
                raise WorkbenchError('Definition history must retain its observed revisions and audit.')
            previous = None
            for value, audit in zip(revisions, doc['audit'], strict=True):
                value = _definition(family, value, catalog_id)
                if previous and (value['id'] != previous['id'] or value['revision'] != previous['revision'] + 1):
                    raise WorkbenchError('Definition history identity or revision changed.')
                _definition_audit(family,value,audit,catalog_id)
                previous = value
            if doc['current'] != revisions[-1]:
                raise WorkbenchError('Definition current value differs from its history.')
            expected = catalog_id + '.' + doc['current']['id']
        else:
            if type(doc['audit']) is not list:raise WorkbenchError('Material audit must retain its fact list.')
            for audit in doc['audit']:_audit(audit)
            value = doc['value']
            if family == 'model_material': value = decode_model_material(value, catalog_id=catalog_id)
            elif family == 'recipe_material': value = decode_recipe_material(value, catalog_id=catalog_id)
            elif family == 'project_snapshot':
                from projects import decode_retained_snapshot
                value = decode_retained_snapshot(value)
            else:
                value = decode_runtime_material(value, catalog_id=catalog_id)
            for audit in doc['audit']:
                if family=='model_material':
                    if (audit['action']!='models.publish' or audit['target']!=value['ref']['id'] or
                            audit['details']!={'revision':value['ref']['revision'],'material_sha256':value['ref']['sha256']}):
                        raise WorkbenchError('Published Model audit differs.')
                elif family=='recipe_material':
                    if (audit['action']!='recipes.material' or audit['target']!=value['ref']['sha256'] or
                            audit['details']!={'recipe_id':value['material']['recipe_id'],'revision':value['material']['recipe_revision']}):
                        raise WorkbenchError('Retained Recipe audit differs.')
                else:raise WorkbenchError('Unsupported immutable material audit fact.')
            inventory = _inventory(family, value)
            if family == 'project_snapshot':
                if type(doc['artifacts']) is not list or len(doc['artifacts'])!=1:raise WorkbenchError('Snapshot requires its exact manifest edge.')
                size=doc['artifacts'][0]['blob']['bytes'];natural(size,'Manifest bytes',1,64*1024)
                inventory=[dict(name=value['manifest_path'],sha256=value['manifest_sha256'],bytes=size)]
            if family == 'runtime_material':
                inventory=([dict(name='manifest.json',sha256=value['descriptor']['manifest_sha256'],bytes=value['descriptor']['manifest_bytes'])]+
                           [dict(name=item['path'],sha256=item['sha256'],bytes=item['bytes']) for item in value['manifest']['files']]) if value['descriptor'] is not None else []
            if type(doc['artifacts']) is not list or doc['artifacts'] != _edges(inventory,family):
                raise WorkbenchError('Retained material artifact edges differ from the owner inventory.')
            expected = catalog_id + '.' + (value['manifest_sha256'] if family == 'project_snapshot' else value['ref']['sha256'])
        if envelope['id'] != expected or (family, expected) in result:
            raise WorkbenchError('Retained material locator differs or repeats.')
        result[(family, expected)] = copy.deepcopy(doc)
    return result


@_boundary
def decode_runtime_material(value, *, catalog_id):
    """Keep original physical descriptors as historical facts, never live bindings."""
    _closed(value, ('ref', 'descriptor', 'environment','manifest'), 'runtime material')
    reference(value['ref'], 'runtime', catalog_id)
    descriptor = value['descriptor']
    if descriptor is None:
        if value['manifest'] is not None:raise WorkbenchError('Built-in environment cannot carry an external runtime manifest.')
        if type(value['environment']) is not dict or digest(value['environment']) != value['ref']['sha256']:
            raise WorkbenchError('Retained built-in runtime identity differs.')
    else:
        if value['environment'] is not None:
            raise WorkbenchError('Retained runtime cannot mix descriptor and environment.')
        if descriptor.get('profile') == 'captured_cpu_python_v1':
            from recipe_process import validate_cpu_snapshot_manifest,encoded
            manifest=validate_cpu_snapshot_manifest(descriptor,value['manifest'])
        elif descriptor.get('profile') == 'managed_torch_python_v1':
            from torch_runtime import verify_descriptor,encoded
            manifest=verify_descriptor(descriptor,value['manifest'])
        else: raise WorkbenchError('Unsupported retained runtime profile.', 'unsupported', 409)
        raw=encoded(manifest)
        if len(raw)!=descriptor['manifest_bytes'] or hashlib.sha256(raw).hexdigest()!=descriptor['manifest_sha256']:
            raise WorkbenchError('Retained runtime manifest identity differs.')
        if descriptor['catalog_id'] != catalog_id or digest(descriptor) != value['ref']['sha256']:
            raise WorkbenchError('Retained runtime descriptor identity differs.')
    return copy.deepcopy(value)


@_boundary
def validate_operation_result(operation, result, records=None):
    """True for a validated owned result; False for another fixed owner."""
    if operation in ('models.create','models.save'):
        decode_model_draft(result,catalog_id=result['task']['catalog_id']);family='model_definition'
    elif operation=='models.publish':
        decode_model_material(result,catalog_id=result['ref']['catalog_id']);family='model_material'
    elif operation in ('graphs.create','graphs.create_external','graphs.save','graphs.clone'):
        decode_graph(result);family='pipeline_graph'
    elif operation in ('recipes.create','recipes.save'):
        decode_recipe_draft(result,catalog_id=result['task']['catalog_id']);family='recipe_definition'
    elif operation in ('recipes.material','recipes.prepare_external_material','recipes.prepare_builtin_material'):
        decode_recipe_material(result,catalog_id=result['ref']['catalog_id']);family='recipe_material'
    else:return False
    if family in EDITABLE:
        create=operation.endswith(('.create','.create_external','.clone'))
        if create and result['revision']!=1 or not create and result['revision']<2:
            raise WorkbenchError('Retained definition result revision differs from its operation.')
    if records is not None:
        documents=decode_records(records)
        values=[value for (owned,_),doc in documents.items() if owned==family
                for value in (doc['revisions'] if family in EDITABLE else [doc['value']])]
        if not any(encode(value)==encode(result) for value in values):
            raise WorkbenchError('Material operation result differs from its retained family closure.')
    return True


class ProjectMaterial:
    def __init__(self, session):
        self.session = session
        self.owner_access = _MaterialAccess(session) if hasattr(session,'access') else None

    def _documents(self):
        self.session.check()
        return decode_records(self.session.snapshot['records'])

    @_boundary
    def _value(self, family, ref):
        catalog_id = _catalog(ref['catalog_id'])
        reference(ref,{'model_material':'model','recipe_material':'recipe_material','runtime_material':'runtime'}[family],catalog_id)
        key = catalog_id + '.' + ref['sha256']
        document = self._documents().get((family, key))
        if document is None: raise WorkbenchError('Retained material is unavailable.', 'unavailable', 409)
        if document['value']['ref'] != ref: raise WorkbenchError('Retained material reference differs.', 'invalid', 400)
        return copy.deepcopy(document['value'])

    @_boundary
    def model(self, ref, *, verify=False):
        value = self._value('model_material', ref)
        if verify: verify_model_closure(value, read_blob=lambda item, maximum: self.blob(ref, item, maximum))
        return value

    @_boundary
    def recipe(self, ref, *, verify=False):
        value = self._value('recipe_material', ref)
        if verify: self.composition_closure(ref)
        return value

    @_boundary
    def blob(self, ref, item, maximum=40*1024**2):
        family = 'model_material' if ref['kind'] == 'model' else 'recipe_material'
        value = self._value(family, ref)
        if item not in _inventory(family, value): raise WorkbenchError('Undeclared material blob.', 'invalid', 400)
        return self.session.artifacts.read_blob(_intrinsic(item), maximum_bytes=maximum)

    @_boundary
    def composition_closure(self, ref):
        value = self.recipe(ref)
        return verify_recipe_closure(value, self.model(value['material']['model']), read_blob=self.blob)

    @_boundary
    def runtime(self, ref, *, verify=False):
        value = self._value('runtime_material', ref)
        if verify and value['descriptor'] is not None:
            descriptor = value['descriptor']
            raw = self.session.artifacts.read_blob({'sha256': descriptor['manifest_sha256'], 'bytes': descriptor['manifest_bytes']}, maximum_bytes=32*1024**2)
            if descriptor['profile'] == 'captured_cpu_python_v1':
                from recipe_process import decode, encoded, validate_cpu_manifest
                manifest = validate_cpu_manifest(decode(raw))
            else:
                from torch_runtime import decode, encoded, validate_manifest
                manifest = validate_manifest(decode(raw))
            if encoded(manifest) != raw: raise WorkbenchError('Retained runtime manifest encoding differs.', 'invalid', 400)
        return value

    @_boundary
    def snapshot_ref(self, project_id, manifest_sha256, *, catalog_id=None, verify=False):
        candidates = [doc for (family, _), doc in self._documents().items() if family == 'project_snapshot' and
                      doc['value']['id'] == project_id and doc['value']['manifest_sha256'] == manifest_sha256 and
                      (catalog_id is None or doc['origin_catalog_id'] == catalog_id)]
        if len(candidates) != 1: raise WorkbenchError('Retained project snapshot is unavailable or ambiguous.', 'unavailable', 409)
        doc = candidates[0]
        if verify:
            from projects import decode, manifest
            edge = doc['artifacts'][0]['blob']
            raw = self.session.artifacts.read_blob(edge, maximum_bytes=64*1024)
            if manifest(decode(raw)) != doc['value']['manifest']:
                raise WorkbenchError('Retained project manifest differs.', 'invalid', 400)
        return copy.deepcopy(doc['value'])

    def capture_definition(self, family, value, before_records, *, action, actor_id=None, audit_facts=None):
        catalog_id = self.session.snapshot['project_id']
        value = _definition(family, value, catalog_id)
        key = catalog_id + '.' + value['id']
        prior = decode_records(before_records).get((family, key))
        revisions = copy.deepcopy(prior['revisions']) if prior else []
        audits = copy.deepcopy(prior['audit']) if prior else []
        if revisions and value == revisions[-1]:
            return {'family': family, 'id': key, 'document': prior}
        if revisions and value['revision'] != revisions[-1]['revision'] + 1:
            raise WorkbenchError('Definition changed outside its canonical history.', 'stale', 409)
        details={'revision':value['revision'],'document_sha256':digest(value)}
        if family=='pipeline_graph':details['execution_sha256']=execution_digest(value)
        facts=copy.deepcopy(audit_facts) if audit_facts is not None else [dict(action=action,target=value['id'],details=details,result='success',actor_id=actor_id,occurred_at=timestamp())]
        if len(facts)!=1:raise WorkbenchError('A definition revision requires its exact owner audit fact.')
        revisions.append(copy.deepcopy(value));audits.extend(facts)
        record = dict(family=family, id=key, document=dict(format=FAMILIES[family], origin_catalog_id=catalog_id,
                      current=copy.deepcopy(value), revisions=revisions, audit=audits))
        decode_records([record]); return record

    def _capture_material(self, family, value, root):
        catalog_id = value['ref']['catalog_id']
        value = decode_model_material(value, catalog_id=catalog_id) if family == 'model_material' else decode_recipe_material(value, catalog_id=catalog_id)
        inventory = _inventory(family, value)
        root_fd = material_fd = None
        try:
            root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            material_fd = os.open(value['ref']['sha256'], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
            for item in inventory:
                fd = os.open(item['name'], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=material_fd)
                try: self.session.artifacts.publish_fd(fd, _declaration(item), maximum_bytes=item['bytes'])
                finally: os.close(fd)
        except OSError:
            raise WorkbenchError('Projection-local material capture is unavailable.','unavailable',409) from None
        finally:
            if material_fd is not None: os.close(material_fd)
            if root_fd is not None: os.close(root_fd)
        record = dict(family=family, id=catalog_id+'.'+value['ref']['sha256'], document=dict(
            format=FAMILIES[family], origin_catalog_id=catalog_id, value=copy.deepcopy(value), artifacts=_edges(inventory,family),
            audit=copy.deepcopy([fact for fact in self.owner_access.facts
                if fact['action']==('models.publish' if family=='model_material' else 'recipes.material')
                and fact['target'] in (value['ref'].get('id'),value['ref']['sha256'])]) if self.owner_access else []))
        prior=decode_records(self.session.snapshot['records']).get((family,record['id']))
        if prior is not None:
            if prior['value']!=record['document']['value'] or prior['artifacts']!=record['document']['artifacts']:
                raise WorkbenchError('Retained immutable material changed.','invalid',400)
            facts=copy.deepcopy(prior['audit'])
            facts.extend(fact for fact in record['document']['audit'] if fact not in facts)
            record['document']['audit']=facts
        decode_records([record]); return record

    @staticmethod
    def declarations(record):
        """Explicit intrinsic declaration upserts, coalesced without hidden state."""
        result={}
        for edge in record['document'].get('artifacts',[]):
            item=edge['blob']; declaration=_declaration(item)
            if item['sha256'] in result and result[item['sha256']]['document']!=declaration:
                raise WorkbenchError('Artifact declarations disagree.','invalid',400)
            result[item['sha256']]=dict(family='project_artifact',id=item['sha256'],document=declaration)
        return list(result.values())

    def capture_model_material(self, value, root): return self._capture_material('model_material', value, root)
    def capture_recipe_material(self, value, root): return self._capture_material('recipe_material', value, root)

    @staticmethod
    def _coalesce(records):
        result={}
        for record in records:
            key=record['family'],record['id']
            if key in result and result[key]!=record:
                raise WorkbenchError('Owned material upserts disagree.','invalid',400)
            result[key]=record
        return list(result.values())

    @_boundary
    def capture_recipe_dependencies(self,record,before_records,*,runtime_manifest=None):
        """Retain exact measured runtime facts without using origin paths.

        Captured runtime manifests must be supplied by an explicit trusted
        current-runtime reader, or already be part of the canonical checkpoint.
        This method never provisions or captures runtime binaries.
        """
        value=record['document']['value'];ref=value['material']['runtime']
        snapshot=retained_json(self.session.artifacts.read_blob(
            _intrinsic(value['material']['recipe_document']),maximum_bytes=2*1024**2).decode(),2*1024**2)
        if snapshot['format']=='builtin_recipe_snapshot_v1':environment=snapshot['validation']['runtime']
        else:
            execution=snapshot['preflight']['material']
            environment=execution.get('torch_runtime',execution.get('cpu_snapshot',execution['runtime']))
        descriptor=environment if environment.get('profile') in ('captured_cpu_python_v1','managed_torch_python_v1') else None
        prior=decode_records(before_records).get(('runtime_material',ref['catalog_id']+'.'+ref['sha256']))
        if prior is not None:
            expected=prior['value']['descriptor'] if descriptor is not None else prior['value']['environment']
            if expected!=environment or prior['value']['ref']!=ref:
                raise WorkbenchError('Recipe and retained runtime identity differ.','invalid',400)
            if descriptor is not None:
                if runtime_manifest is not None:
                    raw=runtime_manifest(copy.deepcopy(descriptor)) if callable(runtime_manifest) else runtime_manifest
                    retained=self.capture_runtime(prior['value'],raw)
                    return [*self.declarations(retained),retained]
                self.session.artifacts.read_blob({'sha256':descriptor['manifest_sha256'],'bytes':descriptor['manifest_bytes']},maximum_bytes=32*1024**2)
            return []
        manifest=None
        manifest_raw=None
        if descriptor is not None:
            manifest_raw=runtime_manifest(copy.deepcopy(descriptor)) if callable(runtime_manifest) else runtime_manifest
            if type(manifest_raw) is not bytes:
                raise WorkbenchError('Explicit captured runtime manifest is unavailable.','unavailable',409)
            if descriptor['profile']=='captured_cpu_python_v1':
                from recipe_process import decode,validate_cpu_manifest
                manifest=validate_cpu_manifest(decode(manifest_raw))
            else:
                from torch_runtime import decode,validate_manifest
                manifest=validate_manifest(decode(manifest_raw))
        runtime=self.capture_runtime(dict(ref=ref,descriptor=descriptor,
            environment=None if descriptor is not None else environment,manifest=manifest),manifest_raw)
        return [*self.declarations(runtime),runtime]

    @_boundary
    def capture_snapshot(self, value, raw, *, catalog_id):
        from projects import decode_retained_snapshot,decode,manifest
        value=decode_retained_snapshot(value);_catalog(catalog_id)
        if type(raw) is not bytes or len(raw)>64*1024 or hashlib.sha256(raw).hexdigest()!=value['manifest_sha256'] or manifest(decode(raw))!=value['manifest']:
            raise WorkbenchError('Exact original project manifest bytes differ.')
        key=catalog_id+'.'+value['manifest_sha256']
        prior=decode_records(self.session.snapshot['records']).get(('project_snapshot',key))
        if prior is not None:
            original=prior['value']
            if any(original[field]!=value[field] for field in ('id','name','manifest_sha256','manifest')):
                raise WorkbenchError('Original snapshot identity differs.','invalid',400)
            # Explicit current root registration may move. It cannot replace
            # original historical root/path identity facts at the same hash.
            return dict(family='project_snapshot',id=key,document=prior)
        item=dict(name=value['manifest_path'],sha256=value['manifest_sha256'],bytes=len(raw))
        self.session.artifacts.publish_bytes(raw,_declaration(item),maximum_bytes=64*1024)
        record=dict(family='project_snapshot',id=catalog_id+'.'+value['manifest_sha256'],document=dict(
            format=FAMILIES['project_snapshot'],origin_catalog_id=catalog_id,value=value,artifacts=_edges([item],'project_snapshot'),audit=[]))
        decode_records([record]);return record

    @_boundary
    def capture_runtime(self,value,manifest_raw=None):
        value=decode_runtime_material(value,catalog_id=value['ref']['catalog_id'])
        items=[]
        if value['descriptor'] is not None:
            descriptor=value['descriptor']
            if type(manifest_raw) is not bytes or len(manifest_raw)!=descriptor['manifest_bytes'] or hashlib.sha256(manifest_raw).hexdigest()!=descriptor['manifest_sha256']:
                raise WorkbenchError('Exact original runtime manifest bytes differ.')
            item=dict(name='manifest.json',sha256=descriptor['manifest_sha256'],bytes=len(manifest_raw))
            self.session.artifacts.publish_bytes(manifest_raw,_declaration(item),maximum_bytes=32*1024**2)
            items=[item,*[dict(name=row['path'],sha256=row['sha256'],bytes=row['bytes']) for row in value['manifest']['files']]]
        record=dict(family='runtime_material',id=value['ref']['catalog_id']+'.'+value['ref']['sha256'],document=dict(
            format=FAMILIES['runtime_material'],origin_catalog_id=value['ref']['catalog_id'],value=value,artifacts=_edges(items,'runtime_material'),audit=[]))
        decode_records([record]);return record

    def restore(self):
        """Rebuild only current-namespace SQL values, without mutable owners."""
        documents=self._documents();catalog_id=self.session.db.dataset_id
        with self.session.db.transaction():
            for table in ('model_definition_drafts','workspace_graphs','workspace_recipe_drafts','model_materials','workspace_recipe_materials'):
                self.session.db.execute('DELETE FROM '+table)
            for (family,_),doc in documents.items():
                if doc['origin_catalog_id']!=catalog_id:continue
                if family in EDITABLE:
                    value=doc['current']
                    table={'model_definition':'model_definition_drafts','pipeline_graph':'workspace_graphs','recipe_definition':'workspace_recipe_drafts'}[family]
                    self.session.db.execute('INSERT INTO '+table+' VALUES(%s,%s,%s)',(value['id'],value['revision'],encode(value)))
                elif family=='model_material':
                    value=doc['value'];ref=value['ref']
                    self.session.db.execute('INSERT INTO model_materials VALUES(%s,%s,%s,%s)',(ref['id'],ref['revision'],ref['sha256'],encode(value)))
                elif family=='recipe_material':
                    value=doc['value'];material=value['material']
                    self.session.db.execute('INSERT INTO workspace_recipe_materials VALUES(%s,%s,%s,%s)',(value['ref']['sha256'],material['recipe_id'],material['recipe_revision'],encode(value)))

    def materialize_projection(self,ref,root):
        """Explicit preparation may recreate a disposable owner byte cache.

        The destination must live inside the current physical SQL projection.
        Canonical files and original runtime paths are never cleanup targets.
        """
        root=Path(root)
        if not root.resolve().is_relative_to(Path(self.session.db.path).resolve()):
            raise WorkbenchError('Material cache must belong to the disposable projection.','invalid',400)
        value=self.model(ref) if ref['kind']=='model' else self.recipe(ref)
        family='model_material' if ref['kind']=='model' else 'recipe_material'
        inventory=_inventory(family,value)
        root.mkdir(mode=0o700,parents=True,exist_ok=True)
        target=root/ref['sha256']
        if target.exists():
            from model_definitions import read_owned_blob
            if target.is_symlink() or set(os.listdir(target))!={item['name'] for item in inventory}:
                raise WorkbenchError('Disposable material cache differs.','unavailable',409)
            for item in inventory:read_owned_blob(root,ref['sha256'],item,item['bytes'])
            return target
        staging=Path(tempfile.mkdtemp(prefix='.material-rebuild-',dir=root))
        try:
            for item in inventory:
                with self.session.artifacts.open_verified(_declaration(item),maximum_bytes=item['bytes']) as source:
                    with (staging/item['name']).open('xb') as destination:
                        while True:
                            raw=os.read(source,1024**2)
                            if not raw:break
                            destination.write(raw)
                        destination.flush();os.fchmod(destination.fileno(),0o400);os.fsync(destination.fileno())
            from metadata import _sync_directory
            _sync_directory(staging)
            # The Session lock serializes owner cache publication. An externally
            # created target is refused, never adopted or overwritten.
            if os.path.lexists(target):raise WorkbenchError('Material cache changed during reconstruction.','stale',409)
            os.rename(staging,target);_sync_directory(root)
            return target
        finally:
            if staging.exists():shutil.rmtree(staging)

    def prepare_recipe(self,owner,graph_id,revision,model_ref,expected_checkpoint,key,*,builtin=False,reconcile_capture=False,runtime_manifest=None):
        operation='recipes.prepare_builtin_material' if builtin else 'recipes.prepare_external_material'
        self.session.access.require('edit',operation,graph_id,owner_only=reconcile_capture and not builtin)
        if builtin:
            # Existing built-in qualification reaches the adapter --probe
            # subprocess. Preserve that explicit execution gate until the
            # project execution stage supplies current-host admission.
            raise WorkbenchError('Built-in material preparation is unavailable while execution is disabled; it requires an explicit current runtime probe.','unavailable',409)
        body=dict(graph_id=graph_id,revision=revision,model=model_ref,reconcile_capture=reconcile_capture)
        def invoke():
            self.materialize_projection(model_ref,owner.dataset.models.path)
            prepare=owner.prepare_builtin_material if builtin else owner.prepare_external_material
            prepared=prepare(graph_id,revision,model_ref,reconcile_capture=reconcile_capture)
            return owner._retain_material(prepared)
        def capture(result,before):
            record=self.capture_recipe_material(result,owner.material_path)
            return {'records':self._coalesce([*self.declarations(record),record,
                *self.capture_recipe_dependencies(record,before,runtime_manifest=runtime_manifest)]),'result':result}
        return self.session.mutate(operation,graph_id,body,expected_checkpoint,key,invoke,capture)

    def mutate_definition(self, family, operation, target, body, expected_checkpoint, key, invoke):
        authority = self.session.access.require('edit', operation, target)
        def capture(result, before):
            validate_operation_result(operation, result)
            return {'records': [self.capture_definition(family,result,before,action=operation,actor_id=authority.actor_id,
                audit_facts=[fact for fact in self.owner_access.facts if fact['target']==result['id']])], 'result': result}
        return self.session.mutate(operation, target, body, expected_checkpoint, key, invoke, capture)

    def publish_model(self, owner, model_id, body, expected_checkpoint, key):
        self.session.access.require('edit', 'models.publish', model_id, owner_only=body.get('reconcile_capture', False))
        def capture(result, before):
            record=self.capture_model_material(result,owner.path)
            return {'records': [*self.declarations(record),record], 'result': result}
        return self.session.mutate('models.publish', model_id, body, expected_checkpoint, key,
                                   lambda: owner.publish(model_id, body), capture)

    def retain_recipe(self, owner, prepared, expected_checkpoint, key, *, runtime_manifest=None):
        value = prepared['document']; target = value['material']['recipe_id']
        self.session.access.require('edit', 'recipes.prepare_external_material', target,
                                    owner_only=prepared.get('reconcile_capture', False))
        body = {'ref': value['ref']}
        def capture(result, before):
            record=self.capture_recipe_material(result,owner.material_path)
            return {'records': self._coalesce([*self.declarations(record),record,
                *self.capture_recipe_dependencies(record,before,runtime_manifest=runtime_manifest)]), 'result': result}
        return self.session.mutate('recipes.material', target, body, expected_checkpoint, key,
                                   lambda: owner._retain_material(prepared), capture)

    @_boundary
    def evidence(self, run, selectors=None, *, read_blob=None):
        import model_evidence
        import recipe_contract
        selectors = {} if selectors is None else selectors
        inventory = {item['name']: item for item in run['artifacts']}
        def read(name, maximum):
            if name not in inventory: raise WorkbenchError('Evidence artifact is unavailable.', 'unavailable', 409)
            item = inventory[name]
            raw = read_blob(name, maximum) if read_blob else self.session.artifacts.read_blob(_intrinsic(item), maximum_bytes=maximum)
            if type(raw) is not bytes or len(raw)>maximum or len(raw)!=item['bytes'] or hashlib.sha256(raw).hexdigest()!=item['sha256']:
                raise WorkbenchError('Evidence artifact differs.', 'invalid', 400)
            return raw
        if run.get('extension_context') is not None:
            import extension_evidence
            ref = {'kind': 'recipe_material', 'catalog_id': run['dataset_id'], 'id': run['approval_material_sha256'], 'sha256': run['approval_material_sha256']}
            composition = self.recipe(ref); closure = self.composition_closure(ref)
            context = extension_evidence.validate_context(run['extension_context'], run, composition, closure['static_context'])
            verified = extension_evidence.verify_blobs(run, context, read_blob=read, captured=closure['captured_inputs'])
            return extension_evidence.query(verified, selectors)
        from pipeline import adapter_for_graph, model_aware_graph
        import image_training
        if not model_aware_graph(run['graph']): return {'state': 'unsupported', 'reason': 'This retained adapter did not capture model_evidence_v1.'}
        if set(selectors) - {'checkpoint_sha256', 'split'} or selectors.get('split', 'validation') != 'validation':
            raise WorkbenchError('Unsupported retained evidence selector.', 'unsupported', 409)
        if adapter_for_graph(run['graph']) is image_training: evaluator = model_evidence
        else:
            import one_fit_evidence as evaluator
        result, descriptors, predictions = evaluator.verify_blobs(run, run['metrics'], read_blob=read)
        result.update(checkpoint=None, predictions=None, metric_definition_hashes={item['id']: model_evidence.digest(item) for item in result['metric_definitions']})
        selected = selectors.get('checkpoint_sha256')
        if selected is not None:
            matches = [index for index, entry in enumerate(result['checkpoint_index']['entries']) if entry['checkpoint']['sha256'] == selected]
            if not matches: raise WorkbenchError('Checkpoint does not belong to this Run.', 'not_found', 404)
            result.update(checkpoint=descriptors[matches[0]], predictions=predictions[matches[0]])
        return result
