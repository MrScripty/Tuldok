"""Sweeps: searching a recipe's settings on this machine, one trial after another.

Owns docs/plans/training-and-curation/spec-t7.md. A sweep definition
(sweeps/<name>.json) names a recipe, the settings it varies and their ranges,
a strategy (grid, random, or successive halving that stops poor trials
early), one or two objectives read from the trials' training logs, and a
budget. Here are: the checks a sweep needs beyond its schema (check_sweeps,
called by check.check_map); its schedule (schedule, a pure function of the
definition); the halving rule (Rungs, goes_on); a trial's definition
(trial_text); a sweep as a plan (plan, called by plan.build_plan for a sweep
target); the runner the build request worker calls for such a plan (execute),
which builds what the recipe needs, then each trial as a build step with one
plan id and one snapshot of the code, while a watcher reads the trial's
training/metrics.jsonl to record where it is and to stop it (its cancel
file) when halving prunes it or the minutes are spent; the two tables that
record a sweep's runs and trials; the reads sweeps and sweep; and the map's
groups of trials (map_groups).

The runner never runs the project's code in this process: a trial is a
recipe built by builds._Build.run_one under the launcher, exactly as a build
step. It writes nothing to the folder; trials are kept as unsaved edits of
the working copy (set_definition), saved with the rest by save.
"""
import copy
import datetime
import hashlib
import itertools
import json
import math
import os
import random
import threading
import time
import uuid

from psycopg.types.json import Jsonb

from . import builds, comparing, documents, launcher, local, snapshot, store, training
from .store import ProjectError

DIRECTORY = 'sweeps'
PARAMETERS = 16
GRID_MOST = 100_000          # points of a grid at most
DRAWS_WITHOUT_NEW = 1000     # a random schedule ends after this many draws in a row with nothing new
RUNGS = 32                   # rungs of halving at most
DEFAULT_FACTOR = 3
DEFAULT_COUNT = None         # a grid's range needs count; random and halving do not
SPECIAL = ('time', 'step')   # objectives that are the last logged time or step
WATCH_SECONDS = 0.25         # how often a running trial's log is read
LATEST_SECONDS = 1.0         # how often the latest line of a running trial is recorded
RUNS_SHOWN = 20
NAME_PART = 100              # characters of a sweep's name in its trials' names
TRIAL_STATES = ('running', 'completed', 'pruned', 'stopped', 'failed')
ORPHAN_PROBLEM = 'Tuldok stopped while this sweep ran.'

TABLES = (
    '''CREATE TABLE IF NOT EXISTS {schema}.sweep_runs (
           id text PRIMARY KEY, sweep text NOT NULL, request_id text, plan_id text,
           state text NOT NULL, ended text, problem text,
           sweep_sha256 text NOT NULL, recipe text NOT NULL, recipe_sha256 text NOT NULL,
           strategy jsonb NOT NULL, objectives jsonb NOT NULL, budget jsonb NOT NULL,
           started_at timestamptz NOT NULL, finished_at timestamptz,
           owner_pid integer, owner_boot text)''',
    'CREATE INDEX IF NOT EXISTS sweep_runs_sweep ON {schema}.sweep_runs (sweep, started_at)',
    '''CREATE TABLE IF NOT EXISTS {schema}.sweep_trials (
           sweep_run text NOT NULL, number integer NOT NULL, reference text NOT NULL, "values" jsonb NOT NULL,
           state text NOT NULL, reused boolean NOT NULL DEFAULT false, run_id text,
           started_at timestamptz, finished_at timestamptz, seconds double precision,
           rungs jsonb NOT NULL DEFAULT '[]', objectives jsonb, latest jsonb, problem text,
           PRIMARY KEY (sweep_run, number))''',
)
_RUN_COLUMNS = ('id', 'sweep', 'request_id', 'plan_id', 'state', 'ended', 'problem', 'sweep_sha256', 'recipe',
                'recipe_sha256', 'strategy', 'objectives', 'budget', 'started_at', 'finished_at')
_TRIAL_COLUMNS = ('number', 'reference', 'values', 'state', 'reused', 'run_id', 'started_at', 'finished_at',
                  'seconds', 'rungs', 'objectives', 'latest', 'problem')


