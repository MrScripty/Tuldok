# Retained checkpoint renderer adapter

Status: isolated implementation under review. Not mounted in production Runs.
The existing Runs/API/contract registry hooks await repository-lead coordination.

`WorkspaceRetainedAnalysis.mount(root, {load, onSelection})` returns:

- `update(request, authorityKey)`: clear previous private state, abort obsolete
  work, load one bounded named query page and the pinned local spec, validate
  identities/counts/types, then render. Host changes authorityKey and calls
  update/dispose whenever credential, catalog, Run or navigation authority changes.
- `resize()`: resize the active Vega view; container changes also use an owned
  ResizeObserver.
- `selection()`: copy of the current exact query selection, or null after
  failure/disposal. Declared checkbox and page controls issue fresh queries.
- `dispose()`: abort pending reads, invalidate late callbacks, finalize Vega,
  disconnect observer and clear DOM/private state.

`load` is host code accepting `(request, {signal, authorityKey, export})`, returning
the query response. It must use current authenticated transport and the exact
registered contract. It must never select credentials from caller metadata.
The optional host onSelection callback receives a checkpoint hash selected by
chart or keyboard buttons; arbitrary callbacks cannot come from chart JSON.

Exports reissue the same bounded request with export true, validate the fresh
response, then download JSON through a short-lived Blob URL that is immediately
revoked. Failure clears existing private content. Vega export/editor/source
actions are disabled. No export uses previously displayed bytes as authority.

## Spec and dependency authority

`examples/analysis/retained_checkpoint_curve.py` is a readable Altair 5.5.0 authoring
script. Run it explicitly with its authoring-only requirements to generate
`static/retained-checkpoint-curve.vl.json`. View opening never imports Python or
executes the script. JSON bytes and their reviewed SHA256 are retained; JSONB
or mutable overrides never replace that byte identity.

This first recipe accepts exactly one local specification, at most 16 KiB, whose
bytes must match the renderer's pinned digest. The specification contains a
single named inline curve dataset, two marks and one checkpoint point-selection
parameter. Arbitrary user specs, URLs, patches, expression functions, embed
options and HTML/tooltips are not accepted. Changing the script/spec requires a
new reviewed digest. The host alone supplies validated curve data. The bound
schema hint is not fetched. A denied Vega loader prevents data/image/link URL
loading even after compilation; tooltips are disabled and table text uses DOM
textContent. A JSON format alone is never the security boundary.

Self-hosted unmodified upstream browser distributions:

| Package | Pinned version | License |
| --- | --- | --- |
| vega | 5.33.0 | BSD-3-Clause |
| vega-lite | 5.23.0 | BSD-3-Clause |
| vega-embed | 6.29.0 | BSD-3-Clause |
| vega-interpreter | 1.2.0 | BSD-3-Clause |

The v5 family matches the v5 schema emitted by Altair 5.5 and supplies UMD
distributions without a new application bundler. Load in the table order before
retained-analysis.js. The interpreter extends window.vega. Embed passes ast true
and expressionInterpreter; strict CSP does not need unsafe-eval or unsafe-inline.
Do not weaken app CSP. `static/vendor/retained-analysis/manifest.json` records
exact asset/tarball hashes, upstream URLs, and retained notices for packages in
the upstream source maps. Notice-source resolution versions do not claim exact
embedded transitive versions. BSD, MIT and ISC notices are retained with the
assets. No license implies dataset/model rights.

## Acceptance boundary

`node tests/browser_retained_analysis.cjs` starts a local fixture server and real
headless Chromium with a disposable profile. It exercises the actual assets,
interpreter, strict CSP, exact authored numbers, physical keyboard/focus, SVG
point selection, pagination/filter, 390px width, stale reply after revoked-mode
response, decoder/spec tampering limits, fresh export and downloaded JSON,
cache-bypassed page reload and disposal. No external chart-asset request or CSP
violation is permitted. Headless/no-sandbox/software rendering is test-only and
does not establish an application execution sandbox.

This test uses authored responses and access-failure substitutes. It establishes
renderer behavior only. It does not establish actual Runs custody, PostgreSQL
execution, real credential revocation, full application accessibility, or
cold-process retained result reproducibility. The follow-up actual PostgreSQL/
retained native Run tests now qualify the direct query boundary, including real
Access revocation and fresh-process reopening. They are distinct from these
authored renderer tests. The full authenticated API-to-Runs browser gate remains
pending shared-hook integration.

## Pending API dependency and shared hook proposal

No shared-file changes are part of this branch. Proposed additive contracts for
lead agreement before implementation:

1. Register new inspect operations `runs.retained_analysis/1` and
   `runs.export_retained_analysis/1`, each with explicit closed request/response
   schema hashes. Keep existing operations/versions unchanged.
2. Add POST `/api/workspace/runs/<run_id>/retained-analysis` and an explicit
   `/retained-analysis/export` sibling. Require the chosen new contract. Existing
   selected-contract rules place run_id in the path only: reject any duplicate
   body run_id, then inject the path ID when delegating to
   `retained_analysis.query(dataset.runs, body_with_route_id,
   export=host_route_choice)`. No user-controlled export flag.
3. In the existing verified native classifier Runs section, build the request
   from its exact artifact/metric/checkpoint inventory. Mount a separate root;
   load through authenticated transport. Dispose on navigation, credential or
   Run replacement; never change coordinator/phase/publication/scientific
   comparison controllers. Include adapter cleanup in existing authority-failure
   paths and exclude obsolete replies before any DOM update.
4. Load self-hosted assets with the agreed current CSP; add actual authenticated
   application/DB/browser tests and CI only after coordinated write-set approval.
   The lead owns serial integration and merge; no approval or schema migration
   is inferred from this proposal.

Official references checked 2026-10-19/20:
[Altair serialization](https://altair-viz.github.io/user_guide/saving_charts.html),
[Vega-Lite parameters](https://vega.github.io/vega-lite/docs/parameter.html),
[vega-embed options](https://vega.github.io/vega-embed/index.html),
[Vega interpreter](https://vega.github.io/vega/usage/interpreter/).
