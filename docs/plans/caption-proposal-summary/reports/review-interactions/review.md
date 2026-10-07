# Caption status projection interaction review

Exact source `e8cde950e597da2f290e8ebcdefdacb47725220a`, tree `2e1afe1b31c02aef41b4f74d3814b8ccc59fcb9a`, against `bf8614b6e4eacd927ce9ef615cd3eb674f15e762`.

No actionable findings. The shared-lock SELECT in `caption_proposals.py:130` materializes every projected row using fetchall before releasing the lock. Python JSON decoding uses these detached texts afterward. The SQL removes only two top-level payload keys and preserves existing descending order/50-row bound; exact GET/persisted data remain unchanged.

Two focused tests passed using the active absolute interpreter with the existing PATH python3 trap first: atomic capture/lock release and actual frozen export/consumer evidence/history/fixed-selection behavior. A separate two-row probe confirmed the writer completes during first-row decoding while the current poll contains both old statuses and the following poll contains both new statuses. Exact GET payloads and nested similarly named metadata remain intact. Direct invocation of PATH python3 exits with the trap's expected 87, so the passing actual consumer test demonstrably selects sys.executable.

UI, controller, API routing, Workbench transactions/review, CI, release owner, consumer fixture, procedural generation and image-generation source are unchanged. This review ran no browser/full suite or remote actions and changed no candidate files/reports. Controlled probes establish lifecycle/consumer-interpreter contracts; they do not claim real-model quality or a measured performance improvement.
