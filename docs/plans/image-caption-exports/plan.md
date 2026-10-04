# Image-caption authoring and frozen export

Status: Verifying. Bounded caption slice authorized by the user's request to continue Tuldok. Local contract evidence and independent source review passed; representative browser evidence and coordinator publication remain pending.

## Outcome and authority

Use imported or existing Pumas-generated images, author and review a caption, search/select the records, then freeze a self-contained imagefolder dataset accepted by the training companion's actual consumer. Preserve the existing one-current-task workbench contract and original corner workflow.

Branch `feature/image-caption-exports` starts at `f2c37005af8ac043bd89276b5485cb169693f0cd` (grounded-text stack). Existing draft PRs, main `2fc4a46`, and the separate Torch-provider integration branch are unchanged. The coordinator owns publication, PR targeting, independent acceptance and eventual integration; this task creates local commits only. Retain this branch for review until the coordinator records its disposition.

Write set: `workbench.py`, `dataset_releases.py`, `static/workbench.html`, `static/workbench.js`, `tests/test_caption_exports.py`, `tests/fixtures/diffusion_check_image_data.py`, `tests/browser_captions.cjs`, `.github/workflows/tests.yml`, `README.md`, and this plan directory. No model, training, generation-provider, dependency or framework changes.

The existing Dataset/Workbench/Releases ownership and [decision](../../decisions/dataset-workbench.md) remain. Standards are MrScripty/Coding-Standards `dcc56f26e884ade260770beceba2501d3746200d`, following the core/router and affected implementation, verification/oracles/GUI, commit, documentation/tooling, frontend/accessibility, persistence/contracts/evolution/protocol, architecture/replay/code-design, security, concurrency and filesystem contracts. No Python/JavaScript language-specific profile is selected.

## Contract and composition

- Workbench owns `image_caption` with exactly `caption`, nonempty and at most 4,000 Unicode code points. Existing source IDs, provenance, source revision, append-only target history and protected parents/groups remain canonical. Generation prompts are retained separately, never converted to target text.
- Editor changes reset the proposed review choice to draft; the user explicitly selects human review. A saved task switch replaces the current target and retains the old target in history. Search includes caption text, with an explicit task filter.
- Releases accepts `image_caption_v1`; its omitted format still means the existing canonical release. No multi-task framework or universal exporter is introduced.
- The shared connected-component graph owns both split allocation and exported family identity. Every relevant unselected bridge, deleted tombstone, parent, protected group, content/pixel identity and legacy book/session relationship participates. A group is the hash of sorted complete-family record IDs, not one arbitrary group value. The relevant full-family snapshots are frozen beside selected records.
- The chapter-26 consumer is `examples/diffusion/check_image_data.py`, SHA-256 `6a4394308a4cc69b4ca965aca7f8459d7711ac9d51ce70492562c6ec6d806f94`. Its unmodified test snapshot is checked byte-for-byte. Producer rows contain only `file_name`, accepted-caption `text`, and component `group`. `validation` maps explicitly to `val`; all train/val/test splits are nonempty.
- The source lock protects snapshot/build. Normalized PNG bytes and actual decoded pixel identity are checked; the same asset-stream helper serves both formats. A complete temporary ZIP is fsynced, hashed and atomically published into the existing release directory. Failures remove incomplete staging and preserve previous releases. Later live edits/deletion never determine frozen output.
- Manifest is a frozen projection of independently owned source/target and split facts, not a new mutable authority. It retains source/target revisions, hashes, provenance, annotations and relevant transitive protected lineage. This promises frozen consumption, not rerunning an image provider or reproducing model training.

Caption semantics change within Workbench and editor; consumer projection changes within Releases and its contract fixtures. Transport composition and acquisition are reused. Necessary coupling is source/target revision and release consistency; no competing image store, registry, queue or adapter framework is retained.

## Evidence and acceptance

1. Caption bounds/shape, history and task/type/review conflict behavior: focused and real SQLite integration, automated.
2. Actual exported PNG/JSONL consumed by the unchanged pinned validator, positive and isolated negative trees: contract and release-artifact, real Python/Pillow/filesystem, automated. Includes EXIF normalization, duplicate pixels, missing captions/groups, cross-split groups, empty splits and advisory small images.
3. Full connected family and deleted/unselected ancestry, preserved legacy assignments, stale/tampered-source rejection, deterministic frozen identity, later edit/delete/reopen: integration and artifact, real SQLite/filesystem, automated.
4. Browser edit → draft → review → reopen → caption/task filter → selection → ZIP download, interrupted/repeated actions, keyboard review reset and narrow layout: user-workflow, representative Linux/Chromium, automated plus screenshot inspection. Pending hosted execution.
5. Existing corner, images, grounded text, canonical release and controller regressions: automated. Local full Python/controller checks passed; browser regressions require a runner able to launch Chromium.

Local environment: Python/Pillow and Node 24; no installs. Repo and fixtures use a separate temporary filesystem, retaining at least 1.5 GiB available on the overlay. Native Chromium fails creating its IPC socket with `Operation not permitted`, including a reviewed escalated run. That is an unavailable local browser claim, not acceptance. Hosted CI is the existing admitted representative path and now includes the caption regression.

No claim covers real caption quality, rights, sensitive metadata removal, perceptual/semantic deduplication, training throughput or trained-model quality.

## Exactly one next slice

Publish the reviewed candidate through the coordinator, run exact-head hosted CI, inspect caption screenshots, and resolve concrete failures before the coordinator accepts or integrates this slice.

[Execution ledger](execution-ledger.md).
