"""Declarative trusted-local recipes: bounded capture, never import or execute."""
import base64
import hashlib
import os
from pathlib import Path
import re
import stat
import struct

from projects import closed, decode, relative_path
from workbench import WorkbenchError, encode

NAME = re.compile(r'[A-Za-z][A-Za-z0-9_-]{0,63}')
SHA = re.compile(r'[a-f0-9]{64}')
MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_CAPTURE_BYTES = 64 * 1024 * 1024
MAX_FILES = 128
RUNTIME_LIMIT = 512 * 1024 * 1024
TYPES = ('input', 'execute', 'output')
PORTS = {'input': (None, 'data'), 'execute': ('data', 'artifacts'), 'output': ('artifacts', None)}
TRUST = 'Trusted local code; filesystem and network are not sandboxed. Runtime installation must remain immutable for the attempt.'
CPU_PROFILE = 'captured_cpu_python_v1'
CPU_DESCRIPTOR = 'runtime-bootstrap/snapshot.json'
CPU_BOOTSTRAP = 'runtime-bootstrap/recipe_process.py'
HOST_NAMES = ('recipe_contract.py', 'projects.py', 'pipeline.py', 'recipe_process.py')
IMPORTED_HOST_FILES = {name: hashlib.sha256((Path(__file__).resolve().parent/name).read_bytes()).hexdigest() for name in HOST_NAMES}


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def file_digest(raw):
    return hashlib.sha256(raw).hexdigest()


