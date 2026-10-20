"""Versioned bounded diagnostic capture; diagnostic JSON conveys no science verdict.

The host and SDK share this inert contract. The host supplies only bytes already
bound to its retained inventory; the writer has no read/export authority.
"""
import hashlib

from .evidence import (EvidenceError, boundary, canonical, closed, decode, digest,
                       name, natural, require, sha)

POLICY_FORMAT = 'extension_field_policy_indexed_v1'
CAPTURE_FORMAT = 'diagnostic_capture_v1'
INDEX_FORMAT = 'diagnostic_index_v1'
SHARD_FORMAT = 'diagnostic_shard_v1'
PAYLOAD_SCHEMA = 'diagnostic_json_object_v1'
INDEX_ROLE = 'diagnostic_index_v1'
SHARD_ROLE = 'diagnostic_shard_v1'
MEDIA_TYPE = 'application/json'


def _scopes(capture, policy):
    """Resolve the declared population from existing fixed probe/capture limits."""
    members = [item['frozen_reference']['member_id'] for item in policy['probe']['candidates']]
    clock = policy['profile']['capture']
    positions = [clock['interval'] * step for step in range(1, clock['max_snapshots'] + 1)]
    order = {(member, point, phase): ordinal for ordinal, (member, point, phase) in enumerate(
        (member, point, phase) for member in members for point in positions for phase in capture['phases'])}
    previous = -1
    total = 0
    scopes = []
    for row in capture['coverage']:
        closed(row, ('case_id', 'checkpoint_point', 'phase', 'required_count', 'optional_count'), 'Diagnostic scope')
        natural(row['checkpoint_point'], 'Diagnostic checkpoint point', 1)
        key = (row['case_id'], row['checkpoint_point'], row['phase'])
        require(key in order and order[key] > previous, 'Diagnostic scope membership/order differs.')
        previous = order[key]
        required = natural(row['required_count'], 'Required diagnostic count')
        optional = natural(row['optional_count'], 'Optional diagnostic count')
        require(required + optional > 0, 'Diagnostic scope must declare a population.')
        scopes.append((total, total + required, total + required + optional, row))
        total += required + optional
    return scopes, total


