def make_handler(dataset):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, data, status=200, content_type='application/json', headers=()):
            if content_type == 'application/json' and not isinstance(data, bytes):
                data = json.dumps(data).encode()
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            for key, value in headers:
                self.send_header(key, value)
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def reply_stream(self, stream, metadata):
            # The owner has already verified a private spool before HTTP success.
            self.send_response(200)
            self.send_header('Content-Type', metadata['media_type'])
            self.send_header('Content-Length', str(metadata['bytes']))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            try:
                while True:
                    raw = stream.read(65536)
                    if not raw:
                        break
                    self.wfile.write(raw)
            except (OSError, ConnectionError):
                # Headers are committed; never append a JSON error to payload.
                self.close_connection = True

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
                body = projects.decode(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError()
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

        def do_GET(self):
            try:
                if not urlsplit(self.path).path.startswith('/api/'):
                    return self._get()
                token, _bearer = self._credential()
                with dataset.access.bind(token):
                    dataset.access.require('inspect', 'http.inspect')
                    try:
                        self._same_origin(False)
                    except access.AccessError as error:
                        dataset.access.denial(error, 'http.get', urlsplit(self.path).path[:512])
                        raise
                    if urlsplit(self.path).path == '/api/access/session':
                        return self.reply(dataset.access.identity())
                    return self._get()
            except access.AccessError as error:
                return self._access_error(error)
            except CommitOutcomeUnknown:
                return self.reply({'error': 'Commit outcome is unknown; inspect state before retrying.', 'code': 'commit_unknown'}, 503)
            except psycopg.Error:
                return self.reply({'error': 'Metadata storage is unavailable.', 'code': 'storage'}, 503)

        def do_POST(self):
            try:
                path = urlsplit(self.path).path
                if path == '/api/access/session':
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
                    if path == '/api/access/logout':
                        self._access_body()
                        dataset.access.logout()
                        return self.reply({'signed_out': True}, headers=[('Set-Cookie', 'tuldok_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')])
                    if path == '/api/access/credentials':
                        return self.reply(dataset.access.issue(self._access_body()), 201)
                    if path.startswith('/api/access/credentials/') and path.endswith('/revoke'):
                        self._access_body()
                        return self.reply(dataset.access.revoke(path.split('/')[-2]))
                    if path.startswith('/api/access/execution-grants/') and path.endswith('/revoke'):
                        projects.closed(self._access_body(), ())
                        return self.reply(dataset.access.revoke_execution(path.split('/')[-2]))
                    return self._post()
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
                if path == '/api/workspace/projects' or path.startswith('/api/workspace/projects/'):
                    self.project_access()
                if path.startswith('/api/workspace/'):
                    parts = path.removeprefix('/api/workspace/').split('/')
                    if parts == ['projects']:
                        return self.reply(dataset.projects.list())
                    if len(parts) == 2 and parts[0] == 'projects':
                        return self.reply(dataset.projects.get(parts[1]))
                    if len(parts) == 4 and parts[0] == 'projects' and parts[2] == 'evidence':
                        return self.reply(dataset.projects.evidence(parts[1], parts[3]))
                    if len(parts) == 4 and parts[0] == 'projects' and parts[2] == 'recipes':
                        query = parse_qs(urlsplit(self.path).query)
                        return self.reply(dataset.pipelines.inspect_external_recipe(parts[1], parts[3], query.get('expected_sha256', [''])[-1]))
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
                    if len(parts) == 2 and parts[0] == 'runs':
                        return self.reply(dataset.runs.get(parts[1]))
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
                    '/auth.js': ('auth.js', 'text/javascript'),
                    '/auth.css': ('auth.css', 'text/css'),
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
                    '/workspace-real.js': ('workspace-real.js', 'text/javascript'),
                    '/workspace-external.js': ('workspace-external.js', 'text/javascript'),
                    '/workspace-service.js': ('workspace-service.js', 'text/javascript'),
                    '/workspace-fixtures.json': ('workspace-fixtures.json', 'application/json'),
                    '/pipeline-editor.js': ('pipeline-editor.js', 'text/javascript'),
                    '/runs-view.js': ('runs-view.js', 'text/javascript'),
                    '/workspaces-data.js': ('workspaces-data.js', 'text/javascript'),
                    '/workspaces-data.css': ('workspaces-data.css', 'text/css'),
                })
                if path in assets:
                    name, kind = assets[path]
                    return self.reply((ROOT / 'static' / name).read_bytes(), content_type=kind + '; charset=utf-8')
                return self.reply({'error': 'Not found.'}, 404)
            except psycopg.Error:
                return self.reply({'error': 'Local PostgreSQL is unavailable. Restart the service and reopen Tuldok; inspect saved results before retrying writes.', 'code': 'storage'}, 503)
            except CommitOutcomeUnknown as error:
                return self.reply({'error': str(error), 'code': 'commit_unknown'}, 503)
            except access.AccessError as error:
                return self.reply({'error': str(error), 'code': error.code}, error.status)
            except workbench.WorkbenchError as error:
                return self.reply({'error': str(error), 'code': error.code}, error.status)
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
                if path == '/api/workspace/projects' or path.startswith('/api/workspace/projects/'):
                    self.project_access()
                limit = native_detection_import.MAX_PREPARE_REQUEST if path == '/api/workbench/native-detection-import/prepare' else native_detection_import.MAX_REQUEST if path == '/api/workbench/native-detection-import/row' else saved_searches.MAX_REQUEST if path == '/api/workbench/searches' or path.startswith('/api/workbench/searches/') else meshes.MAX_REQUEST if path == '/api/workbench/mesh-import' else rheon_sequences.MAX_REQUEST if path in ('/api/workbench/sequence-import', '/api/workbench/sequence-import-item') else MAX_BODY
                if path in ('/api/workbench/pointcloud-import', '/api/workbench/volume-import'):
                    limit = spatial_assets.MAX_REQUEST
                if path.startswith('/api/workspace/'):
                    limit = 256 * 1024
                if not 0 < length <= limit:
                    raise ValueError('Request is too large or empty.')
                raw_body = self.rfile.read(length)
                body = projects.decode(raw_body) if (path == '/api/workspace/projects' or path.startswith('/api/workspace/projects/') or (path.startswith('/api/workspace/runs/') and ('/import-data/' in path or '/artifact-segment/' in path))) else spatial_assets.parse_request(raw_body) if path in ('/api/workbench/pointcloud-import', '/api/workbench/volume-import') else native_detection_import.parse_request(raw_body) if path in ('/api/workbench/native-detection-import/prepare', '/api/workbench/native-detection-import/row') else saved_searches.parse_request(raw_body) if path == '/api/workbench/searches' or path.startswith('/api/workbench/searches/') else sequence_batch_import.parse_request(raw_body) if path in ('/api/workbench/sequence-import', '/api/workbench/sequence-import-item') else meshes.parse_json(raw_body) if path == '/api/workbench/mesh-import' else json.loads(raw_body)
                if not isinstance(body, dict):
                    raise ValueError('Expected an object.')
                path = urlsplit(self.path).path
                if path.startswith('/api/workspace/'):
                    parts = path.removeprefix('/api/workspace/').split('/')
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
                        return self.reply(dataset.pipelines.create(body), 201)
                    if parts == ['graphs', 'external']:
                        return self.reply(dataset.pipelines.create_external(body), 201)
                    if len(parts) == 2 and parts[0] == 'graphs':
                        return self.reply(dataset.pipelines.save(parts[1], body))
                    if len(parts) == 3 and parts[0] == 'graphs':
                        if parts[2] == 'clone':
                            return self.reply(dataset.pipelines.clone(parts[1], body), 201)
                        if parts[2] == 'validate':
                            return self.reply(dataset.pipelines.validate(parts[1], body))
                        if parts[2] == 'preflight-external':
                            projects.closed(body, ('revision',))
                            return self.reply(dataset.pipelines.preflight_external(parts[1], body['revision']))
                    if parts == ['runs']:
                        return self.reply(dataset.runs.submit(body), 201)
                    if parts == ['runs', 'approve-external']:
                        return self.reply(dataset.runs.approve_external(body), 201)
                    if parts == ['runs', 'submit-external']:
                        return self.reply(dataset.runs.submit_external(body), 201)
                    if len(parts) == 3 and parts[0] == 'runs':
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
            except access.AccessError as error:
                return self.reply({'error': str(error), 'code': error.code}, error.status)
            except workbench.WorkbenchError as error:
                return self.reply({'error': str(error), 'code': error.code}, error.status)
            except Conflict as error:
                return self.reply({'error': str(error)}, 409)
            except FileNotFoundError:
                return self.reply({'error': 'Codex CLI or the selected image was not found. Check the installation and dataset.'}, 400)
            except (ValueError, TypeError, OSError, ai_codex.CodexError) as error:
                return self.reply({'error': ai.safe_error(error, body)}, 400)
    return Handler