def bounded_int(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise WorkbenchError(label + ' is outside its supported integer bounds.')
    return value


def named(value):
    if not isinstance(value, str) or not NAME.fullmatch(value):
        raise WorkbenchError('Recipe names must use bounded letters, digits, underscore or hyphen.')
    return value


def decode_definition(raw):
    if len(raw) > 65536:
        raise WorkbenchError('Recipe definition exceeds 64 KiB.')
    value = decode(raw)
    closed(value, ('schema_version', 'format', 'id', 'name', 'version', 'runtime', 'sources', 'entrypoint',
                   'arguments', 'parameters', 'inputs', 'outputs', 'environment', 'resources'), ('native_sources','runtime_snapshot_sha256'))
    if type(value['schema_version']) is not int or value['schema_version'] != 1 or value['format'] != 'external_recipe_v1':
        raise WorkbenchError('Only external_recipe_v1 is supported.', 'unsupported', 400)
    named(value['id'])
    bounded_int(value['version'], 1, 1, 'Recipe version')
    if not isinstance(value['name'], str) or not 1 <= len(value['name']) <= 120:
        raise WorkbenchError('Supply a bounded recipe name.')
    if value['runtime'] not in ('system_python', CPU_PROFILE):
        raise WorkbenchError('Unsupported recipe runtime profile.', 'unsupported', 400)
    if value['runtime'] == CPU_PROFILE:
        snapshot = value.get('runtime_snapshot_sha256')
        if not isinstance(snapshot, str) or not SHA.fullmatch(snapshot):
            raise WorkbenchError('Captured CPU recipes require a runtime snapshot SHA256.')
    elif 'runtime_snapshot_sha256' in value:
        raise WorkbenchError('System Python recipes cannot select a CPU snapshot.')
    sources = value['sources']
    if not isinstance(sources, list) or not 1 <= len(sources) <= 64:
        raise WorkbenchError('Declare 1–64 source files.')
    paths = set()
    for source in sources:
        closed(source, ('path', 'sha256'))
        path = relative_path(source['path'])
        if path in paths or not isinstance(source['sha256'], str) or not SHA.fullmatch(source['sha256']):
            raise WorkbenchError('Source paths must be unique with explicit SHA256 hashes.')
        paths.add(path)
    if not isinstance(value['entrypoint'], str) or value['entrypoint'] not in paths:
        raise WorkbenchError('Entrypoint must be one declared captured source.')
    if 'native_sources' in value:
        natives = value['native_sources']
        if not isinstance(natives,list) or not 1 <= len(natives) <= 8 or any(not isinstance(item,str) or item not in paths for item in natives) or len(set(natives)) != len(natives):
            raise WorkbenchError('Native sources must name 1–8 unique declared sources.')
    if not isinstance(value['parameters'], dict) or len(value['parameters']) > 32:
        raise WorkbenchError('Declare at most 32 typed parameters.')
    for key, rule in value['parameters'].items():
        named(key)
        closed(rule, ('type', 'default'), ('min', 'max', 'enum', 'max_length'))
        kind = rule['type']
        if kind not in ('integer', 'number', 'boolean', 'string'):
            raise WorkbenchError('Unsupported parameter type.')
        allowed = {'type', 'default'} | ({'min', 'max'} if kind in ('integer', 'number') else {'max_length', 'enum'} if kind == 'string' else set())
        if set(rule) - allowed:
            raise WorkbenchError('Parameter constraints differ from its declared type.')
        if kind in ('integer', 'number'):
            import math
            if not all(type(rule.get(k)) in (int, float) and math.isfinite(rule[k]) for k in ('min', 'max')) or rule['min'] > rule['max']:
                raise WorkbenchError('Numeric parameters require finite ordered bounds.')
        if kind == 'string':
            bounded_int(rule.get('max_length'), 1, 1024, 'String length')
            if 'enum' in rule and (not isinstance(rule['enum'], list) or not 1 <= len(rule['enum']) <= 64 or any(not isinstance(x, str) for x in rule['enum'])):
                raise WorkbenchError('String choices must be a bounded list.')
    validate_parameters(value, {})
    if not isinstance(value['inputs'], dict) or len(value['inputs']) > 32:
        raise WorkbenchError('Declare at most 32 named inputs.')
    for key, rule in value['inputs'].items():
        named(key); closed(rule, ('max_bytes',))
        bounded_int(rule['max_bytes'], 1, 40 * 1024 * 1024, 'Input bytes')
    argument_limit = 56 if value['runtime'] == CPU_PROFILE else 59
    if not isinstance(value['arguments'], list) or len(value['arguments']) > argument_limit:
        raise WorkbenchError('Recipe arguments exceed the runtime argument bound.')
    for token in value['arguments']:
        if not isinstance(token, dict) or len(token) != 1:
            raise WorkbenchError('Arguments are single typed tokens.')
        kind, arg = next(iter(token.items()))
        if kind == 'literal':
            if not isinstance(arg, str) or len(arg) > 1024 or '\0' in arg:
                raise WorkbenchError('Literal argument is invalid.')
        elif kind == 'parameter':
            if not isinstance(arg, str) or arg not in value['parameters']: raise WorkbenchError('Unknown parameter argument.')
        elif kind == 'input':
            if not isinstance(arg, str) or arg not in value['inputs']: raise WorkbenchError('Unknown input argument.')
        elif kind == 'source':
            if not isinstance(arg, str) or arg not in paths: raise WorkbenchError('Unknown source argument.')
        elif kind == 'native_policy':
            if not isinstance(arg,str) or arg not in value.get('native_sources',[]): raise WorkbenchError('Native policy argument must select a declared native source.')
        elif kind != 'output_dir' or arg is not True:
            raise WorkbenchError('Unsupported argument token.')
    outputs = value['outputs']
    if not isinstance(outputs, list) or not 1 <= len(outputs) <= 32:
        raise WorkbenchError('Declare 1–32 output files.')
    seen = set()
    for output in outputs:
        closed(output, ('path', 'role', 'max_bytes', 'required'))
        path = relative_path(output['path']); named(output['role'])
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,119}', path) or path in ('artifact-manifest.json', 'custody-receipt.json'):
            raise WorkbenchError('Output must use an unreserved flat filename.')
        if path in seen or type(output['required']) is not bool: raise WorkbenchError('Invalid output contract.')
        seen.add(path)
        bounded_int(output['max_bytes'], 1, MAX_CAPTURE_BYTES, 'Output bytes')
    if value['environment'] != {}:
        raise WorkbenchError('Initial runtime admits no project environment overrides.', 'unsupported', 400)
    closed(value['resources'], ('wall_seconds', 'max_output_bytes'))
    bounded_int(value['resources']['wall_seconds'], 1, 600, 'Wall seconds')
    bounded_int(value['resources']['max_output_bytes'], 1, MAX_CAPTURE_BYTES, 'Output bytes')
    return value


def validate_parameters(definition, values):
    import math
    rules = definition['parameters']
    if not isinstance(values, dict) or set(values) - set(rules):
        raise WorkbenchError('Unknown recipe parameters.')
    result = {}
    for key, rule in rules.items():
        value = values.get(key, rule['default']); kind = rule['type']
        valid = ((type(value) is bool) if kind == 'boolean' else
                 (type(value) is int and rule['min'] <= value <= rule['max']) if kind == 'integer' else
                 (type(value) in (int, float) and math.isfinite(value) and rule['min'] <= value <= rule['max']) if kind == 'number' else
                 (isinstance(value, str) and len(value) <= rule['max_length'] and '\0' not in value and ('enum' not in rule or value in rule['enum'])))
        if not valid: raise WorkbenchError('Invalid value for parameter ' + key + '.')
        result[key] = value
    return result


