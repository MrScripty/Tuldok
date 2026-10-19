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
import signal
import threading

from agent_api import (AgentAPIError, AgentClient, PublicationOwnerClient, CoordinatorOwnerClient, REQUEST_LIMIT, decode,
                       validate_arguments, verify_artifact, verify_publication_artifact)
from tuldok_client import WorkflowClient, download
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
    publication = commands.add_parser('publication-status', help='Inspect saved publication status without retrying compute')
    publication.add_argument('--run-id', required=True)
    timing = commands.add_parser('phase-timings', help='Inspect bounded owner phase observations; does not start or retry work')
    timing.add_argument('--run-id', required=True)
    preparation = commands.add_parser('preparation-timings', help='Inspect current actor exact graph preparation observation')
    preparation.add_argument('--graph-id', required=True)
    preparation.add_argument('--revision', type=int, required=True)
    commands.add_parser('coordinator-status', help='Inspect saved coordinator generation, current readiness and recovery receipt')
    coordinator = commands.add_parser('recover-coordinator', help='Explicit owner recovery without replaying compute')
    coordinator.add_argument('--arguments', type=Path, required=True,
                             help='Exact expected_generation and stable request_key JSON')
    for command in ('recover-publication', 'cancel-publication'):
        recovery = commands.add_parser(command, help='Explicit owner publication action using existing owner configuration')
        recovery.add_argument('--arguments', type=Path, required=True)
    publication_result = commands.add_parser('publication-result', help='Verify an exact attached publication result')
    publication_result.add_argument('--ref', type=Path, required=True)
    publication_download = commands.add_parser('download-publication', help='Collect exact recovered artifact and verify whole SHA256')
    publication_download.add_argument('--ref', type=Path, required=True)
    publication_download.add_argument('--name', required=True)
    publication_download.add_argument('--expected-sha256', required=True)
    publication_download.add_argument('--out', type=Path, required=True)
    operation = commands.add_parser('call', help='Call one locally registered compatible operation with bounded JSON arguments')
    operation.add_argument('--operation', required=True)
    operation.add_argument('--arguments', type=Path, required=True)
    submission = commands.add_parser('submission-manifest', help='Export exact selected material and existing grant without submission')
    source = submission.add_mutually_exclusive_group(required=True)
    source.add_argument('--graph-id')
    source.add_argument('--trial-id')
    submission.add_argument('--revision', type=int)
    submission.add_argument('--approval-id', required=True)
    submission.add_argument('--request-key', required=True)
    for command in ('submit-workflow', 'reconcile-submission', 'compare'):
        workflow = commands.add_parser(command, help='Explicit consumer workflow with typed machine-readable outcome')
        workflow.add_argument('--manifest', type=Path, required=True,
                              help='Exact exported manifest, or unknown receipt for reconcile-submission')
    monitoring = commands.add_parser('monitor', help='Read-only finite monitoring; stopping does not cancel compute')
    monitoring.add_argument('--run-id', required=True)
    monitoring.add_argument('--timeout', type=float, default=60)
    cancellation = commands.add_parser('cancel-workflow', help='Explicit cancellation showing requested versus drained')
    cancellation.add_argument('--run-id', required=True)
    collection = commands.add_parser('collection-manifest', help='Export bounded selection from current exact artifact inventory')
    source = collection.add_mutually_exclusive_group(required=True)
    source.add_argument('--run-id')
    source.add_argument('--ref', type=Path)
    collection.add_argument('--name', action='append', required=True)
    collecting = commands.add_parser('collect', help='Collect exact files; explicit resume rechecks successes and restarts incomplete items')
    collecting.add_argument('--manifest', type=Path, required=True)
    collecting.add_argument('--directory', type=Path, required=True)
    collecting.add_argument('--resume', type=Path)
    batching = commands.add_parser('collect-batch', help='Explicit max20 whole artifacts/8 MiB batch; use ordinary collect --resume for partial receipts')
    batching.add_argument('--manifest', type=Path, required=True)
    batching.add_argument('--directory', type=Path, required=True)
    comparison = commands.add_parser('comparison-manifest', help='Export exact checkpoint/evaluation/metric operands from selected evidence')
    comparison.add_argument('--run-id', required=True)
    comparison.add_argument('--other-run-id', required=True)
    comparison.add_argument('--checkpoint-sha256', required=True)
    comparison.add_argument('--other-checkpoint-sha256', required=True)
    comparison.add_argument('--metric-id', required=True)
    comparison.add_argument('--mode', choices=('paired', 'side_by_side'), default='paired')
    comparison.add_argument('--ref', type=Path)
    comparison.add_argument('--other-ref', type=Path)
    return result


WORKFLOW_COMMANDS = frozenset(('submission-manifest', 'submit-workflow', 'reconcile-submission',
    'monitor', 'cancel-workflow', 'collection-manifest', 'collect', 'collect-batch', 'comparison-manifest', 'compare'))


