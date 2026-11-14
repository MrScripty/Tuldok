"""The rebuild plan: what has to be built, in what order, to have some definitions, and what stands in the way.

Owns docs/plans/definition-first-projects/spec-m4.md. make_plan is a pure
function of the decoded definitions (reference -> document): it follows the
input, environment and subject edges from the targets (a freeze's tasks only
to note one that is missing or on another dataset), but never out of a
blocked step or into a blocked subject recipe, puts what it reaches in
graph.order, gives each step an action from graph.states (with the
environments' states recorded on this machine, spec-m5.md section 5: a ready
environment is not something to set up), explains each blocked
step by its root causes, found over the whole graph (definitions whose own earlier_work.rebuild is no or
needs-work), and adds up the figures the build steps declare in
run.resources. build_plan reads the definitions from a Project's database copy
and the recorded environment states and calls it. Making a plan runs nothing and opens no file: no command, no
estimate command, nothing on disk. A step's estimate is what the estimate
command printed when `estimate` last ran it (spec-m6.md section 7), read from
the database and given only while the definition's text is the one it was
measured for; otherwise null. The totals add up those estimates beside the
declared figures, never mixing the two.
With what was built on this machine (spec-m6.md section 5), a step that is
built has the action built and is not work; one that is out-of-date or failed
is built again, and its reasons say why. build_plan reads those states from
builds.status, which looks at the code root's Git history only when some
product exists. A generate step (spec-d5.md section 3) to be built on a
machine with no Pumas endpoint set is blocked, says so, and keeps the plan
from being buildable, as an environment that is not ready keeps it from
running; the settings file is read for that only when such a step is to be
built.
"""
from collections import deque
import math

from . import documents, graph
from . import local as machine   # make_plan's argument local is the recorded states
from .store import ProjectError

BUILT_KINDS = ('dataset', 'recipe', 'step', 'benchmark')
ACTIONS = ('build', 'set-up', 'blocked', 'ready', 'built')
RESOURCES = ('gpu', 'cpu_threads', 'memory_gb', 'wall_hours', 'disk_gb')
CAUSE_LIMIT = 5
NO_ENDPOINT = ('No Pumas endpoint is set on this machine, so this dataset cannot be generated here; the owner sets '
               'one, then it can be built.')
_CAUSE_LABELS = ('no', 'needs-work')


def _kind(reference):
    return documents.KINDS[documents.parse_reference(reference)[0]]


def _run(document):
    run = document.get('run')
    return run if isinstance(run, dict) else {}


def _own_label(document):
    earlier = document.get('earlier_work')
    return earlier if isinstance(earlier, dict) and earlier.get('rebuild') in _CAUSE_LABELS else None


def every_target(definitions):
    """Every dataset, recipe, step and benchmark, sorted by reference."""
    return sorted(reference for reference in definitions if _kind(reference) in BUILT_KINDS)


def _input_targets(edges_from, reference):
    return sorted({edge.to_ref for edge in edges_from.get(reference, ()) if edge.role.startswith('input:')})


def _held(state):
    """True for a state that blocks a definition by itself (graph.states carries it up through inputs)."""
    return state in ('cannot-rebuild', 'needs-work')


def _closure(definitions, edges_from, states, starts, adopted=frozenset()):
    """Every definition reached from starts, starts included (section 2 of spec-m4.md).

    Input and environment edges are followed; a subject edge only when its
    recipe is not blocked. Nothing is followed out of a blocked definition, out
    of a benchmark with no subject to run, nor out of a definition whose
    current product was adopted (it needs nothing it uses: spec-m8.md section 3).
    """
    seen, pending = set(), list(starts)
    while pending:
        reference = pending.pop()
        if reference in seen or reference not in definitions:
            continue
        seen.add(reference)
        if _held(states[reference]) or (reference in adopted and states[reference] == 'built'):
            continue
        if _kind(reference) == 'benchmark' and not _subjects(definitions[reference], states)['run']:
            continue
        for edge in edges_from.get(reference, ()):
            if edge.role == 'environment' or edge.role.startswith('input:'):
                pending.append(edge.to_ref)
            elif edge.role.startswith('subject:') and not _held(states.get(edge.to_ref)):
                pending.append(edge.to_ref)
    return seen


