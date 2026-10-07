"""Rheon adapter pinned to draft PR 20 fee7b4a; validation is not human review."""
import base64
import hashlib
import io
from pathlib import Path
import tempfile
import zipfile

import rheon_sequence_contract as contract
from workbench import WorkbenchError, encode

SOURCE_COMMIT = 'fee7b4a139574f87b259796b1ba8698a41d31ac1'
ADAPTER = {'repository': 'MrScripty/Rheon', 'contract_commit': SOURCE_COMMIT,
           'pull_request': 20, 'status': 'draft contract, not assumed merged',
           'validator_path': 'tools/import_dense3d_sequence.py'}
MAX_REQUEST = 3 * 1024 * 1024


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


def prepare(run_raw, frames_raw):
    if not 0 < len(run_raw) <= contract.MANIFEST_LIMIT or not 0 < len(frames_raw) <= contract.FRAMES_LIMIT:
        raise WorkbenchError('Rheon files exceed manifest/frame byte bounds.')
    try:
        # Unmodified, source-pinned validator sees only bounded, server-owned files.
        with tempfile.TemporaryDirectory(prefix='tuldok-rheon-') as directory:
            path = Path(directory)
            (path / 'run.json').write_bytes(run_raw)
            (path / 'frames.jsonl').write_bytes(frames_raw)
            summary = contract.verify(path)
        manifest = contract.parse(run_raw)
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
        metadata = {'adapter': ADAPTER, 'manifest': manifest, 'run_sha256': run_hash,
                    'frame_index': index, 'technical_validation': summary,
                    'protected_groups': ['trajectory:' + trajectory, 'initial-family:' + family],
                    'scope': 'whole accepted-state trajectory; transport-only; no training qualification'}
        # Ensure metadata is safe for the existing UTF-8 JSON/history owner.
        encode(metadata).encode('utf-8')
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w', zipfile.ZIP_STORED) as archive:
            archive.writestr(zipfile.ZipInfo('run.json'), run_raw)
            archive.writestr(zipfile.ZipInfo('frames.jsonl'), frames_raw)
        return {'bundle': stream.getvalue(), 'metadata': metadata}
    except (ValueError, KeyError, TypeError, UnicodeError, OverflowError) as error:
        raise WorkbenchError('Invalid completed Rheon sequence: ' + str(error)) from error


def admit(workbench, body):
    if set(body) - {'files', 'name', 'groups', 'parents', 'rights'} or type(body.get('files')) is not dict or set(body['files']) != {'run.json', 'frames.jsonl'}:
        raise WorkbenchError('Supply exactly run.json and frames.jsonl plus sequence metadata.')
    run_raw = decode_file(body['files']['run.json'], contract.MANIFEST_LIMIT, 'run.json')
    frames_raw = decode_file(body['files']['frames.jsonl'], contract.FRAMES_LIMIT, 'frames.jsonl')
    return workbench.sequences.admit(prepare(run_raw, frames_raw), body)
