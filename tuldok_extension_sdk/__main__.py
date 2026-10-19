"""Private authoring kit: inert validation or explicitly granted public-CLI conformance."""
import argparse
import json

from .manifest import ExtensionError, validate


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    validation = commands.add_parser('validate', help='Read one inert package under an explicit local root.')
    validation.add_argument('root')
    validation.add_argument('--manifest', default='extension.json', help='Project-root-relative manifest path.')
    conformance = commands.add_parser('conformance', help='Admit one exact externally granted trial through a selected trusted public CLI.')
    for option in ('config', 'cli', 'cli-sha256', 'selection', 'output'):
        conformance.add_argument('--' + option, required=True)
    conformance.add_argument('--deadline-seconds', type=int, default=180)
    collection = commands.add_parser('collect-publication', help='Collect one exact recovered result through a selected trusted public CLI; never execute.')
    for option in ('config', 'cli', 'cli-sha256', 'ref', 'output'):
        collection.add_argument('--' + option, required=True)
    collection.add_argument('--deadline-seconds', type=int, default=180)
    args = parser.parse_args(argv)
    if args.command == 'conformance':
        return conformance_main(args)
    if args.command == 'collect-publication':
        return publication_main(args)
    try:
        result = validate(args.root, args.manifest)
    except ExtensionError as error:
        print(json.dumps({'state':error.state, 'error':str(error), 'execution':'unsupported'}))
        return 2
    print(json.dumps(result, ensure_ascii=True, allow_nan=False))
    # This exit status describes static declaration validation only. Runtime,
    # permission and host support remain separate facets in the output.
    return int(any(package['state'] != 'valid' or any(entry['state'] != 'valid'
        for entry in package['contributions']) for package in result['packages']))





def _selection(raw):
    """Select existing identities only. This is launcher input, not grant authority."""
    from .evidence import closed, decode, identifier, natural, require, sha
    import re
    value = decode(raw, 65536)
    closed(value, ('format', 'catalog_id', 'actor_id', 'project_id', 'study_id', 'trial_id', 'revision', 'admission_epoch', 'approval_id', 'request_key', 'expected'), 'Conformance selection')
    require(value['format'] == 'extension_sdk_conformance_selection_v1', 'Unsupported conformance selection.', 'unsupported')
    for key in ('catalog_id', 'actor_id', 'project_id', 'study_id', 'trial_id', 'approval_id'):
        identifier(value[key])
    natural(value['revision'], 'Study revision', 1); natural(value['admission_epoch'], 'Admission epoch')
    require(type(value['request_key']) is str and re.fullmatch('[A-Za-z0-9_.:-]{8,128}', value['request_key']), 'Select an explicit stable request key.')
    expected = value['expected']
    closed(expected, ('graph_id', 'graph_revision', 'material_sha256', 'model_sha256', 'runtime_sha256', 'task_sha256', 'profile_definition_sha256'), 'Expected identities')
    identifier(expected['graph_id']); natural(expected['graph_revision'], 'Graph revision', 1)
    for key in ('material_sha256', 'model_sha256', 'runtime_sha256', 'task_sha256', 'profile_definition_sha256'):
        sha(expected[key])
    return value


