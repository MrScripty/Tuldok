"""Lossless bounded structured-grid fields; no producer execution or physics policy."""
from access import authorized
import ast
import base64
import binascii
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import struct
import uuid
import zipfile

from workbench import WorkbenchError, encode, strings, text_value, timestamp

FORMAT = 'scientific_field_sequence_v1'
TASK = 'field_sequence_fields'
BUNDLE_LIMIT = 40 * 1024 * 1024
MAX_BUNDLE_BYTES = BUNDLE_LIMIT
MANIFEST_LIMIT = 1024 * 1024
HEADER_LIMIT = 4096
TOKEN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$')
HASH = re.compile(r'^[a-f0-9]{64}$')
TIME = re.compile(r'^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$')
CENTERINGS = ('cell', 'face_x', 'face_y', 'face_z')
SCOPE = 'Whole stored field sequence; first observed state and declared family do not establish independent trajectories or scientific validity.'


def invalid(message, code='invalid', status=400):
    raise WorkbenchError('Scientific fields: ' + message, code, status)


def exact(value, keys, label):
    if type(value) is not dict or set(value) != set(keys):
        invalid(label + ' fields differ from schema 1.')


def text(value, maximum, label):
    if (type(value) is not str or not value.strip() or len(value) > maximum or
            any(ord(char) < 32 or 127 <= ord(char) <= 159 or 0xD800 <= ord(char) <= 0xDFFF for char in value)):
        invalid(label + ' must be bounded nonempty Unicode text without controls.')
    return value


def path_name(value):
    text(value, 160, 'Member path')
    if ('\\' in value or value.startswith('/') or len(value.split('/')) > 8
            or any(part in ('', '.', '..') for part in value.split('/'))):
        invalid('Member paths must be relative without traversal or empty components.')
    return value


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                invalid('Duplicate JSON key.')
            result[key] = value
        return result
    def constant(_value):
        invalid('Nonfinite JSON constants are unsupported.')
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant)
        pending = [(value, 0)]
        while pending:
            item, depth = pending.pop()
            if depth > 16:
                invalid('Manifest nesting exceeds its schema bound.')
            if type(item) is dict:
                pending.extend((child, depth + 1) for child in item.values())
            elif type(item) is list:
                pending.extend((child, depth + 1) for child in item)
        return value
    except (ValueError, UnicodeError, RecursionError):
        invalid('Manifest must be bounded UTF-8 JSON with unique fields and finite values.')


def finite(value, *, positive=False):
    return (type(value) in (int, float) and abs(value) <= 1e12 and math.isfinite(value)
            and (not positive or value > 0))


def grid_contract(grid):
    exact(grid, ('shape_xyz', 'origin_xyz', 'spacing_xyz', 'orientation', 'units'), 'Grid')
    shape = grid['shape_xyz']
    if type(shape) is not list or len(shape) != 3 or any(type(n) is not int or not 1 <= n <= 128 for n in shape):
        invalid('Grid dimensions must be three integers from 1 to 128.')
    for key in ('origin_xyz', 'spacing_xyz'):
        values = grid[key]
        if type(values) is not list or len(values) != 3 or any(not finite(n, positive=key=='spacing_xyz') for n in values):
            invalid('Grid origin/spacing must be bounded finite XYZ values with positive spacing.')
    orientation = grid['orientation']
    if (type(orientation) is not list or len(orientation) != 3 or
            any(type(row) is not list or len(row) != 3 or any(not finite(n) for n in row) for row in orientation)):
        invalid('Orientation must be a finite 3 by 3 matrix.')
    for left in range(3):
        for right in range(3):
            dot = math.fsum(orientation[row][left] * orientation[row][right] for row in range(3))
            if abs(dot - (1 if left == right else 0)) > 1e-9:
                invalid('Orientation must be orthonormal; shear and deformation are unsupported.')
    text(grid['units'], 80, 'Grid units')


def shape_for(grid, field):
    xyz = list(grid['shape_xyz'])
    if field['centering'] != 'cell':
        xyz['xyz'.index(field['centering'][-1])] += 1
    return list(reversed(xyz))


