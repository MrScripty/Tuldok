# Independent design review

Reviewer: existing independent design agent; read-only review before implementation.
Decision: admitted, with no fundamental blocker.

Confirmed gap from the actual native producer and existing text/caption importers.
The first slice consumes detection-only canonical_v1 ZIPs with 1–100 images.
Global manifest order owns COCO image indices; annotation IDs are split-local,
vocabulary is shared across the three projections, and negative images are kept.
Compare typed canonical JSON so booleans cannot substitute for numeric IDs.

Validate normalized RGB PNG dimensions and the 40-megapixel bound before loading
pixels. Bind measured archive, raw manifest, COCO and consumed PNG hashes. A record
digest is explicitly based on canonical parsed manifest JSON, not a physical row.
Bound strict finite/Unicode JSON, entries, per-row payloads and aggregate tokens.

Keep the exported partition as the new fixed source split and retain the original
source split as declared provenance. Check selected retained-link components in
preparation and the complete existing/deleted local graph under admission lock.
Reuse native-text-origin hashes for foreign IDs/parents to connect canonical text
and image imports. Book links dominate session links exactly as the graph owner
does. Reject group overflow. A unique acquisition session prevents updates to
older unassigned source assets. The native manifest has no complete upstream
family snapshots; disclose that limit rather than claim reconstructed ancestry.

Dataset retains atomic image storage/cleanup. Workbench receives an explicit
internal initial annotation task, preserving the existing caption default, and
revalidates detection against actual oriented geometry inside enrollment. No new
public annotation/review authority, image store, initial revision or job table.

Require lifecycle fences through reads, POSTs, result lookup and collection
refresh; preserve the selected File snapshot, dirty editor and exact selection.
Departed or lost POSTs remain uncertain until an explicit matching saved result.
No replay. Actual exporter and real browser verification must cover EXIF geometry,
fractional/negative boxes, malformed bindings/types, rollback, retained family
splits, foreign text links, Stop, departure and response loss.
