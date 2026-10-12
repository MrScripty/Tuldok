# M2 qualified image workflow

The first real image workflow is implemented on
`feature/workspace-image-runs-20261011`, admitted from the fully qualified
combined PostgreSQL/M1 checkpoint `907da2f3df974802f167dd4ce1905159bf50126a`.
Runnable checkpoint `54fac0fa747f14df7494abd234d8f61326f37f7a` is pushed.
Its successor `f725bd1806bfe5e27635eb817a403b602a14591a` contains the final
damaged-run navigation repair and expanded browser qualification. Final qualified
checkpoint **`acac0d32e89b67fa5d9b351ea058152adbe196e3`** passed
[full lifecycle CI38180720462](https://github.com/MrScripty/Tuldok/actions/runs/38180720462)
with **98 successful steps, zero skipped**, plus
[focused M1 CI38180720467](https://github.com/MrScripty/Tuldok/actions/runs/38180720467).
The final job log confirms **507 tests in 199.067 seconds, OK**, the repaired
Pumas scenario, three recovery checks and the complete real image workflow.
Runtime files are unchanged from independently accepted `f725bd1`; later
commits contain documentation, screenshots and reviewed browser-harness repairs.
M2 technical acceptance is complete within the explicit bounds below.

## Clean source browser evidence

Reviewed runtime `f725bd1806bfe5e27635eb817a403b602a14591a` passed
[full lifecycle CI38179432512](https://github.com/MrScripty/Tuldok/actions/runs/38179432512):
all 98 steps succeeded, zero skipped. Its job log confirms **507 Python tests
in 272.605 seconds, OK**, the real image workflow and all three browser
recovery checks. [Focused CI38179432749](https://github.com/MrScripty/Tuldok/actions/runs/38179432749)
also passed. The earlier runnable checkpoint's CI38179222116 passed all 97
then-registered steps. No inherited gate was removed.

The later publication/test checkpoint `bfdf475` failed
[CI38179625084](https://github.com/MrScripty/Tuldok/actions/runs/38179625084)
at the inherited `browser_pumas_typed.cjs` line 122: the second caption request's
deliberately lost response never reached the expected failed job within the
existing deadline. The run ended with 92 successful steps and five skipped;
it is not an accepted final-head qualification. Authorized job logs provide
the exact location and no page runtime exceptions. This prompted targeted investigation; the earlier green source run did not
waive this failure.

The unchanged test reproduced the exact line-122 timeout locally. A dedicated
worker then proved its missing readiness boundary: holding the real Apply
response after the backend commit lets the old current-revision predicate pass
while `captionProposalBusy` remains true. Replaying the old programmatic submit
then produces zero admission POSTs, as the controller intends. The repaired
test releases that response, waits for completed UI action and cleared pending
receipt, then uses an enabled, visible, hit-tested physical click. It asserts
one new admission, binds the failed job to that exact request ID, and preserves
the unknown-outcome and exactly-two-provider-requests/no-replay assertions.
No timeout was extended and no product file changed.

The independent reviewer accepted the stable test SHA-256
`2280074da9ae31710ec79fe3bd498b6d44827e6aaf0a10b9f11f560603da600d` and
reran it successfully with that same hash before/after execution. Its receipt
is `build/qa/pumas-typed/run-dihbUA/receipt.json`. The subsequent full `acac0d3` CI passed the repaired gate and every remaining
gate. That complete successor run closes the failure; the targeted pass alone
was not treated as acceptance.

`f725bd1806bfe5e27635eb817a403b602a14591a` passed 14 real-browser checks with
`dirty:false`, including real stale-validation rejection/recovery, deliberate
loss of a committed submission response and explicit same-key reconciliation,
delayed correction navigation, loading/error/empty states and restart.
The [published screenshots](../../../../images/workspaces-m2/README.md) retain
the original receipt and hashes. Desktop 1440px, intermediate 1024px, narrow
390px and genuine native Chromium 200% zoom passed overflow checks. At native
zoom, Data, Pipeline and Runs were reached by keyboard; device-pixel ratio
doubled and CSS width halved after clearing device emulation.

The separate `browser_workspace_recovery.cjs` uses explicitly mocked transport
to reproduce exposed-run→new-run validation reset, prediction-fetch failure
isolation and damaged-detail→healthy-run navigation. All three pass. This
suite makes no backend or training execution claim.

The original M1 browser gate passed all 18 checks after its physical click
helper was tightened to wait for post-scroll paint and assert the target is
unobscured. A preceding local attempt missed a checkbox immediately after
closing an embedded dialog; no selection assertion was removed or weakened.
Product behavior was unchanged by this harness repair.

The actual adopted Coding-Standards plan validator passes. It caught a
noncanonical `Implementing` milestone value in the earlier admission record;
the verification checkpoint used the supported `Verifying` value; final
technical acceptance now uses `Accepted`. Engine MCP remains
unavailable; no Engine certification is claimed.

## Earlier candidate evidence (retained chronology)

- All 507 Python tests passed without skips in 309.449 seconds. This included
  storage extension/backup/migration, bounded graph, durable run lifecycle,
  actual CPU training and independently recomputed checkpoint predictions.
- `node tests/browser_workspace_image_run.cjs` passed eight end-to-end checks
  on Chromium 151.0.7922.173: ordinary import/review of 12 authored CC0 images;
  held-out class-coverage refusal; immutable release; parameter edits and
  disconnected graph refusal; one real CPU run from a repeated submission;
  current-record correction/new release with historical bytes unchanged;
  explicit durable test exposure; application restart without replay.
- Every published artifact was downloaded through HTTP and matched its
  manifest byte count and SHA-256, including serialized JSON artifacts.
- This run's receipt is `build/qa/workspace-image-run/run-XZFVOF/receipt.json`.
  Run `b16316695c4345389620dfd9d92cf8ac` consumed release
  `5777be8adb36de691ed13bf74aeb60f4152833c28b2ba334e2d6aaa08e91dcb4`.
  That receipt explicitly marks the uncommitted candidate source. The final
  published captures instead use the clean `f725bd1` run described above.
- The browser, server and trainer inherited the loopback-only libc test
  helper. Twelve canaries proved external IPv4/IPv6 connection, datagram and
  name-resolution refusal while local TCP/UDP/Unix transports worked.
  This is ordinary transport qualification, not an adversarial direct-syscall
  security sandbox. No model weights, external dataset or paid service was used.
- Independent review re-ran all 13 run tests and verified corrections for
  durable admission/recovery, stale submission handling, late correction
  navigation, test-view reset and prediction-fetch failure isolation.
  Final correction-banner/source review and the publication/test delta were
  independently accepted; see [review record](independent-review.md).

The clean captured two-epoch run reports 3.027059336 seconds and 398,884,864
Linux peak RSS bytes (about 380.4 MiB), including runtime loading, release
validation, training and evaluation up to metrics generation. These are observed
values for this tiny local workload, not a performance guarantee.

## Reproduction

Configure a local PostgreSQL service as documented in README. Use an isolated
catalog and a role with CREATEDB for the full migration qualification suite.
Install ordinary requirements in the app environment and
`requirements-training.txt` in a separate optional training environment; set
`TULDOK_TRAINING_PYTHON` to that environment's absolute Python executable.

```sh
python -m unittest discover -s tests
node tests/browser_workspaces.cjs
cc -shared -fPIC -O2 -Wall -Wextra -Werror -o /tmp/tuldok-offline-loopback.so tests/fixtures/workspaces/offline_loopback.c -ldl
LD_PRELOAD=/tmp/tuldok-offline-loopback.so node tests/browser_workspace_image_run.cjs
python app.py --data /tmp/tuldok-image-workspace --port 8092
```

Open `http://127.0.0.1:8092/workspaces` and choose Current local catalog.
Existing schema-v1 catalogs require the explicit documented, quiesced
`upgrade_metadata.py` operation; ordinary startup does not silently upgrade.

On 2026-10-11 the selected execution environment served the populated authored
capture catalog at `http://127.0.0.1:8094/workspaces`. A recovery command after
the environment-disconnected callback confirmed the branch/commit and a live
HTTP 200 response with exactly one completed run. No duplicate build, push,
service or training request was started for recovery. The 2026-10-12 environment
restart retained the repository but removed that temporary service/catalog; the
historical URL is not a claim of current availability. With the described
temporary PostgreSQL and Python environments provisioned, a fresh launch is:

```sh
TULDOK_DATABASE_URL='host=/tmp/tuldok-pg/socket port=5432 dbname=tuldok user=tuldok passfile=/tmp/tuldok-pg/app.pgpass' \
TULDOK_TRAINING_PYTHON=/tmp/tuldok-training-venv/bin/python \
/tmp/tuldok-app-venv/bin/python app.py --data /tmp/tuldok-m2-fresh --port 8095
```

The referenced local passfile contains temporary fixture credentials outside
Git. It is not needed for the portable README setup using the user's own local
PostgreSQL configuration.

The classifier runs from scratch on tiny authored workflow inputs. Its metrics
are actual execution evidence and do not establish model quality. Audio and 3D
remain represented by their honest M1 capability states. No main merge,
deployment or personal-data migration is part of this checkpoint.
