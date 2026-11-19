"""The steps Tuldok provides: import files into a dataset, freeze a dataset with splits from its annotations,
generate a dataset by asking a model a Pumas endpoint serves, embed a dataset's records through that endpoint,
and select some of a dataset's records.

Owns section 6 of docs/plans/definition-first-projects/spec-d4.md, section
3 of spec-d5.md and section 5 of docs/plans/training-and-curation/spec-t5.md
(embed, select, and freeze's records). A dataset whose run names a step (run.step) is built by
Tuldok's own interpreter running

    python -m tuldok_project.steps import <settings file> <output directory> --code <code root>
    python -m tuldok_project.steps freeze <settings file> <output directory> --records <input product> --tasks <file>
    python -m tuldok_project.steps generate <settings file> <output directory> --endpoint <address>
        --report <file> [--records <input product>]
    python -m tuldok_project.steps embed <settings file> <output directory> --endpoint <address>
        --report <file> --records <input product> --facts <file>
    python -m tuldok_project.steps select <settings file> <output directory> --records <input product>

with Tuldok's code first on the module path and the snapshot's code off it
(builds.py sets PYTHONSAFEPATH and PYTHONPATH). A step reads files and writes
its output directory; it opens no database, follows no symbolic link out of
its source, writes nowhere else and deletes nothing. It prints
tuldok_progress_v1 lines and, at its end, what it counted, one plain line
each. The standard library alone is used by import and freeze: the record
rules they share with inside.py (the kinds by extension, the pattern form, an
id's characters) are repeated here and a test keeps the two equal. generate
reaches the endpoint only through pumas.py, the one module that imports
Tuldok's client for it; it is given the machine's address by the build and
writes the address and the endpoint's version to its report file, which the
build keeps in the run's record.

embed reaches the endpoint the same way; the facts file the build writes
tells it which records it embeds (the input's reference and run), the
machine's embedder and prefix, and the output of the dataset's last run when
that run failed, from which it takes the rows already answered.

import_files, freeze_records, generate_records, embed_records and
select_records are the steps as functions on directories; main() is the
command line.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import threading
import time
import uuid

from . import annotations

KINDS = ('text', 'image', 'audio', 'pointcloud', 'mesh', 'array', 'file')
EXTENSIONS = {
    'text': ('.txt', '.md', '.json', '.jsonl', '.csv', '.tsv', '.yaml', '.yml', '.log'),
    'image': ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'),
    'audio': ('.wav', '.flac', '.mp3', '.ogg', '.opus', '.m4a'),
    'pointcloud': ('.xyz',),
    'mesh': ('.obj', '.stl'),
    'array': ('.npy', '.npz', '.safetensors'),
}
STEPS = ('import', 'freeze', 'generate', 'embed', 'select')
RECORD_LIST = 'records.jsonl'
FILES = 'files'
DEFAULT_PATTERN = '**/*'
DEFAULT_INCLUDE = ('accepted',)
ID_LIMIT = 200                      # characters of a record id (spec-d1)
LINE_BYTES = 64 * 1024              # one line of records.jsonl, and one text record (spec-d1)
HASH_LIMIT = 1024 ** 3              # a record over 1 GiB is not hashed (spec-d4 section 3)
PROGRESS_SECONDS = 0.5
PROGRESS_TOTAL = 1_000_000          # the most a progress line may count (launcher._event)
_ID = re.compile(r'[A-Za-z0-9._-]{1,200}')
_NOT_ID = re.compile(r'[^A-Za-z0-9._-]')
_SHA256 = re.compile(r'[0-9a-f]{64}')
_CHUNK = 1 << 20
MAKES = ('text', 'image')           # what generate makes (spec-d5.md section 3)
GENERATE_LIMIT = 100_000            # items one generate makes
RETRY_PAUSES = (1.0, 2.0)           # before asking again an item the endpoint did not admit; twice at most
EMBED_BATCH = 32                    # records one embed request carries, unless the definition says
EMBED_TEXT_BYTES = LINE_BYTES       # a text record embedded (inline, or a UTF-8 file)
EMBED_IMAGE_BYTES = 8 * 1024 * 1024 # an image embedded (the release's bound on one image)
SELECT_LIMIT = 20_000               # records one select (or freeze's records) names


class StepError(Exception):
    """A step that cannot go on; its message is printed and the step exits with status 1."""


# ------------------------------------------------------------------ shared

def kind_by_name(name, head=None):
    """The kind of a file by its extension; a .ply is a mesh when head() (its first bytes) declares faces."""
    extension = os.path.splitext(name.lower())[1]
    if extension == '.ply':
        return 'mesh' if head is not None and _ply_has_faces(head()) else 'pointcloud'
    return next((kind for kind, endings in EXTENSIONS.items() if extension in endings), 'file')


def _ply_has_faces(head):
    text = head.split(b'end_header', 1)[0].decode('ascii', 'replace')
    for line in text.splitlines():
        words = line.split()
        if len(words) == 3 and words[0] == 'element' and words[1] == 'face' and words[2].isdigit():
            return int(words[2]) > 0
    return False


def pattern_regex(text):
    """spec-d1's pattern form: * and ? within one segment, ** across segments."""
    out, at = [], 0
    while at < len(text):
        if text.startswith('**/', at):
            out.append('(?:.*/)?')
            at += 3
        elif text.startswith('**', at):
            out.append('.*')
            at += 2
        elif text[at] == '*':
            out.append('[^/]*')
            at += 1
        elif text[at] == '?':
            out.append('[^/]')
            at += 1
        else:
            out.append(re.escape(text[at]))
            at += 1
    return re.compile(''.join(out), re.S)


def id_from(text):
    """An id made from a path: '/' becomes '__', any other character outside A-Z a-z 0-9 . _ - becomes '_'."""
    made = _NOT_ID.sub('_', text.replace('/', '__'))
    return made[:ID_LIMIT] or '_'


def unique(name, used, limit=None):
    """name, or name with -2, -3, ... before its extension, whichever is not in used; added to used."""
    if name not in used:
        used.add(name)
        return name
    slash = name.rfind('/') + 1
    stem, extension = os.path.splitext(name[slash:])
    stem = name[:slash] + stem
    number = 2
    while True:
        tail = f'-{number}{extension}'
        candidate = (stem[:limit - len(tail)] if limit else stem) + tail
        if candidate not in used:
            used.add(candidate)
            return candidate
        number += 1


