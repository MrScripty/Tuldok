"""The uses-graph of a project: which definition uses which, and in what order to build them.

Owns the edge table of section 2.9 of docs/plans/definition-first-projects/spec-m1-m2.md.
Every function is pure and takes `definitions`, a mapping of reference (such as
'datasets/x') to decoded document. Documents need not be valid: fields of the
wrong type are skipped, so the graph can be read even from a folder with problems.
Edges whose target is not in `definitions` are kept by edges() and uses() but
ignored by order() and cycles().
"""
from dataclasses import dataclass
import heapq

from . import documents


@dataclass(frozen=True, order=True)
class Edge:
    """from_ref uses to_ref in the given role (for example 'input:training')."""
    from_ref: str
    to_ref: str
    role: str


@dataclass(frozen=True)
class Use:
    """One reference field of a document: its role, its JSON pointer, the target, and the named output if any."""
    role: str
    pointer: str
    target: str
    output: str | None = None

    @property
    def accepts(self):
        """The directories this field accepts (documents.ACCEPTS)."""
        return documents.ACCEPTS[self.role.split(':', 1)[0]]


def uses(document):
    """Return every reference a document makes, in document order (the rows of the 2.9 table)."""
    if not isinstance(document, dict):
        return []
    found = []
    run = document.get('run')
    if isinstance(run, dict):
        inputs = run.get('inputs')
        if isinstance(inputs, dict):
            for name, value in inputs.items():
                if isinstance(value, str):
                    found.append(Use(f'input:{name}', documents.pointer('run', 'inputs', name), value))
                elif isinstance(value, dict) and isinstance(value.get('from'), str):
                    output = value.get('output') if isinstance(value.get('output'), str) else None
                    found.append(Use(f'input:{name}', documents.pointer('run', 'inputs', name, 'from'), value['from'], output))
        if isinstance(run.get('environment'), str):
            found.append(Use('environment', '/run/environment', run['environment']))
    kind = document.get('kind')
    if kind == 'recipe' and isinstance(document.get('model'), str):
        found.append(Use('model', '/model', document['model']))
    if kind == 'benchmark':
        subjects = document.get('subjects')
        if isinstance(subjects, list):
            for index, subject in enumerate(subjects):
                if isinstance(subject, dict) and isinstance(subject.get('recipe'), str) and isinstance(subject.get('name'), str):
                    found.append(Use(f'subject:{subject["name"]}', documents.pointer('subjects', index, 'recipe'), subject['recipe']))
        cases = document.get('cases')
        if isinstance(cases, dict) and isinstance(cases.get('dataset'), str):
            found.append(Use('cases', '/cases/dataset', cases['dataset']))
    if kind == 'chart' and isinstance(document.get('benchmark'), str):
        found.append(Use('benchmark', '/benchmark', document['benchmark']))
    return found


def is_wellformed(use):
    """True when the target is a reference into a directory this field accepts."""
    parsed = documents.parse_reference(use.target)
    return parsed is not None and parsed[0] in use.accepts


def edges(definitions):
    """Return the sorted, distinct edges whose target is a reference into a directory the field accepts."""
    found = set()
    for source, document in definitions.items():
        for use in uses(document):
            if is_wellformed(use):
                found.add(Edge(source, use.target, use.role))
    return sorted(found)


def _adjacency(definitions):
    """Return {reference: sorted targets} restricted to references present in definitions."""
    adjacency = {reference: set() for reference in definitions}
    for edge in edges(definitions):
        if edge.to_ref in adjacency:
            adjacency[edge.from_ref].add(edge.to_ref)
    return {reference: sorted(targets) for reference, targets in adjacency.items()}


