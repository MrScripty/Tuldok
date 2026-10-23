# Browser handler fixtures after the cold-Study repair

The [plan](../plan.md) owns current status. This report records the third
complete-candidate campaign and the bounded fixture compatibility repair.

## Exact failed subject

Feature head `3ac3351a741cf5e6ef4712e3577f3fc0d3a3f3e5`, based on main
`133d53c0e2985a6559ba9cebd7d4a9f530051f06`, ran lifecycle
[39893561852](https://github.com/MrScripty/Tuldok/actions/runs/39893561852),
job `120218652037`. The decoded root checkout confirms PR merge
`da7ec49d55b4bf6d8186c02d81918133de718d28`; merge and feature share tree
`06193f266222f32423c24c1677a7458d9895360a`. Coding-Standards remains
`5bce3110fc64d61ff8b4f79468184bd6295855d5`. Both remote baselines were
rechecked unchanged before this diagnosis.

Full discovery ran 2,332 cases in 3,014.033 seconds: **OK**, zero failures,
zero errors, 107 optional/intentional skips. This clears the earlier cold-Study
wait failure on the changed candidate; the previous CI Run's unobserved final
outcome remains unobserved. The three other workflows succeeded: M1 interface
`39893561721`, extension catalog `39893561904`, captured CPU `39893561748`.

| Required real gate | Cases | Seconds | Result |
| --- | ---: | ---: | --- |
| Native Run/fork/Study/accounting | 3 | 839.297 | OK, no skips |
| Native SDK/CLI/MCP | 1 | 32.187 | OK, no skips |
| Note deletion/cold-fork transports | 1 | 14.092 | OK, no skips |

All six project Chromium gates (steps 45–50: authoring/cold reconstruction,
independent fork, runtime, extraction, native recovery and note deletion) passed.
The earlier observation browser (72) also passed. These are scoped successful
results; lifecycle as a whole failed at step 152 and later checks 153–180 were
skipped. No terminal product acceptance is claimed.

## Failure and bounded repair

`node tests/browser_text_classification_proposals.cjs` stopped before HTTP
readiness: `app.main` passes `transfer_controller` to `make_handler`, whose
production signature has an explicit keyword-only argument. The fixture's
`instrumented_handler(dataset, observer=None)` wrapper still had the old
signature and raised `TypeError: instrumented_handler() got an unexpected
keyword argument 'transfer_controller'`. No proposal flow ran; this is not a
proposal assertion failure or observed proposal race.

A read-only scan found exactly one other current `app.make_handler` replacement,
`tests/browser_pumas_typed_server.py`, with the same stale wrapper. Its configured
browser gate had not been reached; its incompatibility was found in source,
not observed as a second failed CI case. Frozen legacy HTTP factories are
separate and remain unchanged.

Both wrappers now mirror the explicit keyword-only `transfer_controller=None`
argument and pass its value unchanged to the original handler. Admission/refusal
instrumentation, test endpoints, gateway configuration and all browser assertions
remain unchanged. No generic keyword swallowing, product change, workflow change,
timeout increase or test exclusion is introduced.

Independent source review cleared both exact files before execution:

| Fixture | SHA256 |
| --- | --- |
| `tests/browser_text_classification_proposals_server.py` | `ec24aee7f1b26ca31724489c05d6bde975213596e1613f5f5c21b2410dbf7ee8` |
| `tests/browser_pumas_typed_server.py` | `0c7244000a2d33d27f457bcc9b49ab17f71916a2345df7c548ceca366671f1e3` |

The deciding local selection is one complete Chromium run of each affected
browser against existing disposable PostgreSQL and synthetic HTTP endpoints.
No native gateway/model fit, broad suite or same-head CI rerun is selected.
Both complete procedures passed exactly once with exit 0, and both retained the
browser assertion that `Runtime.exceptionThrown` is empty. All 912 tracked
source/test hashes were unchanged across execution, including both reviewed
wrapper hashes. Chromium's environment DBus/OOM-score diagnostics remain in raw
logs; they are not application exceptions. This scoped pass does not make the
failed CI campaign successful; the later repository gates still require the
changed-candidate campaign.

## Retained evidence

Under `/workspace/scratch/tuldok-save-load-qa/artifacts/`:

| File | SHA256 |
| --- | --- |
| `lifecycle-39893561852-3ac3351.log` | `7fd2b8ba16a5d50bcb717ecc414ba7f9a99c41920e6ffec6e0c162e6db5aac5a` |
| `exact-candidate-ci-3ac3351-39893561852.json` | `04a4486b2f98c6f5aaa0142ed827d2d3bed3b503e7fc7785b492e11530860574` |
| `browser-handler-3ac3351-repair-receipt.json` | `f6bb8d42ea58dc5ec791cc2a507a109bdaff5298ec32fced3ba22cb82beebd35` |
| `browser-text-classification-proposals-3ac3351-handler-repair.log` | `3a9a92416eccf128698b72e962ca087438ec51e6374e433c21aea0dd73d55100` |
| `browser-pumas-typed-3ac3351-handler-repair.log` | `b7e6c36ab2cc47c8e01c48ee895545220d6b528009df53a8e9bfdee649d08e80` |

Artifact `12479940595` uploaded successfully; no download was attempted and its
manifest remains uninspected. No previously denied retrieval route was retried.
Available checkout logs and independent Git tree reads identify the subject.
Earlier failures and unrun gates retain their original status. The PR stays
draft until a complete changed-candidate campaign and final review close the
plan's acceptance condition.
