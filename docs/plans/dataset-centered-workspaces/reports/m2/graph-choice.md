# S1: bounded graph choice for the first real image workflow

Decision: use a Tuldok-owned fixed DAG for this M2 slice. Pantograph adoption is
rejected for this bounded integration, not declared impossible in the future.
The approved plan explicitly permits this fallback when a supported host cannot
be demonstrated. Do not add a second production scheduler or a general process
node. The M1 fixture editor remains disposable, isolated presentation work.

The independent read-only S1 worker inspected exact Pantograph source
`256b6b94ece4dbbaa1fb236bc4092ad08aa63525` in `/tmp/pantograph-s1`.

- [The host contract](https://github.com/MrScripty/Pantograph/blob/256b6b94ece4dbbaa1fb236bc4092ad08aa63525/docs/headless-workflow.md)
  documents Rust, generated C#/UniFFI and BEAM. Python workflow nodes are child
  consumers, not a Python host binding. The HTTP adapter is an outbound proxy,
  not a headless REST server supplied to Tuldok.
- [The binding build](https://github.com/MrScripty/Pantograph/blob/256b6b94ece4dbbaa1fb236bc4092ad08aa63525/crates/pantograph-uniffi/Cargo.toml)
  requires Rust 1.92.0, UniFFI 0.28.3 and a native library. Rust/Cargo, an installed
  Python host module and a tracked Python host package/native artifact were
  absent in this environment. Native sessions, cancellation and shutdown were
  not executed and are not qualified.
- [The graph package](https://github.com/MrScripty/Pantograph/blob/256b6b94ece4dbbaa1fb236bc4092ad08aa63525/packages/svelte-graph/package.json)
  is source-only 0.1.0 with Svelte 5 and XYFlow peers. Direct Node import failed
  on unbuilt module imports. It requires another frontend build boundary.
- Workspace locks contain 1,116 Rust packages and 796 npm entries. These are
  workspace totals, not a measured minimal runtime. No binary/startup/RAM
  measurement is claimed. The [README license section](https://github.com/MrScripty/Pantograph/blob/256b6b94ece4dbbaa1fb236bc4092ad08aa63525/README.md#license)
  identifies Apache-2.0 license material versus MIT OR Apache-2.0 metadata;
  [release documentation](https://github.com/MrScripty/Pantograph/blob/256b6b94ece4dbbaa1fb236bc4092ad08aa63525/docs/release.md)
  records unqualified release packaging.

The first real recipe has exactly five owned stages: frozen image release,
validate/export, TinyCNN CPU train, validation/test evaluation, publish verified
artifacts. Real parameter editing is limited to epochs, batch size, learning
rate and seed. Arbitrary node definitions, transports, commands, devices,
pretrained models, audio inference and other trainers remain unavailable.
Graphs save and validate on the server; UI code presents the returned contract
and never supplies a second authority for executable graph semantics.

M2 requires a versioned PostgreSQL extension. MB validates the exact catalog
structure and definition hash, so adding tables or refreshing the signature at
startup is not a migration. The extension must preserve existing owners,
unknown-version/drift refusal, exact backup/restore and dataset identity. It is
not another SQLite migration or a sidecar database. Real runs need immutable
release/graph/runtime snapshots and durable submission receipts before a child
can start. Training stays outside DB locks; cancellation requires observed
child cessation, and interrupted training never resumes a partial checkpoint.

Test-result inspection and reuse are durable exposure events. Predictions bind
to frozen source/annotation revisions; opening a current record for correction
must not rewrite the previous result or imply fresh test holdout evidence.

This decision admits no M2 result by itself. Combined-app qualification and the
actual reader, trainer, lifecycle, browser and artifact gates remain required.
