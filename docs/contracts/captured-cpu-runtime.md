# Captured CPU Python runtime

`captured_cpu_python_v1` is an explicitly captured local CPython 3.12 CPU profile.
It adds no installation, scheduler, network isolation or hostile-code sandbox.
The runtime snapshot and reviewed recipe must remain unchanged for an attempt;
all code shares the local UID. `system_python` recipes keep their existing shape,
limits and behavior.

## Capture and authority

`runtime_snapshots.py inspect|create|verify --data CATALOG` is explicit local
administration. Inspection/creation takes a bounded JSON `--config`; creation also
requires `--expected-inventory-sha256 SHA --quiesced`. Source paths and package
entries are explicit. No package hooks, project imports or installations execute
during capture. Required package metadata and licenses remain present. Optional
unsupported components may be excluded only through recorded configuration.

The CLI requires an existing owner, exchanges a local one-use credential in
memory, and revokes the session on exit. Creation holds the existing Runs runtime
lease and catalog lock; an active application or retained queued/running/cancelling/
unknown attempt refuses creation. It never reconciles or cancels work implicitly.
Measured copying plus a declared free-space reserve must fit. External disk
writers remain outside this cooperative allocation guarantee.

The immutable content address is `runtime-snapshots/<manifest-SHA256>`. Source
files are streamed into private staging, compared with the reviewed inventory,
normalized to mode0400 (data) or0500 (ELF), synchronized and published without
replacement. An existing snapshot must verify before reuse. Filesystem content
is canonical; there is no mutable snapshot registry. Lost audit acknowledgements
remain visible and do not authorize replacing content.

## Manifest and descriptor

Canonical manifest JSON has `schema_version:1`, `profile`, `python_version`,
`packages`, `launch`, sorted `files` and `total_bytes`. Each file has relative
`path`, `bytes`, `sha256`, integer `mode` and `kind` (`elf` or `data`). Launch paths
name `python`, `loader`, `home`, `stdlib`, `dynload`, `packages` and ordered
`library_dirs`. Preserve relative native-library layout and qualify its contained
ORIGIN search paths. Undeclared files, links, special files, changed modes/bytes,
unsupported loader mechanisms and escaping references refuse execution.

Limits are 40,000 files, 512 MiB per file, 2 GiB total and 16 MiB manifest. These
are maximum bounds, not an allocation reservation. The recipe definition selects
`runtime: "captured_cpu_python_v1"` and `runtime_snapshot_sha256`. Resolution is
only beneath its bound catalog; browser clients cannot choose source directories.

Material adds `cpu_snapshot`, a bounded descriptor containing manifest identity,
owned root, catalog ID, file/byte counts, Python/package versions and launch paths.
The descriptor and the exact custody module SOURCE become captured inputs at
`runtime-bootstrap/snapshot.json` and `runtime-bootstrap/recipe_process.py`.
Bootstrap SHA256 binds the retained host identity. Cold validation never replaces
it with the currently installed helper source.

The existing material `runtime` remains the trusted system-Python host closure.
The recipe runtime and `cpu_snapshot` identify the target runtime. The UI displays
the target profile; the complete material remains available for review. Existing
recipes gain no default snapshot fields.

CPU recipes may capture at most 256 MiB of named inputs and 320 MiB across all
captured source, input and generated files. Each input remains at most 40 MiB;
source files remain at most 8 MiB and output limits remain 64 MiB. The complete
validated CPU descriptor/bootstrap and reserved launch shape select this policy;
an arbitrary descriptor field cannot enlarge a system-Python recipe. Legacy
system-Python capture limits remain 64 MiB. These are byte bounds, not promises
about resident memory while an optional reader expands or processes its inputs.

## Execution and evidence

The parent verifies the snapshot before launching custody. The helper checks
ordinary captures before READY, then polls cancellation during full snapshot
verification after GO and before forking. The custodied launcher verifies again
before starting captured Python. Snapshot hashing and traversal have a separate
60-second preparation budget; the CPU controller permits62 seconds for readiness.
The old profile retains10/12 seconds. Custodian GO revalidation precedes the child
wall timer; the declared child budget includes launcher checks, Python/package
initialization and recipe execution. Scientific timings use the original script's
own interval. Normal cancellation, child ownership, drainage and unknown-cessation rules
continue to apply.

Reserved `--cpu-launch` executes the captured loader/interpreter by path, with
fixed captured library search directories, disabled loader cache/hardware-capability
substitution and absent global preload. Path execution is explicitly cooperative,
not a claim that a hostile same-UID writer cannot race verification.

The captured child uses LANG=C, LC_ALL=C, PYTHONCOERCECLOCALE=0 and PYTHONUTF8=1.
This keeps UTF-8 Python text/filesystem behavior without uncaptured system locale
or gconv cache mappings. The trusted host retains its existing environment.

`--cpu-child` uses explicit captured PYTHONHOME and `-P -S -B`; validates initial
Python paths and module origins; adds only captured packages; imports NumPy/Torch;
checks versions, CPU-only Torch and actual native mappings; then invokes the
captured recipe. The canonical bounded `tuldok_cpu_runtime` stdout record retains
actual Python/package identity, import locations and mapped libraries. Standard
Run custody retains the stream and its hash. `.pth`, user-site and inherited Python
or loader overrides are excluded. CUDA, JIT/compiler/plugin execution and Torch multiprocessing are not
qualified by this profile. The required torch_shm_manager executable is captured
for normal Torch initialization; its presence alone is not helper-execution
qualification.

Torch's two synthetic modules, `torch.ops` and `torch.classes`, have pseudo
filenames rather than file origins. Only those exact names, exact defining class
identities and expected pseudo filenames are admitted; their defining modules
must be captured manifest files. Evidence records this provenance separately as
`virtual_modules`. Other relative module origins remain invalid. The bootstrap
record proves the observed initialization state, not continuous monitoring of
every import or mapping during arbitrary recipe execution.

Complete backup includes snapshot files. Historical completed Runs preserve their
original descriptor and specification after relocation; new execution resolves the
current snapshot root and requires fresh approval. Hash custody is not scientific
acceptance. Actual CPU computation, checkpoint compatibility, numerical gates and
UI workflows require their own qualification evidence.
