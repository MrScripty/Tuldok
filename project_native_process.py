"""Finite native probe/train/verifier preparation over the existing custodian.

Only the current native domain owner supplies measured runtime and source bytes.
Preparation owns new disposable files, not SQL, portable publication, authority,
or GO. The caller acknowledges READY through its canonical boundary, then uses
the returned ordinary recipe_process.Handle explicitly.
"""
import copy
import hashlib
import os
from pathlib import Path
import re
import stat

import recipe_process as custody

WORKERS = frozenset(('image_training.py', 'text_training.py', 'audio_training.py'))
PHASES = frozenset(('probe', 'train', 'verify'))
TEMPLATE_FORMAT = 'native_parent_binding_v1'
TEMPLATE_LIMIT = 64 * 1024
BOOTSTRAP = Path(__file__).with_name('native_process_bootstrap.py')
ENVIRONMENT = dict(PATH='/usr/bin:/bin', LANG='C.UTF-8', CUDA_VISIBLE_DEVICES='',
    OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', BLIS_NUM_THREADS='1',
    VECLIB_MAXIMUM_THREADS='1', NUMEXPR_NUM_THREADS='1', PYTHONDONTWRITEBYTECODE='1')


def _fail(message, code='invalid'):
    raise custody.ProcessError(message, code)


def validate_current_runtime(value):
    """Pure observed runtime metadata, not a complete package/library closure."""
    if (type(value) is not dict or set(value) != {'executable', 'executable_source', 'executable_sha256',
                                                'trusted_install_owner_uid', 'files'}
            or type(value['files']) is not dict or not 1 <= len(value['files']) <= 3
            or type(value['trusted_install_owner_uid']) is not int or value['trusted_install_owner_uid'] < 0):
        _fail('Invalid observed current native runtime.')
    for key in ('executable', 'executable_source'):
        path = value[key]
        if (type(path) is not str or not 1 <= len(path) <= 4096 or '\0' in path
                or not Path(path).is_absolute() or str(Path(path)) != path or '..' in Path(path).parts):
            _fail('Invalid observed native interpreter path.')
    if type(value['executable_sha256']) is not str or custody.HASH.fullmatch(value['executable_sha256']) is None:
        _fail('Invalid observed native interpreter hash.')
    allowed = {value['executable_source'], str(Path(value['executable']).parent/'pyvenv.cfg'),
               str(Path(value['executable']).parent.parent/'pyvenv.cfg')}
    for path, row in value['files'].items():
        if (path not in allowed or type(row) is not dict or set(row) != {'sha256', 'bytes'}
                or type(row['sha256']) is not str or custody.HASH.fullmatch(row['sha256']) is None
                or type(row['bytes']) is not int or not 0 <= row['bytes'] <= 64*1024*1024):
            _fail('Invalid observed native runtime file.')
    if value['files'].get(value['executable_source'], {}).get('sha256') != value['executable_sha256']:
        _fail('Observed native interpreter source differs.')
    return copy.deepcopy(value)


