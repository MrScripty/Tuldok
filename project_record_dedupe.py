"""Physical deduplication of retained runtime closures in Run history records.

Retained external-recipe Runs each embed the same captured runtime closure three
times: run.spec.runtime_files, run.material.runtime and a contiguous block of
'historical_runtime' payload edges (about 2.5 MB per Run). The store keeps one
content-addressed `run_runtime_closure` record and a compact Run document
(`project_run_history_v2`) that references it. Stores expand compact Runs back
to the exact logical v1 document on read, so domain owners and validators see
unchanged documents. A Run is compacted only when expansion reproduces its
canonical bytes exactly.
"""
import copy
import hashlib

RUN_FAMILY = 'run_history'
RUN_V1 = 'project_run_history_v1'
RUN_V2 = 'project_run_history_v2'
CLOSURE_FAMILY = 'run_runtime_closure'
CLOSURE_FORMAT = 'project_run_runtime_closure_v1'
RUNTIME_ROLE = 'historical_runtime'


def _encode(value):
    from project_store import _encode as canonical
    return canonical(value)


def closure_id(closure):
    """Content address of a closure document."""
    return hashlib.sha256(_encode(closure)).hexdigest()


def compact(document):
    """(compact v2 document, closure document) or None when not exactly reversible."""
    if type(document) is not dict or document.get('format') != RUN_V1:
        return None
    run = document.get('run')
    payloads = document.get('payloads')
    if type(run) is not dict or type(payloads) is not list:
        return None
    spec, material = run.get('spec'), run.get('material')
    if (type(spec) is not dict or type(material) is not dict or 'runtime_files' not in spec
            or 'runtime' not in material or 'runtime_closure' in document):
        return None
    positions = [index for index, edge in enumerate(payloads)
                 if type(edge) is dict and edge.get('role') == RUNTIME_ROLE]
    if not positions or positions != list(range(positions[0], positions[-1] + 1)):
        return None
    start, end = positions[0], positions[-1] + 1
    closure = dict(format=CLOSURE_FORMAT, runtime_files=copy.deepcopy(spec['runtime_files']),
                   runtime=copy.deepcopy(material['runtime']), payload_block=copy.deepcopy(payloads[start:end]))
    reduced = copy.deepcopy(document)
    del reduced['run']['spec']['runtime_files']
    del reduced['run']['material']['runtime']
    reduced['payloads'] = reduced['payloads'][:start] + reduced['payloads'][end:]
    reduced['format'] = RUN_V2
    reduced['runtime_closure'] = dict(id=closure_id(closure), payload_index=start)
    if _encode(expand(reduced, closure)) != _encode(document):
        return None
    return reduced, closure


def expand(document, closure):
    """The exact logical v1 Run document of a compact v2 document."""
    reference = document['runtime_closure']
    if closure.get('format') != CLOSURE_FORMAT or closure_id(closure) != reference['id']:
        from project_store import _fail
        _fail('Run runtime closure differs from its reference.')
    result = copy.deepcopy(document)
    del result['runtime_closure']
    result['format'] = RUN_V1
    result['run']['spec']['runtime_files'] = copy.deepcopy(closure['runtime_files'])
    result['run']['material']['runtime'] = copy.deepcopy(closure['runtime'])
    index = reference['payload_index']
    if type(index) is not int or not 0 <= index <= len(result['payloads']):
        from project_store import _fail
        _fail('Invalid Run runtime closure position.')
    result['payloads'] = result['payloads'][:index] + copy.deepcopy(closure['payload_block']) + result['payloads'][index:]
    return result


def is_compact(family, document):
    return family == RUN_FAMILY and type(document) is dict and document.get('format') == RUN_V2


def logical_records(physical):
    """Logical envelopes of physical records: closures hidden, compact Runs expanded."""
    closures = {item['id']: item['document'] for item in physical if item['family'] == CLOSURE_FAMILY}
    result = []
    for item in physical:
        if item['family'] == CLOSURE_FAMILY:
            continue
        document = item['document']
        if is_compact(item['family'], document):
            closure = closures.get(document['runtime_closure']['id'])
            if closure is None:
                from project_store import _fail
                _fail('Compact Run references a missing runtime closure.')
            document = expand(document, closure)
        result.append(dict(family=item['family'], id=item['id'], document=document))
    return result


def physical_records(logical, *, existing_closures=None):
    """Physical envelopes for logical records, compacting Runs where exact.

    existing_closures maps closure id -> document already stored; compacted
    Runs reference them and every referenced closure is included once.
    """
    closures = dict(existing_closures or {})
    used = set()
    result = []
    for item in logical:
        document = item['document']
        if item['family'] == RUN_FAMILY:
            compacted = compact(document)
            if compacted is not None:
                document, closure = compacted
                identity = document['runtime_closure']['id']
                closures.setdefault(identity, closure)
                used.add(identity)
        result.append(dict(family=item['family'], id=item['id'], document=document))
    result.extend(dict(family=CLOSURE_FAMILY, id=identity, document=closures[identity]) for identity in sorted(used))
    return sorted(result, key=lambda item: (item['family'], item['id']))
