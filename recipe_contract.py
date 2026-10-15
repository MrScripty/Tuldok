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
CPU_INPUT_BYTES = 256 * 1024 * 1024
CPU_CAPTURE_BYTES = 320 * 1024 * 1024
MAX_FILES = 128
RUNTIME_LIMIT = 512 * 1024 * 1024
TYPES = ('input', 'execute', 'output')
PORTS = {'input': (None, 'data'), 'execute': ('data', 'artifacts'), 'output': ('artifacts', None)}
TRUST = 'Trusted local code; filesystem and network are not sandboxed. Runtime installation must remain immutable for the attempt.'
CPU_PROFILE = 'captured_cpu_python_v1'
LARGE_OUTPUT_PROFILE = 'captured_cpu_large_outputs_v1'
INPUT_EVIDENCE = 'runtime-bootstrap/input-evidence.json'
CPU_DESCRIPTOR = 'runtime-bootstrap/snapshot.json'
CPU_BOOTSTRAP = 'runtime-bootstrap/recipe_process.py'
HOST_NAMES = ('recipe_contract.py', 'projects.py', 'pipeline.py', 'recipe_process.py')
EVIDENCE_HOST_NAMES = (*HOST_NAMES, 'extension_evidence.py', 'field_evidence.py', 'scientific_fields.py', 'scientific_release.py')
EVIDENCE_FORMAT = 'external_model_evidence_recipe_v1'
BOUND_EVIDENCE_FORMAT = 'external_model_evidence_recipe_v2'
BOUND_EVIDENCE_HOST_NAMES = (*EVIDENCE_HOST_NAMES, 'extension_bindings.py', 'extension_contract.py', 'agent_api.py',
    *(f'extension_schemas/{name}-v1.json' for name in ('extension','contribution','parameter')))
EVIDENCE_CONTEXT = 'runtime-bootstrap/model-evidence-context.json'
EVIDENCE_CONTEXT_LIMIT = 64 * 1024
IMPORTED_HOST_FILES = {name: hashlib.sha256((Path(__file__).resolve().parent/name).read_bytes()).hexdigest() for name in HOST_NAMES}
IMPORTED_EVIDENCE_HOST_FILES = ({name: hashlib.sha256((Path(__file__).resolve().parent/name).read_bytes()).hexdigest() for name in EVIDENCE_HOST_NAMES}
    if all((Path(__file__).resolve().parent/name).is_file() for name in EVIDENCE_HOST_NAMES) else None)

IMPORTED_BOUND_EVIDENCE_HOST_FILES = {name: hashlib.sha256((Path(__file__).resolve().parent/name).read_bytes()).hexdigest() for name in BOUND_EVIDENCE_HOST_NAMES}


def is_bound_evidence(value):
    return (type(value) is dict and type(value.get('schema_version')) is int
            and value['schema_version'] == 3 and value.get('format') == BOUND_EVIDENCE_FORMAT)


