"""Benchmark result summaries: the statistics and the results/<benchmark>.csv files.

Owns how a list of measured values becomes one summary row, and how summary rows
are written to, read from and checked in a project folder's results/ directory.
The format is section 2.8 of docs/plans/definition-first-projects/spec-m1-m2.md.
"""
import csv
import io
import math
import re
from dataclasses import dataclass
from datetime import datetime

COLUMNS = ('subject', 'metric', 'group', 'count', 'unavailable', 'mean', 'median',
           'p10', 'p90', 'min', 'max', 'commit', 'produced')
STATISTICS = ('mean', 'median', 'p10', 'p90', 'min', 'max')

HEADER = ','.join(COLUMNS)
_INTEGER = re.compile(r'[0-9]+')
# A finite decimal number, including the exponent form repr(float) uses (1e-05).
_DECIMAL = re.compile(r'-?[0-9]+(\.[0-9]+)?([eE][-+]?[0-9]+)?')
_COMMIT = re.compile(r'[0-9a-f]{40}')
_PRODUCED_FORMATS = ((re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}'), '%Y-%m-%d'),
                     (re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z'),
                      '%Y-%m-%dT%H:%M:%SZ'))


@dataclass(frozen=True)
class SummaryRow:
    """One line of a results file. The six statistics are None when count is 0."""
    subject: str
    metric: str
    group: str
    count: int
    unavailable: int
    mean: float | None
    median: float | None
    p10: float | None
    p90: float | None
    min: float | None
    max: float | None
    commit: str
    produced: str


def summarise(values, unavailable=0):
    """Return {'count', 'unavailable', 'mean', 'median', 'p10', 'p90', 'min', 'max'} for measured values."""
    if isinstance(unavailable, bool) or not isinstance(unavailable, int) or unavailable < 0:
        raise ValueError('unavailable must be an integer of at least 0')
    ordered = sorted(float(value) for value in values)
    if not all(math.isfinite(value) for value in ordered):
        raise ValueError('measured values must be finite numbers')
    summary = {'count': len(ordered), 'unavailable': unavailable}
    if not ordered:
        summary.update((name, None) for name in STATISTICS)
        return summary
    summary.update(
        mean=math.fsum(ordered) / len(ordered),
        median=_percentile(ordered, 5),
        p10=_percentile(ordered, 1),
        p90=_percentile(ordered, 9),
        min=ordered[0],
        max=ordered[-1],
    )
    return summary


def _percentile(ordered, tenths):
    """Linear interpolation at position (tenths / 10) * (count - 1), computed without rounding the position."""
    lower, remainder = divmod(tenths * (len(ordered) - 1), 10)
    if remainder == 0:
        return ordered[lower]
    low, high = ordered[lower], ordered[lower + 1]
    return low + (high - low) * (remainder / 10)


def _sort_key(row):
    return (row.subject, row.metric, row.group)


def write_results(rows):
    """Return the text of a results file for these SummaryRow items, sorted as the format requires."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator='\n')
    writer.writerow(COLUMNS)
    for row in sorted(rows, key=_sort_key):
        cells = []
        for column in COLUMNS:
            value = getattr(row, column)
            if column in STATISTICS:
                cells.append('' if value is None else repr(float(value)))
            elif column in ('count', 'unavailable'):
                cells.append(str(int(value)))
            else:
                cells.append(value)
        writer.writerow(cells)
    return buffer.getvalue()


def _records(text):
    """Return ([(first physical line number, cells)], error), error being None or (line number, message)."""
    reader = csv.reader(io.StringIO(text, newline=''), strict=True)
    records = []
    previous_end = 0
    try:
        for cells in reader:
            records.append((previous_end + 1, cells))
            previous_end = reader.line_num
    except csv.Error as error:
        return records, (reader.line_num, str(error))
    return records, None


def read_results(text):
    """Return the SummaryRow items of a results file's text; raise ValueError on a malformed file."""
    rows = []
    records, error = _records(text)
    if error is not None:
        raise ValueError(f'line {error[0]}: results file is not valid CSV: {error[1]}')
    if not records or text.split('\n', 1)[0] != HEADER:
        raise ValueError(f'results file must start with the header {HEADER}')
    for line, cells in records[1:]:
        if len(cells) != len(COLUMNS):
            raise ValueError(f'line {line}: expected {len(COLUMNS)} cells, found {len(cells)}')
        fields = dict(zip(COLUMNS, cells))
        for column in ('count', 'unavailable'):
            if not _INTEGER.fullmatch(fields[column]):
                raise ValueError(f'line {line}: {column} must be an integer of at least 0')
            fields[column] = int(fields[column])
        for column in STATISTICS:
            if fields[column] == '':
                fields[column] = None
            elif _DECIMAL.fullmatch(fields[column]):
                fields[column] = float(fields[column])
            else:
                raise ValueError(f'line {line}: {column} must be a decimal number or empty')
        rows.append(SummaryRow(**fields))
    return rows


def _benchmark_names(benchmark_document):
    """Return (subject names, metric ids, group_by keys, required statistics) read defensively."""
    document = benchmark_document if isinstance(benchmark_document, dict) else {}

    def strings(items, field):
        if not isinstance(items, list):
            return set()
        return {item[field] for item in items
                if isinstance(item, dict) and isinstance(item.get(field), str)}

    summary = document.get('summary') if isinstance(document.get('summary'), dict) else {}
    group_by = summary.get('group_by')
    group_by = {key for key in group_by if isinstance(key, str)} if isinstance(group_by, list) else set()
    statistics = summary.get('statistics')
    if isinstance(statistics, list):
        statistics = [name for name in STATISTICS if name in statistics]
    else:
        statistics = list(STATISTICS)
    return (strings(document.get('subjects'), 'name'), strings(document.get('metrics'), 'id'),
            group_by, statistics)


