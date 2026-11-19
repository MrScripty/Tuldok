"""The steps Tuldok provides: import files into a dataset, freeze a dataset with splits from its annotations,
and generate a dataset by asking a model a Pumas endpoint serves.

Owns section 6 of docs/plans/definition-first-projects/spec-d4.md and section
3 of spec-d5.md. A dataset whose run names a step (run.step) is built by
Tuldok's own interpreter running

    python -m tuldok_project.steps import <settings file> <output directory> --code <code root>
    python -m tuldok_project.steps freeze <settings file> <output directory> --records <input product> --tasks <file>
    python -m tuldok_project.steps generate <settings file> <output directory> --endpoint <address>
        --report <file> [--records <input product>]

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

import_files, freeze_records and generate_records are the steps as functions
on directories; main() is the command line.
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
STEPS = ('import', 'freeze', 'generate', 'annotate')
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
ANNOTATED = 'annotations.jsonl'     # an annotation set's lines (spec-t4.md section 3)
ANNOTATOR = 'annotator.json'        # what made the set
ANNOTATOR_FORMAT = 'tuldok_annotator_v1'
TODO = 'todo.jsonl'                 # the records an annotator command is to annotate, in the run's directory
ANNOTATE_LIMIT = 1_000_000          # records one annotate annotates
ANNOTATE_LINE_BYTES = 64 * 1024 * 1024   # one line a command writes (a large polygon list)
GIVE_UP_AFTER = 10                  # Pumas: every one of the first this many records refused fails the step


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
                            'missing_files', 'too_long', 'bad_lines', 'copied'), 0)
    by_id = _input_records(root, view, counts)
    counts['records'] = len(by_id)
    rows = []
    for task in tasks:
        found, invalid = _read_task(task)
        rows.append(found)
        counts['invalid'] += invalid
    first, first_name = rows[0], tasks[0]['reference'].split('/', 1)[1]
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


# ---------------------------------------------------------------- annotate

def _record_facts(root, record, task):
    """What the value of task on record is checked against, as far as the step can tell from the file's head."""
    from . import annotation_payloads as payloads
    facts = {'kind': record['kind'], 'size': None, 'points': None, 'shape': None}
    path = record.get('path')
    full = _confined(root, path) if isinstance(path, str) and '!' not in path else None
    if full is None:
        return facts
    try:
        with open(full, 'rb') as handle:
            head = handle.read(64 * 1024)
        if record['kind'] == 'image' and head.startswith(b'\x89PNG'):
            facts['size'] = payloads.png_size(head)[:2]
        elif record['kind'] == 'array' and head.startswith(b'\x93NUMPY'):
            facts['shape'] = payloads.npy_header(head)[0]
        elif record['kind'] == 'pointcloud' and task in ('points', 'box3d'):
            facts['points'] = _cloud_count(full, head)
    except (OSError, payloads.PayloadError):
        pass
    return facts


def _cloud_count(full, head):
    """The points of a .ply (its vertex element), an .npy (its first axis) or an .xyz (its rows of numbers)."""
    from . import annotation_payloads as payloads
    if head.startswith(b'ply'):
        for line in head.split(b'end_header', 1)[0].decode('ascii', 'replace').splitlines():
            words = line.split()
            if len(words) == 3 and words[:2] == ['element', 'vertex'] and words[2].isdigit():
                return int(words[2])
        return None
    if head.startswith(b'\x93NUMPY'):
        return payloads.npy_header(head)[0][0]
    count = 0
    with open(full, 'rb') as handle:
        for line in handle:
            words = line.decode('utf-8', 'replace').replace(',', ' ').split()
            if len(words) >= 3 and not words[0].startswith('#'):
                try:
                    [float(word) for word in words[:3]]
                except ValueError:
                    continue
                count += 1
    return count


