"""Closed native job launch, entered only behind the existing custodian GO.

The custodian arms parent-death kill before exec. This module rechecks and
retains that exact parent before importing a captured native worker. It creates
new execution evidence; the original job template is never modified.
"""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import sys

WORKERS = frozenset(('image_training.py', 'text_training.py', 'audio_training.py'))
TEMPLATE_LIMIT = 64 * 1024


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode('utf-8')


def pairs(items):
    value = {}
    for key, item in items:
        if key in value: raise ValueError('Duplicate native template member.')
        value[key] = item
    return value


def read_regular(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as source:
        before = os.fstat(source.fileno())
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_uid != os.getuid() or before.st_mode & 0o222
                or before.st_size > TEMPLATE_LIMIT):
            raise ValueError('Native template is not an owned immutable file.')
        raw = source.read(TEMPLATE_LIMIT + 1)
        after = os.fstat(source.fileno())
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError('Native template changed.')
        if len(raw) > TEMPLATE_LIMIT: raise ValueError('Native template exceeds its bound.')
        return raw


def parent_identity():
    parent = os.getppid()
    if parent <= 1: raise ValueError('Native custodian parent is unavailable.')
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0):
        raise ValueError('Native parent-death protection is unavailable.')
    fields = Path('/proc/' + str(parent) + '/stat').read_text().rsplit(')', 1)[1].split()
    value = dict(pid=parent, start_ticks=fields[19],
                 boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
    if os.getppid() != parent: raise ValueError('Native custodian parent changed.')
    return value


def write_once(directory, name, raw):
    descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o400, dir_fd=directory)
    with os.fdopen(descriptor, 'wb') as target:
        target.write(raw); target.flush(); os.fsync(target.fileno())
    os.fsync(directory)


def main(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 2 or arguments[0] not in ('train', 'verify'):
        raise ValueError('Unsupported native launch phase.')
    # The helper already armed this death signal before executing Python.
    # Re-arm and observe it before runpy or any native worker import.
    parent = parent_identity()
    root = Path.cwd()
    template = Path(arguments[1])
    if template != root / 'native-job-template.json':
        raise ValueError('Native template path differs.')
    raw = read_regular(template)
    value = json.loads(raw, object_pairs_hook=pairs,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite native value.')))
    if (type(value) is not dict or set(value) != {'format', 'phase', 'worker', 'attempt_id', 'request_sha256', 'job'}
            or value['format'] != 'native_parent_binding_v1' or value['phase'] != arguments[0]
            or value['worker'] not in WORKERS or type(value['job']) is not dict
            or type(value['job'].get('parent_pid')) is not int or value['job']['parent_pid'] != 1
            or encoded(value) != raw):
        raise ValueError('Native job template differs from the closed contract.')
    job = dict(value['job'], parent_pid=parent['pid'])
    effective = encoded(job)
    observation = encoded(dict(format='native_parent_observation_v1', attempt_id=value['attempt_id'],
        request_sha256=value['request_sha256'], template_sha256=hashlib.sha256(raw).hexdigest(),
        effective_job_sha256=hashlib.sha256(effective).hexdigest(), helper=parent))
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        write_once(directory, 'effective-job.json', effective)
        write_once(directory, 'native-parent-observation.json', observation)
    finally:
        os.close(directory)
    worker = Path(__file__).resolve().parent / value['worker']
    sys.path.insert(0, str(worker.parent))
    sys.argv[:] = [str(worker), '--job' if value['phase'] == 'train' else '--verify-evidence',
                   str(root / 'effective-job.json')]
    import runpy
    runpy.run_path(str(worker), run_name='__main__')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('Native launch binding failed.', file=sys.stderr, flush=True)
        raise SystemExit(2)
