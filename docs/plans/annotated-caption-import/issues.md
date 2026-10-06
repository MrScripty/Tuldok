# Native caption import issues

- Training-consumer validation does not validate native manifest integrity, paths, unknown row fields or caption maximum. Five unsafe/mismatched examples passed the existing consumer. Disposition: keep the pinned consumer unchanged; implement stricter importer gates separately, with actual persistence evidence.
- Exported PNG bytes can differ from original acquisition bytes. Disposition: derive local source hash from received PNG and retain original acquisition identity only as declared origin evidence.
- Full family snapshots may exceed the existing 30 protected-token bound. Disposition: fail closed; no truncation/new relationship registry in this slice.
- Folder import cannot reconstruct the original ZIP hash. Disposition: record observed source-file/row hashes; do not claim archive authentication.
- Fixture rehearsal saves draft captions after separate asset admission. Disposition: preparation only; production requires one owner transaction/initial history and fault tests.
- HTTP 401 on prior gh inspection reads remains paused. Parent owns PR metadata/hosted checks; working ordinary Git publication remains available when the fully verified slice is ready.

- Dataset legacy session split propagation could otherwise move older unassigned assets during caption acquisition. Fixed using separate acquisition sessions while retaining protected groups; an actual persistence test proves old source/revision state remains unchanged.
- Non-ASCII integrity signatures raised a comparison TypeError during review. Fixed with strict signature shape before constant-time comparison; malformed HTTP input returns 400 without admission.
