# M2 candidate qualification

The first real image workflow is implemented on
`feature/workspace-image-runs-20261011`, admitted from the fully qualified
combined PostgreSQL/M1 checkpoint `907da2f3df974802f167dd4ce1905159bf50126a`.
Runnable checkpoint `54fac0fa747f14df7494abd234d8f61326f37f7a` is pushed.
Its successor `f725bd1806bfe5e27635eb817a403b602a14591a` contains the final
damaged-run navigation repair and expanded browser qualification. Final hosted
lifecycle CI remains required before M2 acceptance.

## Clean source browser evidence

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
the current M2 status is the supported `Verifying` value. Engine MCP remains
unavailable; no Engine certification is claimed.

## Candidate evidence

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
  The receipt explicitly marks the uncommitted candidate source; final
  published screenshots will be captured from a clean source commit.
- The browser, server and trainer inherited the loopback-only libc test
  helper. Twelve canaries proved external IPv4/IPv6 connection, datagram and
  name-resolution refusal while local TCP/UDP/Unix transports worked.
  This is ordinary transport qualification, not an adversarial direct-syscall
  security sandbox. No model weights, external dataset or paid service was used.
- Independent review re-ran all 13 run tests and verified corrections for
  durable admission/recovery, stale submission handling, late correction
  navigation, test-view reset and prediction-fetch failure isolation.
  Final review of correction-banner scoping and the exact commit is pending.

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

The classifier runs from scratch on tiny authored workflow inputs. Its metrics
are actual execution evidence and do not establish model quality. Audio and 3D
remain represented by their honest M1 capability states. No main merge,
deployment or personal-data migration is part of this checkpoint.
