# Managed installed Torch runtime

`managed_torch_python_v1` is an explicit trusted-local external-recipe profile.
It supports `runtime_device: "cuda"` for training and `"cpu"` for deployment
checks using one installed Torch release. CUDA absence fails; it never selects CPU.
Managed CPU restore and inference use this same measured installation and profile.
Other project runtime profiles remain separate contracts; no profile may relabel
this CUDA installation as a captured CPU snapshot.

The catalog owns a canonical manifest under `torch-runtimes/<sha256>.json`.
Owner-only inspection selects absolute Python executable, Python installation
root and site-packages root. It inventories regular files, including extension
libraries and distribution metadata. Registration rechecks the inventory and
publishes it atomically. Recipe `runtime_snapshot_sha256` selects its exact hash.
Preflight verifies installed assets without executing the recipe or an optimizer.
Approved material captures the manifest and bootstrap; retained host identity binds
the bootstrap and registry owner. The dispatch supervisor selects the matching
runtime host closure before process creation. Cold artifact inspection uses retained identities and does not remeasure or
execute installed assets. New execution always verifies the selected installation.

The existing process custodian launches the captured bootstrap with isolated
system Python, then the same owned process execs the measured Python. The supervisor verifies the installed topology and every file before launch
under its existing cancellation and verification deadline. The child verifies
the installed inventory before imports and after recipe execution. CUDA is explicit;
CPU mode hides GPUs and rejects initialization. A private bytecode/cache prefix
prevents installed unmeasured pycache use; `-I -S -B` excludes ambient Python paths
and site hooks. No ambient credentials, Python paths or loader preload variables
are passed. Existing cancellation, deadlines, stream limits, approvals and artifact
publication remain authoritative. CUDA cache files are attempt-local.

This profile is **not hermetic**. The external installation must remain immutable
through the attempt. Host OS libraries, GPU driver/kernel and hardware are external
dependencies; runtime events record observed package/Python/CUDA/GPU/driver versions
and external loader mappings. A writable installation or hostile mutation during
execution is outside this trusted-local boundary. There is no independent GPU
sandbox, package installer, detached scheduler or claim of cross-device bit identity.
Historical scientific catalog transfer does not bundle this external installation;
restored Runs remain inspectable, while new execution requires registration and the
same verified assets at their selected paths.

Bounds: 100,000 installed files, 32 GiB assets, 4 GiB per file, 32 MiB manifest;
320 MiB captured material, 256 MiB total inputs and 40 MiB per input. The existing
600-second child deadline and normal output limits remain authoritative. Readiness
and pre-launch verification each have a 60-second budget. Full installed hashing
has cancellation checkpoints at directory entries and each 1 MiB read. Directory symlinks and asset links
escaping the selected roots are rejected. The required `file_links` manifest
array binds each absolute alias path to its inventoried canonical target;
retargeting an alias between measured files fails verification. Bytecode
directories are excluded.

Owner CLI (existing local catalog and `TULDOK_DATABASE_URL`):

```
python torch_runtimes.py inspect --data CATALOG --configuration configuration.json
python torch_runtimes.py register --data CATALOG --manifest manifest.json --expected-sha256 SHA
python torch_runtimes.py verify --data CATALOG --manifest-sha256 SHA
```

Inspection returns `manifest` plus its digest and measured totals; save that manifest
as canonical sorted compact JSON before registration. Registration never copies or
modifies Pumas packages. Runtime registration is infrastructure; training is a normal
approved project Run and must supply its own model/device/precision evidence.

The current recipe selects exactly `runtime`, `runtime_snapshot_sha256` and
`runtime_device`; device is `cpu` or `cuda`, with no automatic selection. Captured
material and custody specification carry one `torch_runtime` descriptor with
`schema_version`, `profile`, `catalog_id`, `manifest_sha256`, `manifest_bytes`,
`file_count` and `total_bytes`. The exact manifest and owner bootstrap are captured
under `runtime-bootstrap/torch-manifest.json` and `runtime-bootstrap/torch_runtime.py`.
The material environment is empty; the bootstrap constructs its closed device
and cache environment. Registry manifests require canonical JSON and bounded,
no-follow regular-file reads. The helper receives the same owner source through
a sealed descriptor, preserving process ownership without ambient import paths.

`torch_runtime.validate_descriptor`, `verify_descriptor`, `load`, and
`verify(manifest, checkpoint=...)` are the stdlib-only current contract operations.
`verify_descriptor` binds canonical manifest bytes and measured totals before
asset reads. They do not decode historical runtime representations. The offline
migration converter owns any obsolete source decoding.

The bootstrap requires Torch's float32 default and reports it. Model code remains
responsible for explicit tensors, float32 operations, optimizer update counts and
artifact evidence. Runtime unit fixtures establish identity and device policy;
they do not qualify actual CUDA training, CPU restore, or migration A2/A8.


Typed field evidence may use this runtime only through the current bound recipe
(schema 3, `external_model_evidence_recipe_v2`) with ordinary
`extension_field_policy_v1`. Its model/task/provider binding, exact field
population, fixed validation capabilities, bounded context and artifact
publication rules remain authoritative. CPU restore retains the same managed
runtime profile. Unbound managed model-evidence recipes, native source extensions
and the separate canonical field policy are unsupported. A fresh bound admission
rechecks the full installed manifest and exact descriptor against captured bytes;
cold inspection reads retained identities without model execution.

An ordinary managed `external_recipe_v1` may share the same current Project v2
snapshot as a bound trainer. This keeps fresh CPU restore and its typed Run
artifact inputs in the current Project contract. Bound evidence still requires
Project v2; unbound field-evidence recipes and other ordinary runtime profiles
are not admitted through this Project v2 path.

Explicit managed CUDA recipes may reserve1–1800seconds of execution. Ordinary
CPU recipes retain their600second bound. The neutral custody owner and recipe
admission share the CUDA maximum; operators still choose a smaller exact
per-attempt deadline. Exceeding the requested deadline stops/drains the attempt
and is not a numerical accuracy result. Installed-runtime verification before
leader creation retains its separate finite preparation allowance.