def _group_problems(group, group_by):
    """Return the messages for a group cell that breaks the key=value;key=value rule."""
    if group == '':
        return []
    if '\n' in group or '\r' in group:
        return ['group may not contain a line break.']
    keys = []
    for pair in group.split(';'):
        key, separator, value = pair.partition('=')
        if not separator or '=' in value:
            return [f'group pair {pair!r} must be exactly one key=value.']
        keys.append(key)
    messages = [f'group key {key!r} is not in the benchmark\'s summary.group_by.'
                for key in keys if key not in group_by]
    if len(set(keys)) != len(keys):
        messages.append('group keys must not repeat.')
    elif keys != sorted(keys):
        messages.append('group keys must be sorted.')
    return messages


def _produced_is_valid(produced):
    for pattern, date_format in _PRODUCED_FORMATS:
        if pattern.fullmatch(produced):
            try:
                datetime.strptime(produced, date_format)
            except ValueError:
                return False
            return True
    return False


def _row_problems(fields, subjects, metrics, group_by, statistics):
    """Return the messages for one record's thirteen cells, each a sentence without its leading 'The '."""
    messages = []
    if fields['subject'] not in subjects:
        messages.append(f'subject {fields["subject"]!r} is not a subject of the benchmark.')
    if fields['metric'] not in metrics:
        messages.append(f'metric {fields["metric"]!r} is not a metric id of the benchmark.')
    messages.extend(_group_problems(fields['group'], group_by))
    for column in ('count', 'unavailable'):
        if not _INTEGER.fullmatch(fields[column]):
            messages.append(f'{column} {fields[column]!r} must be an integer of at least 0.')
    for column in STATISTICS:
        value = fields[column]
        if value != '' and not _DECIMAL.fullmatch(value):
            messages.append(f'{column} {value!r} must be a decimal number or empty.')
    if _INTEGER.fullmatch(fields['count']):
        if int(fields['count']) == 0:
            filled = [column for column in STATISTICS if fields[column] != '']
            if filled:
                messages.append(f'statistics must be empty when count is 0: {", ".join(filled)}.')
        else:
            missing = [column for column in statistics if fields[column] == '']
            if missing:
                messages.append(f'statistics are missing although count is above 0: {", ".join(missing)}.')
    if fields['commit'] != '' and not _COMMIT.fullmatch(fields['commit']):
        messages.append('commit must be 40 lowercase hexadecimal characters or empty.')
    if not _produced_is_valid(fields['produced']):
        messages.append(f'produced {fields["produced"]!r} must be YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ.')
    return messages


def check_results(text, benchmark_document):
    """Return a list of (severity, pointer, message) problems for a results file against its benchmark."""
    if isinstance(text, (bytes, bytearray)):
        try:
            text = bytes(text).decode('utf-8')
        except UnicodeDecodeError:
            return [('error', '', 'The results file is not UTF-8.')]
    if not isinstance(text, str):
        return [('error', '', 'The results file could not be read as text.')]
    problems = []
    if text == '':
        return [('error', '', 'The results file is empty; it must start with the header line.')]
    if '\r' in text:
        problems.append(('error', '', 'The results file must use \\n line ends, without \\r.'))
    if not text.endswith('\n'):
        problems.append(('warning', '', 'The results file does not end with a line end.'))
    records, error = _records(text)
    header_is_exact = text.split('\n', 1)[0].rstrip('\r') == HEADER
    problems.extend(_record_problems(records, header_is_exact, benchmark_document))
    if error is not None:
        problems.append(('error', f'line {error[0]}', f'The line is not valid RFC 4180 CSV: {error[1]}.'))
    return problems


def _record_problems(records, header_is_exact, benchmark_document):
    """Return the problems of the header and the rows that parsed as CSV, in line order."""
    problems = []
    if not records:
        return problems
    if not header_is_exact:
        problems.append(('error', 'line 1', f'The first line must be exactly {HEADER}.'))
        return problems
    subjects, metrics, group_by, statistics = _benchmark_names(benchmark_document)
    seen = set()
    previous = None
    for line, cells in records[1:]:
        pointer = f'line {line}'
        if not cells:
            problems.append(('error', pointer, 'Empty lines are not allowed.'))
            continue
        if len(cells) != len(COLUMNS):
            problems.append(('error', pointer,
                             f'The line has {len(cells)} cells; it must have {len(COLUMNS)}.'))
            continue
        fields = dict(zip(COLUMNS, cells))
        for message in _row_problems(fields, subjects, metrics, group_by, statistics):
            problems.append(('error', pointer, 'The ' + message))
        key = (fields['subject'], fields['metric'], fields['group'])
        if key in seen:
            problems.append(('error', pointer,
                             'The row repeats an earlier (subject, metric, group).'))
        elif previous is not None and key < previous:
            problems.append(('error', pointer,
                             'The row is out of order; rows are sorted by subject, metric and group.'))
        seen.add(key)
        previous = key if previous is None or key > previous else previous
    return problems