@boundary
def validate_capture(capture, policy, outputs):
    """Admission proof, using current output declarations and selected profile caps.

    Opt-in profiles reserve their declared output maxima within the aggregate
    budget. This proves capacity before compute; actual JSON/array checks remain
    mandatory after capture.
    """
    closed(capture, ('format', 'index', 'shards', 'payload_schema', 'phases', 'coverage',
                     'records_per_shard', 'max_record_bytes'), 'Diagnostic capture')
    require(capture['format'] == CAPTURE_FORMAT and capture['payload_schema'] == PAYLOAD_SCHEMA,
            'Unsupported diagnostic capture/schema.', 'unsupported')
    limits = policy['profile']['limits']
    require(type(outputs) is list and outputs, 'Diagnostic outputs are required.')
    declarations = {item['path']: item for item in outputs}
    require(type(capture['phases']) is list and 1 <= len(capture['phases']) <= len(outputs), 'Diagnostic phases exceed the output population bound.')
    require(all(type(phase) is str and name(phase) for phase in capture['phases'])
            and len(set(capture['phases'])) == len(capture['phases']), 'Diagnostic phases must be unique flat names.')
    require(type(capture['shards']) is list and 1 <= len(capture['shards']) < len(outputs), 'Diagnostic shard count exceeds declared outputs.')
    files = [item['name'] for item in [capture['index'], *capture['shards']]]
    require(all(type(filename) is str and name(filename) for filename in files)
            and len(set(files)) == len(files), 'Diagnostic filenames must be unique.')
    for artifact, role, required in [(capture['index'], INDEX_ROLE, True),
                                     *((item, SHARD_ROLE, False) for item in capture['shards'])]:
        closed(artifact, ('name', 'max_bytes'), 'Diagnostic artifact declaration')
        filename = artifact['name']
        rule = declarations.get(filename)
        require(rule is not None and rule['role'] == role and rule['required'] is required,
                'Diagnostic output role/required declaration differs.')
        natural(artifact['max_bytes'], 'Diagnostic file bound', 1, limits['shard_bytes'])
        require(rule['max_bytes'] == artifact['max_bytes'], 'Diagnostic output byte declaration differs.')
    # A dedicated diagnostic file cannot alias an existing required science file.
    science = {item[key] for item in policy['field_outputs'] for key in ('prediction', 'reference')}
    science.update(item['artifact'] for row in policy['probe_inputs'] for item in row['fields'])
    science.update(('execution-context.json', 'model-evidence.json', 'model-definition.json', 'profile.json',
                    'probe.json', 'metric-definitions.json', 'checkpoints.json', 'observations.json',
                    'field-index.json', 'fitted-transform.json', 'output-policy.json'))
    require(not set(files) & science, 'Diagnostic capture cannot replace scientific evidence.')
    require(sum(item['max_bytes'] for item in outputs) <= limits['total_output_bytes'],
            'Declared diagnostic/scientific outputs cannot fit the admitted aggregate bound.', 'unsupported')
    per_shard = natural(capture['records_per_shard'], 'Diagnostic records per shard', 1)
    record_bytes = natural(capture['max_record_bytes'], 'Diagnostic record bytes', 1, limits['shard_bytes'])
    # Exact worst-case envelope: run IDs and SHA-256 identities have fixed widths.
    envelope = len(canonical(dict(format=SHARD_FORMAT, run_id='0' * 32,
                                  capture_sha256='0' * 64, records=[]))) + 1
    require(all(envelope + per_shard * (record_bytes + 1) <= item['max_bytes']
                for item in capture['shards']), 'Diagnostic record declaration cannot fit each shard.', 'unsupported')
    require(type(capture['coverage']) is list and capture['coverage'], 'Diagnostic coverage is required.')
    scopes, total = _scopes(capture, policy)
    require(total <= len(capture['shards']) * per_shard, 'Diagnostic population cannot fit declared shards.', 'unsupported')
    # Refuse records whose mandatory identity envelope alone exceeds its bound.
    for _start, _mandatory_end, _end, scope in scopes:
        sample = dict(ordinal=total - 1, case_id=scope['case_id'], checkpoint_point=scope['checkpoint_point'],
                      checkpoint_sha256='0' * 64, phase=scope['phase'], payload={})
        require(len(canonical(sample)) <= record_bytes, 'Diagnostic record identity cannot fit its bound.', 'unsupported')
    # Reserve even the uncompressed optional omission list. Compute its size
    # arithmetically, so an impossible count never allocates that population.
    worst_shards = [dict(blob=dict(name=item['name'], bytes=item['max_bytes'], sha256='0' * 64, media_type=MEDIA_TYPE),
        record_count=per_shard, first_ordinal=total - 1, last_ordinal=total - 1) for item in capture['shards']]
    coverage = _coverage(scopes, total, [])
    optional = coverage['optional_count']
    coverage.update(omitted_count=optional, retained_optional_count=0)
    worst_index = _index(capture, '0' * 32, '0' * 64, worst_shards, coverage)
    omission_bytes = len(canonical(dict(start=total - 1, count=total, reason='capture_budget'))) + 1
    require(len(canonical(worst_index)) + optional * omission_bytes + 1 <= capture['index']['max_bytes'],
            'Diagnostic index cannot fit its declared bound.', 'unsupported')
    return capture


def _omissions(scopes, total, omitted):
    require(type(omitted) is list, 'Diagnostic omissions must be explicit ranges.')
    end = 0
    for row in omitted:
        closed(row, ('start', 'count', 'reason'), 'Diagnostic omission')
        start = natural(row['start'], 'Omission start', 0, total)
        count = natural(row['count'], 'Omission count', 1, total)
        require(start >= end and start + count <= total, 'Omission ranges overlap or exceed the population.')
        require(type(row['reason']) is str and row['reason'] in ('capture_budget', 'not_available', 'not_requested'),
                'Unsupported optional diagnostic omission reason.')
        require(any(required_end <= start and start + count <= scope_end
                    for _begin, required_end, scope_end, _scope in scopes),
                'Mandatory diagnostic information cannot be omitted.')
        end = start + count
    return omitted


