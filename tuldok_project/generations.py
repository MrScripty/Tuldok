"""Data generations (docs/plans/training-and-curation/spec-generations.md): which source generation data comes from.

A dataset or step may declare `generation`; one that declares none takes the
generation of its data inputs (the entries of run.inputs naming a dataset or a
step). A recipe's generation is computed from its data inputs; a benchmark's
is declared or its cases' data. resolve() is pure: it takes {reference:
decoded document} (documents need not be valid) and returns every computed
generation and every problem, so the checker and the working copy's reads
share one rule. Inputs without a generation do not decide one, but a labelled
definition that takes one is warned; nothing without a labelled input gets a
generation.
"""
from dataclasses import dataclass, field

from . import documents, graph

MIXED = 'mixed'   # a recipe's or a benchmark's word for crossing generations on purpose; never a generation name
_DATA = ('datasets', 'steps')


@dataclass
class Resolved:
    """generation: {reference: name or None} for datasets, steps, recipes and benchmarks.

    problems: (reference, severity, pointer, message) tuples.
    """
    generation: dict = field(default_factory=dict)
    problems: list = field(default_factory=list)


def _directory(reference):
    parsed = documents.parse_reference(reference) if isinstance(reference, str) else None
    return parsed[0] if parsed else None


def _declared(document, key='generation'):
    value = document.get(key) if isinstance(document, dict) else None
    return value if isinstance(value, str) else None


def _data_inputs(document, definitions):
    """[(pointer, reference)] of the run's inputs that name a dataset or step present in definitions."""
    found = []
    for use in graph.uses(document):
        if use.role.startswith('input:') and _directory(use.target) in _DATA and use.target in definitions:
            found.append((use.pointer, use.target))
    return found


def _listed(pairs):
    return ', '.join(f'{reference} ({generation})' for reference, generation in pairs)


