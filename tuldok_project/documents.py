"""Single-document rules of the project folder format: JSON, names, references, placeholders, schemas.

Owns the rules that can be decided from one file alone (sections 2.1 to 2.7 of
docs/plans/definition-first-projects/spec-m1-m2.md): strict JSON decoding, the
name and reference syntax, the placeholder syntax of commands, the form of
relative paths, and validation against the JSON Schema files in schemas/,
whose errors it turns into a field pointer and one plain sentence. It also owns
Problem, the one shape every checker in this package reports.
"""
from dataclasses import dataclass
from functools import lru_cache
import json
import math
from pathlib import Path
import re

import jsonschema

PROJECT_FORMAT = 'tuldok_project_v1'
DEFINITION_FORMAT = 'tuldok_definition_v1'

# Kind -> the directory that holds definitions of that kind.
DIRECTORIES = {
    'dataset': 'datasets',
    'model': 'models',
    'recipe': 'recipes',
    'benchmark': 'benchmarks',
    'step': 'steps',
    'environment': 'environments',
    'chart': 'charts',
    'annotation': 'annotations',
}
KINDS = {directory: kind for kind, directory in DIRECTORIES.items()}

# Which directories each reference-taking field accepts (2.6, 2.7). The keys
# are the edge roles of 2.9 without their ":<name>" suffix, the role of an
# annotation task's dataset (spec-d4.md section 1), and the two roles
# of a recipe's place on the map (spec-w1.md section 1): derived_from and
# compared_with.
ACCEPTS = {
    'input': ('datasets', 'recipes', 'steps'),
    'environment': ('environments',),
    'model': ('models',),
    'subject': ('recipes',),
    'cases': ('datasets',),
    'benchmark': ('benchmarks',),
    'dataset': ('datasets',),
    'annotations': ('annotations',),
    'derived': ('recipes',),
    'compared': ('recipes',),
}

STATISTICS = ('mean', 'median', 'p10', 'p90', 'min', 'max')

NAME = re.compile(r'^[a-z0-9][a-z0-9._-]{0,119}$')
_REFERENCE = re.compile(r'^([a-z]+)/([a-z0-9][a-z0-9._-]{0,119})$')
_SCHEMAS = Path(__file__).resolve().parent / 'schemas'


@dataclass(frozen=True)
class Problem:
    """One finding: severity is 'error' or 'warning'; path is relative to the project folder."""
    severity: str
    path: str
    pointer: str
    message: str

    def as_dict(self):
        return {'severity': self.severity, 'path': self.path,
                'pointer': self.pointer, 'message': self.message}


class DocumentError(ValueError):
    """A file is not a strict UTF-8 JSON object."""


# ---------------------------------------------------------------- JSON (2.2)

def _refuse_constant(name):
    raise DocumentError(f'The file contains {name}, which this format does not allow.')


def _finite_float(text):
    value = float(text)
    if not math.isfinite(value):
        raise DocumentError(f'The number {text} is too large to represent; write a smaller number.')
    return value