def _set_line(raw, task, by_id, root, output, facts_of, counts):
    """(record, line to keep) from one line an annotator wrote, or None with the reason counted."""
    from . import annotation_payloads as payloads
    try:
        value = json.loads(raw)
    except (ValueError, RecursionError):
        counts['not_json'] += 1
        return None
    if not isinstance(value, dict) or not isinstance(value.get('record'), str) or 'value' not in value \
            or set(value) - {'record', 'sha256', 'value', 'confidence', 'note'}:
        counts['not_lines'] += 1
        return None
    record = by_id.get(value['record'])
    if record is None:
        counts['unknown_records'] += 1
        return None
    confidence, note = value.get('confidence'), value.get('note')
    if (confidence is not None and not (isinstance(confidence, (int, float)) and not isinstance(confidence, bool)
                                        and 0 <= confidence <= 1)) \
            or (note is not None and not (isinstance(note, str) and len(note) <= annotations.NOTE_LIMIT)):
        counts['invalid'] += 1
        return None
    facts = facts_of(record)
    document = task['document']
    errors, unknown = annotations.value_problems(
        document['task'], document.get('vocabulary') or [], 'accepted', value['value'], kind=record['kind'],
        size=facts['size'], fields=annotations.task_fields(document), points=facts['points'], shape=facts['shape'])
    if errors or unknown or value['value'] is None:
        counts['invalid'] += 1
        return None
    for name in annotations.sidecars(document['task'], value['value']):
        full = os.path.realpath(os.path.join(output, FILES, *name.split('/')))
        if not _inside(full, os.path.join(os.path.realpath(output), FILES)) or not os.path.isfile(full):
            counts['missing_sidecars'] += 1
            return None
        with open(full, 'rb') as handle:
            data = handle.read(payloads.SIDECAR_LIMIT + 1)
        if payloads.sidecar_problem(document['task'], data, size=facts['size'], points=facts['points']):
            counts['invalid'] += 1
            return None
    line = {'record': value['record'], 'sha256': _record_hash(root, record), 'value': value['value']}
    if confidence is not None:
        line['confidence'] = confidence
    if note is not None:
        line['note'] = note
    return value['record'], line


def _set_text(line):
    """One line of an annotation set: record, sha256, value (its keys as a line file orders them), confidence, note."""
    ordered = {'record': line['record'], 'sha256': line['sha256'], 'value': annotations.ordered_value(line['value'])}
    for key in ('confidence', 'note'):
        if key in line:
            ordered[key] = line[key]
    return json.dumps(ordered, ensure_ascii=False, separators=(',', ':')) + '\n'


def _read_written(path, task, by_id, root, output, facts_of, counts):
    """The lines an annotator appended to path, the last valid one of each record kept."""
    kept = {}
    if not os.path.isfile(path):
        return kept
    with open(path, 'rb') as handle:
        for raw in handle:
            if len(raw) > ANNOTATE_LINE_BYTES:
                counts['not_lines'] += 1
                continue
            if not raw.strip():
                continue
            found = _set_line(raw, task, by_id, root, output, facts_of, counts)
            if found is not None:
                if found[0] in kept:
                    counts['repeated'] += 1
                kept[found[0]] = found[1]
    return kept


def _resumed(resume, task, by_id, root, output, facts_of, counts):
    """The valid lines (and their sidecars) of an earlier run of this definition whose records' hashes still hold."""
    kept = {}
    path = os.path.join(resume, ANNOTATED)
    if not os.path.isfile(path):
        return kept
    with open(path, 'rb') as handle:
        for raw in handle:
            try:
                value = json.loads(raw)
            except (ValueError, RecursionError):
                continue
            if not isinstance(value, dict) or value.get('record') not in by_id:
                continue
            record = by_id[value['record']]
            if value.get('sha256') is not None and value.get('sha256') != _record_hash(root, record):
                continue
            for name in annotations.sidecars(task['document']['task'], value.get('value')):
                parts = str(name).split('/')
                if str(name).startswith('/') or '..' in parts or '' in parts:
                    continue
                source = os.path.realpath(os.path.join(resume, FILES, *parts))
                if _inside(source, os.path.join(os.path.realpath(resume), FILES)) and os.path.isfile(source):
                    target = os.path.join(output, FILES, *parts)
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    shutil.copyfile(source, target)
            found = _set_line(raw, task, by_id, root, output, facts_of, counts)
            if found is not None:
                kept[found[0]] = found[1]
    counts['resumed'] = len(kept)
    return kept


def _child_env(variables):
    """The environment of an annotator command: the run's, without what makes Tuldok's own code importable."""
    env = {key: value for key, value in os.environ.items() if key not in ('PYTHONSAFEPATH', 'PYTHONPATH')}
    if os.environ.get('TULDOK_ANNOTATE_PYTHONPATH'):
        env['PYTHONPATH'] = env.pop('TULDOK_ANNOTATE_PYTHONPATH')
    env.update(variables)
    return env


