"""Annotation sets: what an annotator wrote into its run's product, read back for review and agreement.

Owns the reading side of section 3 of
docs/plans/training-and-curation/spec-t4.md. A set is the product of a
dataset whose run is the step annotate (annotator.json, annotations.jsonl and
files/); the kept set is the working copy's annotations of the task, given
by the caller. Reading is bounded (the lines file at most 64 MiB, at most
RECORDS_LIMIT records) and every line is checked again against the task as
it now stands, so a set made for an earlier vocabulary shows what still
fits and counts the rest. Nothing of the product is written, nothing is
unpickled, and a sidecar is read only from under the product's files/.
Standard library and Tuldok's pure modules only; no database.
"""
import json
import os

from . import annotation_payloads as payloads, annotations

KEPT = 'kept'                       # the name of the kept set: annotations/<task>.jsonl and its working copy
ANNOTATOR = 'annotator.json'
ANNOTATED = 'annotations.jsonl'
FILES = 'files'
LINES_LIMIT = 64 * 1024 * 1024      # bytes of a set's lines file
RECORDS_LIMIT = 20_000              # records of one set read for agreement (spec-t4.md section 5)
ANNOTATOR_LIMIT = 64 * 1024         # bytes of annotator.json
SETS_LIMIT = 8


class SetProblem(Exception):
    """A set that cannot be read; the message is a sentence."""


def is_annotator(document, task_reference):
    """True when document is a dataset whose run is an annotate for task_reference."""
    run = document.get('run') if isinstance(document, dict) else None
    return (isinstance(run, dict) and run.get('step') == 'annotate'
            and isinstance(run.get('annotations'), list) and run['annotations'][:1] == [task_reference])


def _confined(root, relative):
    """The real path of a regular file at relative under root, or None."""
    if not isinstance(relative, str) or relative.startswith('/') or '\x00' in relative:
        return None
    parts = relative.split('/')
    if '..' in parts or '' in parts:
        return None
    full = os.path.realpath(os.path.join(root, *parts))
    base = os.path.realpath(root)
    return full if full.startswith(base + os.sep) and os.path.isfile(full) else None


def read_annotator(directory):
    """The annotator.json of a set's product directory, or SetProblem."""
    path = os.path.join(directory, ANNOTATOR)
    try:
        with open(path, 'rb') as handle:
            raw = handle.read(ANNOTATOR_LIMIT + 1)
    except OSError:
        raise SetProblem(f'The product has no {ANNOTATOR}.') from None
    try:
        value = json.loads(raw)
    except (ValueError, RecursionError):
        raise SetProblem(f'Its {ANNOTATOR} is not JSON.') from None
    if len(raw) > ANNOTATOR_LIMIT or not isinstance(value, dict) or not isinstance(value.get('by'), dict):
        raise SetProblem(f'Its {ANNOTATOR} is not an annotator file with by.')
    return value


def read_set(directory, document, *, limit=RECORDS_LIMIT):
    """{by, at, records: {record: line}, skipped, truncated} of the set in a product directory.

    A line is {sha256, value, confidence?, note?}; a line whose value the task
    (document) no longer allows is skipped and counted.
    """
    annotator = read_annotator(directory)
    path = os.path.join(directory, ANNOTATED)
    try:
        size = os.path.getsize(path)
    except OSError:
        raise SetProblem(f'The product has no {ANNOTATED}.') from None
    if size > LINES_LIMIT:
        raise SetProblem(f'Its {ANNOTATED} is over {LINES_LIMIT:,} bytes.')
    task, vocabulary = document.get('task'), document.get('vocabulary') or []
    fields = annotations.task_fields(document)
    records, skipped, truncated = {}, 0, False
    with open(path, 'rb') as handle:
        for raw in handle:
            if not raw.strip():
                continue
            if len(records) >= limit:
                truncated = True
                break
            try:
                line = json.loads(raw)
            except (ValueError, RecursionError):
                skipped += 1
                continue
            if not isinstance(line, dict) or not isinstance(line.get('record'), str) or 'value' not in line:
                skipped += 1
                continue
            errors, unknown = annotations.value_problems(task, vocabulary, 'accepted', line['value'], fields=fields)
            confidence = line.get('confidence')
            if errors or unknown or (confidence is not None and not annotations._confidence(confidence)):
                skipped += 1
                continue
            kept = {'sha256': line.get('sha256'), 'value': line['value']}
            if confidence is not None:
                kept['confidence'] = confidence
            if isinstance(line.get('note'), str):
                kept['note'] = line['note']
            records[line['record']] = kept
    return {'by': annotator['by'], 'at': annotator.get('at'), 'records': records, 'skipped': skipped,
            'truncated': truncated}


def sidecar(directory, name):
    """The bytes of a set's sidecar files/<name>, or SetProblem."""
    full = _confined(os.path.join(directory, FILES), name)
    if full is None:
        raise SetProblem(f'The sidecar {name!r} is not under the product\'s {FILES}/.')
    with open(full, 'rb') as handle:
        data = handle.read(payloads.SIDECAR_LIMIT + 1)
    if len(data) > payloads.SIDECAR_LIMIT:
        raise SetProblem(f'The sidecar {name!r} is over {payloads.SIDECAR_LIMIT:,} bytes.')
    return data
