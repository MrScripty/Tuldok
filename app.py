"""Tuldok: local image capture and corner-label dataset workspace."""
import argparse
from contextlib import contextmanager
import psycopg
import ai
import ai_codex
import ai_http
import image_generation
import pumas_operations
import synthetic
import gateway_discovery
import workbench
import dataset_recipes
import dataset_releases
import saved_selections
import saved_searches
import grounded_candidates
import caption_proposals
import text_classification_proposals
import bulk_import
import curation
import caption_import
import native_text_import
import native_detection_import
import rheon_sequences
import sequence_batch_import
import meshes
import spatial_assets
import pipeline
import model_definitions
import experiments
import projects
import access
import agent_api
from mcp_observer import (add_interface_options, configured_interface, observe_begin, observe_stage,
                          observe_selection, observe_request_bytes, observe_close, outcome)
from access import authorized
from http.cookies import SimpleCookie, CookieError
import runs
import base64
import hashlib
import io
import ipaddress
import json
import math
import re
import shutil
from metadata import Metadata, StorageError, CommitOutcomeUnknown, CatalogBusy
from project_store import ProjectStoreError
from image_sources import ImageSources, Conflict, now, metadata, validate_annotation, CORNERS, VISIBILITY, SPLITS
import tempfile
import threading
import time
import uuid
import zipfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent
MAX_BODY = 40 * 1024 * 1024


class Dataset(ImageSources):
    def __init__(self, path, *, dsn=None, project_roots=None):
        self._close_lock = threading.RLock()
        self._closed = False
        self._extraction_condition = threading.Condition()
        self._extraction_requests = {}
        self._extraction_stopping = False
        self._extraction_binding = uuid.uuid4().hex
        self._extraction_guard = None
        self._extraction_closer = None
        self._extraction_close_error = None
        self.path = Path(path).resolve()
        self.path.mkdir(parents=True, exist_ok=True)
        (self.path / 'images').mkdir(exist_ok=True)
        self.ai_lock = threading.Lock()
        self.db = Metadata(self.path, dsn=dsn)
        self.lock = self.db.lock
        self.access = access.Access(self.db, self.path)
        self.image_requests = image_generation.ImageRequests(self.access)
        try:
            with self.access._reconcile():
                self.projects = projects.Projects(self, project_roots)
                self.generation_jobs = synthetic.Jobs(self)
                with self.lock:
                    self._recover_deletions()
                self.workbench = workbench.Workbench(self)
                self.releases = dataset_releases.Releases(self.workbench)
                self.selections = saved_selections.SavedSelections(self.workbench)
                self.searches = saved_searches.SavedSearches(self.workbench)
                self.caption_imports = caption_import.CaptionImports(self.workbench)
                self.native_text_imports = native_text_import.NativeTextImports(self.workbench)
                self.native_detection_imports = native_detection_import.NativeDetectionImports(self.workbench)
                self.grounded = grounded_candidates.Proposals(self.workbench)
                self.caption_proposals = caption_proposals.CaptionProposals(self.workbench)
                self.text_classification_proposals = text_classification_proposals.TextClassificationProposals(self.workbench)
                self.pipelines = pipeline.Pipelines(self)
                self.runs = runs.Runs(self, self.pipelines)
                self.models = model_definitions.ModelDefinitions(self)
                self.studies = experiments.Experiments(self)
        except BaseException:
            if hasattr(self, 'projects'):
                self.projects.close()
            self.db.close()
            raise

    def close(self):
        with self._close_lock:
            if self._closed:
                return
            with self.access._reconcile():
                self.runs.close()
                self.text_classification_proposals.close()
                self.caption_proposals.close()
                self.grounded.close()
                self.generation_jobs.close()
                self.projects.close()
                self.db.close()
                self._closed = True

    def close_for_project_extraction(self, *, deadline):
        """Bound this explicit stop without treating a timeout as cessation."""
        guard = self._extraction_guard
        if guard is None:
            raise workbench.WorkbenchError('A drained original controller is required.', 'source_busy', 409)
        guard.require(self)
        if type(deadline) not in (int, float) or not math.isfinite(deadline):
            raise workbench.WorkbenchError('An exact stop deadline is required.')
        with self._extraction_condition:
            if self._extraction_closer is None:
                def close_owned():
                    try:
                        self.close()
                    except BaseException as error:
                        self._extraction_close_error = error
                self._extraction_closer = threading.Thread(
                    target=close_owned, name='tuldok-legacy-extraction-close', daemon=True)
                try:
                    self._extraction_closer.start()
                except BaseException as error:
                    self._extraction_close_error = error
                    raise workbench.WorkbenchError('Owned legacy closure could not start; source remains fenced.', 'unknown', 503) from error
            closer = self._extraction_closer
        closer.join(max(0, deadline - time.monotonic()))
        if closer.is_alive():
            raise workbench.WorkbenchError('Owned legacy workers have not drained; source remains fenced.', 'source_busy', 409)
        if self._extraction_close_error is not None:
            raise workbench.WorkbenchError('Owned legacy closure failed; source remains fenced.', 'unknown', 503) from self._extraction_close_error
        if not self._closed:
            raise workbench.WorkbenchError('Owned legacy closure is unconfirmed; source remains fenced.', 'unknown', 503)
        guard.require(self)

    @contextmanager
    def _project_request(self):
        """Fence new legacy handlers before an explicit extraction stop."""
        identity = threading.get_ident()
        with self._extraction_condition:
            if self._extraction_stopping:
                raise workbench.WorkbenchError('This catalog is stopped for project extraction.', 'source_stopping', 409)
            self._extraction_requests[identity] = self._extraction_requests.get(identity, 0) + 1
        try:
            yield
        finally:
            with self._extraction_condition:
                self._extraction_requests[identity] -= 1
                if not self._extraction_requests[identity]:
                    del self._extraction_requests[identity]
                self._extraction_condition.notify_all()

    def stop_for_project_extraction(self, backup_parent_fd, backup_directory, external_roots=None):
        """Explicit owner action; ordinary preview/Open never enters this path."""
        deadline = time.monotonic() + 60
        identity = threading.get_ident()
        with self._extraction_condition:
            if self._extraction_stopping:
                raise workbench.WorkbenchError('Catalog extraction stop already has an owner.', 'source_stopping', 409)
            self.access.require('admin', 'project_transfer.stop_source', owner_only=True)
            self._extraction_stopping = True
            guard = _LegacyExtractionGuard(self, self._extraction_binding, identity)
            self._extraction_guard = guard
            while any(thread != identity and count for thread, count in self._extraction_requests.items()):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise workbench.WorkbenchError('Existing requests have not drained; catalog remains fenced.', 'source_busy', 409)
                self._extraction_condition.wait(min(.1, remaining))
        from project_transfer import stop_source
        return stop_source(self, backup_parent_fd=backup_parent_fd, backup_directory=backup_directory,
                           external_roots=external_roots, controller_guard=guard)


    @authorized('execute', 'dataset.suggest', owner_only=True)
    def suggest(self, body):
        sample_id = body.get('sample_id')
        before = self.sample(sample_id)
        if before is None:
            raise ValueError('Image not found.')
        if type(body.get('revision')) is not int or body['revision'] != before['revision']:
            raise Conflict('This image changed in another tab. Reload it before requesting a suggestion.')
        if not self.ai_lock.acquire(blocking=False):
            raise Conflict('Another AI suggestion is running. Wait for it to finish.')
        try:
            result, source = ai.suggest(self.path / 'images' / sample_id / 'image.png', body)
            if not {'book_present', 'crop_suitable', 'corner_reference', 'corners'}.issubset(result):
                raise ValueError('The model returned an incomplete corner label.')
            annotation = validate_annotation(result)
            annotation['suggested_by'] = source
            after = self.sample(sample_id)
            if after is None or after['revision'] != before['revision']:
                raise Conflict('This image changed while the model was running. Reload it before applying a suggestion.')
            return {'sample_id': sample_id, 'revision': before['revision'], 'annotation': annotation}
        finally:
            self.ai_lock.release()

    @authorized('inspect', 'dataset.export')
    def export(self):
        with self.lock:
            return self._export()

    def _export(self):
        rows = [row for row in self.rows() if row['annotation']]
        if not rows:
            raise ValueError('Label at least one image before exporting.')
        target = tempfile.TemporaryFile()
        try:
            with zipfile.ZipFile(target, 'w', zipfile.ZIP_STORED) as archive:
                manifest = []
                for row in rows:
                    image_path = 'images/' + row['id'] + '.png'
                    archive.write(self.path / 'images' / row['id'] / 'image.png', image_path)
                    manifest.append(dict(row, image=image_path, group_id=('book:' + row['book_id']) if row['book_id'] else ('session:' + row['session_id'])))
                archive.writestr('labels.jsonl', ''.join(json.dumps(r) + '\n' for r in manifest))
                archive.writestr('schema.json', json.dumps({
                    'version': 2, 'coordinates': 'Normalized 0..1 in EXIF-oriented image pixels: x/(width-1), y/(height-1).',
                    'corner_order': CORNERS, 'hidden_coordinates': None,
                    'corner_reference': 'Per annotation: book means corners as viewed with the book upright; image means screen-relative. Legacy labels are image-relative.',
                    'target': 'Outer corners of the whole open spread or closed cover, without padding.',
                    'samples': len(rows), 'unlabeled_excluded': len(self.rows()) - len(rows),
                }, indent=2))
            target.seek(0)
            return target
        except Exception:
            target.close()
            raise