def _coverage(scopes, total, omitted):
    required = sum(mandatory_end - start for start, mandatory_end, _end, _scope in scopes)
    omitted_count = sum(row['count'] for row in omitted)
    return dict(total_count=total, required_count=required, optional_count=total - required,
                retained_required_count=required, retained_optional_count=total - required - omitted_count,
                omitted_count=omitted_count, omitted=omitted)


def _index(capture, run_id, material_sha256, shards, coverage):
    return dict(format=INDEX_FORMAT, payload_schema=PAYLOAD_SCHEMA, run_id=run_id,
                material_sha256=material_sha256, capture_sha256=digest(capture),
                shards=shards, total_shard_bytes=sum(item['blob']['bytes'] for item in shards), coverage=coverage)


def _records(capture, policy, records, omitted, checkpoints, checkpoint=lambda: None):
    scopes, total = _scopes(capture, policy)
    _omissions(scopes, total, omitted)
    require(type(records) is list and len(records) == total - sum(row['count'] for row in omitted),
            'Diagnostic retained count differs from complete declared coverage.')
    missing = {ordinal for row in omitted for ordinal in range(row['start'], row['start'] + row['count'])}
    expected = (ordinal for ordinal in range(total) if ordinal not in missing)
    scope_position = 0
    for ordinal, record in zip(expected, records, strict=True):
        checkpoint()
        closed(record, ('ordinal', 'case_id', 'checkpoint_point', 'checkpoint_sha256', 'phase', 'payload'), 'Diagnostic record')
        while ordinal >= scopes[scope_position][2]:
            scope_position += 1
        scope = scopes[scope_position][3]
        require(type(record['ordinal']) is int and type(record['checkpoint_point']) is int and record['ordinal'] == ordinal and
                record['case_id'] == scope['case_id'] and record['checkpoint_point'] == scope['checkpoint_point'] and
                record['phase'] == scope['phase'], 'Diagnostic ordinal/case/checkpoint/phase differs.')
        sha(record['checkpoint_sha256'])
        require(record['checkpoint_sha256'] == checkpoints[scope['checkpoint_point']], 'Diagnostic checkpoint Ref differs.')
        require(type(record['payload']) is dict, 'Diagnostic payload must be a finite JSON object.')
        require(len(canonical(record)) <= capture['max_record_bytes'], 'Diagnostic record exceeds its admitted byte bound.')
    return _coverage(scopes, total, omitted)


@boundary
def write(writer, records, omitted):
    """Write exact bounded records; never sample/truncate mandatory information."""
    policy = writer.policy
    require(policy.get('format') == POLICY_FORMAT, 'Indexed diagnostics require their explicit policy.', 'unsupported')
    capture = policy['diagnostic_capture']
    checkpoints = {entry['clocks'][policy['profile']['capture']['clock']]: entry['checkpoint']['sha256'] for entry in writer.entries}
    coverage = _records(capture, policy, records, omitted, checkpoints)
    shards = []; documents = []
    for position in range(0, len(records), capture['records_per_shard']):
        rows = records[position:position + capture['records_per_shard']]
        artifact = capture['shards'][len(shards)]
        filename = artifact['name']
        document = dict(format=SHARD_FORMAT, run_id=writer.context['run_id'], capture_sha256=digest(capture), records=rows)
        require(len(canonical(document)) + 1 <= artifact['max_bytes'], 'Diagnostic shard exceeds its declared output bound.')
        raw = canonical(document) + b'\n'
        documents.append((filename, raw))
        blob = dict(name=filename, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(), media_type=MEDIA_TYPE)
        shards.append(dict(blob=blob, record_count=len(rows),
                           first_ordinal=rows[0]['ordinal'], last_ordinal=rows[-1]['ordinal']))
    value = _index(capture, writer.context['run_id'], writer.context['composition']['sha256'], shards, coverage)
    require(len(canonical(value)) + 1 <= capture['index']['max_bytes'], 'Diagnostic index exceeds its declared output bound.')
    documents.append((capture['index']['name'], canonical(value) + b'\n'))
    require(sum(item['bytes'] for item in writer.inventory()) + sum(len(raw) for _filename, raw in documents)
            <= policy['profile']['limits']['total_output_bytes'], 'Diagnostic capture exceeds the admitted aggregate bound.')
    for filename, raw in documents:
        writer.write_raw(filename, raw)
    return value


