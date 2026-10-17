# Output inventory rename race

Status: Active. Owner: root. User authority: Tuldok improvements needed by the
ongoing CUDA/CPU model sequence. Separate infrastructure branch, no model edits.

Run786bdd62edb845fe8950c4a952bbcc78 reached5000updates then drained with reason
output_limit. Retained output files total under32MiB. The pressure evidence writer
renames profile.json to training-profile.json. A deterministic real rename between
live directory listing and lstat reproduces FileNotFoundError, which the helper
classifies as output_limit. Stderr empty, leader SIGTERM; no successful published
checkpoint is reused. This identifies a reproducible cause compatible with the
failure; the old receipt did not retain the exact observation exception.

Fix only the live monitor: ignore FileNotFoundError for a listed child that has
vanished, allowing next scan and existing final publication validation to check
surviving files. Keep other errors, regular-file/count/size/total bounds, wall
limits and final custody validation unchanged. This is observational sampling,
not an instantaneous inventory or OS memory sandbox. No silent retry/replay.

Verify deterministic rename, subsequent oversize rejection, other-error rejection,
existing exact output bounds and Linux custody lifecycle tests. Deploy only with
no active catalog Runs, preserving all prior states and exact owner/catalog.
Close the failed Study and admit one fresh late-arm fit from initialization;
retain original successful early fit and fresh CPUrestore, read-only recovery.
Standards MCP snapshot:v1:f2c192e8-4ff4-41a9-b019-8e6b050c27a7 applies; independent
Standards and Spec reviews required before completion. No push or merge.