def _ask_pumas(settings, task, todo, by_id, root, output, endpoint, lines, facts_of, counts, out, progress):
    """Annotate the records of todo by asking a served model, appending a line for each answer that fits."""
    from . import pumas
    document = task['document']
    asked = settings['pumas']
    try:
        listing = pumas.served(endpoint)
        entry = pumas.choose(listing, asked['model'], asked.get('profile'))
    except pumas.PumasError as exc:
        raise StepError(f'The Pumas endpoint at {endpoint} cannot be asked: {exc}') from None
    capability = None
    token = uuid.uuid4().hex[:16]
    for number, record_id in enumerate(todo, 1):
        record = by_id[record_id]
        found = pumas.routes(entry, document['task'], record['kind'])
        if not found:
            counts['refused'] += 1
        else:
            capability = found[0]['capability']
            facts = facts_of(record)
            try:
                content = _record_content(root, record)
                value = pumas.suggest(
                    endpoint, listing, entry, found[0], document['task'], document.get('vocabulary') or [],
                    content, asked.get('instruction'), request_id=f'tuldok-annotate:{token}:{number}',
                    size=facts['size'],
                    check=lambda v: _fits(document, record, facts, v))
            except pumas.PumasError as exc:
                if exc.code not in ('unsuitable', 'invalid'):
                    raise StepError(f'Record {record_id!r}: {exc}') from None
                counts['refused'] += 1
                out(f'Record {record_id}: {exc}')
            else:
                line = {'record': record_id, 'sha256': _record_hash(root, record), 'value': value}
                lines.write(_set_text(line))
                lines.flush()
                counts['made'] += 1
        if number == min(GIVE_UP_AFTER, len(todo)) and not counts['made'] and counts['refused'] == number:
            raise StepError(f'The model refused or could not answer every one of the first {number} records.')
        progress(number, {'made': counts['made'], 'refused': counts['refused']})
    return {'kind': 'model', 'name': entry['model'], 'version': entry['profile'],
            'capability': capability}


def _fits(document, record, facts, value):
    """The problems of a model's answer as a value of the task, terms outside the vocabulary included."""
    errors, unknown = annotations.value_problems(document['task'], document.get('vocabulary') or [], 'accepted', value,
                                                 kind=record['kind'], size=facts['size'],
                                                 fields=annotations.task_fields(document))
    return errors + [f'The term {term!r} is not in the vocabulary of the task.' for term in unknown]


def _record_content(root, record):
    """{kind, text} or {kind, data} of a record, read whole up to the bound a suggestion sends."""
    if record.get('path') is None:
        return {'kind': record['kind'], 'text': record.get('text') or ''}
    full = _confined(root, record['path']) if '!' not in record['path'] else None
    if full is None:
        from . import pumas
        raise pumas.PumasError(f'The record {record["id"]!r} cannot be read here.', 'invalid')
    with open(full, 'rb') as handle:
        data = handle.read(16 * 1024 * 1024 + 1)
    if record['kind'] == 'text':
        return {'kind': 'text', 'text': data.decode('utf-8', 'replace')}
    return {'kind': record['kind'], 'data': data}


