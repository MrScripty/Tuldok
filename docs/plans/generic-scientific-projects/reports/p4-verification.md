# P4 qualification — optional native generation

Candidate branch: `feature/native-scientific-generation-20261013`, based on
qualified PR48 `7d59060`. This report records worktree evidence; published commit
and exact-head CI will be recorded after publication. No merge or deployment.

## Implemented behavior

Optional captured native sources add a recursively verified loader/library policy
to existing approved recipes. The optional Rheon wrapper generates bounded real
Jacobi trajectories and retains every native array without conversion. Completed
Run artifacts can enter Data through a server-derived source receipt; imports are
drafts and require separate human review/freeze. Existing Python-only recipe
shapes and project-source releases remain supported.

A real complete backup/restore test exposed an existing relocation defect:
receipt-bound absolute execution paths were being compared with the new catalog
path. Validation now preserves the original declaration and complete spec hash;
artifact reads use restored owned paths, while dispatch rejects relocated paths.
No historical receipt or execution specification is rewritten.

## Real native workflow

The final browser run is `build/qa/workspace-native-generation/run-uxEq8B`.
Its [receipt](p4/browser-receipt.json) and six screenshots are retained beside
[candidate source hashes](p4/source-files.json). Chrome 151 and a loopback-only
application transport canary were used; this is not a recipe network sandbox.

All six workflow gates passed:

1. Owner-approved production Run executes the sealed native/loader path; invalid
   controls fail preflight and changed artifacts cannot import.
2. Independent NumPy 2.5.4 decodes original native wire, verifies all twelve NPY
   array payloads/shapes/dtypes/MAC locations and eighteen inspected planes, and
   checks retained policy/mapped-library identities and bounded diagnostics.
3. Import creates a draft; separate human review and canonical freeze retain the
   exact generated bundle and original custody receipt.
4. Real seed 101 changes arrays and family; seed 100 with one frame preserves
   the trajectory family and first-frame bytes.
5. Cancellation reaches `queued → running → cancelling → cancelled` with drained
   custody and no importable partial result. This observation does not assert
   that native frame generation had begun before cancellation.
6. Restart preserves the completed Run, reviewed Data, exact frozen release and
   unchanged project sources.

The primary Run is `82e605bd024346d2ae89cf6cef1465b2`, 32³/two frames/seed 100.
Native binary SHA256 is
`4e4e49f0e3febf5b11556c2a1daac3dc684e9fb9a9c3c742329d804a4913ceff`.
Original build receipt SHA256 is
`332aa36d8ce02585be77fbd74f8a7dfcfe9a297a3054b5bb67461ee3556d1e40`.
The receipt records output and release hashes, runtime mappings, numerical
observations, second-seed checks and screenshots. Units remain explicitly native
and unspecified. This qualifies bounded generation/custody, not training, GPU
performance, general physics validity or P5 autonomous evaluation.

## Focused checks

- 20 host/helper tests pass, including recursive ELF rejection, captured native
  policies, preload refusal and unchanged omitted-native shapes.
- 9 adapter tests pass with explicit qualified binary/receipt environment paths,
  including real two-seed generation. Without those inputs, native-only tests
  report explicit skips; authored fixtures are not real acceptance.
- 6 real Run import/HTTP tests pass: permission boundaries, draft-only admission,
  original receipt bytes, duplicate refusal, changed bytes, noncompleted states,
  rollback cleanup and unknown commit acknowledgement.
- 9 scientific reader tests pass with NumPy enabled: original project releases,
  real neutral Run import/freeze/cold CLI, tampered/mixed provenance, and complete
  PostgreSQL/artifact backup restoration to a different directory. Restored
  `Runs.capture_artifact` returns the same bytes and source receipt.
- 11 retained external Runs tests pass after the relocation fix. The independent
  point-cloud/volume reader environment passes all 20 checks without skips.
- External controller, workspace service, auth controller/helper and affected
  JavaScript syntax checks pass. Existing recovery browser passes.
- Actual application startup with the optional adapters directory physically
  absent passes owner authentication, static UI delivery, generic project
  inspection, draft scientific import and exact Data slice inspection. No producer
  executes and Runs stays empty. See [receipt](p4/no-adapter-receipt.json) and
  [exact qualification procedure](p4/no-adapter-procedure.txt).
- Independent source review found no blocking issue. Plan-contract validation
  and whitespace checks pass. No static type checker or Standards Engine
  certification is claimed.

Full Python regression passes: **771 tests in 962.842 seconds**, with two optional-reader skips separately covered by the 20-test independent reader run. All 185 runtime/unit-test Python sources remain unchanged. [Before/after inventories](p4/python-suite-source-files.json) record the separate standalone oracle refinement. Final published-head CI remains pending. The standalone
native NumPy oracle received an evidence-only validation refinement after the
full-suite inventory was taken; it is not imported by the unit suite and the
final real browser ran that revised oracle. Record both inventories explicitly.

## Remaining scope

P5 requires a separately reviewed captured CPU runtime, actual fitting/evaluation
and larger lossless result handling. P6/P7 remain planned. Dataset-workflows A8
positive real-model proposals and original Rheon v2 packet retrieval/qualification
remain separate open gates. ASR and general 3D training are explicit extensions.

## Published-head gate

Commit `c7c696bda48cc2917253ffbcf4d01f763196eecc` passed hosted UI run 38447405152 and lifecycle run 38447405078. PR49 remains draft and unmerged. P4 is accepted; P5 may proceed on its own branch.