def _elf_dependencies(raw):
    """Read ELF64 little-endian dynamic names without executing loader discovery."""
    if raw[:4] != b'\x7fELF': return []
    if raw[4:6] != b'\x02\x01': raise WorkbenchError('Runtime ELF layout is unsupported.')
    offset = struct.unpack_from('<Q', raw, 32)[0]
    size, count = struct.unpack_from('<HH', raw, 54)
    segments = [struct.unpack_from('<IIQQQQQQ', raw, offset + i * size) for i in range(count)]
    needed, strings, length, result = [], None, None, []
    for kind, _, pos, _va, _, n, _, _ in segments:
        if kind == 3: result.append(raw[pos:pos+n].rstrip(b'\0').decode())
        if kind == 2:
            for at in range(pos, pos+n, 16):
                tag, val = struct.unpack_from('<QQ', raw, at)
                if tag == 0: break
                if tag == 1: needed.append(val)
                if tag == 5: strings = val
                if tag == 10: length = val
    if needed:
        for kind, _, pos, va, _, n, _, _ in segments:
            if kind == 1 and strings is not None and va <= strings < va+n:
                base = pos + strings-va
                for at in needed:
                    if length is None or at >= length: raise WorkbenchError('Invalid runtime dynamic names.')
                    end = raw.find(b'\0', base+at, base+length)
                    if end < 0: raise WorkbenchError('Invalid runtime dynamic name.')
                    result.append(raw[base+at:end].decode())
                break
        else: raise WorkbenchError('Missing runtime string table.')
    return result


def runtime_identity(profile=None):
    """Finite trusted installation closure; no process launch or project discovery."""
    profile = profile or {'executable': '/usr/bin/python3', 'trusted_install_owner_uid': os.stat('/usr').st_uid}
    closed(profile, ('executable', 'trusted_install_owner_uid'))
    uid = profile['trusted_install_owner_uid']
    if type(uid) is not int or uid == os.getuid() or uid != os.stat('/usr').st_uid:
        raise WorkbenchError('Runtime installation owner is unqualified.', 'unsupported', 409)
    executable = Path(profile['executable']).resolve(strict=True)
    if executable.parent != Path('/usr/bin') or not re.fullmatch(r'python3\.\d+', executable.name):
        raise WorkbenchError('Runtime must be the configured system Python installation.', 'unsupported', 409)
    library = Path('/usr/lib') / executable.name
    if not library.is_dir(): raise WorkbenchError('System Python standard library is unavailable.', 'unavailable', 409)
    pending = [executable]
    for directory, dirs, files in os.walk(library, followlinks=False):
        dirs[:] = sorted(dirs)
        if any((Path(directory)/name).is_symlink() for name in dirs):
            raise WorkbenchError('Runtime library directory symlinks are unsupported.')
        for name in sorted(files):
            pending.append(Path(directory)/name)
        if len(pending) > 10000: raise WorkbenchError('Runtime closure exceeds file bound.')
    files, total = {}, 0
    while pending:
        path = pending.pop().resolve(strict=True)
        if str(path) in files: continue
        if not (path.is_relative_to('/usr') or path == Path('/etc') / executable.name / 'sitecustomize.py'):
            raise WorkbenchError('Runtime dependency escapes trusted installation.')
        for ancestor in (path, *path.parents):
            if ancestor == Path('/'): break
            info = ancestor.stat()
            if info.st_uid != uid or info.st_mode & 0o022:
                raise WorkbenchError('Runtime installation is writable or has a different owner.', 'unsupported', 409)
            if ancestor in (Path('/usr'), Path('/etc')): break
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > 64 * 1024 * 1024:
            raise WorkbenchError('Runtime dependency is not a bounded regular file.')
        raw = path.read_bytes(); after = path.stat()
        if (info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise WorkbenchError('Runtime changed during preflight.', 'stale', 409)
        total += len(raw)
        if total > RUNTIME_LIMIT: raise WorkbenchError('Runtime closure exceeds byte bound.')
        files[str(path)] = {'bytes': len(raw), 'sha256': file_digest(raw)}
        for name in _elf_dependencies(raw):
            if name.startswith('/'):
                dependency = Path(name)
            else:
                if '/' in name: raise WorkbenchError('Runtime dependency has unsupported path.')
                dependency = next((base/name for base in (Path('/usr/lib/x86_64-linux-gnu'), Path('/usr/lib')) if (base/name).exists()), None)
                if dependency is None: raise WorkbenchError('Runtime dependency is missing: ' + name, 'unavailable', 409)
            pending.append(dependency)
    return {'profile': 'system_python', 'executable': str(executable), 'executable_sha256': files[str(executable)]['sha256'],
            'trusted_install_owner_uid': uid, 'files': dict(sorted(files.items())), 'closure_sha256': digest(files),
            'assumption': TRUST, 'flags': ['-I', '-S', '-B']}


NATIVE_POLICY = 'glibc_x86_64_no_preload_v1'
NATIVE_LIBRARY = '/usr/lib/x86_64-linux-gnu'
NATIVE_LOADER = NATIVE_LIBRARY + '/ld-linux-x86-64.so.2'
NATIVE_ARGUMENTS = ['--inhibit-cache', '--library-path', NATIVE_LIBRARY, '--glibc-hwcaps-mask', '']


def native_policy_path(source):
    return 'native-policy/' + hashlib.sha256(source.encode()).hexdigest() + '.json'


def strict_native_elf(raw, *, executable=False):
    """Closed ELF64/x86-64 dynamic dependency policy, without loader execution."""
    def fail():
        raise WorkbenchError('Native ELF is malformed or outside the qualified loader policy.', 'unsupported', 400)
    if type(raw) is not bytes or len(raw) < 64 or raw[:7] != b'\x7fELF\x02\x01\x01': fail()
    etype, machine, version = struct.unpack_from('<HHI', raw,16)
    offset = struct.unpack_from('<Q',raw,32)[0]
    ehsize, size, count = struct.unpack_from('<HHH',raw,52)
    if (etype != 3 or machine != 62 or version != 1 or ehsize != 64 or size != 56
            or not 1 <= count <= 128 or offset < 64 or offset + count*size > len(raw)): fail()
    segments = [struct.unpack_from('<IIQQQQQQ', raw, offset+i*size) for i in range(count)]
    dynamic = []; interpreter = None; loads = []; dynamic_seen = False
    for kind, _flags, pos, va, _pa, length, memory, _align in segments:
        if pos + length > len(raw) or (kind == 1 and length > memory): fail()
        if kind == 1: loads.append((pos,va,length))
        if kind == 3:
            if interpreter is not None or not 1 <= length <= 256: fail()
            value = raw[pos:pos+length]
            if value[-1:] != b'\0' or b'\0' in value[:-1]: fail()
            try: interpreter = value[:-1].decode('ascii')
            except UnicodeError: fail()
            if interpreter not in ('/lib64/ld-linux-x86-64.so.2', NATIVE_LOADER): fail()
        if kind == 2:
            if dynamic_seen or length % 16 or not 16 <= length <= 65536: fail()
            dynamic_seen = True
            terminated = False
            for at in range(pos,pos+length,16):
                tag, value = struct.unpack_from('<QQ',raw,at)
                if tag == 0:
                    terminated = True; break
                dynamic.append((tag,value))
            if not terminated: fail()
    if not loads or not dynamic or (executable and interpreter is None): fail()
    # Dynamic configuration/audit/filter mechanisms can load undeclared code.
    forbidden = {15,29,0x6ffffefa,0x6ffffefb,0x6ffffefc,0x7ffffffd,0x7fffffff}
    if any(tag in forbidden for tag,_value in dynamic): fail()
    tables = [value for tag,value in dynamic if tag == 5]
    sizes = [value for tag,value in dynamic if tag == 10]
    if len(tables) != 1 or len(sizes) != 1 or not 1 <= sizes[0] <= len(raw): fail()
    matches = [pos+tables[0]-va for pos,va,length in loads if va <= tables[0] and tables[0]+sizes[0] <= va+length]
    if len(matches) != 1: fail()
    base = matches[0]; needed = []
    for tag,value in dynamic:
        if tag != 1: continue
        if value >= sizes[0]: fail()
        end = raw.find(b'\0',base+value,base+sizes[0])
        if end < 0: fail()
        try: name = raw[base+value:end].decode('ascii')
        except UnicodeError: fail()
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.+-]{0,127}',name) or name in needed: fail()
        needed.append(name)
    if len(needed) > 64: fail()
    return needed


