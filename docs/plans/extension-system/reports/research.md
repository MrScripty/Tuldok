# Tuldok extension system research and design recommendation

Date: 15 October 2026

## Recommendation

Build a small, manifest-driven extension seam around the ownership boundaries already chosen for Tuldok. Use declarative discovery and configuration, captured executable source, explicitly qualified local runtimes, and execution through the existing Runs owner. Start with trusted local Python extensions and a CPU vertical slice. Keep GPU execution inside the numerical worker; qualify a GPU runtime separately.

The aim is practical: after implementing this seam once, changing a physics model's input fields, output fields, training procedure, or solver-stage sequence should normally require a new extension/model/task version and fresh validation, without editing Tuldok's application owners.

This is a research recommendation, not a claim that the extension ABI, runtime, numerical example, or performance has been implemented or measured. The research found useful precedents, but does not recommend adopting napari, VS Code, pluggy, Arrow, Wasmtime, or another framework as Tuldok's foundation.

The seven priorities are:

1. Separate extension discovery, installation, validation, and execution.
2. Define narrow versioned contributions and explicit stage contracts.
3. Choose local execution and dependency boundaries before promising isolation.
4. Separate multimodal semantics from array storage and transport.
5. Keep UI contributions mostly declarative.
6. Preserve exact authority, immutable provenance, and historical interpretation.
7. Ship an authoring kit and conformance tests with the first real extension.

The most important proof is change locality: an independently packaged extension must change its I/O and stage sequence, survive removal and upgrade, and leave existing image/text/audio and unrelated scientific workflows usable.

## Existing architecture and the precise gap

The source review is pinned to Tuldok commit f99182c03da1e070081718ef6829eaeac3c82640, the supplied PR62 design baseline. That design identifies application main f58880df as its implementation baseline. The research does not treat the design as implemented product behavior.

The selected architecture already provides most of the right boundaries:

- Pipeline is the sole editable execution-recipe owner.
- Experiments own trial membership, budget and selection intent.
- Runs owns attempts, supervision, cancellation, artifact custody and publication.
- Access owns current authority, review, grants and protected-data exposure.
- Task/model/trainer/evaluator adapters own numerical and semantic meaning.
- Projects and RuntimeSnapshots own captured source and runtime identity.
- HTTP, CLI, MCP and browser views project those same owners.
- Passive observation remains operator opt-in and cannot become required execution machinery.

