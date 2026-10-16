# P5 native package and fresh-consumer qualification

The real workspace extends the retained diagnostic candidate with native package controls. It reads configured project-root aliases, requires an exact existing captured CPU runtime snapshot and a new directory, prepares one immutable operation, then requires separate exact approval and explicit Study admission. Preparation and approval do not execute a Run. Packaging and a separate fresh consumer use the original Study budget; they never call standalone external submission.

Authoritative package-state reads keep package completion separate from fresh inference verification. Only a completed package supplies a verified download, and only a successful separate consumer receipt marks fresh inference verified. Candidate status remains diagnostic. Missing configured roots and failed state reads produce setup/error text rather than completion claims.

Final acceptance receipt: [`examples/p5-native-package-browser-receipt.json`](examples/p5-native-package-browser-receipt.json), from `build/qa/candidate-package/run-znJknv/receipt.json` with 10 actual viewport captures. The base commit is `c04c0d00453665675ed81b077befa7a9c5e97a2f` with the native P5 UI changes dirty; these exact tested files are the delivered source:

| Tested file | SHA256 |
|---|---|
| `static/workspace-service.js` | `9dd0aa246f885ed4beb40b9f4c4745747df8346d18550b50211346fa1bff0b5b` |
| `static/workspace-real.js` | `3253849345d72c4d4e153288942e02c8f0c891c0b85ae3e2491c5a4f7924db91` |
| `static/workspaces.css` | `efbb74af1712236a769ced2f9e330ac542999b28b27476ce260af0cc78f43b76` |
| `candidate_packages.py` | `12e0909560b9fce0fcc35c6309dbfb5ccef7c4851f094ee1dc45f5504715fae3` |
| `tests/browser_candidate_package.cjs` | `2adcdff00b7fa92808512872da3ab7d4bb075dc74ee0e69388e648b7129e2eb3` |

Source training Run `595df887aac94ee886e2d96eb7ec2dbb`; actual package Run `510939d356b147b2a91d653fbd85e7a0`; independent fresh-consumer Run `9cc6562a86b84e4c8da87360fe38ff0a`. Downloaded package SHA256 `b6cf3ebc1260de9b0e00ea932773b141698c7e8231502e83441f2a2375a57abe`. The authoritative Study has 3 charged attempts. The exact existing captured CPU runtime is `50502c0ba923f3134073188efd55c20b0468c008b1bdfbdc87fd72ea830ffe3d`. Preparation and approval preserve the Run count; only explicit admission creates each operation Run. The browser makes no standalone submission.

Automatic dark preference is exercised at 1440/390 with a visible 3 px keyboard focus outline. Sampled text/panel contrast is 14.18:1 and focus/panel contrast is 9.54:1. Full colors and source fingerprints are in the receipt. Reproduce with `node tests/browser_candidate_package.cjs`, inheriting database/training runtime configuration and setting `TULDOK_MODEL_BROWSER_RECEIPT`, an optional `TULDOK_MODEL_BROWSER_RUN_ID` from that real receipt, and explicit `TULDOK_PACKAGE_RUNTIME_CONFIG`/`TULDOK_PACKAGE_RUNTIME_INVENTORY` for an already reviewed CPU runtime.

## Recovery and review

`node tests/test_workspace_candidate_controller.cjs` covers three independently reproduced recovery defects: a known stale admission must clear the rejected intent and re-read the Study; a possible preparation commit followed by denial must retain the original actor-bound key; and a failed package-state read must retain the saved unresolved operation rather than offer a replacement form. Initial definite preparation refusal can revise inputs. Unknown transport outcomes retain their keys for reconciliation. A positive idempotent preparation response resolves its journal. The existing model and external controller suites and browser contract-pin unittest also pass.

Independent read-only P6 review reran all original reproductions and the durable test suite after the fixes, with no remaining concrete blocker in its action/session/generation/journal scope. Controlled transport regressions are separate from the real browser package execution.

The earlier successful `build/qa/candidate-package/run-LeLWga` flow consumed three finite slots on the first real training Study. The final run uses a third real trained Study with two remaining slots and prepares new projects against final fixed backend source. Prior partial harness runs completed packaging before a disabled-control wait or a CDP selector quoting error; it did not complete a verifier or produce a final receipt. No uncertain action from that run was replayed against the final Study.

This qualification checks packaging, reconstruction and retained probes on authored CC0 patterns. It makes no useful-model, generalization, GPU or numerical/physical acceptance claim.