def is_evidence(value):
    return (is_bound_evidence(value) or (type(value) is dict
            and type(value.get('schema_version')) is int and value['schema_version'] == 2
            and value.get('format') == EVIDENCE_FORMAT))


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
                   'arguments', 'parameters', 'inputs', 'outputs', 'environment', 'resources'), ('native_sources','runtime_snapshot_sha256','model_evidence','extension_selection'))
    evidence = is_evidence(value)
    bound = is_bound_evidence(value)
    if bound != ('extension_selection' in value):
        raise WorkbenchError('Contribution selection requires the explicit bound recipe version.', 'unsupported', 400)
    if bound:
        import extension_bindings
        extension_bindings.selection_references(value['extension_selection'])
    if not evidence and (type(value['schema_version']) is not int or value['schema_version'] != 1 or value['format'] != 'external_recipe_v1'):
        raise WorkbenchError('Unsupported explicit external recipe version.', 'unsupported', 400)
    if evidence != ('model_evidence' in value):
        raise WorkbenchError('Model evidence policy requires its explicit recipe version.', 'unsupported', 400)
    if evidence and (value['runtime'] != CPU_PROFILE or 'native_sources' in value):
        raise WorkbenchError('Initial model evidence requires captured CPU Python without native sources.', 'unsupported', 400)
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
        elif kind == 'model_evidence_context':
            if not evidence or arg is not True:raise WorkbenchError('Model context requires its explicit recipe version.')
        elif kind not in ('output_dir', 'input_evidence') or arg is not True:
            raise WorkbenchError('Unsupported argument token.')
    closed(value['resources'], ('wall_seconds', 'max_output_bytes'), ('profile',))
    large = 'profile' in value['resources']
    if large and (value['resources']['profile'] != LARGE_OUTPUT_PROFILE or value['runtime'] != CPU_PROFILE):
        raise WorkbenchError('Large outputs require the declared captured CPU resource profile.')
    outputs = value['outputs']
    if not isinstance(outputs, list) or not 1 <= len(outputs) <= (96 if large else 32):
        raise WorkbenchError('Output file count exceeds the resource profile bound.')
    seen = set()
    for output in outputs:
        closed(output, ('path', 'role', 'max_bytes', 'required'))
        path = relative_path(output['path']); named(output['role'])
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,119}', path) or path in ('artifact-manifest.json', 'custody-receipt.json'):
            raise WorkbenchError('Output must use an unreserved flat filename.')
        if path in seen or type(output['required']) is not bool: raise WorkbenchError('Invalid output contract.')
        seen.add(path)
        bounded_int(output['max_bytes'], 1, 512 * 1024 * 1024 if large else MAX_CAPTURE_BYTES, 'Output bytes')
    if value['environment'] != {}:
        raise WorkbenchError('Initial runtime admits no project environment overrides.', 'unsupported', 400)
    bounded_int(value['resources']['wall_seconds'], 1, 2400 if large else 600, 'Wall seconds')
    bounded_int(value['resources']['max_output_bytes'], 1, 4 * 1024**3 if large else MAX_CAPTURE_BYTES, 'Output bytes')
    if evidence:
        if value['arguments'].count({'model_evidence_context':True}) != 1:
            raise WorkbenchError('Declare exactly one model-evidence context argument.')
        import extension_evidence
        extension_evidence.validate_policy(value['model_evidence'], value)
        context_output=next((item for item in outputs if item['path']=='execution-context.json'),None)
        if context_output is None or context_output['required'] is not True or context_output['max_bytes'] != EVIDENCE_CONTEXT_LIMIT:
            raise WorkbenchError('Declare the exact bounded required context output.')
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
    snapshot = False
    try:
        raw, receipt = projects.read_recipe_reference(project_id, reference_id, expected_sha256)
    except WorkbenchError as error:
        if error.code != 'unsupported':
            raise
        raw, receipt = projects.read_snapshot_recipe_reference(project_id, reference_id, expected_sha256)
        snapshot = True
    definition = decode_definition(raw)
    bound = is_bound_evidence(definition)
    if snapshot != bound:
        raise WorkbenchError('Only the explicit bound recipe uses a Project v2 snapshot.', 'unsupported', 400)
    result = {'definition': definition, 'receipt': receipt, 'parameter_definitions': definition['parameters'],
              'inputs': definition['inputs'], 'outputs': definition['outputs'], 'runtime': definition['runtime']}
    if bound:
        import extension_bindings
        resolved = extension_bindings.resolve(projects, project_id, receipt['manifest_sha256'],
            extension_bindings.selection_references(definition['extension_selection']))
        extension_bindings.validate_configuration(resolved['binding'], definition, validate_parameters(definition, {}))
        extension_bindings.validate_provider_requirements(resolved['binding'],resolved['blobs'],definition)
        result['extension_binding'] = resolved['binding']
        policy = definition['model_evidence']
        result['model_task'] = {'kind':'task','catalog_id':projects.db.dataset_id,
            'id':policy['task']['id'],'revision':policy['task']['revision'],'sha256':digest(policy['task']['definition'])}
        result['selection_policy'] = {'format':'selection_policy_v1',
            'metric_definition_sha256':digest(policy['metric_definitions'][0]),'checkpoint_rule':'last',
            'replicate_reduce':'individual','required_capabilities':policy['profile']['required_capabilities'],
            'numerical_acceptance':'diagnostic','tie_break':'trial_id'}
    return result