def sha256_file(path, limit=HASH_LIMIT):
    """(SHA-256 of the file, its size); the hash is None when the file is over limit."""
    with open(path, 'rb') as handle:
        size = os.fstat(handle.fileno()).st_size
        if size > limit:
            return None, size
        digest = hashlib.sha256()
        while True:
            chunk = handle.read(_CHUNK)
            if not chunk:
                return digest.hexdigest(), size
            digest.update(chunk)


def _sha256_text(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _line(record):
    return json.dumps(record, ensure_ascii=False, separators=(',', ':')) + '\n'


def _inside(path, root):
    return path == root or path.startswith(root + os.sep)


def _place(source, target):
    """Hard-link source to target, copying it when a link cannot be made (another file system); 'link' or 'copy'."""
    os.makedirs(os.path.dirname(target), exist_ok=True)
    try:
        os.link(source, target, follow_symlinks=False)
        return 'link'
    except OSError:
        shutil.copyfile(source, target, follow_symlinks=False)
        return 'copy'


class Progress:
    """Prints tuldok_progress_v1 lines: at the start, at most every PROGRESS_SECONDS, and at the end."""

    def __init__(self, stage, total, out):
        self.stage, self.total, self.out = stage, total, out
        self.last = 0.0

    def __call__(self, completed, metrics, *, final=False):
        now = time.monotonic()
        if not final and completed and now - self.last < PROGRESS_SECONDS:
            return
        self.last = now
        total = max(self.total, completed)
        if total > PROGRESS_TOTAL:
            completed, total = completed * PROGRESS_TOTAL // total, PROGRESS_TOTAL
        self.out(json.dumps({'format': 'tuldok_progress_v1', 'stage': self.stage, 'completed': completed,
                             'total': total, 'metrics': metrics}, separators=(',', ':')))


def _say(out, counts, words):
    for key, text in words:
        if counts.get(key):
            out(f'{counts[key]} {text}')


# ------------------------------------------------------------------- import

def _source_root(source, code_root):
    if os.path.isabs(source):
        root = source
    else:
        if code_root is None:
            raise StepError(f'The source {source!r} is relative to the code root, but no code root was given.')
        code_real = os.path.realpath(code_root)
        root = os.path.join(code_real, source)
        if not _inside(os.path.realpath(root), code_real):
            raise StepError(f'The source {source} leads outside the code root through a symbolic link.')
    real = os.path.realpath(root)
    if not os.path.isdir(real):
        raise StepError(f'The source {source} is not a directory here.')
    return real


def _walk(root, matches, counts):
    """[(path under the source, real path)] of the regular files the pattern takes, sorted bytewise in UTF-8."""
    found = []
    for directory, folders, names in os.walk(root):
        for name in list(folders):
            full = os.path.join(directory, name)
            if os.path.islink(full):
                folders.remove(name)   # never descended into; one inside the source is walked where it leads
                if not _inside(os.path.realpath(full), root):
                    counts['links_out'] += 1
        folders.sort()
        for name in names:
            full = os.path.join(directory, name)
            relative = os.path.relpath(full, root).replace(os.sep, '/')
            if not matches(relative):
                continue
            real = full
            if os.path.islink(full):
                real = os.path.realpath(full)
                if not _inside(real, root):
                    counts['links_out'] += 1
                    continue
            try:
                mode = os.stat(real).st_mode
            except OSError:
                counts['unreadable'] += 1
                continue
            if not stat.S_ISREG(mode):
                counts['not_files'] += 1
                continue
            try:
                relative.encode('utf-8')
            except UnicodeEncodeError:
                counts['names_not_utf8'] += 1
                continue
            found.append((relative, real))
    found.sort(key=lambda item: item[0].encode('utf-8'))
    return found


def _addresses(paths):
    """{path under the source: its address in the output}: files/<path>, or for a path holding '!' (which an
    address reads as an archive) the path with '_' for '!', made unique against every other address."""
    used = {f'{FILES}/{path}' for path in paths if '!' not in path}
    found = {path: f'{FILES}/{path}' for path in paths if '!' not in path}
    for path in paths:
        if '!' in path:
            found[path] = unique(f'{FILES}/{path.replace("!", "_")}', used)
    return found


def _line_texts(path, json_lines, counts):
    """(line number, text) of each non-empty line of a text file; a .jsonl line {"text": ...} gives that string."""
    with open(path, 'rb') as handle:
        for number, raw in enumerate(handle, 1):
            try:
                text = raw.decode('utf-8').rstrip('\n').rstrip('\r')
            except UnicodeDecodeError:
                counts['lines_not_utf8'] += 1
                continue
            if not text.strip():
                continue
            if json_lines:
                try:
                    value = json.loads(text)
                except (ValueError, RecursionError):
                    value = None
                if isinstance(value, dict) and isinstance(value.get('text'), str):
                    text = value['text']
                    if not text.strip():
                        continue
            yield number, text


def import_files(settings, output, *, code_root=None, out=print):
    """The import step: settings as section 6 gives them, into the existing directory output. Returns the counts."""
    source = settings['source']
    rights = settings['rights']
    chosen_kind = settings.get('kind')
    split_lines = settings.get('lines', False) is True
    root = _source_root(source, code_root)
    matches = pattern_regex(settings.get('pattern', DEFAULT_PATTERN)).fullmatch
    counts = dict.fromkeys(('records', 'files', 'lines', 'bytes', 'links_out', 'not_files', 'unreadable',
                            'names_not_utf8', 'lines_not_utf8', 'too_long', 'copied'), 0)
    found = _walk(root, matches, counts)
    addresses = _addresses([path for path, _ in found])
    progress = Progress('import', len(found), out)
    progress(0, {})
    used_ids = set()
    with open(os.path.join(output, RECORD_LIST), 'x', encoding='utf-8') as listing:
        for done, (path, real) in enumerate(found, 1):
            def head(real=real):
                with open(real, 'rb') as handle:
                    return handle.read(64 * 1024)
            kind = chosen_kind or kind_by_name(path, head)
            if split_lines and kind == 'text':
                for number, text in _line_texts(real, path.lower().endswith('.jsonl'), counts):
                    data = text.encode('utf-8')
                    record = {'id': None, 'kind': 'text', 'text': text, 'sha256': hashlib.sha256(data).hexdigest(),
                              'bytes': len(data), 'rights': rights, 'origin': {'path': path, 'line': number}}
                    if len(data) > LINE_BYTES or len(_line(record).encode('utf-8')) + ID_LIMIT > LINE_BYTES:
                        counts['too_long'] += 1
                        continue
                    record['id'] = unique(id_from(f'{path}/{number}'), used_ids, ID_LIMIT)
                    listing.write(_line(record))
                    counts['records'] += 1
                    counts['lines'] += 1
                    counts['bytes'] += len(data)
            else:
                address = addresses[path]
                if _place(real, os.path.join(output, *address.split('/'))) == 'copy':
                    counts['copied'] += 1
                digest, size = sha256_file(os.path.join(output, *address.split('/')))
                record = {'id': unique(id_from(path), used_ids, ID_LIMIT), 'kind': kind, 'path': address,
                          'sha256': digest, 'bytes': size, 'rights': rights, 'origin': {'path': path}}
                listing.write(_line(record))
                counts['records'] += 1
                counts['files'] += 1
                counts['bytes'] += size
            progress(done, {'records': counts['records'], 'links_out': counts['links_out']})
    progress(len(found), {'records': counts['records'], 'links_out': counts['links_out']}, final=True)
    out(f'{counts["records"]} records imported from {source}: {counts["files"]} files, {counts["lines"]} lines.')
    _say(out, counts, (('links_out', 'symbolic links leaving the source were skipped.'),
                       ('not_files', 'entries that are not regular files were skipped.'),
                       ('unreadable', 'entries that could not be read were skipped.'),
                       ('names_not_utf8', 'files whose names are not UTF-8 were skipped.'),
                       ('lines_not_utf8', 'lines that are not UTF-8 were skipped.'),
                       ('too_long', f'lines too long for a record ({LINE_BYTES} bytes) were skipped.'),
                       ('copied', 'files were copied, since they could not be linked.')))
    return counts


# ------------------------------------------------------------------- freeze

def _list_record(value):
    """A record from one decoded line of an input's records.jsonl (spec-d1's rules), or None."""
    if not isinstance(value, dict) or not isinstance(value.get('id'), str) or value.get('kind') not in KINDS:
        return None
    path, text = value.get('path'), value.get('text')
    if path is not None and (not isinstance(path, str) or not path):
        return None
    if path is None and (value['kind'] != 'text' or not isinstance(text, str)):
        return None
    return value


def _input_records(root, view, counts):
    """(records in order, {id: record}) of the input product: its records.jsonl, else every regular file."""
    listed = os.path.join(root, RECORD_LIST)
    records = []
    if os.path.isfile(listed) and not os.path.islink(listed):
        with open(listed, 'rb') as handle:
            for raw in handle:
                if not raw.strip():
                    continue
                try:
                    value = _list_record(json.loads(raw))
                except (ValueError, RecursionError):
                    value = None
                if value is None:
                    counts['bad_lines'] += 1
                else:
                    records.append(dict(value))
    elif view is not None:
        raise StepError('The input dataset is shown through a view, and freeze reads only a product\'s '
                        f'{RECORD_LIST} or its files; give the input a {RECORD_LIST}.')
    else:
        for directory, folders, names in os.walk(root):
            folders.sort()
            for name in names:
                full = os.path.join(directory, name)
                if os.path.islink(full) or not os.path.isfile(full):
                    continue
                address = os.path.relpath(full, root).replace(os.sep, '/')
                records.append({'id': address, 'kind': kind_by_name(address), 'path': address})
        records.sort(key=lambda record: record['id'].encode('utf-8', 'surrogateescape'))
    by_id = {}
    for record in records:
        if record['id'] in by_id:
            counts['bad_lines'] += 1
        else:
            by_id[record['id']] = record
    return by_id


def _record_hash(root, record):
    """The record's SHA-256: as its list gives it, else of its file or text; None over HASH_LIMIT or in an archive."""
    if 'hash' in record:
        return record['hash']
    given = record.get('sha256')
    if isinstance(given, str) and _SHA256.fullmatch(given):
        found = given
    elif record.get('path') is None:
        found = _sha256_text(record['text'])
    elif '!' in record['path']:
        found = None
    else:
        full = _confined(root, record['path'])
        found = sha256_file(full)[0] if full is not None else None
    record['hash'] = found
    return found


def _confined(root, address):
    """The real path of a regular file at address under root, or None when it is missing or leaves root."""
    full = os.path.realpath(os.path.join(root, *address.split('/')))
    return full if _inside(full, root) and full != root and os.path.isfile(full) else None


def _read_task(task):
    """(rows by record of the task's sound lines, how many lines were invalid)."""
    path, expected = task.get('lines'), task.get('sha256')
    if path is None:
        return {}, 0
    with open(path, 'rb') as handle:
        raw = handle.read(annotations.FILE_LIMIT + 1)
    if len(raw) > annotations.FILE_LIMIT:
        raise StepError(f'The annotations of {task["reference"]} are over {annotations.FILE_LIMIT} bytes.')
    if expected is not None and hashlib.sha256(raw).hexdigest() != expected:
        raise StepError(f'The annotations of {task["reference"]} are not the file the build read; build again.')
    parsed = annotations.read(raw, task['task'], task.get('vocabulary') or [])
    whole = [problem.message for problem in parsed.problems if problem.line is None and problem.severity == 'error']
    if whole:
        raise StepError(f'The annotations of {task["reference"]} cannot be read: {whole[0]}')
    return {row['record']: row for number, row in parsed.rows if number not in parsed.invalid}, len(parsed.invalid)


def _stale(row, record, root):
    """True when the annotation does not describe this record's content (or the record is gone)."""
    if record is None:
        return True
    return row['sha256'] is not None and row['sha256'] != _record_hash(root, record)


def _cut(count, shares):
    """[(split, start, end)] cutting count items by shares, the splits taken in the order of their names.

    By name, not as written: a definition's settings reach the step through
    the database, which keeps no order of an object's keys.
    """
    total = sum(shares.values())
    found, start, running = [], 0, 0
    for name, weight in sorted(shares.items()):
        running += weight
        end = count * running // total
        found.append((name, start, end))
        start = end
    return found


def order_key(seed, record_hash, identifier):
    """The key freeze orders records by: the SHA-256 of '<seed>:<record hash>' ('id:<id>' when it has none)."""
    tied = record_hash if record_hash is not None else f'id:{identifier}'
    return hashlib.sha256(f'{seed}:{tied}'.encode('utf-8')).hexdigest()


_FROZEN_KEYS = ('id', 'kind', 'path', 'text', 'array', 'sha256', 'bytes', 'rights', 'origin', 'meta')


def freeze_records(settings, output, *, records, tasks, view=None, out=print):
    """The freeze step: settings as section 6 gives them, from the input product at records, into output.

    tasks is a list of {reference, task, vocabulary, lines (a path or None),
    sha256 (of that file, checked, or None)}, the first being the one whose
    states include a record. Returns the counts.
    """
    seed, shares = settings['seed'], dict(settings['shares'])
    include = set(settings.get('include', DEFAULT_INCLUDE))
    if not tasks:
        raise StepError('freeze needs at least one task.')
    root = os.path.realpath(records)
    counts = dict.fromkeys(('records', 'included', 'stale', 'excluded', 'unannotated', 'invalid', 'stale_other',
                            'missing_files', 'too_long', 'bad_lines', 'copied', 'not_named'), 0)
    by_id = _input_records(root, view, counts)
    counts['records'] = len(by_id)
    rows = []
    for task in tasks:
        found, invalid = _read_task(task)
        rows.append(found)
        counts['invalid'] += invalid
    first, first_name = rows[0], tasks[0]['reference'].split('/', 1)[1]
    if settings.get('records') is not None:
        # Only the records named (a selection on the map, spec-t5.md section 5), before the states decide.
        named = set(settings['records'])
        absent = next((identifier for identifier in settings['records'] if identifier not in by_id), None)
        if absent is not None:
            raise StepError(f'The record {absent!r} named in records is not in the input.')
        counts['not_named'] = sum(1 for identifier in first if identifier not in named)
        first = {identifier: row for identifier, row in first.items() if identifier in named}
        by_id = {identifier: record for identifier, record in by_id.items() if identifier in named}
    progress = Progress('freeze', len(first), out)
    progress(0, {})
    chosen = []
    for done, (identifier, row) in enumerate(sorted(first.items(), key=lambda item: item[0].encode('utf-8')), 1):
        record = by_id.get(identifier)
        if _stale(row, record, root):
            counts['stale'] += 1
        elif row['state'] not in include:
            counts['excluded'] += 1
        else:
            chosen.append(record)
        progress(done, {'included': len(chosen), 'stale': counts['stale'], 'excluded': counts['excluded']})
    counts['unannotated'] = sum(1 for identifier in by_id if identifier not in first)
    chosen.sort(key=lambda record: (order_key(seed, _record_hash(root, record), record['id']), record['id']))
    used_ids, placed = set(), {}
    with open(os.path.join(output, RECORD_LIST), 'x', encoding='utf-8') as listing:
        for split, start, end in _cut(len(chosen), shares):
            for record in chosen[start:end]:
                line = _frozen(record, split, tasks, rows, root, output, placed, used_ids, counts)
                if line is not None:
                    listing.write(line)
                    counts['included'] += 1
    progress(len(first), {'included': counts['included'], 'stale': counts['stale'],
                          'excluded': counts['excluded']}, final=True)
    out(f'{counts["included"]} of {counts["records"]} records frozen by {first_name}: '
        + ', '.join(f'{split} {end - start}' for split, start, end in _cut(len(chosen), shares)) + '.')
    _say(out, counts, (('stale', f'annotations of {first_name} are stale (the record is gone or its content '
                                 'differs) and were left out.'),
                       ('excluded', f'records were left out by their state under {first_name}.'),
                       ('not_named', 'annotated records were left out since records does not name them.'),
                       ('unannotated', f'records have no annotation under {first_name} and were left out.'),
                       ('invalid', 'annotations are not valid for their task and were not read.'),
                       ('stale_other', 'stale annotations of the other tasks were not carried.'),
                       ('missing_files', 'records whose file is missing from the input were left out.'),
                       ('too_long', f'records too long for one line ({LINE_BYTES} bytes) were left out.'),
                       ('bad_lines', f'lines of the input\'s {RECORD_LIST} are not records and were skipped.'),
                       ('copied', 'files were copied, since they could not be linked.')))
    return counts


def _frozen(record, split, tasks, rows, root, output, placed, used_ids, counts):
    """The records.jsonl line of one frozen record, its file linked under files/; None when it is left out."""
    line = {key: record[key] for key in _FROZEN_KEYS if record.get(key) is not None}
    extra = {key: value for key, value in record.items() if key not in _FROZEN_KEYS
             and key not in ('split', 'annotations', 'hash')}
    if extra:
        line['meta'] = {**extra, **(line.get('meta') or {})}
    line['sha256'] = _record_hash(root, record)
    if record.get('path') is not None:
        outer = record['path'].split('!', 1)[0]
        source = _confined(root, outer)
        if source is None:
            counts['missing_files'] += 1
            return None
        target = outer if outer.startswith(f'{FILES}/') else f'{FILES}/{outer}'
        if target not in placed:
            if _place(source, os.path.join(output, *target.split('/'))) == 'copy':
                counts['copied'] += 1
            placed[target] = os.path.getsize(source)
        line['path'] = target + record['path'][len(outer):]
        if '!' not in record['path'] and not isinstance(line.get('bytes'), int):
            line['bytes'] = placed[target]
    identifier = record['id'] if _ID.fullmatch(record['id']) else id_from(record['id'])
    line['id'] = unique(identifier, used_ids, ID_LIMIT)
    line['split'] = split
    carried = {}
    for task, found in zip(tasks, rows):
        row = found.get(record['id'])
        if row is None:
            continue
        if _stale(row, record, root):
            counts['stale_other'] += 1
            continue
        carried[task['reference'].split('/', 1)[1]] = {'state': row['state'], 'value': row['value']}
    line['annotations'] = carried
    ordered = {key: line[key] for key in (*_FROZEN_KEYS, 'split', 'annotations') if key in line}
    text = _line(ordered)
    if len(text.encode('utf-8')) > LINE_BYTES:
        counts['too_long'] += 1
        return None
    return text


# ----------------------------------------------------------------- generate

def prompt_parts(template):
    """[('text', characters) or ('name', placeholder)] of a prompt; ValueError for a stray brace.

    {n} and {text} are the placeholders; {{ and }} are literal braces.
    """
    parts, at = [], 0
    while at < len(template):
        if template.startswith('{{', at):
            parts.append(('text', '{'))
            at += 2
        elif template.startswith('}}', at):
            parts.append(('text', '}'))
            at += 2
        elif template[at] == '{':
            end = template.find('}', at + 1)
            if end < 0 or '{' in template[at + 1:end]:
                raise ValueError('has a { that is not closed; write {{ for a brace')
            parts.append(('name', template[at + 1:end]))
            at = end + 1
        elif template[at] == '}':
            raise ValueError('has a } that is not opened; write }} for a brace')
        else:
            parts.append(('text', template[at]))
            at += 1
    return parts


def fill_prompt(template, values):
    """The prompt with each {name} replaced from values (KeyError naming one it does not hold)."""
    return ''.join(text if part == 'text' else str(values[text]) for part, text in prompt_parts(template))


def _prompt_texts(root, view, counts):
    """[(record id, text)] of the text records of the input product, in its order."""
    by_id = _input_records(root, view, counts)
    found = []
    for identifier, record in by_id.items():
        if record['kind'] != 'text':
            counts['not_text'] += 1
            continue
        if record.get('path') is None:
            found.append((identifier, record['text']))
            continue
        full = _confined(root, record['path']) if '!' not in record['path'] else None
        if full is None or os.path.getsize(full) > LINE_BYTES:
            counts['unread'] += 1
            continue
        with open(full, 'rb') as handle:
            raw = handle.read()
        try:
            found.append((identifier, raw.decode('utf-8')))
        except UnicodeDecodeError:
            counts['unread'] += 1
    return found


def _ask(pumas, endpoint, listing, prepared, prompt, seed, number, token, pauses, out):
    """One item made, asking again (after a pause) what the endpoint refused before the provider took it."""
    never = threading.Event()   # a cancel stops the whole step
    for attempt in range(len(pauses) + 1):
        try:
            return pumas.make_one(endpoint, listing, prepared, prompt, seed, f'tuldok-generate:{token}:{number}:'
                                  f'{attempt + 1}', never)
        except pumas.PumasError as exc:
            if exc.outcome != 'not_admitted' or attempt == len(pauses):
                tries = f' (asked {attempt + 1} times)' if attempt else ''
                raise StepError(f'Item {number} failed{tries}: {exc}') from None
            out(f'Item {number} was not admitted ({exc.provider_code or "refused"}); asking again in '
                f'{pauses[attempt]:g} s.')
            time.sleep(pauses[attempt])


def generate_records(settings, output, *, endpoint, records=None, view=None, report=None, out=print,
                     pauses=RETRY_PAUSES):
    """The generate step (spec-d5.md section 3): settings as the definition gives them, into output.

    endpoint is the machine's Pumas address; records the input product of
    prompts, or None; report a file to write {address, version} to. Nothing
    is asked before what the endpoint serves has been read and every item
    checked against it. Returns the counts.
    """
    from . import pumas   # the step's one way to the endpoint
    make, template, rights = settings['make'], settings['prompt'], settings['rights']
    seed = settings.get('seed')
    counts = dict.fromkeys(('made', 'inputs', 'not_text', 'unread', 'bad_lines', 'retried', 'in_files'), 0)
    if records is not None:
        texts = _prompt_texts(os.path.realpath(records), view, counts)
        counts['inputs'] = len(texts)
        per = settings.get('per', 1)
        items = [(identifier, text) for identifier, text in texts for _ in range(per)]
    else:
        items = [(None, None)] * settings['count']
    if len(items) > GENERATE_LIMIT:
        raise StepError(f'It would make {len(items):,} items; one generate makes at most {GENERATE_LIMIT:,}.')
    try:
        listing = pumas.served(endpoint)
    except pumas.PumasError as exc:
        raise StepError(f'The Pumas endpoint at {endpoint} did not say what it serves: {exc}') from None
    if report is not None:
        with open(report, 'w', encoding='utf-8') as handle:
            json.dump({'address': endpoint, 'version': pumas.version(endpoint)}, handle)
    try:
        prepared = pumas.prepare_make(listing, settings)
        asked = []
        for number, (source, text) in enumerate(items, 1):
            values = {'n': number} if source is None else {'n': number, 'text': text}
            try:
                prompt = fill_prompt(template, values)
            except (KeyError, ValueError) as exc:
                raise StepError(f'The prompt cannot be filled for item {number}: {exc}') from None
            item_seed = seed + number - 1 if seed is not None and prepared['takes_seed'] else None
            pumas.check_item(prepared, prompt, item_seed)
            asked.append((source, prompt, item_seed))
    except pumas.PumasError as exc:
        raise StepError(f'Nothing was asked: {exc}') from None
    entry, row = prepared['entry'], prepared['row']
    sent = {key: value for key, value in (prepared['options'] or {}).items() if key != 'kind'}
    token = uuid.uuid4().hex[:16]
    progress = Progress('generate', len(asked), out)
    progress(0, {})
    out(f'Asking {entry["model"]} ({entry["profile"]}) by {row["capability"]} for {len(asked)} '
        f'{"texts" if make == "text" else "images"}.')
    used_ids = set()
    with open(os.path.join(output, RECORD_LIST), 'x', encoding='utf-8') as listing_file:
        for number, (source, prompt, item_seed) in enumerate(asked, 1):
            made = _ask(pumas, endpoint, listing, prepared, prompt, item_seed, number, token, pauses, out)
            identifier = unique(f'g{number:06d}', used_ids, ID_LIMIT)
            origin = {'generated': {'model': entry['model'], 'profile': entry['profile'],
                                    'capability': row['capability'], 'prompt': prompt,
                                    'seed': made.get('seed', item_seed) if make == 'image' else None,
                                    'options': sent, 'input': source}}
            listing_file.write(_line(_generated_record(output, identifier, make, made, rights, origin, counts)))
            listing_file.flush()
            counts['made'] += 1
            progress(number, {'made': counts['made']})
    progress(len(asked), {'made': counts['made']}, final=True)
    out(f'{counts["made"]} {"texts" if make == "text" else "images"} made by {entry["model"]}.')
    _say(out, counts, (('not_text', 'records of the input are not text and were not used.'),
                       ('unread', f'text records of the input could not be read (missing, over {LINE_BYTES} bytes '
                                  'or not UTF-8) and were not used.'),
                       ('bad_lines', f'lines of the input\'s {RECORD_LIST} are not records and were skipped.'),
                       ('in_files', f'texts too long for one line ({LINE_BYTES} bytes) were written as files.')))
    return counts


def _generated_record(output, identifier, make, made, rights, origin, counts):
    """The records.jsonl line of one made item; an image, or a text too long for a line, is a file under files/."""
    if make == 'text':
        data = made['text'].encode('utf-8', 'surrogatepass')
        record = {'id': identifier, 'kind': 'text', 'text': made['text'], 'sha256': hashlib.sha256(data).hexdigest(),
                  'bytes': len(data), 'rights': rights, 'origin': origin}
        if len(_line(record).encode('utf-8', 'surrogatepass')) <= LINE_BYTES:
            return record
        counts['in_files'] += 1
        address = f'{FILES}/{identifier}.txt'
    else:
        data = made['png']
        address = f'{FILES}/{identifier}.png'
    target = os.path.join(output, *address.split('/'))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, 'xb') as handle:
        handle.write(data)
    return {'id': identifier, 'kind': make, 'path': address, 'sha256': hashlib.sha256(data).hexdigest(),
            'bytes': len(data), 'rights': rights, 'origin': origin}