class _CLI:
    """Fixed public CLI calls. It imports no AgentClient/application into the SDK."""
    def __init__(self, args):
        import fcntl
        import hashlib
        import os
        from pathlib import Path
        import time
        from .evidence import EvidenceError, read_regular, require, sha
        self.args = args; self.calls = []; self.run_id = None; self.admission = False; self.entry_fd = None
        require(type(args.deadline_seconds) is int and 1 <= args.deadline_seconds <= 3600, 'Select a 1..3600 second command budget.')
        self.deadline = time.monotonic() + args.deadline_seconds
        self.cli = Path(args.cli).absolute(); self.config = Path(args.config).absolute()
        sha(args.cli_sha256)
        source = read_regular(self.cli, 1024**2)
        require(hashlib.sha256(source).hexdigest() == args.cli_sha256, 'Selected trusted CLI source hash differs.', 'stale')
        read_regular(self.config, 65536)  # AgentClient owns its private config/token schema.
        require(hasattr(os, 'memfd_create'), 'Sealed trusted-CLI execution requires Linux.', 'unsupported')
        descriptor = os.memfd_create('tuldok-sdk-trusted-cli', os.MFD_ALLOW_SEALING | os.MFD_CLOEXEC)
        try:
            with os.fdopen(os.dup(descriptor), 'wb') as stream:
                stream.write(source); stream.flush()
            # Linux UAPI F_ADD_SEALS/F_GET_SEALS and WRITE|GROW|SHRINK|SEAL.
            # Some CPython builds expose fcntl() without these symbolic names.
            fcntl.fcntl(descriptor, 1033, 0x000f)
            require(fcntl.fcntl(descriptor, 1034) & 0x000f == 0x000f, 'Trusted CLI snapshot cannot be sealed.', 'unsupported')
        except BaseException:
            os.close(descriptor)
            raise
        self.entry_fd = descriptor

    def close(self):
        import os
        if self.entry_fd is not None:
            os.close(self.entry_fd); self.entry_fd = None

    def _run(self, arguments, *, mutation=False):
        import os
        import selectors
        import subprocess
        import sys
        import time
        from .evidence import EvidenceError, decode, require
        remaining = self.deadline-time.monotonic()
        require(remaining > 0, 'Conformance deadline elapsed; inspect durable state.', 'unknown')
        # The entry bytes are sealed, not reopened through the selected path.
        # The explicitly trusted CLI installation still owns its import closure.
        bootstrap = "import os,sys;fd=int(sys.argv[1]);root=sys.argv[2];source=sys.argv[3];args=sys.argv[4:];raw=os.fdopen(fd,'rb').read(1048577);sys.path.insert(0,root);sys.argv=[source]+args;exec(compile(raw,source,'exec'),{'__name__':'__main__','__file__':source})"
        os.lseek(self.entry_fd, 0, os.SEEK_SET)
        argv = [sys.executable, '-I', '-B', '-c', bootstrap, str(self.entry_fd), str(self.cli.parent), str(self.cli), '--config', str(self.config), *arguments]
        process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, pass_fds=(self.entry_fd,))
        streams = selectors.DefaultSelector(); output = {'stdout': bytearray(), 'stderr': bytearray()}
        bounds = {'stdout': 8*1024**2, 'stderr': 65536}
        try:
            for label, pipe in (('stdout', process.stdout), ('stderr', process.stderr)):
                os.set_blocking(pipe.fileno(), False); streams.register(pipe, selectors.EVENT_READ, label)
            while streams.get_map():
                remaining = self.deadline-time.monotonic()
                require(remaining > 0, 'Selected CLI did not return; inspect durable state before any explicit retry.', 'unknown' if mutation or self.admission else 'unavailable')
                for key, _mask in streams.select(remaining):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        streams.unregister(key.fileobj); continue
                    label = key.data
                    require(len(output[label])+len(chunk) <= bounds[label], 'Selected CLI exceeded its result bound.', 'unknown' if mutation or self.admission else 'unavailable')
                    output[label].extend(chunk)
            try:
                process.wait(timeout=max(.001, self.deadline-time.monotonic()))
            except subprocess.TimeoutExpired:
                raise EvidenceError('Selected CLI did not terminate; inspect durable state.', 'unknown' if mutation or self.admission else 'unavailable') from None
        except KeyboardInterrupt:
            raise EvidenceError('Conformance interrupted; inspect durable state before retrying.', 'unknown' if mutation or self.admission else 'unavailable') from None
        finally:
            streams.close()
            if process.poll() is None:
                process.kill()
            process.wait(); process.stdout.close(); process.stderr.close()
        raw, diagnostic = bytes(output['stdout']), bytes(output['stderr'])
        if process.returncode:
            try:
                error = decode(diagnostic, 65536)
            except EvidenceError:
                raise EvidenceError('Selected CLI refused without a valid bounded diagnostic.', 'unknown' if mutation else 'unavailable') from None
            status = error.get('status') if type(error) is dict else None
            definite = type(status) is int and 400 <= status < 500
            reason = error.get('code', 'cli_refused') if type(error) is dict else 'cli_refused'
            require(type(reason) is str and len(reason) <= 80, 'Invalid CLI diagnostic.')
            raise EvidenceError('Selected public CLI refused: ' + reason + '.', 'refused' if definite else 'unknown' if mutation else 'unavailable')
        return decode(raw)

    def call(self, operation, arguments):
        import tempfile
        from pathlib import Path
        from .evidence import canonical, require
        require(operation in ('identity.get', 'studies.get', 'studies.trial', 'recipes.material', 'models.material', 'graphs.get', 'studies.admit', 'runs.get', 'runs.model_evidence', 'runs.publication_result'), 'Unsupported conformance operation.', 'unsupported')
        self.calls.append(operation)
        with tempfile.TemporaryDirectory(prefix='tuldok-sdk-call-') as temporary:
            path = Path(temporary)/'arguments.json'; path.write_bytes(canonical(arguments)); path.chmod(0o600)
            return self._run(['call', '--operation', operation, '--arguments', str(path)], mutation=operation == 'studies.admit')

    def download(self, run_id, item, destination):
        from .evidence import name, sha, natural
        name(item['name']); sha(item['sha256']); natural(item['bytes'], 'Artifact bytes', 1, 8*1024**2)
        self.calls.append('runs.artifact_chunk')
        return self._run(['download', '--run-id', run_id, '--name', item['name'], '--expected-sha256', item['sha256'], '--out', str(destination)])

    def download_publication(self, ref, item, destination):
        import tempfile
        from pathlib import Path
        from .evidence import canonical, name, sha, natural
        from .publication import result_reference
        result_reference(ref); name(item['name']); sha(item['sha256'])
        natural(item['bytes'], 'Artifact bytes', 0, 512*1024**2)
        self.calls.append('runs.publication_artifact_chunk')
        with tempfile.TemporaryDirectory(prefix='tuldok-sdk-publication-') as temporary:
            path = Path(temporary) / 'result-ref.json'; path.write_bytes(canonical(ref)); path.chmod(0o600)
            return self._run(['download-publication', '--ref', str(path), '--name', item['name'],
                '--expected-sha256', item['sha256'], '--out', str(destination)])