def bound_sources(projects, inspected):
    """Capture a selected provider inventory using the authenticated Project receipt."""
    import extension_bindings
    definition = inspected['definition']; receipt = inspected['receipt']
    result = extension_bindings.resolve(projects, receipt['project_id'], receipt['manifest_sha256'],
        extension_bindings.selection_references(definition['extension_selection']))
    if encode(result['binding']) != encode(inspected['extension_binding']):
        raise WorkbenchError('Contribution binding changed during capture.', 'stale', 409)
    selected = extension_bindings.validate_roles(result['binding'], definition['extension_selection'])
    if definition['entrypoint'] != selected['trainer']['implementation']['source']:
        raise WorkbenchError('Recipe entrypoint differs from the selected trainer source.')
    extension_bindings.validate_provider_requirements(result['binding'],result['blobs'],definition)
    sources = dict(result['blobs'])
    for source in definition['sources']:
        if source['path'] not in sources or file_digest(sources[source['path']]) != source['sha256']:
            raise WorkbenchError('Recipe source is absent from its exact contribution inventory.')
    if extension_bindings.BINDING_PATH in sources:
        raise WorkbenchError('Provider inventory uses the reserved binding capture path.')
    sources[extension_bindings.BINDING_PATH] = encode(result['binding']).encode()
    if len(sources) > 64 or sum(map(len, sources.values())) > MAX_SOURCE_BYTES:
        raise WorkbenchError('Bound source closure exceeds64 files/8MiB.', 'too_large', 400)
    return sources


def validate_bound_sources(definition, binding, sources, *, specification=None, task=None):
    """Cold rederivation from retained files, with no Project reads or execution."""
    import extension_bindings
    raw = sources.get(extension_bindings.BINDING_PATH)
    if not isinstance(raw, bytes) or len(raw) > extension_bindings.BOUND_DOCUMENT_LIMIT:
        raise WorkbenchError('Retained binding document is missing or oversized.', 'unavailable', 409)
    value = decode(raw)
    if encode(value) != encode(binding):
        raise WorkbenchError('Retained binding document differs.', 'unavailable', 409)
    inventory = {item['path'] for item in binding['inventory']}
    blobs = {path:sources[path] for path in inventory if path in sources}
    extension_bindings.validate_captured(binding, blobs)
    extension_bindings.validate_provider_requirements(binding,blobs,definition)
    extension_bindings.validate_configuration(binding, definition, validate_parameters(definition, {}),
                                               specification=specification, task=task)
    selected = extension_bindings.validate_roles(binding, definition['extension_selection'])
    if definition['entrypoint'] != selected['trainer']['implementation']['source']:
        raise WorkbenchError('Retained entrypoint differs from its trainer contribution.', 'unavailable', 409)
    if set(sources) != inventory | {extension_bindings.BINDING_PATH}:
        raise WorkbenchError('Retained bound source inventory differs.', 'unavailable', 409)
    for source in definition['sources']:
        if source['path'] not in sources or file_digest(sources[source['path']]) != source['sha256']:
            raise WorkbenchError('Retained recipe source differs from its binding.', 'unavailable', 409)
    return binding


def validate_bound_captures(material, captured):
    if is_bound_evidence(material['recipe']):
        return validate_bound_sources(material['recipe'], material['extension_binding'],
            {path[len('source/'):]:raw for path,raw in captured.items() if path.startswith('source/')})


def host_identity(*, evidence=False, bound=False):
    import recipe_process
    root = Path(__file__).resolve().parent
    imported = IMPORTED_BOUND_EVIDENCE_HOST_FILES if bound else IMPORTED_EVIDENCE_HOST_FILES if evidence else IMPORTED_HOST_FILES
    if imported is None:
        raise WorkbenchError('Canonical field evidence dependency is unavailable; restart after explicit provisioning.', 'unavailable', 409)
    current = {name: file_digest((root/name).read_bytes()) for name in (BOUND_EVIDENCE_HOST_NAMES if bound else EVIDENCE_HOST_NAMES if evidence else HOST_NAMES)}
    if current != imported or file_digest(recipe_process.SOURCE) != current['recipe_process.py']:
        raise WorkbenchError('Execution host changed after import. Restart before preflight or execution.', 'stale', 409)
    return current