# ------------------------------------------------------------------- select

def select_records(settings, output, *, records, view=None, out=print):
    """The select step (spec-t5.md section 5): the named records of the input product, in its order, each line as
    the input has it (split and annotations kept), its file linked under files/. Returns the counts."""
    wanted = settings['records']
    root = os.path.realpath(records)
    counts = dict.fromkeys(('records', 'selected', 'missing_files', 'too_long', 'bad_lines', 'copied'), 0)
    by_id = _input_records(root, view, counts)
    counts['records'] = len(by_id)
    absent = next((identifier for identifier in wanted if identifier not in by_id), None)
    if absent is not None:
        raise StepError(f'The record {absent!r} is not in the input, which holds {len(by_id):,} records.')
    named = set(wanted)
    progress = Progress('select', len(named), out)
    progress(0, {})
    used_ids, placed = set(), {}
    with open(os.path.join(output, RECORD_LIST), 'x', encoding='utf-8') as listing:
        for record in by_id.values():
            if record['id'] not in named:
                continue
            line = _selected(record, root, output, placed, used_ids, counts)
            if line is not None:
                listing.write(line)
                counts['selected'] += 1
            progress(counts['selected'], {'selected': counts['selected']})
    progress(counts['selected'], {'selected': counts['selected']}, final=True)
    out(f'{counts["selected"]} of {counts["records"]} records selected.')
    _say(out, counts, (('missing_files', 'records whose file is missing from the input were left out.'),
                       ('too_long', f'records too long for one line ({LINE_BYTES} bytes) were left out.'),
                       ('bad_lines', f'lines of the input\'s {RECORD_LIST} are not records and were skipped.'),
                       ('copied', 'files were copied, since they could not be linked.')))
    return counts