def native_policies(definition, sources, runtime):
    """Capture every recursively required trusted native library into material."""
    import recipe_process
    recipe_process.verify_native_loader_policy(runtime['trusted_install_owner_uid'])
    result = {}
    for source in definition['native_sources']:
        needed = strict_native_elf(sources[source], executable=True)
        pending = [Path(NATIVE_LOADER), *(Path(NATIVE_LIBRARY)/name for name in needed)]
        files = {}
        while pending:
            path = pending.pop().resolve(strict=True)
            if str(path) in files: continue
            if path.parent != Path(NATIVE_LIBRARY) or len(files) >= 64:
                raise WorkbenchError('Native library closure escapes its finite trusted directory.')
            for ancestor in (path,*path.parents):
                if ancestor == Path('/'): break
                info = ancestor.stat()
                if info.st_uid != runtime['trusted_install_owner_uid'] or info.st_mode & 0o022:
                    raise WorkbenchError('Native runtime owner or permissions differ from trusted installation.')
                if ancestor == Path('/usr'): break
            info = path.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_SOURCE_BYTES:
                raise WorkbenchError('Native library exceeds its regular-file bound.')
            raw = path.read_bytes(); after = path.stat()
            if (info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns) != (after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):
                raise WorkbenchError('Native runtime changed during preflight.', 'stale',409)
            dependencies = strict_native_elf(raw)
            files[str(path)] = {'bytes':len(raw),'sha256':file_digest(raw)}
            pending.extend(Path(NATIVE_LIBRARY)/name for name in dependencies)
        policy = {'schema_version':1,'policy':NATIVE_POLICY,'source':{'path':source,'sha256':file_digest(sources[source])},
                  'loader':dict(path=NATIVE_LOADER,**files[NATIVE_LOADER]),'library_directory':NATIVE_LIBRARY,
                  'loader_arguments':list(NATIVE_ARGUMENTS),
                  'runtime_files':[dict(path=path,**record) for path,record in sorted(files.items())],
                  'absent_paths':['/etc/ld.so.preload']}
        result[source] = policy
        runtime['files'].update(files)
    runtime['files'] = dict(sorted(runtime['files'].items()))
    runtime['closure_sha256'] = digest(runtime['files'])
    return result