def _external_graph_selector(graph):
    """Read the public external graph wire shape without application imports."""
    import re
    from .evidence import canonical, closed, identifier, natural, require, sha
    required = {'schema_version', 'mode', 'id', 'revision', 'name', 'recipe', 'recipe_version', 'nodes', 'edges'}
    require(type(graph) is dict and required <= set(graph) <= required | {'layout'}, 'External graph fields differ.')
    require(graph['mode'] == 'real' and graph['recipe'] == 'external_recipe', 'Conformance requires a real external recipe graph.', 'unsupported')
    for key in ('schema_version', 'recipe_version'):
        natural(graph[key], key, 1, 1)
    nodes = graph['nodes']
    require(type(nodes) is list and len(nodes) == 3, 'External graph requires three unambiguous nodes.')
    typed = {}; identifiers = set()
    for node in nodes:
        closed(node, ('id', 'type', 'definition_version', 'parameters'), 'External node')
        require(type(node['id']) is str and re.fullmatch('[A-Za-z][A-Za-z0-9_-]{0,39}', node['id'])
                and node['id'] not in identifiers, 'External node IDs must be valid and unique.')
        require(type(node['type']) is str and node['type'] in ('input', 'execute', 'output')
                and node['type'] not in typed, 'External node roles must be unambiguous.')
        natural(node['definition_version'], 'External node version', 1, 1)
        require(type(node['parameters']) is dict, 'External node parameters must be an object.')
        identifiers.add(node['id']); typed[node['type']] = node
    edges = graph['edges']
    expected = [{'from': typed['input']['id'], 'output': 'data', 'to': typed['execute']['id'], 'input': 'data'},
                {'from': typed['execute']['id'], 'output': 'artifacts', 'to': typed['output']['id'], 'input': 'artifacts'}]
    require(type(edges) is list and len(edges) == 2 and
            sorted(canonical(edge) for edge in edges) == sorted(canonical(edge) for edge in expected)
            and typed['output']['parameters'] == {}, 'External graph connections or output parameters differ.')
    selector = typed['input']['parameters']
    closed(selector, ('project_id', 'recipe_id', 'expected_sha256', 'inputs'), 'External input selector')
    identifier(selector['project_id']); sha(selector['expected_sha256'])
    require(type(selector['recipe_id']) is str and 1 <= len(selector['recipe_id']) <= 64
            and type(selector['inputs']) is dict, 'External source selector differs.')
    return {key: selector[key] for key in ('project_id', 'recipe_id', 'expected_sha256')}