def _selected(record, root, output, placed, used_ids, counts):
    """The records.jsonl line of one selected record, as the input has it, its file linked under files/."""
    keys = (*_FROZEN_KEYS, 'split', 'annotations')
    line = {key: record[key] for key in keys if record.get(key) is not None}
    extra = {key: value for key, value in record.items() if key not in keys and key != 'hash'}
    if extra:
        line['meta'] = {**extra, **(line.get('meta') or {})}
    line['sha256'] = _record_hash(root, record)
    if line['sha256'] is None:
        del line['sha256']
    if record.get('path') is not None:
        outer = record['path'].split('!', 1)[0]
        source = _confined(root, outer)
        if source is None:
            counts['missing_files'] += 1
            return None
        target = outer if outer.startswith(f'{FILES}/') else f'{FILES}/{outer}'
        if target not in placed:
            if _place(source, os.path.join(output, *target.split('/'))) == 'copy':
                counts['copied'] += 1
            placed[target] = os.path.getsize(source)
        line['path'] = target + record['path'][len(outer):]
        if '!' not in record['path'] and not isinstance(line.get('bytes'), int):
            line['bytes'] = placed[target]
    identifier = record['id'] if _ID.fullmatch(record['id']) else id_from(record['id'])
    line['id'] = unique(identifier, used_ids, ID_LIMIT)
    if identifier != record['id']:
        line.setdefault('meta', {})['selected_from'] = record['id']
    ordered = {key: line[key] for key in keys if key in line}
    text = _line(ordered)
    if len(text.encode('utf-8')) > LINE_BYTES:
        counts['too_long'] += 1
        return None
    return text


