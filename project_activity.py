"""Bounded live observation from the ordinary project evidence reference.

The producer owns publication and meaning; this projection never grants Run
custody, execution, scientific verification or model acceptance.
"""
from datetime import datetime, timezone

from workbench import WorkbenchError

REFERENCE_ID = 'activity'
STATES = ('idle', 'running', 'completed', 'failed', 'cancelled')


def activity(value):
    required = {'schema_version', 'producer', 'sequence', 'updated_at', 'state', 'phase', 'message', 'progress'}
    if type(value) is not dict or set(value) != required or type(value['schema_version']) is not int or value['schema_version'] != 1:
        raise WorkbenchError('Unsupported project activity publication.')
    for name, bound in (('producer', 120), ('phase', 120), ('message', 1000), ('updated_at', 80)):
        item = value[name]
        if (type(item) is not str or not item or len(item) > bound
                or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in item)):
            raise WorkbenchError('Invalid activity ' + name + '.')
    if type(value['sequence']) is not int or not 0 <= value['sequence'] < 2**53 or value['state'] not in STATES:
        raise WorkbenchError('Invalid activity sequence or state.')
    try:
        stamp = datetime.fromisoformat(value['updated_at'])
        if stamp.tzinfo is None or stamp.utcoffset().total_seconds() != 0:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise WorkbenchError('Activity time must be an ISO UTC timestamp.') from None
    progress = value['progress']
    if type(progress) is not dict or set(progress) != {'completed', 'total'}:
        raise WorkbenchError('Invalid activity progress.')
    done, total = progress['completed'], progress['total']
    if type(done) is not int or not 0 <= done < 2**53 or (total is not None and (type(total) is not int or not done <= total < 2**53)):
        raise WorkbenchError('Invalid activity progress bounds.')
    age = max(0, (datetime.now(timezone.utc) - stamp).total_seconds())
    return {**value, 'available': True, 'age_s': age, 'stale': value['state'] == 'running' and age > 10,
            'authority': 'external_observation'}