def workflow_command(client, args):
    workflow = WorkflowClient(client)
    stop = threading.Event()
    old_handler = None
    if args.command in ('monitor', 'collect', 'collect-batch') and threading.current_thread() is threading.main_thread():
        old_handler = signal.signal(signal.SIGINT, lambda *_: stop.set())
    try:
        if args.command == 'submission-manifest':
            fields = dict(approval_id=args.approval_id, request_key=args.request_key)
            if args.trial_id is not None:
                if args.revision is not None:
                    raise AgentAPIError('Trial selection reads its current Study revision; omit --revision.')
                value = workflow.trial_submission_manifest(args.trial_id, **fields)
            else:
                if args.revision is None:
                    raise AgentAPIError('Graph selection requires --revision.')
                value = workflow.submission_manifest(args.graph_id, args.revision, **fields)
        elif args.command in ('submit-workflow', 'reconcile-submission'):
            action = workflow.submit if args.command == 'submit-workflow' else workflow.reconcile
            value = action(read_arguments(args.manifest))
            return value, value['state'] == 'acknowledged'
        elif args.command == 'monitor':
            value = workflow.monitor(args.run_id, timeout=args.timeout, cancelled=stop)
            return value, value['state'] == 'terminal'
        elif args.command == 'cancel-workflow':
            value = workflow.cancel(args.run_id)
        elif args.command == 'collection-manifest':
            value = workflow.collection_manifest(names=args.name, run_id=args.run_id,
                result_ref=read_arguments(args.ref) if args.ref else None)
        elif args.command == 'collect':
            value = workflow.collect(read_arguments(args.manifest), args.directory,
                resume=read_arguments(args.resume) if args.resume else None, cancelled=stop)
            return value, value['state'] == 'complete'
        elif args.command == 'collect-batch':
            value = workflow.collect_batch(read_arguments(args.manifest), args.directory, cancelled=stop)
            return value, value['state'] == 'complete'
        elif args.command == 'comparison-manifest':
            value = workflow.comparison_manifest(args.run_id, args.other_run_id,
                checkpoint_sha256=args.checkpoint_sha256, other_checkpoint_sha256=args.other_checkpoint_sha256,
                metric_id=args.metric_id, mode=args.mode, result_ref=read_arguments(args.ref) if args.ref else None,
                other_result_ref=read_arguments(args.other_ref) if args.other_ref else None)
        else:
            value = workflow.compare(read_arguments(args.manifest))
            return value, value['status'] < 400
        return value, True
    finally:
        if old_handler is not None:
            signal.signal(signal.SIGINT, old_handler)


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
        client_type = PublicationOwnerClient if args.command in ('recover-publication', 'cancel-publication') else AgentClient
        if args.command == 'recover-coordinator':
            client_type = CoordinatorOwnerClient
        client = client_type.from_config(args.config)
        if args.command in WORKFLOW_COMMANDS:
            result, success = workflow_command(client, args)
            written = _write_output(sys.stdout, result, observer, observation, status=200 if success else 409)
            return 0 if success and written else 1
        if args.command in ('download', 'download-publication'):
            ref = read_arguments(args.ref) if args.command == 'download-publication' else None
            if ref is not None:
                validate_arguments('runs.publication_artifact_chunk', {'ref': ref, 'name': args.name,
                    'expected_sha256': args.expected_sha256, 'offset': 0, 'max_bytes': 8*1024*1024})
            run_id = ref.get('run_id') if ref is not None else args.run_id
            selected_operation = 'runs.publication_artifact_chunk' if ref is not None else 'runs.artifact_chunk'
            observe_selection(observer, observation, selected_operation,
                              {'run_id': run_id, 'name': args.name, 'expected_sha256': args.expected_sha256})
            for phase in ('validated', 'admitted', 'dispatch'):
                observe_stage(observer, observation, phase)
            result = download(client, run_id, args.name, args.expected_sha256, args.out, result_ref=ref)
        else:
            if args.command == 'call':
                operation, arguments = args.operation, read_arguments(args.arguments)
            elif args.command == 'phase-timings':
                operation, arguments = 'runs.phase_timings', {'run_id': args.run_id}
            elif args.command == 'preparation-timings':
                operation, arguments = 'graphs.preparation_timings', {'graph_id': args.graph_id, 'revision': args.revision}
            elif args.command == 'coordinator-status':
                operation, arguments = 'runs.coordinator_health', {}
            elif args.command == 'recover-coordinator':
                operation, arguments = 'runs.recover_coordinator', read_arguments(args.arguments)
            elif args.command in ('recover-publication', 'cancel-publication'):
                operation = 'runs.recover_publication' if args.command == 'recover-publication' else 'runs.cancel_publication'
                arguments = read_arguments(args.arguments)
            elif args.command == 'publication-status':
                operation, arguments = 'runs.publication_status', {'run_id': args.run_id}
            elif args.command == 'publication-result':
                operation, arguments = 'runs.publication_result', {'ref': read_arguments(args.ref)}
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
