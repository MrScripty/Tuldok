"""The fields a run kept: its native (reference) and predicted fields, and their signed error, side by side.

Owns sections 1 and 2 of docs/plans/definition-first-projects/spec-d6.md. A
product keeps fields when the top of its directory holds INDEX
(field-index.json): a list of entries, each with a list of cases, each case
naming a predicted and a reference .npy (and optionally a mask) by a plain
file name at the top of the product. fields lists every case with whether it
can be compared and why not; the member a case stands for is named from
probe.json (format probe_v1) when the product holds one, and the figures the
run reported itself (numeric fields ending relative_l2 of a JSON file at the
top whose format ends _diagnostic_v1) are listed beside, never used.
field_compare reads one case: a slice of the native field, the predicted
field and their difference (predicted minus native) through two axes, as
array_slice draws one, and the error's figures over the whole field (inside
the mask, finite values only), in 64-bit floats with math.fsum and
math.sumprod. The figures of a case are kept (FIGURES_KEPT of them, least
recently used dropped) while its files are unchanged, so a slider moved reads
only the slice. Bounds: FIELD_VALUES values a field, INDEX_BYTES of the index,
JSON_BYTES of probe.json and of a diagnostic file, CASES cases listed. The
arrays are read by inside_arrays; nothing here writes, opens the project or
checks a hash: bytes is compared with the file and a mismatch is shown, not
refused.
"""
import collections
import json
import math
import operator
import os
import threading
from array import array
from itertools import compress, repeat

from . import inside, inside_arrays
from .inside_archive import locate
from .store import ProjectError

INDEX = 'field-index.json'
PROBE = 'probe.json'
PROBE_FORMAT = 'probe_v1'
DIAGNOSTIC_SUFFIX = '_diagnostic_v1'
REPORTED_SUFFIX = 'relative_l2'
FIELD_VALUES = 16_777_216        # values of one field
INDEX_BYTES = 4 * 1024 * 1024    # the field index
JSON_BYTES = 4 * 1024 * 1024     # probe.json, and a file looked at for a diagnostic
TOP_JSON_FILES = 500             # JSON files at the top looked at for a diagnostic
CASES = 10_000                   # cases listed
SLICE_MOST = 256                 # rows and columns of a slice
FIGURES_KEPT = 16                # cases whose whole-field figures are kept
NUMERIC = ('f', 'i', 'u')
MASKS = ('b', 'i', 'u')
_FIGURES = ('count', 'nonfinite', 'max_abs_error', 'mean_error', 'rmse', 'relative_l2', 'mean_free_relative_l2')
_lock = threading.Lock()
_kept = collections.OrderedDict()   # (root, entry, case, stamps) -> (figures, means)


def _refuse(message, code='unsupported'):
    raise ProjectError(message, code)


def forget_figures():
    with _lock:
        _kept.clear()


# ------------------------------------------------------------------ reading JSON at the top

def _json_at(product, name, most):
    """The decoded JSON of the file name at the top of the product, or None when there is none; refused when it is
    larger than most or not JSON."""
    try:
        place = locate(product.root, name)
    except ProjectError:
        return None
    if (place.size or 0) > most:
        _refuse(f'{name} is {place.size} bytes; at most {most} are read.', 'too-large')
    try:
        return json.loads(bytes(place.head(place.size or 0)).decode('utf-8'))
    except (ValueError, RecursionError):
        _refuse(f'{name} is not JSON.')


def _index(product):
    """The entries of the product's field index, or None when it keeps none; a damaged index is refused."""
    value = _json_at(product, INDEX, INDEX_BYTES)
    if value is None:
        try:
            locate(product.root, INDEX)
        except ProjectError:
            return None
    if not isinstance(value, list):
        _refuse(f'{INDEX} must be a list of entries.')
    for position, entry in enumerate(value):
        if not isinstance(entry, dict) or not isinstance(entry.get('cases'), list):
            _refuse(f'Entry {position} of {INDEX} must be an object with a list of cases.')
    return value


def _probe_members(product):
    """{member_ordinal: (member id, split)} from probe.json of format probe_v1; empty when there is none."""
    try:
        value = _json_at(product, PROBE, JSON_BYTES)
    except ProjectError:
        return {}
    if not isinstance(value, dict) or value.get('format') != PROBE_FORMAT or not isinstance(value.get('members'),
                                                                                              list):
        return {}
    found = {}
    for position, member in enumerate(value['members']):
        if not isinstance(member, dict):
            continue
        ordinal = member.get('ordinal', position)
        frozen = member.get('frozen_reference') if isinstance(member.get('frozen_reference'), dict) else {}
        identifier = frozen.get('member_id') if isinstance(frozen.get('member_id'), str) else None
        split = next((item for item in (frozen.get('split'), member.get('split'), value.get('split'))
                      if isinstance(item, str)), None)
        if type(ordinal) is int and (identifier or split):
            found.setdefault(ordinal, (identifier, split))
    return found


