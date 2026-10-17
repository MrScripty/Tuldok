# Current project workspace

Open a project from **Open project**, select a configured root, and enter its
relative manifest path. Current manifests use project schema 2, including the
`extensions` list. The existing project snapshot catalog owns registration and
saved identity. A registered project can be opened directly at
`/workspaces?project=PROJECT_ID#data` (or `#pipeline` / `#runs`). The project ID is
32 lowercase hexadecimal characters; registration and access checks still apply.

Data lists the saved references and their current availability and hashes.
**Import fields** explicitly captures one scientific field bundle into the
ordinary catalog; the observed hash is checked again before import. Importing
does not alter the source project. The resulting field record opens in Data's
existing inspector, where review and release remain separate actions.

Runs lists external evidence. **Inspect external evidence** displays bounded
text and its measured identity. This inspection does not claim a completed
managed Run, scientific validation, or model acceptance. Pipeline's **Inspect
recipe** uses the current recipe inspection contract to distinguish an explicitly
bound model recipe from an ordinary recipe. Bound recipes open prospective Model
and finite Study preparation; ordinary recipes open saved graph creation,
including managed CPU restore and exact recorded Run-artifact input selection.
Project schema alone does not determine a recipe's kind. Unsupported variants
remain unavailable; an inspection rejection does not select another interface.
File presence does not qualify execution or grant approval.

The bound trial review accepts only current captured CPU and managed Torch
provider profiles that match the inspected recipe, with the exact recipe runtime
snapshot, any declared provider snapshot and sufficient declared limits. A
closed Study can prepare a trial and reach explicit review without approval or
admission. The approval control becomes available only after the current owner
acknowledges that exact review. No Run starts merely from inspection, preparation
or enabling approval. Activity polls preserve an outstanding inspection for the
same project/manifest/recipe hashes; navigation or changed recipe identity fences
its late response.

Unchanged immutable policy numbers retain their inspected JSON source spelling
at the authoring transport boundary, including `0.0`, exponent notation and
signed zero. UI calculations still use ordinary numbers; edited configuration
uses normal current validation. This requires native JSON source context and
raw-number support. A browser lacking them reports unsupported authoring rather
than changing scientific policy identity. Backend equality checks are unchanged.

An ordinary evidence reference whose ID is `activity` enables the live project
panel. Its publication format and validation belong to
[project inspection](projects.md). A visible active project refreshes its current
detail once per second after the previous request finishes. Hidden documents
pause requests. Each request has a ten-second deadline; failed requests show
unavailable progress until a successful observation. Invalid publisher content
does not retain a healthy progress display. A stale running producer is shown
as **Waiting for producer**.

The same refresh updates changed reference availability and selected evidence
text without taking keyboard focus. Missing or mismatched selected evidence
clears its former preview. Switching project or workspace, refreshing manually,
and leaving the page cancel the prior polling lifetime; late replies cannot
replace the current project. Progress remains an external observation, separate
from managed execution and verified artifact custody.

Browser qualification uses `tests/browser_workspace_project.cjs --lab-root PATH`
for exact copies of lab source/evidence, live updates, unavailable publications,
focus, project switching, held responses, deep links, and restart. The separate
`tests/browser_scientific_fields.cjs` current-project fixture checks explicit
import, field inspection, review, release, and independent cold custody. Both
launch the candidate on an ephemeral port with temporary data paths. The managed
review regression additionally uses the actual pressure source and measured
runtime in an isolated catalog with a copied manifest/recipe, exercises ordinary
CPU restore inspection and same-identity/changed-selection/changed-recipe held
responses across real activity polls, and stops with a closed Trial and enabled
approval, zero grants, zero admissions and zero Runs. Their
headless browser sandbox flags are verification settings; normal application
startup is unchanged. These checks establish browser/data behavior, and do not
establish pressure accuracy, training qualification, production cutover, or a
manual interaction on the user's desktop.