def npy_payload(raw, field, grid):
    """Validate literal headers before computing shapes; retain every payload bit."""
    if len(raw) < 10 or raw[:8] != b'\x93NUMPY\x01\x00':
        invalid('Only NPY 1.0 members are supported.', 'unsupported')
    size = struct.unpack_from('<H', raw, 8)[0]
    end = 10 + size
    if not 0 < size <= HEADER_LIMIT or end > len(raw) or end % 16 or raw[end-1:end] != b'\n':
        invalid('NPY header length, alignment or terminator is invalid.')
    try:
        tree = ast.parse(raw[10:end].decode('ascii').strip(), mode='eval').body
        if not isinstance(tree, ast.Dict) or len(tree.keys) != 3:
            invalid('NPY header requires exactly three literal fields.')
        keys = [key.value if isinstance(key, ast.Constant) and type(key.value) is str else None for key in tree.keys]
        if set(keys) != {'descr', 'fortran_order', 'shape'}:
            invalid('NPY header fields must be unique descr, fortran_order and shape.')
        nodes = dict(zip(keys, tree.values))
        if (not isinstance(nodes['descr'], ast.Constant) or type(nodes['descr'].value) is not str or
                not isinstance(nodes['fortran_order'], ast.Constant) or nodes['fortran_order'].value is not False or
                not isinstance(nodes['shape'], ast.Tuple) or len(nodes['shape'].elts) != 3 or
                any(not isinstance(node, ast.Constant) or type(node.value) is not int for node in nodes['shape'].elts)):
            invalid('NPY values must be literal dtype, false C-order flag and three integer dimensions.')
        dtype = nodes['descr'].value
        shape = [node.value for node in nodes['shape'].elts]
    except (SyntaxError, ValueError, UnicodeError, RecursionError):
        invalid('Malformed or unsupported NPY literal header.')
    if dtype != field['dtype'] or shape != shape_for(grid, field):
        invalid('NPY dtype or shape disagrees with declared field placement.')
    width = 4 if dtype == '<f4' else 8
    if len(raw) - end != math.prod(shape) * width:
        invalid('NPY payload length differs from its shape; truncated/trailing bytes are unsupported.')
    payload = memoryview(raw)[end:]
    if any(not math.isfinite(item[0]) for item in struct.iter_unpack('<f' if width == 4 else '<d', payload)):
        invalid('Field arrays must contain finite values.')
    return payload, shape


def manifest_contract(value):
    exact(value, ('format','schema_version','grid','time_units','fields','frames','family','sources','provenance'), 'Manifest')
    if value['format'] != FORMAT or type(value['schema_version']) is not int or value['schema_version'] != 1:
        invalid('Only scientific_field_sequence_v1 schema 1 is supported.', 'unsupported')
    grid_contract(value['grid'])
    text(value['time_units'], 80, 'Time units')
    fields = value['fields']
    if type(fields) is not list or not 1 <= len(fields) <= 16:
        invalid('Choose 1 to 16 named fields.')
    by_id = {}
    for field in fields:
        exact(field, ('id','label','dtype','centering','units','stage'), 'Field')
        key = field['id']
        if type(key) is not str or not TOKEN.fullmatch(key) or key in by_id:
            invalid('Field IDs must be bounded unique tokens.')
        for name, limit in (('label',160),('units',80),('stage',160)):
            text(field[name], limit, 'Field ' + name)
        if field['dtype'] not in ('<f4','<f8') or field['centering'] not in CENTERINGS:
            invalid('Fields require little-endian float32/float64 and cell or axis-face placement.', 'unsupported')
        by_id[key] = field
    frames = value['frames']
    if type(frames) is not list or not 1 <= len(frames) <= 256:
        invalid('Choose 1 to 256 complete stored frames.')
    previous = None
    refs = []
    for frame in frames:
        exact(frame, ('time','arrays'), 'Frame')
        label = text(frame['time'], 64, 'Frame time')
        if not TIME.fullmatch(label):
            invalid('Frame time must be a decimal string.')
        try:
            time = Decimal(label)
            if not time.is_finite() or time.copy_abs() > Decimal('1e12') or (previous is not None and time <= previous):
                invalid('Frame times must be finite, bounded and strictly increasing.')
        except InvalidOperation:
            invalid('Invalid decimal frame time.')
        previous = time
        arrays = frame['arrays']
        if type(arrays) is not list or len(arrays) != len(fields):
            invalid('Every frame requires exactly one array per field.')
        seen = set()
        for array in arrays:
            exact(array, ('field','path','bytes','sha256'), 'Array')
            if type(array['field']) is not str or array['field'] not in by_id or array['field'] in seen:
                invalid('Frame field references must be complete and unique.')
            seen.add(array['field']); refs.append(array)
    exact(value['family'], ('namespace','id'), 'Family')
    for name in ('namespace','id'):
        text(value['family'][name], 160, 'Declared family ' + name)
    exact(value['provenance'], ('producer','source_id'), 'Provenance')
    text(value['provenance']['producer'], 160, 'Producer')
    text(value['provenance']['source_id'], 256, 'Source identity')
    sources = value['sources']
    if type(sources) is not list or len(sources) > 16:
        invalid('At most 16 opaque original source files are supported.')
    for source in sources:
        exact(source, ('path','bytes','sha256','description'), 'Original source')
        text(source['description'], 160, 'Original source description')
        refs.append(source)
    paths = {'manifest.json'}
    for ref in refs:
        name = path_name(ref['path'])
        if name in paths:
            invalid('Every array/source path must be unique.')
        paths.add(name)
        if type(ref['bytes']) is not int or not 0 < ref['bytes'] <= BUNDLE_LIMIT:
            invalid('Declared file size must be a bounded positive integer.')
        if type(ref['sha256']) is not str or not HASH.fullmatch(ref['sha256']):
            invalid('Declared file hash must be lowercase SHA256.')
    return by_id, refs