def validate_native_policies(material, definition):
    """Validate retained policy declarations with no live runtime dependency."""
    policies = material.get('native_policies')
    if 'native_sources' not in definition:
        if 'native_policies' in material: raise WorkbenchError('Unexpected native policy material.')
        return {}
    if not isinstance(policies,dict) or set(policies) != set(definition['native_sources']):
        raise WorkbenchError('Native source and policy inventories differ.')
    runtime = material.get('runtime')
    if not isinstance(runtime,dict) or not isinstance(runtime.get('files'),dict):
        raise WorkbenchError('Invalid native runtime closure.')
    sources = {item['path']:item['sha256'] for item in definition['sources']}
    generated = {}
    for source,policy in policies.items():
        closed(policy, ('schema_version','policy','source','loader','library_directory','loader_arguments','runtime_files','absent_paths'))
        if (type(policy['schema_version']) is not int or policy['schema_version'] != 1 or policy['policy'] != NATIVE_POLICY
                or policy['source'] != {'path':source,'sha256':sources[source]}
                or policy['library_directory'] != NATIVE_LIBRARY or policy['loader_arguments'] != NATIVE_ARGUMENTS
                or policy['absent_paths'] != ['/etc/ld.so.preload']):
            raise WorkbenchError('Native loader policy is inconsistent.')
        rows = policy['runtime_files']
        if not isinstance(rows,list) or not 1 <= len(rows) <= 64: raise WorkbenchError('Invalid native runtime inventory.')
        seen = set()
        for row in rows:
            closed(row, ('path','bytes','sha256'))
            path = row['path']
            if not isinstance(path,str) or str(Path(path).parent) != NATIVE_LIBRARY or path in seen:
                raise WorkbenchError('Native library path differs from policy.')
            relative_path(path[1:]); seen.add(path)
            expected = material['runtime']['files'].get(path)
            if not isinstance(expected,dict) or set(expected) != {'bytes','sha256'} or encode(row) != encode(dict(path=path,**expected)):
                raise WorkbenchError('Native library differs from retained runtime closure.')
        loader = policy['loader']
        if NATIVE_LOADER not in seen or loader != dict(path=NATIVE_LOADER,**material['runtime']['files'][NATIVE_LOADER]):
            raise WorkbenchError('Native loader identity is inconsistent.')
        generated[native_policy_path(source)] = encode(policy).encode()
    return generated


def graph_parameters(graph):
    nodes = graph['nodes']
    if len(nodes) != 3 or {n['type'] for n in nodes} != set(TYPES) or any(n['definition_version'] != 1 for n in nodes):
        raise WorkbenchError('External graphs require exactly input, execute and output version-1 nodes.')
    typed = {n['type']: n for n in nodes}
    expected = [{'from':typed[a]['id'], 'output':PORTS[a][1], 'to':typed[b]['id'], 'input':PORTS[b][0]} for a,b in zip(TYPES,TYPES[1:])]
    if sorted(map(encode, graph['edges'])) != sorted(map(encode, expected)) or typed['output']['parameters']:
        raise WorkbenchError('Connect external input → execute → output exactly once.')
    config = typed['input']['parameters']
    closed(config, ('project_id', 'recipe_id', 'expected_sha256', 'inputs'))
    return config, typed['execute']['parameters']


def inspect_recipe(projects, project_id, reference_id, expected_sha256):
    raw, receipt = projects.read_recipe_reference(project_id, reference_id, expected_sha256)
    definition = decode_definition(raw)
    return {'definition': definition, 'receipt': receipt, 'parameter_definitions': definition['parameters'],
            'inputs': definition['inputs'], 'outputs': definition['outputs'], 'runtime': definition['runtime']}


def host_identity():
    import recipe_process
    root = Path(__file__).resolve().parent
    current = {name: file_digest((root/name).read_bytes()) for name in HOST_NAMES}
    if current != IMPORTED_HOST_FILES or file_digest(recipe_process.SOURCE) != current['recipe_process.py']:
        raise WorkbenchError('Execution host changed after import. Restart before preflight or execution.', 'stale', 409)
    return current