# -------------------------------------------------------------------- embed

def _embeddable(root, record, counts):
    """(kind, what is sent: a text or image bytes) of one input record, or None (counted) when it is not sent."""
    kind = record['kind']
    if kind == 'text':
        if record.get('path') is None:
            text = record['text']
        else:
            full = _confined(root, record['path']) if '!' not in record['path'] else None
            if full is None or os.path.getsize(full) > EMBED_TEXT_BYTES:
                counts['unread'] += 1
                return None
            with open(full, 'rb') as handle:
                try:
                    text = handle.read().decode('utf-8')
                except UnicodeDecodeError:
                    counts['unread'] += 1
                    return None
        if not text.strip() or len(text.encode('utf-8', 'surrogatepass')) > EMBED_TEXT_BYTES:
            counts['unread'] += 1
            return None
        return 'text', text
    if kind == 'image':
        full = _confined(root, record['path']) if record.get('path') and '!' not in record['path'] else None
        if full is None or os.path.getsize(full) > EMBED_IMAGE_BYTES:
            counts['unread'] += 1
            return None
        with open(full, 'rb') as handle:
            data = handle.read()
        if not (data.startswith(b'\x89PNG\r\n\x1a\n') or data.startswith(b'\xff\xd8')):
            counts['unread'] += 1
            return None
        return 'image', data
    counts['other_kinds'] += 1
    counts.setdefault('kinds', {})
    counts['kinds'][kind] = counts['kinds'].get(kind, 0) + 1
    return None


