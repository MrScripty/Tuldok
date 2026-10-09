# Authored interval-controls preview contract v1

Producer evidence is pinned to MrScripty/Rheon draft PR20 commit
fee7b4a139574f87b259796b1ba8698a41d31ac1. The exact v1 validator source is recorded in [rheon-v1-source.json](rheon-v1-source.json). The global v1 boundary/inlet config is
a static declaration. Diagnostics source_m3 is not a complete source/force control.

The strict optional JSON sidecar schema is `rheon.dense3d.interval-controls`,
integer version1. Every key is required and unknown keys are rejected. Root keys:
schema, version, run_sha256, frames_sha256, axis_order, side_order, speed_sign,
units, provenance, intervals. Hashes bind exact raw imported files. axis_order is
["x","y","z"], side_order ["low","high"], speed_sign "positive outward normal".
Units are exactly time:"s", outward_speed:"m/s", inlet_fraction:"dimensionless",
source_rate:"m^3/s", body_acceleration:"m/s^2".

Provenance keys are origin, author, source_note. Only origin
"independently_authored_contract_fixture" is supported at this stage. author and
source_note are nonempty strings of at most1000 codepoints without control
characters. Self-declaration does not prove authorship or simulation execution.

Exactly eight ordered entries associate accepted intervals1..8. Keys:
start_frame, end_frame (integers k-1,k), start_time_s, end_time_s, dt_s (exact
adjacent frame values), carrier_before, carrier_after, liquid_before, liquid_after
(exact adjacent canonical decimal-u64 {id,version} stamps), boundary_stamp
{id:"47",version:"0"}, inlet_stamp {id:"53",version:"0"}, outward_speed_m_s
[[-0.25,0.25],[0,0],[0,0]], inlet_fraction [[0,0],[0,0],[0,0]], source_mode "none",
source_rate_m3_s0, body_acceleration_m_s2[0,0,0]. Values must be finite. This
fixed-case proposal explicitly describes absence of distributed sources, rather
than interpreting a zero net rate as absence. It does not support general forces
or sparse controls. Constructor frame0 has no interval or control entry.

The independently authored factory tests/fixtures/rheon_authored_controls.py is
the exact executable fixture definition. Its assertions are not producer output.
The preview never adds it to the stored bundle or marks old data complete.


## Current scope

This authored version1 sidecar is an inspection attachment for an existing v1 two-file bundle. It is never inserted into stored raw bytes or inferred as producer output. Constructor0 has no controls. The source-pinned implementation is `sequence_inspection.py`, which accepts at most96KiB request JSON and64KiB decoded authored controls, with exact annotation/source revisions and raw-bundle revalidation. Native review uses its separate bounded endpoint.

Producer version2 is a separate supported three-file protocol described in [simulation-sequences.md](simulation-sequences.md). Its emitted declarations must bind the original frames and exact run members; they are not authored-v1 assertions. No earlier proposed-v2 text defines the current adapter. Validation does not authenticate either author or producer, grant human review, or qualify physical/scientific targets.
