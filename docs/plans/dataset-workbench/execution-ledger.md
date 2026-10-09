# Execution ledger

## 2026-10-02 recovery and design

Recovered three unfinished backend modules and an ADR on local development branch; no implementation was published. Verified remote main at 2fc4a46. Baseline: `python3 -m unittest discover -s tests` passed 39 tests.

Applied Coding-Standards snapshot dcc56f26e884ade260770beceba2501d3746200d: Core, Planning, Architecture composed-design admission, Verification. Read the supplied revised Dataset Production research (modality contracts and controlled synthetic production) and Cooking the Cat chapters 14/18 (standards decisions and coherent observable development slices). Primary format references: https://cocodataset.org/#format-data, https://www.unicode.org/reports/tr15/, https://www.w3.org/TR/annotation-model/#text-position-selector. W3C selector semantics inform offsets; the JSONL format is explicitly Tuldok-owned, not a full W3C annotation interchange implementation.

The recovered code required integration, tests, and hardening. Added HTTP composition and source-split preservation; made archive hashes describe the bytes actually copied, with fixed ZIP metadata for stable repeated releases.