The design explicitly anticipates task/model/adapter versions for changed fields and stages. It does not freeze a universal tensor/operator API. It also says the composition root supplies supported adapters, without a persistent marketplace. Current external recipes already have an inert preview/preflight and captured executable path, but their public graph is input → execute → output. Consequently, a general independently installable extension contract is still an additional design decision. Capability negotiation for agent operations is a useful parallel, not an existing plugin loader. [Tuldok architecture](https://github.com/MrScripty/Tuldok/blob/f99182c03da1e070081718ef6829eaeac3c82640/docs/plans/end-to-end-model-development/reports/architecture-design.md), [evidence contracts](https://github.com/MrScripty/Tuldok/blob/f99182c03da1e070081718ef6829eaeac3c82640/docs/plans/end-to-end-model-development/reports/evidence-contract-design.md), [external recipes](https://github.com/MrScripty/Tuldok/blob/f99182c03da1e070081718ef6829eaeac3c82640/docs/contracts/external-recipes.md).

“Without core edits” should therefore mean adding content and behavior within qualified extension points after that seam exists. A new security class, runtime family, executable browser capability, or transport primitive can still require an intentional core change. Promising that arbitrary future behavior never needs core work would make the contract meaningless.

## Priority 1 Separate discovery from activation

### Decision

Discover bounded static manifests from explicitly configured extension locations or package inventories. Reading the catalog, opening a project, editing a model, and running preflight must not import extension code, load weights, run a probe, invoke a build backend, or install dependencies.

A package manifest should identify its immutable source material and declare contributions, required host contracts, runtime requirements, permissions, bounds, licenses, and declarative UI descriptors. A package may advertise contributions that are currently unavailable; the UI should say why.

Maintain distinct states:

- Found: static metadata can be read.
- Valid: manifest and referenced material pass inert checks.
- Enabled: the operator has selected the extension for use.
- Available: required host and qualified runtime contracts are present.
- Admitted: a particular exact execution has passed normal authority and material checks.
- Running/completed/failed: ordinary Run lifecycle states.

Do not collapse these into “installed means trusted” or “registered means authorized.”

### Evidence and alternatives

napari's npe2 manifest separates declared contributions from Python callables, and activation occurs when a contribution is requested. Python entry points advertise components through distribution metadata; resolving their object reference imports Python. These are useful reasons to keep discovery separate from loading. They do not provide a sandbox. [napari manifest reference](https://napari.org/stable/plugins/technical_references/manifest.html), [PyPA entry points specification](https://packaging.python.org/en/latest/specifications/entry-points/).

For Tuldok, a captured project extension is the best initial delivery format because it fits existing source/import closure and recipe custody. A wheel plus an entry-point group can be a later packaging convenience. It must not bypass source capture or silently expand the host's site-packages.

Start with a bounded in-memory contribution catalog assembled by the composition root from enabled manifests. No daemon, remote marketplace, automatic download, or second database is needed.

Package installation is a separate execution/supply-chain step: generating Python package metadata can invoke a build backend, and launching a candidate interpreter can run startup hooks. Read known metadata files directly during inert discovery. Source hashes prove identity, not publisher trust; any future signing policy needs its own trust and revocation model. [pip build-system interface](https://pip.pypa.io/en/stable/reference/build-system/), [Python startup customization](https://docs.python.org/3/library/site.html).

### Small experiment

Create three manifest-only fixtures: valid but missing runtime; invalid version; and a package whose Python import raises or writes a marker. Listing, previewing, and preflight must never trigger the import. Record startup cost and prove unrelated extensions still appear when one manifest is invalid.

## Priority 2 Define contributions and lifecycle contracts

### Decision

Treat “extension” as a package of narrowly typed contributions, rather than a class that receives the whole application object.

Initial contribution families should be:

| Contribution | Owns | Must not own |
| --- | --- | --- |
| Task | Input/target/output meaning, comparison rules, clocks and applicable metrics | Run admission, dataset review or universal scientific validity |
| Reader or derivation | A named captured format to a named task representation | Arbitrary filesystem discovery or implicit conversion on inspection |
| Model | Computation configuration, source closure, preprocessing and output policy | Fitted weights or a second copy of recipe training controls |
| Trainer | Parameter schema, supported task/model tuples, lifecycle and capture capabilities | Queue/process custody or hidden runtime installation |
| Evaluator | Metric definitions, acceptance protocol, field/stage semantics and output tolerances | Relabeling byte integrity as numerical acceptance |
| View descriptor | Bounded queries, controls and renderer bindings | Direct database/filesystem access or hidden model execution |

Use a small static contract vocabulary for describe/validate/prepare/result schemas; numerical operations execute only through admitted Runs. These are conceptual seams, not proposed final public method names. Some work can remain one captured recipe with internal stages.

Keep three version domains separate: extension protocol version; semantic task/model/evaluator versions; and package/source/runtime content identities. A package version alone cannot establish compatibility.

### Stages

A stage needs a namespaced ID, semantic version, input/output ports, applicable clock, resource requirements, and failure policy. A stage sequence is an immutable part of selected trainer/recipe material. Stage outputs record producing stage and exact input lineage.

Initially let the selected trainer integration derive a finite stage sequence. Render it read-only or as bounded trainer-qualified options. This preserves PR62's workflow-versus-model distinction. Do not add a universal node editor merely to expose stage extensibility.

One Run may execute prepare → fit → infer → evaluate internally. A stage that requires different inputs, permissions, runtime, or resource envelope should be a separately admitted Run connected by verified artifacts. Neither a progress event nor an extension callback may start an unapproved child attempt.

Model operations within a numerical worker should usually be ordinary local function calls. Sending every optimizer step or solver stencil through host RPC would add cost and coupling without improving ownership.

### Evidence and alternatives

pluggy demonstrates explicit hook specifications, multiple implementations, validation and ordering choices. That is a useful authoring pattern for trusted Python integrations. Its hook dispatcher does not solve cross-process transport, custody, permissions, or GPU lifecycle. If used, keep it inside a trusted worker or narrowly reviewed host component. [pluggy documentation](https://pluggy.readthedocs.io/en/stable/).

For provider selection, resolve one explicit compatible provider. Avoid implicit “first plugin wins,” import-order precedence, monkey-patching core objects, or arbitrary around-everything hooks. Broadcast notifications can have multiple observers; an executable task provider should not be selected by observer ordering.

### Small experiment

Package a task, trainer, evaluator and three-stage workflow independently. Change one input port and add a stage in a new version. Prove the old material still opens, new drafts validate against the new contract, incompatible bindings fail before admission, and no core owner file changes.

## Priority 3 Choose execution and dependency boundaries honestly

### Recommended first boundary

Use trusted local Python/native numerical code in existing captured runtimes, launched and supervised by Runs. An extension does not get its own supervisor or permanent background server.

Prefer one worker process per admitted numerical attempt. Reuse a runtime environment by immutable identity where the current runtime owner supports it; do not require a separate environment for every package if their exact dependencies are compatible. Incompatible dependency closures must never be resolved by mutating the host environment.

Keep the application process free of extension numerical imports, GPU initialization and checkpoint deserialization. The installed host interpreter and its dependencies should not become a shared extension dependency pool.

| Option | Appropriate role | Main limitation | Recommendation |
| --- | --- | --- | --- |
| In-process Python hooks | Small reviewed host adapters or worker-internal hooks | Dependency conflicts, shared state, native crashes and broad authority | Limited use only |
| Captured out-of-process Python/native | NumPy/Torch/scientific libraries and local CPU/GPU execution | Process separation alone is not security containment | First execution path |
| Container or separately restricted OS identity | Stronger filesystem/network/resource boundary where operationally supported | Additional platform, storage, driver and custody qualification | Separate future profile |
| WASM/WASI | Small portable transforms or validators that fit its runtime imports | Existing native/GPU stacks and libraries need separate compatibility work | Optional later target |

VS Code's separate UI/workspace/remote extension hosts show why runtime location and UI location are different concerns. Browser extensions cannot simply run arbitrary native executables. Wasmtime shows capability-based filesystem access through WASI; it does not establish that a particular Tuldok Python/CUDA stack can run there. [VS Code extension hosts](https://code.visualstudio.com/api/advanced-topics/extension-host), [VS Code web extensions](https://code.visualstudio.com/api/extension-guides/web-extensions), [Wasmtime security](https://docs.wasmtime.dev/security.html).

### Trust and resource limits

Current external recipes are trusted same-user code. Clearing environment variables, withholding the application DSN, closing file descriptors, or creating a virtualenv does not remove same-user filesystem/network/database authority. Describe this plainly in approval material. A manifest permission declaration is review information until an actual boundary enforces it. PostgreSQL peer/trust authentication can also make “no DSN given” a poor security assumption. [Tuldok actor contract](https://github.com/MrScripty/Tuldok/blob/f99182c03da1e070081718ef6829eaeac3c82640/docs/contracts/actors.md), [PostgreSQL peer authentication](https://www.postgresql.org/docs/current/auth-peer.html), [trust authentication](https://www.postgresql.org/docs/current/auth-trust.html).

Distinguish dependency isolation, crash containment, process custody, and adversarial sandboxing. Test and advertise each independently. Wall-time and output limits are not aggregate RSS, CPU, GPU-memory or disk quotas.

Runtime requirements should include interpreter/ABI, OS/architecture, package and native-library closure, accelerator backend, and supported precision. Exact package locks help provisioning but do not qualify drivers, hardware kernels, floating-point reproducibility, or runtime immutability. Python virtual environments are not generally portable directories. [Python venv documentation](https://docs.python.org/3/library/venv.html), [PyPA reproducible-environment specification](https://packaging.python.org/en/latest/specifications/pylock-toml/).

### GPU

Keep model, optimizer, native solver and device buffers in the same numerical worker initially. The host exchanges metadata and persisted CPU-readable evidence. A CUDA/ROCm/Metal label is not a qualified runtime: require actual supported hardware/backend/driver and producer-consumer receipts.

Do not silently fall back from GPU to CPU or change precision. Offer a separately declared compatible profile, and create new material if selected. Automatic fallback is acceptable only when its exact semantics, resource costs and provenance are already part of the approved profile.

### Small experiment

Run two intentionally incompatible numerical dependency closures side by side, then test a native crash, hang, descendant process, cancellation and controller loss. Existing Runs custody must reach its documented terminal or fenced-unknown state. Separately qualify one actual GPU training/inference profile; until then report GPU unavailable.

## Priority 4 Separate multimodal semantics from transport

### The common envelope

A port should bind a semantic type ID/version/digest, artifact identity, encoding/version, shape and dtype where applicable, coordinate/clock metadata, validity/mask policy, provenance and access classification.

The common envelope must allow new extension-owned semantic types without teaching the core their numerical meaning. Unknown types can remain opaque verified artifacts. They must not automatically become comparable metrics, renderable tensors or accepted model inputs.

For a first version, require an exact known semantic contract intersection. A generic JSON schema proves structure, not that two grids, tokenizers, pressure gauges or loss definitions mean the same thing. Avoid an ambitious schema-subsumption engine.

### Modality contracts

| Data family | Required meaning beyond bytes and shape | Typical silent failure to reject |
| --- | --- | --- |
| Image | Encoded versus decoded identity; spatial/channel axes; color space; channel order; alpha; dtype/range; transform history | RGB/BGR swap, lossy downcast, unrecorded resize or normalization |
| Text | Raw text versus tokens; encoding/normalization; tokenizer/vocabulary identity; sequence boundaries; masks; truncation; offset convention when present | Same integer IDs with different vocabularies; offsets in different coordinate systems |
| Audio | Encoded versus decoded identity; sample rate; time origin; channel layout; amplitude scaling; valid lengths; resampling policy | Implicit resampling, channel remixing or normalized-amplitude change |
| Mesh | Positions, connectivity, attribute attachment domain, index validity, frame/units/transform; explicit stronger topology guarantees | Vertex attribute treated as face-corner data; meters interpreted as centimeters |
| Point cloud | Point coordinates/frame/units; feature meaning; stable IDs when temporal identity matters | Reordered points treated as matching particles |
| Volume or physical field | Named spatial/component/time axes; grid geometry; centering; frame; units; mask; stage and boundary/gauge conventions where relevant | Cell/face confusion, transposed axes, wrong stage or unmatched physical time |

xarray's dimensions and coordinates are a useful conceptual distinction, while arbitrary attributes are not automatically interpreted. OpenUSD's mesh schema distinguishes connectivity and interpolation domains; basic mesh validation does not establish manifoldness or physical suitability. glTF and OpenUSD illustrate why coordinate and unit conventions must travel with geometry. These are semantic lessons, not proposals to use those object models as the Tuldok ABI. [xarray data structures](https://docs.xarray.dev/en/stable/user-guide/data-structures.html), [OpenUSD mesh](https://openusd.org/release/api/class_usd_geom_mesh.html), [OpenUSD points](https://openusd.org/release/api/class_usd_geom_points.html), [glTF coordinates and units](https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html#coordinate-system-and-units), [OpenUSD linear units](https://openusd.org/release/api/group___usd_geom_linear_units__group.html).

Media and tokenizer libraries expose useful conversion operations, but convenience decoding/resampling must not silently change scientific or evaluation inputs. Pin decoder/tokenizer behavior and record transforms as explicit versioned material. [Hugging Face dataset features](https://huggingface.co/docs/datasets/v4.8.4/about_dataset_features), [audio processing](https://huggingface.co/docs/datasets/v4.8.0/audio_process), [tokenizer interface](https://huggingface.co/docs/transformers/main_classes/tokenizer).

### Data plane choices

Use a small bounded JSON control plane and artifact/file references for large values. Preserve current exact inventory, flat output names and profile limits. Do not embed full volumes or repeated checkpoint predictions in JSON, stdout, MCP messages or database rows.

Start with already supported array encodings and owner-controlled captured files. Do not add a format just to make a plugin example look generic. Numeric NPY readers should reject object-dtype/pickled arrays and validate shape/size bounds before materialization; disabling pickle is a baseline parser control, not a general malformed-file sandbox. [NumPy load](https://numpy.org/doc/stable/reference/generated/numpy.load.html).

| Mechanism | Good fit | Important boundary |
| --- | --- | --- |
| Captured/published files and memory mapping | Local durable inputs, checkpoints and evidence | Define ownership, immutable publication and supported readers |
| Arrow IPC | Cross-process tabular/ragged data where needed | Semantic type still needs an acknowledged Tuldok contract |
| Arrow C Data Interface | Same-process columnar interoperability | Explicitly not cross-process transport or persistence |
| DLPack | Worker-internal dense tensor exchange between compatible libraries | Shared lifetime/device/stream/mutation rules; not a general IPC protocol |
| Zarr-style chunked arrays | Large slice-oriented volumes/trajectories if existing files prove inadequate | Codec, chunk, shard, atomicity, inventory and access policies need qualification |

Arrow's IPC and C interfaces solve different boundaries. DLPack exposes dense strided array/device interchange and requires correct stream handling; it does not carry task semantics. Zarr's chunk/shard separation is useful for partial reads but is not directly compatible with assuming every chunk is a separately declared flat Run output. [Arrow C interface](https://arrow.apache.org/docs/format/CDataInterface.html), [Arrow IPC](https://arrow.apache.org/docs/format/Columnar.html), [DLPack specification](https://dmlc.github.io/dlpack/latest/python_spec.html), [Zarr arrays and sharding](https://zarr.readthedocs.io/en/stable/user-guide/arrays/).

A shared-memory optimization must specify owner, reader permissions, lifetime, release/crash cleanup, size validation, mutability and synchronization. Do not advertise “zero-copy across plugins” before measuring the complete path. CUDA IPC is a separate mechanism with lifecycle constraints; it should not be the first path.

### Small experiment

Measure end-to-end preparation, hashing, transfer, decode, computation, publication and bounded slice inspection for representative image batches, ragged token batches, audio windows, meshes and 3D fields. Include cold and warm runs, peak memory, retained bytes and cancellation cleanup. Test wrong axes, sample rate, tokenizer, units, centering, masks and stage IDs. Incompatible meaning must fail before numerical execution or comparison.

## Priority 5 Use declarative UI contributions first

### Decision

Let extensions supply names, parameter schemas, help text, supported actions, stage summaries, metric definitions and bounded view descriptors. Core renderers handle common parameter forms, curves, tables, image overlays, text spans, audio waveforms/spectrograms and scientific slices only where those renderers actually exist.

A descriptor must bind an exact query contract, semantic type and renderer version. An unavailable renderer produces an explicit unsupported view and a verified download when permitted. It must not coerce an unknown field into a misleading generic chart.

Custom browser JavaScript should be a separate later contribution class, with a clear origin/isolation boundary, content-security policy, narrow validated message bridge, no arbitrary network or filesystem access, and explicit compatibility tests. Custom UI must use the same authorization and exposure owners as ordinary clients.

VS Code demonstrates declarative contributions as well as a separate webview model with messaging and security requirements. This is a reason to keep simple views declarative and treat executable views as a separate commitment. [VS Code web extensions](https://code.visualstudio.com/api/extension-guides/web-extensions), [webview security](https://code.visualstudio.com/api/extension-guides/webview#security).

### Small experiment

Using only descriptors, render one classifier result and one 3D field pair with stage/time metadata, shared reference/prediction scale and a separate error scale. Verify agent queries and browser views select the same evidence. Add a novel field type and prove the fallback is honest. Do not implement a custom webview unless this experiment exposes a concrete unmet requirement.

## Priority 6 Preserve authority and historical interpretation

### Decision

An enabled extension may contribute capabilities; it cannot mint authority. All external execution remains bound to the exact reviewed material and existing one-use grant rules. Discovery, UI buttons and MCP availability never override Access.

Include the extension manifest, task/model/trainer/evaluator definitions, code/import closure, dependency/runtime identities, resolved stage plan, conversion policies, inputs, parameters and resource/permission envelope in exact executable material. Reuse owner hashing and persistence rules rather than adding a second identity service.

Availability should distinguish unsupported contract, disabled extension, missing runtime, denied authority and temporarily unavailable device. Permission changes and capability changes should be checked at normal owner boundaries.

Upgrades install new immutable package material side by side. Existing Runs and trials remain pinned to their original interpretation. Opening history must not execute the latest plugin, auto-migrate artifacts, reinterpret old output or retrain a model.

Keep structural artifact/evidence readers host-owned and bounded. Unknown historical semantic types stay opaque. Where custom semantic evaluation requires executable code, make it a separately admitted evaluator operation; do not sneak execution into a GET/query/viewer request. The exact split between host generic validation and extension-specific semantic checks needs to be resolved before freezing the ABI. A useful first split is host-owned structural validation and bounded projections over declared primitive representations, with derived numerical values produced by the admitted evaluator. This allows a new task to reuse curves, field slices or token rows without running extension code when someone inspects history. It does not make an arbitrary novel representation automatically inspectable.

Disable/uninstall should stop new selection/admission and preserve the material needed to inspect existing evidence. Deleting referenced material is an owner lifecycle decision, not a package-manager side effect.

Do not deserialize model objects to draw a chart. Even restricted PyTorch weight loading has a narrower guarantee than general code safety. Prefer data-only weight formats when compatible, and perform reconstruction inside the qualified worker. [PyTorch serialization security](https://docs.pytorch.org/docs/stable/notes/serialization), [Safetensors documentation](https://huggingface.co/docs/safetensors/index).

Protected split membership and whole-artifact population classification must apply equally to extension queries, previews, downloads, caching and export. An opaque NPZ/ZIP is not an exemption. Optional observer output cannot replace required audit or prove absence of legacy clients. These are already explicit concerns in PR62 and should remain invariant. [Tuldok evidence and compatibility design](https://github.com/MrScripty/Tuldok/blob/f99182c03da1e070081718ef6829eaeac3c82640/docs/plans/end-to-end-model-development/reports/evidence-contract-design.md), [implementation handoff](https://github.com/MrScripty/Tuldok/blob/f99182c03da1e070081718ef6829eaeac3c82640/docs/plans/end-to-end-model-development/reports/implementation-handoff.md).

### Small experiment

Run with version A, enable version B with changed I/O and evaluator meaning, then remove B. Confirm A's retained evidence remains readable without importing B. Tamper with a source, manifest, weights, runtime or output byte; each must fail at its owned verification boundary. Change an unconsumed approved material and show the old grant cannot launch it.

## Priority 7 Make third-party authoring a tested product

### Decision

Publish a small authoring SDK only after the first independent extension exposes the stable seams. The SDK should be a lightweight protocol/types/helper package; it should not require importing the application, starting PostgreSQL, or installing a preferred training framework merely to validate a manifest.

Provide:

- A minimal captured-project template and a complete worked extension.
- Versioned manifest/semantic schemas and checked examples.
- A command that performs inert validation.
- A separate explicit smoke/conformance execution command.
- Helpers for bounded progress, checkpoint descriptors and final evidence inventories.
- Documented parameter, clock, comparison and omission semantics.
- Runtime preparation and troubleshooting instructions.
- Compatibility matrix and a machine-readable conformance result.
- A migration example showing one changed input and one added stage.

The author should implement numerical behavior and task meaning. The host should supply capture, admission, cancellation, custody, common queries and basic presentation.

Test untrusted manifests and malformed artifacts as parser inputs. That does not make executable extension code untrusted-safe. Keep those threat models separate.

### Minimum conformance suite

1. Discovery remains inert; duplicate IDs, unknown versions, external schema references and excessive sizes fail boundedly.
2. Exact supported contract intersections resolve deterministically; no provider-order fallback.
3. All required material is captured; no live checkout, model cache or undeclared download is needed.
4. Every parameter is validated without coercion; source/model/I/O/stage changes invalidate dependent material.
5. No code execution occurs through open, edit, preflight, query, view or export inspection.
6. Bad input shape/type/semantics fails before training; explicit conversions create new provenance.
7. Progress is bounded and provisional; it cannot declare completion or nominate undeclared artifacts.
8. Required evidence omission fails publication; optional omission has an explicit reason.
9. Native crash, cancellation, descendants, controller loss and ambiguous acknowledgement preserve Runs custody rules.
10. Checkpoint/probe/stage/clock/input identities cross-check; wrong tokenizer/class order/grid/units is rejected.
11. CPU and each advertised accelerator profile pass actual producer and fresh-consumer tests.
12. Upgrade, disable, removal, backup/restore and old/new clients preserve truthful historical behavior.
13. All views/queries/downloads/exports enforce current authority and protected-population rules.
14. Removing the extension leaves unrelated tasks usable.

## A concrete first extension

### Proposed subject

Use a small three-dimensional scalar-field surrogate extension. A diffusion/heat-field example makes geometry, input channels, stage changes and physical clocks concrete without depending on a particular external solver repository.

This is a worked specification to implement and measure, not an executed simulation or a claim of physical qualification. Reuse a real permitted captured dataset when available; generated reference data would be a separately authorized recipe.

Call the illustrative package tuldok-field-surrogate. Its first profile is CPU-only. Optional CUDA support remains unavailable until a separately qualified runtime passes its gate.

### Package contents

- manifest.json: immutable package identity, host contract requirements and contributions.
- task.json: scalar field input/target/output semantics and allowed comparisons.
- model.json: bounded model options, captured source/import closure and preprocessing/output policy.
- trainer.json: closed parameters, supported task/model/profile tuples and stage plan.
- evaluator.json: exact metric definitions, tolerances and explicit limits of the claim.
- views.json: generic curve and 3D slice descriptors.
- src/: captured reader, trainer, inference and evaluator sources.
- fixtures/: small permitted input/output artifacts and negative conformance cases.
- dependency/runtime requirements and licenses.

This is a packaging sketch. Final paths, wire names and schemas should follow the repository's established naming conventions during implementation.

### Input and output contract

An input member binds an immutable source case/family, initial scalar field, grid geometry, material coefficient, boundary policy, target time and reference target when evaluation requires one.

For the first qualified subset:

- Field array has explicit little-endian numeric dtype and declared z,y,x axis order.
- Grid declares origin, spacing, cell centering, coordinate frame and spatial units.
- Scalar field declares its physical unit, mask policy and stage.
- Material coefficient and timestep have explicit units and admissible ranges.
- Physical target time and optimizer update are separate clocks.
- Boundary conditions are part of task identity; no generic “physics” default.
- Family-connected train/validation/test membership is frozen before deriving windows.
- Fitted normalization records exactly which fitting members produced its statistics.

The output contains predicted field, bounded metric rows, fixed-probe observations and retained checkpoint descriptors under exact declared output names. Predictions bind case, grid, stage, time, mask and model/checkpoint identities. Numerical acceptance is evaluator-owned. A low value error alone does not establish physical correctness.

### First lifecycle

1. Inert discovery validates the package and reports supported contracts and missing runtime requirements.
2. A separately prepared qualified CPU runtime becomes available.
3. A reader/derivation Run, if needed, maps permitted frozen source material into the trainer's exact representation.
4. Pipeline binds the task, model, trainer, evaluator/profile, inputs and runtime; it resolves all defaults and outputs before material hashing.
5. Normal review/grant/admission applies.
6. The numerical worker executes prepare → fit → infer → evaluate inside the approved envelope. Runs remains the only process/custody owner.
7. The producer closes its exact outputs; Runs verifies custody/inventory and host structural checks. Task-specific evaluator work is retained through its admitted execution.
8. The browser and agent use the same bounded evidence queries; generic views show matched field slices and declared errors.
9. Packaging retains weights, reconstruction/preprocessing/source closure and semantic/runtime contracts.
10. A separately admitted fresh consumer uses only package, compatible runtime and permitted probes; it verifies expected outputs under owned tolerances.

The actual first implementation can omit training if the smallest useful task is an inference/evaluation adapter around a captured model. However, claiming the model-development extension path requires a later real fit/checkpoint/probe gate.

### Deliberate second version

Change the model from initial-field-only input to initial field plus a spatial source field and boundary mask. Add a named boundary-enforcement stage after inference.

Expected effects:

- New task/model/trainer and source identities where meaning or implementation changes.
- New input and parameter validation, model reconstruction and output-policy binding.
- New exact stage material and comparison compatibility decisions.
- New preflight and execution approval.
- No change to Pipeline, Runs, Access, Experiment ownership or process supervisor.
- No core numerical code for source terms or boundary enforcement.
- Existing version-A Runs retain their original stage and input interpretation.
- Raw predicted output and post-boundary-enforcement output remain separately identifiable; corrected success cannot be presented as raw-model success.

Passing this A/B change is the central extension-design acceptance test. A “hello world plugin” alone would not prove the user's actual requirement.

### Multimodal co-tests

Do not build a second numerical example for every modality before proving the seam. Instead, add small contract/conformance fixtures for existing image/text/audio workflows and proposed mesh/point-cloud contracts. They should exercise differing ports, ragged lengths, sample clocks, tokenizers and geometry. These fixtures prove the envelope does not assume dense 3D arrays; they do not claim all modality-specific training integrations are complete.

## Experiments that should decide the design

All entries below are proposed work. No performance number or pass result is asserted.

| Experiment | Evidence to collect | Decision it unlocks |
| --- | --- | --- |
| Inert discovery and malformed package | Import/write/network markers remain absent; bounded rejection; extension-specific failure | Manifest mechanism and trust states |
| Independent A/B field extension | Changed I/O and stage order with no core owner changes; old evidence still readable | Contribution and semantic contract adequacy |
| Dependency conflict and native failure | Exact runtime inventories, crash/cancel/descendant/unknown-state receipts | Runtime/process boundary |
| Representative payload paths | Cold/warm latency, copies, peak RAM, hashing/publication cost, slice latency | Files first versus Arrow IPC/shared memory/chunking |
| Real local accelerator profile | Device/backend/driver identities, numerical tolerance, synchronized timings, crash cleanup | Whether GPU may be advertised |
| Declarative UI only | Authoring effort, honest unsupported fallbacks, browser/agent evidence parity | Whether executable UI is actually needed |
| Fresh consumer and upgrade/removal | Complete package closure, tamper failures, deterministic or tolerance-bound output, old/new compatibility | SDK stability and reproducibility claims |

Choose payload sizes from actual user workloads and current supported resource profiles. If representative data cannot fit today's explicit limits, record that gap and qualify a new profile. Do not silently widen limits for a demonstration. Choose service targets with the user before optimizing; arbitrary benchmark thresholds are not architecture evidence.

## Decisions to record before implementation

The following are still genuine choices:

1. Exact first extension contribution subset and the minimum supported author workflow.
2. Whether enabled packages are configured project-by-project, installation-wide, or both, and which owner controls enablement.
3. Host structural validation versus task-specific executable evaluation, including how new semantic queries stay inert.
4. Whether stage variation remains trainer-derived or needs bounded user-editable composition.
5. Initial artifact encodings, shape/type constraint vocabulary and what stays opaque.
6. Supported operating systems and runtime profiles, with an explicit accelerator qualification matrix.
7. Trust statement for same-user code; whether stronger containment is a requirement for the first release.
8. Numerical reproducibility policy: exact bytes, exact values, or declared tolerance by operation/runtime.
9. Supported version overlap, historical-reader retention and removal policy.
10. Whether custom executable UI is needed at all.

These decisions should become a short architecture decision record with owners and acceptance tests. They do not require choosing a marketplace, universal graph language or plugin framework first.

## Research and implementation boundary

Completed here:

- Read the six pinned Tuldok architecture/contract sources.
- Compared primary official precedents for discovery, hooks, runtime hosts, multimodal semantics, tensor/columnar interchange, UI extension boundaries and serialization.
- Recommended a first boundary and an experiment/conformance plan.
- Worked through one substantive changing-I/O/changing-stage extension design.

Not established by this research:

- Runtime or sandbox qualification.
- GPU availability.
- A final plugin ABI or public manifest schema.
- Measured transfer or extension-authoring performance.
- Executed numerical results or correctness.
- An implemented independently installable extension.

Recommended next deliverable: the extension decision record plus a small independently packaged CPU field extension and its A/B conformance receipts. This is the shortest path from a plausible plugin design to evidence that Tuldok can evolve with the user's models.

