"""Explicit current native qualification, before the short admission transaction.

The configured interpreter and installed packages are operator-managed inputs.
Measured interpreter/source bytes and observed package versions are evidence;
they do not promise a complete package closure or scientific reproducibility.
No serialized validation result can become this process-local preparation.
"""
import copy
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import os
from pathlib import Path
import shutil
import sys

from model_definitions import checked_json, natural, reference
from pipeline import (adapter_for_graph, decode_graph, digest, execution_digest,
                      identifier, model_aware_graph, closed, decode_probe_observation)
from project_session import operation_records
from workbench import WorkbenchError, timestamp


OPERATIONS=frozenset(('native_preparation.intent','native_preparation.validate'))
_CURRENT=ContextVar('project_native_preparation',default=None)


def _fail(message,code='unavailable'):
    raise WorkbenchError(message,code,409)


def _sha(value):
    if type(value) is not str or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):
        _fail('Native preparation requires an exact SHA256.','invalid')


def _key(operation,key):
    from experiments import request_key
    request_key(key)
    return 'native-'+digest(dict(operation=operation,key=key))


def _validation_observation(result,records):
    closed(result,('status','valid','errors','validation_token','graph_revision','execution_sha256','release','runtime'),('selection_policy',))
    if type(result['valid']) is not bool or type(result['errors']) is not list or len(result['errors'])>100:
        _fail('Invalid native validation result.','invalid')
    natural(result['graph_revision'],'Graph revision',1);_sha(result['execution_sha256'])
    if result['validation_token'] is not None:_sha(result['validation_token'])
    for error in result['errors']:
        closed(error,('path','message','code'))
        if any(type(error[k]) is not str or len(error[k])>2000 for k in error):_fail('Invalid native validation error.','invalid')
    if (result['valid'] and (result['errors'] or result['status']!='valid' or result['validation_token'] is None)
            or not result['valid'] and (not result['errors'] or result['status']!=result['errors'][0]['code'] or result['validation_token'] is not None)):
        _fail('Contradictory native validation result.','invalid')
    release=result['release']
    if release is not None:
        import release_validation
        integrity=release.get('recipe') in release_validation.RECIPES
        fields=('id','sha256','format','recipe','allowed_recipes','records','split_counts','prior_test_exposure','status')
        if integrity:
            fields+=('result_kind','validation_summary')
            if release['recipe'] in release_validation.CLASSIFICATION_RECIPES:fields+=('class_vocabulary',)
            closed(release,fields)
            if release['result_kind']!='release_validation':_fail('Invalid integrity release result kind.','invalid')
        else:closed(release,(*fields,'class_vocabulary'),('audio_summary',))
        _sha(release['id']);_sha(release['sha256'])
        if release['id']!=release['sha256'] or release['status']!='available':_fail('Invalid frozen input observation.','invalid')
        for name in ('format','recipe'):
            if type(release[name]) is not str or not 1<=len(release[name])<=120:_fail('Invalid release task.','invalid')
        for name in ('allowed_recipes',):
            if type(release[name]) is not list or len(release[name])>10000 or any(type(v) is not str or len(v)>1000 for v in release[name]):
                _fail('Invalid release vocabulary.','invalid')
        if 'class_vocabulary' in release:
            manifests=[] if records is None else [record['document']['manifest'] for record in records
                if record['family']=='dataset_release' and record['id']==release['id']]
            release_validation.decode_class_vocabulary(release['class_vocabulary'],release['recipe'],
                manifest=manifests[0] if len(manifests)==1 else None)
        natural(release['records'],'Frozen record count');closed(release['split_counts'],('train','validation','test'))
        for count in release['split_counts'].values():natural(count,'Split count')
        exposure=release['prior_test_exposure'];closed(exposure,('exposed','events'))
        if type(exposure['exposed']) is not bool or type(exposure['events']) is not list or len(exposure['events'])>100000:
            _fail('Invalid prior disclosure observations.','invalid')
        for event in exposure['events']:
            closed(event,('id','record_id','source_hash','reason','run_id','release_id','created_at'))
            for field in ('id','run_id'):identifier(event[field])
            for field in ('source_hash','release_id'):_sha(event[field])
            for field in ('record_id','reason','created_at'):
                if type(event[field]) is not str or len(event[field])>1000:_fail('Invalid disclosure observation text.','invalid')
        if 'audio_summary' in release:
            audio=release['audio_summary'];closed(audio,('sample_rates_hz','analyzed_frames','coordinate_contract'))
            if type(audio['sample_rates_hz']) is not list or len(audio['sample_rates_hz'])>1000:_fail('Invalid audio rate inventory.','invalid')
            for rate in audio['sample_rates_hz']:natural(rate,'Sample rate',1)
            natural(audio['analyzed_frames'],'Analyzed frames')
            if type(audio['coordinate_contract']) is not str or len(audio['coordinate_contract'])>1000:_fail('Invalid audio coordinate contract.','invalid')
        if integrity:
            matches=[] if records is None else [record['document']['manifest'] for record in records
                if record['family']=='dataset_release' and record['id']==release['id']]
            if len(matches)!=1:_fail('Integrity validation needs its exact retained frozen manifest.')
            manifest=matches[0]
            summary=release_validation.decode_summary(release['validation_summary'],release['recipe'],
                manifest=manifest,release_id=release['id'])
            if (release['records']!=len(manifest['records']) or release['split_counts']!=summary['split_counts']
                    or release['format']!=manifest.get('format','canonical_v1')):
                _fail('Integrity release header differs from its frozen summary.','invalid')
            if release['recipe'] in release_validation.CLASSIFICATION_RECIPES:
                if release['class_vocabulary']!=summary['class_vocabulary']:_fail('Integrity class vocabulary differs.','invalid')
    runtime=result['runtime']
    recipes=[]
    if runtime is not None:
        import release_validation
        from pipeline import MODEL_RECIPES
        for recipe in ('image_classification','text_classification','audio_classification',*MODEL_RECIPES,*release_validation.RECIPES):
            try:decode_probe_observation(recipe,runtime,with_definition=True)
            except (WorkbenchError,TypeError,ValueError):continue
            recipes.append(recipe)
        if len(recipes)!=1:_fail('Unclassified native validation runtime.','invalid')
    if 'selection_policy' in result:
        from experiments import validate_retained_policy
        validate_retained_policy(result['selection_policy'])
    if result['valid']:
        if release is None or runtime is None or not runtime['available'] or release['recipe']!=recipes[0]:
            _fail('Native validation lacks its exact runtime and frozen input.','invalid')
        if records is not None:
            from project_material_fork import is_intent
            matches=[]
            for record in records:
                if record['family']!='pipeline_graph':continue
                for graph in record['document']['revisions']:
                    if is_intent(graph):continue
                    if graph['revision']!=result['graph_revision'] or execution_digest(graph)!=result['execution_sha256']:continue
                    token=digest(dict(graph_id=graph['id'],revision=graph['revision'],execution_sha256=execution_digest(graph),
                        release_sha256=release['sha256'],runtime=runtime))
                    release_id=next((node['parameters']['release_id'] for node in graph['nodes'] if node['type']=='release'),None)
                    if graph['recipe']==recipes[0] and token==result['validation_token'] and release_id==release['id']:matches.append(graph)
            if not matches:_fail('Native validation has no exact retained graph/runtime binding.','invalid')