def recipe_host_identity(definition):
    return host_identity(evidence=is_evidence(definition),bound=is_bound_evidence(definition))


def revalidate_bound_material(projects, material, captured, profile=None):
    """Recheck an owner-prepared immutable capture for an exact grant consumer.

    Current Project bytes are compared privately against this exact retained
    composition. Admission authorization stays with its owner; current runtime
    and host qualification remain required. Cold disclosure uses retained bytes.
    """
    if not is_bound_evidence(material['recipe']):
        raise WorkbenchError('Retained-only preparation requires the bound recipe version.')
    validate_material(material)
    measured={path:{'bytes':len(raw),'sha256':file_digest(raw)} for path,raw in captured.items()}
    if encode(measured)!=encode(material['captures']):
        raise WorkbenchError('Retained execution capture differs.','unavailable',409)
    validate_bound_captures(material,captured)
    # Exact retained composition has already been authorized and checked by
    # Pipeline. This private nondisclosing comparison grants no ambient Project
    # reads to its agent consumer, while preserving source freshness on new work.
    import extension_bindings
    binding=material['extension_binding']
    try:
        saved,manifest_raw=projects._snapshot_saved(material['project']['project_id'],material['project']['manifest_sha256'])
        current=extension_bindings._resolve(saved,manifest_raw,
            extension_bindings.selection_references(material['recipe']['extension_selection']),
            lambda path,limit:projects._read_snapshot_file(saved,path,limit))
        if encode(current['binding'])!=encode(binding):
            raise WorkbenchError('Current contribution binding differs.')
        for path,raw in current['blobs'].items():
            if raw!=captured.get('source/'+path):raise WorkbenchError('Current provider bytes differ.')
        ref=next((item for item in saved['manifest']['recipes'] if item['id']==material['project']['reference_id']),None)
        if ref is None or ref['path']!=material['project']['path']:
            raise WorkbenchError('Current recipe reference differs.')
        raw=projects._read_snapshot_file(saved,ref['path'],65536)
        if (file_digest(raw)!=material['project']['measured_sha256'] or
                ref.get('sha256',file_digest(raw))!=file_digest(raw) or
                encode(decode_definition(raw))!=encode(material['recipe'])):
            raise WorkbenchError('Current recipe definition differs.')
        for name,receipt in material['inputs'].items():
            if 'kind' in receipt:raise WorkbenchError('Bound field inputs require Project references.')
            ref=next((item for item in saved['manifest']['data'] if item['id']==receipt['reference_id']),None)
            if ref is None or ref['path']!=receipt['path']:raise WorkbenchError('Current input reference differs.')
            raw=projects._read_snapshot_file(saved,ref['path'],material['recipe']['inputs'][name]['max_bytes'])
            if raw!=captured['input/'+name] or ref.get('sha256',file_digest(raw))!=file_digest(raw):
                raise WorkbenchError('Current Project input differs.')
        projects._snapshot_saved(material['project']['project_id'],material['project']['manifest_sha256'])
    except WorkbenchError:
        raise WorkbenchError('Bound Project, provider, recipe or input changed after review.','stale',409) from None
    if recipe_host_identity(material['recipe'])!=material['host_files'] or runtime_identity(profile)!=material['runtime']:
        raise WorkbenchError('Bound execution host or runtime changed after preparation.','stale',409)
    from runtime_snapshots import RuntimeSnapshots
    snapshot=RuntimeSnapshots(projects.db,projects.access,projects.db.path).get(
        material['recipe']['runtime_snapshot_sha256'],verify=True)
    if encode(snapshot)!=encode(material['cpu_snapshot']):
        raise WorkbenchError('Bound CPU snapshot changed after preparation.','stale',409)
    return material