def prepare(projects, graph, execution_sha256, profile=None):
    config, values = graph_parameters(graph)
    inspected = inspect_recipe(projects, config['project_id'], config['recipe_id'], config['expected_sha256'])
    definition = inspected['definition']; values = validate_parameters(definition, values)
    sources = projects.read_recipe_sources(config['project_id'], definition['sources'])
    if not isinstance(config['inputs'], dict) or set(config['inputs']) != set(definition['inputs']):
        raise WorkbenchError('Bind every declared input exactly once.')
    captured = {'source/' + path: raw for path, raw in sources.items()}
    inputs = {}
    for name, binding in config['inputs'].items():
        closed(binding, ('reference_id', 'expected_sha256'))
        raw, receipt = projects.read_data_reference(config['project_id'], binding['reference_id'], binding['expected_sha256'], definition['inputs'][name]['max_bytes'])
        captured['input/' + name] = raw; inputs[name] = receipt
    if len(captured) > MAX_FILES or sum(map(len,captured.values())) > MAX_CAPTURE_BYTES:
        raise WorkbenchError('Captured source and input files exceed the total bound.')
    try:
        runtime = runtime_identity(profile)
    except (OSError, struct.error, UnicodeError):
        raise WorkbenchError('Qualified system runtime cannot be safely inspected.', 'unavailable', 409) from None
    policies = None
    if 'native_sources' in definition:
        try:
            policies = native_policies(definition,sources,runtime)
        except OSError:
            raise WorkbenchError('Native runtime cannot be safely inspected.', 'unavailable',409) from None
        for source,policy in policies.items():
            captured[native_policy_path(source)] = encode(policy).encode()
        if len(captured) > MAX_FILES or sum(map(len,captured.values())) > MAX_CAPTURE_BYTES:
            raise WorkbenchError('Generated native policies exceed the capture bound.')
    cpu_snapshot = None
    if definition['runtime'] == CPU_PROFILE:
        import recipe_process
        from runtime_snapshots import RuntimeSnapshots
        cpu_snapshot = RuntimeSnapshots(projects.db, projects.access, projects.db.path).get(
            definition['runtime_snapshot_sha256'], verify=True)
        captured[CPU_DESCRIPTOR] = recipe_process.encoded(cpu_snapshot)
        captured[CPU_BOOTSTRAP] = recipe_process.SOURCE
        if len(captured) > MAX_FILES or sum(map(len,captured.values())) > MAX_CAPTURE_BYTES:
            raise WorkbenchError('Generated CPU bootstrap exceeds the capture bound.')
    host = host_identity()
    material = {'schema_version': 1, 'catalog_id': projects.db.dataset_id, 'project': inspected['receipt'], 'graph_execution_sha256': execution_sha256,
                'recipe': definition, 'parameters': values, 'inputs': inputs,
                'captures': {path: {'bytes':len(raw),'sha256':file_digest(raw)} for path,raw in sorted(captured.items())},
                'runtime': runtime, 'host_files': host, 'permissions': {'filesystem':'trusted-local', 'network':'not_isolated'},
                'environment': {'LANG':'C.UTF-8'}, 'resources': definition['resources']}
    if policies is not None: material['native_policies'] = policies
    if cpu_snapshot is not None: material['cpu_snapshot'] = cpu_snapshot
    validate_material(material)
    return {'valid':True, 'status':'valid', 'material':material, 'material_sha256':digest(material), 'validation_token':digest(material),
            'parameter_definitions':definition['parameters'], 'outputs':definition['outputs'], 'runtime':runtime,
            'graph_revision':graph['revision'], 'execution_sha256':execution_sha256}, captured