def resolve(definitions):
    """Every generation and every generation problem of a project (spec-generations.md sections 1 and 2)."""
    resolved = Resolved()
    data = {}
    walking = set()
    conflicted = set()   # datasets and steps without a generation because their inputs disagree (an error already)

    def unlabelled(reference, inputs):
        """A warning per data input of a labelled definition that has no generation of its own (section 1)."""
        seen = set()
        for pointer, target in inputs:
            if target in seen or data.get(target) is not None or target in conflicted:
                continue
            seen.add(target)
            resolved.problems.append((reference, 'warning', pointer,
                                      f'Takes unlabelled data {target}; label it with the generation it comes from.'))

    def of_data(reference):
        """The generation of a dataset or step (None: unlabelled, or its inputs disagree), walked once each."""
        if reference in data:
            return data[reference]
        if reference in walking:   # a cycle of inputs: the cycle rule reports it
            return None
        walking.add(reference)
        document = definitions[reference]
        inputs = _data_inputs(document, definitions)
        labelled = [(pointer, target, of_data(target)) for pointer, target in inputs]
        walking.discard(reference)
        labelled = [(pointer, target, value) for pointer, target, value in labelled if value is not None]
        declared = _declared(document)
        names = sorted({value for _, _, value in labelled})
        if declared is not None:
            wrong = [(target, value) for _, target, value in labelled if value != declared]
            if wrong and declared != MIXED:
                resolved.problems.append((reference, 'error', '/generation',
                                          f'This declares the data generation {declared!r} but its inputs come from '
                                          f'another: {_listed(wrong)}; make it from data of {declared!r} only, or '
                                          'change generation.'))
            value = declared if declared != MIXED else None
        elif len(names) > 1:
            resolved.problems.append((reference, 'error', labelled[0][0],
                                      f'Its inputs come from different data generations: '
                                      f'{_listed((t, v) for _, t, v in labelled)}; make it from one generation.'))
            value = None
            conflicted.add(reference)
        else:
            value = names[0] if names else None
        data[reference] = value
        if value is not None:
            unlabelled(reference, inputs)
        return value

    for reference in sorted(definitions):
        directory = _directory(reference)
        if directory in _DATA:
            resolved.generation[reference] = of_data(reference)

    for reference in sorted(definitions):
        document, directory = definitions[reference], _directory(reference)
        if directory != 'recipes' or not isinstance(document, dict):
            continue
        inputs = _data_inputs(document, definitions)
        labelled = [(pointer, target, data.get(target)) for pointer, target in inputs]
        labelled = [item for item in labelled if item[2] is not None]
        names = sorted({value for _, _, value in labelled})
        mixed = document.get('generations') == MIXED
        if len(names) > 1:
            listed = _listed((t, v) for _, t, v in labelled)
            if mixed:
                resolved.problems.append((reference, 'warning', '/generations',
                                          f'This recipe mixes data generations on purpose: {listed}.'))
            else:
                resolved.problems.append((reference, 'error', labelled[0][0],
                                          f'This recipe mixes data generations: {listed}; train on one generation, '
                                          'or declare "generations": "mixed" for a deliberate cross-generation '
                                          'experiment.'))
            resolved.generation[reference] = MIXED
        else:
            resolved.generation[reference] = names[0] if names else None
        if resolved.generation[reference] is not None:
            unlabelled(reference, inputs)

    for reference in sorted(definitions):
        document, directory = definitions[reference], _directory(reference)
        if directory != 'benchmarks' or not isinstance(document, dict):
            continue
        cases, seen, inputs = [], set(), []
        for use in graph.uses(document):
            if (use.role == 'cases' or use.role.startswith('input:')) and use.target in data:
                inputs.append((use.pointer, use.target))
                if data[use.target] is not None and use.target not in seen:
                    seen.add(use.target)
                    cases.append((use.pointer, use.target, data[use.target]))
        declared = _declared(document)
        names = sorted({value for _, _, value in cases})
        if declared is not None:
            wrong = [(target, value) for _, target, value in cases if value != declared]
            if wrong:
                resolved.problems.append((reference, 'error', '/generation',
                                          f'This benchmark declares its cases of the data generation {declared!r} '
                                          f'but its data comes from another: {_listed(wrong)}; fix generation or '
                                          'the cases.'))
            value = declared
        elif len(names) > 1:
            resolved.problems.append((reference, 'error', cases[0][0],
                                      f'Its cases come from different data generations: '
                                      f'{_listed((t, v) for _, t, v in cases)}; measure on one generation.'))
            value = None
        else:
            value = names[0] if names else None
        resolved.generation[reference] = value
        if value is not None:
            unlabelled(reference, inputs)
        subjects = document.get('subjects') if isinstance(document.get('subjects'), list) else []
        spanned = {}
        for subject in subjects:
            recipe = subject.get('recipe') if isinstance(subject, dict) else None
            generation = resolved.generation.get(recipe) if isinstance(recipe, str) else None
            if generation is not None:
                spanned.setdefault(generation, []).append(subject.get('name') or recipe)
        if len(spanned) > 1 and document.get('generations') != MIXED:
            listed = '; '.join(f'{name}: {", ".join(str(s) for s in names)}' for name, names in sorted(spanned.items()))
            resolved.problems.append((reference, 'warning', '/subjects',
                                      f'The subjects come from different data generations ({listed}); measure one '
                                      'generation, or declare "generations": "mixed" if comparing across them is '
                                      'meant.'))
    return resolved


def check_generations(definitions, add):
    """Report the generation rules for {reference: folder.Definition} (called by check.check_map)."""
    decoded = {reference: d.document for reference, d in definitions.items() if isinstance(d.document, dict)}
    for reference, severity, pointer, message in resolve(decoded).problems:
        add(severity, definitions[reference].path, pointer, message)


def labelled(documents_by_reference):
    """{reference: generation} of the datasets, steps, recipes and benchmarks that have one."""
    return {reference: value for reference, value in resolve(documents_by_reference).generation.items()
            if value is not None}