def current_runtime(executable):
    """Measure only the explicit current interpreter and venv configuration.

    Installed packages and native libraries remain operator-managed dependencies;
    the actual native probe observes their reported versions. No executable runs
    here and no alternative interpreter is selected.
    """
    if type(executable) is not str or not executable or '\0' in executable:
        _fail('Choose the explicitly configured native interpreter.')
    configured = Path(os.path.abspath(executable))
    try:
        physical = configured.resolve(strict=True)
        files = {}
        for path in dict.fromkeys((physical, configured.parent/'pyvenv.cfg', configured.parent.parent/'pyvenv.cfg')):
            if path != physical and not os.path.lexists(path): continue
            raw = custody.read_regular(path, 64*1024*1024)
            files[str(path)] = dict(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
        if configured.resolve(strict=True) != physical or not os.path.samestat(configured.stat(),physical.stat()):
            _fail('Configured native interpreter alias changed.', 'stale')
        return validate_current_runtime(dict(executable=str(configured), executable_source=str(physical),
            executable_sha256=files[str(physical)]['sha256'], trusted_install_owner_uid=os.stat('/usr').st_uid,
            files=files))
    except OSError:
        _fail('Configured current native interpreter is unavailable.', 'unavailable')


def validate_prepared_spec(value, *, phase, worker):
    """Pure finite native invocation grammar; never a current runtime resolver."""
    value = custody.decode_retained_spec(value)
    if (type(phase) is not str or phase not in PHASES or type(worker) is not str or worker not in WORKERS
            or value['schema_version'] != 1 or value['env'] != ENVIRONMENT
            or value.get('native_loader_policy') != 'glibc_x86_64_no_preload_v1'
            or any(key in value for key in ('cpu_snapshot', 'torch_runtime', 'resource_profile'))):
        _fail('Unsupported retained native phase specification.')
    root = Path(value['cwd'])
    if str(root) != value['cwd'] or '..' in root.parts:
        _fail('Retained native working directory differs.')
    source = root / 'source'
    captures = {row['path'] for row in value['captured_files']}
    template = str(root / 'native-job-template.json')
    bootstrap = str(source / BOOTSTRAP.name)
    for path in captures:
        item = Path(path)
        if path == template and phase != 'probe': continue
        if (item.parent != source or str(item) != path
                or re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,119}\.py', item.name) is None
                or item.name == BOOTSTRAP.name and phase == 'probe'):
            _fail('Unclassified retained native capture path.')
    if str(source / worker) not in captures:
        _fail('Retained native worker capture is missing.')
    executable = value['argv'][0]
    if phase == 'probe':
        expected = [executable, '-B', str(source / worker), '--probe']
        if value['argv'] not in (expected, expected + ['--model-aware']):
            _fail('Retained native probe argument vector differs.')
    elif (value['argv'] != [executable, '-I', '-B', bootstrap, phase, template]
          or not {bootstrap, template} <= captures):
        _fail('Retained native job bootstrap differs.')
    if phase in ('probe', 'train') and value['output_dir'] != str(root / 'output'):
        _fail('Retained native output directory differs.')
    return value


def _job_template(spec, phase, template):
    if (type(template) is not bytes or not 1 <= len(template) <= TEMPLATE_LIMIT):
        _fail('Native retained job template is unavailable or exceeds its bound.', 'stale')
    frame = custody.decode(template)
    if (type(frame) is not dict or set(frame) != {'format','phase','worker','attempt_id','request_sha256','job'}
            or frame['format'] != TEMPLATE_FORMAT or frame['phase'] != phase
            or frame['attempt_id'] != spec['attempt_id'] or frame['request_sha256'] != spec['request_sha256']
            or type(frame['job']) is not dict or type(frame['job'].get('parent_pid')) is not int
            or frame['job']['parent_pid'] != 1 or custody.encoded(frame) != template):
        _fail('Native retained job template differs from its phase.', 'stale')
    return frame