def validate_material(material):
    """Cold structural custody checks; no filesystem access or current-code comparison."""
    closed(material, ('schema_version', 'catalog_id', 'project', 'graph_execution_sha256', 'recipe',
                      'parameters', 'inputs', 'captures', 'runtime', 'host_files', 'permissions', 'environment', 'resources'), ('native_policies','cpu_snapshot'))
    if type(material['schema_version']) is not int or material['schema_version'] != 1 or not isinstance(material['catalog_id'], str) or not material['catalog_id']:
        raise WorkbenchError('Invalid execution material identity.')
    def sha(value):
        if not isinstance(value, str) or not SHA.fullmatch(value): raise WorkbenchError('Invalid material SHA256.')
    def receipt(value):
        closed(value, ('project_id', 'manifest_sha256', 'reference_id', 'path', 'measured_sha256'))
        if not isinstance(value['project_id'], str) or not re.fullmatch('[a-f0-9]{32}', value['project_id']): raise WorkbenchError('Invalid material project identity.')
        if not isinstance(value['reference_id'], str) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', value['reference_id']): raise WorkbenchError('Invalid reference identity.')
        relative_path(value['path']); sha(value['manifest_sha256']); sha(value['measured_sha256'])
    sha(material['graph_execution_sha256']); receipt(material['project'])
    definition = decode_definition(encode(material['recipe']).encode())
    if encode(validate_parameters(definition, material['parameters'])) != encode(material['parameters']):
        raise WorkbenchError('Retained parameters must include every typed value.')
    if material['resources'] != definition['resources'] or material['environment'] != {'LANG':'C.UTF-8'} or material['permissions'] != {'filesystem':'trusted-local', 'network':'not_isolated'}:
        raise WorkbenchError('Material execution policy is inconsistent.')
    if not isinstance(material['inputs'], dict) or set(material['inputs']) != set(definition['inputs']): raise WorkbenchError('Material input inventory differs.')
    expected = {'source/'+item['path']:item['sha256'] for item in definition['sources']}
    for name, item in material['inputs'].items():
        receipt(item)
        if (item['project_id'], item['manifest_sha256']) != (material['project']['project_id'], material['project']['manifest_sha256']):
            raise WorkbenchError('Input receipt belongs to another project snapshot.')
        expected['input/'+name] = item['measured_sha256']
    generated = validate_native_policies(material,definition)
    if definition['runtime'] == CPU_PROFILE:
        import recipe_process
        try:
            descriptor = recipe_process.validate_cpu_snapshot_descriptor(material.get('cpu_snapshot'))
        except recipe_process.ProcessError as error:
            raise WorkbenchError(str(error)) from None
        if descriptor['catalog_id'] != material['catalog_id'] or descriptor['manifest_sha256'] != definition['runtime_snapshot_sha256']:
            raise WorkbenchError('CPU snapshot differs from the approved catalog and recipe.')
        generated[CPU_DESCRIPTOR] = recipe_process.encoded(descriptor)
        # Historical bootstrap identity belongs to retained host material, never
        # to the currently installed helper source during a cold read.
        if not isinstance(material['host_files'],dict):
            raise WorkbenchError('Invalid retained host closure.')
        expected[CPU_BOOTSTRAP] = material['host_files'].get('recipe_process.py')
        sha(expected[CPU_BOOTSTRAP])
    elif 'cpu_snapshot' in material:
        raise WorkbenchError('System Python material cannot contain a CPU snapshot.')
    expected.update({path:file_digest(raw) for path,raw in generated.items()})
    captures = material['captures']
    if not isinstance(captures, dict) or set(captures) != set(expected) or len(captures) > MAX_FILES:
        raise WorkbenchError('Captured inventory differs from the declared source and inputs.')
    total = 0
    for path, item in captures.items():
        relative_path(path); closed(item, ('bytes','sha256')); sha(item['sha256'])
        limit = MAX_SOURCE_BYTES if path.startswith(('source/','native-policy/','runtime-bootstrap/')) else definition['inputs'][path.split('/',1)[1]]['max_bytes']
        bounded_int(item['bytes'],0,limit,'Capture bytes'); total += item['bytes']
        if path in generated and item['bytes'] != len(generated[path]): raise WorkbenchError('Generated native policy size differs.')
        if item['sha256'] != expected[path]: raise WorkbenchError('Captured digest contradicts source/input identity.')
    if total > MAX_CAPTURE_BYTES: raise WorkbenchError('Captured material exceeds byte bound.')
    runtime = material['runtime']
    closed(runtime, ('profile','executable','executable_sha256','trusted_install_owner_uid','files','closure_sha256','assumption','flags'))
    if runtime['profile'] != 'system_python' or runtime['flags'] != ['-I','-S','-B'] or not isinstance(runtime['executable'],str) or not re.fullmatch(r'/usr/bin/python3\.\d+',runtime['executable']):
        raise WorkbenchError('Retained runtime profile is unsupported.')
    bounded_int(runtime['trusted_install_owner_uid'],0,2**32-2,'Runtime owner')
    if runtime['assumption'] != TRUST: raise WorkbenchError('Runtime trust policy differs.')
    files = runtime['files']; total = 0
    if not isinstance(files,dict) or not 1 <= len(files) <= 10000: raise WorkbenchError('Invalid runtime closure size.')
    for path, item in files.items():
        if not isinstance(path,str) or not (path.startswith('/usr/') or path == '/etc/' + Path(runtime['executable']).name + '/sitecustomize.py'):
            raise WorkbenchError('Runtime path escapes the supported trusted installation.')
        relative_path(path[1:]); closed(item,('bytes','sha256')); sha(item['sha256'])
        bounded_int(item['bytes'],0,64*1024*1024,'Runtime file bytes'); total += item['bytes']
    if total > RUNTIME_LIMIT or runtime['executable'] not in files or files[runtime['executable']]['sha256'] != runtime['executable_sha256'] or digest(files) != runtime['closure_sha256']:
        raise WorkbenchError('Runtime closure identity is inconsistent.')
    if not isinstance(material['host_files'],dict) or set(material['host_files']) != set(HOST_NAMES): raise WorkbenchError('Invalid retained host closure.')
    for value in material['host_files'].values(): sha(value)
    return material


