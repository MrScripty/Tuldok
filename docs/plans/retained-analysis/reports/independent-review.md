# Independent review

Reviewer: separate GPT-6.1 Sol instance, high reasoning, read-only code/tests.
Final disposition: no remaining blocking findings in additive query or isolated
renderer. No review-side files or credentials created.

Findings closed before final review:

1. Plan overstated semantic identity rejection before evidence reads. Narrowed
   acceptance to malformed identity rejection before reads and exact semantic
   rejection before return. Added early size-bounded evaluation check before
   expensive inherited verification, repeated inside final SQL snapshot.
2. Early malformed Run-envelope preflight could raise raw TypeError/KeyError.
   Added typed unavailable409 mapping and isolated malformed-envelope cases.
3. Browser decoder accepted mismatched supports/ordinals and missing provenance,
   metric definition or column types. Enforced relationships and complete used
   fields; each malformed variant now reaches and fails that boundary.
4. Browser fixture could interact before Vega embed settled. Waits include busy
   completion; keyboard and actual SVG pointer paths are exercised separately.

Final independent checks: 12 Python fixture tests pass, one PostgreSQL SQL test
skips; actual headless Chromium fixture passes, including bad-spec cancellation.
Reviewer verified asset hashes and notice-file presence. Spec stream cancellation,
update abort/busy cleanup and owned child-process exit were reviewed in final code.

Reviewed SHA256:

| File | SHA256 |
| --- | --- |
| retained_analysis.py | 317ba63b0f89367ba26dd62b8157910654943eb8a9d3ab1442f09f09827f218b |
| tests/test_retained_analysis.py | 10ab4c7ad35c9df868320add066799a18896538ee59593156d4b52b0b2d1a11a |
| static/retained-analysis.js | b6203812c4dd04586062e903ef981cff074ba80ff5d01eeb218b711c8417a1e9 |
| tests/browser_retained_analysis.cjs | 822d6df2d8c29e909f6f0dcee42595f90c9eae70306ff9c8b20eba042bdd05ce |
| static/retained-checkpoint-curve.vl.json | 6603c860ce76a434a11e6c96cf7418246ce2dd5da3d7a56a5f2448a0537ec183 |

Limit: query fixture orchestration and real browser rendering over authored data
are established. Actual PostgreSQL/retained-Run custody/revocation, production
integration and full cold-process scientific reproducibility are unqualified.
Do not merge or register this capability on the basis of fixture evidence alone.
