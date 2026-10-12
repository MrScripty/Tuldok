# Audio runs increment — implementation evidence

Admission: `audio-mesh-admission-20261012.md`, canonical plan blob
`d7c0b894219da0d229eee960b9a11616805276a5`, operation `continue`.
Branch `feature/workspace-audio-runs-20261012` starts at d4a5b196 and includes
root's narrow HTML selector commit 2faae824. Main and older worktrees remain
unchanged. No schema migration or new runtime dependency is introduced.

First runnable checkpoint implements real authored WAV admission/review,
classification preview/freeze, checked complete-family reader and editable
audio graph. A missing trainer produces `unavailable` and admits no run.

Evidence before source checkpoint:

- Five real PostgreSQL audio release/graph tests passed in 3.441 seconds.
- All fourteen existing text reader/trainer/run cases passed in 13.804 seconds
  after shared-family extraction, including a real CPU run and reopen.
- All ten existing audio parser/custody/backup cases passed in 2.969 seconds
  after the custody-only lazy import.
- Actual Chromium release/graph walkthrough passed four checks: keyboard empty
  Runs navigation, authored source admission, UI freeze/download, edited graph
  and honest unavailable validation. Desktop 1440 and narrow 390 captures have
  no document horizontal overflow. This checkpoint uses fixture setup through
  ordinary HTTP import/review followed by actual Data/Pipeline UI actions.

The first candidate captures and receipt are in
`build/qa/workspace-audio-run/run-b9U4dz`; they truthfully record a dirty working
tree. Clean source-bound captures follow the source commit. Root/independent
review and final CPU, cancellation/restart, correction/exposure, offline and
hosted gates remain pending; this is not final audio execution acceptance.

Launch from the feature worktree with the configured local PostgreSQL service:

```sh
TULDOK_TRAINING_PYTHON=/path/to/optional-cpu-python python app.py --data /path/to/catalog --port 8099
```

Set `TULDOK_DATABASE_URL` using the existing local PostgreSQL runbook. Existing
catalog migration/backup requirements remain unchanged. No personal catalog was
opened. The local browser command is `node tests/browser_workspace_audio_run.cjs`
with app Python on PATH and the same test-service environment.


Clean checkpoint `1959775933030a3639ad504143207d9d8d786f1d` repeats all four
browser checks with `dirty:false`; source-bound unmodified captures are in
[the checkpoint gallery](../../../images/workspaces-audio-runs-checkpoint/README.md).
Root and owner reviewed desktop Pipeline/narrow Data. The feature branch is
pushed; no PR, merge or deployment has been performed by this worker.


## Real CPU checkpoint

The next source checkpoint implements the admitted eight fixed PCM features,
train-only scaling and deterministic bounded logistic regression. Binary and
three-class real fits publish verified JSON models and source/frame/channel
predictions. No dependencies, schema changes or model downloads were added.

Focused qualification: ten audio tests passed in 33.514s, including an actual
child cancellation/drain and explicit fresh retry; a separate real supervisor
process-death/reopen/retry case passed in 10.006s. The ordinary earlier close
experiment correctly cancelled queued work; its test was corrected to represent
abrupt connection loss separately from graceful shutdown, without changing the
production lifecycle. Analytic silence/DC/Nyquist/band-edge and odd-length
impulse cases plus an independent scalar PCM/direct-DFT model oracle check
channel selection, half-open coordinates, feature values, training means and
binary probabilities. Nonconvergence refusal and multi-class cold-read models
are exercised separately. No model-quality claim is inferred.

Existing shared-owner regression checks: Runs 13 (27.626s), Pipeline 6 (2.678s),
text 14 (15.235s), fixture service and Workbench controllers passed. Root's
retained-image/text check at clean1959775 compared both prediction splits,
public results, raw graph/run/exposure rows and 68 managed file hashes against
the main-identical baseline with a child-process trap: byte-identical, no replay.
It will repeat against final source.

