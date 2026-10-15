# Private static extension authoring front-end

This preparatory SDK slice validates one inert package against E1's canonical
contract. It does not qualify E2 execution or E3's real A/B authoring gate.

Explicitly provision `requirements-extensions.lock` in the authoring environment,
then run from the source kit:

```sh
python -m pip install --require-hashes -r requirements-extensions.lock
python -m tuldok_extension_sdk validate examples/extensions/template
python -m tuldok_extension_sdk validate PROJECT_ROOT --manifest nested/extension.json
```

Every referenced path is relative to PROJECT_ROOT. The root must be a selected
local directory; references are bounded regular files accessed through held
no-follow descriptors. No package code, model, subprocess, network client, app,
DB or Torch is started. This validation reader is qualified on Linux; it does
not claim a hostile-code sandbox or execute-platform qualification.

JSON output is the exact canonical catalog projection: validity, integrity,
host support, runtime qualification and permission are separate. Exit0 means
the one selected package and its included contribution declarations validate
statically. Runtime and permission remain unavailable; unknown host contracts
remain visibly unsupported even when their syntax is valid. Exit1 means a
package/contribution outcome is invalid/unsupported/unavailable. Exit2 means the
selected root/manifest/schema material cannot establish a catalog. Missing
optional validation returns unavailable; no installation is attempted.

Cross-package dependencies need a selected host context, so a dependency outside
this single package remains unavailable. There is no fallback provider, local
execution command, approval shortcut or conformance runner. Actual conformance
requires accepted P1–P4 and a normal authorized E2 Run; inference helpers and
E3 A/B migration follow those proven contracts.

The source kit consists of `tuldok_extension_sdk/`, canonical stdlib owner
`extension_contract.py`, `extension_schemas/`, the optional validator requirements
and the selected authored package. It can be copied into a directory containing
no Tuldok app/database/runtime files. Included `contracts/` copies must match
canonical `extension_schemas/` exactly before validation. Host and SDK import the
same declaration/catalog functions; there is no second policy implementation.
The shared negative corpus lives in `tests/test_extensions.py` and its catalog
fixtures. `tests/test_extension_sdk.py` proves source identity, file boundaries,
CLI outcomes and a fresh kit process without application/DB/Torch provisioning.

Only source captures for private/local use are in scope. No public package
release, installer or license grant is made. The template's license/notice slot
requires actual author/source/data/weight rights before a future export.