def validate_job_evidence(spec, *, phase, helper, template, effective_job, parent_observation, receipt):
    """Pure exact native job proof for inline history or current measured bytes.

    The existing native worker still owns scientific job semantics. This seam
    binds only the immutable template, qualified helper, distinct effective job
    and closed custodian receipt; it confers no current execution authority.
    """
    spec = custody.decode_retained_spec(spec)
    if type(phase) is not str or phase not in PHASES or not custody.valid_identity(helper):
        _fail('Invalid native job evidence phase or helper.')
    if phase == 'probe':
        if any(value is not None for value in (template,effective_job,parent_observation)):
            _fail('Native probe cannot carry job execution evidence.', 'stale')
        worker = Path(spec['argv'][2]).name if len(spec['argv']) > 2 else ''
        frame = None
    else:
        frame = _job_template(spec,phase,template)
        worker = frame['worker']
    spec = validate_prepared_spec(spec,phase=phase,worker=worker)
    expected = dict(attempt_id=spec['attempt_id'],request_sha256=spec['request_sha256'],
                    spec_sha256=hashlib.sha256(custody.encoded(spec)).hexdigest(),helper=helper)
    if type(receipt) is not dict:_fail('Native job evidence requires its closed custody receipt.')
    receipt = custody.validate_receipt(custody.encoded(receipt),expected)
    if not receipt['drained']:_fail('Native descendant drainage is unconfirmed.', 'unknown')
    if frame is not None:
        row = next(item for item in spec['captured_files'] if item['path'] == str(Path(spec['cwd'])/'native-job-template.json'))
        if len(template) != row['bytes'] or hashlib.sha256(template).hexdigest() != row['sha256']:
            _fail('Native retained job template differs from its captured identity.', 'stale')
        if effective_job is not None or parent_observation is not None:
            if (type(effective_job) is not bytes or type(parent_observation) is not bytes
                    or not 1 <= len(effective_job) <= TEMPLATE_LIMIT
                    or not 1 <= len(parent_observation) <= TEMPLATE_LIMIT):
                _fail('Native measured job evidence is incomplete or exceeds its bound.', 'unknown')
            expected_job = dict(frame['job'],parent_pid=helper['pid'])
            expected_observation = dict(format='native_parent_observation_v1',
                attempt_id=spec['attempt_id'],request_sha256=spec['request_sha256'],
                template_sha256=hashlib.sha256(template).hexdigest(),
                effective_job_sha256=hashlib.sha256(effective_job).hexdigest(),helper=helper)
            if (effective_job != custody.encoded(expected_job) or parent_observation != custody.encoded(expected_observation)
                    or not receipt['go_received']):
                _fail('Native effective job differs from its exact qualified parent.', 'stale')
        elif receipt['outcome'] == 'completed':
            _fail('Completed native phase lacks measured job evidence.', 'unknown')
    return dict(receipt=receipt,template=template,effective_job=effective_job,parent_observation=parent_observation)


def _record(path, raw):
    return dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))


def _write(directory, name, raw):
    descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o400, dir_fd=directory)
    with os.fdopen(descriptor, 'wb') as target:
        target.write(raw); target.flush(); os.fsync(target.fileno())


def _parent(path):
    """Walk the caller's explicit current path without directory symlinks."""
    if not path.is_absolute() or '..' in path.parts or path.name in ('', '.', '..'):
        _fail('Native staging requires an absolute new path.')
    descriptor = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parent.parts[1:]:
            following = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor); descriptor = following
        return descriptor
    except BaseException:
        os.close(descriptor); raise


def _directory(path):
    parent = _parent(path)
    try:
        descriptor = os.open(path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    finally:os.close(parent)
    info = os.fstat(descriptor)
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        os.close(descriptor)
        _fail('Native phase evidence requires its current private physical directory.', 'stale')
    return descriptor


def _read_at(directory, name, maximum, *, immutable=False):
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    with os.fdopen(descriptor, 'rb') as source:
        before = os.fstat(source.fileno())
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_uid != os.getuid()
                or before.st_size > maximum or immutable and before.st_mode & 0o222):
            _fail('Native phase evidence file is unsafe or exceeds its bound.', 'stale')
        raw = source.read(maximum + 1)
        after = os.fstat(source.fileno())
        identity = lambda row: (row.st_dev,row.st_ino,row.st_mode,row.st_nlink,row.st_uid,
                                row.st_size,row.st_mtime_ns,row.st_ctime_ns)
        if (len(raw) > maximum or identity(before) != identity(after)
                or identity(after) != identity(os.stat(name, dir_fd=directory, follow_symlinks=False))):
            _fail('Native phase evidence changed during observation.', 'stale')
        return raw


