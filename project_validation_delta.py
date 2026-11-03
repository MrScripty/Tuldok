"""Edit-scoped validation: re-check only what a mutation can affect.

A mutation's candidate is the previous, completely validated checkpoint plus
changed/added records (no deletions) and its new operation receipt. Each
validation component of validate_project_records is a pure function of the
documents and identities of a known set of record families (see the audit in
docs/plans/database-working-store.md, stage 4). A component whose input
families contain no changed record has the same outcome as for the previous
checkpoint, so it is skipped. Old operation receipts are re-checked only when
records they bind to changed or a new receipt shares their key space.

Anything not classified here is always validated. TULDOK_VALIDATION_CROSSCHECK=1
additionally runs complete validation and requires the same outcome.
"""
import contextvars
from contextlib import contextmanager
from dataclasses import dataclass

from project_data import FAMILIES as _DATA
from project_history import FAMILY_FORMATS as _HISTORY
from project_material import FAMILIES as _MATERIAL
from project_producers import FAMILIES as _PRODUCERS

DATA = frozenset(_DATA)
HISTORY = frozenset(_HISTORY)
MATERIAL = frozenset(_MATERIAL)
PRODUCERS = frozenset(_PRODUCERS)

# Families whose documents or identities each component reads.
COMPONENTS = {
    'data': DATA | {'workbench_text', 'project_artifact', 'project_fork'} | PRODUCERS,
    'fork': frozenset({'project_fork'}),
    'composition': frozenset({'project_composition', 'project_fork', 'run_observation'}),
    'extraction': frozenset({'project_extraction', 'project_fork', 'project_snapshot', 'project_file', 'project_artifact'}),
    'files': frozenset({'project_file', 'project_fork'}),
    'native': frozenset({'native_execution_history', 'project_artifact', 'run_history'}),
    'material': MATERIAL | {'project_fork', 'project_artifact'},
    'producers': PRODUCERS | {'project_artifact', 'workbench_record', 'workbench_text'},
    'history': HISTORY | MATERIAL | {'project_artifact', 'dataset_exposure', 'pipeline_graph'},
    'measurements': frozenset({'measurement_source', 'project_artifact', 'project_snapshot'}),
    'sources': frozenset({'project_snapshot'}),
}

# Operation-receipt prefixes -> families their result binds to. A prefix
# mapped to an empty set binds only immutable or append-only facts.
RECEIPT_BINDINGS = {
    'data.': DATA | {'workbench_text'},
    'models.': frozenset(), 'graphs.': frozenset(), 'recipes.': frozenset(),
    'studies.': HISTORY | {'pipeline_graph', 'project_artifact'},
    'history.disclose': HISTORY | {'pipeline_graph', 'project_artifact'},
    'source.': frozenset(),
    'measurements.': frozenset({'measurement_source'}),
    'runs.': frozenset({'run_history'}),
    'producers.': frozenset(),
    'files.': frozenset(),
    'study_execution.': HISTORY | MATERIAL,
    'runtime.': frozenset({'runtime_material', 'project_artifact'}),
    'native_preparation.': MATERIAL | {'pipeline_graph', 'dataset_release'},
    'artifacts.resolve': frozenset(),
}
# A new receipt in these key spaces can change the meaning of older ones.
SHARED_KEY_SPACES = ('study_execution.', 'runtime.')
# Receipts these prefixes claim are also validated inside history decoding.
HISTORY_RECEIPTS = ('studies.', 'history.disclose')


def _prefix(operation):
    return next((prefix for prefix in RECEIPT_BINDINGS if operation.startswith(prefix)), None)


@dataclass(frozen=True)
class ValidationDelta:
    """Identities a mutation changed relative to its validated base checkpoint."""
    changed: frozenset
    operations: frozenset = frozenset()   # operation names of new/changed receipts
    added: frozenset = frozenset()        # changed identities absent from the base

    @property
    def families(self):
        # A newly added artifact declaration cannot change any component: an
        # unchanged record referencing an undeclared blob already failed base
        # validation. New declarations are still checked by the claim loop.
        return frozenset(family for family, identity in self.changed
                         if not (family == 'project_artifact' and (family, identity) in self.added))

    def touches(self, component):
        return bool(self.families & COMPONENTS[component])

    def history_receipt_added(self):
        return any(operation.startswith(HISTORY_RECEIPTS) for operation in self.operations)

    def receipt_needed(self, operation, identity):
        if identity in self.changed:
            return True
        prefix = _prefix(operation)
        if prefix is None:
            return True
        if self.families & RECEIPT_BINDINGS[prefix]:
            return True
        if prefix in SHARED_KEY_SPACES and any(op.startswith(prefix) for op in self.operations):
            return True
        return False


_DELTA = contextvars.ContextVar('validation_delta', default=None)


@contextmanager
def edit_delta(delta):
    """Validate the enclosed candidate relative to its validated base checkpoint."""
    token = _DELTA.set(delta)
    try:
        yield
    finally:
        _DELTA.reset(token)


def current_delta():
    return _DELTA.get()
