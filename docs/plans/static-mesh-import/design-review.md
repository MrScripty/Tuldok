# Independent initial design review

Read-only reviewer /root/independent_design_review admitted the closed profile before source implementation; no blocking design issue. Reviewed existing PR20 storage/Workbench/releases/UI, actual authored PLY files and their sidecar hashes, and primary format definition. Refinements required in implementation: atomic migration plus table setup, preserved sequence bytes/API/provenance, shared saved-set/release cap before BLOB reads, mesh caption ancestry compatibility, stale same-ID/leave inspection fencing. These are acceptance details, not an additional permission requirement.

Canonical write set also includes caption_import.py, saved_selections.py, static/workbench.css, tests/test_meshes_controller.cjs, tests/qa_artifacts.cjs and .gitignore. The QA helper is copied byte-exactly from still-open cleanup PR21 head 2026d716ea88fc303ed3e298031b3314f30d4ea7 for the new slice; inherited QA cleanup remains independently owned by PR21.
