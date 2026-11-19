"""Write the training files Tuldok reads, from a project's own training script.

Owns section 3 of docs/plans/training-and-curation/spec-t1.md; the files are
those of its section 2, under training/ of the run's output directory:

    from tuldok_log import Logger, autolog
    log = Logger(output)
    log.log(step, loss=0.21, lr=1e-3)
    log.log_histograms(step, model)
    log.log_sample(step, 'prediction', png_bytes_or_array)

    track = autolog(model, optimizer, directory=output, every=10, loss=criterion)

A project's script imports this in the project's environment; Tuldok's server
never does. Standard library only: PyTorch is imported only inside autolog,
and the functions that take a model or a tensor use the object's own methods
(named_parameters, detach, histc, numpy) without importing anything. Every
line is written whole with one write() on a file opened for appending, so a
reader sees whole lines (or, while a write lands, a partial last line it
leaves for later). A sample's file is written under a temporary name and
renamed before its line is appended to samples.jsonl.
"""
import datetime
import json
import math
import os
import re
import struct
import threading
import time

__all__ = ['Logger', 'autolog', 'Autolog']
__version__ = '1'

DIRECTORY = 'training'
METRICS = 'metrics.jsonl'
HISTOGRAMS = 'histograms.jsonl'
SAMPLES = 'samples.jsonl'
CHECKPOINTS = 'checkpoints.jsonl'
STARTED = 'training.json'
FORMAT = 'tuldok_training_v1'
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
KINDS = ('weights', 'gradients')
_RESERVED = ('step', 'time', 'epoch')
_SAFE = re.compile(r'[^A-Za-z0-9._-]+')
# NumPy's type codes that an .npy written here may carry (numeric only).
_NUMERIC_KINDS = ('f', 'i', 'u', 'b')


def _scalar(value):
    """value as a JSON number, or None when it is not finite (a tensor of one value is read with item())."""
    if hasattr(value, 'item') and not isinstance(value, (int, float)):
        value = value.item()
    number = float(value)
    return number if math.isfinite(number) else None