def _conformance(selection, client, output):
    """One admission and read-only observation; no creation/approval/retry owner."""
    import hashlib
    import time
    from .evidence import canonical, identifier, load_context, name, natural, read_regular, require, sha, validate_projection
    expected = selection['expected']
    same = lambda left, right: canonical(left) == canonical(right)
    identity = client.call('identity.get', {})
    require(identity.get('kind') == 'agent' and identity.get('catalog_id') == selection['catalog_id'] and identity.get('actor_id') == selection['actor_id'], 'Configured current actor/catalog differs.', 'refused')
    require(type(identity.get('scopes')) is list and {'inspect', 'execute'} <= set(identity['scopes']), 'Current inspect and execute scopes are required.', 'refused')
    study = client.call('studies.get', {'study_id': selection['study_id']})['study']
    require(study['id'] == selection['study_id'] and same(study['revision'], selection['revision']) and same(study['admission_epoch'], selection['admission_epoch']) and study['open'] is True and study['state'] == 'open', 'Study revision/epoch is stale or not already open.', 'stale')
    trial = client.call('studies.trial', {'trial_id': selection['trial_id']})
    require(trial['id'] == selection['trial_id'] and trial['study_id'] == study['id'] and trial['id'] in study['trial_ids'], 'Trial membership differs.', 'stale')
    ref = trial['material']
    require(ref['kind'] == 'recipe_material' and ref['catalog_id'] == selection['catalog_id'] and ref['id'] == ref['sha256'] == expected['material_sha256'], 'Trial composition differs.', 'stale')
    retained = client.call('recipes.material', {'ref': ref}); material = retained['material']
    require(same(retained['ref'], ref) and hashlib.sha256(canonical(material)).hexdigest() == ref['sha256'] and material['catalog_id'] == selection['catalog_id'], 'Published composition identity differs.', 'stale')
    require(material['recipe_id'] == expected['graph_id'] and same(material['recipe_revision'], expected['graph_revision']) and material['model']['sha256'] == expected['model_sha256'] and material['runtime']['sha256'] == expected['runtime_sha256'] and material['evaluation_profile']['sha256'] == expected['profile_definition_sha256'], 'Expected graph/model/runtime/profile differs.', 'stale')
    require(material['trainer']['id'] == 'external_model_evidence_recipe_v1', 'Conformance selects only the existing explicit external evidence recipe.', 'unsupported')
    model = client.call('models.material', {'ref': material['model']})
    require(same(model['ref'], material['model']) and model['material']['task']['sha256'] == expected['task_sha256'], 'Expected Task differs.', 'stale')
    graph = client.call('graphs.get', {'graph_id': expected['graph_id']})
    require(type(graph) is dict and graph.get('id') == expected['graph_id'] and same(graph.get('revision'), expected['graph_revision']), 'Expected current graph identity/revision differs.', 'stale')
    selector = _external_graph_selector(graph)
    require(selector['project_id'] == selection['project_id'] and model['material'].get('kind') == 'captured_source'
            and same(selector, model['material'].get('source_selector')), 'Expected project/captured recipe selector differs.', 'stale')
    body = {key: selection[key] for key in ('study_id', 'trial_id', 'revision', 'admission_epoch', 'approval_id', 'request_key')}
    client.admission = True
    admitted = client.call('studies.admit', body)
    reservation, run = admitted['reservation'], admitted['run']
    run_id = identifier(run['id']); client.run_id = run_id
    for key in ('study_id', 'trial_id', 'admission_epoch', 'actor_id', 'request_key'):
        require(same(reservation[key], selection[key]), 'Admission receipt differs from explicit selection.', 'unknown')
    require(reservation['run_id'] == run_id and reservation['material_sha256'] == expected['material_sha256'], 'Admission receipt material/Run differs.', 'unknown')
    def run_identity(value):
        require(value['id'] == run_id and value['dataset_id'] == selection['catalog_id'] and value['actor_id'] == selection['actor_id']
            and value['approval_id'] == selection['approval_id'] and value['approval_material_sha256'] == expected['material_sha256']
            and value['material_sha256'] == material['executable_sha256'] and same(value['study_membership'], {'study_id': selection['study_id'], 'trial_id': selection['trial_id']}), 'Run differs from selected admission.', 'unknown')
    run_identity(run)
    while run['state'] in ('queued', 'running', 'cancelling'):
        require(time.monotonic() < client.deadline, 'Conformance deadline elapsed; Run may still be active.', 'unknown')
        time.sleep(min(.2, max(0, client.deadline-time.monotonic())))
        run = client.call('runs.get', {'run_id': run_id}); run_identity(run)
    require(run['state'] == 'completed', 'Run did not complete; no successful contract result.', 'unknown' if run['state'] == 'unknown' else 'failed')
    projection = client.call('runs.model_evidence', {'run_id': run_id})
    require(projection.get('state') == 'verified', 'Run has no verified current evidence.', 'unavailable')
    artifacts = run['artifacts']; require(type(artifacts) is list and 1 <= len(artifacts) <= 128, 'Published output inventory is missing or excessive.')
    for item in artifacts:
        require(type(item) is dict, 'Invalid published artifact.')
        name(item['name']); sha(item['sha256']); natural(item['bytes'], 'Artifact bytes', 1, 8*1024**2)
    require(len({item['name'] for item in artifacts}) == len(artifacts) and sum(item['bytes'] for item in artifacts) <= 64*1024**2, 'Published output inventory duplicates or exceeds the conformance bound.')
    blobs = {}
    for item in artifacts:
        require(item.get('locked') is False, 'Protected output is unavailable to conformance.', 'refused')
        destination = output/item['name']
        client.download(run_id, item, destination)
        raw = read_regular(destination, 8*1024**2)
        require(len(raw) == item['bytes'] and hashlib.sha256(raw).hexdigest() == item['sha256'], 'Whole artifact identity differs.')
        blobs[item['name']] = raw
    context_raw = blobs.get('execution-context.json'); context = load_context(context_raw)
    require(context['run_id'] == run_id and context['request_sha256'] == reservation['request_sha256'] and context['composition']['sha256'] == expected['material_sha256']
        and context['static']['execution_material_sha256'] == material['executable_sha256'] and context['static']['catalog_id'] == selection['catalog_id']
        and context['static']['model']['sha256'] == expected['model_sha256'] and context['static']['task']['sha256'] == expected['task_sha256']
        and context['static']['profile']['definition']['sha256'] == expected['profile_definition_sha256'], 'Retained context differs from selected Run/material.')
    contract = validate_projection(projection, context_raw, blobs)
    return dict(format='extension_sdk_conformance_v1', state='passed', contract=contract, numerical='not_evaluated',
        run_id=run_id, study_id=selection['study_id'], trial_id=selection['trial_id'], request_key=selection['request_key'],
        material_sha256=expected['material_sha256'], artifacts=[{key:item[key] for key in ('name', 'bytes', 'sha256')} for item in artifacts],
        operations=client.calls, scope='actual_authorized_run_and_public_identity_blob_contract; numerical_acceptance_is_separate')


