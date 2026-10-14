# Local WAV data v1

The audio owner accepts original local audio, timed human annotation, review and
canonical frozen export. Exactly one reviewed labelled interval per recording
can additionally use the [bounded local CPU classification recipe](workspace-audio-training.md)
through Pipeline and Runs. ASR, resampling, downmix and crop remain unavailable. Playing a channel is a transient browser
preview, not a derived dataset asset or inference result.

## Source and ownership

`audio_assets.py` admits a closed RIFF/WAVE PCM profile using the Python standard
`wave` reader after byte/chunk validation: little-endian PCM signed 16-bit,
mono/stereo, 8,000–96,000 Hz, at most 8 MiB and 120 seconds. Format must be the
16-byte PCM form. Extensible WAV, RF64, floats, compressed codecs, more channels,
empty/truncated data, inconsistent byte/frame rates and partial frames are
refused. Other bounded RIFF chunks remain unchanged. Import does not normalize,
re-encode or infer annotation.

`POST /api/workbench/audio-import` accepts exactly `wav` (base64 original),
`name`, `rights`, `groups`, and optional `parents`. Unknown fields are invalid;
there is no transform/import override. Identical original bytes return conflict,
so a lost response can be reconciled in the collection without repeating effects.

Original bytes are durable at `audio/<record-id>/source.wav` beneath the managed
catalog. Workbench retains `kind=audio`, `task=audio_timed`, immutable source
revision 1, annotation revisions, append-only history, rights-note corrections
and parents. Parsed metadata lives in the existing immutable origin JSON, not a
parallel store. Schema 3's explicit audio-kind admission is a separate reviewed
PostgreSQL prerequisite. Existing v1/v2 catalogs require the explicitly quiesced
upgrade; startup never rewrites their schema.

Audio admission writes and fsyncs the complete original before the PostgreSQL
record/history transaction commits. The existing metadata rollback callback
propagates file custody through nested savepoints to the outer transaction. A known rollback removes the unreferenced
file. A lost commit acknowledgement retains it, because metadata may have
committed. The collection and source hash decide reconciliation. Process death
before commit can leave an unreferenced UUID directory; it is never shown as a
record and is not automatically removed or retried. Backup includes the whole
catalog tree. A process crash does not imply a successful import.

Each source carries a protected original SHA-256 group and a protected decoded
PCM/rate/channel family group. Equal PCM with different RIFF metadata therefore
stays together. Session/subject groups and parents supplied by the human remain
in the existing connected-family allocator, including unselected bridges.
Headers alone do not establish semantic independence. Removing either mandatory
audio group is refused.

## Timed annotation

An annotation is exactly `{"segments": [...]}` with 1–200 entries. Each entry
contains exactly:

| Field | Meaning |
| --- | --- |
| `start_frame` | Integer source sample-frame index, included; at least zero |
| `end_frame` | Integer source frame index, excluded; greater than start and at most frame count |
| `channel` | Integer zero-based original channel index |
| `transcript` | Human text, up to 4,000 Unicode code points; may be empty if label is present |
| `label` | Human class, up to 80 code points; may be empty if transcript is present |
| `speaker` | Optional human speaker label, up to 120 code points; empty string means absent |

There are no floating timestamps in durable targets. One sample frame contains
one sample from each interleaved channel. UI seconds equal frame/rate for display
only. Overlap between different annotated events is allowed; identical entries
are refused. Speaker identity is human-supplied metadata. Silence is not an
inferred transcript or verification. Audio review requires an explicit human
review decision, never the programmatic verifier state.

Saving uses existing record/source revision checks. Draft interval fields must
be added/updated or cleared before record save; an unapplied form cannot silently
vanish into a successful save. Edits return the review selection to draft.
Reload and historical frozen targets remain separate.

## Playback and waveform

The native player supports play/pause/seek of all original channels.
`GET /api/workbench/audio-inspection/<id>` supplies at most 600 exact source-frame
peak bins per channel. The accessible channel/frame/transcript form is timing
authority; waveform pixels are summary information.

Selected interval playback uses the browser Web Audio decoder with the original
sample rate, requires matching channel/frame counts, then copies only the chosen
channel's `[start,end)` samples to a transient playback buffer. If the browser
cannot preserve those source coordinates, interval playback reports unavailable;
the original native player and annotation form remain available. Device playback
may perform normal output conversion. No transformed file is published.

Record replacement/page exit stops playback and closes its context; late
waveform and playback preparation results cannot take over a newer record or
resume after Pause. Browser requests do not claim cancellation of dataset work.

## Freeze and consumer contract

`canonical_v1` is the existing release owner. Audio additionally requires an
available hash-verified original, valid `audio_timed` targets and human review.
The selected-revision preview binds saved targets; stale selections/drafts fail
closed. Audio contributes its original byte size to the existing 40 MiB
synchronous immutable-asset selection bound. Family allocation remains unchanged
and impossible requested nonempty splits are actionable errors.

The ZIP contains `assets/<record-id>.wav` byte-identical to the original, complete
record/source/review/provenance snapshots in `manifest.json`, and typed records
in each split's `records.jsonl`. Audio rows declare
`audio_target_schema_version: 1` and the exact coordinate contract. There is no
cropped audio or implied ASR alignment. Export is data transport, not a qualified
training format.

Evidence uses authored known stereo impulses, Python integration through real
PostgreSQL, separately implemented FFmpeg decode, actual Chromium Web Audio
samples, keyboard review, frozen JSONL/raw-byte equality and backup/restore.
FFmpeg is a verification-only dependency; the application does not invoke it.