def read_phase_evidence(stage, spec, *, phase, helper):
    """Read one caller-qualified original physical phase, never restore custody.

    The caller must first prove its current original-host/root/projection journal
    binding. This function uses only that explicit stage and its custody child;
    retained absolute paths cannot select another filesystem root. No runtime
    lookup, process observation, signal, launch or GO occurs here.
    """
    return _read_phase_evidence(stage, spec, phase=phase, helper=helper,
                                custody_directory=Path(stage) / 'custody')


def _read_phase_evidence(stage, spec, *, phase, helper, custody_directory):
    stage = Path(stage)
    spec = custody.decode_retained_spec(spec)
    if spec['cwd'] != str(stage) or not custody.valid_identity(helper):
        _fail('Native phase evidence differs from its qualified physical stage or helper.', 'stale')
    if type(phase) is not str or phase not in PHASES:
        _fail('Unsupported native phase evidence.')
    root = source = owner = None
    try:
        root = _directory(stage)
        template = None
        if phase == 'probe':
            worker = Path(spec['argv'][2]).name if len(spec['argv']) > 2 else ''
        else:
            template = _read_at(root, 'native-job-template.json', TEMPLATE_LIMIT, immutable=True)
            frame = _job_template(spec,phase,template)
            worker = frame['worker']
        spec = validate_prepared_spec(spec, phase=phase, worker=worker)
        source = os.open('source', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
        for item in spec['captured_files']:
            name = Path(item['path']).name
            raw = template if item['path'] == str(stage/'native-job-template.json') else _read_at(
                source, name, item['bytes'], immutable=True)
            if raw is None or len(raw) != item['bytes'] or hashlib.sha256(raw).hexdigest() != item['sha256']:
                _fail('Native retained capture differs from its exact specification.', 'stale')
        expected = dict(attempt_id=spec['attempt_id'],request_sha256=spec['request_sha256'],
                        spec_sha256=hashlib.sha256(custody.encoded(spec)).hexdigest(),helper=helper)
        try:
            owner = _directory(Path(custody_directory))
            receipt_raw = _read_at(owner,'receipt.json',16384)
            receipt = custody.validate_receipt(receipt_raw,expected)
            if custody.encoded(receipt) != receipt_raw:
                _fail('Native custody receipt lost its exact canonical bytes.', 'stale')
        except (OSError,custody.ProcessError):
            _fail('Native phase has no exact drainage receipt.', 'unknown')
        if not receipt['drained']: _fail('Native descendant drainage is unconfirmed.', 'unknown')
        streams = {}
        for name in ('stdout','stderr'):
            row = receipt['streams'][name]
            raw = _read_at(owner,name+'.log',custody.STREAM_LIMIT)
            if len(raw) != row['bytes'] or hashlib.sha256(raw).hexdigest() != row['sha256']:
                _fail('Native measured stream differs from its custody receipt.', 'stale')
            streams[name] = raw
        effective = observation = None
        if template is not None:
            present = []
            for name in ('effective-job.json','native-parent-observation.json'):
                try:os.stat(name,dir_fd=root,follow_symlinks=False);present.append(True)
                except FileNotFoundError:present.append(False)
            if any(present):
                if not all(present): _fail('Native measured job evidence is incomplete.', 'unknown')
                effective = _read_at(root,'effective-job.json',TEMPLATE_LIMIT,immutable=True)
                observation = _read_at(root,'native-parent-observation.json',TEMPLATE_LIMIT,immutable=True)
        proof = validate_job_evidence(spec,phase=phase,helper=helper,template=template,
            effective_job=effective,parent_observation=observation,receipt=receipt)
        if not os.path.samestat(os.fstat(root),os.stat(stage,follow_symlinks=False)):
            _fail('Native physical phase changed during observation.', 'stale')
        if (not os.path.samestat(os.fstat(source),os.stat('source',dir_fd=root,follow_symlinks=False))
                or not os.path.samestat(os.fstat(owner),os.stat(custody_directory,follow_symlinks=False))):
            _fail('Native phase evidence directory changed during observation.', 'stale')
        return dict(proof,stdout=streams['stdout'],stderr=streams['stderr'])
    finally:
        for descriptor in (owner,source,root):
            if descriptor is not None:os.close(descriptor)


class PreparedNative:
    """A fixed phase specification and its new files; never an execution grant."""
    def __init__(self, stage, phase, spec, template, runtime=None):
        self.stage, self.phase = stage, phase
        self._spec, self.template = copy.deepcopy(spec), template
        self._runtime = copy.deepcopy(runtime)

    @property
    def spec(self):
        return copy.deepcopy(self._spec)

    def launch(self, custody_directory, *, _before_spawn=None):
        """Return a READY/GO Handle. This method never sends GO."""
        if self._runtime is None:
            return custody.launch(self.spec, custody_directory, _before_spawn=_before_spawn)
        self.check_current_runtime()
        descriptor = os.open(self._runtime['executable_source'], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            if not os.path.samestat(os.fstat(descriptor), os.stat(self._runtime['executable'])):
                _fail('Configured interpreter alias changed before launch.', 'stale')
            return custody.launch(self.spec, custody_directory, executable_fd=descriptor,
                                  _before_spawn=_before_spawn)
        finally:os.close(descriptor)

    def check_current_runtime(self):
        """Explicit owner check before GO; never dispatches or grants permission."""
        if self._runtime is not None and current_runtime(self._runtime['executable']) != self._runtime:
            _fail('Current native interpreter or venv configuration changed.', 'stale')
        return copy.deepcopy(self._runtime)

    def evidence(self, handle):
        """Read the same exact phase proof used by original-host recovery."""
        if handle.spec != self._spec or handle.ready is None:
            _fail('Native phase handle differs from its prepared specification.', 'unknown')
        result = _read_phase_evidence(self.stage, self._spec, phase=self.phase,
                                      helper=handle.ready, custody_directory=handle.directory)
        if result['template'] != self.template:
            _fail('Native immutable job template differs from its prepared value.', 'stale')
        return result


def prepare(stage, *, phase, attempt_id, request_sha256, runtime, worker, sources,
            job=None, model_aware=False, wall_seconds=None, max_output_bytes=64 * 1024 * 1024):
    """Create one new phase, using only caller-supplied current measurements.

    runtime is current_runtime's explicit interpreter/venv observation, or the
    four-field regular-file input executable/executable_sha256/
    trusted_install_owner_uid/files. These are observed files, not complete
    installed package/library closure. sources maps bounded Python
    basenames to exact captured bytes. The existing worker owns job semantics;
    this boundary requires parent_pid=1 and retains the whole template exactly.
    A verifier may inspect the preceding training phase's private output folder.
    """
    if (type(phase) is not str or phase not in PHASES or type(worker) is not str
            or worker not in WORKERS or type(model_aware) is not bool
            or type(attempt_id) is not str or custody.ID.fullmatch(attempt_id) is None
            or type(request_sha256) is not str or custody.HASH.fullmatch(request_sha256) is None):
        _fail('Invalid fixed native phase identity.')
    if (type(runtime) is not dict or set(runtime) not in (
            {'executable', 'executable_sha256', 'trusted_install_owner_uid', 'files'},
            {'executable', 'executable_source', 'executable_sha256', 'trusted_install_owner_uid', 'files'})
            or type(runtime['files']) is not dict or not runtime['files']):
        _fail('Supply an explicitly measured current native runtime.')
    measured = validate_current_runtime(runtime) if 'executable_source' in runtime else None
    if (type(sources) is not dict or worker not in sources or not 1 <= len(sources) <= 120
            or any(type(name) is not str or re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,119}\.py', name) is None
                   or name == BOOTSTRAP.name or type(raw) is not bytes for name, raw in sources.items())):
        _fail('Supply the exact finite native worker source closure.')
    if sum(map(len, sources.values())) > 64 * 1024 * 1024 - TEMPLATE_LIMIT:
        _fail('Native source closure exceeds its custody bound.')
    stage = Path(stage)
    if phase == 'probe':
        if job is not None: _fail('Native probe cannot accept a job.')
        template = None
        output = stage / 'output'
    else:
        if type(job) is not dict or type(job.get('parent_pid')) is not int or job['parent_pid'] != 1:
            _fail('Native job must retain its parent_pid=1 template.')
        if type(job.get('output_dir')) is not str or not Path(job['output_dir']).is_absolute():
            _fail('Native job requires its current private output directory.')
        output = Path(job['output_dir'])
        if phase == 'train' and output != stage / 'output':
            _fail('Native training output must belong to its new phase.')
        template = custody.encoded(dict(format=TEMPLATE_FORMAT, phase=phase, worker=worker,
            attempt_id=attempt_id, request_sha256=request_sha256, job=job))
        if len(template) > TEMPLATE_LIMIT: _fail('Native job template exceeds 64 KiB.')
    files = []
    for path, item in runtime['files'].items():
        if (type(path) is not str or not Path(path).is_absolute() or type(item) is not dict
                or set(item) != {'sha256', 'bytes'}): _fail('Invalid measured native runtime file.')
        files.append(dict(path=path, **item))
    executable = runtime['executable']
    executable_source = runtime.get('executable_source', executable)
    if (executable_source not in runtime['files'] or runtime['files'][executable_source]['sha256'] != runtime['executable_sha256']):
        _fail('Native interpreter is absent from its measured runtime closure.')
    captures = [_record(stage / 'source' / name, raw) for name, raw in sorted(sources.items())]
    if template is not None:
        bootstrap = BOOTSTRAP.read_bytes()
        captures.extend((_record(stage / 'source' / BOOTSTRAP.name, bootstrap),
                         _record(stage / 'native-job-template.json', template)))
        argv = [executable, '-I', '-B', str(stage / 'source' / BOOTSTRAP.name), phase,
                str(stage / 'native-job-template.json')]
    else:
        argv = [executable, '-B', str(stage / 'source' / worker), '--probe',
                *(['--model-aware'] if model_aware else [])]
    spec = custody.validate_spec(dict(schema_version=1, attempt_id=attempt_id, request_sha256=request_sha256,
        argv=argv, env=ENVIRONMENT.copy(), cwd=str(stage), stdin_base64='',
        wall_seconds=wall_seconds if wall_seconds is not None else {'probe':45, 'train':600, 'verify':90}[phase],
        executable_sha256=runtime['executable_sha256'], max_output_bytes=max_output_bytes,
        output_dir=str(output), captured_files=captures, runtime_files=sorted(files, key=lambda row:row['path']),
        trusted_install_owner_uid=runtime['trusted_install_owner_uid'], native_loader_policy='glibc_x86_64_no_preload_v1'))
    parent = _parent(stage)
    directory = source = None
    try:
        os.mkdir(stage.name, 0o700, dir_fd=parent)
        directory = os.open(stage.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        os.mkdir('source', 0o700, dir_fd=directory)
        source = os.open('source', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
        if output == stage / 'output': os.mkdir('output', 0o700, dir_fd=directory)
        elif phase == 'verify':
            check = os.open(output, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                info = os.fstat(check)
                if info.st_uid != os.getuid() or info.st_mode & 0o077:
                    _fail('Native verifier output must be a current private directory.')
            finally: os.close(check)
        for name, raw in sorted(sources.items()): _write(source, name, raw)
        if template is not None:
            _write(source, BOOTSTRAP.name, bootstrap)
            _write(directory, 'native-job-template.json', template)
        os.fsync(source); os.fsync(directory); os.fsync(parent)
    finally:
        for descriptor in (source, directory, parent):
            if descriptor is not None: os.close(descriptor)
    return PreparedNative(stage, phase, spec, template, measured)
