# Optional Rheon field producer

The optional `adapters/rheon` package implements the producer-specific boundary;
no generic owner requires Rheon. It uses the existing external recipe, approval,
sole Runs supervisor, scientific field format, and artifact import. It neither
registers a second scheduler nor modifies lab/Rheon algorithms.

## Qualified source and controls

Initial native SHA256 is
`4e4e49f0e3febf5b11556c2a1daac3dc684e9fb9a9c3c742329d804a4913ceff`.
Lab commit is `e8a90bfef6b2955c502008ccc62443e29dd9f2ec`; Rheon commit is
`2209012bc5f902693d0f695ec1c2d854126af317`. The original receipt must bind these
identities and `cargo build --release --locked --manifest-path probes/trajectory/Cargo.toml`
with toolchain evidence. Source receipt bytes are retained unchanged.

Grid is an integer 8–32, frame count 1–2, and seed 0–2147483647. Jacobi is fixed.
Native timestep 1/60, density 1.25, solver thresholds, initial zero fields and
seeded forcing remain the original algorithm's constants. These are not editable
physical controls or claims of SI units. Defaults are 32/two frames/seed 100.
The recipe declares a 120-second wall bound and 16 MiB aggregate output bound.

## Public adapter interface

`project.assemble(binary, receipt, destination)` validates existing captured
inputs and creates a new directory containing `project.json`, `recipe.json`,
`generate.py`, `rheon-trajectory-probe`, and `build-receipt.json`. It returns the
project manifest, refuses overwrite, and never executes the producer. Inputs and
source are ordinary explicit project references; no invented input dataset is
introduced for the internally generated initial condition.

The standalone captured wrapper accepts `--native`, `--build-receipt`,
`--native-policy`, `--grid`, `--frames`, `--seed`, and `--output`.
`generate(...)` validates all inputs before spawning and returns its producer
receipt only after successful native exit, complete wire validation, and writing
all declared outputs. It requires an empty existing output directory. Publication
into durable completed Runs remains the Runs owner's separate responsibility.

## Native execution identity

The generic host supplies a captured `glibc_x86_64_no_preload_v1` policy through
`{native_policy: sourcepath}`. It binds source, loader, native library inventory,
fixed arguments and preload absence. The wrapper reads and hashes bounded regular
files without following final symlinks, then seals the exact native and loader
bytes into memfds. It executes the loader descriptor with cache disabled, the
explicit `/usr/lib/x86_64-linux-gnu` library path, and an empty glibc hwcaps mask.
It never changes source mode or executes a pathname after hashing different bytes.

At READY, before sending frame commands, the wrapper reads a bounded child mapping
inventory. Every file-backed mapping must match the device/inode of a hash-checked
native library or one of the two sealed descriptors. All required libraries and
both descriptors must be present. Anonymous/kernel vDSO/vvar mappings have no file
identity. The resulting map identities are retained as observations, not portable
file hashes. The captured policy supplies the corresponding content identities.

This is qualified for the reviewed native binary without dynamic plugins.
Trusted installation files and `/etc/ld.so.preload` absence must remain immutable
for the attempt; hostile administrators are outside the contract. The wrapper
only cleans up its immediate child on failure. Existing helper subreaping,
pidfds, bounded cancellation, and unknown fences own descendant cessation.

## Wire and lossless data

Native READY is one little-endian u32-length JSON envelope. Each `02` byte requests
one accepted frame: another JSON envelope followed by raw RHS and pressure f64,
three MAC velocity f32 arrays, then tracer f32. Final `00` requests stop. There
must be exactly the requested frames and no trailing bytes. READY controls, frame
indices/times, finite field values, bounded tracer, and native divergence/Courant
diagnostics are checked. Wire is limited to 4 MiB, native diagnostics to 64 KiB,
JSON messages to 64 KiB, and the wrapper's protocol observation to 100 seconds.

Array storage is X-fastest; NPY uses C-order `(z,y,x)`. RHS/pressure/tracer are
cell-centered. Velocity X/Y/Z respectively adds one sample to the X/Y/Z axis.
Wrapping adds only NPY headers; original element bytes, including signed zero and
f64 precision, are unchanged. RHS is preprojection, pressure solved, velocity
corrected and tracer advected. Native length/time/field units remain unspecified.
No simultaneous-stage interpretation is implied.

`fields.zip` contains a generic `scientific_field_sequence_v1` manifest, one
uncompressed NPY per field/frame, and exact original wire, build receipt and
producer receipt plus the exact captured native policy. The declared family binds scene/initial-condition convention,
grid and seed; frame count and build hash cannot create an independent family.
The generic parser also applies its canonical source/state protection.

Outputs are `fields.zip` (role `scientific_fields`), `wire.bin` (`native_wire`),
`producer-receipt.json` (`producer_receipt`), and `native-diagnostics.txt`
(`native_diagnostics`). Receipt fields bind controls, binary/build/policy/wrapper
hashes, original command bytes, wire bytes/hash, diagnostic hash, loaded mapping
observations, READY and frame reports, and qualification limits. An artifact's
role does not establish format validity or authorize import/review.

## Verification and limits

Focused tests include authored malformed-wire/format fixtures, immutable input
handling, recipe/project setup, family protection, and actual sealed-loader
32³/two-frame runs for seeds 100 and 101 when the pinned optional build exists.
Missing native prerequisites are explicit skips, never mocked acceptance.
Independent end-to-end qualification owns approved Runs completion, NumPy/native
cold checks, import, review, freeze, original download, restart, and cancellation.
This generation checkpoint does not qualify training, Pumas/GPU execution,
historical benchmark reproduction, or general scientific accuracy.
