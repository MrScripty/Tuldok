# Actual text/audio one-fit Runs browser qualification

Both task gates passed on committed test source `a9154952e69e75945cdeb26ecf262ac1c9ae0ce8`,
with Chromium 151.0.7922.173, PostgreSQL and the separately provisioned sklearn
1.7.2 CPU runtime. The isolated source combines product `06d5b01` with UI owner
commit `4214e36` (local cherry-pick `16da6da`). No UI source was edited by this gate.
Exact application, producer, UI and test SHA-256 values are retained in the
[text receipt](examples/p4-one-fit-browser-text-receipt.json) and
[audio receipt](examples/p4-one-fit-browser-audio-receipt.json).

Each gate authors and freezes 18 task fixtures through the existing one-fit
qualification driver. It creates two actual model-aware Study/Run fits and one
actual unchanged legacy recipe fit. Study admission uses authenticated HTTP;
workers perform real CPU computation. No completed rows, checkpoint bytes or
model predictions are injected. The first Run independently reconstructs copied
JSON in an isolated interpreter; maximum probability error was zero for both
final fixtures. Browser owner authentication uses the ordinary local login and
HttpOnly session exchange, through the existing test fixture helper.

| Task | First model-aware Run | Second model-aware Run | Actual legacy Run |
| --- | --- | --- | --- |
| Text | `63f893d5f55140519d58523938366bbb` | `24c90794dd6f4d4688d09165ae9f4181` | `9c53a01c40844251a120046afef63777` |
| Audio | `4822f4dbe86b40c3aff1ebf84e296702` | `26c3fedef0634fe798c4cf832d1eb68c` | `ec37e1f475d949998fd33335d4e97a83` |

Native keyboard activation and select controls verified all of the following:

- Runs show linked fit evidence, exactly one **Fit pass 1** checkpoint and frozen
  validation probes. Epoch and optimizer-update clocks remain null; no epoch
  curve is drawn. At 1440×900 and 390×844 the page has no horizontal overflow;
  the checkpoint table retains its own bounded horizontal scroll. Keyboard focus
  on the exact fitted-state link has a visible three-pixel outline.
- The retained whole fitted-state HTTP response has the exact checkpoint byte
  count and SHA-256: text 2,177 bytes, audio 1,637 bytes. Both test artifacts return
  HTTP 409 while locked; the Run remains unexposed after the entire workflow.
- Choosing the second actual Run, its single checkpoint, loss definition and
  paired mode produces a zero paired delta. The observed request binds both
  evaluation hashes, both checkpoint hashes, both metric-definition hashes and
  the explicit metric/mode. No browser-generated replacement values are used.
- The frozen-probe correction link opens ordinary Data with the exact current
  record ID/revision and visible frozen-target context. No unrelated image
  preparation form is required for text/audio navigation.
- The actual legacy fit honestly reports that checkpoint/probe history was not
  captured. Returning to the model-aware Run and loading a fresh main document
  preserves the single checkpoint and exact backend evidence.

Screenshots were inspected at both widths and remain in the disposable QA paths
listed in the receipts. Each task has linked-fit evidence at both widths, plus
390-pixel comparison, current Data and honest legacy-result captures. Browser
console exceptions and server tracebacks were absent. The retained compatibility
qualifier also passed unchanged on the final composed P4 source `9ec73d0`, using
pinned legacy `f1ecf788`; `/tmp/p4-retained-9ec73d0.json` records exact artifact
preservation through upgrade and both backup/restore routes.

To repeat either task in the established CPU/PostgreSQL environment, put the
runtime's Python first on `PATH`, set `TULDOK_TRAINING_PYTHON` and
`TULDOK_DATABASE_URL`, then run:

```sh
TULDOK_ONE_FIT_TASK=text node tests/browser_one_fit_model_evidence.cjs
TULDOK_ONE_FIT_TASK=audio node tests/browser_one_fit_model_evidence.cjs
```

This gate starts from actual HTTP-prepared model-aware Runs. It does not qualify
browser import, model configuration, correction editing, native browser zoom or
mobile touch interaction. Existing task browser suites own import/editing and
P3 owns its model-configuration browser gate. Authored text intents and generated
PCM tones qualify evidence plumbing, not accuracy, generalization or physical
validity. No generic text/audio inference package or scientific physical adapter
claim follows from these results.
