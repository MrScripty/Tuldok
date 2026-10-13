# P5a verification — captured CPU comparison

Candidate branch: `feature/scientific-cpu-comparison-20261013`, based on qualified
PR49 `c7c696b`. The actual model/UI workflow passed; final full regression and hosted CI
remain pending. No merge or deployment.

## Runtime and native prerequisites

The locked parallel build succeeded against the pinned lab/Rheon sources, using
Rust/Cargo 1.92.0. Source trees and Cargo.lock remained unchanged; all 18 cached
registry archives matched their lock checksums after the explicit dependency
fetch. The offline build produced a 1,063,328-byte binary with SHA256
`583c939548d68ec7b25cf60bb9434ca1416f28ab6c06b3cad68a1aaf10b344db`.
[Build receipt](p5a/parallel-receipt.json) and adjacent logs retain the evidence.

The corrected CPU snapshot contains 21,088 files / 880,817,080 bytes and has
manifest SHA256
`cc54ef199fc192b70f702e85dda70bfc8697bf3220373ae9f031afd8b237f0a7`.
It was fully verified before atomic publication. No Python packages were installed.
The original failed snapshot remains preserved outside the final QA catalog.

The [real runtime probe](p5a/runtime-qualification.json) passed through production
preflight, explicit QA owner approval and Runs custody. It executed forward and
backward arithmetic under captured CPython 3.12.14, NumPy 2.5.4 and Torch 2.8.0+cpu;
compared exact NumPy payloads with an independent arithmetic oracle; saved and
weights-only reloaded a checkpoint; cancelled an initialized CPU process with
confirmed drainage; and reopened exact completed artifacts. All 24 observed
startup and post-computation native mappings belonged to captured ELF inventory.
Independent review verified custody, log and artifact hashes. This authored
computation is runtime qualification, not historical model/scientific acceptance.
The original installation was not physically removed during qualification.

Failed bootstrap attempts remain retained and drained. They exposed uncaptured
locale mappings, an overbroad exclusion of Torch's required shared-memory helper,
and synthetic module origins. The final profile uses a fixed C locale with Python
UTF-8, captures required helper bytes, and admits only the exact two known Torch
synthetic objects with captured defining-module provenance. Ordinary module and
native mapping checks remain strict. Torch multiprocessing is not qualified.

## Contract and review checks

- 22 helper tests pass, independently repeated; cancellation during slow GO
  verification drains without starting a child.
- 12 snapshot owner tests pass, including authority/lease refusal, drift, capacity,
  partial capture, uncertain audit acknowledgement and prepublication verification.
- 4 CPU material tests pass, including old omitted-profile shapes, Unicode paths,
  selector bounds and retained bootstrap/host identity.
- 10 optional adapter tests pass with explicit real native inputs, including
  sealed READY/STOP and failure cleanup. No fixture is model acceptance.
- 8 retained recipe-contract and 11 external Runs checks passed before the last
  helper bootstrap refinements; the final full regression will supersede them.
- Affected JavaScript syntax/controller tests, Python syntax, plan contract and
  whitespace checks pass. Independent source/numerical review found no remaining
  blocker. No static type checker or Standards Engine certificate is claimed.

## Actual model/UI qualification

The real browser passed four gates in
`build/qa/workspace-cpu-comparison/run-VBdQCB`. Run
`0cc3ef6b5f9e460f873c8eda1ba3d525` completed with confirmed drainage in
542.157760 seconds (recorded started-to-finished wall time).
[Browser receipt](p5a/browser-receipt.json), [independent cold audit](p5a/cold-report.json),
four desktop/narrow screenshots and [candidate source hashes](p5a/source-files.json)
are retained here. Six artifacts were downloaded through HTTP and checked against
the public inventory; restart returned identical artifact bytes and material hash.
Project sources and original checkpoint/freeze bytes remained unchanged.

The unchanged CPU comparison executed all 12 timed trajectories (three methods,
four previously exposed seeds, 120 frames each), plus four complete accuracy
replays: 24 native launches in total. All methods used eight threads and one
benchmark repetition. Maximum residual was 9.98758848e-9, divergence 1.43051147e-6,
and Courant 0.46830165. Maximum reported velocity/tracer relative error was
9.00478467e-8, below the original strict 1e-5 gate. Median 120-frame wall times
were 35.357 s Jacobi, 25.729 s SGS and 4.699 s learned on this host. These include
sealed launch overhead and are observations, not historical timing reproduction.

The original accuracy replay computed full velocity/tracer norms in memory;
those field arrays are not retained by this comparison. The independent cold
oracle recomputes report coverage/maxima/medians and cross-artifact identities,
not norms from absent arrays. RHS/pressure accuracy is outside this P5a script.
Full-field retention and fresh training remain P5b/P5c.

Owner-local QA separately read custody receipts and streams and verified their
hash bindings; these are not HTTP log downloads or MCP parity evidence. The
ordinary libc loopback-only canary passed all 12 checks for the UI transport;
this is not a recipe network sandbox. Screenshots were visually inspected at
1440 and 390 pixels without horizontal overflow. Only the observed eight-thread,
one-repetition configuration is qualified here; other allowed settings retain
their declared timeout and are not covered by this observation.

Generic startup with adapters physically absent passed 10 actual checks in an
isolated source copy: owner authentication, workspaces/workbench, generic project
identity, authored scientific draft import/slice, empty Runs and unchanged copied
sources. [Receipt](p5a/no-adapter-receipt.json) and
[procedure](p5a/no-adapter-procedure.txt) retain the evidence; no snapshot or model
was copied for this check.

## Publication and remaining scope

Pending commit, push, draft PR and exact-head CI. P5a does not complete G4 or G8.
Fresh release-consuming fitting, autonomous evaluation, agent interface parity and
final compatibility/UI/restore qualification remain. The independent A8 real-model
proposal and original Rheon v2 packet gates remain open.
