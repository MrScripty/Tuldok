# P3b native ready/stop qualification — 2026-10-13

The production `recipe_process.py` helper completed a real native ready/stop
exchange with the pinned `rheon-trajectory-probe`. No native/lab source was changed,
no frame was requested, and no model was loaded or trained.

- Source pins: lab `e8a90bfef6b2955c502008ccc62443e29dd9f2ec`;
  Rheon `2209012bc5f902693d0f695ec1c2d854126af317`. Scratch build uses Rust 1.92.0.
- Native executable SHA256: `4e4e49f0e3febf5b11556c2a1daac3dc684e9fb9a9c3c742329d804a4913ceff`.
- Production helper SHA256: `f73d0881c9c3d509616e11e783a65e2bce2b9eeb9afa467602b953c93d0298f5`.
- Arguments: `8 jacobi 100`. Captured stdin: one byte `00` (stop).
- The helper established READY, received GO, executed the sealed native binary,
  captured exactly 237 stdout bytes (one length-prefixed `rheon-trajectory-v1`
  ready envelope), and observed leader return code 0 followed by ECHILD.
- Durable receipt: completed, spawn closed, drained, ECHILD true. Stderr empty.
- The declared system runtime plus recursively inspected native ELF dependencies
  contained 1316 files / 64246348 bytes. All
  dependency files resolved under `/usr`, with installation owner UID
  65534, no group/world write, and no current-user write;
  the already admitted Python sitecustomize exception remains in the helper's
  system inventory. The helper rehashed this captured inventory before READY and GO.
- Runtime closure SHA256: `418e458318bf71ed2739e98aab4778cfa9c91171b5982f803734823c6d1159dc`.

Compact receipt and direct native library identities are retained in
[p3b-native-probe-receipt.json](p3b-native-probe-receipt.json).
The full measured inventory, control events, raw logs and receipt remain under
`/workspace/scratch/tuldok-p3b-production-native/`; `qualify.py` reproduces this
local probe into a fresh UUID directory using the existing pinned binary.

This establishes local native process custody and wire readiness only. It does
not establish simulation accuracy, generated trajectories, training, GPU/Pumas
acceptance, hosted native runtime portability, or the later scientific milestones.
The direct native invocation is a helper qualification; the admitted application
recipe profile remains the reviewed system-Python profile.