def parse_bundle(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= BUNDLE_LIMIT:
        invalid('Select an original bundle of at most 40 MiB.', 'too_large')
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            names = archive.namelist()
            if (not entries or len(entries) > 4113 or len(names) != len(set(names)) or
                    raw[:4] != b'PK\x03\x04' or raw[-22:-18] != b'PK\x05\x06' or archive.comment):
                invalid('Bundle must be a bounded ZIP without duplicate entries, preamble, comment or trailing bytes.')
            for item in entries:
                path_name(item.filename)
                if (item.compress_type != zipfile.ZIP_STORED or item.flag_bits & 1 or item.file_size != item.compress_size or
                        stat.S_IFMT(item.external_attr >> 16) not in (0, stat.S_IFREG)):
                    invalid('Only stored, unencrypted regular ZIP files are supported.')
            if sum(item.file_size for item in entries) > BUNDLE_LIMIT or 'manifest.json' not in names:
                invalid('Bundle expanded size or manifest is invalid.')
            if not 0 < archive.getinfo('manifest.json').file_size <= MANIFEST_LIMIT:
                invalid('Manifest exceeds its 1 MiB bound.')
            value = decode(archive.read('manifest.json'))
            fields, refs = manifest_contract(value)
            if set(names) != {'manifest.json'} | {ref['path'] for ref in refs}:
                invalid('Bundle files differ from the exact declared inventory.')
            for ref in refs:
                if archive.getinfo(ref['path']).file_size != ref['bytes']:
                    invalid('Declared file size differs from the archived member.')
                contents = archive.read(ref['path'])
                if hashlib.sha256(contents).hexdigest() != ref['sha256']:
                    invalid('Archived bytes differ from the declared SHA256.')
            first_state = []
            for index, frame in enumerate(value['frames']):
                for array in frame['arrays']:
                    field = fields[array['field']]
                    payload, _shape = npy_payload(archive.read(array['path']), field, value['grid'])
                    if index == 0:
                        first_state.append((field['centering'], field['dtype'], hashlib.sha256(payload).hexdigest()))
            # Numeric JSON spellings and signed zero cannot separate identical grids.
            geometry = dict(value['grid'])
            for key in ('origin_xyz','spacing_xyz'):
                geometry[key] = [float(n) if n else 0.0 for n in geometry[key]]
            geometry['orientation'] = [[float(n) if n else 0.0 for n in row] for row in geometry['orientation']]
            state_sha = hashlib.sha256(encode({'grid':geometry,'arrays':sorted(first_state)}).encode()).hexdigest()
            source_sha = hashlib.sha256(raw).hexdigest()
            family_sha = hashlib.sha256(encode(value['family']).encode()).hexdigest()
            return {'schema_version':1,'format':FORMAT,'manifest':value,'frame_count':len(value['frames']),
                    'field_count':len(value['fields']),'source_bytes':len(raw),'first_observed_state_sha256':state_sha,
                    'protected_groups':['field-sequence-source:'+source_sha,'field-sequence-state:'+state_sha,
                                        'field-sequence-family:'+family_sha], 'scope':SCOPE}
    except (zipfile.BadZipFile, OSError, KeyError, RuntimeError, OverflowError, RecursionError, struct.error) as error:
        invalid('Malformed scientific bundle: ' + type(error).__name__)


def validate_source(method, source, raw):
    """Validate retained source declarations against captured scientific bytes.

    Run evidence establishes internal custody relationships. It does not prove
    historical database authority or reproduce the full approved material.
    """
    digest = hashlib.sha256(raw).hexdigest()
    if method == 'project_data_import':
        exact(source, ('project_id', 'manifest_sha256', 'reference_id', 'path', 'measured_sha256'), 'Project source')
        if type(source['project_id']) is not str or not re.fullmatch('[a-f0-9]{32}', source['project_id']):
            invalid('Invalid project source ID.')
        for key in ('manifest_sha256', 'measured_sha256'):
            if type(source[key]) is not str or not HASH.fullmatch(source[key]):
                invalid('Invalid project source hash.')
        text(source['reference_id'], 64, 'Project reference')
        text(source['path'], 512, 'Project source path')
    elif method == 'run_artifact_import':
        import recipe_process
        try:
            recipe_process.validate_artifact_source(source, digest, len(raw))
        except recipe_process.ProcessError as error:
            invalid(str(error), error.code, 409 if error.code == 'conflict' else 400)
    else:
        invalid('Unsupported scientific source method.')
    if source['measured_sha256'] != digest:
        invalid('Captured bytes differ from their source receipt.', 'conflict', 409)
    return dict(source)


class ScientificAssets:
    def __init__(self, workbench):
        self.access = workbench.access
        self.workbench = workbench
        self.path = workbench.dataset.path / 'field_sequence'

    @authorized('edit', 'scientific_fields.admit')
    def admit(self, raw, body, source):
        return self._admit(raw, body, 'project_data_import', source)

    @authorized('edit', 'scientific_fields.admit_run_artifact')
    def admit_run_artifact(self, run_id, name, expected_sha256, body):
        raw, source = self.workbench.dataset.runs.capture_artifact(run_id, name, expected_sha256)
        return self._admit(raw, body, 'run_artifact_import', source)

    def _admit(self, raw, body, method, source):
        from immutable_assets import publish_file
        if type(body) is not dict or set(body) - {'name','rights','groups','parents'}:
            invalid('Unexpected import metadata fields.')
        meta = parse_bundle(raw)
        name = text_value(body.get('name', 'Scientific field sequence'), 'Name')
        rights = text_value(body.get('rights', 'unknown'), 'Rights / permission note', 1000)
        groups = strings(body.get('groups', []), 'Protected groups', maximum=27)
        parents = strings(body.get('parents', []), 'Parent IDs')
        groups = list(dict.fromkeys(groups + meta['protected_groups']))
        source = validate_source(method, source, raw)
        digest = hashlib.sha256(raw).hexdigest()
        source_key = 'project_source' if method == 'project_data_import' else 'run_source'
        origin = {'method':method,'rights':rights,'field_sequence':meta,
                  'source_sha256':digest,source_key:source}
        record_id, created = uuid.uuid4().hex, timestamp()
        w = self.workbench
        with w.lock, w.db.transaction():
            for parent in parents:
                w._get(parent)
            if w.db.execute("SELECT 1 FROM workbench_records WHERE kind='field_sequence' AND content_hash=%s", (digest,)).fetchone():
                invalid('This exact scientific bundle already exists.', 'conflict', 409)
            with publish_file(w.db, self.path / record_id, 'source.zip', raw):
                w.db.execute('INSERT INTO workbench_records VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (record_id,'field_sequence',name,None,None,digest,None,encode(groups),encode(parents),
                     encode(origin),TASK,None,'draft',1,created,created))
                record = w._get(record_id)
                w._history(record)
                self.access.audit('scientific_fields.admit', record_id, {'revision': record['revision'], 'source_sha256': digest})
        return record

    def _capture(self, record_id):
        if type(record_id) is not str or not re.fullmatch('[a-f0-9]{32}', record_id):
            invalid('Invalid scientific record identity.')
        try:
            path = self.path / record_id / 'source.zip'
            if path.is_symlink() or path.parent.is_symlink():
                invalid('Stored bundle must be a regular owned file.', 'unavailable', 409)
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, 'rb') as handle:
                before = os.fstat(handle.fileno())
                if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= BUNDLE_LIMIT:
                    invalid('Stored bundle must be a bounded regular file.', 'unavailable', 409)
                raw = handle.read(BUNDLE_LIMIT + 1)
                after = os.fstat(handle.fileno())
                if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                    invalid('Stored bundle changed during capture.', 'conflict', 409)
            if not 0 < len(raw) <= BUNDLE_LIMIT:
                invalid('Stored bundle exceeds its byte bound.', 'unavailable', 409)
            return raw
        except OSError:
            invalid('Original scientific bundle is unavailable.', 'unavailable', 404)

    @authorized('inspect', 'scientific_fields.metadata')
    def metadata(self, record_id, provenance):
        meta = provenance.get('field_sequence')
        if type(meta) is not dict or meta.get('schema_version') != 1 or meta.get('format') != FORMAT:
            invalid('Stored scientific metadata is unavailable.', 'unavailable', 409)
        try:
            raw = self._capture(record_id)
            available = hashlib.sha256(raw).hexdigest() == provenance.get('source_sha256') and len(raw) == meta.get('source_bytes')
        except WorkbenchError:
            available = False
        return dict(meta), available

    @authorized('inspect', 'scientific_fields.asset', target=lambda record: record.get('id') if isinstance(record, dict) else None)
    def asset(self, record):
        raw = self._capture(record['id'])
        if hashlib.sha256(raw).hexdigest() != record['content_hash'] or encode(parse_bundle(raw)) != encode(record['field_sequence']):
            invalid('Stored scientific bytes or metadata changed outside Tuldok.', 'conflict', 409)
        return raw, 'application/zip'

    @authorized('inspect', 'scientific_fields.inspect')
    def inspect(self, record_id, frame=0, field=None, axis='z', index=0):
        w = self.workbench
        with w.lock:
            record = w._get(record_id)
            if record['kind'] != 'field_sequence':
                invalid('Inspection requires a scientific field sequence.')
            raw, _ = self.asset(record)
        meta = record['field_sequence']['manifest']
        if type(frame) is not int or not 0 <= frame < len(meta['frames']):
            invalid('Choose an existing frame index.')
        field = meta['fields'][0]['id'] if field is None else field
        definition = next((item for item in meta['fields'] if item['id'] == field), None)
        if definition is None or axis not in ('x','y','z') or type(index) is not int:
            invalid('Choose an existing field, axis and integer slice index.')
        array = next(item for item in meta['frames'][frame]['arrays'] if item['field'] == field)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            payload, shape = npy_payload(archive.read(array['path']), definition, meta['grid'])
        xyz = list(reversed(shape)); fixed = 'xyz'.index(axis)
        if not 0 <= index < xyz[fixed]:
            invalid('Slice index lies outside the field dimensions.')
        row_axis, column_axis = {'z':('y','x'),'y':('z','x'),'x':('z','y')}[axis]
        row_index, column_index = 'xyz'.index(row_axis), 'xyz'.index(column_axis)
        width = 4 if definition['dtype'] == '<f4' else 8
        fmt = '<f' if width == 4 else '<d'
        coordinates = [0,0,0]; coordinates[fixed] = index
        values = []
        for row in range(xyz[row_index]):
            line = []
            coordinates[row_index] = row
            for column in range(xyz[column_index]):
                coordinates[column_index] = column
                x,y,z = coordinates
                offset = (x + xyz[0]*(y + xyz[1]*z))*width
                line.append(struct.unpack_from(fmt, payload, offset)[0])
            values.append(line)
        grid = meta['grid']; offset = [.5,.5,.5]
        if definition['centering'] != 'cell':
            offset['xyz'.index(definition['centering'][-1])] = 0.0
        sample = offset[:]; sample[fixed] += index
        physical = [grid['origin_xyz'][i] + math.fsum(grid['orientation'][i][j]*grid['spacing_xyz'][j]*sample[j] for j in range(3)) for i in range(3)]
        step = lambda component: [grid['orientation'][i][component]*grid['spacing_xyz'][component] for i in range(3)]
        return {'id':record_id,'content_hash':record['content_hash'],'frame':frame,'field':field,
                'shape_zyx':shape,'axis':axis,'index':index,'values':values,'row_axis':row_axis,'column_axis':column_axis,
                'physical_origin':physical,'physical_row_step':step(row_index),'physical_column_step':step(column_index),
                'time':meta['frames'][frame]['time'],'time_units':meta['time_units'],'grid':grid,
                **{key:definition[key] for key in ('units','stage','centering','dtype')}}
