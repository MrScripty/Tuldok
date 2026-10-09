"""Rheon adapters pinned to draft PR20 v1 and PR32 v2; validation is not human review."""
import base64
import hashlib
import io
from pathlib import Path
import tempfile
import zipfile

import rheon_sequence_contract as contract
import rheon_controls_contract as controls_contract
from workbench import WorkbenchError, encode

SOURCE_COMMIT = 'fee7b4a139574f87b259796b1ba8698a41d31ac1'
ADAPTER = {'repository': 'MrScripty/Rheon', 'contract_commit': SOURCE_COMMIT,
           'pull_request': 20, 'status': 'draft contract, not assumed merged',
           'validator_path': 'tools/import_dense3d_sequence.py'}
MAX_REQUEST = 3 * 1024 * 1024
CONTROLS_ADAPTER = {'repository': 'MrScripty/Rheon', 'contract_commit': '020437fa638ad56823b544ba1f9207ceef065f12',
    'pull_request': 32, 'status': 'draft contract, not assumed merged; validation does not authenticate producer identity',
    'validator_path': 'tools/import_dense3d_controls.py',
    'validator_source_sha256': '215f98241e01a6fb099b5b1b8789e00c951988e1382438afbd45cfbb7e1c4c43'}


def decode_file(value, cap, name):
    try:
        if type(value) is not str or len(value) > ((cap + 2) // 3) * 4:
            raise ValueError()
        raw = base64.b64decode(value, validate=True)
        if not 0 < len(raw) <= cap:
            raise ValueError()
        return raw
    except ValueError:
        raise WorkbenchError(f'{name} must be a complete base64 file of at most {cap} bytes.') from None


def prepare(run_raw, frames_raw, controls_raw=None):
    if not 0 < len(run_raw) <= contract.MANIFEST_LIMIT or not 0 < len(frames_raw) <= contract.FRAMES_LIMIT:
        raise WorkbenchError('Rheon files exceed manifest/frame byte bounds.')
    try:
        manifest = contract.parse(run_raw)
        version = contract.integer(manifest['version'], 1, 2, 'sequence version')
        if version == 1 and controls_raw is not None:
            raise ValueError('v1 import requires the original two-file bundle; authored controls belong in the inspector')
        if version == 2 and (type(controls_raw) is not bytes or not 0 < len(controls_raw) <= controls_contract.CONTROLS_LIMIT):
            raise ValueError('v2 requires complete controls.json, at most 65536 bytes')
        # Source-pinned validators (v2 dependency alias only) see bounded server-owned files.
        with tempfile.TemporaryDirectory(prefix='tuldok-rheon-') as directory:
            path = Path(directory)
            (path / 'run.json').write_bytes(run_raw)
            (path / 'frames.jsonl').write_bytes(frames_raw)
            if version == 2:
                (path / 'controls.json').write_bytes(controls_raw)
            summary = (controls_contract if version == 2 else contract).verify(path)
        lines = [line + b'\n' for line in frames_raw.split(b'\n')[:-1]]
        index, offset = [], 0
        for line in lines:
            frame = contract.parse(line)
            index.append({key: frame[key] for key in ('frame', 'time_s', 'dt_s', 'carrier_stamp', 'liquid_stamp', 'diagnostics')})
            index[-1].update(byte_offset=offset, byte_length=len(line), sha256=hashlib.sha256(line).hexdigest())
            offset += len(line)
        constructor = contract._fields(contract.parse(lines[0]))
        constructor = {name: [0.0 if value == 0 else value for value in values] for name, values in constructor.items()}
        physical = {key: value for key, value in contract.CONFIG.items() if not key.endswith(('_id', '_version'))}
        family = hashlib.sha256(encode({'geometry': contract.GEOMETRY, 'config': physical, 'fields': constructor}).encode()).hexdigest()
        run_hash = hashlib.sha256(run_raw).hexdigest()
        trajectory = hashlib.sha256(run_raw + b'\0' + frames_raw).hexdigest()
        metadata = {'adapter': CONTROLS_ADAPTER if version == 2 else ADAPTER, 'manifest': manifest, 'run_sha256': run_hash,
                    'frame_index': index, 'technical_validation': summary,
                    'protected_groups': ['trajectory:' + trajectory, 'initial-family:' + family],
                    'scope': 'whole accepted-state trajectory; transport-only; no training qualification'}
        if version == 2:
            metadata['controls'] = {'sha256': manifest['controls_sha256'], 'bytes': len(controls_raw),
                'interval_count': 8, 'provenance': contract.parse(controls_raw)['provenance'],
                'origin_status': 'wire declaration; validation alone does not authenticate producer identity'}
        # Ensure metadata is safe for the existing UTF-8 JSON/history owner.
        encode(metadata).encode('utf-8')
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w', zipfile.ZIP_STORED) as archive:
            archive.writestr(zipfile.ZipInfo('run.json'), run_raw)
            archive.writestr(zipfile.ZipInfo('frames.jsonl'), frames_raw)
            if version == 2:
                archive.writestr(zipfile.ZipInfo('controls.json'), controls_raw)
        return {'bundle': stream.getvalue(), 'metadata': metadata}
    except (ValueError, KeyError, TypeError, UnicodeError, OverflowError, RecursionError) as error:
        raise WorkbenchError('Invalid completed Rheon sequence: ' + str(error)) from error


def admit(workbench, body):
    if type(body) is not dict or set(body) - {'files', 'name', 'groups', 'parents', 'rights'} or type(body.get('files')) is not dict or set(body['files']) not in ({'run.json', 'frames.jsonl'}, {'run.json', 'frames.jsonl', 'controls.json'}):
        raise WorkbenchError('Supply run.json and frames.jsonl; version 2 also requires controls.json.')
    run_raw = decode_file(body['files']['run.json'], contract.MANIFEST_LIMIT, 'run.json')
    frames_raw = decode_file(body['files']['frames.jsonl'], contract.FRAMES_LIMIT, 'frames.jsonl')
    controls_raw = decode_file(body['files']['controls.json'], controls_contract.CONTROLS_LIMIT, 'controls.json') if 'controls.json' in body['files'] else None
    return workbench.sequences.admit(prepare(run_raw, frames_raw, controls_raw), body)