def _unique_object(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise DocumentError(f'The key {key!r} appears twice in one object; keep only one.')
        seen[key] = value
    return seen


def decode(raw):
    """Return the JSON object in raw (bytes or str); raise DocumentError on anything 2.2 refuses."""
    if isinstance(raw, bytes):
        try:
            raw = raw.decode('utf-8')
        except UnicodeDecodeError as exc:
            raise DocumentError(f'The file is not UTF-8 text (bad byte at offset {exc.start}).') from None
    try:
        value = json.loads(raw, object_pairs_hook=_unique_object,
                           parse_constant=_refuse_constant, parse_float=_finite_float)
    except json.JSONDecodeError as exc:
        raise DocumentError(f'The file is not valid JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}.') from None
    if not isinstance(value, dict):
        raise DocumentError('The file must hold one JSON object, not a list or a single value.')
    return value


# ------------------------------------------------------ names and references

def is_name(value):
    """True when value follows the name rule of 2.1."""
    return isinstance(value, str) and NAME.fullmatch(value) is not None


def parse_reference(value):
    """Return (directory, name) for a reference string such as 'datasets/x', or None."""
    if not isinstance(value, str):
        return None
    match = _REFERENCE.fullmatch(value)
    if match is None or match.group(1) not in KINDS:
        return None
    return match.group(1), match.group(2)


def reference(directory, name):
    return f'{directory}/{name}'


def pointer(*parts):
    """Return the JSON pointer for these path parts (keys or list indexes)."""
    return ''.join('/' + str(part).replace('~', '~0').replace('/', '~1') for part in parts)


# ------------------------------------------------------------- paths (2.6)

def relative_path_problem(value):
    """Return a sentence fragment when value is not a normal relative path, else None.

    Normal means: not empty, not absolute, no '..', and no empty or '.' parts
    (so no doubled or trailing '/').
    """
    if not isinstance(value, str) or not value:
        return 'must be a non-empty relative path'
    if '\x00' in value:
        return 'contains a NUL character'
    if value.startswith('/'):
        return 'is absolute; write it relative'
    parts = value.split('/')
    if '..' in parts:
        return "contains '..'; paths must stay inside their root"
    if any(part in ('', '.') for part in parts):
        return "is not in normal form; remove empty or '.' parts and any trailing '/'"
    return None


# ------------------------------------------------------- placeholders (2.6)

def placeholders(text):
    """Return the names written as {name} in text; raise ValueError on a brace with no partner.

    '{{' and '}}' are literal braces and are not returned.
    """
    names, index = [], 0
    while index < len(text):
        char = text[index]
        if char == '{':
            if text.startswith('{{', index):
                index += 2
                continue
            end = text.find('}', index + 1)
            inner = text[index + 1:end] if end >= 0 else ''
            if end < 0 or '{' in inner:
                raise ValueError('has a "{" with no closing "}"; write "{{" for a literal brace')
            names.append(inner)
            index = end + 1
        elif char == '}':
            if text.startswith('}}', index):
                index += 2
                continue
            raise ValueError('has a "}" with no opening "{"; write "}}" for a literal brace')
        else:
            index += 1
    return names


def command_placeholder_problems(text, *, inputs, has_settings, benchmark):
    """Return sentences for each placeholder in text that 2.6 does not allow here.

    inputs is the set of declared input names; has_settings says whether the run
    has settings or settings_file; benchmark says whether {subject} is allowed.
    """
    try:
        names = placeholders(text)
    except ValueError as exc:
        return [f'The text {text!r} {exc}.']
    problems = []
    for name in names:
        if name == 'output':
            continue
        if name == 'settings':
            if not has_settings:
                problems.append('{settings} is used but the run has neither settings nor settings_file; add one or remove the placeholder.')
            continue
        if name.startswith('inputs.'):
            if name[len('inputs.'):] not in inputs:
                problems.append(f'{{{name}}} names an input that run.inputs does not declare; declare it or fix the name.')
            continue
        if name in ('subject', 'subject.name'):
            if not benchmark:
                problems.append(f'{{{name}}} is only allowed in a benchmark; remove it.')
            continue
        problems.append(f'{{{name}}} is not a known placeholder; use {{output}}, {{settings}}, {{inputs.<name>}}, or write "{{{{" for a literal brace.')
    return problems


def argument_placeholder_problems(text, *, has_recipe):
    """Return sentences for placeholders a benchmark subject's argument may not use (only {recipe})."""
    try:
        names = placeholders(text)
    except ValueError as exc:
        return [f'The text {text!r} {exc}.']
    problems = []
    for name in names:
        if name == 'recipe':
            if not has_recipe:
                problems.append('{recipe} is used but this subject has no recipe; add one or remove the placeholder.')
        else:
            problems.append(f'{{{name}}} is not allowed in a subject argument; only {{recipe}} is.')
    return problems


# ----------------------------------------------------------------- schemas

@lru_cache(maxsize=None)
def validator(name):
    """Return the cached Draft 2020-12 validator for schemas/<name>.schema.json ('project' or a kind)."""
    schema = json.loads((_SCHEMAS / f'{name}.schema.json').read_text(encoding='utf-8'))
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


def _short(value):
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= 60 else text[:57] + '...'


def _translate(error):
    """Yield (pointer, message) for one jsonschema error."""
    at = list(error.absolute_path)
    where = pointer(*at)
    schema = error.schema if isinstance(error.schema, dict) else {}
    if error.validator == 'required':
        for field in error.validator_value:
            if isinstance(error.instance, dict) and field not in error.instance and error.message.startswith(repr(field)):
                yield pointer(*at, field), f'Add the required field {field!r}.'
        return
    if error.validator == 'additionalProperties' and schema.get('additionalProperties') is False:
        known = schema.get('properties', {})
        for field in sorted(error.instance):
            if field not in known:
                yield pointer(*at, field), f'Remove the unknown field {field!r}; this format does not define it here.'
        return
    description = schema.get('description')
    if 'propertyNames' in error.absolute_schema_path:
        # jsonschema reports a bad key at its object; point at the key instead.
        expected = f'; expected {description}' if description else ''
        yield pointer(*at, error.instance), f'The key {error.instance!r} is not valid here{expected}.'
        return
    if error.validator == 'const':
        yield where, f'The value must be {json.dumps(error.validator_value)}.'
        return
    if error.validator == 'not' and description:
        yield where, description
        return
    if description:
        yield where, f'The value {_short(error.instance)} is not valid here; expected {description}.'
        return
    message = error.message if len(error.message) <= 200 else error.message[:197] + '...'
    yield where, message[0].upper() + message[1:] + ('' if message.endswith('.') else '.')


def schema_problems(name, document):
    """Return (pointer, message) pairs for every way document breaks schemas/<name>.schema.json."""
    found = []
    for error in validator(name).iter_errors(document):
        found.extend(_translate(error))
    return sorted(set(found))
