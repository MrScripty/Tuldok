# Integrated stopped-transfer witness

The exact reporting composition `cd420c44c42ff85487965a858865170cfc0a9358`
already implements M2 coordinator recovery, M3 retained owner clocks and attached
same-Run publication results. This test-only follow-up qualifies their combined
stopped transfer and current public consumers. It changes no production file,
schema, contract, README or workflow. Historical receipts remain unchanged.

The actual gate passed **1 test in 16.930 seconds, zero failures/errors/skips**.
[qualification.json](qualification.json) binds the test, production/fixture hashes,
command and environment. [qualification.log](qualification.log) is the full raw
unittest result; [domain-receipt.json](domain-receipt.json) retains the observed
identities, table summaries, raw-byte hashes and exact cleanup names.

One real neutral byte-copy attempt completed and drained, then its original
publication-copy boundary was deliberately faulted. A separate real PostgreSQL
advisory-lock holder caused a coordinator timeout. Explicit owner recovery produced
an immutable completed acknowledgement, and same-Run publication continuation
attached an exact result Ref without another compute launch. The original Run
remains interrupted with its original events. Stored clocks contain both the
incomplete publication interval and measured recovery-publication interval.

After all writers stopped, the ordinary backup restored into a new directory and
separate fresh database while preserving the original. Before application startup,
all **43 raw table representations**, identity sequences and complete ordinary-file
tree matched. The private coordinator journal matched byte-for-byte. Actual cold
activation advanced the diagnostic generation while retaining the completed
acknowledgement, original fault, stored Run and clocks. Cold clocks did not invent
continued open intervals; the legacy failed-Run artifact path still refused.

An inspect-only credential retained by the backup drove current authenticated
HTTP/SDK and separate CLI processes. Both inspected exact coordinator/timing/result
identities and collected the same 55-byte artifact with whole SHA256 verification
and mode0600 publication. Every raw table and sequence still matched afterward.
A launch tripwire covering restore, activation and all consumer calls recorded
zero calls. Original stopped SQL/files and the immutable backup tree remained
unchanged. Only the new fixture's source schema and independent restored database
were dropped; both absence queries passed before recording the success receipt.

This is one neutral direct-external attempt with one grant, one consumption and
zero Study reservations. It does not prove populated Study accounting transfer,
all historical schema/old-client/upgrade/interruption gates, or performance. No
Torch runtime, model training, CUDA or scientific workload was used. PUB-1 still
requires the actual original failure/custody/profile/output inventory; SCI-1 still
requires its real pair, criterion authority and environment. Independent review,
hosted integration and postmerge qualification remain separate lead-owned gates.
No full T8/M2/M3/M5 or broader product acceptance is claimed by this witness.