def prepare(projects, graph, execution_sha256, profile=None, *, releases=None, runs=None):
    config, values = graph_parameters(graph)
    inspected = inspect_recipe(projects, config['project_id'], config['recipe_id'], config['expected_sha256'])
    definition = inspected['definition']; values = validate_parameters(definition, values)
    bound = is_bound_evidence(definition)
    sources = bound_sources(projects, inspected) if bound else projects.read_recipe_sources(config['project_id'], definition['sources'])
    if bound:
        import extension_bindings
        extension_bindings.validate_configuration(inspected['extension_binding'], definition, values)
    if not isinstance(config['inputs'], dict) or set(config['inputs']) != set(definition['inputs']):
        raise WorkbenchError('Bind every declared input exactly once.')
    if is_evidence(definition) and any(type(binding) is not dict or 'kind' in binding for binding in config['inputs'].values()):
        raise WorkbenchError('Authored model evidence supports only explicit project inputs, including unused inputs.','unsupported',409)
    captured = {'source/' + path: raw for path, raw in sources.items()}
    inputs = {}
    for name, binding in config['inputs'].items():
        if bound and isinstance(binding,dict) and 'kind' in binding:
            raise WorkbenchError('Bound field evidence requires authored Project inputs.','unsupported',400)
        if isinstance(binding, dict) and binding.get('kind') == 'run_artifact':
            closed(binding, ('kind', 'run_id', 'artifact_name', 'expected_sha256'))
            if runs is None:
                raise WorkbenchError('Run artifact input owner is unavailable.', 'unavailable', 409)
            raw, source = runs.capture_artifact(binding['run_id'], binding['artifact_name'], binding['expected_sha256'],
                                                max_bytes=definition['inputs'][name]['max_bytes'])
            receipt = {'kind': 'run_artifact', 'source': source}
        elif isinstance(binding, dict) and binding.get('kind') == 'frozen_release':
            closed(binding, ('kind', 'release_id', 'expected_sha256'))
            if releases is None:
                raise WorkbenchError('Frozen release input owner is unavailable.', 'unavailable', 409)
            raw, receipt = releases.capture_input(binding['release_id'], binding['expected_sha256'], definition['inputs'][name]['max_bytes'])
        else:
            closed(binding, ('reference_id', 'expected_sha256'))
            reader = projects.read_snapshot_data_reference if bound else projects.read_data_reference
            raw, receipt = reader(config['project_id'], binding['reference_id'], binding['expected_sha256'], definition['inputs'][name]['max_bytes'])
        captured['input/' + name] = raw; inputs[name] = receipt
    if {'input_evidence': True} in definition['arguments']:
        captured[INPUT_EVIDENCE] = encode(inputs).encode()
    capture_limit = CPU_CAPTURE_BYTES if definition['runtime'] == CPU_PROFILE else MAX_CAPTURE_BYTES
    input_limit = CPU_INPUT_BYTES if definition['runtime'] == CPU_PROFILE else MAX_CAPTURE_BYTES
    if sum(len(raw) for path,raw in captured.items() if path.startswith('input/')) > input_limit:
        raise WorkbenchError('Captured inputs exceed the runtime profile byte bound.')
    if len(captured) > MAX_FILES or sum(map(len,captured.values())) > capture_limit:
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
        if len(captured) > MAX_FILES or sum(map(len,captured.values())) > capture_limit:
            raise WorkbenchError('Generated native policies exceed the capture bound.')
    cpu_snapshot = None
    if definition['runtime'] == CPU_PROFILE:
        import recipe_process
        from runtime_snapshots import RuntimeSnapshots
        cpu_snapshot = RuntimeSnapshots(projects.db, projects.access, projects.db.path).get(
            definition['runtime_snapshot_sha256'], verify=True)
        captured[CPU_DESCRIPTOR] = recipe_process.encoded(cpu_snapshot)
        captured[CPU_BOOTSTRAP] = recipe_process.SOURCE
        if len(captured) > MAX_FILES or sum(map(len,captured.values())) > capture_limit:
            raise WorkbenchError('Generated CPU bootstrap exceeds the capture bound.')
    evidence = is_evidence(definition)
    if evidence and (len(captured)>=MAX_FILES or sum(map(len,captured.values()))+EVIDENCE_CONTEXT_LIMIT>CPU_CAPTURE_BYTES):
        raise WorkbenchError('Capture must reserve one bounded generated context file.')
    host = recipe_host_identity(definition)
    material = {'schema_version': 3 if bound else 2 if evidence else 1, 'catalog_id': projects.db.dataset_id, 'project': inspected['receipt'], 'graph_execution_sha256': execution_sha256,
                'recipe': definition, 'parameters': values, 'inputs': inputs,
                'captures': {path: {'bytes':len(raw),'sha256':file_digest(raw)} for path,raw in sorted(captured.items())},
                'runtime': runtime, 'host_files': host, 'permissions': {'filesystem':'trusted-local', 'network':'not_isolated'},
                'environment': {'LANG':'C.UTF-8'}, 'resources': definition['resources']}
    if bound: material['extension_binding'] = inspected['extension_binding']
    if policies is not None: material['native_policies'] = policies
    if cpu_snapshot is not None: material['cpu_snapshot'] = cpu_snapshot
    validate_material(material)
    return {'valid':True, 'status':'valid', 'material':material, 'material_sha256':digest(material), 'validation_token':digest(material),
            'parameter_definitions':definition['parameters'], 'outputs':definition['outputs'], 'runtime':runtime,
            'graph_revision':graph['revision'], 'execution_sha256':execution_sha256}, captured


