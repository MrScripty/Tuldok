# Multi-source instruction authoring

The Workbench composer produces a local draft prompt from 2–4 existing text sources and a human question. Capture one exact passage per source using selected text or Unicode codepoint offsets. Inspect the assembled prompt, save it, author an independent answer, reopen it and explicitly review it against every passage and the source rights. No generation provider, inference, model or training runs. Exact quotes do not establish semantic grounding or permission. UI remains provisional.

`grounded_instructions.py` owns only the composition recipe and current source bindings. Workbench still owns immutable canonical text, independent responses, rights corrections, CAS and append-only history. The existing release owner exports `text_instruction_v1` consumer rows with exactly `prompt` and `completion`; this is not a new training format. Existing preference bindings also refuse stale context evidence and retain context assets.

## Passage and composition contract

`POST /api/workbench/instruction-compose` accepts only `request_id`, `name`, `question` and `contexts`. The stable 32-hex request ID deduplicates exact repeated requests, including acknowledgment loss. Reusing it with different claims refuses atomically. Each context has exactly `id`, `revision`, `source_revision`, `content_hash`, `start`, `end`, `quote`. IDs refer to distinct existing available local text records. Offsets are half-open Unicode codepoint positions in canonical NFC/LF source text, not browser UTF-16 positions or bytes. SHA256 and quoted slices must match the source under the shared lock. The UI converts selected DOM text to codepoints; offsets and exact quotes remain inspectable.

Recipe `tuldok_grounded_instruction_v1` uses this exact composition, with one-based source numbering and source IDs:

```text
Source 1 [<id>]
<exact quote>

Source 2 [<id>]
<exact quote>

Question
<question>
```

Sections have exactly two LF separators. Source quotes and question whitespace are retained; question CR/CRLF becomes LF and Unicode becomes NFC, matching the existing text owner. Source IDs, source revisions/hashes, spans, quote and creation metadata/rights remain immutable provenance. Current source inspection evidence is a separate owned binding. An imported/copied string does not become a verified grounded example. No additional native instruction importer or foreign `contexts` consumer column is introduced.

Limits are 2–4 passages, one per source; 10,000 codepoints per passage; 4,000 question codepoints; 20,000 completion codepoints on every answer Save; 1MiB composition/reinspection HTTP request and captured context evidence; 5,000 retained original family members on composition. Existing response selections are bounded to 5,000 exact answers and 40MiB for the complete logical release, including duplicated consumer strings, source snapshots and assets. These are synchronous resource limits, not tokenizer limits; no text is silently truncated.

## Edits, review and family integrity

Text content stays immutable. Annotation, groups and rights changes advance record revisions; immutable text `source_revision` stays 1. Inspect current contexts explicitly after an edit; export and answer Save refuse stale bindings. Deliberate reinspection retains the original source IDs/hash/spans/quotes, updates current metadata bindings and the prompt revision, and atomically resets every answer to draft with new revisions/history. Creation evidence and original answer provenance remain intact. Reopen and review each answer again; exact release selections never update automatically. A generic composed-prompt metadata edit also changes the saved review binding: an unchanged completion cannot carry approval via a no-op Save.

Delete current text source from use to retain its bytes, history, IDs and family links as a tombstone. Asset reads, further annotation/answer use and release exports refuse unavailable sources. Dependent composed instructions remain inspectable and blocked; reinspection cannot restore a deleted source or replace its content. Compose a new instruction deliberately for different sources.

The existing connected-component allocator owns splits. Admission evaluates all prospective group, content and parent links, including existing unselected bridges, and refuses conflicting inherited fixed splits or unknown lineage before inserting a prompt. The existing immutable `parents` list retains direct quoted source IDs first and all other original connected-family record IDs afterward. These additional parents represent protected lineage, not additional quoted passages, and preserve the existing graph/snapshot contract after group edits/deletions. Every contributing source family stays together; no passage or answer is independently split from its prompt.

## Frozen evidence and observed consumer

The instruction manifest retains prompt creation evidence, current source bindings, independent answer review digests and full current `grounded_sources`. Deduplicated `contexts/<source-id>.txt` assets let an independent reader recompute full hashes and exact passage slices. `prompts/<prompt-id>.txt`, response snapshots and row mappings remain the existing release authority. Preview/atomic publication includes all bytes in the 40MiB bound; later edits/deletions cannot mutate a frozen ZIP.

The existing pinned consumer is TRL0.23.1, commit `4529a1c8b1813480a85b02c9c8e7f75a29085d65`, with Datasets4.1.1, commit `9be15a723b460586999b6aa1f346e284342fcc1f`. `tests/instruction-consumer-pins.json` retains exact installed source hashes. `tests/check_instruction_consumer.py --reader-only <archive>` verifies those files through distribution paths, independently checks context hashes/offsets/families/review bindings and reads actual serialized JSONL with the unchanged Datasets JSON reader. It stops before importing or constructing tokenizer/model/trainer machinery. Later consumer EOS, token limits, loss configuration, training and semantic quality are separate decisions.

`tests/browser_grounded_instructions.cjs` exercises actual Chromium passage selection, draft composition, separately saved draft answer/reopen/review, repeated and lost/held acknowledgments, later edits, source rights correction, deliberate reset/rereview, stale fixed selections, deletion, immutable ZIP download and the pinned reader-only flow. Source fixtures are tiny human-authored Unicode text, not observed benchmark answers or evidence of model quality. `tests/test_grounded_instructions.py` covers malformed claims, caps, prospective fixed-family conflicts, original-family preservation, atomic rollback and preference bypass prevention.