def cycles(definitions):
    """Return each group of definitions that use each other in a cycle, as sorted tuples, sorted.

    A group is a strongly connected component with more than one member, or one
    definition that uses itself.
    """
    adjacency = _adjacency(definitions)
    index_of, low, on_stack, stack, groups = {}, {}, set(), [], []
    counter = 0
    for start in sorted(adjacency):
        if start in index_of:
            continue
        # Iterative Tarjan: each frame is (node, iterator over its targets).
        index_of[start] = low[start] = counter
        counter += 1
        stack.append(start)
        on_stack.add(start)
        frames = [(start, iter(adjacency[start]))]
        while frames:
            node, targets = frames[-1]
            advanced = False
            for target in targets:
                if target not in index_of:
                    index_of[target] = low[target] = counter
                    counter += 1
                    stack.append(target)
                    on_stack.add(target)
                    frames.append((target, iter(adjacency[target])))
                    advanced = True
                    break
                if target in on_stack:
                    low[node] = min(low[node], index_of[target])
            if advanced:
                continue
            frames.pop()
            if frames:
                parent = frames[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index_of[node]:
                group = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    group.append(member)
                    if member == node:
                        break
                if len(group) > 1 or node in adjacency[node]:
                    groups.append(tuple(sorted(group)))
    return sorted(groups)


def order(definitions):
    """Return every reference with each one after everything it uses; ties broken by reference string.

    Raises ValueError when the graph has a cycle, since no such order exists.
    """
    adjacency = _adjacency(definitions)
    waiting = {reference: len(targets) for reference, targets in adjacency.items()}
    users = {reference: [] for reference in adjacency}
    for reference, targets in adjacency.items():
        for target in targets:
            users[target].append(reference)
    ready = [reference for reference, count in waiting.items() if count == 0]
    heapq.heapify(ready)
    result = []
    while ready:
        reference = heapq.heappop(ready)
        result.append(reference)
        for user in users[reference]:
            waiting[user] -= 1
            if waiting[user] == 0:
                heapq.heappush(ready, user)
    if len(result) != len(adjacency):
        raise ValueError('The definitions use each other in a cycle: '
                         + '; '.join(', '.join(group) for group in cycles(definitions)) + '.')
    return result


def users_of(definitions, reference):
    """Return the sorted edges whose target is reference: what uses it, and how."""
    return [edge for edge in edges(definitions) if edge.to_ref == reference]


# ------------------------------------------------------------ states (4.3)

# The two states that travel upward through input edges, worst last.
_CARRIED = (None, 'needs-work', 'cannot-rebuild')
_OWN_STATE = {'needs-work': 1, 'no': 2}  # earlier_work.rebuild -> index into _CARRIED
_BASE_STATE = {'dataset': 'not-built', 'recipe': 'not-built', 'benchmark': 'not-built',
               'step': 'not-built', 'environment': 'not-set-up', 'model': 'none', 'chart': 'none'}
_BUILT = ('dataset', 'recipe', 'step', 'benchmark')
_ENVIRONMENT_STATES = ('ready', 'failing', 'not-set-up')
_BUILD_STATES = ('running', 'built', 'out-of-date', 'failed')


def _kind(reference, document):
    parsed = documents.parse_reference(reference)
    if parsed is not None:
        return documents.KINDS[parsed[0]]
    return document.get('kind') if isinstance(document, dict) else None


def states(definitions, local=None):
    """Return {reference: state} for every definition, by section 4.3 of the spec.

    local, when given, maps references to the state this machine records for
    them, and is applied last. For an environment it is ready, failing or
    not-set-up (spec-m5.md section 2) and replaces the computed state. For a
    dataset, recipe, step or benchmark it is a build state (spec-m6.md
    section 5): running, built or out-of-date replace whatever was computed;
    failed replaces not-built only, since cannot-rebuild and needs-work take
    precedence when there is no current product. A local state that is not a
    state of that kind is ignored, and local states are never carried upward.

    cannot-rebuild and needs-work come from a definition's own
    earlier_work.rebuild or from anything it uses through input edges, directly
    or further up; the worse of the two wins. A definition that local says is
    built carries nothing to what uses it, and nothing through it: its product
    is on this machine to be used, whether it was built here or adopted
    (spec-m8.md section 3). Other edges (environment, model, subjects, cases,
    chart) carry nothing. Otherwise the state follows the
    kind. The table is read in order, so a model marked rebuild "no" is
    cannot-rebuild, not none. Cycles are tolerated: the result is the fixed point.
    """
    severity = {}
    for reference, document in definitions.items():
        earlier = document.get('earlier_work') if isinstance(document, dict) else None
        rebuild = earlier.get('rebuild') if isinstance(earlier, dict) else None
        severity[reference] = _OWN_STATE.get(rebuild, 0)
    users = {reference: [] for reference in definitions}
    for edge in edges(definitions):
        if edge.role.startswith('input:') and edge.to_ref in users:
            users[edge.to_ref].append(edge.from_ref)
    built_here = {reference for reference, state in (local or {}).items()
                  if state == 'built' and reference in definitions
                  and _kind(reference, definitions[reference]) in _BUILT}
    # Severity only rises, at most twice per definition, so this ends even on a cycle.
    pending = [reference for reference, value in severity.items() if value and reference not in built_here]
    while pending:
        reference = pending.pop()
        for user in users[reference]:
            if user not in built_here and severity[user] < severity[reference]:
                severity[user] = severity[reference]
                pending.append(user)
    found = {reference: _CARRIED[severity[reference]] or _BASE_STATE.get(_kind(reference, document), 'none')
             for reference, document in definitions.items()}
    for reference, state in (local or {}).items():
        if reference not in found:
            continue
        kind = _kind(reference, definitions[reference])
        if kind == 'environment' and state in _ENVIRONMENT_STATES:
            found[reference] = state
        elif kind in _BUILT and state in _BUILD_STATES:
            if state == 'failed' and found[reference] in _CARRIED[1:]:
                continue
            found[reference] = state
    return found