def preparation_owner(owner):
    """Select only the fixed current project owner; legacy paths stay legacy."""
    from project_material import _MaterialAccess
    from project_execution import ProjectExecution
    adapter=getattr(owner.dataset,'project_native_preparation',None)
    project=isinstance(owner.access,_MaterialAccess) or isinstance(getattr(owner.dataset,'project_execution',None),ProjectExecution)
    if not project and adapter is None:return None
    if not isinstance(adapter,ProjectNativePreparation) or adapter.db is not owner.db:
        _fail('Current native preparation for the runtime probe is unavailable.')
    return adapter


def validate_operation_result(operation,result,records=None):
    if operation not in OPERATIONS:return False
    try:
        if operation=='native_preparation.intent':
            closed(result,('format','origin_catalog_id','actor_id','purpose','graph','model','composition',
                           'release_id','definition_identity','runtime','occurred_at'))
            if result['format']!='project_native_preparation_intent_v1' or result['purpose'] not in ('material','validation','admission'):
                _fail('Unsupported native preparation intent.','unsupported')
            for field in ('origin_catalog_id','actor_id'):identifier(result[field])
            graph=result['graph'];closed(graph,('id','revision','document_sha256','execution_sha256'))
            identifier(graph['id']);natural(graph['revision'],'Graph revision',1)
            for field in ('document_sha256','execution_sha256'):_sha(graph[field])
            _sha(result['release_id'])
            if result['model'] is not None:reference(result['model'],'model',result['origin_catalog_id'])
            if result['composition'] is not None:reference(result['composition'],'recipe_material',result['origin_catalog_id'])
            identity=result['definition_identity'];closed(identity,('definition_files','adapter_definition_sha256'))
            if type(identity['definition_files']) is not dict or not 1<=len(identity['definition_files'])<=120:
                _fail('Invalid native definition inventory.','invalid')
            from project_native_process import WORKERS, validate_current_runtime
            for name,sha in identity['definition_files'].items():
                if type(name) is not str or Path(name).name!=name or not name.endswith('.py'):
                    _fail('Invalid native definition filename.','invalid')
                _sha(sha)
            if not set(identity['definition_files'])&WORKERS or digest(identity['definition_files'])!=identity['adapter_definition_sha256']:
                _fail('Native definition identity differs.','invalid')
            validate_current_runtime(result['runtime'])
            from datetime import datetime
            if datetime.fromisoformat(result['occurred_at']).utcoffset() is None:_fail('Native intent time requires an offset.','invalid')
            if records is not None:
                matches=[r['document'] for r in records if r['family']=='pipeline_graph'
                    and r['document']['origin_catalog_id']==result['origin_catalog_id']
                    and r['document']['current']['id']==graph['id']]
                if len(matches)!=1 or not any(v['revision']==graph['revision'] and digest(v)==graph['document_sha256']
                    and execution_digest(v)==graph['execution_sha256'] for v in matches[0]['revisions']):
                    _fail('Native intent has no exact retained graph.','invalid')
                actual=next(v for v in matches[0]['revisions'] if v['revision']==graph['revision'])
                if (next((node['parameters']['release_id'] for node in actual['nodes'] if node['type']=='release'),None)!=result['release_id']
                        or Path(adapter_for_graph(actual).__file__).name not in identity['definition_files']):
                    _fail('Native intent source or frozen input differs from its graph.','invalid')
                from types import SimpleNamespace
                from project_material import ProjectMaterial
                retained=ProjectMaterial(SimpleNamespace(snapshot=dict(records=records),check=lambda:None))
                if result['model'] is not None:retained.model(result['model'])
                if result['composition'] is not None:
                    composition=retained.recipe(result['composition'])['material']
                    if (composition['model']!=result['model'] or composition['recipe_id']!=graph['id']
                            or composition['recipe_revision']!=graph['revision']):
                        _fail('Native admission intent differs from its retained composition.','invalid')
        else:
            _validation_observation(result,records)
            checked_json(result,1024**2)
        return True
    except WorkbenchError:raise
    except (ValueError,TypeError,KeyError,AttributeError,ImportError):
        _fail('Invalid native preparation observation.','invalid')


