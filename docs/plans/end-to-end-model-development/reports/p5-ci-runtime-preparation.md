# P5 captured-runtime CI fixture qualification

Source: helper/workflow commit `7a3dbf2`, qualified on clean integration source
`f7537752f3811af6b7c247e1b40ff85d1b854b02` (final P5 `c8ceca1`).
This records local execution. No GitHub Actions pass is claimed by this report.

`tests/prepare_candidate_runtime.py` uses the explicitly provisioned current
Linux x86-64 Python 3.12 / Torch 2.8.0+cpu environment. It does not install,
download, alter packages, run capture, or change a runtime profile. It chooses
the fixed forward-inference subset before calling the existing owner inventory.
Complete distribution metadata and upstream notices remain captured; unknown
redistribution rights are not changed. Unused torchvision is not selected;
unused functorch native code, Torch native tests/test data and optional tkinter
are explicit fixed exclusions. No failed ELF check causes another exclusion.

Two preparations produced the same config SHA
`d908e84d88af84f1dad319c34294693c941cc4794c3e9f4b2802b0f3ff6b3de5`
and runtime inventory SHA
`50502c0ba923f3134073188efd55c20b0468c008b1bdfbdc87fd72ea830ffe3d`:
20,804 files, 896,562,621 bytes. This exactly matches the independently qualified
original subset. The second preparation binds the new real model browser receipt.
The helper source SHA is
`5fd6e73ae2fa3cf1f67ddb731873b6ddbfe5e8945d50bb1c94bc7c5160c9f643`.
Exact versions and owner source hashes are retained in the preparation artifact.

The unchanged actual model browser gate passed on the clean source. Its retained
catalog was stopped before the unchanged candidate browser invoked ordinary
`runtime_snapshots.py create --config ... --expected-inventory-sha256 ... --quiesced`.
This created the snapshot in the new catalog `dfa0394652954d70bf480e3dd390c7f4`.
The subsequent real UI package and captured fresh-consumer gate passed with three
charged slots, inert exact approvals, separate package/fresh states and bounded
1440/390 light/dark displays. Source Run `e83591aa94af4186b2fd42eb044fb6b4`, package
Run `f310f140f02a4c228ed17cebe3cdd2de`, verifier Run
`8494d09bafa948fe8866530764a103d7`. Downloaded whole package SHA:
`33409e3f188459733b6f4d30996312b976b097f2873f4d6e74d240f36f9035e1`.
The authored fixture establishes execution and reconstruction, not generalization.

Local evidence roots are `/workspace/p5-qualification/ci-runtime-helper-02` and
`/workspace/p5-qualification/ci-ui-helper-02`; the latter contains model receipt
`model-development/run-2gUCBT/receipt.json` and package receipt
`candidate-package/run-g9XK1l/receipt.json`, snapshot descriptor and screenshots.

`.github/workflows/candidate-packages.yml` proposes a separate 25-minute job.
It provisions dependencies explicitly, runs the actual model browser, prepares
the reviewable runtime config/inventory, exports the three required package
browser inputs, and runs the actual package browser. Existing lifecycle jobs are
unchanged. Its captured inventory is measured afresh on CI and any unsupported
host dependency or loader path fails through the existing strict owner.

## Canonical qualification prerequisites in generic CI

The composed canonical Release tests use an independently decoded NumPy array
and the historical authored fixture at
`057c8abf571d62331486dc56ef43064e72f9d03a`. Generic discovery runs in the base
interpreter, separate from the provisioned training environment. Its old
requirements omitted NumPy; a depth-one checkout also omitted that Git object.

The lifecycle workflow now explicitly fetches only that exact commit at depth
one, verifies the fixture path exists, and reuses the unchanged existing
`requirements-spatial-qualification.txt` in the base verification interpreter.
The fixture reader still checks its complete source SHA
`3c25603d4d95cd904b0d09582daadf000c0977af7bcdcea39ef2c6deffe86e5f`.
Application dependencies, the training/agent environments, assertions, skips,
timeouts and permissions are unchanged.

A fresh temporary depth-one repository reproduced the absent-object failure;
the exact fetch supplied all8,721 fixture bytes with the reviewed SHA. This
uses the retained local repository as the Git remote and does not claim a new
GitHub Actions result. The affected actual PostgreSQL canonical Release suite
passed all9 tests in11.697 seconds under the existing qualified NumPy2.5.4
environment. Independent workflow review is clear. The repaired hosted job
must still complete on its new source head.
