"""Explicit project execution through the existing authenticated agent client.

Models and training adapters stay in the opened project. This CLI owns no
catalog, approvals, scheduler, model deserializer or competing Run state.
"""
import argparse
import json
import os
from pathlib import Path
import stat
import sys
import tempfile

from agent_api import AgentAPIError, AgentClient, REQUEST_LIMIT, decode, validate_arguments, verify_artifact
from mcp_observer import (add_interface_options, configured_interface, observe_begin,
                          observe_stage, observe_selection, observe_close, outcome)


def read_arguments(path):
    """Read bounded regular JSON; operation schemas remain agent_api-owned."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > REQUEST_LIMIT:
            raise AgentAPIError('Arguments must be a regular JSON file within 1 MiB.')
        raw = os.read(fd, REQUEST_LIMIT + 1)
        after = os.fstat(fd)
        if (len(raw) != before.st_size or
                (before.st_size, before.st_mtime_ns, before.st_ctime_ns) !=
                (after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
            raise AgentAPIError('Arguments changed while reading.', 'conflict', 409)
        return decode(raw)
    finally:
        os.close(fd)


def download(client, run_id, name, expected_sha256, destination):
    """Publish verified bytes exclusively; provisional bytes never replace work."""
    destination = Path(destination)
    if os.path.lexists(destination):
        raise AgentAPIError('Destination already exists; choose a new file.', 'conflict', 409)
    fd, provisional = tempfile.mkstemp(prefix='.tuldok-download-', dir=destination.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            receipt = verify_artifact(client, run_id, name, expected_sha256,
                                      consume=handle.write)
            handle.flush()
            os.fsync(handle.fileno())
        # Same-directory link is atomic and refuses concurrent destination creation.
        os.link(provisional, destination, follow_symlinks=False)
        return dict(receipt, run_id=run_id, name=name, output=str(destination))
    except FileExistsError:
        raise AgentAPIError('Destination already exists; choose a new file.', 'conflict', 409) from None
    finally:
        os.unlink(provisional)


def invoke(client, operation, arguments, *, observer=None, observation=None):
    envelope = (client.call(operation, arguments, observer=observer, observation=observation)
                if observer is not None else client.call(operation, arguments))
    if envelope['status'] >= 400:
        error = envelope['result']
        raise AgentAPIError(error['error'], error['code'], envelope['status'])
    return envelope


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('--config', type=Path, required=True,
                        help='Private existing AgentClient endpoint/catalog/token-file configuration')
    add_interface_options(result)
    commands = result.add_subparsers(dest='command', required=True)
    opening = commands.add_parser('open', help='Register/inspect a project without executing its code')
    opening.add_argument('--root', required=True)
    opening.add_argument('--manifest', required=True)
    inspecting = commands.add_parser('inspect', help='Inspect a registered project')
    inspecting.add_argument('--project-id', required=True)
    evidence = commands.add_parser('evidence', help='Preview bounded external project evidence')
    evidence.add_argument('--project-id', required=True)
    evidence.add_argument('--reference-id', required=True)
    importing = commands.add_parser('import-data', help='Import an exact inspected scientific data reference')
    importing.add_argument('--project-id', required=True)
    importing.add_argument('--reference-id', required=True)
    importing.add_argument('--expected-sha256', required=True)
    recipe = commands.add_parser('recipe', help='Inspect an exact recipe and its typed parameters')
    recipe.add_argument('--project-id', required=True)
    recipe.add_argument('--reference-id', required=True)
    recipe.add_argument('--expected-sha256', required=True)
    prepare = commands.add_parser('prepare', help='Save an external graph from exact named inputs/parameters')
    prepare.add_argument('--arguments', type=Path, required=True,
                         help='graphs.create_external JSON arguments; prints the saved graph before preflight')
    preflight = commands.add_parser('preflight', help='Inspect exact execution material; never runs project code')
    preflight.add_argument('--graph-id', required=True)
    preflight.add_argument('--revision', type=int, required=True)
    submit = commands.add_parser('submit', help='Submit exact reviewed material with an existing owner grant')
    submit.add_argument('--arguments', type=Path, required=True,
                        help='runs.submit_external JSON arguments, including approval_id and stable request_key')
    status = commands.add_parser('status', help='Read a durable Run or its bounded progress/result summary')
    status.add_argument('--run-id', required=True)
    status.add_argument('--progress', action='store_true')
    cancel = commands.add_parser('cancel', help='Explicitly request cancellation of an existing Run')
    cancel.add_argument('--run-id', required=True)
    artifact = commands.add_parser('download', help='Download a complete artifact with SHA256 verification')
    artifact.add_argument('--run-id', required=True)
    artifact.add_argument('--name', required=True)
    artifact.add_argument('--expected-sha256', required=True)
    artifact.add_argument('--out', type=Path, required=True)
    operation = commands.add_parser('call', help='Call one locally registered compatible operation with bounded JSON arguments')
    operation.add_argument('--operation', required=True)
    operation.add_argument('--arguments', type=Path, required=True)
    return result


def _write_output(stream, value, observer, observation, *, status=200, failed=False,
                  http_status=None, observed_outcome=None):
    raw = (json.dumps(value, ensure_ascii=True, allow_nan=False,
                      **({} if failed else {'indent': 2})) + '\n').encode('ascii')
    classified = observed_outcome or outcome(status)
    observe_stage(observer, observation, 'returned', outcome=classified,
                  envelope_status=status, http_status=http_status)
    written = 0
    try:
        try:
            fd = stream.fileno()
        except (AttributeError, OSError, ValueError):
            fd = None
        if fd is None:
            count = stream.write(raw.decode('ascii'))
            written = len(raw) if count is None else count
            stream.flush()
            if written != len(raw):
                raise OSError('incomplete-output')
        else:
            view = memoryview(raw)
            while view:
                count = os.write(fd, view)
                if count <= 0:
                    raise OSError('incomplete-output')
                written += count
                view = view[count:]
    except (OSError, ValueError):
        observe_stage(observer, observation, 'terminal', outcome='unknown',
                      response_bytes=written, delivery='incomplete')
        return False
    observe_stage(observer, observation, 'terminal', outcome=classified,
                  envelope_status=status, http_status=http_status, response_bytes=written, delivery='written')
    return True


def main(argv=None, *, observer=None):
    args = parser().parse_args(argv)
    owned_observer = observer is None
    if owned_observer:
        observer = configured_interface(args, 'cli')
    observation = observe_begin(observer, args.command if args.command in ('status', 'download') else 'call')
    try:
        status, http_status = 200, None
        client = AgentClient.from_config(args.config)
        if args.command == 'download':
            observe_selection(observer, observation, 'runs.artifact_chunk',
                              {'run_id': args.run_id, 'name': args.name, 'expected_sha256': args.expected_sha256})
            for phase in ('validated', 'admitted', 'dispatch'):
                observe_stage(observer, observation, phase)
            result = download(client, args.run_id, args.name, args.expected_sha256, args.out)
        else:
            if args.command == 'call':
                operation, arguments = args.operation, read_arguments(args.arguments)
            elif args.command == 'open':
                operation, arguments = 'project_snapshots.open', dict(root=args.root, manifest_path=args.manifest)
            elif args.command == 'inspect':
                operation, arguments = 'project_snapshots.get', dict(project_id=args.project_id)
            elif args.command in ('evidence', 'import-data'):
                operation = 'projects.evidence' if args.command == 'evidence' else 'data.import_project_scientific'
                arguments = dict(project_id=args.project_id, reference_id=args.reference_id)
                if args.command == 'import-data':
                    arguments['expected_sha256'] = args.expected_sha256
            elif args.command == 'recipe':
                operation, arguments = 'recipes.inspect', dict(project_id=args.project_id,
                    reference_id=args.reference_id, expected_sha256=args.expected_sha256)
            elif args.command in ('prepare', 'submit'):
                operation = 'graphs.create_external' if args.command == 'prepare' else 'runs.submit_external'
                arguments = read_arguments(args.arguments)
                # CLI submission requires explicit grant selection even though the
                # domain operation also supports the separate owner UI path.
                if args.command == 'submit' and (not isinstance(arguments, dict) or 'approval_id' not in arguments):
                    raise AgentAPIError('Select the existing owner approval_id for this exact material.')
            elif args.command == 'preflight':
                operation, arguments = 'graphs.preflight_external', dict(graph_id=args.graph_id, revision=args.revision)
            else:
                operation = 'runs.cancel' if args.command == 'cancel' else 'runs.progress' if args.progress else 'runs.get'
                arguments = dict(run_id=args.run_id)
            if args.command in ('open', 'inspect'):
                # Select command semantics from validated capabilities before
                # dispatch. A failed call never triggers a second operation.
                validate_arguments(operation, arguments)
                selected = client.selected_contracts()
                legacy_operation = 'projects.open' if args.command == 'open' else 'projects.get'
                if operation not in selected and legacy_operation in selected:
                    operation = legacy_operation
            envelope = invoke(client, operation, arguments, observer=observer, observation=observation)
            result, status = envelope['result'], envelope['status']
            http_status = status
        return 0 if _write_output(sys.stdout, result, observer, observation, status=status, http_status=http_status) else 1
    except AgentAPIError as error:
        _write_output(sys.stderr, {'code': error.code, 'error': str(error), 'status': error.status},
                      observer, observation, status=error.status, failed=True, observed_outcome=(
                          'transport-error' if error.code in ('transport', 'response_too_large') else
                          'registry-refusal' if error.code == 'registry_mismatch' else
                          'permission-refusal' if error.status in (401, 403) else 'call-error'))
        return 1
    except OSError:
        _write_output(sys.stderr, {'code': 'unavailable', 'error': 'Local file operation failed; inspect saved state before retrying.'},
                      observer, observation, status=503, failed=True)
        return 1
    finally:
        if owned_observer and observer is not None:
            observe_close(observer)


if __name__ == '__main__':
    raise SystemExit(main())