def _reported(product):
    """[{file, field, value}]: the numeric fields ending relative_l2 of each *_diagnostic_v1 file at the top."""
    out = []
    names = sorted(item.name for item in os.scandir(product.root)
                   if item.name.lower().endswith('.json') and item.name != INDEX)[:TOP_JSON_FILES]
    for name in names:
        try:
            place = locate(product.root, name)
            if (place.size or 0) > JSON_BYTES:
                continue
            raw = bytes(place.head(place.size or 0))
            if DIAGNOSTIC_SUFFIX.encode() not in raw:
                continue
            value = json.loads(raw.decode('utf-8'))
        except (ProjectError, ValueError, RecursionError):
            continue
        if not isinstance(value, dict) or not isinstance(value.get('format'), str) \
                or not value['format'].endswith(DIAGNOSTIC_SUFFIX):
            continue
        for field, item in value.items():
            if (field.endswith(REPORTED_SUFFIX) and isinstance(item, (int, float)) and not isinstance(item, bool)
                    and math.isfinite(item)):
                out.append({'file': name, 'field': field, 'value': item})
    return out


# ------------------------------------------------------------------ one case

def _name_of(part):
    """The file name a case's predicted, reference or mask names, or None."""
    return part.get('name') if isinstance(part, dict) and isinstance(part.get('name'), str) else None


def _plain_problem(name):
    if not name or '/' in name or '\\' in name or '..' in name or '!' in name or '\x00' in name:
        return f'{name!r} is not a plain file name at the top of the product'
    if not name.lower().endswith('.npy'):
        return f'{name} is not an .npy file'
    return None


class _Case:
    """One case of the index, its files read as far as their headers."""

    def __init__(self, product, entry, position, raw, members):
        self.entry, self.case = entry, position
        self.raw = raw if isinstance(raw, dict) else {}
        self.predicted = _name_of(self.raw.get('predicted'))
        self.reference = _name_of(self.raw.get('reference'))
        mask = self.raw.get('mask')
        self.mask = _name_of(mask)
        self.shape = self.dtype = None
        self.reason, self.code = None, 'unsupported'
        self.bytes_mismatch = []
        self.files = {}   # role -> (place, header)
        ordinal = self.raw.get('member_ordinal')
        member = members.get(ordinal) if type(ordinal) is int else None
        self.name = member[0] if member and member[0] else f'case {position}' if entry == 0 else \
            f'entry {entry} case {position}'
        self.split = member[1] if member else None
        if not isinstance(raw, dict):
            self.reason = 'The case is not a JSON object.'
            return
        if self.predicted is None or self.reference is None:
            self.reason = 'The case does not name its predicted and reference files.'
            return
        if mask is not None and self.mask is None:
            self.reason = 'The mask must be null or name a file.'
            return
        self.reason = self._read(product)

    def _read(self, product):
        roles = [('predicted', self.predicted), ('reference', self.reference)]
        if self.mask is not None:
            roles.append(('mask', self.mask))
        for role, name in roles:
            problem = _plain_problem(name)
            if problem:
                return f'The {role} file: {problem}.'
            try:
                place = locate(product.root, name)
            except ProjectError:
                return f'The {role} file {name} is not in the product.'
            declared = self.raw[role].get('bytes')
            if type(declared) is int and declared != place.size:
                self.bytes_mismatch.append(name)
            try:
                header = inside_arrays.read_header(place)
            except ProjectError as error:
                return f'The {role} file {name}: {error}'
            if header.problem is not None:
                return f'The {role} file {name} is {header.problem}.'
            if header.kind not in (MASKS if role == 'mask' else NUMERIC):
                return f'The {role} file {name} is of the type {header.dtype}, not ' + (
                    'a boolean or integer mask.' if role == 'mask' else 'a number.')
            try:
                inside_arrays.check_length(place.blob(), header, name)
            except ProjectError as error:
                return f'The {role} file: {error}'
            self.files[role] = (place, header)
        predicted, reference = self.files['predicted'][1], self.files['reference'][1]
        self.shape = reference.shape
        self.dtype = (predicted.dtype if predicted.dtype == reference.dtype
                      else f'{predicted.dtype} / {reference.dtype}')
        for role in ('predicted', 'mask'):
            if role in self.files and self.files[role][1].shape != reference.shape:
                return (f'The {role} file is of the shape {self.files[role][1].shape}; the reference is of the shape '
                        f'{reference.shape}.')
        if not 1 <= len(reference.shape) <= 4:
            return f'The fields have {len(reference.shape)} axes; one to four are compared.'
        if reference.count > FIELD_VALUES:
            self.code = 'too-large'
            return f'The fields have {reference.count} values each; at most {FIELD_VALUES} are compared.'
        return None

    def listed(self):
        details = {key: value for key, value in self.raw.items() if key not in ('predicted', 'reference', 'mask')}
        item = {'entry': self.entry, 'case': self.case, 'name': self.name, 'split': self.split,
                'predicted': self.predicted, 'reference': self.reference, 'mask': self.mask, 'shape': self.shape,
                'dtype': self.dtype, 'comparable': self.reason is None, 'details': details}
        if self.reason is not None:
            item['reason'] = self.reason
        if self.bytes_mismatch:
            item['bytes_mismatch'] = self.bytes_mismatch
        return item

    def stamps(self):
        out = []
        for role in ('predicted', 'reference', 'mask'):
            if role in self.files:
                info = os.stat(self.files[role][0].path)
                out.append((role, info.st_size, info.st_mtime_ns, info.st_ino))
        return tuple(out)