def validate_material(material):
    """Cold structural custody checks; no filesystem access or current-code comparison."""
    closed(material, ('schema_version', 'catalog_id', 'project', 'graph_execution_sha256', 'recipe',
                      'parameters', 'inputs', 'captures', 'runtime', 'host_files', 'permissions', 'environment', 'resources'), ('native_policies','cpu_snapshot','extension_binding'))
    if type(material['schema_version']) is not int or material['schema_version'] not in (1,2,3) or not isinstance(material['catalog_id'], str) or not material['catalog_id']:
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
    evidence = is_evidence(definition)
    bound = is_bound_evidence(definition)
    if bound != ('extension_binding' in material):raise WorkbenchError('Material binding requires its explicit recipe version.')
    if bound:
        import extension_bindings
        extension_bindings.validate_configuration(material['extension_binding'], definition, material['parameters'])
    if material['schema_version'] != (3 if bound else 2 if evidence else 1):raise WorkbenchError('Recipe/material version differs.')
    if evidence and (len(material['captures'])>=MAX_FILES or sum(item['bytes'] for item in material['captures'].values())+EVIDENCE_CONTEXT_LIMIT>CPU_CAPTURE_BYTES):
        raise WorkbenchError('Material leaves no generated context capacity.')
    if encode(validate_parameters(definition, material['parameters'])) != encode(material['parameters']):
        raise WorkbenchError('Retained parameters must include every typed value.')
    if material['resources'] != definition['resources'] or material['environment'] != {'LANG':'C.UTF-8'} or material['permissions'] != {'filesystem':'trusted-local', 'network':'not_isolated'}:
        raise WorkbenchError('Material execution policy is inconsistent.')
    if not isinstance(material['inputs'], dict) or set(material['inputs']) != set(definition['inputs']): raise WorkbenchError('Material input inventory differs.')
    expected = {'source/'+item['path']:item['sha256'] for item in definition['sources']}
    if bound:
        binding = material['extension_binding']
        if binding['project']['id'] != material['project']['project_id'] or binding['project']['manifest_sha256'] != material['project']['manifest_sha256']:
            raise WorkbenchError('Contribution binding belongs to another Project snapshot.')
        expected = {'source/'+item['path']:item['sha256'] for item in binding['inventory']}
        expected['source/'+extension_bindings.BINDING_PATH] = file_digest(encode(binding).encode())
    for name, item in material['inputs'].items():
        if isinstance(item, dict) and item.get('kind') == 'run_artifact':
            import recipe_process
            closed(item, ('kind', 'source'))
            source = item['source']
            capture = material['captures'].get('input/' + name) if isinstance(material['captures'], dict) else None
            if not isinstance(capture, dict) or not isinstance(source, dict):
                raise WorkbenchError('Run input capture or receipt is missing.')
            try:
                recipe_process.validate_artifact_source(source, capture.get('sha256'), capture.get('bytes'))
            except recipe_process.ProcessError as error:
                raise WorkbenchError('Invalid Run input custody: ' + str(error)) from None
            if source['catalog_id'] != material['catalog_id']:
                raise WorkbenchError('Run input belongs to another catalog.')
            bounded_int(source['artifact_bytes'], 0, definition['inputs'][name]['max_bytes'], 'Run input bytes')
            expected['input/' + name] = source['measured_sha256']
            continue
        elif isinstance(item, dict) and item.get('kind') == 'frozen_release':
            closed(item, ('kind','catalog_id','release_id','measured_sha256','bytes'))
            sha(item['release_id']); sha(item['measured_sha256'])
            if item['catalog_id'] != material['catalog_id'] or item['release_id'] != item['measured_sha256']:
                raise WorkbenchError('Frozen input receipt belongs to another catalog or content identity.')
            bounded_int(item['bytes'],1,definition['inputs'][name]['max_bytes'],'Frozen input bytes')
        else:
            receipt(item)
            if (item['project_id'], item['manifest_sha256']) != (material['project']['project_id'], material['project']['manifest_sha256']):
                raise WorkbenchError('Input receipt belongs to another project snapshot.')
        expected['input/'+name] = item['measured_sha256']
    if evidence and any(type(item) is not dict or 'kind' in item for item in material['inputs'].values()):
        raise WorkbenchError('Authored model evidence cannot retain unsupported input kinds.','unsupported',409)
    generated = validate_native_policies(material,definition)
    if {'input_evidence': True} in definition['arguments']:
        generated[INPUT_EVIDENCE] = encode(material['inputs']).encode()
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
    total = 0; input_total = 0
    for path, item in captures.items():
        relative_path(path); closed(item, ('bytes','sha256')); sha(item['sha256'])
        limit = MAX_SOURCE_BYTES if path.startswith(('source/','native-policy/','runtime-bootstrap/')) else definition['inputs'][path.split('/',1)[1]]['max_bytes']
        bounded_int(item['bytes'],0,limit,'Capture bytes'); total += item['bytes']
        if path.startswith('input/'):
            input_total += item['bytes']
            input_receipt = material['inputs'][path.split('/',1)[1]]
            if input_receipt.get('kind') == 'frozen_release' and input_receipt['bytes'] != item['bytes']:
                raise WorkbenchError('Frozen input receipt and captured size differ.')
        if path in generated and item['bytes'] != len(generated[path]): raise WorkbenchError('Generated native policy size differs.')
        if item['sha256'] != expected[path]: raise WorkbenchError('Captured digest contradicts source/input identity.')
    capture_limit = CPU_CAPTURE_BYTES if definition['runtime'] == CPU_PROFILE else MAX_CAPTURE_BYTES
    input_limit = CPU_INPUT_BYTES if definition['runtime'] == CPU_PROFILE else MAX_CAPTURE_BYTES
    if total > capture_limit or input_total > input_limit:
        raise WorkbenchError('Captured material exceeds runtime profile byte bound.')
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
    if not isinstance(material['host_files'],dict) or set(material['host_files']) != set(BOUND_EVIDENCE_HOST_NAMES if bound else EVIDENCE_HOST_NAMES if evidence else HOST_NAMES): raise WorkbenchError('Invalid retained host closure.')
    for value in material['host_files'].values(): sha(value)
    return material