class _Partial:
    """The rows answered so far, appended as they come: embeddings/.<name>.partial (32-bit floats, little-endian),
    .<name>.partial.ids (one id a line) and .<name>.partial.json (what they were asked with)."""

    def __init__(self, directory, name):
        self.rows = os.path.join(directory, f'.{name}.partial')
        self.ids = os.path.join(directory, f'.{name}.partial.ids')
        self.meta = os.path.join(directory, f'.{name}.partial.json')

    def read(self, expected):
        """{id: row bytes} of a partial whose meta equals expected; {} when there is none or it differs."""
        try:
            with open(self.meta, encoding='utf-8') as handle:
                meta = json.load(handle)
            if meta != expected:
                return {}
            with open(self.ids, encoding='utf-8') as handle:
                ids = [line.rstrip('\n') for line in handle if line.endswith('\n')]
            width = meta['width'] * 4 if meta.get('width') else None
            with open(self.rows, 'rb') as handle:
                data = handle.read()
        except (OSError, ValueError, KeyError, TypeError):
            return {}
        if not width:
            return {}
        count = min(len(ids), len(data) // width)
        return {ids[i]: data[i * width:(i + 1) * width] for i in range(count)}


def _float_bytes(vector):
    import array as array_module
    packed = array_module.array('f', vector)
    if sys.byteorder != 'little':
        packed.byteswap()
    return packed.tobytes()


def embed_records(settings, output, *, endpoint, records, facts, report=None, out=print, pauses=RETRY_PAUSES):
    """The embed step (spec-t5.md section 5): one vector per text and image record of the input product, asked of
    the embedder the endpoint serves, written as embeddings/<name>.npy and .json.

    facts: {source: {dataset, run}, name (the default set name), model,
    profile, prefix (the machine's), resume (a failed run's output, or
    None)}. Nothing is asked before what the endpoint serves has been read and
    every kind of record checked against it. Returns the counts.
    """
    from . import embeddings, pumas   # the step's one way to the endpoint, and the contract's writer
    root = os.path.realpath(records)
    counts = dict.fromkeys(('embedded', 'resumed', 'records', 'unread', 'other_kinds', 'bad_lines', 'no_route'), 0)
    by_id = _input_records(root, None, counts)
    counts['records'] = len(by_id)
    items = []
    for identifier, record in by_id.items():
        found = _embeddable(root, record, counts)
        if found is not None:
            items.append((identifier, *found))
    if not items:
        raise StepError('Nothing in the input can be embedded: Pumas 0.8.0 embeds texts and PNG or JPEG images, '
                        f'and its {len(by_id):,} records hold none that can be sent.')
    try:
        listing = pumas.served(endpoint)
    except pumas.PumasError as exc:
        raise StepError(f'The Pumas endpoint at {endpoint} did not say what it serves: {exc}') from None
    if report is not None:
        with open(report, 'w', encoding='utf-8') as handle:
            json.dump({'address': endpoint, 'version': pumas.version(endpoint)}, handle)
    named = settings.get('model')
    model = named if named is not None else facts.get('model')
    profile = settings.get('profile') if named is not None else facts.get('profile')
    dimensions = settings.get('dimensions')
    try:
        entry, named_by = pumas.choose_embedder(listing, model, profile)
        routes = pumas.embedding_routes(entry)
        pumas.check_dimensions(routes, dimensions)
    except pumas.PumasError as exc:
        raise StepError(f'Nothing was asked: {exc}') from None
    if named_by == 'named':
        named_by = 'definition' if named is not None else 'setting'
    kinds = {kind for _, kind, _ in items}
    if not kinds & set(routes):
        raise StepError(f'Nothing was asked: {entry["model"]} ({entry["profile"]}) cannot embed '
                        + ' or '.join(sorted(kinds)) + ' now; it embeds ' + (' and '.join(sorted(routes)) or 'nothing')
                        + '.')
    for kind in sorted(kinds - set(routes)):
        counts['no_route'] += sum(1 for item in items if item[1] == kind)
        counts.setdefault('unrouted', []).append(kind)
    items = [item for item in items if item[1] in routes]
    prefix = settings['prefix'] if 'prefix' in settings else facts.get('prefix')
    if prefix is None:
        prefix = pumas.DEFAULT_PREFIX
    name = settings.get('name') or facts['name']
    directory = os.path.join(output, embeddings.DIRECTORY)
    os.makedirs(directory, exist_ok=True)
    partial = _Partial(directory, name)
    asked = {'source_run': facts['source'].get('run'), 'model': entry['model'], 'profile': entry['profile'],
             'model_id': entry['model_id'], 'prefix': prefix, 'dimensions': dimensions}
    taken = {}
    if facts.get('resume'):
        earlier = _Partial(os.path.join(facts['resume'], embeddings.DIRECTORY), name)
        try:
            with open(earlier.meta, encoding='utf-8') as handle:
                width = json.load(handle).get('width')
        except (OSError, ValueError, AttributeError):
            width = None
        if width:
            taken = earlier.read({**asked, 'width': width})
            asked['width'] = width
    wanted = {identifier for identifier, _, _ in items}
    taken = {identifier: row for identifier, row in taken.items() if identifier in wanted}
    width = asked.get('width') if taken else None
    rows_file = open(partial.rows, 'xb')
    ids_file = open(partial.ids, 'x', encoding='utf-8')
    written = 0

    def keep(identifiers, rows):
        nonlocal written
        rows_file.write(b''.join(rows))
        rows_file.flush()
        ids_file.write(''.join(identifier + '\n' for identifier in identifiers))
        ids_file.flush()
        written += len(identifiers)

    def meta(found_width):
        with open(partial.meta, 'w', encoding='utf-8') as handle:
            json.dump({**asked, 'width': found_width}, handle)

    try:
        if taken:
            meta(width)
            order = [identifier for identifier, _, _ in items if identifier in taken]
            keep(order, [taken[identifier] for identifier in order])
            counts['resumed'] = len(order)
            out(f'{len(order)} rows were taken from the failed run before, asked with the same model, prefix and '
                'dimensions; the rest are asked for.')
        remaining = [item for item in items if item[0] not in taken]
        progress = Progress('embed', len(items), out)
        progress(counts['resumed'], {'embedded': counts['resumed'], 'resumed': counts['resumed']})
        out(f'Asking {entry["model"]} ({entry["profile"]}) for {len(remaining)} vectors'
            + (f' of {dimensions} dimensions' if dimensions else '') + '.')
        token = uuid.uuid4().hex[:16]
        size = settings.get('batch', EMBED_BATCH)
        number = 0
        for kind in ('text', 'image'):
            route = routes.get(kind)
            mine = [item for item in remaining if item[1] == kind]
            if route is None or not mine:
                continue
            most = pumas.batch_size(kind, route[2], size)
            at = 0
            while at < len(mine):
                chunk = mine[at:at + most]
                if kind == 'image':   # at most the release's bytes in one request
                    while len(chunk) > 1 and sum(len(data) for _, _, data in chunk) * 4 // 3 > pumas.IMAGE_REQUEST_BYTES:
                        chunk = chunk[:-1]
                at += len(chunk)
                number += 1
                try:
                    sent = ([prefix + text for _, _, text in chunk] if kind == 'text'
                            else [pumas.image_part(data) for _, _, data in chunk])
                except pumas.PumasError as exc:
                    raise StepError(f'The record {chunk[0][0]} cannot be sent: {exc}') from None
                vectors = _ask_vectors(pumas, endpoint, listing, entry, route, sent, dimensions, number, token,
                                       pauses, out, chunk[0][0])
                if width is None:
                    width = len(vectors[0])
                    meta(width)
                elif len(vectors[0]) != width:
                    raise StepError(f'The endpoint answered vectors of {len(vectors[0])} dimensions for the record '
                                    f'{chunk[0][0]}; earlier ones had {width}.')
                keep([identifier for identifier, _, _ in chunk], [_float_bytes(vector) for vector in vectors])
                counts['embedded'] += len(chunk)
                progress(counts['embedded'] + counts['resumed'],
                         {'embedded': counts['embedded'] + counts['resumed'], 'resumed': counts['resumed']})
    finally:
        rows_file.close()
        ids_file.close()
    total = counts['embedded'] + counts['resumed']
    progress(total, {'embedded': total, 'resumed': counts['resumed']}, final=True)
    with open(partial.ids, encoding='utf-8') as handle:
        ids = [line.rstrip('\n') for line in handle]
    notes = []
    if counts['other_kinds']:
        notes.append(', '.join(f'{count} {kind}' for kind, count in sorted(counts['kinds'].items()))
                     + ' records were not embedded: Pumas 0.8.0 embeds texts and images.')
    if counts['no_route']:
        notes.append(f'{counts["no_route"]} records were not embedded: {entry["model"]} does not embed '
                     + ' or '.join(counts['unrouted']) + '.')
    if counts['unread']:
        notes.append(f'{counts["unread"]} records could not be sent (a text over {EMBED_TEXT_BYTES} bytes, not '
                     f'UTF-8 or empty; an image over {EMBED_IMAGE_BYTES} bytes, not PNG or JPEG, or missing).')
    header = "{'descr': '<f4', 'fortran_order': False, 'shape': (%d, %d), }" % (len(ids), width)
    padding = 64 - (10 + len(header) + 1) % 64
    text = (header + ' ' * padding + '\n').encode('latin-1')
    with open(os.path.join(directory, f'{name}.npy'), 'xb') as target, open(partial.rows, 'rb') as source:
        target.write(b'\x93NUMPY\x01\x00' + len(text).to_bytes(2, 'little') + text)
        shutil.copyfileobj(source, target)
    used = sorted({routes[kind][0] for _, kind, _ in items})
    index = {'format': embeddings.FORMAT, 'records': ids, 'dimensions': width, 'metric': 'cosine',
             'model': {'name': entry['model'], 'model_id': entry['model_id'], 'profile': entry['profile'],
                       'capability': ', '.join(used), 'dimensions_asked': dimensions, 'named_by': named_by,
                       'via': 'pumas'},
             'prefix': prefix if prefix and any(kind == 'text' for _, kind, _ in items) else None,
             'source': {'dataset': facts['source'].get('dataset'), 'run': facts['source'].get('run')},
             'notes': notes}
    with open(os.path.join(directory, f'{name}.json'), 'x', encoding='utf-8') as handle:
        json.dump(index, handle, ensure_ascii=False, separators=(',', ':'))
    for path in (partial.rows, partial.ids, partial.meta):
        os.unlink(path)
    out(f'{total} records embedded by {entry["model"]} ({width} dimensions)'
        + (f', {counts["resumed"]} of them taken from the failed run before' if counts['resumed'] else '') + '.')
    for note in notes:
        out(note)
    return counts


def _ask_vectors(pumas, endpoint, listing, entry, route, sent, dimensions, number, token, pauses, out, first):
    """One batch's vectors, asking again (after a pause) what the endpoint refused before the provider took it."""
    for attempt in range(len(pauses) + 1):
        try:
            return pumas.embed_batch(endpoint, listing, entry, route, sent, dimensions,
                                     f'tuldok-embed:{token}:{number}:{attempt + 1}')
        except pumas.PumasError as exc:
            if exc.outcome != 'not_admitted' or attempt == len(pauses):
                tries = f' (asked {attempt + 1} times)' if attempt else ''
                raise StepError(f'Batch {number}, from the record {first}, failed{tries}: {exc}') from None
            out(f'Batch {number} was not admitted ({exc.provider_code or "refused"}); asking again in '
                f'{pauses[attempt]:g} s.')
            time.sleep(pauses[attempt])


# --------------------------------------------------------------- command line

def _arguments(argv):
    parser = argparse.ArgumentParser(prog='python -m tuldok_project.steps',
                                     description='Run a step Tuldok provides (spec-d4.md section 6).')
    parser.add_argument('step', choices=STEPS)
    parser.add_argument('settings', help='the run\'s settings file')
    parser.add_argument('output', help='the run\'s output directory, which exists')
    parser.add_argument('--code', help='the code root the run sees (for a relative source)')
    parser.add_argument('--records', help='freeze: the input product\'s directory')
    parser.add_argument('--tasks', help='freeze: a JSON file of the tasks and their line files')
    parser.add_argument('--endpoint', help='generate: the Pumas endpoint this machine uses')
    parser.add_argument('--report', help='generate: a file to write the endpoint\'s address and version to')
    parser.add_argument('--facts', help='embed: a JSON file of the source, the machine\'s embedder and what to resume')
    return parser.parse_args(argv)


def main(argv=None):
    arguments = _arguments(argv)
    out = lambda text: print(text, flush=True)  # noqa: E731
    try:
        with open(arguments.settings, encoding='utf-8') as handle:
            settings = json.load(handle)
        if not os.path.isdir(arguments.output):
            raise StepError(f'The output directory {arguments.output} does not exist.')
        if arguments.step == 'import':
            import_files(settings, arguments.output, code_root=arguments.code, out=out)
        elif arguments.step == 'embed':
            if arguments.endpoint is None or arguments.records is None or arguments.facts is None:
                raise StepError('embed needs --endpoint, --records and --facts.')
            with open(arguments.facts, encoding='utf-8') as handle:
                facts = json.load(handle)
            embed_records(settings, arguments.output, endpoint=arguments.endpoint, records=arguments.records,
                          facts=facts, report=arguments.report, out=out)
        elif arguments.step == 'select':
            if arguments.records is None:
                raise StepError('select needs --records.')
            select_records(settings, arguments.output, records=arguments.records, out=out)
        elif arguments.step == 'generate':
            if arguments.endpoint is None:
                raise StepError('generate needs --endpoint, the Pumas endpoint this machine uses.')
            generate_records(settings, arguments.output, endpoint=arguments.endpoint, records=arguments.records,
                             report=arguments.report, out=out)
        else:
            if arguments.records is None or arguments.tasks is None:
                raise StepError('freeze needs --records and --tasks.')
            with open(arguments.tasks, encoding='utf-8') as handle:
                described = json.load(handle)
            freeze_records(settings, arguments.output, records=arguments.records, tasks=described['tasks'],
                           view=described.get('view'), out=out)
    except (StepError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f'{arguments.step}: {exc}', file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