def _cases(product, entries, members):
    found = []
    for entry, item in enumerate(entries):
        for position, raw in enumerate(item['cases']):
            if len(found) >= CASES:
                return found, True
            found.append(_Case(product, entry, position, raw, members))
    return found, False


@inside.reading
def fields(product):
    """{kept, cases, reported}: every case of the product's field index, and the figures the run reported."""
    entries = _index(product)
    if entries is None:
        return {'kept': False, 'cases': [], 'reported': [], 'more': False}
    found, more = _cases(product, entries, _probe_members(product))
    return {'kept': True, 'cases': [case.listed() for case in found], 'reported': _reported(product), 'more': more}


# ------------------------------------------------------------------ figures

def _finite(values):
    """Whether every value is finite (one sum when it is finite, else value by value)."""
    try:
        if math.isfinite(math.fsum(values)):
            return True
    except (OverflowError, ValueError):
        pass
    return all(map(math.isfinite, values))


def _number(compute):
    """compute(), or None when it overflows or is not a finite number."""
    try:
        value = compute()
    except (OverflowError, ValueError, ZeroDivisionError):
        return None
    return value if value is not None and math.isfinite(value) else None


def _figures(predicted, reference, inside_mask):
    """(figures over the inside cells whose two values are finite, (mean predicted, mean reference) or None)."""
    if inside_mask is not None:
        predicted = array('d', compress(predicted, inside_mask))
        reference = array('d', compress(reference, inside_mask))
    nonfinite = 0
    if not (_finite(predicted) and _finite(reference)):
        good_p, good_r = list(map(math.isfinite, predicted)), list(map(math.isfinite, reference))
        nonfinite = good_p.count(False) + good_r.count(False)
        keep = list(map(operator.and_, good_p, good_r))
        predicted, reference = array('d', compress(predicted, keep)), array('d', compress(reference, keep))
    count = len(reference)
    figures = dict.fromkeys(_FIGURES)
    figures.update(count=count, nonfinite=nonfinite)
    if not count:
        return figures, None
    error = array('d', map(operator.sub, predicted, reference))
    squares = _number(lambda: math.sumprod(error, error))
    norm_reference = _number(lambda: math.sqrt(math.sumprod(reference, reference)))
    figures['max_abs_error'] = _number(lambda: max(map(abs, error)))
    figures['mean_error'] = _number(lambda: math.fsum(error) / count)
    figures['rmse'] = _number(lambda: math.sqrt(squares / count)) if squares is not None else None
    if squares is not None and norm_reference:
        figures['relative_l2'] = _number(lambda: math.sqrt(squares) / norm_reference)
    mean_p = _number(lambda: math.fsum(predicted) / count)
    mean_r = _number(lambda: math.fsum(reference) / count)
    means = None
    if mean_p is not None and mean_r is not None:
        means = (mean_p, mean_r)
        free_p = array('d', map(operator.sub, predicted, repeat(mean_p)))
        free_r = array('d', map(operator.sub, reference, repeat(mean_r)))
        free_error = array('d', map(operator.sub, free_p, free_r))
        free_norm = _number(lambda: math.sqrt(math.sumprod(free_r, free_r)))
        free_squares = _number(lambda: math.sumprod(free_error, free_error))
        if free_norm and free_squares is not None:
            figures['mean_free_relative_l2'] = _number(lambda: math.sqrt(free_squares) / free_norm)
    return figures, means


