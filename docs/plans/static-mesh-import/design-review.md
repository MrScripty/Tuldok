# Independent initial design review

Read-only reviewer /root/independent_design_review admitted the closed profile before source implementation; no blocking design issue. Reviewed existing PR20 storage/Workbench/releases/UI, actual authored PLY files and their sidecar hashes, and primary format definition. Refinements required in implementation: atomic migration plus table setup, preserved sequence bytes/API/provenance, shared saved-set/release cap before BLOB reads, mesh caption ancestry compatibility, stale same-ID/leave inspection fencing. These are acceptance details, not an additional permission requirement.

Canonical write set also includes caption_import.py, saved_selections.py, static/workbench.css, tests/test_meshes_controller.cjs, tests/qa_artifacts.cjs and .gitignore. The QA helper is copied byte-exactly from still-open cleanup PR21 head 2026d716ea88fc303ed3e298031b3314f30d4ea7 for the new slice; inherited QA cleanup remains independently owned by PR21.

# Independent implementation review

Reviewer closed three concrete implementation issues with independent reproductions: extreme JSON exponent escaping invalid400, unknown records/asset table schemas escaping setup rollback, and native float32 decimal double rounding. Regressions now enforce known full column/constraint shapes and atomic migration/table setup, typed HTTP/no-write failure, exact midpoint-neighbor/tie/subnormal native interpretation. Extent-relative projection also avoids subnormal-center clipping. Sequence-specific diagnostics and facade API remain preserved.

Final independent probes: 13 mesh tests, 11 sequence tests, projection/controller, 53 direct C strtof cases and real mesh Chromium at exact 1e7f735de1af1a045f139f35b56402ce056d251e all pass. Initial and implementation reviews admitted; no remaining source blockers. No reviewer writes, Rheon execution, model work or public changes.