def _line(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')) + '\n').encode('utf-8')


class Logger:
    """Writes the training files of one run into <directory>/training/.

    directory is the run's output directory (the {output} a recipe's command is
    given). The clock (each line's time) starts when the Logger is made.
    """

    def __init__(self, directory):
        self.directory = os.path.join(os.fspath(directory), DIRECTORY)
        os.makedirs(os.path.join(self.directory, 'samples'), exist_ok=True)
        self._start = time.monotonic()
        self._lock = threading.Lock()
        self._files = {}
        started = os.path.join(self.directory, STARTED)
        if not os.path.exists(started):
            stamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
            self._replace(started, json.dumps({'format': FORMAT, 'started_at': stamp,
                                               'helper': 'tuldok_log ' + __version__}).encode('utf-8') + b'\n')

    # ---------------------------------------------------------------- plumbing

    def elapsed(self):
        """Seconds since the Logger was made."""
        return round(time.monotonic() - self._start, 6)

    def _append(self, name, value):
        data = _line(value)
        with self._lock:
            fd = self._files.get(name)
            if fd is None:
                fd = self._files[name] = os.open(os.path.join(self.directory, name),
                                                 os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
            written = os.write(fd, data)
            while written < len(data):  # a short write is rare on a regular file; finish the line
                written += os.write(fd, data[written:])

    @staticmethod
    def _replace(path, data):
        temporary = f'{path}.{os.getpid()}.{threading.get_ident()}.part'
        with open(temporary, 'wb') as handle:
            handle.write(data)
        os.replace(temporary, path)

    def close(self):
        with self._lock:
            for fd in self._files.values():
                os.close(fd)
            self._files.clear()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    # ----------------------------------------------------------------- metrics

    def log(self, step, *, epoch=None, **scalars):
        """One line of metrics.jsonl: step, time, epoch when given, and each named scalar (null when not finite)."""
        line = {'step': int(step), 'time': self.elapsed()}
        if epoch is not None:
            line['epoch'] = _scalar(epoch)
        for name, value in scalars.items():
            if name in _RESERVED:
                raise ValueError(f'{name} is not a name for a scalar; it is a key of every line.')
            line[name] = None if value is None else _scalar(value)
        self._append(METRICS, line)

    def checkpoint(self, step, path, **figures):
        """One line of checkpoints.jsonl: a checkpoint the script kept, by its path in the output directory."""
        line = {'step': int(step), 'time': self.elapsed(), 'path': os.fspath(path)}
        for name, value in figures.items():
            line[name] = None if value is None else _scalar(value)
        self._append(CHECKPOINTS, line)

    # -------------------------------------------------------------- histograms

    def log_histograms(self, step, model=None, *, tensors=None, kinds=KINDS, bins=32, most=64):
        """Lines of histograms.jsonl: for a model, each parameter's weights and (when it has one) its gradient; for
        tensors, a mapping of name to values, as weights. At most most tensors a call."""
        elapsed = self.elapsed()
        written = 0
        if model is not None:
            for name, parameter in model.named_parameters():
                if written >= most:
                    break
                for kind in kinds:
                    values = parameter if kind == 'weights' else getattr(parameter, 'grad', None)
                    if values is None:
                        continue
                    self._histogram(step, elapsed, name, kind, values, bins)
                written += 1
        for name, values in (tensors or {}).items():
            if written >= most:
                break
            self._histogram(step, elapsed, str(name), 'weights', values, bins)
            written += 1

    def _histogram(self, step, elapsed, name, kind, values, bins):
        edges, counts, nonfinite = histogram(values, bins)
        if edges is None:
            return
        line = {'step': int(step), 'time': elapsed, 'name': name, 'kind': kind, 'edges': edges, 'counts': counts}
        if nonfinite:
            line['nonfinite'] = nonfinite
        self._append(HISTOGRAMS, line)

    # ----------------------------------------------------------------- samples

    def log_sample(self, step, name, value):
        """A sample: PNG bytes as a .png, anything else (an array, a tensor, a nested list of numbers) as an .npy;
        written whole under samples/, then indexed in samples.jsonl. Returns its path relative to training/."""
        elapsed = self.elapsed()
        safe = _SAFE.sub('_', str(name)).strip('._') or 'sample'
        if isinstance(value, (bytes, bytearray, memoryview)):
            data = bytes(value)
            if not data.startswith(PNG_SIGNATURE):
                raise ValueError('A sample given as bytes must be a PNG.')
            extension = '.png'
        else:
            data = npy_bytes(value)
            extension = '.npy'
        relative = f'samples/{int(step):09d}-{safe[:80]}{extension}'
        self._replace(os.path.join(self.directory, relative), data)
        self._append(SAMPLES, {'step': int(step), 'time': elapsed, 'name': str(name), 'path': relative})
        return relative


# --------------------------------------------------------------------- histograms

def _flat(values):
    """The numbers of values as a flat list of floats: a tensor (detached, on the CPU), an object with tolist(), a
    nested sequence."""
    if hasattr(values, 'detach'):
        values = values.detach().cpu()
    if hasattr(values, 'tolist'):
        values = values.tolist()
    out = []
    stack = [values]
    while stack:
        item = stack.pop()
        if isinstance(item, (list, tuple)):
            stack.extend(reversed(item))
        else:
            out.append(float(item))
    return out


def histogram(values, bins=32):
    """(edges, counts, nonfinite) of values' finite numbers over bins equal bins; (None, None, n) when none is
    finite. A tensor is counted by its own histc (no copy to Python) when it has one."""
    bins = max(1, int(bins))
    if hasattr(values, 'histc') and hasattr(values, 'detach'):
        tensor = values.detach().float()
        finite = tensor[tensor.isfinite()] if hasattr(tensor, 'isfinite') else tensor
        nonfinite = int(tensor.numel() - finite.numel())
        if finite.numel() == 0:
            return None, None, nonfinite
        low, high = float(finite.min()), float(finite.max())
        if high == low:
            low, high = low - 0.5, high + 0.5
        counts = [int(c) for c in finite.histc(bins=bins, min=low, max=high).tolist()]
        return _edges(low, high, bins), counts, nonfinite
    numbers = _flat(values)
    finite = [n for n in numbers if math.isfinite(n)]
    nonfinite = len(numbers) - len(finite)
    if not finite:
        return None, None, nonfinite
    low, high = min(finite), max(finite)
    if high == low:
        low, high = low - 0.5, high + 0.5
    counts = [0] * bins
    width = (high - low) / bins
    for n in finite:
        counts[min(bins - 1, int((n - low) / width))] += 1
    return _edges(low, high, bins), counts, nonfinite


def _edges(low, high, bins):
    edges = [low + (high - low) * i / bins for i in range(bins + 1)]
    edges[-1] = high
    return edges


# ------------------------------------------------------------------------- .npy

def npy_bytes(value):
    """The bytes of an .npy (version 1.0, C order, little-endian) of value: an array with __array_interface__ or
    dtype/shape/tobytes (NumPy), a tensor (detached, on the CPU), or a nested list of numbers (as float32)."""
    if hasattr(value, 'detach'):
        value = value.detach().cpu()
        if hasattr(value, 'numpy'):
            try:
                value = value.numpy()
            except (RuntimeError, TypeError):  # PyTorch built without NumPy
                value = value.tolist()
        else:
            value = value.tolist()
    dtype = getattr(value, 'dtype', None)
    descr = getattr(dtype, 'str', None)
    if descr and hasattr(value, 'tobytes') and hasattr(value, 'shape'):
        if getattr(dtype, 'kind', descr[1:2]) not in _NUMERIC_KINDS:
            raise ValueError(f'A sample must be numeric; this one is of type {descr}.')
        if descr[0] == '>':
            value = value.byteswap()
            descr = '<' + descr[1:]
        shape = tuple(int(n) for n in value.shape)
        return _npy_header(descr, shape) + value.tobytes(order='C')
    shape, flat = _shape_of(value)
    return _npy_header('<f4', shape) + struct.pack(f'<{len(flat)}f', *flat)


def _shape_of(value):
    shape = []
    probe = value
    while isinstance(probe, (list, tuple)):
        shape.append(len(probe))
        if not probe:
            break
        probe = probe[0]
    flat = _flat(value)
    expected = 1
    for n in shape:
        expected *= n
    if expected != len(flat):
        raise ValueError('A sample given as a list must be rectangular.')
    return tuple(shape), flat


def _npy_header(descr, shape):
    shape_text = '(' + ', '.join(str(n) for n in shape) + (',)' if len(shape) == 1 else ')')
    header = "{'descr': '%s', 'fortran_order': False, 'shape': %s, }" % (descr, shape_text)
    padding = 64 - (10 + len(header) + 1) % 64
    header = header + ' ' * (padding % 64) + '\n'
    return b'\x93NUMPY\x01\x00' + struct.pack('<H', len(header)) + header.encode('latin-1')


# ---------------------------------------------------------------------- autolog

class Autolog:
    """What autolog() registered: hooks on the optimizer (and the loss module); note() adds scalars to the next line,
    close() removes the hooks. steps counts the optimizer's steps."""

    def __init__(self, model, optimizer, logger, every, histograms_every, loss, bins, most):
        import torch  # noqa: F401  (only here: autolog is for PyTorch)
        if not hasattr(optimizer, 'register_step_post_hook'):
            raise RuntimeError('autolog needs PyTorch 2.0 or later (optimizer step hooks).')
        self.model, self.optimizer, self.logger = model, optimizer, logger
        self.every, self.histograms_every = max(1, int(every)), max(1, int(histograms_every or every))
        self.bins, self.most = bins, most
        self.steps = 0
        self._losses, self._noted, self._grad_norm = [], {}, None
        self._handles = [optimizer.register_step_pre_hook(self._before), optimizer.register_step_post_hook(self._after)]
        if loss is not None:
            if not hasattr(loss, 'register_forward_hook'):
                raise TypeError('loss must be the loss module (an nn.Module) whose output is the loss.')
            self._handles.append(loss.register_forward_hook(self._loss_seen))

    def note(self, **scalars):
        """Scalars for the next line (loss among them: its mean since the last line is written)."""
        for name, value in scalars.items():
            if name == 'loss':
                self._losses.append(_scalar(value))
            else:
                self._noted[name] = value

    def _loss_seen(self, module, inputs, output):
        if hasattr(output, 'numel') and output.numel() == 1:
            self._losses.append(_scalar(output.detach()))

    def _due(self, every):
        return (self.steps + 1) % every == 0 or self.steps == 0

    def _before(self, optimizer, args, kwargs):
        if self._due(self.every):
            import torch
            norms = [p.grad.detach().float().norm(2) for group in optimizer.param_groups for p in group['params']
                     if p.grad is not None]
            self._grad_norm = float(torch.stack(norms).norm(2)) if norms else None
        if self._due(self.histograms_every):  # gradients exist only before the step (they may be zeroed after)
            self.logger.log_histograms(self.steps + 1, self.model, kinds=('gradients',), bins=self.bins,
                                       most=self.most)

    def _after(self, optimizer, args, kwargs):
        self.steps += 1
        step = self.steps
        if step % self.every == 0 or step == 1:
            scalars = {}
            losses = [value for value in self._losses if value is not None]
            if self._losses:
                scalars['loss'] = math.fsum(losses) / len(losses) if losses else None
            groups = optimizer.param_groups
            for index, group in enumerate(groups):
                if 'lr' in group:
                    scalars['lr' if len(groups) == 1 else f'lr/{index}'] = float(group['lr'])
            if self._grad_norm is not None:
                scalars['grad_norm'] = self._grad_norm
            scalars.update(self._noted)
            self.logger.log(step, **scalars)
            self._losses, self._noted, self._grad_norm = [], {}, None
        if step % self.histograms_every == 0 or step == 1:
            self.logger.log_histograms(step, self.model, kinds=('weights',), bins=self.bins, most=self.most)

    def close(self):
        for handle in self._handles:
            handle.remove()
        self._handles = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def autolog(model, optimizer, *, directory=None, logger=None, every=50, histograms_every=None, loss=None, bins=32,
            most=64):
    """Logs a PyTorch model's training through hooks, without the script naming what is logged.

    Every every optimizer steps (and after the first) one metrics line: the loss (the mean of those seen since the
    last line, when loss is the loss module or the script calls note(loss=...)), the learning rate of each
    parameter group, and the gradient norm over all parameters before the step. Every histograms_every steps
    (default every) the histograms of each parameter's weights (after the step) and gradients (before it). Give
    directory (the run's output) or logger. Returns the Autolog; close() removes the hooks.
    """
    if logger is None:
        if directory is None:
            raise TypeError('autolog needs directory (the run\'s output directory) or logger.')
        logger = Logger(directory)
    return Autolog(model, optimizer, logger, every, histograms_every, loss, bins, most)