def _whole_figures(product, case):
    key = (product.root, case.entry, case.case, case.stamps())
    with _lock:
        if key in _kept:
            _kept.move_to_end(key)
            return _kept[key]
    values = {role: inside_arrays.c_order_values(place.blob(), header, place.address)
              for role, (place, header) in case.files.items()}
    inside_mask = None
    if 'mask' in values:
        inside_mask = [1 if value else 0 for value in values['mask']]
    found = _figures(values['predicted'], values['reference'], inside_mask)
    with _lock:
        _kept[key] = found
        while len(_kept) > FIGURES_KEPT:
            _kept.popitem(last=False)
    return found


# ------------------------------------------------------------------ the slice

def _drawn(ndim, axis):
    """(the two axes drawn or [0] for one axis, the axis cut across or None) of a field of ndim axes."""
    if ndim == 1:
        return [0], None
    if ndim == 2:
        return [0, 1], None
    if axis is None:
        axis = ndim - 1
    if not 0 <= axis < ndim:
        _refuse(f'axis must be one of the {ndim} axes of the fields.', 'invalid')
    return [other for other in range(ndim) if other != axis][-2:], axis


@inside.reading
def field_compare(product, *, entry, case, axis=None, index=None, mean_free=False):
    """A slice of one kept case's native, predicted and signed error fields, with the error's whole-field figures."""
    entries = _index(product)
    if entries is None:
        _refuse('This product keeps no fields.', 'not-found')
    if not 0 <= entry < len(entries) or not 0 <= case < len(entries[entry]['cases']):
        _refuse(f'There is no case {case} of entry {entry} in {INDEX}.', 'not-found')
    found = _Case(product, entry, case, entries[entry]['cases'][case], {})
    if found.reason is not None:
        _refuse(f'Case {case} of entry {entry} cannot be compared: {found.reason}', found.code)
    figures, means = _whole_figures(product, found)
    shape, ndim = found.shape, len(found.shape)
    axes, axis = _drawn(ndim, axis)
    if index is None:
        index = [size // 2 for size in shape]
    if len(index) != ndim:
        _refuse(f'index must give one position for each of the {ndim} axes of the fields.', 'invalid')
    index = list(index)
    sliced = {}
    for role, (place, header) in found.files.items():
        _, _, rows, columns, stride, values = inside_arrays.slice_values(place.blob(), header, role, axes=axes,
                                                                          index=index, most=SLICE_MOST)
        sliced[role] = values
    reference, predicted = sliced['reference'], sliced['predicted']
    inside_cells = [bool(value) for value in sliced['mask']] if 'mask' in sliced else None
    shift_p, shift_r = means if mean_free and means is not None else (0.0, 0.0)
    nan = math.nan
    shown_r, shown_p, error = [], [], []
    low = high = None
    limit = None
    for position, (r, p) in enumerate(zip(reference, predicted)):
        if inside_cells is not None and not inside_cells[position]:
            shown_r.append(nan)
            shown_p.append(nan)
            error.append(nan)
            continue
        r, p = float(r), float(p)
        shown_r.append(r)
        shown_p.append(p)
        for value in (r, p):
            if math.isfinite(value):
                low = value if low is None or value < low else low
                high = value if high is None or value > high else high
        try:
            difference = (p - shift_p) - (r - shift_r)
        except OverflowError:
            difference = nan
        error.append(difference)
        if math.isfinite(difference):
            limit = abs(difference) if limit is None or abs(difference) > limit else limit
    return {'entry': entry, 'case': case, 'shape': shape, 'dtype': found.dtype, 'axes': axes, 'axis': axis,
            'index': index, 'rows': rows, 'columns': columns, 'stride': stride, 'mean_free': bool(mean_free),
            'reference_f32': inside_arrays.float32_base64(shown_r),
            'predicted_f32': inside_arrays.float32_base64(shown_p),
            'error_f32': inside_arrays.float32_base64(error),
            'range': None if low is None else [low, high], 'error_limit': limit, 'figures': figures}