@boundary
def verify(capture, policy, payloads, context, checkpoint_index, checkpoint=lambda: None):
    """Validate only host-retained inventory bytes, without filesystem discovery."""
    index = decode(payloads[capture['index']['name']])
    closed(index, ('format', 'payload_schema', 'run_id', 'material_sha256', 'capture_sha256', 'shards', 'total_shard_bytes', 'coverage'), 'Diagnostic index')
    require(index['format'] == INDEX_FORMAT and index['payload_schema'] == PAYLOAD_SCHEMA and
            index['run_id'] == context['run_id'] and index['material_sha256'] == context['composition']['sha256'] and
            index['capture_sha256'] == digest(capture), 'Diagnostic index admitted identity differs.')
    require(type(index['shards']) is list and len(index['shards']) <= len(capture['shards']), 'Diagnostic shard count differs.')
    records = []
    for position, shard in enumerate(index['shards']):
        checkpoint()
        closed(shard, ('blob', 'record_count', 'first_ordinal', 'last_ordinal'), 'Diagnostic shard entry')
        blob = shard['blob']
        closed(blob, ('name', 'bytes', 'sha256', 'media_type'), 'Diagnostic Blob')
        filename = capture['shards'][position]['name']
        raw = payloads[filename]
        require(blob == dict(name=filename, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(), media_type=MEDIA_TYPE),
                'Diagnostic shard differs from retained artifact identity/media type.')
        document = decode(raw)
        closed(document, ('format', 'run_id', 'capture_sha256', 'records'), 'Diagnostic shard')
        require(document['format'] == SHARD_FORMAT and document['run_id'] == context['run_id'] and
                document['capture_sha256'] == digest(capture), 'Diagnostic shard admitted identity differs.')
        rows = document['records']
        require(type(rows) is list and 1 <= len(rows) <= capture['records_per_shard'], 'Diagnostic shard record count exceeds its bound.')
        require(position == len(index['shards']) - 1 or len(rows) == capture['records_per_shard'], 'Diagnostic shard packing differs.')
        require(type(shard['record_count']) is int and shard['record_count'] == len(rows) and
                type(shard['first_ordinal']) is int and shard['first_ordinal'] == rows[0]['ordinal'] and
                type(shard['last_ordinal']) is int and shard['last_ordinal'] == rows[-1]['ordinal'], 'Diagnostic shard count/range differs.')
        records.extend(rows)
    require({item['name'] for item in capture['shards']} & set(payloads) == {item['blob']['name'] for item in index['shards']},
            'Retained diagnostic shards differ from the indexed set.')
    natural(index['total_shard_bytes'], 'Diagnostic aggregate shard bytes')
    require(index['total_shard_bytes'] == sum(item['blob']['bytes'] for item in index['shards']),
            'Diagnostic aggregate byte count differs.')
    checkpoints = {entry['clocks'][policy['profile']['capture']['clock']]: entry['checkpoint']['sha256']
                   for entry in checkpoint_index['entries']}
    coverage = index['coverage']
    require(type(coverage) is dict and 'omitted' in coverage, 'Diagnostic coverage is required.')
    expected = _records(capture, policy, records, coverage['omitted'], checkpoints, checkpoint)
    require(canonical(coverage) == canonical(expected), 'Diagnostic aggregate coverage/count differs.')
    return index
