"""Rheon adapter pinned to draft PR 20 fee7b4a; validation is not human review."""
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
CONTROLS_SOURCE_COMMIT = '2209012bc5f902693d0f695ec1c2d854126af317'
CONTROLS_ADAPTER = {'repository': 'MrScripty/Rheon', 'contract_commit': CONTROLS_SOURCE_COMMIT,
    'status': 'source-pinned merged producer-v2 contract; validation is not authenticity certification',
    'validator_path': 'tools/import_dense3d_controls.py',
    'validator_sha256': '215f98241e01a6fb099b5b1b8789e00c951988e1382438afbd45cfbb7e1c4c43'}
MAX_REQUEST = 3 * 1024 * 1024
V1_FILES = {'run.json', 'frames.jsonl'}
V2_FILES = V1_FILES | {'controls.json'}


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
    if controls_raw is not None and not 0 < len(controls_raw) <= controls_contract.CONTROLS_LIMIT:
        raise WorkbenchError('Rheon controls exceed their byte bound.')
    try:
        manifest = contract.parse(run_raw)
        version = manifest.get('version') if type(manifest) is dict else None
        if type(version) is not int or version not in (1, 2):
            raise ValueError('Only explicit Rheon versions 1 and 2 are supported.')
        if (version == 2) != (controls_raw is not None):
            raise ValueError('Version 1 requires exactly two files; version 2 requires controls.json as its third file.')
        reader = controls_contract if version == 2 else contract
        # Unmodified, source-pinned validator sees only bounded, server-owned files.
        with tempfile.TemporaryDirectory(prefix='tuldok-rheon-') as directory:
            path = Path(directory)
            (path / 'run.json').write_bytes(run_raw)
            (path / 'frames.jsonl').write_bytes(frames_raw)
            if controls_raw is not None:
                (path / 'controls.json').write_bytes(controls_raw)
            summary = reader.verify(path)
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
        identity = run_raw + b'\0' + frames_raw
        if controls_raw is not None:
            identity += b'\0' + controls_raw
        trajectory = hashlib.sha256(identity).hexdigest()
        metadata = {'adapter': ADAPTER, 'manifest': manifest, 'run_sha256': run_hash,
                    'frame_index': index, 'technical_validation': summary,
                    'protected_groups': ['trajectory:' + trajectory, 'initial-family:' + family],
                    'scope': 'whole accepted-state trajectory; transport-only; no training qualification'}
        if controls_raw is not None:
            controls = contract.parse(controls_raw)
            metadata.update(adapter=CONTROLS_ADAPTER, controls_sha256=manifest['controls_sha256'],
                            controls_bytes=len(controls_raw),
                            controls_summary={**{key: controls[key] for key in
                                ('schema', 'version', 'axis_order', 'side_order', 'speed_sign', 'units', 'provenance', 'intervals')},
                                'interval_count': len(controls['intervals'])})
        # Ensure metadata is safe for the existing UTF-8 JSON/history owner.
        encode(metadata).encode('utf-8')
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w', zipfile.ZIP_STORED) as archive:
            archive.writestr(zipfile.ZipInfo('run.json'), run_raw)
            archive.writestr(zipfile.ZipInfo('frames.jsonl'), frames_raw)
            if controls_raw is not None:
                archive.writestr(zipfile.ZipInfo('controls.json'), controls_raw)
        return {'bundle': stream.getvalue(), 'metadata': metadata}
    except (ValueError, KeyError, TypeError, UnicodeError, OverflowError, RecursionError) as error:
        raise WorkbenchError('Invalid completed Rheon sequence: ' + str(error)) from error


def prepare_files(files):
    """Decode bounded HTTP files; manifest version chooses the exact supported set."""
    if type(files) is not dict or set(files) not in (V1_FILES, V2_FILES):
        raise WorkbenchError('Supply run.json / frames.jsonl, plus controls.json only for version 2.')
    run_raw = decode_file(files['run.json'], contract.MANIFEST_LIMIT, 'run.json')
    frames_raw = decode_file(files['frames.jsonl'], contract.FRAMES_LIMIT, 'frames.jsonl')
    controls_raw = decode_file(files['controls.json'], controls_contract.CONTROLS_LIMIT, 'controls.json') if 'controls.json' in files else None
    return prepare(run_raw, frames_raw) if controls_raw is None else prepare(run_raw, frames_raw, controls_raw)


def admit(workbench, body):
    workbench.access.require('edit', 'rheon_sequences.admit')
    if type(body) is not dict or set(body) - {'files', 'name', 'groups', 'parents', 'rights'}:
        raise WorkbenchError('Supply supported sequence files and metadata.')
    return workbench.sequences.admit(prepare_files(body.get('files')), body)
