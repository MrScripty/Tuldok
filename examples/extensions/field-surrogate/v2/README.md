# Scalar A, explicit evidence source v2

This private authored example fits an affine mapping from an initial dimensionless
4×4×4 scalar field to its explicit target. It uses two training members and one
fixed validation member. It makes no physics or generalization claim.

The new fixture declares zero XYZ origin, identity orientation, metre coordinates,
unit spacing, float64 cell placement and an identity gauge explicitly. These are
new author declarations captured before execution. The original v1 preparation
fixture, source, frozen oracle and Run receipts retain their original meaning.

`extension.json` and `task.json` are inert E1 declarations. `recipe.json` explicitly
selects `external_model_evidence_recipe_v1` schema2; ordinary external_recipe_v1
cannot receive model context or admit this source through its old grant path.
`project.json` is the ordinary project registration for that explicit recipe.
The extension manifest, task, notices and Python source all belong to its captured
source closure. No package code executes during inspection or publication.

The model definition contains architecture and field names only. Learning rate
and the fixed64-update training schedule are recipe controls. The worker computes
train-only population statistics and performs actual full-batch gradient updates.
It retains state and fixed-probe fields at16,32,48,64 to satisfy the declared
interval16 profile. All27 output files fit the ordinary32-file profile; there is
no profile promotion. Last-checkpoint selection is diagnostic, not quality acceptance.

Runs supplies the exact bounded context after assigning an ordinary admitted
attempt under the full composed owner grant. The source copies those exact context
bytes into a declared output and writes D2 checkpoint/probe/field/metric documents.
The host verifies structural and identity closure; it never imports this worker,
loads weights or implements its numerical method. `cold_oracle.py` independently
checks the retained NumPy state, closed-form gradient trajectory and every probe
using only the standard library. Freeze its SHA before the first real v2 Run.

The host context/decoder and Pipeline/Runs integration are in development on a
separate feature branch. A real Run, cold queries, public projections and E2
acceptance must be qualified before advertising this capability. Static validation
and structural fixture tests do not establish them. No public release or complete
inference-package/redistribution claim is made here.