class NativePreparationContext:
    """A lexical current qualification, never a portable admission capability."""
    def __init__(self,adapter,owner,graph,model,composition,purpose,key):
        self.adapter,self.owner=adapter,owner
        self.graph=copy.deepcopy(decode_graph(graph));self.model=copy.deepcopy(model)
        self.recipe=self.graph['recipe']
        self.composition=copy.deepcopy(composition);self.purpose=purpose;self.key=key
        self.actor=adapter.access.require('execute','pipeline.probe_native',self.graph['recipe'],owner_only=True)
        self.configured_executable=os.environ.get('TULDOK_TRAINING_PYTHON') or sys.executable
        self.definition=owner.definition_identity(self.graph['recipe'])
        self.sources={name:(owner.source_path/name).read_bytes() for name in self.definition['definition_files']}
        self.release_id=next(node['parameters']['release_id'] for node in self.graph['nodes'] if node['type']=='release')
        self.release=owner.inspect_release(self.release_id,private=True,recipe=self.graph['recipe'])
        self.model_value=adapter.materials.model(model,verify=True) if model is not None else None
        if model is not None:
            current_model,_definition=owner._builtin_model_for_graph(self.graph,model)
            if current_model!=self.model_value or {item['import_path']:item['blob']['sha256']
                    for item in current_model['material']['source_closure']}!=self.definition['definition_files']:
                _fail('Published native model differs from its graph or current source.','stale')
        from project_native_process import current_runtime
        self.runtime=current_runtime(self.configured_executable)
        self._active=False;self._probe=None;self._prepared=None;self._consumed=False;self.phase=None

    def _check(self,recipe):
        if not self._active or _CURRENT.get() is not self or recipe!=self.graph['recipe']:
            _fail('An explicit current native preparation is required.')
        self.adapter.session.check()
        actor=self.adapter.access.require('execute','pipeline.probe_native',recipe,owner_only=True)
        if actor.actor_id!=self.actor.actor_id:_fail('Native preparation caller changed.','conflict')
        if (os.environ.get('TULDOK_TRAINING_PYTHON') or sys.executable)!=self.configured_executable:
            _fail('Configured native interpreter changed.','stale')
        if self.owner.get(self.graph['id'])!=self.graph or self.owner.definition_identity(recipe)!=self.definition:
            _fail('Native graph or source changed during qualification.','stale')
        if any(hashlib.sha256((self.owner.source_path/name).read_bytes()).hexdigest()!=sha
               for name,sha in self.definition['definition_files'].items()):
            _fail('Native source bytes changed.','stale')
        current=self.owner.inspect_release(self.release_id,private=True,recipe=recipe)
        if current!=self.release:_fail('Native frozen input observation changed.','stale')
        if self.model is not None and self.adapter.materials.model(self.model,verify=True)!=self.model_value:
            _fail('Native model observation changed.','stale')
        from project_native_process import current_runtime
        if current_runtime(self.configured_executable)!=self.runtime:_fail('Configured native interpreter identity changed.','stale')
        return actor

    def authorize_probe(self,recipe):
        return self._check(recipe)

    def native_inputs(self,recipe):
        self.authorize_probe(recipe)
        return dict(runtime=copy.deepcopy(self.runtime),worker=Path(adapter_for_graph(self.graph).__file__).name,
            sources=copy.deepcopy(self.sources),model_aware=model_aware_graph(self.graph),definition_identity=copy.deepcopy(self.definition))

    def probe(self,owner,recipe):
        if owner.db is not self.adapter.db:_fail('Native preparation belongs to another projection.')
        self._check(recipe)
        if self._probe is None:
            if self.adapter.db.in_transaction:_fail('Native probe cannot run inside a metadata transaction.','unsupported')
            self.authorize_probe(recipe)
            result=self.adapter.execution.native.probe(recipe,expected_checkpoint=self.adapter.session.snapshot['checkpoint'],
                request_key=self.key+'.probe',preparation=self)
            self._probe=copy.deepcopy(result['runtime']);self.phase=copy.deepcopy(result['phase'])
        return copy.deepcopy(self._probe)

    def capture_builtin(self,owner,value):
        self._check(self.graph['recipe'])
        if self.composition is None or value!=self.composition:_fail('Prepared native material differs.','stale')
        if self.adapter.db.in_transaction:
            if self._prepared is None or self._consumed:_fail('Native qualification is missing or already consumed.')
            self._consumed=True
            return copy.deepcopy(self._prepared)
        if self._prepared is None:self._prepared=owner._prepare_builtin_recipe_material_current(value)
        return copy.deepcopy(self._prepared)

    def consume_admission(self):
        self._check(self.recipe)
        if self._consumed:_fail('Native qualification has already been consumed.')
        self._consumed=True


