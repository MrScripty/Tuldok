# P4 admission — bounded native generation

PR48 at `7d590605006f48f6c3f710b91a75ad4455d0a9d7` passed hosted UI
38440828965 and all 132 lifecycle steps in 38440828870. Fresh main remains
`c522bf6`. P4 uses `feature/native-scientific-generation-20261013`; no merge or
deployment is authorized. Apply the adopted architecture, Python/JavaScript,
untrusted-execution, persistence, dependency and verification standards.
Independent design review found this bounded scope viable at existing limits.

## Goal and measured bounds

Run optional native Rheon generation through the existing approved-recipe owner,
then import a verified artifact into Data for inspection, review, freeze and cold
read. Preserve Python-only recipes and historical scientific source identities.

The pinned native binary is 766,832 bytes; the existing 32³/two-frame wire is
2,122,648 bytes. Its lossless generic bundle, including all twelve NPY arrays and
original evidence, fits the existing 40 MiB bundle and 64 MiB Run limits. Initial
recipe limits are 16 MiB outputs and 120 seconds. No global bounds increase.

Source pins are Rheon `2209012bc5f902693d0f695ec1c2d854126af317` and lab
`e8a90bfef6b2955c502008ccc62443e29dd9f2ec`. Native binary SHA256 is
`4e4e49f0e3febf5b11556c2a1daac3dc684e9fb9a9c3c742329d804a4913ceff`.
P3b READY/STOP custody evidence alone does not qualify generation.

## Optional adapter

`adapters/rheon/generate.py` is a self-contained standard-library wrapper. Its
arguments are `--native`, `--build-receipt`, `--native-policy`, `--grid`,
`--frames`, `--seed` and `--output`. It owns native protocol parsing, bounded
controls, producer conversion and diagnostics; core owners have no new Rheon
branches. Initial controls are grid 8–32, frames 1–2 and a bounded integer seed,
with Jacobi fixed. Time step 1/60 and density 1.25 remain fixed. Native units are
explicitly unspecified. Preserve all six fields, exact float32/float64 payloads,
C-order ZYX/MAC placement, time and stage.

Family identity binds the declared initial-condition convention, grid and seed;
requested frame count and build changes alone do not establish independent
trajectories. Binary/build hashes remain provenance. The exact original build
receipt is a genuine declared input; do not invent a dataset input for native
internal initial conditions. Outputs are `fields.zip`, `wire.bin`, a producer
receipt and bounded diagnostics. Role `scientific_fields` enables a generic UI
action but is not evidence that bytes are valid.

`adapters/rheon/project.py --binary PATH --build-receipt PATH --destination PATH`
creates a new directory only. It copies exact input bytes and writes the generic
project/recipe manifests without building, executing or modifying source repos.

## Generic native closure

Optional `native_sources` declares 1–8 unique paths already present in `sources`.
An argument `{native_policy: source_path}` refers to generated captured policy
JSON under `native-policy/<source-path-SHA256>.json`. Material adds
`native_policies` keyed by source path only when native sources are declared.
Omitted-native definitions/material/specs gain no default fields.

Apply a strict bounded ELF64 little-endian x86-64 policy recursively to the
executable, loader and every added DSO. Require the qualified PIE/interpreter
combination; reject malformed headers/string tables, path/token dependencies,
RPATH/RUNPATH, AUDIT/DEPAUDIT, FILTER and AUXILIARY mechanisms. Resolve the finite
closure only under trusted `/usr/lib/x86_64-linux-gnu`. Retain every dependency's
size/hash under existing runtime limits and ownership checks.

Captured policy fields are `schema_version`, `policy`, `source {path, sha256}`,
`loader {path, bytes, sha256}`, `library_directory`, `loader_arguments`,
`runtime_files` and `absent_paths`. Policy is
`glibc_x86_64_no_preload_v1`. Loader arguments inhibit cache, fix the library
path and disable glibc hardware-capability substitutions. The only absent path
is `/etc/ld.so.preload`.

