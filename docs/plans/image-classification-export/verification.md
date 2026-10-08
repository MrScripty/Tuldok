# Qualification record

Base: public development `cdb8e241b002c5beef464df1bec36f10efb7023e`.
The source snapshot was restored from the connected repository reader, with all
375 Git blob hashes and the original commit/tree verified before editing.
Frozen main remains separate. No branch, pull request or merge was published.

## Passed

- The explicit nonbrowser aggregate scope passed **41/41 registered commands**,
  with zero failures or skips in that scope. This included **367 Python tests**,
  the 18 new classification tests, existing controllers and syntax gates, the
  focused classification controller, and the actual consumer gate.
- Python checks used a real local HTTP server for preview, token-required freeze,
  download hashes, stale-revision rejection and immutable reread. The source
  and release tests also cover draft/programmatic-review rejection, malformed
  multiple labels, path-like and Unicode labels, preserved same-split repeats,
  conflicting cross-split pixel identities, unselected bridges, missing/changed
  assets, deterministic repeated export and partial-file cleanup.
- Installed **torch 2.8.0+cpu**, **torchvision 0.23.0+cpu** and **scikit-learn
  1.7.2** read the actual archive. The six records decoded through ImageFolder,
  with exact exported folder/index/label correspondence in train/val/test.
- The unchanged pinned Chapter 8 `train_image_classifier.py` ran its tiny CPU
  model for one epoch, then validation, checkpoint reload and final test. The
  actual ImageFolder rejected an empty class; the actual trainer rejected one
  class. No model weights or real training data were downloaded.
- The installed reader source SHA-256 was
  `b2a36e520cf451d82b993e6fdaa1266d8526ef6a402dcf401f23f0c9cd0a8efa`.
  The trainer source SHA-256 was
  `a198463590d41660c21ae45313b47c3a5baf38889eb9bc029e4c7fe8aa741ac1`.

The aggregate was intentionally selected with:

```sh
python scripts/qualify_text_classification_local.py \
  --python /path/to/pinned-consumer/bin/python \
  --only '^(?!node tests/browser)(?!node tests/test_rights_note_artifacts).+'
```

Disposable receipts, ZIPs, a tiny checkpoint and logs are stored under ignored
`build/qa/`. They are not source inputs and are not committed.

## Browser gap

The complete registry contains **72 commands**. The **31 browser-dependent
commands were excluded** from the aggregate above; this is not a full aggregate
pass. The newly authored browser test could not start its Chromium fixture:
ProcessSingleton's `socket()` returned `EPERM` before debugger readiness. A
reviewed elevated execution retry produced the same runtime failure.

The supported existing cloud browser was also checked. It rejected navigation
to the loopback preview with `net::ERR_BLOCKED_BY_CLIENT`. No network/security
setting was changed and no alternate route bypassed that restriction.

Therefore cancel/discard dialogs, actual visual rendering, reload behavior and
narrow screenshots in the new browser gate are **authored but not executed** in
this environment. Controller tests cover corresponding state/epoch semantics,
but do not substitute for rendering/browser qualification. CI registers the
browser gate for execution in its normal supported Chrome environment.

## Meaning of the consumer smoke

The authored solid-color images prove export/reader/runner compatibility. Their
metrics do not establish real-data quality, class coverage adequacy, usefulness
of learned features or a model ready for deployment. No inference integration,
audio support or new Rheon training qualification is implied.
