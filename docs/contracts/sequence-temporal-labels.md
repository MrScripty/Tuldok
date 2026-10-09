# Human-defined temporal labels, version1

Workbench owns this optional annotation extension on existing task `sequence_transport`, not the Rheon producer. Whole sequence records/assets/revisions/review/family-safe canonical releases keep existing contracts. Annotation is exactly legacy `{note}` or `{note,temporal_labels}`; a legacy save is deliberate complete-target replacement. `note` uses existing4000-codepoint stripped Unicode semantics.

```json
{"note":"Human whole-trajectory review rationale", "temporal_labels":{
  "version":1, "origin":"human_defined_annotation",
  "frame_semantics":"inclusive native accepted-state frame indices; constructor 0 has no preceding accepted interval",
  "source":{"content_hash":"<whole stored ZIP SHA256>","run_sha256":"<raw run.json SHA256>","frames_sha256":"<raw frames.jsonl SHA256>"},
  "ranges":[{"label":"Reviewer-defined appearance regime","note":"Human rationale",
    "start_frame":0,"end_frame":8,
    "start":{"frame":0,"time_s":0.0,"sha256":"<original frame line incl newline SHA256>","carrier_stamp":{"id":"43","version":"0"},"liquid_stamp":{"id":"41","version":"0"}},
    "end":{"frame":8,"time_s":0.5,"sha256":"<original frame line incl newline SHA256>","carrier_stamp":{"id":"43","version":"8"},"liquid_stamp":{"id":"41","version":"8"}}
  }]
}}
```

Every object has exact closed keys shown. Version/frame indices are strict integer JSON numbers, never booleans/floats. Bounds0<=start<=end<=8; inclusive native endpoint states, no inferred continuous interpolation/force interval truth. Time requests may spell numerically equal finite int/float, never bool: browser JSON.stringify0.0 emits0. Canonical stored endpoint copies preserve source metadata numeric type; new-envelope release validation also requires exact canonical encoding. Stamps remain exact string objects; lowercase64-hex source/endpoint hashes must match authoritative immutable record metadata. Original bundle/index is independently reverified under existing lock/transaction/preview rollback before mutation/export. No author edits source frames, fields, controls, units, diagnostics or producer provenance.

At most16 ranges and64KiB canonical UTF8 annotation bytes. `label`1..80codepoints; rationale `note`1..500codepoints, valid Unicode, Python text_value strip semantics, no NFC/case folding. Duplicate normalized label/start/end is refused regardless of rationale. Order retained, overlap and different labels permitted. Empty ranges mean absence of authored targets, not a reviewed physical negative. Request size/semantic/source failures publish no revision/history/raw changes. Source/revision conflict returns409 via existing record CAS. Human review remains explicit and separate; programmatic sequence review is refused. The origin string describes target authorship scope and is not authenticated human identity or physical truth.

Canonical whole-record JSONL/manifest retain these targets plus original metadata and exact nested raw ZIP. No per-frame records or split allocation are created; transitive source/initial-family grouping remains indivisible, including unselected relatives. Label search/filter/analysis expose strings under existing metadata semantics; a consumer interprets its own taxonomy and must choose this target version explicitly. No dedicated model-training consumer, scientific validity or model success is qualified. Old frozen release bytes remain immutable after later target edits.

UI: Add/Edit/Remove/Clear stage only; pending input must Add/Update or Cancel before Save or destructive target action. Cancel preserves staged targets/other edits and does not restore human review. Existing editor dirty/review-reset/save/history/reload owns persistence. Restored-page lifecycle preserves staged/pending drafts and retires old action/save epochs; only exact owner may resume. A server-confirmed held Save can leave that retained local pair stale, so next Save requires deliberate reload409 rather than automatic replacement.