class _LegacyExtractionGuard:
    """An in-process controller proof, never a transport or project record."""
    def __init__(self, dataset, binding, owner_thread):
        self.dataset, self.binding, self.owner_thread = dataset, binding, owner_thread

    def require(self, dataset):
        with dataset._extraction_condition:
            if (dataset is not self.dataset or dataset._extraction_guard is not self
                    or dataset._extraction_binding != self.binding or not dataset._extraction_stopping
                    or threading.get_ident() != self.owner_thread
                    or any(thread != self.owner_thread and count for thread, count in dataset._extraction_requests.items())):
                raise workbench.WorkbenchError('Extraction requires the drained original catalog controller.', 'source_busy', 409)


def make_handler(dataset, observer=None, *, transfer_controller=None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def _observe_request(self, handler):
            self._handoff_stopped_source()
            name, version = (agent_api.observation_operation(self.command, self.path, self.headers)
                             if observer is not None else (None, None))
            self._observation_operation, self._observation_version = name, version
            self._observation = observe_begin(observer, self.command, name, selected_version=version)
            self._observation_finished = False
            self._contract_selection = None
            try:
                if (urlsplit(self.path).path == '/api/workspace/project-transfer'
                        or urlsplit(self.path).path.startswith('/api/workspace/project-transfer/')):
                    return self._handle_project_transfer()
                if isinstance(dataset, Dataset):
                    try:
                        with dataset._project_request():
                            return handler()
                    except workbench.WorkbenchError as error:
                        return self.reply({'error': str(error), 'code': error.code}, error.status)
                return handler()
            finally:
                if not self._observation_finished:
                    observe_stage(observer, self._observation, 'terminal', outcome='unknown', delivery='incomplete')
                    self._observation_finished = True

        def _handoff_stopped_source(self):
            nonlocal dataset
            if transfer_controller is None or transfer_controller.phase == 'source_live':
                return
            source = transfer_controller.dataset
            # A failed stop may still have old handlers draining. Keep their
            # original Dataset closure until the source's request gate proves
            # them absent; new ordinary requests remain fenced meanwhile.
            with source._extraction_condition:
                if source._extraction_stopping and not any(source._extraction_requests.values()):
                    dataset = transfer_controller.control_workspace

        def _handle_project_transfer(self):
            """One explicit source-to-control authority transition, never Open."""
            nonlocal dataset
            routes = {('GET', '/api/workspace/project-transfer'): 'status',
                ('POST', '/api/workspace/project-transfer/preview'): 'preview',
                ('GET', '/api/workspace/project-transfer/report'): 'report_page',
                ('POST', '/api/workspace/project-transfer/stop'): 'stop',
                ('POST', '/api/workspace/project-transfer/extract'): 'extract'}
            try:
                if transfer_controller is None:
                    raise workbench.WorkbenchError('Configure an explicit existing legacy extraction controller first.', 'unavailable', 409)
                action = routes.get((self.command, urlsplit(self.path).path))
                if action is None:
                    raise workbench.WorkbenchError('Unknown extraction operation.', 'unsupported', 404)
                name = 'project_transfer.' + action
                token, bearer = self._credential()
                authority = transfer_controller.access
                with authority.bind(token):
                    self._same_origin(self.command == 'POST' and not bearer)
                    selected = self._select_contract()
                    agent_api.require_selection(selected, name)
                    body = None
                    if self.command == 'POST':
                        if self.headers.get_content_type() != 'application/json':
                            raise agent_api.AgentAPIError('Send a bounded JSON request.', 'invalid', 400)
                        length = int(self.headers.get('Content-Length', '0'))
                        if not 0 < length <= agent_api.REQUEST_LIMIT:
                            raise agent_api.AgentAPIError('Extraction request exceeds its bound.', 'too_large', 413)
                        raw = self.rfile.read(length)
                        observe_request_bytes(observer, self._observation, len(raw))
                        body = agent_api.decode(raw)
                    arguments = agent_api.validate_selected(selected, self.command, self.path, body)
                    self._observe_dispatch(body)
                    try:
                        if action == 'status': value = transfer_controller.status()
                        elif action == 'preview': value = transfer_controller.preview(**arguments)
                        elif action == 'report_page': value = transfer_controller.report_page(**arguments)
                        elif action == 'stop': value = transfer_controller.stop(**arguments)
                        else: value = transfer_controller.extract(**arguments)
                    finally:
                        self._handoff_stopped_source()
                    return self.reply(value)
            except (workbench.WorkbenchError, ProjectStoreError, agent_api.AgentAPIError, access.AccessError) as error:
                result = {'error': str(error), 'code': error.code}
                if hasattr(error, 'receipt'):
                    result['receipt'] = error.receipt
                return self.reply(result, error.status)
            except (CommitOutcomeUnknown, psycopg.Error):
                return self.reply({'error': 'Extraction outcome requires explicit inspection.', 'code': 'storage'}, 503)
            except OSError:
                return self.reply({'error': 'Extraction storage outcome requires explicit status inspection; retained staging was not removed.',
                                   'code': 'storage'}, 503)

        def _observe_dispatch(self, body=None):
            observe_selection(observer, getattr(self, '_observation', None),
                              self._observation_operation, body, self._observation_version)
            for phase in ('validated', 'admitted', 'dispatch'):
                observe_stage(observer, getattr(self, '_observation', None), phase)

        def _write_observed(self, chunks, status):
            observation = getattr(self, '_observation', None)
            written = 0
            try:
                for raw in chunks:
                    view = memoryview(raw)
                    while view:
                        count = self.connection.send(view)
                        if count <= 0:
                            raise BrokenPipeError()
                        written += count
                        view = view[count:]
            except (OSError, ConnectionError):
                self.close_connection = True
                observe_stage(observer, observation, 'terminal', outcome='unknown',
                              response_bytes=written, delivery='incomplete')
            else:
                observe_stage(observer, observation, 'terminal', outcome=outcome(status),
                              envelope_status=status, http_status=status,
                              response_bytes=written, delivery='written')
            self._observation_finished = True

        def reply(self, data, status=200, content_type='application/json', headers=()):
            selected = getattr(self, '_contract_selection', None)
            if selected is not None and content_type == 'application/json':
                try:
                    agent_api.validate_output(selected[0], {'status': status, 'result': data}, selected[1])
                    data = agent_api.encoded(data)
                    if len(data) > agent_api.RESPONSE_LIMIT:
                        raise agent_api.AgentAPIError('Selected result exceeds its bound.')
                except agent_api.AgentAPIError:
                    data, status = {'error': 'Selected result is invalid; inspect durable state before retrying.',
                                    'code': 'contract_output'}, 502
            if content_type == 'application/json' and not isinstance(data, bytes):
                data = json.dumps(data).encode()
            if selected is not None and selected[0] == 'runs.artifact_segments':
                guard = getattr(self, '_artifact_segments_guard', None)
                if guard is not None:
                    del self._artifact_segments_guard
                if guard is not None and status < 400:
                    guard()  # Current authority after schema validation and serialization.
            observe_stage(observer, getattr(self, '_observation', None), 'returned',
                          outcome=outcome(status), envelope_status=status, http_status=status)
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            for key, value in headers:
                self.send_header(key, value)
            self.end_headers()
            self._write_observed((data,), status)

        def project_error(self, error):
            value = {'error': str(error), 'code': error.code}
            # Only the typed project boundary can attach a non-secret durable
            # receipt. Selected output validation checks its closed schema.
            if getattr(dataset, 'project_files_mode', False) and hasattr(error, 'receipt'):
                value['receipt'] = error.receipt
            return self.reply(value, error.status)

        def reply_stream(self, stream, metadata):
            # The owner has already verified a private spool before HTTP success.
            observe_stage(observer, getattr(self, '_observation', None), 'returned',
                          outcome='success', envelope_status=200, http_status=200)
            self.send_response(200)
            self.send_header('Content-Type', metadata['media_type'])
            self.send_header('Content-Length', str(metadata['bytes']))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            def chunks():
                while True:
                    raw = stream.read(65536)
                    if not raw:
                        return
                    yield raw
            self._write_observed(chunks(), 200)

        def project_access(self):
            # This opt-in file inspection surface is local-only until actor authentication.
            host = urlsplit('http://' + self.headers.get('Host', '')).hostname
            if (host not in ('localhost', '127.0.0.1', '::1') or
                    not ipaddress.ip_address(self.client_address[0]).is_loopback):
                raise workbench.WorkbenchError('Project inspection requires a local loopback client and host.', 'forbidden', 403)

        def _credential(self):
            authorization = self.headers.get('Authorization')
            if authorization is not None:
                if self.headers.get('Cookie'):
                    raise access.AccessError('Use one credential transport per request.', 'forbidden', 403)
                parts = authorization.split(' ')
                if len(parts) != 2 or parts[0].lower() != 'bearer' or not parts[1]:
                    raise access.AccessError('Use an authenticated bearer credential.', 'unauthenticated', 401)
                return parts[1], True
            try:
                cookies = SimpleCookie(self.headers.get('Cookie', ''))
                token = cookies['tuldok_session'].value if 'tuldok_session' in cookies else ''
            except CookieError:
                token = ''
            return token, False

        def _same_origin(self, required):
            origin = self.headers.get('Origin')
            if (required and not origin) or (origin and origin != 'http://' + self.headers.get('Host', '')):
                raise access.AccessError('A same-origin request is required.', 'forbidden', 403)

        def _access_body(self):
            if self.headers.get_content_type() != 'application/json':
                raise access.AccessError('Send a JSON object.', 'invalid', 400)
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 16384:
                    raise ValueError()
                raw = self.rfile.read(length)
                observe_request_bytes(observer, getattr(self, '_observation', None), len(raw))
                body = projects.decode(raw)
                if not isinstance(body, dict):
                    raise ValueError()
                self._observe_dispatch(body)
                return body
            except (ValueError, workbench.WorkbenchError):
                raise access.AccessError('Access requests require a bounded JSON object.', 'invalid', 400) from None

        def _access_error(self, error):
            try:
                dataset.access.denial(error, 'http.request', urlsplit(self.path).path[:512], anonymous=True)
            except CommitOutcomeUnknown:
                return self.reply({'error': 'Commit outcome is unknown; inspect state before retrying.', 'code': 'commit_unknown'}, 503)
            except psycopg.Error:
                return self.reply({'error': 'Metadata storage is unavailable.', 'code': 'storage'}, 503)
            return self.reply({'error': str(error), 'code': error.code}, error.status)

        def _model_page_query(self, *, study=False):
            query=parse_qs(urlsplit(self.path).query)
            allowed=('offset','limit','revision') if study else ('cursor','limit')
            if set(query)-set(allowed) or any(len(values)!=1 for values in query.values()):
                raise workbench.WorkbenchError('Invalid page query.')
            result={}
            for key,values in query.items():
                if key=='cursor':result[key]=values[0]
                elif not re.fullmatch('[0-9]{1,16}',values[0]):raise workbench.WorkbenchError('Invalid numeric page query.')
                else:result[key]=int(values[0])
            return result

        def _lineage_page_query(self):
            try:
                query = parse_qs(urlsplit(self.path).query, keep_blank_values=True, max_num_fields=4)
            except ValueError as error:
                raise workbench.WorkbenchError('Invalid lineage page query.') from error
            if set(query) - {'cursor', 'limit', 'revision', 'cohort'} or any(len(v) != 1 for v in query.values()):
                raise workbench.WorkbenchError('Invalid lineage page query.')
            result = {key: values[0] for key, values in query.items()}
            if 'limit' in result:
                if not re.fullmatch('[0-9]{1,2}', result['limit']):
                    raise workbench.WorkbenchError('Invalid lineage page limit.')
                result['limit'] = int(result['limit'])
            return result

        def _select_contract(self):
            selected = agent_api.select_request(self.headers, self.command, self.path)
            if selected is not None:
                lengths = self.headers.get_all('Content-Length', [])
                if (self.headers.get_all('Transfer-Encoding', []) or len(lengths) > 1
                        or (lengths and not re.fullmatch('[0-9]{1,10}', lengths[0]))
                        or (self.command == 'GET' and lengths and int(lengths[0]) != 0)
                        or (self.command == 'POST' and (len(lengths) != 1 or
                            not 0 < int(lengths[0]) <= agent_api.REQUEST_LIMIT))):
                    raise agent_api.AgentAPIError('Selected request framing is unsupported.', 'contract_mismatch', 409)
            self._contract_selection = selected
            return selected

        def _snapshot_contract_access(self, project_id, operation, version, scope='inspect'):
            # Older wire contracts keep E1's owner-only v2 source boundary.
            selected = self._contract_selection
            if selected is not None and selected[0] == operation and selected[1] >= version:
                return
            saved = dataset.projects._saved(project_id, extensions=True)
            if saved['manifest']['schema_version'] == 2:
                dataset.access.require(scope, operation, project_id, owner_only=True)

        def _graph_snapshot_contract_access(self, graph_id, revision, operation, version, scope='inspect', *, graph=None):
            selected = self._contract_selection
            if selected is not None and selected[0] == operation and selected[1] >= version:
                return
            if graph is None:
                graph = dataset.pipelines.get(graph_id)
            if graph['revision'] != revision:
                raise workbench.WorkbenchError('Graph changed. Reload.', 'stale', 409)
            if graph.get('recipe') == 'external_recipe':
                configuration, _parameters = pipeline.recipe_contract.graph_parameters(graph)
                self._snapshot_contract_access(configuration['project_id'], operation, version, scope)

        def do_GET(self):
            return self._observe_request(self._handle_GET)

        def _handle_GET(self):
            self._contract_selection = None
            try:
                if not urlsplit(self.path).path.startswith('/api/'):
                    self._select_contract()
                    self._observe_dispatch()
                    return self._get()
                token, _bearer = self._credential()
                with dataset.access.bind(token):
                    dataset.access.require('inspect', 'http.inspect')
                    try:
                        self._same_origin(False)
                    except access.AccessError as error:
                        dataset.access.denial(error, 'http.get', urlsplit(self.path).path[:512])
                        raise
                    selected = self._select_contract()
                    agent_api.validate_selected(selected, self.command, self.path, None)
                    self._observe_dispatch()
                    if urlsplit(self.path).path == '/api/access/session':
                        return self.reply(dataset.access.identity())
                    return self._get()
            except agent_api.AgentAPIError as error:
                return self.reply({'error': str(error), 'code': error.code}, error.status)
            except access.AccessError as error:
                return self._access_error(error)
            except CommitOutcomeUnknown:
                return self.reply({'error': 'Commit outcome is unknown; inspect state before retrying.', 'code': 'commit_unknown'}, 503)
            except psycopg.Error:
                return self.reply({'error': 'Metadata storage is unavailable.', 'code': 'storage'}, 503)

        def do_POST(self):
            return self._observe_request(self._handle_POST)

        def _handle_POST(self):
            self._contract_selection = None
            try:
                path = urlsplit(self.path).path
                if path == '/api/access/session':
                    self._select_contract()
                    self._same_origin(True)
                    body = self._access_body()
                    if set(body) != {'token'}:
                        raise access.AccessError('Provide one sign-in token.', 'invalid', 400)
                    result = dataset.access.exchange(body['token'])
                    cookie = 'tuldok_session=' + result['token'] + '; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800'
                    return self.reply(result['identity'], headers=[('Set-Cookie', cookie)])
                token, bearer = self._credential()
                with dataset.access.bind(token):
                    try:
                        self._same_origin(not bearer)
                    except access.AccessError as error:
                        dataset.access.denial(error, 'http.post', path)
                        raise
                    self._select_contract()
                    if path == '/api/access/logout':
                        self._access_body()
                        dataset.access.logout()
                        return self.reply({'signed_out': True}, headers=[('Set-Cookie', 'tuldok_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')])
                    if path == '/api/access/credentials':
                        return self.reply(dataset.access.issue(self._access_body()), 201)
                    if path.startswith('/api/access/credentials/') and path.endswith('/revoke'):
                        self._access_body()
                        return self.reply(dataset.access.revoke(path.split('/')[-2]))
                    if (getattr(dataset, 'project_files_mode', False) and
                            not path.startswith('/api/workspace/project-files/')):
                        return self.reply({'error': 'This domain is unavailable until its canonical project publication is implemented.',
                                           'code': 'unavailable'}, 409)
                    if path.startswith('/api/access/execution-grants/') and path.endswith('/revoke'):
                        projects.closed(self._access_body(), ())
                        return self.reply(dataset.access.revoke_execution(path.split('/')[-2]))
                    return self._post()
            except agent_api.AgentAPIError as error:
                return self.reply({'error': str(error), 'code': error.code}, error.status)
            except access.AccessError as error:
                return self._access_error(error)
            except CommitOutcomeUnknown:
                return self.reply({'error': 'Commit outcome is unknown; inspect state before retrying.', 'code': 'commit_unknown'}, 503)
            except psycopg.Error:
                return self.reply({'error': 'Metadata storage is unavailable.', 'code': 'storage'}, 503)

        def _get(self):
            path = urlsplit(self.path).path
            try:
                if path == '/api/agent/operations':
                    return self.reply(agent_api.discovery())
                if path == '/api/agent/capabilities':
                    capabilities = (dataset.capabilities() if getattr(dataset, 'project_files_mode', False)
                                    else agent_api.capabilities(dataset.db.dataset_id))
                    if not getattr(dataset, 'project_files_mode', False):
                        for operation in capabilities['operations']:
                            if operation['id'].startswith('project_files.'):
                                operation['availability'] = 'unavailable'
                            if operation['id'].startswith('project_transfer.'):
                                operation['availability'] = ('available' if transfer_controller is not None
                                                             else 'unavailable')
                    return self.reply(capabilities)
                if path == '/api/workspace/context' and getattr(dataset, 'project_files_mode', False):
                    # Bootstrap identifies the installation that owns this
                    # credential, without constructing a legacy domain owner.
                    return self.reply({'version': 1, 'mode': 'real', 'dataset_id': dataset.db.dataset_id,
                                       'project_files': True})
                if path == '/api/workspace/project-files' or path.startswith('/api/workspace/project-files/'):
                    if not getattr(dataset, 'project_files_mode', False):
                        raise workbench.WorkbenchError('Start explicit project-file mode to use this capability.', 'unavailable', 409)
                    from project_workspace import http_arguments
                    name, arguments = http_arguments('GET', self.path)
                    return self.reply(dataset.dispatch(name, arguments,
                        selected_version=self._contract_selection[1] if self._contract_selection else None))
                if getattr(dataset, 'project_files_mode', False) and path.startswith('/api/'):
                    raise workbench.WorkbenchError('This domain is unavailable until its canonical project publication is implemented.',
                                                  'unavailable', 409)
                if (path == '/api/workspace/projects' or path.startswith('/api/workspace/projects/')
                        or path == '/api/workspace/project-snapshots' or path.startswith('/api/workspace/project-snapshots/')):
                    self.project_access()
                if path.startswith('/api/workspace/'):
                    parts = path.removeprefix('/api/workspace/').split('/')
                    if parts == ['experiment-lineage']:
                        agent_api.require_selection(self._contract_selection,'studies.lineage')
                        return self.reply(dataset.studies.lineage.list(**self._lineage_page_query()))
                    if len(parts) == 2 and parts[0] == 'experiment-lineage':
                        agent_api.require_selection(self._contract_selection,'studies.lineage_trial')
                        return self.reply(dataset.studies.lineage.get(parts[1]))
                    if parts == ['models']:
                        agent_api.require_selection(self._contract_selection,'models.list')
                        return self.reply(dataset.models.list(**self._model_page_query()))
                    if parts == ['model-recipes']:
                        agent_api.require_selection(self._contract_selection,'recipes.list_drafts')
                        return self.reply(dataset.pipelines.list_recipes(**self._model_page_query()))
                    if len(parts)==2 and parts[0]=='model-recipes':
                        agent_api.require_selection(self._contract_selection,'recipes.get')
                        return self.reply(dataset.pipelines.get_recipe(parts[1]))
                    if len(parts)==2 and parts[0]=='models':
                        agent_api.require_selection(self._contract_selection,'models.get')
                        return self.reply(dataset.models.get(parts[1]))
                    if parts == ['studies']:
                        agent_api.require_selection(self._contract_selection,'studies.list')
                        return self.reply(dataset.studies.list(**self._model_page_query()))
                    if len(parts)==2 and parts[0]=='studies':
                        agent_api.require_selection(self._contract_selection,'studies.get')
                        return self.reply(dataset.studies.get(parts[1],**self._model_page_query(study=True)))
                    if len(parts)==2 and parts[0]=='candidates':
                        agent_api.require_selection(self._contract_selection,'studies.candidate')
                        return self.reply(dataset.studies.candidate(parts[1]))
                    if len(parts)==3 and parts[0]=='candidates' and parts[2]=='package-state':
                        agent_api.require_selection(self._contract_selection,'studies.package_state')
                        return self.reply(dataset.studies.package_state(parts[1]))
                    if len(parts)==2 and parts[0]=='trials':
                        agent_api.require_selection(self._contract_selection,'studies.trial')
                        return self.reply(dataset.studies.trial(parts[1]))
                    if parts == ['project-snapshots']:
                        if self._contract_selection is not None:
                            agent_api.require_selection(self._contract_selection,'project_snapshots.list')
                            return self.reply(dataset.projects.list_snapshot_catalog(**self._model_page_query()))
                        return self.reply(dataset.projects.list_snapshots())
                    if len(parts) == 2 and parts[0] == 'project-snapshots':
                        if self._contract_selection is not None:
                            agent_api.require_selection(self._contract_selection,'project_snapshots.get')
                            result = dataset.projects.inspect_snapshot(parts[1])
                            if self._contract_selection[1] == 1:
                                result.pop('activity', None)
                            return self.reply(result)
                        return self.reply(dataset.projects.get_snapshot(parts[1]))
                    if parts == ['projects']:
                        return self.reply(dataset.projects.list())
                    if len(parts) == 2 and parts[0] == 'projects':
                        return self.reply(dataset.projects.get(parts[1]))
                    if len(parts) == 4 and parts[0] == 'projects' and parts[2] == 'evidence':
                        return self.reply(dataset.projects.evidence(parts[1], parts[3]))
                    if len(parts) == 4 and parts[0] == 'projects' and parts[2] == 'recipes':
                        query = parse_qs(urlsplit(self.path).query)
                        selected = self._contract_selection
                        version = selected[1] if selected is not None and selected[0] == 'recipes.inspect' else 1
                        self._snapshot_contract_access(parts[1],'recipes.inspect',3)
                        return self.reply(dataset.pipelines.inspect_external_recipe(
                            parts[1], parts[3], query.get('expected_sha256', [''])[-1], contract_version=version))
                    if parts == ['context']:
                        return self.reply({'version': 1, 'mode': 'real', 'dataset_id': dataset.db.dataset_id,
                                           'recipe': 'image_classification_v1', 'execution': 'optional_local_cpu'})
                    if parts == ['definitions']:
                        return self.reply(dataset.pipelines.definitions())
                    if parts == ['releases']:
                        return self.reply(dataset.pipelines.releases())
                    if parts == ['graphs']:
                        return self.reply(dataset.pipelines.list())
                    if len(parts) == 2 and parts[0] == 'graphs':
                        return self.reply(dataset.pipelines.get(parts[1]))
                    if parts == ['run-artifact-inputs']:
                        return self.reply(dataset.runs.input_candidates())
                    if parts == ['runs']:
                        return self.reply(dataset.runs.list())
                    if parts == ['coordinator']:
                        agent_api.require_selection(self._contract_selection, 'runs.coordinator_health')
                        return self.reply(dataset.runs.coordinator_health())
                    if len(parts) == 2 and parts[0] == 'runs':
                        return self.reply(dataset.runs.get(parts[1]))
                    if len(parts) == 3 and parts[0] == 'runs' and parts[2] == 'phase-timings':
                        agent_api.require_selection(self._contract_selection, 'runs.phase_timings')
                        return self.reply(dataset.runs.phase_timings(parts[1]))
                    if len(parts) == 3 and parts[0] == 'runs' and parts[2] == 'publication':
                        agent_api.require_selection(self._contract_selection, 'runs.publication_status')
                        return self.reply(dataset.runs.publication_status(parts[1], contract_version=self._contract_selection[1]))
                    if len(parts) == 3 and parts[0] == 'runs' and parts[2] == 'candidates':
                        agent_api.require_selection(self._contract_selection,'studies.candidates')
                        return self.reply(dataset.studies.candidates(parts[1],**self._model_page_query()))
                    if len(parts) == 3 and parts[0] == 'runs' and parts[2] == 'progress':
                        return self.reply(dataset.runs.external_progress(parts[1]))
                    if len(parts) == 3 and parts[0] == 'runs' and parts[2] == 'predictions':
                        query = parse_qs(urlsplit(self.path).query)
                        return self.reply(dataset.runs.predictions(parts[1], query.get('split', ['validation'])[-1]))
                    if len(parts) == 4 and parts[0] == 'runs' and parts[2] == 'artifacts':
                        with dataset.runs.open_artifact(parts[1], parts[3]) as (stream, metadata):
                            return self.reply_stream(stream, metadata)
                    return self.reply({'error': 'Workspace route not found.', 'code': 'not_found'}, 404)
                if path == '/api/workbench/releases/input-candidates':
                    return self.reply(dataset.releases.input_candidates())
                if path == '/api/workbench/selections':
                    return self.reply(dataset.selections.list())
                if path == '/api/workbench/searches':
                    return self.reply(dataset.searches.list())
                if path.startswith('/api/workbench/searches/'):
                    return self.reply(dataset.searches.get(path.removeprefix('/api/workbench/searches/')))
                if path.startswith('/api/workbench/selections/'):
                    return self.reply(dataset.selections.load(path.removeprefix('/api/workbench/selections/')))
                if path.startswith('/api/workbench/import-result/'):
                    return self.reply(bulk_import.find_result(dataset.workbench, path.rsplit('/', 1)[-1]))
                if path.startswith('/api/workbench/sequence-import-result/'):
                    return self.reply(sequence_batch_import.find_result(dataset.workbench, path.rsplit('/', 1)[-1]))
                if path == '/api/workbench/text-classification-proposals':
                    return self.reply(dataset.text_classification_proposals.snapshot())
                if path.startswith('/api/workbench/text-classification-proposals/'):
                    return self.reply(dataset.text_classification_proposals.get(path.rsplit('/', 1)[-1]))
                if path == '/api/workbench/caption-proposals':
                    return self.reply(dataset.caption_proposals.snapshot())
                if path.startswith('/api/workbench/caption-proposals/'):
                    return self.reply(dataset.caption_proposals.get(path.rsplit('/', 1)[-1]))
                if path == '/api/workbench/grounded/jobs':
                    return self.reply(dataset.grounded.snapshot())
                if path.startswith('/api/workbench/grounded/jobs/'):
                    return self.reply(dataset.grounded.get(path.rsplit('/', 1)[-1]))
                if path == '/api/workbench/records':
                    options = {key: value[-1] for key, value in parse_qs(urlsplit(self.path).query).items()}
                    return self.reply(dataset.workbench.query(options))
                if path == '/api/workbench/recipes':
                    return self.reply(dataset_recipes.RECIPES)
                if path.startswith('/api/workbench/records/'):
                    if path.endswith('/scientific'):
                        options = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                        if set(options) - {'frame', 'field', 'axis', 'index'} or any(len(values) != 1 for values in options.values()):
                            raise workbench.WorkbenchError('Choose one frame, field, axis and slice index.')
                        return self.reply(dataset.workbench.scientific.inspect(path.split('/')[-2],
                            frame=int(options.get('frame', ['0'])[0]), field=options.get('field', [None])[0],
                            axis=options.get('axis', ['z'])[0], index=int(options.get('index', ['0'])[0])))
                    if path.endswith('/preferences'):
                        return self.reply(dataset.workbench.preferences.list(path.split('/')[-2]))
                    if path.endswith('/responses'):
                        return self.reply(dataset.workbench.responses(path.split('/')[-2]))
                    return self.reply(dataset.workbench.get(path.rsplit('/', 1)[-1]))
                if path.startswith('/api/workbench/preference-history/'):
                    return self.reply(dataset.workbench.preferences.history(path.rsplit('/', 1)[-1]))
                if path.startswith('/api/workbench/response-history/'):
                    return self.reply(dataset.workbench.response_history(path.rsplit('/', 1)[-1]))
                if path.startswith('/api/workbench/history/'):
                    return self.reply(dataset.workbench.history(path.rsplit('/', 1)[-1]))
                if path.startswith('/api/workbench/pointcloud-inspection/'):
                    return self.reply(dataset.workbench.pointclouds.inspect(path.rsplit('/', 1)[-1]))
                if path.startswith('/api/workbench/volume-inspection/'):
                    options = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                    if set(options) - {'axis', 'index'} or any(len(values) != 1 for values in options.values()):
                        raise workbench.WorkbenchError('Choose one volume axis and index.')
                    return self.reply(dataset.workbench.volumes.inspect(path.rsplit('/', 1)[-1],
                        axis=options.get('axis', ['z'])[0], index=int(options.get('index', ['0'])[0])))
                if path.startswith('/api/workbench/audio-inspection/'):
                    return self.reply(dataset.workbench.audio.inspect(path.rsplit('/', 1)[-1]))
                if path.startswith('/api/workbench/mesh-release-validation/'):
                    import mesh_release
                    release_id = path.rsplit('/', 1)[-1]
                    archive = dataset.releases.locate(release_id)
                    return self.reply(mesh_release.validate_release(archive, expected_sha256=release_id))
                if path.startswith('/api/workbench/mesh-inspection/'):
                    return self.reply(dataset.workbench.meshes.inspect(path.rsplit('/', 1)[-1]))
                if path.startswith('/api/workbench/asset/'):
                    with dataset.lock:
                        record_id = path.rsplit('/', 1)[-1]
                        dataset.workbench.get(record_id)
                        asset, kind = dataset.workbench.asset(record_id)
                        return self.reply(asset.read_bytes() if isinstance(asset, Path) else asset, content_type=kind)
                if path.startswith('/api/workbench/releases/'):
                    release_id = path.rsplit('/', 1)[-1].removesuffix('.zip')
                    archive = dataset.releases.locate(release_id)
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/zip')
                    self.send_header('Content-Length', str(archive.stat().st_size))
                    self.send_header('Content-Disposition', 'attachment; filename="tuldok-' + release_id[:12] + '.zip"')
                    self.send_header('X-Content-Type-Options', 'nosniff')
                    self.end_headers()
                    with archive.open('rb') as source:
                        shutil.copyfileobj(source, self.wfile)
                    return
                if path == '/api/ai/config':
                    return self.reply(ai.codex_models())
                if path == '/api/generation/jobs':
                    with dataset.lock:
                        snapshot = dict(dataset.generation_jobs.snapshot(), samples=dataset.rows())
                    return self.reply(snapshot)
                if path == '/api/samples':
                    return self.reply(dataset.rows())
                if path.startswith(('/api/image/', '/api/thumb/')):
                    with dataset.lock:
                        sample = dataset.sample(path.rsplit('/', 1)[-1])
                        if not sample:
                            return self.reply({'error': 'Image not found.'}, 404)
                        thumb = path.startswith('/api/thumb/')
                        data = (dataset.path / 'images' / sample['id'] / ('thumb.jpg' if thumb else 'image.png')).read_bytes()
                    return self.reply(data, content_type='image/jpeg' if thumb else 'image/png')
                if path == '/api/export':
                    with dataset.export() as archive:
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/zip')
                        self.send_header('Content-Disposition', 'attachment; filename="tuldok-dataset.zip"')
                        self.send_header('Cache-Control', 'no-store')
                        self.end_headers()
                        shutil.copyfileobj(archive, self.wfile)
                    return
                assets = {'/native-detection-import.js': ('native_detection_import.js', 'text/javascript'), '/saved-searches.js': ('saved-searches.js', 'text/javascript'), '/sequence-batch.js': ('sequence-batch.js', 'text/javascript'), '/pumas-typed.js': ('pumas-typed.js', 'text/javascript'), '/pumas-gateways.js': ('pumas-gateways.js', 'text/javascript'), '/meshes.js': ('meshes.js', 'text/javascript'), '/sequences.js': ('sequences.js', 'text/javascript'), '/text-classification-proposals.js': ('text-classification-proposals.js', 'text/javascript'), '/caption-proposals.js': ('caption-proposals.js', 'text/javascript'), '/curation.js': ('curation.js', 'text/javascript'), '/caption-import.js': ('caption_import.js', 'text/javascript'), '/bulk-import.js': ('bulk_import.js', 'text/javascript'), '/saved-selections.js': ('saved-selections.js', 'text/javascript'), '/workbench': ('workbench.html', 'text/html'), '/workbench.js': ('workbench.js', 'text/javascript'), '/workbench.css': ('workbench.css', 'text/css'), '/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css'), '/rights-note.js': ('rights-note.js', 'text/javascript'), '/preferences.js': ('preferences.js', 'text/javascript'), '/instruction-responses.js': ('instruction-responses.js', 'text/javascript'), '/native-text-import.js': ('native_text_import.js', 'text/javascript')}
                # Opt-in workspace shell keeps fixture and real service boundaries distinct.
                assets.update({
                    '/project-files': ('project-files.html', 'text/html'),
                    '/project-files.js': ('project-files.js', 'text/javascript'),
                    '/project-files.css': ('project-files.css', 'text/css'),
                    '/project-transfer': ('project-transfer.html', 'text/html'),
                    '/project-transfer.js': ('project-transfer.js', 'text/javascript'),
                    '/project-transfer.css': ('project-transfer.css', 'text/css'),
                    '/auth.js': ('auth.js', 'text/javascript'),
                    '/auth.css': ('auth.css', 'text/css'),
                    '/workspace-project-activity.js': ('workspace-project-activity.js', 'text/javascript'),
                    '/workspace-projects.js': ('workspace-projects.js', 'text/javascript'),
                    '/workbench-layout.js': ('workbench-layout.js', 'text/javascript'),
                    '/workbench-layout.css': ('workbench-layout.css', 'text/css'),
                    '/pointclouds.js': ('pointclouds.js', 'text/javascript'),
                    '/volume-editor.js': ('volume-editor.js', 'text/javascript'),
                    '/scientific-fields.js': ('scientific-fields.js', 'text/javascript'),
                    '/audio-editor.js': ('audio-editor.js', 'text/javascript'),
                    '/audio-editor.css': ('audio-editor.css', 'text/css'),
                    '/meshes.css': ('meshes.css', 'text/css'),
                    '/workspaces': ('workspaces.html', 'text/html'),
                    '/workspaces.css': ('workspaces.css', 'text/css'),
                    '/workspaces.js': ('workspaces.js', 'text/javascript'),
                    '/experiment-lineage.js': ('experiment-lineage.js', 'text/javascript'),
                    '/experiment-lineage.css': ('experiment-lineage.css', 'text/css'),
                    '/workspace-real.js': ('workspace-real.js', 'text/javascript'),
                    '/workspace-external.js': ('workspace-external.js', 'text/javascript'),
                    '/workspace-phase-timings.js': ('workspace-phase-timings.js', 'text/javascript'),
                    '/workspace-service.js': ('workspace-service.js', 'text/javascript'),
                    '/static/retained-analysis.js': ('retained-analysis.js', 'text/javascript'),
                    '/static/retained-checkpoint-curve.vl.json': ('retained-checkpoint-curve.vl.json', 'application/json'),
                    '/static/vendor/retained-analysis/vega.min.js': ('vendor/retained-analysis/vega.min.js', 'text/javascript'),
                    '/static/vendor/retained-analysis/vega-lite.min.js': ('vendor/retained-analysis/vega-lite.min.js', 'text/javascript'),
                    '/static/vendor/retained-analysis/vega-embed.min.js': ('vendor/retained-analysis/vega-embed.min.js', 'text/javascript'),
                    '/static/vendor/retained-analysis/vega-interpreter.min.js': ('vendor/retained-analysis/vega-interpreter.min.js', 'text/javascript'),
                    '/workspace-scientific-comparison.js': ('workspace-scientific-comparison.js', 'text/javascript'),
                    '/workspace-fixtures.json': ('workspace-fixtures.json', 'application/json'),
                    '/pipeline-editor.js': ('pipeline-editor.js', 'text/javascript'),
                    '/runs-view.js': ('runs-view.js', 'text/javascript'),
                    '/workspaces-data.js': ('workspaces-data.js', 'text/javascript'),
                    '/workspaces-data.css': ('workspaces-data.css', 'text/css'),
                })
                if getattr(dataset, 'project_files_mode', False) and path in ('/', '/workspaces', '/workbench'):
                    path = '/project-files'
                if path in assets:
                    name, kind = assets[path]
                    return self.reply((ROOT / 'static' / name).read_bytes(), content_type=kind + '; charset=utf-8')
                return self.reply({'error': 'Not found.'}, 404)
            except psycopg.Error:
                return self.reply({'error': 'Local PostgreSQL is unavailable. Restart the service and reopen Tuldok; inspect saved results before retrying writes.', 'code': 'storage'}, 503)
            except CommitOutcomeUnknown as error:
                return self.reply({'error': str(error), 'code': 'commit_unknown'}, 503)
            except CatalogBusy as error:
                return self.reply({'error': str(error), 'code': 'storage'}, 503)
            except access.AccessError as error:
                return self.reply({'error': str(error), 'code': error.code}, error.status)
            except workbench.WorkbenchError as error:
                return self.project_error(error)
            except ProjectStoreError as error:
                return self.project_error(error)
            except (ValueError, OSError) as error:
                return self.reply({'error': str(error)}, 400)

        def _post(self):
            body = {}
            try:
                # Same-origin JSON only; no cross-site form submissions.
                origin = self.headers.get('Origin')
                if origin and urlsplit(origin).netloc != self.headers.get('Host'):
                    return self.reply({'error': 'Cross-origin requests are not accepted.'}, 403)
                if self.headers.get_content_type() != 'application/json':
                    raise ValueError('Send JSON.')
                length = int(self.headers.get('Content-Length', '0'))
                path = urlsplit(self.path).path
                if (path == '/api/workspace/projects' or path.startswith('/api/workspace/projects/')
                        or path == '/api/workspace/project-snapshots' or path.startswith('/api/workspace/project-snapshots/')):
                    self.project_access()
                limit = native_detection_import.MAX_PREPARE_REQUEST if path == '/api/workbench/native-detection-import/prepare' else native_detection_import.MAX_REQUEST if path == '/api/workbench/native-detection-import/row' else saved_searches.MAX_REQUEST if path == '/api/workbench/searches' or path.startswith('/api/workbench/searches/') else meshes.MAX_REQUEST if path == '/api/workbench/mesh-import' else rheon_sequences.MAX_REQUEST if path in ('/api/workbench/sequence-import', '/api/workbench/sequence-import-item') else MAX_BODY
                if path in ('/api/workbench/pointcloud-import', '/api/workbench/volume-import'):
                    limit = spatial_assets.MAX_REQUEST
                if path.startswith('/api/workspace/'):
                    limit = 256 * 1024
                if path == '/api/workspace/project-files' or path.startswith('/api/workspace/project-files/'):
                    limit = agent_api.REQUEST_LIMIT
                if not 0 < length <= limit:
                    raise ValueError('Request is too large or empty.')
                raw_body = self.rfile.read(length)
                observe_request_bytes(observer, getattr(self, '_observation', None), len(raw_body))
                body = projects.decode(raw_body) if (path == '/api/workspace/project-snapshots' or path.startswith('/api/workspace/project-snapshots/') or path == '/api/workspace/projects' or path.startswith('/api/workspace/projects/') or (path.startswith('/api/workspace/runs/') and ('/import-data/' in path or '/artifact-segment/' in path))) else spatial_assets.parse_request(raw_body) if path in ('/api/workbench/pointcloud-import', '/api/workbench/volume-import') else native_detection_import.parse_request(raw_body) if path in ('/api/workbench/native-detection-import/prepare', '/api/workbench/native-detection-import/row') else saved_searches.parse_request(raw_body) if path == '/api/workbench/searches' or path.startswith('/api/workbench/searches/') else sequence_batch_import.parse_request(raw_body) if path in ('/api/workbench/sequence-import', '/api/workbench/sequence-import-item') else meshes.parse_json(raw_body) if path == '/api/workbench/mesh-import' else json.loads(raw_body)
                if getattr(self, '_contract_selection', None) is not None:
                    # Strict JSON at the selected boundary, preserving ordinary HTTP semantics.
                    body = agent_api.decode(raw_body)
                    agent_api.validate_selected(self._contract_selection, self.command, self.path, body)
                elif path == '/api/workspace/project-files' or path.startswith('/api/workspace/project-files/'):
                    body = agent_api.decode(raw_body)
                if not isinstance(body, dict):
                    raise ValueError('Expected an object.')
                self._observe_dispatch(body)
                path = urlsplit(self.path).path
                if path == '/api/workspace/project-files' or path.startswith('/api/workspace/project-files/'):
                    if not getattr(dataset, 'project_files_mode', False):
                        raise workbench.WorkbenchError('Start explicit project-file mode to use this capability.', 'unavailable', 409)
                    from project_workspace import http_arguments
                    name, body = http_arguments('POST', self.path, body)
                    return self.reply(dataset.dispatch(name, body,
                        selected_version=self._contract_selection[1] if self._contract_selection else None))
                if getattr(dataset, 'project_files_mode', False):
                    raise workbench.WorkbenchError('This domain is unavailable until its canonical project publication is implemented.',
                                                  'unavailable', 409)
                if path.startswith('/api/workspace/'):
                    parts = path.removeprefix('/api/workspace/').split('/')
                    if parts == ['scientific-comparison']:
                        agent_api.require_selection(self._contract_selection, 'runs.compare_scientific_evidence')
                        return self.reply(dataset.runs.compare_scientific_evidence(body))
                    if parts == ['artifact-segments']:
                        agent_api.require_selection(self._contract_selection, 'runs.artifact_segments')
                        guards = []
                        value = dataset.runs.artifact_segments(body, _delivery_guard=guards.append)
                        self._artifact_segments_guard = guards[0]
                        return self.reply(value)
                    if parts == ['coordinator', 'recover']:
                        agent_api.require_selection(self._contract_selection, 'runs.recover_coordinator')
                        return self.reply(dataset.runs.recover_coordinator(body))
                    if len(parts) == 3 and parts[0] == 'runs' and parts[2] in ('recover-publication', 'cancel-publication'):
                        operation = 'runs.recover_publication' if parts[2] == 'recover-publication' else 'runs.cancel_publication'
                        agent_api.require_selection(self._contract_selection, operation)
                        action = dataset.runs.recover_publication if parts[2] == 'recover-publication' else dataset.runs.cancel_publication
                        return self.reply(action(dict(body, run_id=parts[1])))
                    if parts == ['publication-results']:
                        agent_api.require_selection(self._contract_selection, 'runs.publication_result')
                        return self.reply(dataset.runs.publication_result(body['ref']))
                    if parts == ['publication-results', 'model-evidence']:
                        agent_api.require_selection(self._contract_selection, 'runs.publication_model_evidence')
                        return self.reply(dataset.runs.publication_model_evidence(body['ref'], body.get('selectors')))
                    if parts == ['publication-results', 'compare-model-evidence']:
                        agent_api.require_selection(self._contract_selection, 'runs.compare_publication_evidence')
                        return self.reply(dataset.runs.compare_publication_evidence(body['ref'], body['other_ref'], body['selection']))
                    if len(parts) == 3 and parts[:2] == ['publication-results', 'artifact-segment']:
                        agent_api.require_selection(self._contract_selection, 'runs.publication_artifact_chunk')
                        return self.reply(dataset.runs.publication_artifact_segment(body['ref'], parts[2],
                            {key: value for key, value in body.items() if key != 'ref'}))
                    if parts == ['models']:
                        agent_api.require_selection(self._contract_selection,'models.create')
                        return self.reply(dataset.models.create(body),201)
                    if parts == ['model-recipes']:
                        agent_api.require_selection(self._contract_selection,'recipes.create')
                        return self.reply(dataset.pipelines.create_recipe(body),201)
                    if len(parts)==2 and parts[0]=='model-recipes':
                        agent_api.require_selection(self._contract_selection,'recipes.save')
                        return self.reply(dataset.pipelines.save_recipe(parts[1],body))
                    if len(parts)==2 and parts[0]=='models':
                        agent_api.require_selection(self._contract_selection,'models.save')
                        return self.reply(dataset.models.save(parts[1],body))
                    if len(parts)==3 and parts[0]=='models' and parts[2]=='publish':
                        agent_api.require_selection(self._contract_selection,'models.publish')
                        def source_guard(source):
                            if source['kind'] == 'captured_source':
                                self._snapshot_contract_access(source['source_selector']['project_id'],
                                                               'models.publish',2,'edit')
                        return self.reply(dataset.models.publish(parts[1],body,_source_guard=source_guard))
                    if parts == ['recipe-material','preflight']:
                        agent_api.require_selection(self._contract_selection,'recipes.preflight_material')
                        projects.closed(body,('ref',))
                        try:
                            return self.reply(dataset.pipelines.preflight_recipe_material(body['ref'],report=True))
                        except workbench.WorkbenchError as error:
                            report=getattr(error,'preflight_report',None)
                            if report is None:raise
                            return self.reply({'error':str(error),'code':error.code,'preflight_report':report},error.status)
                    if parts in (['model-material'],['recipe-material']):
                        model=parts==['model-material'];name='models.material' if model else 'recipes.material'
                        agent_api.require_selection(self._contract_selection,name);projects.closed(body,('ref',))
                        return self.reply(dataset.models.material(body['ref'],verify=True) if model else
                                          dataset.pipelines.recipe_material(body['ref'],verify=True))
                    if parts == ['experiment-lineage']:
                        agent_api.require_selection(self._contract_selection,'studies.record_lineage')
                        return self.reply(dataset.studies.lineage.record(body),201)
                    if parts == ['experiment-lineage','branch']:
                        agent_api.require_selection(self._contract_selection,'studies.branch_trial')
                        return self.reply(dataset.studies.lineage.branch(body),201)
                    if len(parts)==3 and parts[0]=='studies' and parts[2]=='prepare-branch':
                        agent_api.require_selection(self._contract_selection,'studies.prepare_branch')
                        def lineage_graph_guard(graph):
                            self._graph_snapshot_contract_access(graph['id'],graph['revision'],
                                'studies.prepare_branch',1,'edit',graph=graph)
                        return self.reply(dataset.studies.lineage.prepare(parts[1],body,
                                          _graph_guard=lineage_graph_guard),201)
                    if parts == ['studies']:
                        agent_api.require_selection(self._contract_selection,'studies.create')
                        return self.reply(dataset.studies.create(body),201)
                    if len(parts)==2 and parts[0]=='studies':
                        agent_api.require_selection(self._contract_selection,'studies.save')
                        return self.reply(dataset.studies.save(parts[1],body))
                    if len(parts)==3 and parts[0]=='studies':
                        if parts[2] in ('prepare-package','prepare-verifier'):
                            name=parts[2].replace('-','_')
                            agent_api.require_selection(self._contract_selection,'studies.'+name)
                            return self.reply(getattr(dataset.studies,name)(parts[1],body),201)
                        if parts[2]=='select-candidate':
                            agent_api.require_selection(self._contract_selection,'studies.select_candidate')
                            return self.reply(dataset.studies.select_candidate(parts[1],body),201)
                        operation={'prepare-trial':'studies.prepare_trial','continue':'studies.continue',
                                   'approve':'studies.approve',
                                   'admit':'studies.admit','stop':'studies.stop','reconcile':'studies.reconcile'}.get(parts[2])
                        if operation:
                            agent_api.require_selection(self._contract_selection,operation)
                            if parts[2]=='prepare-trial':
                                def graph_guard(graph):
                                    self._graph_snapshot_contract_access(body['graph_id'],body['graph_revision'],
                                        'studies.prepare_trial',2,'edit',graph=graph)
                                return self.reply(dataset.studies.prepare_trial(parts[1],body,_graph_guard=graph_guard),201)
                            if parts[2]=='continue':return self.reply(dataset.studies.continue_study(parts[1],body))
                            if parts[2]=='approve':return self.reply(dataset.studies.approve(parts[1],body),201)
                            if parts[2]=='admit':return self.reply(dataset.studies.admit(parts[1],body,selection=self._contract_selection),201)
                            if parts[2]=='stop':return self.reply(dataset.studies.stop(parts[1],body))
                            projects.closed(body,())
                            return self.reply(dataset.studies.reconcile(parts[1]))
                    if parts == ['project-snapshots']:
                        if self._contract_selection is not None:
                            agent_api.require_selection(self._contract_selection,'project_snapshots.open')
                            result = dataset.projects.register_snapshot(body)
                            if self._contract_selection[1] == 1:
                                result.pop('activity', None)
                            return self.reply(result, 201)
                        return self.reply(dataset.projects.open_snapshot(body), 201)
                    if parts == ['projects']:
                        return self.reply(dataset.projects.open(body), 201)
                    if len(parts) == 4 and parts[0] == 'projects' and parts[2] == 'import-data':
                        projects.closed(body, ('expected_sha256',), ('name', 'rights', 'groups', 'parents'))
                        raw, origin = dataset.projects.read_data_reference(parts[1], parts[3],
                            body['expected_sha256'], projects.DATA_LIMIT)
                        admission = {key: value for key, value in body.items() if key != 'expected_sha256'}
                        return self.reply(dataset.workbench.scientific.admit(raw, admission, origin), 201)
                    if len(parts) == 4 and parts[0] == 'runs' and parts[2] == 'import-data':
                        projects.closed(body, ('expected_sha256',), ('name', 'rights', 'groups', 'parents'))
                        admission = {key: value for key, value in body.items() if key != 'expected_sha256'}
                        return self.reply(dataset.workbench.scientific.admit_run_artifact(
                            parts[1], parts[3], body['expected_sha256'], admission), 201)
                    if len(parts) == 4 and parts[0] == 'runs' and parts[2] == 'artifact-segment':
                        return self.reply(dataset.runs.artifact_segment(parts[1], parts[3], body))
                    if parts == ['graphs']:
                        if body.get('recipe') in tuple(pipeline.MODEL_RECIPES):
                            agent_api.require_selection(self._contract_selection,'graphs.create')
                        return self.reply(dataset.pipelines.create(body), 201)
                    if parts == ['graphs', 'external']:
                        self._snapshot_contract_access(body.get('project_id'),'graphs.create_external',2,'edit')
                        return self.reply(dataset.pipelines.create_external(body), 201)
                    if len(parts) == 2 and parts[0] == 'graphs':
                        if isinstance(body.get('document'),dict) and body['document'].get('recipe') in tuple(pipeline.MODEL_RECIPES):
                            agent_api.require_selection(self._contract_selection,'graphs.save')
                        return self.reply(dataset.pipelines.save(parts[1], body))
                    if len(parts) == 3 and parts[0] == 'graphs':
                        if parts[2] == 'preparation-timings':
                            agent_api.require_selection(self._contract_selection, 'graphs.preparation_timings')
                            projects.closed(body, ('revision',))
                            return self.reply(dataset.pipelines.preparation_timings(parts[1], body['revision']))
                        if parts[2] == 'clone':
                            return self.reply(dataset.pipelines.clone(parts[1], body), 201)
                        if parts[2] == 'validate':
                            projects.closed(body, ('revision',))
                            self._graph_snapshot_contract_access(parts[1],body['revision'],'graphs.validate',2)
                            return self.reply(dataset.pipelines.validate(parts[1], body))
                        if parts[2] == 'preflight-external':
                            projects.closed(body, ('revision',))
                            self._graph_snapshot_contract_access(parts[1],body['revision'],'graphs.preflight_external',2)
                            if self._contract_selection is not None and self._contract_selection[:2] in (
                                    ('graphs.preflight_external', 3), ('graphs.preflight_external', 4)):
                                try:
                                    return self.reply(dataset.pipelines.preflight_external(
                                        parts[1], body['revision'], contract_version=self._contract_selection[1]))
                                except workbench.WorkbenchError as error:
                                    report = getattr(error, 'preflight_report', None)
                                    if report is None:
                                        raise
                                    return self.reply({'error': str(error), 'code': error.code,
                                                       'preflight_report': report}, error.status)
                            return self.reply(dataset.pipelines.preflight_external(parts[1], body['revision']))
                    if parts == ['runs']:
                        return self.reply(dataset.runs.submit(body), 201)
                    if parts == ['runs', 'approve-external']:
                        return self.reply(dataset.runs.approve_external(body), 201)
                    if parts == ['runs', 'submit-external']:
                        def graph_guard(graph):
                            self._graph_snapshot_contract_access(body['graph_id'],body['graph_revision'],
                                'runs.submit_external',2,graph=graph)
                        return self.reply(dataset.runs.submit_external(body,_graph_guard=graph_guard), 201)
                    if (len(parts) == 3 or len(parts) == 4 and parts[3] == 'export') and parts[0] == 'runs' and parts[2] == 'retained-analysis':
                        import retained_analysis
                        operation = 'runs.export_retained_analysis' if len(parts) == 4 else 'runs.retained_analysis'
                        agent_api.require_selection(self._contract_selection, operation)
                        # The selected-contract decoder rejects all duplicate
                        # body Run IDs before this path-owned identity is added.
                        return self.reply(retained_analysis.query(dataset.runs, dict(body, run_id=parts[1]),
                                                                  export=len(parts) == 4))
                    if len(parts) == 3 and parts[0] == 'runs':
                        if parts[2] == 'model-evidence':
                            agent_api.require_selection(self._contract_selection,'runs.model_evidence')
                            return self.reply(dataset.runs.model_evidence(parts[1],body,contract_version=self._contract_selection[1]))
                        if parts[2] == 'compare-model-evidence':
                            agent_api.require_selection(self._contract_selection,'runs.compare_model_evidence')
                            if self._contract_selection[1]==2:
                                choices={key:value for key,value in body.items() if key!='other_run_id'}
                                return self.reply(dataset.runs.compare_model_evidence(parts[1],body['other_run_id'],choices))
                            projects.closed(body,('other_run_id',))
                            return self.reply(dataset.runs.compare_model_evidence(parts[1],body['other_run_id']))
                        if parts[2] == 'cancel':
                            return self.reply(dataset.runs.cancel(parts[1]))
                        if parts[2] == 'retry':
                            return self.reply(dataset.runs.retry(parts[1], body), 201)
                        if parts[2] == 'expose-test':
                            return self.reply(dataset.runs.expose_test(parts[1], body))
                    return self.reply({'error': 'Workspace route not found.', 'code': 'not_found'}, 404)
                if path == '/api/workbench/selections':
                    return self.reply(dataset.selections.create(body), 201)
                if path == '/api/workbench/searches':
                    return self.reply(dataset.searches.create(body), 201)
                if path.startswith('/api/workbench/searches/'):
                    parts = path.removeprefix('/api/workbench/searches/').split('/')
                    if len(parts) != 2:
                        raise workbench.WorkbenchError('Invalid saved search route.')
                    return self.reply(dataset.searches.mutate(parts[0], parts[1], body))
                if path.startswith('/api/workbench/selections/'):
                    parts = path.removeprefix('/api/workbench/selections/').split('/')
                    if len(parts) != 2:
                        raise workbench.WorkbenchError('Invalid saved selection route.')
                    return self.reply(dataset.selections.mutate(parts[0], parts[1], body))
                if path == '/api/workbench/text-classification-proposals':
                    return self.reply(dataset.text_classification_proposals.start(body), 202)
                if path == '/api/workbench/text-classification-proposals/cancel':
                    return self.reply(dataset.text_classification_proposals.cancel(body))
                if path.startswith('/api/workbench/text-classification-proposals/decide/'):
                    return self.reply(dataset.text_classification_proposals.decide(path.rsplit('/', 1)[-1], body))
                if path == '/api/workbench/caption-proposals':
                    return self.reply(dataset.caption_proposals.start(body), 202)
                if path == '/api/workbench/caption-proposals/cancel':
                    return self.reply(dataset.caption_proposals.cancel(body))
                if path.startswith('/api/workbench/caption-proposals/decide/'):
                    return self.reply(dataset.caption_proposals.decide(path.rsplit('/', 1)[-1], body))
                if path == '/api/workbench/grounded/jobs':
                    return self.reply(dataset.grounded.start(body), 202)
                if path == '/api/workbench/grounded/cancel':
                    return self.reply(dataset.grounded.cancel(body.get('job_id')))
                if path.startswith('/api/workbench/grounded/review/'):
                    return self.reply(dataset.grounded.review(path.rsplit('/', 1)[-1], body))
                if path == '/api/workbench/import':
                    return self.reply(dataset.workbench.import_asset(body), 201)
                if path in ('/api/workbench/pointcloud-import', '/api/workbench/volume-import'):
                    kind = 'pointcloud' if path.endswith('/pointcloud-import') else 'volume'
                    return self.reply(spatial_assets.admit(dataset.workbench, kind, body), 201)
                if path == '/api/workbench/audio-import':
                    return self.reply(dataset.workbench.audio.admit(body), 201)
                if path == '/api/workbench/mesh-import':
                    return self.reply(meshes.admit(dataset.workbench, body), 201)
                if path == '/api/workbench/sequence-import':
                    return self.reply(rheon_sequences.admit(dataset.workbench, body), 201)
                if path == '/api/workbench/sequence-import-item':
                    return self.reply(sequence_batch_import.import_item(dataset.workbench, body), 201)
                if path == '/api/workbench/curation':
                    return self.reply(curation.inspect(dataset.workbench, body))
                if path == '/api/workbench/import-row':
                    return self.reply(bulk_import.import_row(dataset.workbench, body), 201)
                if path.startswith('/api/workbench/rights/'):
                    return self.reply(dataset.workbench.correct_rights_note(path.rsplit('/', 1)[-1], body))
                if path == '/api/workbench/native-text-import/prepare':
                    return self.reply(dataset.native_text_imports.prepare(body))
                if path == '/api/workbench/native-text-import/row':
                    return self.reply(dataset.native_text_imports.admit(body), 201)
                if path == '/api/workbench/native-detection-import/prepare':
                    return self.reply(dataset.native_detection_imports.prepare(body))
                if path == '/api/workbench/native-detection-import/row':
                    return self.reply(dataset.native_detection_imports.admit(body), 201)
                if path == '/api/workbench/caption-import/prepare':
                    return self.reply(dataset.caption_imports.prepare(body))
                if path == '/api/workbench/caption-import/row':
                    return self.reply(dataset.caption_imports.admit(body), 201)
                if path.startswith('/api/workbench/records/'):
                    return self.reply(dataset.workbench.save(path.rsplit('/', 1)[-1], body))
                if path == '/api/workbench/preferences':
                    return self.reply(dataset.workbench.preferences.save(body))
                if path == '/api/workbench/preferences/delete':
                    return self.reply(dataset.workbench.preferences.delete(body))
                if path == '/api/workbench/responses':
                    return self.reply(dataset.workbench.save_response(body))
                if path == '/api/workbench/generate':
                    return self.reply(dataset_recipes.generate(dataset.workbench, body), 201)
                if path == '/api/workbench/releases/preview':
                    return self.reply(dataset.releases.preview(body))
                if path == '/api/workbench/releases':
                    return self.reply(dataset.releases.create(body), 201)
                if path == '/api/generation/jobs':
                    return self.reply(dataset.generation_jobs.start(body), 201)
                if path == '/api/generation/jobs/cancel':
                    return self.reply(dataset.generation_jobs.cancel(body.get('job_id')))
                if path == '/api/generation/jobs/resume':
                    return self.reply(dataset.generation_jobs.resume(body.get('job_id')))
                if path in ('/api/generation/prompt-models', '/api/generation/typed-models', '/api/generation/typed-capabilities',
                            '/api/ai/scan', '/api/generation/scan', '/api/generation/advertised-gateways',
                            '/api/generation/inspect-gateway', '/api/generation/models', '/api/ai/models'):
                    dataset.access.require('execute', 'providers.inspect', owner_only=True)
                if path == '/api/generation/prompt-models':
                    return self.reply(ai_http.text_models(body.get('server_url')))
                if path == '/api/generation/typed-models':
                    if set(body) != {'server_url'}: raise ValueError('Supply only the gateway URL.')
                    return self.reply(pumas_operations.models(body['server_url']))
                if path == '/api/generation/typed-capabilities':
                    if set(body) != {'server_url', 'model', 'profile'}: raise ValueError('Supply the exact selected model and optional profile.')
                    return self.reply(pumas_operations.capabilities(body['server_url'], body['model'], body['profile']))
                if path == '/api/ai/scan':
                    return self.reply(gateway_discovery.scan_labeling())
                if path == '/api/generation/scan':
                    return self.reply(gateway_discovery.scan())
                if path == '/api/generation/advertised-gateways':
                    return self.reply(gateway_discovery.scan_advertised())
                if path == '/api/generation/inspect-gateway':
                    return self.reply(gateway_discovery.inspect_advertised(body.get('server_url')))
                if path == '/api/generation/models':
                    return self.reply(image_generation.models(body))
                if path == '/api/generation/cancel':
                    return self.reply(dataset.image_requests.cancel(body.get('request_id')))
                if path == '/api/generation/generate':
                    return self.reply(dataset.image_requests.generate(body, self.connection))
                if path == '/api/ai/models':
                    return self.reply(ai.models(body))
                if path == '/api/ai/suggest':
                    return self.reply(dataset.suggest(body))
                if path == '/api/samples':
                    return self.reply(dataset.add(body), 201)
                if path.startswith('/api/samples/delete/'):
                    return self.reply(dataset.delete(path.rsplit('/', 1)[-1], body))
                if path.startswith('/api/labels/'):
                    return self.reply(dataset.save(path.rsplit('/', 1)[-1], body))
                return self.reply({'error': 'Not found.'}, 404)
            except psycopg.Error:
                return self.reply({'error': 'Local PostgreSQL is unavailable. Restart the service and reopen Tuldok; inspect saved results before retrying writes.', 'code': 'storage'}, 503)
            except CommitOutcomeUnknown as error:
                return self.reply({'error': str(error), 'code': 'commit_unknown'}, 503)
            except CatalogBusy as error:
                return self.reply({'error': str(error), 'code': 'storage'}, 503)
            except access.AccessError as error:
                return self.reply({'error': str(error), 'code': error.code}, error.status)
            except workbench.WorkbenchError as error:
                return self.project_error(error)
            except ProjectStoreError as error:
                return self.project_error(error)
            except Conflict as error:
                return self.reply({'error': str(error)}, 409)
            except FileNotFoundError:
                return self.reply({'error': 'Codex CLI or the selected image was not found. Check the installation and dataset.'}, 400)
            except (ValueError, TypeError, OSError, ai_codex.CodexError) as error:
                return self.reply({'error': ai.safe_error(error, body)}, 400)
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_interface_options(parser)
    parser.add_argument('--data', type=Path, default=ROOT / 'data')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8091)
    parser.add_argument('--project-root', action='append', default=[], metavar='ALIAS=PATH',
                        help='Allow read-only project inspection beneath a local directory; repeat for multiple roots.')
    parser.add_argument('--project-files-root', action='append', default=[], metavar='ALIAS=PATH',
                        help='Use inert external text-project mode beneath explicit local roots; other domain writes are unavailable.')
    parser.add_argument('--project-runtime-source', action='append', default=[], metavar='ALIAS=CONFIG_FILE',
                        help='Allow explicit offline CPU runtime capture from an operator-owned local configuration; never capture on Open.')
    parser.add_argument('--project-transfer-control', type=Path,
                        help='Enable explicit stopped extraction from this existing legacy controller into a separate local authority host.')
    parser.add_argument('--project-transfer-root', action='append', default=[], metavar='ALIAS=PATH',
                        help='Configure backup and destination roots for explicit legacy extraction; requires --project-transfer-control.')
    args = parser.parse_args()
    roots = {}
    for binding in args.project_root:
        alias, separator, location = binding.partition('=')
        if not separator or not location or alias in roots:
            parser.error('Each project root needs a unique ALIAS=PATH.')
        roots[alias] = location
    transfer_controller = control_workspace = None
    try:
        if args.project_files_root:
            if roots or args.project_transfer_control or args.project_transfer_root:
                parser.error('Choose project-file mode or legacy snapshot inspection roots, not both.')
            file_roots = {}
            for binding in args.project_files_root:
                alias, separator, location = binding.partition('=')
                if not separator or not location or alias in file_roots:
                    parser.error('Each project-file root needs a unique ALIAS=PATH.')
                file_roots[alias] = location
            from project_workspace import ProjectWorkspace
            runtime_sources = {}
            from recipe_process import read_regular, decode
            for binding in args.project_runtime_source:
                alias, separator, location = binding.partition('=')
                if not separator or not location or alias in runtime_sources:
                    parser.error('Each runtime source needs a unique ALIAS=CONFIG_FILE.')
                runtime_sources[alias] = decode(read_regular(Path(location).expanduser(), 65536))
            dataset = ProjectWorkspace(args.data, file_roots, runtime_sources=runtime_sources)
        else:
            if args.project_runtime_source:
                parser.error('Project runtime sources require external project-file mode.')
            dataset = Dataset(args.data, project_roots=roots)
            if args.project_transfer_control:
                transfer_roots = {}
                for binding in args.project_transfer_root:
                    alias, separator, location = binding.partition('=')
                    if not separator or not location or alias in transfer_roots:
                        parser.error('Each extraction root needs a unique ALIAS=PATH.')
                    transfer_roots[alias] = location
                from project_workspace import ProjectWorkspace
                from project_transfer_controller import ProjectTransferController
                control_workspace = ProjectWorkspace(args.project_transfer_control, transfer_roots)
                transfer_controller = ProjectTransferController(dataset, control_workspace)
                control_workspace.transfer_controller = transfer_controller
            elif args.project_transfer_root:
                parser.error('Extraction roots require --project-transfer-control.')
    except (StorageError, workbench.WorkbenchError) as error:
        parser.exit(2, str(error) + "\n")
    observer = configured_interface(args, 'http')
    server = ThreadingHTTPServer((args.host, args.port), make_handler(dataset, observer,
                                                                  transfer_controller=transfer_controller))
    print('Tuldok: http://' + args.host + ':' + str(server.server_port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if transfer_controller is not None:
            transfer_controller.close()
        if control_workspace is not None:
            control_workspace.close()
        dataset.close()
        if observer is not None:
            observe_close(observer)


if __name__ == '__main__':
    main()
