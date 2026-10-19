"""Bounded diagnostic owner clocks, separate from admission and result proof."""
import copy
from collections import OrderedDict
from contextlib import contextmanager
import json
import re
import threading

from recipe_process import PhaseTimings, PHASE_NAMES, PHASE_WAIT_REASONS, PHASE_MAX_MS

MAX_RECORDS = 4
MAX_BYTES = 32 * 1024
OWNER_PHASES = {
    'pipeline': {'prepare', 'capture'},
    'runs': {'catalog_lock_wait', 'queue', 'launch_verification', 'output_validation',
             'publication', 'recovery_verification', 'recovery_publication'},
    'custodian': {'custodian_preparation', 'go_wait', 'runtime_verification', 'leader_lifetime', 'drain'},
}


def validate_record(value):
    """Closed stored shape; an untrusted clock never supplies execution authority."""
    def natural(number, maximum):
        if type(number) is not int or not 0 <= number <= maximum:
            raise ValueError('Invalid diagnostic timing number.')
    if (type(value) is not dict or set(value) != {'format', 'owner', 'clock_id', 'observed_at_ms', 'dropped_spans', 'spans'}
            or value['format'] != 'owner_phase_timings_v1'
            or value['owner'] not in ('pipeline', 'runs', 'custodian')
            or type(value['clock_id']) is not str or not re.fullmatch('[a-f0-9]{32}', value['clock_id'])
            or type(value['spans']) is not list or len(value['spans']) > 32):
        raise ValueError('Invalid owner timing record.')
    natural(value['observed_at_ms'], 2**53-1); natural(value['dropped_spans'], 2**31-1)
    sequences = set()
    for item in value['spans']:
        if (type(item) is not dict or set(item) != {'sequence', 'phase', 'state', 'started_offset_ms', 'ended_offset_ms', 'elapsed_ms', 'wait_reason'}
                or item['phase'] not in PHASE_NAMES or item['phase'] not in OWNER_PHASES[value['owner']]
                or item['state'] not in ('open', 'measured', 'incomplete')
                or item['wait_reason'] not in (*PHASE_WAIT_REASONS, None)):
            raise ValueError('Invalid owner timing span.')
        natural(item['sequence'], 2**31-1)
        if item['sequence'] == 0 or item['sequence'] in sequences: raise ValueError('Duplicate diagnostic sequence.')
        sequences.add(item['sequence'])
        natural(item['started_offset_ms'], PHASE_MAX_MS); natural(item['elapsed_ms'], PHASE_MAX_MS)
        if item['started_offset_ms'] + item['elapsed_ms'] > PHASE_MAX_MS:
            raise ValueError('Diagnostic offset exceeds its owner clock bound.')
        if item['state'] == 'measured':
            natural(item['ended_offset_ms'], PHASE_MAX_MS)
            if item['ended_offset_ms'] - item['started_offset_ms'] != item['elapsed_ms']:
                raise ValueError('Diagnostic duration differs from its own clock.')
        elif item['ended_offset_ms'] is not None:
            raise ValueError('Unfinished diagnostic span claims an end.')
        if item['state'] != 'open' and item['wait_reason'] is not None:
            raise ValueError('Closed diagnostic span claims a current wait.')
    return copy.deepcopy(value)


def retained(records):
    if type(records) is not list or len(records) > MAX_RECORDS:
        raise ValueError('Excessive timing records.')
    if len(json.dumps(records, allow_nan=False).encode()) > MAX_BYTES:
        raise ValueError('Excessive diagnostic timing bytes.')
    result = [validate_record(item) for item in records]
    if len({item['clock_id'] for item in result}) != len(result): raise ValueError('Duplicate owner clock.')
    return result


def incomplete(record):
    result = validate_record(record)
    for item in result['spans']:
        if item['state'] == 'open': item.update(state='incomplete', wait_reason=None)
    return result


class Book:
    """At most 64 live histories; eviction only loses diagnostic granularity."""
    def __init__(self):
        self._records = OrderedDict()
        self._lock = threading.RLock()

    def get(self, key):
        with self._lock:
            return self._records.get(key)

    def start(self, key, owner):
        with self._lock:
            record = PhaseTimings(owner)
            self._records[key] = record
            self._records.move_to_end(key)
            while len(self._records) > 64: self._records.popitem(last=False)
            return record

    def ensure(self, key, owner):
        with self._lock:
            return self._records.get(key) or self.start(key, owner)


@contextmanager
def observe(record, phase, reason=None):
    span = record.begin(phase, reason)
    try:
        yield
    except BaseException:
        record.finish(span, complete=False)
        raise
    else:
        record.finish(span)
