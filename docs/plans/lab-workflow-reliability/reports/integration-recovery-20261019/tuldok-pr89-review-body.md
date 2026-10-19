Current Project/model workflows can use an explicitly selected, inventoried Torch CPU/CUDA installation and display externally changing Project activity and evidence. Pumas Library owns the installed Python/PyTorch environment; Tuldok verifies that installation and retains approval, cancellation, deadline, process custody and artifact-publication checks.

This PR adds managed Torch registration/bootstrap, bound-model authoring, live Project observations and exact scientific-number transport. The one-time converter and fixtures remain outside application startup and ordinary CI; this review did not execute it against a catalog.

Integration review repairs:
- Preserve every one of the 106 published main contract identities. Add snapshot inspection/open v2 and recipe inspection v4, with the corresponding legacy wire projections and explicit browser pins.
- Select compatible snapshot or legacy CLI operations from validated capabilities before dispatch. Authentication, malformed capabilities and failed operations never trigger a second dispatch.
- Cancel stale initial and nested recipe inspections when Project/recipe identity changes. Preserve evidence-preview focus during refresh without stealing focus moved elsewhere.
- Persist the private registry file mode and both containing directories before acknowledging registration, including an existing-registration retry.

Validation is separated by source and execution environment. The original PR description reports the author's prior CUDA training/CPU restore and lifecycle/browser qualifications; those hardware results have not been independently reproduced here. This integration has not reproduced CUDA or scientific training. Local regression checks cover contract identities, CLI refusal/selection, registry fault injection, managed asset/process helpers and actual Chromium polling/focus with synthetic transport. Database-backed old/new HTTP compatibility, full workflow/browser and scheduling tests are required hosted PostgreSQL 17 checks. Local PostgreSQL provisioning is unavailable because the package proxy returns 403; database skips are not passes.

The dependent performance PR retains all subsequent concurrency, custody-fence, CUDA-deadline, output-rename and request-latency commits through de0f1b833f1922b4a86c12036405fe8cd795b4a0. It will be reviewed and merged serially after this PR. Historical runtime receipts are supporting evidence, not fresh hardware verification. The trusted installed runtime must remain unchanged during execution; OS libraries and GPU drivers remain external dependencies.
