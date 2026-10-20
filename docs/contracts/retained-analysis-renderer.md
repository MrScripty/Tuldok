# Retained checkpoint renderer adapter

Status: mounted in existing Runs for verified completed native classifier
results, with lead-approved additive HTTP/contract and lifecycle hooks.

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
and expressionInterpreter. The renderer runs with script-src self, without
unsafe-eval or inline scripts. Its isolated fixture also uses style-src self.
The deployed /workspaces policy retains unsafe-inline for existing application
CSS; this grants no inline script/eval permission. The meta policy precedes all
assets and restricts data connections to the same origin, objects/base to none,
images/media to existing local/data/blob needs, and frames/forms to self.
No pre-existing CSP was relaxed. `static/vendor/retained-analysis/manifest.json` records
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

The authored renderer test establishes malformed/oversized spec and response
rejection, precise widget lifecycle and strict-CSP compatibility. It does not
substitute for custody or access acceptance.

`node tests/browser_retained_analysis_actual.cjs` separately opens the normal
application with the existing PostgreSQL catalog and a normally trained,
retained two-epoch native classifier fixture. It checks the actual named query,
exact retained numbers, keyboard-linked table, 390px layout, actual response
cancellation, authorized JSON download, real credential revocation, and a fresh
application-process/cache-bypassed reopen. It also revokes access immediately
before normal Run detail, prediction and model-evidence requests, proving that
denials clear previously rendered private content even after identity becomes
null. Deployed CSP violations are captured; ordinary runtime code generation
is explicitly checked with the DevTools CSP bypass disabled. No remote chart
asset is requested. These are bounded workflow checks, not full-application
accessibility or performance certification.

## Integrated host contract

Two new inspect/read operations, `runs.retained_analysis/1` and
`runs.export_retained_analysis/1`, have closed typed request/response schemas and
exact browser pins. Every prior contract/discovery document remains unchanged.
POST `/api/workspace/runs/<run_id>/retained-analysis` and its `/export` sibling
require an explicitly selected contract. Bodies omit run_id and reject any
duplicate; the handler supplies the validated URL ID. The export flag is owned
by the route.

The existing verified native classifier section constructs requests from its
exact artifact/metric/checkpoint inventory. The widget owns a separate root and
uses authenticated bounded transport with timeout/caller-abort wiring. Mount,
Run replacement, navigation, session change and access failure dispose its
view. Old responses cannot update a new selection or authority. Failed access
also clears the containing private Run. The model transport captures Run,
credential and generation before dispatch and forwards access denials before
local catches, including old checkpoint/candidate/package/comparison reads.
Aborted or invalidated-generation replies cannot trigger cleanup. Existing coordinator/phase/publication/
scientific controllers retain their ownership; no new computation starts on
view opening. The Dataset selector starts disabled until existing initialization
attaches its handlers, including during local vendor-asset loading.

The branch composes reliability baseline 83a1e128 and adds CI commands using one
actual retained fixture outside uploaded QA artifacts; private login material
stays outside evidence. The repository lead alone merges this dependent PR.
See [acceptance](../plans/retained-analysis/reports/m4-integrated/acceptance.md).

Official references checked 2026-10-19/20:
[Altair serialization](https://altair-viz.github.io/user_guide/saving_charts.html),
[Vega-Lite parameters](https://vega.github.io/vega-lite/docs/parameter.html),
[vega-embed options](https://vega.github.io/vega-embed/index.html),
[Vega interpreter](https://vega.github.io/vega/usage/interpreter/).
