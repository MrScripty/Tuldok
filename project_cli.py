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

from agent_api import AgentAPIError, AgentClient, REQUEST_LIMIT, decode, verify_artifact


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


def invoke(client, operation, arguments):
    envelope = client.call(operation, arguments)
    if envelope['status'] >= 400:
        error = envelope['result']
        raise AgentAPIError(error['error'], error['code'], envelope['status'])
    return envelope['result']


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('--config', type=Path, required=True,
                        help='Private existing AgentClient endpoint/catalog/token-file configuration')
    commands = result.add_subparsers(dest='command', required=True)
    opening = commands.add_parser('open', help='Register/inspect a project without executing its code')
    opening.add_argument('--root', required=True)
    opening.add_argument('--manifest', required=True)
    inspecting = commands.add_parser('inspect', help='Inspect a registered project')
    inspecting.add_argument('--project-id', required=True)
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


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        client = AgentClient.from_config(args.config)
        if args.command == 'download':
            result = download(client, args.run_id, args.name, args.expected_sha256, args.out)
        else:
            if args.command == 'call':
                operation, arguments = args.operation, read_arguments(args.arguments)
            elif args.command == 'open':
                operation, arguments = 'projects.open', dict(root=args.root, manifest_path=args.manifest)
            elif args.command == 'inspect':
                operation, arguments = 'projects.get', dict(project_id=args.project_id)
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
            result = invoke(client, operation, arguments)
        print(json.dumps(result, ensure_ascii=True, allow_nan=False, indent=2))
        return 0
    except AgentAPIError as error:
        print(json.dumps({'code': error.code, 'error': str(error), 'status': error.status}), file=sys.stderr)
        return 1
    except OSError:
        print(json.dumps({'code': 'unavailable', 'error': 'Local file operation failed; inspect saved state before retrying.'}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