Optional spec `native_loader_policy` names that fixed policy, not a general
filesystem-observation API. Existing launch/READY/GO verification checks trusted
`/etc` ownership and absence of any preload entry, including dangling symlinks.
The wrapper verifies/seals native and loader bytes and executes their descriptors,
then verifies actual mapped files at native READY before requesting frames.
This qualifies pinned trusted code under the existing immutable-installation
assumption, not arbitrary dynamic plugins or hostile administrators. No second
helper authority, scheduler or process owner.

## Completed artifact to Data

`Runs.capture_artifact(run_id, name, expected_sha256)` requires inspect authority,
verifies the complete published external result and custody, captures exact bytes,
rechecks their hash and returns a server-derived receipt.
`ScientificAssets.admit_run_artifact(run_id, name, expected_sha256, body)` requires
edit authority and calls that owner itself. HTTP exposes
`POST /api/workspace/runs/:id/import-data/:name`, accepting only the expected hash
and existing optional name/rights/groups/parents metadata. Parse strict bounded
JSON. Callers cannot supply provenance, review status or approvals.

New provenance method `run_artifact_import` selects `run_source`, never
`project_source`. The closed source receipt has version, catalog/Run/attempt IDs,
request/material hashes, artifact name/role/size/measured hash, custody hash,
READY identity and canonical base64 of 1–16384 original custody receipt bytes.
Run/attempt/request identities must agree. Artifact size/hash must match captured
bytes. Shared pure `recipe_process.validate_receipt(raw, expected_identity)`
requires completed and drained custody; `load_receipt` delegates after reading.
Cold readers verify retained relationships, not independent historical database
approval authenticity or a recomputed full material document.

Import creates a draft. Human review and freeze remain separate. Preserve the
old project representation and reject mixed variants. Existing duplicate-content
policy returns conflict without a second record; a lost acknowledgement is
reconciled by inspecting catalog content, not rerunning production. Preserve
rollback cleanup and uncertain-commit custody. No database schema change.

Restore refinement: retain absolute execution paths/spec hashes as historical
evidence while reading artifacts beneath the restored catalog. Validate the full
spec against its canonical declared staging path. Dispatch refuses a path that
differs from the current owned staging location; never replay restored attempts.

## Exact write ownership

- Runtime: `recipe_contract.py`, `recipe_process.py`, corresponding two test files.
- Adapter: `adapters/rheon/generate.py`, `project.py`, `README.md`,
  `docs/contracts/rheon-producer.md`, `tests/test_rheon_adapter.py`.
- Root: `runs.py`, `scientific_fields.py`, `app.py`,
  `tests/test_run_scientific_import.py`, `tests/test_external_http.py` if needed.
- Reader: `scientific_release.py`, `tests/test_scientific_release.py`; an additional
  scientific storage test file only if the existing restore fixture needs it.
- UI: `static/workspace-real.js`, `workspace-service.js`, `workspace-external.js`,
  `workspaces.css`, `workspaces.js`, `tests/test_workspace_external_controller.cjs`.
  The `workspaces.js` callback reuses generic catalog navigation and dirty/intent
  guards instead of the classification correction path.
- Evidence: `tests/browser_workspace_native.cjs`,
  `tests/qualify_native_generation.py`, dedicated reports/screenshots.
- Root documentation/packaging: README, external-recipes/scientific-fields
  contracts, this plan directory and `.github/workflows/tests.yml`.

## Acceptance

Qualify actual 32³/two-frame seed 100 and a second seed through approved Runs;
compare every field against original wire with independent NumPy. Exercise exact
artifact import, Data inspection, owner review, freeze/download, cold read,
restart and relocated complete backup restore. Check frame-count family stability,
invalid controls before execution, cancellation without partial import, artifact
drift, rollback/unknown acknowledgement, authority denials, and desktop/narrow/
keyboard UI. Preserve generic startup without the optional adapter and old
Python/project-source behavior. Native generation is not P5 training, GPU,
performance or general scientific-quality acceptance.