class PurePreparationContext:
    """Current integrity qualification; it cannot authorize a child phase."""
    def __init__(self,adapter,owner,graph):
        self.adapter,self.owner=adapter,owner;self.graph=copy.deepcopy(graph)
        self.recipe=graph['recipe'];self.definition=owner.definition_identity(self.recipe)
        self.actor=adapter.access.require('execute','pipeline.snapshot',graph['id'],owner_only=True)
        self.validation=owner.validate_graph(graph)
        if not self.validation['valid']:
            first=self.validation['errors'][0];_fail(first['message'],first['code'])
        self.release=owner.inspect_release(self.validation['release']['id'],private=True,recipe=self.recipe)
        self._consumed=False;self._active=True

    def consume_admission(self):
        if not self._active or self._consumed:_fail('Current integrity qualification has already been consumed.')
        self.adapter.session.check()
        actor=self.adapter.access.require('execute','pipeline.snapshot',self.graph['id'],owner_only=True)
        if actor.actor_id!=self.actor.actor_id:_fail('Current integrity caller changed.','conflict')
        if self.owner.get(self.graph['id'])!=self.graph or self.owner.definition_identity(self.recipe)!=self.definition:
            _fail('Current integrity graph or source changed.','stale')
        if self.owner.inspect_release(self.release['id'],private=True,recipe=self.recipe)!=self.release:
            _fail('Current integrity frozen input changed.','stale')
        self._consumed=True