def spec_for_material(material, staging, *, context=None):
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
        elif kind == 'input_evidence': arg = str(staging/INPUT_EVIDENCE)
        elif kind == 'model_evidence_context': arg = str(staging/EVIDENCE_CONTEXT)
        else: arg = str(output)
        argv.append(arg)
    spec = {'schema_version':1,'argv':argv,'env':dict(material['environment']),'cwd':str(staging), 'stdin_base64':base64.b64encode(b'').decode(),
            'wall_seconds':definition['resources']['wall_seconds'], 'executable_sha256':runtime['executable_sha256'],
            'max_output_bytes':definition['resources']['max_output_bytes'], 'output_dir':str(output),'captured_files':records,
            'runtime_files':[dict(path=path,**record) for path,record in sorted(runtime['files'].items())],
            'trusted_install_owner_uid':runtime['trusted_install_owner_uid']}
    if 'native_policies' in material or 'cpu_snapshot' in material: spec['native_loader_policy'] = NATIVE_POLICY
    if 'cpu_snapshot' in material: spec['cpu_snapshot'] = material['cpu_snapshot']
    if 'profile' in definition['resources']: spec['resource_profile'] = definition['resources']['profile']
    if is_evidence(definition):
        spec['schema_version']=2
        spec['model_evidence_context']=None
        if context is not None:
            import extension_evidence
            raw=extension_evidence.canonical(extension_evidence.checked(context))
            ref={'path':str(staging/EVIDENCE_CONTEXT),'bytes':len(raw),'sha256':file_digest(raw)}
            spec['model_evidence_context']=ref
            spec['captured_files'].append(ref)
    elif context is not None:raise WorkbenchError('Legacy recipes cannot receive model context.')
    return spec