def _sha256(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


# ================================================================ paths into run.settings

def parts(path):
    """The parts of a dotted path: keys, and whole numbers for parts of digits (a list's index)."""
    return [int(part) if part.isdigit() else part for part in path.split('.')]


def _child(holder, part):
    """(found, value) of one part in an object or a list."""
    if isinstance(holder, dict) and isinstance(part, str) and part in holder:
        return True, holder[part]
    if isinstance(holder, dict) and isinstance(part, int) and str(part) in holder:
        return True, holder[str(part)]
    if isinstance(holder, list) and isinstance(part, int) and part < len(holder):
        return True, holder[part]
    return False, None


def path_problem(settings, path):
    """A sentence when path cannot be set in settings (its parents missing, or not objects or lists), else None."""
    holder = settings
    steps = parts(path)
    for depth, part in enumerate(steps[:-1]):
        found, value = _child(holder, part)
        if not found:
            return f'{".".join(map(str, steps[:depth + 1]))} is not in the recipe\'s settings'
        if not isinstance(value, (dict, list)):
            return f'{".".join(map(str, steps[:depth + 1]))} is not an object or a list in the recipe\'s settings'
        holder = value
    last = steps[-1]
    if isinstance(holder, list) and not (isinstance(last, int) and last < len(holder)):
        return f'{path} indexes a list of {len(holder)} items past its end'
    return None


def set_path(settings, path, value):
    """Set value at path in settings (changed in place); the parents exist (path_problem said so)."""
    holder = settings
    steps = parts(path)
    for part in steps[:-1]:
        holder = _child(holder, part)[1]
    last = steps[-1]
    if isinstance(holder, list):
        holder[last] = value
    else:
        holder[str(last)] = value


# ================================================================ checking

def check_sweeps(definitions, add):
    """Report the rules of section 2 that need the recipe, or that a schema cannot say, for every sweep.

    definitions maps references to folder.Definition. A missing recipe is
    check_references' problem.
    """
    for reference, definition in definitions.items():
        document = definition.document
        if definition.kind != 'sweep' or not isinstance(document, dict):
            continue
        path = definition.path
        parameters = [item for item in document.get('parameters') or [] if isinstance(item, dict)]
        seen = set()
        for index, item in enumerate(parameters):
            name = item.get('path')
            if not isinstance(name, str):
                continue
            where = documents.pointer('parameters', index)
            if name in seen:
                add('error', path, where + '/path', f'{name} is varied twice; keep one parameter for it.')
            seen.add(name)
            low, high = item.get('low'), item.get('high')
            if _number(low) and _number(high):
                if low >= high:
                    add('error', path, where, f'low ({low}) must be less than high ({high}).')
                if item.get('scale') == 'log' and low <= 0:
                    add('error', path, where + '/low', 'A log scale needs low above 0.')
                if item.get('integer') and not (float(low).is_integer() and float(high).is_integer()):
                    add('error', path, where, 'An integer range needs whole numbers for low and high.')
            values = item.get('values')
            if isinstance(values, list) and len({json.dumps(value) for value in values}) != len(values):
                add('error', path, where + '/values', 'The values repeat; list each once.')
        strategy = document.get('strategy') if isinstance(document.get('strategy'), dict) else {}
        if strategy.get('kind') == 'grid':
            for index, item in enumerate(parameters):
                if 'low' in item and 'count' not in item:
                    add('error', path, documents.pointer('parameters', index),
                        'A grid takes count points of a range; add count (2 to 64).')
            if not any(('low' in item and 'count' not in item) for item in parameters):
                size = math.prod(len(_grid_points(item)) for item in parameters) if parameters else 0
                trials = (document.get('budget') or {}).get('trials') if isinstance(document.get('budget'), dict) else None
                if size > GRID_MOST:
                    add('error', path, '/parameters', f'The grid has {size:,} points; at most {GRID_MOST:,} are allowed.')
                elif isinstance(trials, int) and size > trials:
                    add('warning', path, '/budget/trials', f'The grid has {size:,} points and the budget {trials}; '
                                                           f'the first {trials} in order are run.')
        if strategy.get('kind') == 'halving' and strategy.get('unit', 'step') == 'step' and _number(strategy.get('min')) \
                and not float(strategy['min']).is_integer():
            add('error', path, '/strategy/min', 'A rung in steps is a whole number of steps.')
        objectives = [item for item in document.get('objectives') or [] if isinstance(item, dict)]
        if len({item.get('metric') for item in objectives}) != len(objectives):
            add('error', path, '/objectives', 'The two objectives name the same metric; name two.')
        recipe = definitions.get(document.get('recipe')) if isinstance(document.get('recipe'), str) else None
        if recipe is None or recipe.kind != 'recipe' or not isinstance(recipe.document, dict):
            continue
        run = recipe.document.get('run') if isinstance(recipe.document.get('run'), dict) else None
        if run is None or 'command' not in run:
            add('error', path, '/recipe', f'{document["recipe"]} has no run.command, so it has no trials to run.')
            continue
        if not isinstance(run.get('settings'), dict):
            add('error', path, '/recipe', f'{document["recipe"]} has no settings written in it'
                + (' (its settings are in a file)' if 'settings_file' in run else '')
                + '; a sweep varies run.settings. Branch from here gives a branch its own copy.')
            continue
        for index, item in enumerate(parameters):
            if isinstance(item.get('path'), str):
                wrong = path_problem(run['settings'], item['path'])
                if wrong:
                    add('error', path, documents.pointer('parameters', index, 'path'), f'{wrong}.')


# ================================================================ the schedule

def rounded(value, integer=False, low=None, high=None):
    """A drawn value as kept: 6 significant digits, or for an integer floor(x + 0.5) within low and high."""
    if integer:
        whole = math.floor(value + 0.5)
        return int(min(high, max(low, whole)))
    return float(f'{value:.6g}')


def _range_value(item, u):
    low, high = float(item['low']), float(item['high'])
    if item.get('scale') == 'log':
        value = math.exp(math.log(low) + u * (math.log(high) - math.log(low)))
    else:
        value = low + u * (high - low)
    return rounded(value, bool(item.get('integer')), low, high)


def _grid_points(item):
    if 'values' in item:
        return list(item['values'])
    count = item.get('count') or 2
    points = []
    for index in range(count):
        value = _range_value(item, index / (count - 1))
        if not any(_same(value, point) for point in points):
            points.append(value)
    return points


def _same(a, b):
    return comparing._canon(a) == comparing._canon(b)


def _key(values):
    return tuple(comparing._canon(value) for value in values)


def schedule(document):
    """Yield {path: value} for each trial in order (section 3); finite for a grid, until exhausted for random."""
    parameters = document['parameters']
    names = [item['path'] for item in parameters]
    strategy = document['strategy']
    if strategy['kind'] == 'grid':
        for combination in itertools.product(*(_grid_points(item) for item in parameters)):
            yield dict(zip(names, combination))
        return
    rng = random.Random(strategy['seed'])
    seen = set()
    misses = 0
    while misses < DRAWS_WITHOUT_NEW:
        drawn = []
        for item in parameters:
            if 'values' in item:
                drawn.append(item['values'][rng.randrange(len(item['values']))])
            else:
                drawn.append(_range_value(item, rng.random()))
        key = _key(drawn)
        if key in seen:
            misses += 1
            continue
        misses = 0
        seen.add(key)
        yield dict(zip(names, drawn))


# ================================================================ halving

def rung_points(strategy):
    """The rungs of halving: min × factor^k, k from 0, at most RUNGS; whole numbers in steps."""
    factor = strategy.get('factor', DEFAULT_FACTOR)
    first = strategy['min']
    steps = strategy.get('unit', 'step') == 'step'
    return [int(first) * factor ** k if steps else float(first) * factor ** k for k in range(RUNGS)]


class Rungs:
    """Which rungs a trial crosses as its lines arrive: feed(unit value, latest metric value) -> [(k, point, value)]."""

    def __init__(self, points):
        self.points, self.next = points, 0

    def feed(self, at, value):
        crossed = []
        while self.next < len(self.points) and at >= self.points[self.next]:
            crossed.append((self.next, self.points[self.next], value))
            self.next += 1
        return crossed


def goes_on(value, recorded, better, factor):
    """(goes on, n, kept): a trial's value at a rung against the values recorded there before it (section 5)."""
    n = len(recorded) + 1
    kept = math.ceil(n / factor)
    if n < factor:
        return True, n, kept
    beaten_by = sum(1 for other in recorded if (other > value if better == 'higher' else other < value))
    return beaten_by < kept, n, kept


# ================================================================ objectives

def _objective_of(log, objective):
    """An objective's value from a read metrics log (training._Metrics), or None."""
    metric = objective['metric']
    if metric in SPECIAL:
        if not len(log.steps):
            return None
        return float(log.times[-1]) if metric == 'time' else int(log.steps[-1])
    held = log.series.get(metric)
    if held is None:
        return None
    finite = [value for value in held[1] if math.isfinite(value)]
    if not finite:
        return None
    if objective.get('take', 'last') == 'best':
        return max(finite) if objective['better'] == 'higher' else min(finite)
    return finite[-1]


def read_objectives(output, objectives, run_id=''):
    """{metric: value} of a trial's output directory as its training log now is (None where it has none)."""
    run = training.Run(run_id, 'succeeded', output)
    with training._Read(run, training.METRICS) as log:
        if log is None:
            return {item['metric']: None for item in objectives}, None
        latest = {'step': int(log.steps[-1]), 'time': float(log.times[-1])} if len(log.steps) else None
        return {item['metric']: _objective_of(log, item) for item in objectives}, latest


# ================================================================ a trial's definition

def trial_document(sweep_reference, sweep, recipe_reference, recipe, number, values):
    """The document of trial number of a sweep (section 4)."""
    shown = ', '.join(f'{path} = {json.dumps(value)}' for path, value in values.items())
    document = {'format': documents.DEFINITION_FORMAT, 'kind': 'recipe',
                'title': f'{sweep["title"]} · trial {number}'[:200],
                'description': f'Trial {number} of {sweep_reference}: {shown}.'[:4000]}
    for key in ('model', 'group'):
        if key in recipe:
            document[key] = recipe[key]
    document['labels'] = {'short': f'T{number}'}
    document['change'] = 'sweep-trial'
    document['derived_from'] = recipe_reference
    document['sweep'] = {'definition': sweep_reference, 'trial': number, 'values': dict(values)}
    run = copy.deepcopy(recipe['run'])
    for path, value in values.items():
        set_path(run['settings'], path, value)
    document['run'] = run
    return document


def trial_text(sweep_reference, sweep, recipe_reference, recipe, number, values):
    return json.dumps(trial_document(sweep_reference, sweep, recipe_reference, recipe, number, values),
                      indent=2, ensure_ascii=False) + '\n'


def trial_names(sweep_reference, number):
    """The names a trial may take, in order: <sweep>-<NNN>, then -2, -3, ..."""
    base = f'{sweep_reference.split("/", 1)[1][:NAME_PART]}-{number:03d}'
    yield base
    for suffix in itertools.count(2):
        yield f'{base}-{suffix}'


def place_trial(texts, sweep_reference, number, text):
    """(reference, same) for a trial's text: the first name free or holding the same text (same true)."""
    for name in trial_names(sweep_reference, number):
        reference = f'recipes/{name}'
        held = texts.get(reference)
        if held is None:
            return reference, False
        if held == text:
            return reference, True


# ================================================================ reading the tables

def _q(schema, template):
    from psycopg import sql
    return sql.SQL(template).format(schema=sql.Identifier(schema))


def reap(project):
    """Mark failed every running sweep run whose process is gone (or ran before this boot)."""
    rows = project._execute("SELECT id, owner_pid, owner_boot FROM {schema}.sweep_runs WHERE state = 'running'").fetchall()
    boot = builds.boot_id()
    for run_id, pid, owner_boot in rows:
        if owner_boot != boot or pid is None or not builds._alive(pid) or pid == os.getpid() and not _active(run_id):
            project._execute('''UPDATE {schema}.sweep_runs SET state = 'failed', ended = 'failed', problem = %s,
                                    finished_at = now() WHERE id = %s AND state = 'running' ''', (ORPHAN_PROBLEM, run_id))
            project._execute("UPDATE {schema}.sweep_trials SET state = 'stopped', finished_at = now(), problem = %s "
                             "WHERE sweep_run = %s AND state = 'running'", (ORPHAN_PROBLEM, run_id))


_ACTIVE = set()          # sweep runs this process is running
_ACTIVE_LOCK = threading.Lock()


def _active(run_id):
    with _ACTIVE_LOCK:
        return run_id in _ACTIVE


def _runs_of(project, reference, limit=RUNS_SHOWN):
    rows = project._execute('SELECT ' + ', '.join(_RUN_COLUMNS) + ' FROM {schema}.sweep_runs WHERE sweep = %s '
                            'ORDER BY started_at DESC, id LIMIT %s', (reference, limit)).fetchall()
    return [dict(zip(_RUN_COLUMNS, row)) for row in rows]


def _trials_of(project, run_id):
    rows = project._execute('SELECT ' + ', '.join(f'"{c}"' if c == 'values' else c for c in _TRIAL_COLUMNS)
                            + ' FROM {schema}.sweep_trials WHERE sweep_run = %s ORDER BY number', (run_id,)).fetchall()
    return [dict(zip(_TRIAL_COLUMNS, row)) for row in rows]


def _texts(project, references=None):
    if references is None:
        rows = project._execute(f'SELECT {store._REFERENCE_SQL}, text FROM {{schema}}.definitions WHERE NOT removed')
    else:
        rows = project._execute(f'SELECT {store._REFERENCE_SQL}, text FROM {{schema}}.definitions '
                                f'WHERE NOT removed AND {store._REFERENCE_SQL} = ANY(%s)', (list(references),))
    return dict(rows.fetchall())


def _definition(project, reference):
    directory, name = documents.parse_reference(reference) or (None, None)
    row = project._execute('SELECT text, document FROM {schema}.definitions WHERE directory = %s AND name = %s '
                           'AND NOT removed', (directory, name)).fetchone()
    return (None, None) if row is None else row


def find(project, text):
    """The reference of the sweep named by text (sweeps/<name> or a bare name); not-found otherwise."""
    reference = text if isinstance(text, str) and text.startswith(DIRECTORY + '/') else f'{DIRECTORY}/{text}'
    parsed = documents.parse_reference(reference)
    if parsed is None or parsed[0] != DIRECTORY or _definition(project, reference)[0] is None:
        raise ProjectError(f'There is no sweep {text}.', 'not-found', references=[reference])
    return reference


def sweep_state(project, reference, texts=None):
    """not-built, running, built (its last run finished with the texts as they are now) or failed."""
    runs = _runs_of(project, reference, 1)
    if not runs:
        return 'not-built', None
    last = runs[0]
    if last['state'] == 'running':
        return 'running', last
    texts = texts or {}
    sweep_text = texts.get(reference) or _definition(project, reference)[0]
    recipe_text = texts.get(last['recipe']) or _definition(project, last['recipe'])[0]
    same = (sweep_text is not None and _sha256(sweep_text) == last['sweep_sha256'] and recipe_text is not None
            and _sha256(recipe_text) == last['recipe_sha256'])
    if last['state'] == 'finished' and same:
        return 'built', last
    if last['state'] == 'failed' and same:
        return 'failed', last
    return 'not-built', last


# ================================================================ a sweep as a plan

def _strategy_words(document):
    strategy, budget = document['strategy'], document['budget']
    if strategy['kind'] == 'grid':
        words = 'a grid'
    elif strategy['kind'] == 'random':
        words = f'random draws (seed {strategy.get("seed")})'
    else:
        rungs = ', '.join(f'{point:g}' for point in rung_points(strategy)[:4])
        words = (f'random draws (seed {strategy.get("seed")}) with successive halving on {strategy.get("metric")} at '
                 f'{strategy.get("unit", "step")}s {rungs}, … (keeping the best 1/{strategy.get("factor", DEFAULT_FACTOR)})')
    limit = f'at most {budget["trials"]} trials' + (f' and {budget["minutes"]:g} minutes' if budget.get('minutes') else '')
    return f'Trials of {document["recipe"]} by {words}, {limit}, one at a time.'


def plan(project, targets, *, every=False):
    """The plan of a sweep (section 5): what its recipe needs, then the sweep's own step. Refused invalid unless alone."""
    from . import plan as planning
    if every or len(targets) != 1:
        raise ProjectError('A sweep is planned and built alone: name it as the only target, without every.',
                           'invalid', references=list(targets))
    reference = targets[0]
    text, document = _definition(project, reference)
    if text is None:
        raise ProjectError(f'There is no definition {reference}.', 'not-found', references=[reference])
    recipe_reference = document['recipe']
    recipe_text, recipe = _definition(project, recipe_reference)
    if recipe_text is None:
        raise ProjectError(f'{reference} varies {recipe_reference}, which is not a recipe of the project.',
                           'not-found', references=[recipe_reference])
    made = planning.build_plan(project, [recipe_reference])
    own = next((step for step in made['steps'] if step['reference'] == recipe_reference), None)
    steps = [dict(step) for step in made['steps'] if step['reference'] != recipe_reference]
    state, _last = sweep_state(project, reference, {reference: text, recipe_reference: recipe_text})
    blocked_by = [cause for cause in (own or {}).get('blocked_by', []) if cause['reference'] != recipe_reference]
    run = recipe.get('run') if isinstance(recipe.get('run'), dict) else {}
    budget = document['budget']
    reasons = [_strategy_words(document)]
    if not isinstance(run.get('settings'), dict) or 'command' not in run:
        action = 'blocked'
        blocked_by.append({'reference': recipe_reference, 'rebuild': 'no',
                           'reason': 'it has no run.command with settings written in it'})
    elif blocked_by or (own and own['action'] == 'blocked' and own['blocked_by'] and not
                        all(cause['reference'] == recipe_reference for cause in own['blocked_by'])):
        action = 'blocked'
    elif any(step['action'] == 'blocked' for step in steps):
        action = 'blocked'
    else:
        action = 'built' if state == 'built' else 'build'
    for number, step in enumerate(steps, 1):
        step['number'] = number
    steps.append({'number': len(steps) + 1, 'reference': reference, 'kind': 'sweep', 'title': document.get('title'),
                  'state': state, 'action': action, 'command': run.get('command'),
                  'environment': run.get('environment'), 'step': None, 'annotations': [],
                  'inputs': (own or {}).get('inputs', {}),
                  'resources': {'gpu': ((run.get('resources') or {}).get('gpu') is True),
                                'cpu_threads': None, 'memory_gb': None,
                                'wall_hours': budget['minutes'] / 60 if budget.get('minutes') else None,
                                'disk_gb': None},
                  'estimate': None, 'blocked_by': blocked_by[:planning.CAUSE_LIMIT],
                  'blocked_by_more': max(0, len(blocked_by) - planning.CAUSE_LIMIT),
                  'reasons': reasons, 'scratch': False, 'adopted': False,
                  'recipe': recipe_reference, 'trials': budget['trials']})
    blocked = [step['reference'] for step in steps if step['action'] == 'blocked']
    disk_gb, disk_unknown = planning._total(steps, 'disk_gb')
    wall_hours, wall_unknown = planning._total(steps, 'wall_hours')
    estimated_disk_gb, estimated_disk_steps = planning._estimated(steps, 'disk_bytes', 1000 ** 3)
    estimated_wall_hours, estimated_wall_steps = planning._estimated(steps, 'wall_seconds', 3600)
    notes = [note for note in made['notes']] + [
        f'{reference} builds trials of {recipe_reference}, each a recipe derived from it, one after another; '
        'one approval covers them all.']
    return {'targets': [reference], 'every': False, 'buildable': reference not in blocked and not blocked,
            'blocked_targets': [reference] if blocked else [],
            'counts': {action_name: sum(step['action'] == action_name for step in steps)
                       for action_name in planning.ACTIONS},
            'gpu_steps': sum(step['action'] == 'build' and step['resources']['gpu'] is True for step in steps),
            'disk_gb': disk_gb, 'disk_unknown': disk_unknown, 'wall_hours': wall_hours, 'wall_unknown': wall_unknown,
            'estimated_disk_gb': estimated_disk_gb, 'estimated_disk_steps': estimated_disk_steps,
            'estimated_wall_hours': estimated_wall_hours, 'estimated_wall_steps': estimated_wall_steps,
            'notes': notes, 'steps': steps, 'sweep': reference}


# ================================================================ running

def _connect(dsn):
    import psycopg
    return psycopg.connect(store.connection_info(dsn), autocommit=True)


class _Watch:
    """Reads a running trial's metrics, records where it is, and stops it when halving prunes it or time is up."""

    def __init__(self, sweep, connection, schema, run_id, number, recorded, deadline, clock):
        self.sweep, self.connection, self.schema = sweep, connection, schema
        self.sweep_run, self.number, self.recorded = run_id, number, recorded
        self.deadline, self.clock = deadline, clock
        strategy = sweep['strategy']
        self.halving = strategy if strategy['kind'] == 'halving' else None
        self.rungs = Rungs(rung_points(strategy)) if self.halving else None
        self.metrics = [item['metric'] for item in sweep['objectives'] if item['metric'] not in SPECIAL]
        if self.halving and self.halving['metric'] not in self.metrics:
            self.metrics.append(self.halving['metric'])
        self.pointer = {name: 0 for name in self.metrics}
        self.latest = {name: None for name in self.metrics}
        self.best = {name: None for name in self.metrics}
        self.position = 0
        self.reached = []        # the rungs recorded: {rung, at, value, n, kept, goes_on}
        self.reason = None       # pruned, minutes
        self.problem = None
        self.directory = self.output = self.run_id = None
        self.written = 0.0
        self.done = threading.Event()
        self.lock = threading.Lock()
        self.thread = None

    def begin(self, item):
        self.directory, self.run_id = item['directory'], item['run_id']
        self.output = os.path.join(item['directory'], builds.OUTPUT)
        self.connection.execute(_q(self.schema, 'UPDATE {schema}.sweep_trials SET run_id = %s, started_at = now() '
                                                'WHERE sweep_run = %s AND number = %s'),
                                (self.run_id, self.sweep_run, self.number))
        self.thread = threading.Thread(target=self._loop, name=f'tuldok-sweep-trial-{self.number}', daemon=True)
        self.thread.start()

    def _loop(self):
        while not self.done.wait(WATCH_SECONDS):
            try:
                self.look()
            except Exception:  # a read that failed is tried again on the next look
                pass

    def end(self):
        self.done.set()
        if self.thread is not None:
            self.thread.join()
        try:
            self.look(final=True)
        except Exception:
            pass

    def _stop(self, reason, problem):
        if self.reason is None:
            self.reason, self.problem = reason, problem
            try:
                os.close(os.open(os.path.join(self.directory, launcher.CANCEL_FILE),
                                 os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o644))
            except OSError:
                pass  # the run ended meanwhile

    def look(self, final=False):
        with self.lock:
            if self.output is None:
                return
            changed = False
            run = training.Run(self.run_id or '', 'running', self.output)
            with training._Read(run, training.METRICS) as log:
                if log is not None:
                    changed = self._lines(log)
                    step = int(log.steps[-1]) if len(log.steps) else None
                    at = float(log.times[-1]) if len(log.times) else None
                else:
                    step = at = None
            if not final and self.reason is None and self.deadline is not None and self.clock() >= self.deadline:
                self._stop('minutes', 'The sweep\'s minutes were spent while it ran.')
            now = self.clock()
            if changed and (final or now - self.written >= LATEST_SECONDS or self.reached and self._fresh_rung):
                self._fresh_rung = False
                self.written = now
                latest = {'step': step, 'time': at, 'values': dict(self.latest)}
                self.connection.execute(_q(self.schema, 'UPDATE {schema}.sweep_trials SET latest = %s, rungs = %s '
                                                        'WHERE sweep_run = %s AND number = %s'),
                                        (Jsonb(latest), Jsonb(self.reached), self.sweep_run, self.number))

    _fresh_rung = False

    def _lines(self, log):
        count = len(log.steps)
        if count <= self.position:
            return False
        for index in range(self.position, count):
            for name in self.metrics:
                held = log.series.get(name)
                if held is None:
                    continue
                positions, values = held
                while self.pointer[name] < len(positions) and positions[self.pointer[name]] <= index:
                    value = values[self.pointer[name]]
                    if math.isfinite(value):
                        self.latest[name] = value
                    self.pointer[name] += 1
            if self.halving and self.reason is None:
                at = log.steps[index] if self.halving.get('unit', 'step') == 'step' else log.times[index]
                for rung, point, value in self.rungs.feed(at, self.latest[self.halving['metric']]):
                    if value is None:
                        continue
                    held = self.recorded.setdefault(rung, [])
                    keep, n, kept = goes_on(value, held, self.halving['better'], self.halving.get('factor', DEFAULT_FACTOR))
                    held.append(value)
                    self.reached.append({'rung': rung, 'at': point, 'value': value, 'n': n, 'kept': kept,
                                         'goes_on': keep})
                    self._fresh_rung = True
                    if not keep:
                        unit = self.halving.get('unit', 'step')
                        self._stop('pruned', f'Pruned by successive halving at rung {rung + 1} ({unit} {point}): '
                                             f'{self.halving["metric"]} {value:.6g} was not among the best {kept} of {n}.')
                        break
        self.position = count
        return True


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def execute(project_folder, made, *, request_id=None, extra_env=None, scratch=False, dsn=None, on_event=None,
            expect=None, stop=None, clock=time.monotonic):
    """Run a sweep's plan (plan()): what its recipe needs, then its trials; return what builds.execute returns.

    Refused as builds.execute refuses (blocked, running, the code, the
    commit). stop() is asked before each step and each trial; on_event is
    called with 'start' and 'end' for every run, as builds.execute calls it.
    ok is true when the sweep finished (its schedule or a budget spent).
    """
    folder = os.fspath(project_folder)
    reference = made['sweep']
    if made['blocked_targets']:
        raise ProjectError(f'{reference} cannot be built now. See plan for why.', 'blocked',
                           references=made['blocked_targets'])
    sweep_step = next(step for step in made['steps'] if step['kind'] == 'sweep')
    if sweep_step['state'] == 'running':
        raise ProjectError(f'{reference} is running; wait for it to end.', 'running', references=[reference])
    to_build = [step for step in made['steps'] if step['action'] == 'build' and step['kind'] != 'sweep']
    running = [step['reference'] for step in to_build if step['state'] == 'running']
    if running:
        raise ProjectError('Another build is running ' + ', '.join(running) + '; wait for it to end.', 'running',
                           references=running)
    outer = on_event or (lambda kind, item: None)
    build = builds._Build(folder, made, extra_env=extra_env, scratch=scratch, dsn=dsn, on_event=outer,
                          expect=copy.deepcopy(expect) if expect is not None else None)
    with builds.opened(folder, dsn) as project:
        state = project._state()
        code_paths = (store._read_project_file(state['folder']) or {}).get('code_paths')
        code_root = builds._code_root(project)
        home = local.home(project.project_id, create=True)
        schema = project.schema
        sweep_text, sweep = _definition(project, reference)
        recipe_reference = sweep['recipe']
        recipe_text, recipe = _definition(project, recipe_reference)
    try:
        build.code = snapshot.prepare(code_root, code_paths, home=home, scratch=scratch)
    except snapshot.SnapshotError as exc:
        raise builds._snapshot_error(exc) from None
    approved = (expect or {}).get('commit')
    if approved is not None and build.code.commit != approved:
        raise ProjectError(f'The code is at commit {build.code.commit[:12] or "(none)"}, not at '
                           f'{approved[:12]} as approved; ask for the build again.', 'stale')
    for used, text in ((reference, sweep_text), (recipe_reference, recipe_text)):
        wanted = ((expect or {}).get('definitions') or {}).get(used)
        if expect is not None and wanted != _sha256(text):
            raise ProjectError(f'{used} is not what the build was approved with; ask for the build again.', 'stale',
                               references=[used])
    result = {'plan_id': build.plan_id, 'confirmed': True, 'ok': False, 'steps': build.done, 'skipped': []}
    run_id = uuid.uuid4().hex
    connection = _connect(dsn)
    with _ACTIVE_LOCK:
        _ACTIVE.add(run_id)
    try:
        with builds.opened(folder, dsn) as project:
            project._execute('INSERT INTO {schema}.plans (id, created_at, targets, steps, scratch) '
                             'VALUES (%s, now(), %s, %s, %s)',
                             (build.plan_id, Jsonb(made['targets']), Jsonb(made['steps']), scratch))
            project._execute('''INSERT INTO {schema}.sweep_runs (id, sweep, request_id, plan_id, state, sweep_sha256,
                                    recipe, recipe_sha256, strategy, objectives, budget, started_at, owner_pid,
                                    owner_boot)
                                VALUES (%s, %s, %s, %s, 'running', %s, %s, %s, %s, %s, %s, now(), %s, %s)''',
                             (run_id, reference, request_id, build.plan_id, _sha256(sweep_text), recipe_reference,
                              _sha256(recipe_text), Jsonb(sweep['strategy']), Jsonb(sweep['objectives']),
                              Jsonb(sweep['budget']), os.getpid(), builds.boot_id()))
        ended, problem = _run(build, folder, dsn, connection, schema, run_id, reference, sweep, recipe_reference,
                              recipe, made, stop, clock)
    except BaseException as exc:
        connection.execute(_q(schema, '''UPDATE {schema}.sweep_runs SET state = 'failed', ended = 'failed',
                                             problem = %s, finished_at = now() WHERE id = %s'''),
                           (f'{type(exc).__name__}: {exc}'[:2000], run_id))
        connection.execute(_q(schema, "UPDATE {schema}.sweep_trials SET state = 'stopped', finished_at = now() "
                                      "WHERE sweep_run = %s AND state = 'running'"), (run_id,))
        raise
    finally:
        with _ACTIVE_LOCK:
            _ACTIVE.discard(run_id)
    final = {'failed': 'failed', 'cancelled': 'cancelled'}.get(ended, 'finished')
    connection.execute(_q(schema, '''UPDATE {schema}.sweep_runs SET state = %s, ended = %s, problem = %s,
                                         finished_at = now() WHERE id = %s'''), (final, ended, problem, run_id))
    connection.close()
    result['ok'] = final == 'finished'
    return result


def _run(build, folder, dsn, connection, schema, run_id, reference, sweep, recipe_reference, recipe, made, stop,
         clock):
    """The steps and trials of one sweep run; (why it ended, its problem)."""
    needed = {step['environment'] for step in made['steps'] if step['action'] == 'build' and step['environment']}
    for step in made['steps']:
        if step['kind'] == 'environment':
            if step['reference'] in needed:
                with builds.opened(folder, dsn) as project:
                    build.environment(project, step['reference'])
            continue
        if step['kind'] == 'sweep' or step['action'] != 'build':
            continue
        if stop is not None and stop():
            return 'cancelled', 'It was cancelled before its trials.'
        item = build.run_one(step['reference'])
        build.done.append(item)
        build.on_event('end', item)
        if item['state'] != 'succeeded':
            return 'failed', f'{step["reference"]} ended {item["state"]}: {item["problem"]}'

    budget = sweep['budget']
    started = clock()
    deadline = started + budget['minutes'] * 60 if budget.get('minutes') else None
    recorded = {}
    used = 0
    outer = build.on_event
    for number, values in enumerate(schedule(sweep), 1):
        if used >= budget['trials']:
            return 'trials', None
        if deadline is not None and clock() >= deadline:
            return 'minutes', None
        if stop is not None and stop():
            return 'cancelled', 'It was cancelled.'
        used += 1
        text = trial_text(reference, sweep, recipe_reference, recipe, number, values)
        with builds.opened(folder, dsn) as project:
            trial, same = place_trial(_texts(project), reference, number, text)
            built = same and (builds.status(project).get(trial) or {}).get('state') == 'built'
            problem = None
            if not same:
                try:
                    project.set_definition(trial, text)
                except ProjectError as exc:
                    shown = '; '.join(item.message for item in (exc.problems or [])[:3])
                    problem = f'The trial does not check: {exc}' + (f' {shown}' if shown else '')
            product = builds._current_product(project, trial) if built else None
        connection.execute(_q(schema, '''INSERT INTO {schema}.sweep_trials (sweep_run, number, reference, "values",
                                             state, reused, started_at) VALUES (%s, %s, %s, %s, 'running', %s, now())'''),
                           (run_id, number, trial, Jsonb(values), built))
        if problem is not None:
            _end_trial(connection, schema, run_id, number, 'failed', problem=problem)
            continue
        if built:
            found, latest = read_objectives(product['directory'], sweep['objectives'], product['run_id'])
            _end_trial(connection, schema, run_id, number, 'completed', run=product['run_id'], objectives=found,
                       latest=latest)
            continue
        if build.expect is not None:
            build.expect.setdefault('definitions', {})[trial] = _sha256(text)
        watch = _Watch(sweep, connection, schema, run_id, number, recorded, deadline, clock)

        def on_event(kind, item, watch=watch):
            if kind == 'start':
                watch.begin(item)
            outer(kind, item)

        build.on_event = on_event
        try:
            item = build.run_one(trial)
        finally:
            watch.end()
            build.on_event = outer
        build.done.append(item)
        outer('end', item)
        output = os.path.join(item['directory'], builds.OUTPUT)
        found, latest = read_objectives(output, sweep['objectives'], item['run_id'])
        latest = latest and {**latest, 'values': {name: value for name, value in watch.latest.items()}}
        if item['state'] == 'succeeded':
            state, why = 'completed', None
        elif item['state'] == 'cancelled' and watch.reason == 'pruned':
            state, why = 'pruned', watch.problem
        elif item['state'] == 'cancelled':
            state, why = 'stopped', watch.problem or 'It was stopped.'
        else:
            state, why = 'failed', item['problem']
        if state in ('pruned', 'stopped'):
            connection.execute(_q(schema, 'UPDATE {schema}.runs SET problem = %s WHERE id = %s'),
                               (why, item['run_id']))
        _end_trial(connection, schema, run_id, number, state, run=item['run_id'], objectives=found, latest=latest,
                   problem=why, seconds=item.get('seconds'), rungs=watch.reached)
        if state == 'stopped':
            if watch.reason == 'minutes':
                return 'minutes', None
            return 'cancelled', 'It was cancelled while a trial ran.'
    return 'schedule', None


def _end_trial(connection, schema, run_id, number, state, *, run=None, objectives=None, latest=None, problem=None,
               seconds=None, rungs=None):
    connection.execute(_q(schema, '''UPDATE {schema}.sweep_trials SET state = %s, run_id = coalesce(%s, run_id),
                                         objectives = %s, latest = coalesce(%s, latest), problem = %s, seconds = %s,
                                         rungs = coalesce(%s, rungs), finished_at = now()
                                     WHERE sweep_run = %s AND number = %s'''),
                       (state, run, Jsonb(objectives) if objectives is not None else None,
                        Jsonb(latest) if latest is not None else None, problem, seconds,
                        Jsonb(rungs) if rungs is not None else None, run_id, number))


# ================================================================ the reads

def _counts(trials):
    counts = {state: 0 for state in TRIAL_STATES}
    for trial in trials:
        counts[trial['state']] = counts.get(trial['state'], 0) + 1
    return counts


def _best(trials, objective):
    best = None
    for trial in trials:
        value = (trial['objectives'] or {}).get(objective['metric']) if trial['state'] == 'completed' else None
        if value is None:
            continue
        if best is None or (value > best['value'] if objective['better'] == 'higher' else value < best['value']):
            best = {'number': trial['number'], 'reference': trial['reference'], 'value': value}
    return best


def _frontier(trials, objectives):
    from . import charts
    if len(objectives) != 2:
        return []
    first, second = objectives
    points = [(trial['number'], (trial['objectives'] or {}).get(second['metric']),
               (trial['objectives'] or {}).get(first['metric'])) for trial in trials if trial['state'] == 'completed']
    points = [point for point in points if point[1] is not None and point[2] is not None]
    flags = charts.frontier([(x, y) for _, x, y in points], first['better'], second['better'])
    return [number for (number, _, _), on in zip(points, flags) if on]


def _axes(trials, parameters, objectives):
    """The trials as benchmark_axes answers a benchmark's subjects: the objectives and the parameters as axes."""
    metrics = []
    for objective in objectives:
        found = [(trial['objectives'] or {}).get(objective['metric']) for trial in trials]
        found = [value for value in found if value is not None]
        metrics.append({'id': objective['metric'], 'title': objective.get('title') or objective['metric'], 'units': '',
                        'better': objective['better'], 'positive': bool(found) and all(v > 0 for v in found),
                        'low': min(found) if found else None, 'high': max(found) if found else None})
    lead = objectives[0]['metric']
    settings, positions = [], {}
    for item in parameters:
        path = item['path']
        values = {trial['number']: trial['values'][path] for trial in trials if path in (trial['values'] or {})}
        if all(_number(value) for value in values.values()):
            axis = {'path': path, 'kind': 'number', 'categories': None,
                    'low': min(values.values()) if values else None, 'high': max(values.values()) if values else None}
            placed = dict(values)
        else:
            kinds = sorted({comparing._canon(value) for value in values.values()}, key=comparing._category_order)
            first = {}
            for value in values.values():
                first.setdefault(comparing._canon(value), value)
            axis = {'path': path, 'kind': 'category', 'categories': [first[kind] for kind in kinds],
                    'low': 0, 'high': max(0, len(kinds) - 1)}
            placed = {number: kinds.index(comparing._canon(value)) for number, value in values.items()}
        both = [trial for trial in trials if trial['state'] == 'completed' and trial['number'] in placed
                and (trial['objectives'] or {}).get(lead) is not None]
        axis['count'] = len(values)
        axis['distinct'] = len({comparing._canon(value) for value in values.values()})
        axis['association'] = comparing.spearman([placed[trial['number']] for trial in both],
                                                 [trial['objectives'][lead] for trial in both])
        settings.append(axis)
        positions[path] = placed
    subjects = [{'subject': trial['reference'], 'title': f'Trial {trial["number"]}', 'recipe': trial['reference'],
                 'number': trial['number'], 'state': trial['state'],
                 'metrics': {objective['metric']: (trial['objectives'] or {}).get(objective['metric'])
                             for objective in objectives},
                 'settings': {item['path']: positions[item['path']].get(trial['number']) for item in parameters}}
                for trial in trials]
    return {'benchmark': None, 'statistic': None, 'metrics': metrics, 'settings': settings, 'left_out': 0,
            'subjects': subjects}


def _running_objectives(trial, objectives):
    """A running trial's objectives so far, from its latest line (time and step as logged)."""
    latest = trial['latest'] or {}
    out = {}
    for objective in objectives:
        metric = objective['metric']
        out[metric] = latest.get(metric) if metric in SPECIAL else (latest.get('values') or {}).get(metric)
    return out


def _request_of(project, reference):
    row = project._execute('''SELECT id, state, requested_by, requested_at FROM {schema}.build_requests
                              WHERE targets = %s ORDER BY requested_at DESC, id LIMIT 1''',
                           (Jsonb([reference]),)).fetchone()
    return None if row is None else dict(zip(('id', 'state', 'requested_by', 'requested_at'), row))


def _rung_list(strategy, trials):
    if strategy['kind'] != 'halving':
        return []
    points = rung_points(strategy)
    reached = max([rung['rung'] for trial in trials for rung in trial['rungs'] or []], default=-1)
    return points[:max(2, reached + 2)]


def show(project, text, run=None):
    """The answer of the read sweep (section 6)."""
    reference = find(project, text)
    reap(project)
    sweep_text, document = _definition(project, reference)
    runs = _runs_of(project, reference)
    chosen = None
    if run is not None:
        chosen = next((item for item in runs if item['id'] == run), None)
        if chosen is None:
            raise ProjectError(f'{reference} has no run {run}.', 'not-found', references=[reference])
    elif runs:
        chosen = runs[0]
    trials = _trials_of(project, chosen['id']) if chosen else []
    defined = set(_texts(project, [trial['reference'] for trial in trials])) if trials else set()
    objectives = document.get('objectives') or []
    for trial in trials:
        trial['defined'] = trial['reference'] in defined
        if trial['state'] == 'running':
            trial['objectives'] = _running_objectives(trial, objectives)
    state, _ = sweep_state(project, reference)
    parameters = document.get('parameters') or []
    seconds = None
    if chosen:
        end = chosen['finished_at'] or _now()
        seconds = (end - chosen['started_at']).total_seconds()
    shown_run = None if chosen is None else {
        'id': chosen['id'], 'state': chosen['state'], 'ended': chosen['ended'], 'problem': chosen['problem'],
        'started_at': chosen['started_at'], 'finished_at': chosen['finished_at'], 'seconds': seconds,
        'trials': len(trials), 'counts': _counts(trials), 'request_id': chosen['request_id']}
    return {'reference': reference, 'title': document.get('title'), 'description': document.get('description'),
            'recipe': document.get('recipe'), 'parameters': parameters, 'strategy': document.get('strategy'),
            'objectives': objectives, 'budget': document.get('budget'), 'state': state,
            'changed': bool(chosen) and chosen['sweep_sha256'] != _sha256(sweep_text),
            'request': _request_of(project, reference), 'run': shown_run,
            'runs': [{'id': item['id'], 'state': item['state'], 'started_at': item['started_at'],
                      'trials': project._execute('SELECT count(*) FROM {schema}.sweep_trials WHERE sweep_run = %s',
                                                 (item['id'],)).fetchone()[0]} for item in runs],
            'trials': trials, 'best': _best(trials, objectives[0]) if objectives else None,
            'frontier': _frontier(trials, objectives), 'rungs': _rung_list(document.get('strategy') or {}, trials),
            'axes': _axes(trials, parameters, objectives) if objectives else None}


def listing(project):
    """The answer of the read sweeps: every sweep with its latest run in brief."""
    reap(project)
    rows = project._execute(f'SELECT {store._REFERENCE_SQL}, document FROM {{schema}}.definitions '
                            "WHERE directory = 'sweeps' AND NOT removed ORDER BY name").fetchall()
    out = []
    for reference, document in rows:
        state, last = sweep_state(project, reference)
        brief = None
        if last is not None:
            trials = _trials_of(project, last['id'])
            objectives = document.get('objectives') or []
            brief = {'id': last['id'], 'state': last['state'], 'ended': last['ended'], 'started_at': last['started_at'],
                     'finished_at': last['finished_at'], 'counts': _counts(trials),
                     'best': _best(trials, objectives[0]) if objectives else None}
        out.append({'reference': reference, 'title': document.get('title'), 'recipe': document.get('recipe'),
                    'strategy': (document.get('strategy') or {}).get('kind'), 'objectives': document.get('objectives'),
                    'budget': document.get('budget'), 'state': state, 'run': brief})
    return {'sweeps': out}


# ================================================================ the map

def map_groups(definitions, models):
    """Groups of the map for the sweeps that have trials, each model's sweep set (section 6); returns the groups.

    definitions maps references to {kind, title, document}; models are the
    map's models (changed in place: sweep, and a trial's group).
    """
    groups, counts = [], {}
    for model in models:
        document = definitions[model['reference']]['document']
        block = document.get('sweep') if isinstance(document.get('sweep'), dict) else None
        sweep = block.get('definition') if block and isinstance(block.get('definition'), str) else None
        found = definitions.get(sweep) if sweep else None
        if found is None or found['kind'] != 'sweep':
            continue
        model['sweep'] = sweep
        model['group'] = sweep
        counts[sweep] = counts.get(sweep, 0) + 1
    for sweep in sorted(counts):
        document = definitions[sweep]['document']
        recipe = definitions.get(document.get('recipe'))
        parent = recipe['document'].get('group') if recipe is not None else None
        groups.append({'id': sweep, 'title': definitions[sweep]['title'],
                       'parent': parent if isinstance(parent, str) else None,
                       'description': f'The trials of {sweep}, a search over the settings of {document.get("recipe")}.',
                       'models': counts[sweep], 'sweep': True})
    return groups