def annotate_records(settings, output, *, records, task, run_directory, command=None, code=None, endpoint=None,
                     resume=None, out=print):
    """The annotate step (spec-t4.md section 4): an annotation set of task for the records of the input product.

    task is {'reference', 'document'}; command the annotator's argv (run from
    code), or None to ask the model settings.pumas names at endpoint; resume
    the output directory of an earlier run of the same definition. Returns
    the counts.
    """
    root = os.path.realpath(records)
    counts = dict.fromkeys(('bad_lines', 'resumed', 'made', 'refused', 'not_json', 'not_lines', 'unknown_records',
                            'invalid', 'missing_sidecars', 'repeated'), 0)
    by_id = _input_records(root, None, counts)
    facts_cache = {}

    def facts_of(record):
        if record['id'] not in facts_cache:
            facts_cache[record['id']] = _record_facts(root, record, task['document']['task'])
        return facts_cache[record['id']]
    os.makedirs(os.path.join(output, FILES), exist_ok=True)
    kept = _resumed(resume, task, by_id, root, output, facts_of, counts) if resume else {}
    limit = settings.get('limit', ANNOTATE_LIMIT)
    todo = [record_id for record_id in by_id if record_id not in kept and annotations.allows_kind(
        task['document']['task'], by_id[record_id]['kind'])][:max(0, limit - len(kept))]
    out(f'{len(todo)} records to annotate for {task["reference"]}' + (f'; {len(kept)} kept from the run before'
                                                                     if kept else '') + '.')
    progress = Progress('annotate', len(todo), out)
    progress(0, {})
    path = os.path.join(output, ANNOTATED)
    with open(path, 'w', encoding='utf-8') as lines:
        for record_id in sorted(kept, key=annotations.sort_key):
            lines.write(_set_text(kept[record_id]))
    by = dict(settings['by'])
    if command is not None:
        todo_path = os.path.join(run_directory, TODO)
        with open(todo_path, 'w', encoding='utf-8') as handle:
            for record_id in todo:
                record = dict(by_id[record_id])
                record.pop('hash', None)
                if record.get('path') is not None and '!' not in record['path']:
                    record['path'] = os.path.join(root, *record['path'].split('/'))
                handle.write(_line(record))
        task_path = os.path.join(run_directory, 'task.json')
        with open(task_path, 'w', encoding='utf-8') as handle:
            json.dump(dict(task['document'], reference=task['reference']), handle, ensure_ascii=False, indent=2)
        import subprocess
        env = _child_env({'TULDOK_RECORDS': root, 'TULDOK_TODO': todo_path, 'TULDOK_TASK': task_path,
                          'TULDOK_ANNOTATIONS': os.path.abspath(path),
                          'TULDOK_FILES': os.path.abspath(os.path.join(output, FILES)),
                          'TULDOK_ANNOTATE_OPTIONS': json.dumps(settings.get('options') or {})})
        status = subprocess.call(command, cwd=code or run_directory, env=env, stdin=subprocess.DEVNULL)
        if status != 0:
            raise StepError(f'The annotator command ended with status {status}; what it wrote is kept for the next '
                            'build to resume from.')
    else:
        if endpoint is None:
            raise StepError('An annotate asking a model needs --endpoint, the Pumas endpoint this machine uses.')
        with open(path, 'a', encoding='utf-8') as lines:
            made = _ask_pumas(settings, task, todo, by_id, root, output, endpoint, lines, facts_of, counts, out,
                              progress)
        by.setdefault('kind', 'model')
        by.setdefault('name', made['name'])
        by['model'] = {'model': made['name'], 'profile': made['version'], 'capability': made['capability']}
    final = _read_written(path, task, by_id, root, output, facts_of, counts)
    with open(path, 'w', encoding='utf-8') as lines:
        for record_id in sorted(final, key=annotations.sort_key):
            lines.write(_set_text(final[record_id]))
    by['settings'] = {key: value for key, value in settings.items() if key != 'by'}
    annotator = {'format': ANNOTATOR_FORMAT, 'task': task['reference'], 'by': by, 'records': len(by_id),
                 'made': len(final), 'at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    with open(os.path.join(output, ANNOTATOR), 'w', encoding='utf-8') as handle:
        json.dump(annotator, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    counts['kept'] = len(final)
    progress(len(todo), {'kept': len(final)}, final=True)
    out(f'{len(final)} records annotated for {task["reference"]}.')
    _say(out, counts, (('refused', 'records the model could not annotate were skipped.'),
                       ('not_json', 'lines the annotator wrote are not JSON and were dropped.'),
                       ('not_lines', 'lines the annotator wrote are not annotation lines and were dropped.'),
                       ('unknown_records', 'lines name a record the input does not have and were dropped.'),
                       ('invalid', 'lines hold a value the task does not allow and were dropped.'),
                       ('missing_sidecars', 'lines name a sidecar that is not under files/ and were dropped.'),
                       ('repeated', 'records were annotated more than once; the last line of each is kept.'),
                       ('bad_lines', f'lines of the input\'s {RECORD_LIST} are not records and were skipped.')))
    return counts


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
    parser.add_argument('--task', help='annotate: a JSON file {reference, document} of the task')
    parser.add_argument('--command-json', help='annotate: the annotator command\'s argv as JSON')
    parser.add_argument('--resume', help='annotate: the output of an earlier run of the same definition')
    parser.add_argument('--run-directory', help='annotate: the run\'s directory')
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
        elif arguments.step == 'annotate':
            if arguments.records is None or arguments.task is None or arguments.run_directory is None:
                raise StepError('annotate needs --records, --task and --run-directory.')
            with open(arguments.task, encoding='utf-8') as handle:
                task = json.load(handle)
            annotate_records(settings, arguments.output, records=arguments.records, task=task,
                             run_directory=arguments.run_directory,
                             command=json.loads(arguments.command_json) if arguments.command_json else None,
                             code=arguments.code, endpoint=arguments.endpoint, resume=arguments.resume, out=out)
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