def spec_for_material(material, staging):
    """Pure reconstruction: retained approvals never depend on current source/runtime."""
    validate_material(material)
    staging = Path(staging).absolute()
    output = staging/'output'
    definition = material['recipe']; runtime = material['runtime']
    records = [dict(path=str(staging/relative), **record) for relative,record in sorted(material['captures'].items())]
    argv = [runtime['executable'], *runtime['flags'], str(staging/'source'/definition['entrypoint'])]
    if definition['runtime'] == CPU_PROFILE:
        argv = [runtime['executable'], *runtime['flags'], str(staging/CPU_BOOTSTRAP),
                '--cpu-launch', str(staging/CPU_DESCRIPTOR), str(staging/'source'/definition['entrypoint'])]
    for token in definition['arguments']:
        kind, value = next(iter(token.items()))
        if kind == 'literal': arg = value
        elif kind == 'parameter':
            item = material['parameters'][value]; arg = ('true' if item else 'false') if type(item) is bool else str(item)
        elif kind == 'input': arg = str(staging/'input'/value)
        elif kind == 'source': arg = str(staging/'source'/value)
        elif kind == 'native_policy': arg = str(staging/native_policy_path(value))
        else: arg = str(output)
        argv.append(arg)
    spec = {'schema_version':1,'argv':argv,'env':dict(material['environment']),'cwd':str(staging), 'stdin_base64':base64.b64encode(b'').decode(),
            'wall_seconds':definition['resources']['wall_seconds'], 'executable_sha256':runtime['executable_sha256'],
            'max_output_bytes':definition['resources']['max_output_bytes'], 'output_dir':str(output),'captured_files':records,
            'runtime_files':[dict(path=path,**record) for path,record in sorted(runtime['files'].items())],
            'trusted_install_owner_uid':runtime['trusted_install_owner_uid']}
    if 'native_policies' in material or 'cpu_snapshot' in material: spec['native_loader_policy'] = NATIVE_POLICY
    if 'cpu_snapshot' in material: spec['cpu_snapshot'] = material['cpu_snapshot']
    return spec


def validate_spec(material, spec, staging):
    expected = spec_for_material(material, staging)
    actual = {key:value for key,value in spec.items() if key not in ('attempt_id', 'request_sha256')}
    if encode(actual) != encode(expected):
        raise WorkbenchError('Execution specification differs from the approved material.', 'conflict', 409)
    return expected


def _sync_directory(path):
    fd = os.open(path, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try: os.fsync(fd)
    finally: os.close(fd)


def capture(preflight, captured, staging):
    staging = Path(staging).absolute()
    # The Runs owner supplies an existing private attempt parent, never a client path.
    staging.mkdir(mode=0o700, exist_ok=False)
    output = staging/'output'; output.mkdir(mode=0o700)
    for relative, raw in captured.items():
        path = staging/relative; path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        with path.open('xb') as handle:
            handle.write(raw); handle.flush(); os.fchmod(handle.fileno(),0o400); os.fsync(handle.fileno())
    for directory, _dirs, _files in os.walk(staging, topdown=False):
        _sync_directory(directory)
    _sync_directory(staging.parent)
    return dict(preflight, spec=spec_for_material(preflight['material'], staging))


def verify_outputs(output_dir, outputs, max_output_bytes):
    root = Path(output_dir)
    if root.is_symlink() or not root.is_dir(): raise WorkbenchError('Output root is not a regular directory.')
    allowed = {entry['path']:entry for entry in outputs}; found = {}; total = 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        if any((Path(directory)/name).is_symlink() for name in dirs): raise WorkbenchError('Output directory symlinks are forbidden.')
        for name in files:
            path = Path(directory)/name; relative = path.relative_to(root).as_posix()
            if relative not in allowed or len(found) >= MAX_FILES: raise WorkbenchError('Undeclared output file.')
            fd = os.open(path, os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
            try:
                info = os.fstat(fd); rule = allowed[relative]
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > rule['max_bytes']: raise WorkbenchError('Output must be a bounded unlinked regular file.')
                chunks = []; remaining = rule['max_bytes']+1
                while remaining:
                    raw = os.read(fd,min(65536,remaining))
                    if not raw: break
                    chunks.append(raw); remaining -= len(raw)
                raw = b''.join(chunks); after = os.fstat(fd)
                if len(raw) != info.st_size or (info.st_size,info.st_mtime_ns,info.st_ctime_ns) != (after.st_size,after.st_mtime_ns,after.st_ctime_ns): raise WorkbenchError('Output changed during verification.')
                total += len(raw)
                if total > max_output_bytes: raise WorkbenchError('Output total exceeds declared limit.')
                found[relative] = {'path':relative,'role':rule['role'],'bytes':len(raw),'sha256':file_digest(raw)}
            finally: os.close(fd)
    if any(item['required'] and item['path'] not in found for item in outputs): raise WorkbenchError('Required output is missing.')
    return list(found.values())
