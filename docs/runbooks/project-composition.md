# Compose retained projects

The owner operation `project_files.compose` creates one independent project from
an open editable primary and one or more explicit retained project checkpoints.
It preserves the original scientific evidence and forks the primary editable
notes, data and definitions through the same owners as Save As. Secondary drafts
and operation receipts remain inert historical sources. No source project is
modified and no imported program, runtime or credential becomes active.

Negotiate the operation's version-1 contract through the native project owner
client. The route is `POST /api/workspace/project-files/compose`. In addition to
the current `binding`, `expected_checkpoint` and one fresh `request_key`, supply:

- `root`, `directory` and `name` for a new destination under a configured root;
- `sources`, an ordered list of additional selections, each containing `root`,
  `directory`, `project_id` and `checkpoint`.

The current project is implicitly the first source. At most 15 additional
sources are accepted by the HTTP contract. All source projects must be idle and
available for native exclusive store ownership. The primary's captured working
files must be clean. The destination cannot contain, lie inside or alias any
source, and existing unrelated destinations are never overwritten.

Equal canonical envelopes share one retained representation. Same-ID conflicts
are rejected except for Run documents that differ only in their historical
approval grant/consumption while retaining the same admission and every other
field. The complete alternate document is retained as a native Run observation;
it does not become a second Run or create a disclosure. Both documents remain
subject to the history owner's proof and payload validation.

The persisted `project_composition_v1` record binds the ordered source identities
and exact canonical envelope hashes to the destination's ordinary fork overlay.
A source membership explicitly identifies any alternate Run observation needed
to recover that source's document. Its decoder rejects missing, altered or
contradictory memberships. Subsequent ordinary forks preserve and archive this
provenance. Older software that does not support this family must reject the
project explicitly; records must not be dropped for compatibility.

Payloads are verified and copied as independent ordinary files. A missing copy
can be supplied by another source with the same verified declaration; a corrupt
selected source is rejected. Unique bytes cannot be omitted. Only dependencies
classified as regenerable by their domain owners can remain explicitly missing.

On success, `state` describes the newly selected project, `fork` reports the
primary origin and copy completeness, and `sources` lists every selected source
identity/checkpoint in order. The local owner installation retains its own
credentials. Existing Save As and lifecycle-state contracts are unchanged.

Retain a request before dispatch. An interrupted publication can leave an inert
stage or a complete unselected destination. Inspect the original request and
owner state before reconciling with the same key and arguments. Native receipts
bind reconciliation to the complete ordered source set. A timeout does not
justify another request key or deleting a retained stage. Selection failure
returns a durable unselected receipt while preserving the current primary.
