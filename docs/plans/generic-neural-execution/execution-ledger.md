# Execution ledger

## 2026-10-14: Discovery and plan admission

Preserved clean saved branch `work` at f2751c3; fetched origin/main and created
`feat/generic-neural-project-execution` at exact d856a984535a430909761ed13ce42eadd55b0710.
No AGENTS.md/applicable skills found. Read the adopted plan template and relevant
standards from Coding-Standards dcc56f26 (available clone HEAD188beda1).
Read-only lab clone HEAD e8a90bf inspected: train_cpu.py contains actual NumPy CNN
gradients and Adam; trajectory_model.py fits independent gains in closed form.
Existing external_recipe_v1 and captured_cpu_python_v1 suffice for the proposed
adapter contract; no schema alteration is admitted. Delegation authorizes start of
the scoped plan after structural validation. Publication/draft PR authorized;
merge/final tags are not part of this lane.

## 2026-10-14: Generic CLI qualification

Implemented `project_cli.py` exclusively through public AgentClient and
verify_artifact APIs. Explicit open/inspect/recipe/prepare/preflight/submit/status/
cancel/download commands share production owners; the CLI neither creates
grants nor retries mutations. Downloads verify whole SHA256 before exclusive
mode0600 publication and preserve existing/concurrently created work.

Recorded [generic verification](reports/verification.md). Final optional-environment
command `.venv-agent/bin/python -m unittest discover -s tests -p 'test_agent_*.py' -v`
ran30 tests in45.611s:29 passed,1 skipped because an actual classifier runtime was
not selected. This includes all7 new CLI tests plus actual SDK→HTTP→domain
qualification. The environment came from unchanged `requirements-agent.lock`
with required hashes; `pip check` passed. Other observed checks:28 external
tests,5 artifact-segment tests, unchanged actual Chromium external workflow,
controller/syntax/whitespace checks, structural plan validation and6 read-only
lab NumPy trainer checks. No neural pressure reproduction is inferred.

Moved the CLI tests to `test_agent_project_cli.py` so existing optional-agent CI
runs them without changing app dependencies or the workflow. Base environments
explicitly skip only its2 HTTP tests if JSON Schema is absent; those skips do not
count as CLI acceptance. No changes to other implementation owners.

The lab CNN's radius-one limitation and modal optimizer_steps0 are now documented
as distinct model-acceptance constraints. A1/A2/A4 generic acceptance is satisfied;
A3 and Milestone2 remain blocked pending paired lab sources/data and parent
coordination. No corresponding execution was denied or attempted with unknown
outcome. The original stale `work` branch and read-only lab source remain intact.

## 2026-10-14: Parent-authorized continuation

The parent relayed lab-only CPU regeneration/refit/cold prediction reports and
explicitly authorized continued PR58 CI/review and managed runtime preparation
while exact lab pins are packaged. These reports are not Tuldok managed acceptance
and do not satisfy neural optimization A3. The plan resumes Active for independently
useful runtime preparation; source/data-dependent acceptance remains pending.
PR58 lifecycle CI passed at cdbe5136e05f2b49c43b9884f3ed03dcc8c7025c:
https://github.com/MrScripty/Tuldok/actions/runs/38522834049/job/115716250347.
No submitted independent review exists; CodeRabbit's comment says draft PRs are
not reviewed automatically. The parent was asked to relay review findings or
explicitly authorize a manual bot request; no bot/person message was sent.

Prepared the unchanged CPU profile with explicit Torch2.8.0+cpu and NumPy2.5.4
packages in ignored `.venv-training`. Initial inventory refused functorch's
compiled extension and optional Torch test executables for noncontained native
search paths. Unsupported optional components are recorded as explicit exclusions;
the loader rule is unchanged and torch_shm_manager remains required.
Reuse the existing generic captured-runtime qualification script rather than
adding another test harness or interpreting authored computation as pressure
model acceptance.

## 2026-10-14: Actual paired managed training and restore

Parent supplied lab PR1 2a49aa81a26efc8ccbfdc3f756b39ccd5019ff15 and clean
source d2b344fcbf2267e5851f6f1bb2371cb8ca48e58b. Created an isolated ignored
clone under Tuldok build/ without altering lab sources. Official Rust1.92.0
tools and pinned root Cargo.lock built the original pressure generator. All18
reference cases verified; packaged dataset38cd3176...ebbd9cf and splits
de228c36...8fd82c7a exactly match the handoff. The wrapper requires NumPy2.3.5,
so the original2.5.4 snapshot was preserved and a fresh2.3.5 snapshot captured:
9b05b82bfbe16feec4c8497547fa8adb4fa9d988135033d3413ea9c9c4668335.

Existing generic captured-runtime probe passed compute/checkpoint/cancellation/
catalog reopen at snapshotae67a1a7...02d1d. The scoped generic qualification
driver then used the actual project CLI, authenticated HTTP, owner-granted
material, production custody and full artifact downloads. Training Run
6bf8bf9fcec141be95426576e941f886 completed/drained with200Adam updates and exact
historical checkpoint7f514ff9...c64121. Restore Run
097d69d2c6d144b9881e6baed52f8198 consumed five exact completed training artifacts
plus project dataset, completed/drained with zero updates and exact retained
predictions. All12outputs verified through CLI downloads and verified again
after service/catalog reopen. Runtime evidence confirms pinned2.3.5/2.8.0+cpu.

Native evaluation of the restored predictions reproduced the negative diagnostic:
0/16qualified, maximum corrected float32 divergence17.457689086596172; test mean
relative pressure L2=7.664304193007793. This is not modal parity or speedup.
Actual Chromium Runs inspection passed for both CLI-created CNN attempts at
1440/390pixels. The reviewed screenshots visibly retain the large numerical
errors and diagnostic scope; no new UI code was needed. The7ordinary CLI tests
passed in8.933s. [Managed report, compact receipts and captures](reports/managed-cnn.md).

The first driver attempt failed before graph/Run creation because project detail
does not include a raw manifest. It now verifies the exact local fixture manifest
against registered SHA256 before selecting refs, and the corrected actual path
passed. The first capture used a nonexistent fixture value; selecting catalog
corrected the test-only screenshot procedure. No failed attempt was accepted.
The driver remains generic and has no numerical/physics implementation.

A1–A4 are satisfied within their stated diagnostic/custody scope. Added A5 for
the explicitly requested independent source/standards review and final candidate
CI; those remain pending. No public cross-repository comment or release tag was
created. The task stays Verifying rather than declaring unobserved review passed.
