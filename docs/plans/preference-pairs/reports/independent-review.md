# Independent review

Separate reviewer preference_review read the design before implementation and then reviewed working code and executed independent probes. No source edits or public writes by reviewer.

Design clarified: dissent from all current live reviewed judgments of selected exact bindings participates in proof, even if unselected; stale deletion compares stored bindings; selections serialize stored revisions; all parent adoption paths fence independent judgment intent; identical strings warn; ties/abstentions exclude with reason and do not veto direction.

Three code findings resolved and independently verified:

1. Rights-note save could discard an existing dirty judgment. Preflight now reports the retained judgment and returns; late-started judgment intent also fences parent adoption.
2. A post-save list read could silently replace answer revisions under a retained later draft. Editor now snapshots its answer evidence at explicit edit time; body and displayed text use that snapshot. Independent held-ack/unseen-answer-r2 probe keeps original answer r1 and does not silently review r2.
3. Deleted-history response could paint after prompt/editor replacement. Parent/intent epoch fences response; parent adoption clears history.

Reviewer verified focused persistence/HTTP checks, controller interleavings and the independent retained-draft probe. Independently reran unchanged hash-pinned DPO consumer: four rows, three prompts, maximum 2,249 tokens, 6,669 padding positions. Backend review confirms one Dataset lock/transaction for CAS/history, deletion retains historical evidence, reversed-side dissent compares chosen identity, exclusions still validate exact review/bindings, full archive budget includes competing evidence/projections, and existing family allocator/content-addressed publication remain authoritative. No remaining correctness blockers found. After review, matching competing evidence was additionally bounded before manifest construction, and dedicated preference tests directly exercised fixed legacy splits/deleted ancestry/reopen/missing lineage and readonly preview.