def validate_spec(material, spec, staging, *, context=None):
    if is_evidence(material['recipe']) and context is None:
        raise WorkbenchError('Final model-evidence specification requires authoritative attempt context.')
    expected = spec_for_material(material, staging, context=context)
    actual = {key:value for key,value in spec.items() if key not in ('attempt_id', 'request_sha256')}
    if encode(actual) != encode(expected):
        raise WorkbenchError('Execution specification differs from the approved material.', 'conflict', 409)
    return expected


def _sync_directory(path):
    fd = os.open(path, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try: os.fsync(fd)
    finally: os.close(fd)


def capture(preflight, captured, staging):
    validate_bound_captures(preflight['material'], captured)
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
    """Hash declared outputs with bounded memory and anchored file descriptors."""
    root = Path(output_dir).absolute()
    root_fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in root.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
            os.close(root_fd)
            root_fd = child
        root_info = os.fstat(root_fd)
        allowed = {entry['path']: entry for entry in outputs}
        found = {}
        total = 0
        identity = lambda info: (info.st_dev, info.st_ino, info.st_mode, info.st_uid,
                                 info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        for directory, dirs, files, directory_fd in os.fwalk('.', dir_fd=root_fd, follow_symlinks=False):
            if any(stat.S_ISLNK(os.stat(name, dir_fd=directory_fd, follow_symlinks=False).st_mode) for name in dirs):
                raise WorkbenchError('Output directory symlinks are forbidden.')
            for name in files:
                relative = (Path(directory) / name).as_posix()
                if relative not in allowed or len(found) >= MAX_FILES:
                    raise WorkbenchError('Undeclared output file.')
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
                try:
                    info = os.fstat(fd)
                    rule = allowed[relative]
                    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                            or info.st_uid != os.getuid() or info.st_size > rule['max_bytes']):
                        raise WorkbenchError('Output must be a bounded unlinked regular file.')
                    measured = 0
                    checksum = hashlib.sha256()
                    while True:
                        raw = os.read(fd, min(1024 * 1024, rule['max_bytes'] + 1 - measured))
                        if not raw:
                            break
                        measured += len(raw)
                        if measured > rule['max_bytes'] or total + measured > max_output_bytes:
                            raise WorkbenchError('Output total exceeds declared limit.')
                        checksum.update(raw)
                    after = os.fstat(fd)
                    current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                    if measured != info.st_size or identity(info) != identity(after) or identity(info) != identity(current):
                        raise WorkbenchError('Output changed during verification.')
                    total += measured
                    found[relative] = {'path': relative, 'role': rule['role'],
                                       'bytes': measured, 'sha256': checksum.hexdigest()}
                finally:
                    os.close(fd)
        current_root = os.stat(root, follow_symlinks=False)
        if (root_info.st_dev, root_info.st_ino) != (current_root.st_dev, current_root.st_ino):
            raise WorkbenchError('Output root changed during verification.')
        if any(item['required'] and item['path'] not in found for item in outputs):
            raise WorkbenchError('Required output is missing.')
        return list(found.values())
    except OSError as error:
        raise WorkbenchError('Output cannot be safely verified.', 'unavailable', 409) from error
    finally:
        os.close(root_fd)
