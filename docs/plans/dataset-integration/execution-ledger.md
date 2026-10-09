# Integration merge ledger

All merges are ordinary two-parent commits; no squash, cherry-pick, force push,
main merge or source-history rewrite. Existing development source stays preserved.

| Merge | First parent | Second parent | Result tree |
| --- | --- | --- | --- |
| `6bf6d3a57de0ad360ff3a40efbf7372d945cc85c` | `3ce5b181decfbf40cc4b661fb07caa39d6bc8e3e` | `801d598a1400afdc2360128a1657896b89da10c4` | `943e6c0a61162957a315a2d6b7aea6187cac2fc2` |
| `f4ade9cfd0aa740830ffff2e24a8f24d75f3d9e4` | `6bf6d3a57de0ad360ff3a40efbf7372d945cc85c` | `7c43e9b8fe6ff23d3e75d356361fe616c8365d9c` | `95800e34f522b872609db011f3e0d6464b4212ff` |
| `3b77b32b24fb00dc2f436eb8b80f26e53b5b9063` | `f4ade9cfd0aa740830ffff2e24a8f24d75f3d9e4` | `e1336b0db419d11acb8788906f169ab3d29e33c3` | `9aa28afb2e2881bae04433899275a3024f55f743` |

First merge cleanly carries the exact published generation repair/tests/docs;
synthetic.py and image_generation.py retain exact PR4 component bytes. No new
generation behavior is authored here.

Second merge conflicts were resolved by composition:

- `app.py`: retain saved-selection list/load routes and raw-import result lookup;
  include both `/saved-selections.js` and `/bulk-import.js` static entries. Existing
  Dataset.selections composition and raw-image enrollment transaction both survive.
- `static/workbench.html`: retain repaired filter/saved-set shell and script, insert
  complete bulk panel beside existing import/generation UI and load bulk script
  after workbench and saved-set scripts. No panel/control is discarded.
- `static/workbench.css`: retain saved-set/filter/release rules and append bulk
  status/results rules. Existing responsive breakpoints remain.
- `.github/workflows/tests.yml`: union both component push branches, controller
  and browser gates and screenshot paths; add the separate integration branch.
  Explicit env mappings remain attached to every browser step, including metadata
  and bulk suites. Later add bulk-script syntax and combined-browser gates plus
  its own screenshot path. No assertion/deadline/gate is removed or weakened.

Workbench.query/filter and atomic import changes auto-merge without overlap.
Existing saved-set persistence, raw-import module/controller and release module
retain exact owner-component bytes. Source/CI union audit checks those bytes and
every inherited registered run command/screenshot path.

During qualification parent reported the cached-preview and lone-surrogate defects.
PR6 repair appends `bfbebbb` to preserved `2311f7c`. PR7 surrogate commit
`dd18514612ca4584b94431bf5a2a5dd5ea743155` appends to preserved `3ce5b18`, then normal
merge `e1336b0` has parents dd185146 and bfbebbb. Third integration merge is clean
and retains both fixes/tests/evidence, plus all original raw-import source.
Final qualification commit adds only the combined test, workflow gates, docs and
inspected combined screenshots after this merge; its exact head/tree are returned
in the delivery receipt and hosted metadata.

Existing PR6/7 metadata was updated only to report their authorized repairs and exact
CI receipts. No review thread was resolved and no manual review requested. Parent
coordinates remaining independent review and eventual draft consolidation.