def causes(definitions, edges_from, reference):
    """The root causes of a blocked definition, nearest first (fewest input edges away, then by reference).

    A cause is the definition itself, or anything it reaches through input
    edges, whose own earlier_work.rebuild is no or needs-work. Each is
    {reference, rebuild, reason}.
    """
    distance = {reference: 0}
    queue = deque([reference])
    while queue:
        current = queue.popleft()
        for target in _input_targets(edges_from, current):
            if target in definitions and target not in distance:
                distance[target] = distance[current] + 1
                queue.append(target)
    found = []
    for item in sorted(distance, key=lambda name: (distance[name], name)):
        label = _own_label(definitions[item])
        if label is not None:
            found.append({'reference': item, 'rebuild': label['rebuild'], 'reason': label.get('reason')})
    return found


def _inputs(document):
    """{name: {reference, output}} for the run's inputs, in document order."""
    inputs = _run(document).get('inputs')
    if not isinstance(inputs, dict):
        return {}
    found = {}
    for name, value in inputs.items():
        if isinstance(value, str):
            found[name] = {'reference': value, 'output': None}
        elif isinstance(value, dict):
            found[name] = {'reference': value.get('from'), 'output': value.get('output')}
    return found


def _tasks(run):
    """The tasks a freeze step reads (run.annotations), in order; empty for any other run."""
    tasks = run.get('annotations') if run.get('step') == 'freeze' else None
    return [task for task in (tasks if isinstance(tasks, list) else ()) if isinstance(task, str)]


def _task_notes(definitions, reference, document):
    """Notes on a freeze's tasks that do not exist or are on another dataset than its input (spec-d4.md section 6).

    The plan follows a step's annotations edges only this far: a task is
    never a step. Such a freeze fails before it runs.
    """
    used = _inputs(document).get('records', {}).get('reference')
    notes = []
    for task in _tasks(_run(document)):
        target = definitions.get(task)
        if target is None:
            notes.append(f'{reference} freezes by {task}, which does not exist; it fails when built.')
        elif target.get('dataset') != used:
            notes.append(f'{reference} freezes by {task}, which annotates {target.get("dataset")}, not its input '
                         f'{used}; it fails when built.')
    return notes


def _resources(document):
    declared = _run(document).get('resources')
    declared = declared if isinstance(declared, dict) else {}
    return {name: declared.get(name) for name in RESOURCES}


def _subjects(document, states):
    """{run, skipped} for a benchmark: a subject is skipped when its recipe is blocked."""
    run, skipped = [], []
    subjects = document.get('subjects')
    for subject in subjects if isinstance(subjects, list) else ():
        if not isinstance(subject, dict) or not isinstance(subject.get('name'), str):
            continue
        recipe = subject.get('recipe')
        if isinstance(recipe, str) and _held(states.get(recipe)):
            skipped.append({'name': subject['name'], 'recipe': recipe,
                            'reason': f'its recipe {recipe} is blocked'})
        else:
            run.append(subject['name'])
    return {'run': run, 'skipped': skipped}


def _action(kind, state):
    if kind == 'environment':
        return 'ready' if state == 'ready' else 'set-up'  # not-set-up, or failing its last check
    if state in ('not-built', 'out-of-date', 'failed', 'running'):
        return 'build'  # a running step is refused by builds.execute, never started twice
    if state == 'built':
        return 'built'
    if state in ('cannot-rebuild', 'needs-work'):
        return 'blocked'
    return None