def publication_main(args):
    from .evidence import EvidenceError, decode, read_regular
    from .publication import collect, result_reference
    client = None
    try:
        ref = result_reference(decode(read_regular(args.ref, 65536), 65536))
        client = _CLI(args)
        result = collect(client, ref, args.output)
    except (EvidenceError, OSError, ImportError, KeyError, TypeError, ValueError, KeyboardInterrupt) as error:
        result = {'format': 'extension_sdk_publication_collection_v1', 'state': error.state if isinstance(error, EvidenceError) else 'unavailable',
                  'error': str(error) if isinstance(error, EvidenceError) else 'Publication collection is unavailable.',
                  'numerical': 'not_evaluated'}
        print(json.dumps(result, ensure_ascii=True, allow_nan=False)); return 2
    finally:
        if client is not None: client.close()
    print(json.dumps(result, ensure_ascii=True, allow_nan=False)); return 0


def conformance_main(args):
    from pathlib import Path
    from .evidence import EvidenceError, read_regular, require
    client = None; selection = None
    try:
        selection = _selection(read_regular(args.selection, 65536))
        client = _CLI(args)
        output = Path(args.output).absolute()
        require(not output.exists() and not output.is_symlink(), 'Choose an absent conformance output directory.')
        output.mkdir(mode=0o700)
        result = _conformance(selection, client, output)
    except (EvidenceError, OSError, ImportError, KeyError, TypeError, ValueError, OverflowError, KeyboardInterrupt) as error:
        state = error.state if isinstance(error, EvidenceError) else 'unavailable'
        if client is not None and client.admission and client.run_id is None and state not in ('refused', 'stale', 'unsupported'):
            state = 'unknown'
        if isinstance(error, KeyboardInterrupt):
            state = 'unknown' if client is not None and client.admission else 'unavailable'
        result = dict(format='extension_sdk_conformance_v1', state=state, contract={'state':'not_evaluated'}, numerical='not_evaluated',
            error=str(error) if isinstance(error, EvidenceError) else 'Required CLI/configuration/projection is unavailable or malformed.')
        if selection is not None:
            result.update(study_id=selection['study_id'], trial_id=selection['trial_id'], request_key=selection['request_key'])
        if client is not None and client.run_id is not None:
            result['run_id'] = client.run_id
        print(json.dumps(result, ensure_ascii=True, allow_nan=False))
        return 2
    finally:
        if client is not None:
            client.close()
    print(json.dumps(result, ensure_ascii=True, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
