"""What a training script logged into its run's output directory, read while it is still being written.

Owns sections 2, 4 and 5 of docs/plans/training-and-curation/spec-t1.md. A run's
training files lie under training/ of its output directory: metrics.jsonl (a
line per log: step, time, named scalars), histograms.jsonl (a line per tensor
per log: edges and counts of its weights or gradients), samples.jsonl with the
files under samples/ it names, checkpoints.jsonl, and training.json. They are
read whatever the run's state, as soon as it has a directory: a running run's
files are being appended to, so only complete lines are taken and a partial
last line is left for the next read. What has been read of each file is kept
(FILES_KEPT files, least recently used dropped) with its offset, so reading
again reads only what was appended; a file that became shorter or is another
file (its device and inode) is read again from the start. A histogram line is
kept as its offset and length; its bins are read again when asked for. Long
series are sent in buckets of a power of two consecutive points (series()),
so that a page that holds some buckets can be sent only the later ones.

Standard library only; nothing here writes, opens the project, or runs or
imports the project's code. Every read is bounded (the constants below); a
damaged line is counted and reported, never a failure.
"""
import collections
import json
import math
import os
import threading
from array import array

from . import inside, inside_shapes
from .inside_archive import locate
from .store import ProjectError

DIRECTORY = 'training'
METRICS = 'metrics.jsonl'
HISTOGRAMS = 'histograms.jsonl'
SAMPLES = 'samples.jsonl'
CHECKPOINTS = 'checkpoints.jsonl'
STARTED = 'training.json'
STARTED_FORMAT = 'tuldok_training_v1'
KINDS = ('weights', 'gradients')
IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp')
ARRAY_EXTENSIONS = ('.npy',)

LINE_BYTES = 64 * 1024              # a line of metrics, samples or checkpoints
HISTOGRAM_LINE_BYTES = 256 * 1024   # a line of histograms
METRICS_LINES = 1_000_000           # metrics lines kept
SERIES = 200                        # series kept
NAME_CHARACTERS = 200               # of a series' name
TENSOR_CHARACTERS = 1000            # of a histogram's tensor name
HISTOGRAM_LINES = 1_000_000         # histogram lines indexed
PAIRS = 2000                        # tensor and kind pairs indexed
BINS = 1024                         # bins of one histogram line
SAMPLE_LINES = 100_000
CHECKPOINT_LINES = 10_000
CHECKPOINTS_SHOWN = 200
OTHER_KEYS = 200                    # names of keys that are not series, listed
STARTED_BYTES = 64 * 1024
PROBLEMS = 20
FILES_KEPT = 64                     # file states kept in memory (four a run)
CHUNK = 1 << 20                     # bytes read at a time
SAMPLE_SLICE = 128                  # rows and columns of an array sample's slice
_RESERVED = ('step', 'time', 'epoch')


class Run:
    """A run whose training files are read: its id, its state and its output directory (None when it has none)."""

    def __init__(self, run_id, state, output):
        self.run_id, self.state = run_id, state
        self.root = os.path.realpath(output) if output and os.path.isdir(output) else None

    @property
    def active(self):
        return self.state in ('queued', 'running')

    def product(self):
        """The inside.Product of its output directory, for reading a sample's file; not-found when there is none."""
        if self.root is None:
            raise ProjectError(f'Run {self.run_id} has no output directory yet.', 'not-found')
        return inside.Product(self.run_id, self.root)