class ProjectNativePreparation:
    def __init__(self,projection):
        self.projection=projection;self.session=projection.session;self.db=projection.db
        self.access=projection.execution.runtime_access;self.execution=projection.execution;self.materials=projection.materials

    def current(self,owner):
        context=_CURRENT.get()
        if not isinstance(context,NativePreparationContext) or context.adapter is not self or owner.db is not self.db:
            _fail('Native qualification requires an explicit current preparation.')
        return context

    def probe(self,owner,recipe):
        actor=self.access._context()
        if actor.mode=='job':
            if actor.kind!='runs' or actor.catalog_id!=self.session.project_id:
                _fail('Native probe requires its exact current Run admission.')
            self.access.require('execute','pipeline.probe_native',recipe)
            result=self.execution.native.probe_current_run(owner,recipe)
            return copy.deepcopy(result['runtime'])
        return self.current(owner).probe(owner,recipe)

    @contextmanager
    def _scope(self,owner,graph,model,composition,purpose,expected_checkpoint,key):
        if self.db.in_transaction:_fail('Native preparation must precede the metadata transaction.','unsupported')
        if _CURRENT.get() is not None:_fail('A native preparation is already active.','busy')
        self.access.require('edit','native_preparation.'+purpose,graph['id'],owner_only=True)
        self.session.check()
        if self.session.snapshot['checkpoint']!=expected_checkpoint:_fail('Expected project checkpoint changed.','stale_project')
        context=NativePreparationContext(self,owner,graph,model,composition,purpose,_key(purpose,key))
        result=dict(format='project_native_preparation_intent_v1',origin_catalog_id=self.session.project_id,
            actor_id=context.actor.actor_id,purpose=purpose,graph=dict(id=graph['id'],revision=graph['revision'],
            document_sha256=digest(graph),execution_sha256=execution_digest(graph)),model=model,
            composition=None if composition is None else composition['ref'],release_id=context.release_id,
            definition_identity=context.definition,runtime=context.runtime,occurred_at=timestamp())
        body={name:copy.deepcopy(value) for name,value in result.items() if name not in ('format','occurred_at')}
        self.session.mutate('native_preparation.intent',graph['id'],body,expected_checkpoint,context.key,
            lambda:copy.deepcopy(result),lambda value,before:dict(records=[],result=value),scope='execute')
        context._active=True;token=_CURRENT.set(context)
        try:yield context
        finally:_CURRENT.reset(token);context._active=False;context._prepared=None

    def validate_graph(self,owner,graph_id,revision,expected_checkpoint,key):
        self.access.require('edit','native_preparation.validation',graph_id,owner_only=True)
        self.access.require('execute','pipeline.probe_native',graph_id,owner_only=True)
        body=dict(graph_id=graph_id,revision=revision)
        prior=operation_records(self.session.snapshot['records']).get(key)
        if prior is not None:
            return self.session.mutate('native_preparation.validate',graph_id,body,expected_checkpoint,key,
                lambda:(_ for _ in ()).throw(RuntimeError('Native validation replay launched a probe.')),
                lambda value,before:dict(records=[],result=value),scope='execute')
        graph=owner.get(graph_id)
        if graph['revision']!=revision:_fail('Graph changed before native validation.','stale')
        import release_validation
        if adapter_for_graph(graph) is release_validation:
            self.session.check()
            if self.session.snapshot['checkpoint']!=expected_checkpoint:_fail('Expected project checkpoint changed.','stale_project')
            value=owner.validate_graph(graph)
            return self.session.mutate('native_preparation.validate',graph_id,body,expected_checkpoint,key,
                lambda:copy.deepcopy(value),lambda value,before:dict(records=[],result=value),scope='execute')
        with self._scope(owner,graph,None,None,'validation',expected_checkpoint,key) as context:
            value=owner.validate_graph(graph);context._check(graph['recipe'])
            return self.session.mutate('native_preparation.validate',graph_id,body,self.session.snapshot['checkpoint'],key,
                lambda:copy.deepcopy(value),lambda value,before:dict(records=[],result=value),scope='execute')

    @contextmanager
    def current_graph(self,owner,graph_id,revision,expected_checkpoint,key):
        if self.db.in_transaction:_fail('Current native validation must precede admission.','unsupported')
        self.access.require('edit','native_preparation.admission',graph_id,owner_only=True)
        self.session.check()
        if self.session.snapshot['checkpoint']!=expected_checkpoint:_fail('Expected project checkpoint changed.','stale_project')
        graph=owner.get(graph_id)
        if graph['revision']!=revision:_fail('Graph changed before native admission.','stale')
        import release_validation
        if adapter_for_graph(graph) is release_validation:
            context=PurePreparationContext(self,owner,graph)
            try:yield context
            finally:context._active=False
            return
        with self._scope(owner,graph,None,None,'admission',expected_checkpoint,key) as context:
            context.validation=owner.validate_graph(graph)
            if not context.validation['valid']:
                first=context.validation['errors'][0];_fail(first['message'],first['code'])
            context._check(graph['recipe'])
            yield context

    def prepare_recipe(self,owner,graph_id,revision,model_ref,expected_checkpoint,key):
        self.materials._require_resolved('pipeline_graph',graph_id)
        self.access.require('edit','recipes.prepare_builtin_material',graph_id,owner_only=True)
        self.access.require('execute','pipeline.probe_native',graph_id,owner_only=True)
        body=dict(graph_id=graph_id,revision=revision,model=model_ref,reconcile_capture=False)
        operation='recipes.prepare_builtin_material'
        if key in operation_records(self.session.snapshot['records']):
            return self.session.mutate(operation,graph_id,body,expected_checkpoint,key,
                lambda:(_ for _ in ()).throw(RuntimeError('Material replay launched a native probe.')),
                lambda value,before:dict(records=[],result=value))
        graph=owner.get(graph_id)
        if graph['revision']!=revision or not model_aware_graph(graph):_fail('Exact model-aware graph is unavailable.','stale')
        self.materials.materialize_projection(model_ref,owner.dataset.models.path)
        with self._scope(owner,graph,model_ref,None,'material',expected_checkpoint,key) as context:
            prepared=owner.prepare_builtin_material(graph_id,revision,model_ref)
            try:
                context._check(graph['recipe'])
                def capture(value,before):
                    record=self.materials.capture_recipe_material(value,owner.material_path)
                    return dict(records=self.materials._coalesce([record,*self.materials.declarations(record),
                        *self.materials.capture_recipe_dependencies(record,before)]),result=value)
                return self.session.mutate(operation,graph_id,body,self.session.snapshot['checkpoint'],key,
                    lambda:owner._retain_material(prepared),capture)
            finally:
                if prepared['staging'].exists():shutil.rmtree(prepared['staging'])

    @contextmanager
    def admission(self,owner,material_ref,expected_checkpoint,key):
        value=self.materials.recipe(material_ref,verify=True)
        import json
        snapshot=json.loads(self.materials.blob(material_ref,value['material']['recipe_document'],2*1024**2))
        graph=decode_graph(snapshot['graph'])
        with self._scope(owner,graph,value['material']['model'],value,'admission',expected_checkpoint,key) as context:
            context.capture_builtin(owner,value)
            yield context