The actual headless audio browser candidate passed twelve checks with eleven
captures (`build/qa/workspace-audio-run/run-QyqTW7`): real release/graph/CPU run,
loading/error/late responses, stale edits, lost committed response and duplicate
click reconciliation, exact frame results, correction/new release, durable test
exposure and restart. This candidate receipt truthfully records dirty source;
final clean/native-zoom captures and independent review remain pending. Root's
4a919ad integrates the exact training scope into HTML/README and registers the
new browser in hosted lifecycle CI. No hosted success is claimed yet.


## Independent custody finding and repair

Independent reviewer reproduced P2 on runtime61a9f67: after the release reader
verified captured ZIP bytes, the runtime probe hook replaced the pathname with
zero-sample WAVs. The trainer reopened that pathname and could publish zero-RMS
features under the original release identity. This was a real custody defect;
prior successful fitting/browser evidence did not establish this race property.

The repair makes the private reader return the manifest plus its exact owned
immutable ZIP capture. The public inspection response remains manifest-only;
training extracts features from the retained capture, with no second pathname
read or weaker rehash fallback. The actual-trainer regression replaces the path
after verification: it fails against the old adapter (mean RMS 0) and passes
against the repair (retained original mean RMS greater than .15). Repair evidence
is `/tmp/tuldok-audio-owned-bytes-before.log` and
`/tmp/tuldok-audio-owned-bytes.log` (1 test, 2.455s). Independent exact-repair
retest remains a separate gate.

The earlier clean cbbde7c native/loopback workflow passed thirteen checks with
fourteen captures at `build/qa/workspace-audio-run/run-F882Kq`; it is retained as
historical evidence. Final clean captures follow the source repair. Source
review and hosted qualification remain pending; no failure is waived.


## Repaired source qualification

Runtime repair `5db224059162e2600bb4f05d754de167f4d752f3` passed all thirteen
focused audio tests in 53.897s. Independent review repeated the thirteen with
zero skips in 55.721s and accepted the custody repair: an atomic pathname swap
to zero WAV samples during probing retained the original frozen SHA and
produced mean RMS 0.20060549270526823, matching the independent scalar original
0.2006054927052682. No additional audio source blocker was demonstrated.
The portable [review evidence](../../../images/workspaces-audio-runs/independent-owned-capture.json)
and [focused test log](../../../images/workspaces-audio-runs/focused-audio-tests.txt)
are preserved with the screenshots. Final visual review remains independent.

Harness-only successor `a9f5ad39132a8795122bfbb360591ff17d142d0a` added
saved interval and prediction frame detail captures without changing runtime.
Root's visual review then identified a channel display ambiguity: Data showed
human channel numbers alongside zero-based indices, while predictions showed
only the index. Renderer-only `292ba880b8bdcb80a469e5d370e29e5f006929a9` now
states “Source channel 1 (index 0)” explicitly without changing stored values.
Independent review accepted this exact copy change; runtime tests remain
applicable.

Clean292ba880's actual native Chromium workflow passed thirteen checks and
produced fifteen original JPEG85 screenshots at
`build/qa/workspace-audio-run/run-jUilnE`. The
[final feature gallery](../../../images/workspaces-audio-runs/README.md)
contains all captures, an exact source receipt (`dirty:false`) and SHA-256
manifest. The owner visually inspected final saved source fields, prediction
references, desktop graph/results and native Runs; the preceding full gallery
was also inspected before the one-line wording correction. Desktop 1440,
intermediate 1024, narrow 390 and native 200% layouts remain readable without
document horizontal overflow. Root and independent visual acceptance are
recorded separately from this implementation pass.

The final browser uses eighteen authored mathematical CC0 WAVs admitted and
reviewed through ordinary HTTP APIs, then actual release, graph, submission,
results and correction controls. It verifies loading/error/late-response and
keyboard navigation, stale revisions, lost committed response reconciliation,
one real CPU child, locked test artifacts, immutable results after correction,
durable exposure and reopen without replay. Its twelve transport canaries
qualify ordinary libc loopback restrictions, not a direct-syscall sandbox.

Root has integrated the repaired runtime into its combined feature source and
owns one combined Python run, final retained-image/text proof, draft PR and
hosted gates. Those results are not inferred from this feature pass. No main
merge, deployment, new dependency, weight download or personal catalog access
was performed by this worker. ASR and general audio inference remain unavailable.