def _total(steps, field):
    """(sum of the declared figure over build steps, how many build steps declare none)."""
    declared = [step['resources'][field] for step in steps if step['action'] == 'build']
    numbers = [value for value in declared if isinstance(value, (int, float)) and not isinstance(value, bool)]
    return round(math.fsum(numbers), 6), len(declared) - len(numbers)


def _estimated(steps, field, scale):
    """(sum of the estimated field over build steps that have one, divided by scale; how many have one)."""
    values = [step['estimate'][field] for step in steps
              if step['action'] == 'build' and step['estimate'] and step['estimate'].get(field) is not None]
    return math.fsum(values) / scale, len(values)


def make_plan(definitions, targets, *, every=False, local=None, built=None, estimates=None, endpoint=False):
    """The plan for targets over {reference: document}, as section 3 and 4 of spec-m4.md describe it.

    local is graph.states' mapping of references to the state recorded on
    this machine; without it every environment is not-set-up and nothing is
    built. built is builds.status' mapping of reference to {causes, scratch};
    each step's reasons are its causes (why it is out of date, failed or
    running) and scratch says whether its current product is a scratch one.
    estimates is builds.stored_estimates' mapping of reference to the
    current estimate ({disk_bytes, wall_seconds, items, measured_at}).
    endpoint says whether this machine has a Pumas endpoint set, or is a
    function answering that, asked only when a generate step would be built
    (so that a plan with none reads no settings file); without one such a
    step is blocked by itself (rebuild 'endpoint').

    every adds every dataset, recipe, step and benchmark to the targets. A
    chart target is replaced by its benchmark, an annotation task by its
    dataset (spec-d4.md section 1); a model target adds nothing
    and a note saying so. Raises ValueError naming any target that is not a
    definition.
    """
    asked = list(targets) + (every_target(definitions) if every else [])
    unknown = [reference for reference in asked if reference not in definitions]
    if unknown:
        raise ValueError('There is no definition ' + ', '.join(unknown) + '.')
    edges_from = {}
    for edge in graph.edges(definitions):
        edges_from.setdefault(edge.from_ref, []).append(edge)
    resolved, notes = [], []
    for reference in asked:
        kind = _kind(reference)
        if kind == 'chart':
            benchmark = definitions[reference].get('benchmark')
            notes.append(f'{reference} is drawn from {benchmark}, which is planned in its place.')
            reference = benchmark
        elif kind == 'annotation':
            dataset = definitions[reference].get('dataset')
            notes.append(f'{reference} annotates the records of {dataset}, which is planned in its place.')
            reference = dataset
        elif kind == 'model':
            notes.append(f'{reference} is a model; a model is not built, only the recipes that train it.')
        if reference not in resolved:
            resolved.append(reference)
    states = graph.states(definitions, local)
    adopted = {reference for reference, entry in (built or {}).items() if entry.get('adopted')}
    members = _closure(definitions, edges_from, states,
                       [reference for reference in resolved if _kind(reference) != 'model'], adopted)
    members = {reference for reference in members if _kind(reference) not in ('model', 'chart', 'annotation')}
    ordered = graph.order({reference: definitions[reference] for reference in members})
    actions = {reference: _action(_kind(reference), states[reference]) for reference in ordered}

    asked = {}

    def has_endpoint():
        if 'set' not in asked:
            asked['set'] = bool(endpoint() if callable(endpoint) else endpoint)
        return asked['set']

    steps = []
    for number, reference in enumerate(ordered, 1):
        document, kind = definitions[reference], _kind(reference)
        run = _run(document)
        action = actions[reference]
        provided = run.get('step') if isinstance(run.get('step'), str) else None
        step = {'number': number, 'reference': reference, 'kind': kind, 'title': document.get('title'),
                'state': states[reference], 'action': action,
                'command': ['tuldok', provided] if provided else run.get('command'),
                'environment': None if provided else run.get('environment'),
                'step': provided, 'annotations': _tasks(run),
                'inputs': _inputs(document), 'resources': _resources(document),
                'estimate': (estimates or {}).get(reference),
                'blocked_by': [], 'blocked_by_more': 0,
                'reasons': list((built or {}).get(reference, {}).get('causes', [])),
                'scratch': bool((built or {}).get(reference, {}).get('scratch', False)),
                'adopted': reference in adopted}
        if kind == 'benchmark':
            step['subjects'] = _subjects(document, states)
            if action == 'build' and not step['subjects']['run']:
                # Nothing would run: blocked, though by no cause of its own.
                step['action'] = action = actions[reference] = 'blocked'
        if provided == 'freeze':
            notes.extend(_task_notes(definitions, reference, document))
        if provided == 'generate' and action == 'build' and not has_endpoint():
            step['action'] = action = actions[reference] = 'blocked'
            step['blocked_by'] = [{'reference': reference, 'rebuild': 'endpoint', 'reason': NO_ENDPOINT}]
            notes.append(f'{reference} is generated through a Pumas endpoint, and none is set on this machine.')
            steps.append(step)
            continue
        if action == 'blocked':
            found = causes(definitions, edges_from, reference)
            step['blocked_by'] = found[:CAUSE_LIMIT]
            step['blocked_by_more'] = max(0, len(found) - CAUSE_LIMIT)
        steps.append(step)

    blocked = {step['reference'] for step in steps if step['action'] == 'blocked'}
    # A generate held by the missing endpoint stops the build wherever it stands, as a target or not.
    held = [step['reference'] for step in steps if step['reference'] not in resolved
            and any(cause['rebuild'] == 'endpoint' for cause in step['blocked_by'])]
    disk_gb, disk_unknown = _total(steps, 'disk_gb')
    wall_hours, wall_unknown = _total(steps, 'wall_hours')
    estimated_disk_gb, estimated_disk_steps = _estimated(steps, 'disk_bytes', 1000 ** 3)
    estimated_wall_hours, estimated_wall_steps = _estimated(steps, 'wall_seconds', 3600)
    return {'targets': resolved, 'every': every,
            'buildable': not any(reference in blocked for reference in resolved) and not held,
            'blocked_targets': [reference for reference in resolved if reference in blocked] + held,
            'counts': {action: sum(step['action'] == action for step in steps) for action in ACTIONS},
            'gpu_steps': sum(step['action'] == 'build' and step['resources']['gpu'] is True for step in steps),
            'disk_gb': disk_gb, 'disk_unknown': disk_unknown,
            'wall_hours': wall_hours, 'wall_unknown': wall_unknown,
            'estimated_disk_gb': estimated_disk_gb, 'estimated_disk_steps': estimated_disk_steps,
            'estimated_wall_hours': estimated_wall_hours, 'estimated_wall_steps': estimated_wall_steps,
            'notes': notes, 'steps': steps}


def build_plan(project, targets, *, every=False):
    """The plan for targets in an open Project, from its database copy alone.

    Raises ProjectError (code not-found) naming the first target that is not a
    definition of the project. Holds no state; runs nothing and opens no file
    unless something was built (then Git is asked what changed, section 5).
    """
    from . import builds, environments
    definitions = project._documents(removed=False)
    for reference in targets:
        if documents.parse_reference(reference) is None:
            raise ProjectError(f'{reference!r} is not a reference such as datasets/<name>.', 'not-found',
                               references=[reference])
        if reference not in definitions:
            raise ProjectError(f'There is no definition {reference}.', 'not-found', references=[reference])
    built = builds.status(project)
    local = {**environments.recorded_states(project._connection, project.schema),
             **{reference: entry['state'] for reference, entry in built.items()}}
    return make_plan(definitions, targets, every=every, local=local, built=built,
                     estimates=builds.stored_estimates(project), endpoint=lambda: machine.pumas_endpoint() is not None)