def _number(value):
    """value as a float when it is a JSON number (not a boolean), else None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return float(value)
    except OverflowError:
        return math.inf if value > 0 else -math.inf


def _finite(value):
    number = _number(value)
    return number if number is not None and math.isfinite(number) else None


def _step(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


# ------------------------------------------------------------------ reading a file that grows

class _Log:
    """One file read incrementally: whole lines only, from where the last read stopped."""

    line_limit = LINE_BYTES
    line_most = METRICS_LINES

    def __init__(self, path, label):
        self.path, self.label = path, label
        self.lock = threading.Lock()
        self._start()

    def _start(self):
        self.identity, self.offset, self.number, self.skipping = None, 0, 0, False
        self.bad, self.problems, self.truncated = 0, [], False
        self.reset()

    def reset(self):
        """Forgets what was read (a subclass's own state)."""

    def take(self, value, number, start, length):
        """Keeps one decoded line; returns a sentence saying why it is refused, or None."""
        raise NotImplementedError

    def problem(self, number, text, bad=True):
        self.bad += bad
        if len(self.problems) < PROBLEMS:
            self.problems.append({'file': f'{DIRECTORY}/{self.label}', 'line': number, 'problem': text})

    def refresh(self):
        """Reads what was appended since the last read (all of it after a change of file); call with lock held."""
        try:
            stat = os.stat(self.path)
        except OSError:
            if self.identity is not None:
                self._start()
            return
        identity = (stat.st_dev, stat.st_ino)
        if identity != self.identity or stat.st_size < self.offset:
            self._start()
            self.identity = identity
        if stat.st_size == self.offset or self.truncated:
            return
        with open(self.path, 'rb') as handle:
            handle.seek(self.offset)
            pending = b''
            while True:
                chunk = handle.read(CHUNK)
                if not chunk:
                    break
                pending += chunk
                start = 0
                while True:
                    end = pending.find(b'\n', start)
                    if end < 0:
                        break
                    self._line(pending[start:end], self.offset)
                    self.offset += end - start + 1
                    start = end + 1
                    if self.truncated:
                        return
                pending = pending[start:]
                if len(pending) > self.line_limit:  # a line too long: skip its bytes up to its newline
                    if not self.skipping:
                        self.number += 1
                        self.problem(self.number, f'The line is longer than {self.line_limit} bytes.')
                        self.skipping = True
                    self.offset += len(pending)
                    pending = b''

    def _line(self, raw, start):
        if self.skipping:  # the end of a line too long, already counted
            self.skipping = False
            return
        self.number += 1
        if self.number > self.line_most:
            self.truncated = True
            return
        if not raw.strip():
            return
        if len(raw) > self.line_limit:
            self.problem(self.number, f'The line is longer than {self.line_limit} bytes.')
            return
        try:
            value = json.loads(raw.decode('utf-8'))
        except (UnicodeDecodeError, ValueError, RecursionError):
            self.problem(self.number, 'The line is not JSON.')
            return
        if not isinstance(value, dict):
            self.problem(self.number, 'The line is not a JSON object.')
            return
        wrong = self.take(value, self.number, start, len(raw))
        if wrong:
            self.problem(self.number, wrong)


class _Metrics(_Log):
    def reset(self):
        self.steps, self.times, self.epochs = array('q'), array('d'), array('d')
        self.series = {}       # name -> (array of line positions, array of values)
        self.nonfinite = collections.Counter()
        self.stats = {}        # name -> [min, max, last] of its finite values
        self.other_keys = []
        self.dropped = set()

    def take(self, value, number, start, length):
        step, time = _step(value.get('step')), _finite(value.get('time'))
        if step is None:
            return 'It has no step (an integer of 0 or more).'
        if time is None or time < 0:
            return 'It has no time (seconds since the run started, 0 or more).'
        epoch = _finite(value.get('epoch'))
        at = len(self.steps)
        self.steps.append(step)
        self.times.append(time)
        self.epochs.append(math.nan if epoch is None else epoch)
        for key, item in value.items():
            if key in _RESERVED:
                continue
            number = None if item is None else _number(item)
            if item is not None and number is None:
                if key not in self.other_keys and len(self.other_keys) < OTHER_KEYS:
                    self.other_keys.append(key)
                continue
            held = self.series.get(key)
            if held is None:
                if not key or len(key) > NAME_CHARACTERS:
                    continue
                if len(self.series) >= SERIES:
                    if key not in self.dropped:
                        self.dropped.add(key)
                        self.problem(number, f'More than {SERIES} series: {key[:80]} is not kept.', bad=False)
                    continue
                held = self.series[key] = (array('q'), array('d'))
            if number is None or not math.isfinite(number):
                self.nonfinite[key] += 1
                number = math.nan
            else:
                stats = self.stats.get(key)
                if stats is None:
                    self.stats[key] = [number, number, number]
                else:
                    stats[0], stats[1], stats[2] = min(stats[0], number), max(stats[1], number), number
            held[0].append(at)
            held[1].append(number)
        return None


class _Histograms(_Log):
    line_limit = HISTOGRAM_LINE_BYTES
    line_most = HISTOGRAM_LINES

    def reset(self):
        self.pairs = {}        # (name, kind) -> (steps, times, offsets, lengths)
        self.dropped = set()

    def take(self, value, number, start, length):
        wrong = histogram_problem(value)
        if wrong:
            return wrong
        key = (value['name'], value['kind'])
        held = self.pairs.get(key)
        if held is None:
            if len(self.pairs) >= PAIRS:
                if key not in self.dropped:
                    self.dropped.add(key)
                    self.problem(number, f'More than {PAIRS} tensors: {key[0][:80]} ({key[1]}) is not kept.',
                                 bad=False)
                return None
            held = self.pairs[key] = (array('q'), array('d'), array('q'), array('q'))
        held[0].append(value['step'])
        held[1].append(_finite(value.get('time')) or 0.0)
        held[2].append(start)
        held[3].append(length)
        return None


def histogram_problem(value):
    """A sentence saying why value is not a histogram line, or None."""
    if _step(value.get('step')) is None:
        return 'It has no step (an integer of 0 or more).'
    name = value.get('name')
    if not isinstance(name, str) or not name or len(name) > TENSOR_CHARACTERS:
        return f'It has no name (1 to {TENSOR_CHARACTERS} characters).'
    if value.get('kind') not in KINDS:
        return 'Its kind is not weights or gradients.'
    edges, counts = value.get('edges'), value.get('counts')
    if not isinstance(edges, list) or not isinstance(counts, list) or not 1 <= len(counts) <= BINS \
            or len(edges) != len(counts) + 1:
        return f'It needs edges (n + 1 numbers) and counts (n numbers), 1 to {BINS} bins.'
    previous = -math.inf
    for edge in edges:
        number = _finite(edge)
        if number is None or number < previous:
            return 'Its edges are not finite numbers in order.'
        previous = number
    for count in counts:
        number = _finite(count)
        if number is None or number < 0:
            return 'Its counts are not numbers of 0 or more.'
    return None


class _Samples(_Log):
    line_most = SAMPLE_LINES

    def reset(self):
        self.entries = []      # dicts: step, time, name, path, kind

    def take(self, value, number, start, length):
        step, name, path = _step(value.get('step')), value.get('name'), value.get('path')
        if step is None:
            return 'It has no step (an integer of 0 or more).'
        if not isinstance(name, str) or not name or len(name) > NAME_CHARACTERS:
            return f'It has no name (1 to {NAME_CHARACTERS} characters).'
        if not isinstance(path, str) or not path.startswith('samples/') or '!' in path or '\\' in path \
                or any(part in ('', '.', '..') for part in path.split('/')):
            return 'Its path is not a plain address under samples/.'
        extension = os.path.splitext(path.lower())[1]
        kind = 'image' if extension in IMAGE_EXTENSIONS else 'array' if extension in ARRAY_EXTENSIONS else None
        if kind is None:
            return 'Its file is not a PNG, JPEG or WebP image or an .npy array.'
        self.entries.append({'step': step, 'time': _finite(value.get('time')), 'name': name, 'path': path,
                             'kind': kind})
        return None


class _Checkpoints(_Log):
    line_most = CHECKPOINT_LINES

    def reset(self):
        self.entries = []

    def take(self, value, number, start, length):
        step, path = _step(value.get('step')), value.get('path')
        if step is None:
            return 'It has no step (an integer of 0 or more).'
        if not isinstance(path, str) or not path or len(path) > 4096:
            return 'It has no path.'
        entry = {'step': step, 'time': _finite(value.get('time')), 'path': path}
        entry['figures'] = {key: _finite(item) for key, item in value.items()
                            if key not in ('step', 'time', 'path') and _number(item) is not None}
        self.entries.append(entry)
        return None


_CLASSES = {METRICS: _Metrics, HISTOGRAMS: _Histograms, SAMPLES: _Samples, CHECKPOINTS: _Checkpoints}
_kept_lock = threading.Lock()
_kept = collections.OrderedDict()   # (real path of the file, its class) -> _Log


def forget():
    """Forgets every file read (the tests)."""
    with _kept_lock:
        _kept.clear()


def _path(run, name):
    """The real path of training/<name> under the run's output, or None when it has none or it lies outside."""
    if run.root is None:
        return None
    full = os.path.realpath(os.path.join(run.root, DIRECTORY, name))
    if not full.startswith(run.root + os.sep) or not os.path.isfile(full):
        return None
    return full


class _Read:
    """The state of one file of a run, refreshed, with its lock held for the block."""

    def __init__(self, run, name):
        self.run, self.name, self.log = run, name, None

    def __enter__(self):
        path = _path(self.run, self.name)
        if path is None:
            return None
        key = (path, self.name)
        with _kept_lock:
            log = _kept.get(key)
            if log is None:
                log = _kept[key] = _CLASSES[self.name](path, self.name)
            _kept.move_to_end(key)
            while len(_kept) > FILES_KEPT:
                _kept.popitem(last=False)
        log.lock.acquire()
        self.log = log
        try:
            log.refresh()
        except OSError:
            log._start()
        return log

    def __exit__(self, *exc):
        if self.log is not None:
            self.log.lock.release()
        return False


def _started(run):
    path = _path(run, STARTED)
    if path is None:
        return None
    try:
        with open(path, 'rb') as handle:
            value = json.loads(handle.read(STARTED_BYTES).decode('utf-8'))
    except (OSError, UnicodeDecodeError, ValueError, RecursionError):
        return None
    if isinstance(value, dict) and value.get('format') == STARTED_FORMAT and isinstance(value.get('started_at'), str):
        return value['started_at'][:64]
    return None


# ----------------------------------------------------------------------------- operations

def overview(run):
    """The operation training: what the run logged, by series, tensor, sample name and checkpoint."""
    present = run.root is not None and os.path.isdir(os.path.join(run.root, DIRECTORY))
    result = {'run': {'id': run.run_id, 'state': run.state, 'active': run.active}, 'present': present,
              'started_at': _started(run) if present else None, 'series': [], 'lines': 0, 'last_step': None,
              'last_time': None, 'other_keys': [], 'histograms': [], 'histogram_lines': 0, 'samples': [],
              'sample_lines': 0, 'checkpoints': [], 'problems': [], 'bad_lines': 0, 'truncated': False}
    if not present:
        return result
    problems = []
    with _Read(run, METRICS) as log:
        if log is not None:
            for name, (at, values) in log.series.items():
                low, high, last = log.stats.get(name, (None, None, None))
                result['series'].append({'name': name, 'points': len(values), 'nonfinite': log.nonfinite[name],
                                         'first_step': log.steps[at[0]] if at else None,
                                         'last_step': log.steps[at[-1]] if at else None, 'last': last,
                                         'min': low, 'max': high})
            result['lines'] = len(log.steps)
            if log.steps:
                result['last_step'], result['last_time'] = log.steps[-1], log.times[-1]
            result['other_keys'] = list(log.other_keys)
            _gather(result, problems, log)
    with _Read(run, HISTOGRAMS) as log:
        if log is not None:
            for (name, kind), (steps, _times, _offsets, _lengths) in log.pairs.items():
                result['histograms'].append({'name': name, 'kind': kind, 'rows': len(steps),
                                             'first_step': steps[0], 'last_step': steps[-1]})
            result['histogram_lines'] = sum(len(held[0]) for held in log.pairs.values())
            _gather(result, problems, log)
    with _Read(run, SAMPLES) as log:
        if log is not None:
            names = collections.OrderedDict()
            for entry in log.entries:
                held = names.setdefault(entry['name'], {'name': entry['name'], 'count': 0, 'last_step': None})
                held['count'] += 1
                held['last_step'] = entry['step']
            result['samples'] = list(names.values())
            result['sample_lines'] = len(log.entries)
            _gather(result, problems, log)
    with _Read(run, CHECKPOINTS) as log:
        if log is not None:
            result['checkpoints'] = [dict(entry, figures=dict(entry['figures']))
                                     for entry in log.entries[-CHECKPOINTS_SHOWN:]]
            _gather(result, problems, log)
    result['problems'] = problems[:PROBLEMS]
    return result


def _gather(result, problems, log):
    result['bad_lines'] += log.bad
    result['truncated'] = result['truncated'] or log.truncated
    problems.extend(log.problems)


def series(run, wanted, *, most=1000):
    """The operation training_series: each wanted series ({name, size, since}) in buckets, from since when the
    page holds buckets of the same size."""
    answer = {'series': [], 'lines': 0}
    with _Read(run, METRICS) as log:
        if log is None:
            if run.root is None:
                raise ProjectError(f'Run {run.run_id} has no output directory yet.', 'not-found')
            for item in wanted:
                answer['series'].append(_empty(item['name']))
            return answer
        answer['lines'] = len(log.steps)
        for item in wanted:
            held = log.series.get(item['name'])
            if held is None:
                answer['series'].append(_empty(item['name']))
                continue
            answer['series'].append(_bucketed(log, item['name'], held, item.get('size', 0), item.get('since', 0),
                                              most))
    return answer


def _empty(name):
    return {'name': name, 'points': 0, 'nonfinite': 0, 'size': 1, 'first': 0, 'buckets': []}


def bucket_size(points, most):
    """The smallest power of two for which points make at most most buckets."""
    size = 1
    while (points + size - 1) // size > most:
        size *= 2
    return size


def _bucketed(log, name, held, size_held, since, most):
    at, values = held
    points = len(values)
    size = bucket_size(points, most)
    count = (points + size - 1) // size
    first = min(since, count) if size_held == size else 0
    buckets = []
    for number in range(first, count):
        low, high = number * size, min(points, (number + 1) * size)
        finite = [value for value in values[low:high] if not math.isnan(value)]
        if finite:
            mean = math.fsum(finite) / len(finite)
            if not math.isfinite(mean):  # the sum overflowed
                mean = math.fsum(value / len(finite) for value in finite)
            low_value, high_value = min(finite), max(finite)
        else:
            mean = low_value = high_value = None
        buckets.append([log.steps[at[low]], log.steps[at[high - 1]], log.times[at[high - 1]], mean, low_value,
                        high_value])
    return {'name': name, 'points': points, 'nonfinite': log.nonfinite[name], 'size': size, 'first': first,
            'buckets': buckets}


def _chosen(count, most):
    """Positions of count rows, evenly chosen when there are more than most; the first and the last kept."""
    if count <= most:
        return list(range(count)), 1
    if most == 1:
        return [count - 1], count
    picked = sorted({round(i * (count - 1) / (most - 1)) for i in range(most)})
    return picked, (count - 1) / (most - 1)


def histograms(run, *, name, kind, most=120, bins=48):
    """The operation training_histograms: one tensor's histograms over the steps, re-binned onto one grid."""
    with _Read(run, HISTOGRAMS) as log:
        held = log.pairs.get((name, kind)) if log is not None else None
        if held is None:
            raise ProjectError(f'Run {run.run_id} logged no histograms of the {kind} of {name}.', 'not-found')
        steps, times, offsets, lengths = held
        positions, stride = _chosen(len(steps), most)
        rows = []
        with open(log.path, 'rb') as handle:
            for position in positions:
                handle.seek(offsets[position])
                raw = handle.read(lengths[position])
                try:
                    value = json.loads(raw.decode('utf-8'))
                except (UnicodeDecodeError, ValueError, RecursionError):
                    value = None
                if not isinstance(value, dict) or histogram_problem(value) or value['name'] != name \
                        or value['kind'] != kind:
                    continue  # the file changed under the index: the next read finds it
                rows.append((steps[position], times[position], [float(e) for e in value['edges']],
                             [float(c) for c in value['counts']], _finite(value.get('nonfinite')) or 0))
    if not rows:
        raise ProjectError(f'The histograms of {name} could not be read again; ask again.', 'unsupported')
    low = min(row[2][0] for row in rows)
    high = max(row[2][-1] for row in rows)
    counts = [rebin(edges, row_counts, low, high, bins) for _s, _t, edges, row_counts, _n in rows]
    return {'name': name, 'kind': kind, 'rows': [{'step': s, 'time': t} for s, t, *_rest in rows],
            'stride': stride, 'low': low, 'high': high, 'bins': bins, 'counts': counts,
            'totals': [math.fsum(row[3]) for row in rows], 'nonfinite': sum(row[4] for row in rows)}


def rebin(edges, counts, low, high, bins):
    """counts over edges shared out onto bins equal bins over [low, high] by overlap (spread evenly in a bin)."""
    target = [0.0] * bins
    width = (high - low) / bins
    if not width > 0 or not math.isfinite(width):
        target[bins // 2] = math.fsum(counts)
        return target

    def at(x):
        return min(bins - 1, max(0, int((x - low) / width)))

    for index, count in enumerate(counts):
        if not count:
            continue
        a, b = edges[index], edges[index + 1]
        if not b > a:
            target[at(a)] += count
            continue
        first, last = at(a), at(b)
        if first == last:
            target[first] += count
            continue
        for place in range(first, last + 1):
            left = max(a, low + place * width)
            right = min(b, low + (place + 1) * width) if place < bins - 1 else b
            if right > left:
                target[place] += count * (right - left) / (b - a)
    return target


def _sample_shown(run, entry, index):
    address = f'{DIRECTORY}/{entry["path"]}'
    shown = dict(entry, index=index, bytes=None, problem=None)
    path = _path(run, entry['path'])
    if path is None:
        shown['problem'] = 'The file is missing.'
        return shown
    try:
        shown['bytes'] = os.path.getsize(path)
    except OSError:
        shown['problem'] = 'The file is missing.'
        return shown
    if entry['kind'] == 'image':
        shown['url'] = inside.file_url(run.run_id, address)
    return shown


def samples(run, *, name=None, offset=0, limit=50):
    """The operation training_samples: one page of the samples, of one name or all."""
    with _Read(run, SAMPLES) as log:
        if log is None:
            if run.root is None:
                raise ProjectError(f'Run {run.run_id} has no output directory yet.', 'not-found')
            return {'samples': [], 'total': 0}
        chosen = [(index, entry) for index, entry in enumerate(log.entries) if name is None or entry['name'] == name]
    return {'samples': [_sample_shown(run, entry, index) for index, entry in chosen[offset:offset + limit]],
            'total': len(chosen)}


@inside.reading
def _sample_content(product, run, shown):
    address = f'{DIRECTORY}/{shown["path"]}'
    if shown['kind'] == 'image':
        content = inside_shapes.image_content(locate(product.root, address))
        content['url'] = shown['url']
        return content
    return inside.array_slice(product, path=address, most=SAMPLE_SLICE)


def sample(run, *, index):
    """The operation training_sample: one sample with its content (an image's size, an array's slice)."""
    with _Read(run, SAMPLES) as log:
        entry = log.entries[index] if log is not None and index < len(log.entries) else None
    if entry is None:
        raise ProjectError(f'Run {run.run_id} logged no sample {index}.', 'not-found')
    shown = _sample_shown(run, entry, index)
    if shown['problem']:
        raise ProjectError(f'Sample {index} of run {run.run_id}: {shown["problem"]}', 'not-found')
    return {'sample': shown, 'content': _sample_content(run.product(), run, shown)}
