# Independent QA hygiene review

Reviewed the cleanup worktree against `309a87d753f97b245385f8d6db20353ab536a836`. No production owner, model, simulation, public application or protected branch changes were made by this review.

The baseline contains all 3,834 original report paths (195,517,431 bytes); its `docs/plans` tree is `d8480c55bcde971ce26022512422f61565eac2f8`. Retaining the reachable ancestor and retrieval instructions preserves original bytes without another large archive. All 11 relocated caption/UI input files match that ancestor byte for byte. The four compressed oracle receipts, 40 historical outcome source hashes and extracted 43-command registry were checked independently. Legacy exit-only outcomes are labeled without inferring source qualification. Authored review prose and the real-Pumas observation remain accessible.

New output routing uses fresh ignored directories and JPEG quality 85 for ordinary screenshots. Original image data and PNG fixtures remain lossless. The qualification runner enumerates only each gate's output subtree; it neither scans historical reports nor copies earlier runs. The fake-gate regression covers two runs, historical/prior-output exclusion and unchanged inputs. Current source/fixture/report destinations are rejected; CI uploads the new ignored QA tree.

Two review findings were sent to the owner. Nine screenshot callers originally supplied filenames to a directory helper; the owner corrected them, and the workbench browser check now passes with actual desktop/narrow JPEG files. Historical summaries originally treated exit-only successful gates as nonpassing; their corrected compact summaries match the original schemas.

Independent checks passed: the routing Node regression, three QA qualification Python tests, 15 caption-import Python tests, UI capture syntax, the actual workbench Chromium lifecycle/download/narrow-layout check, and the rights artifact regression's two actual browser reruns. The latter preserved all 13 tracked fixture inputs after each run and retained four JPEG captures in distinct ignored directories. This is focused precommit review; the owner's complete clean-checkout gate run remains necessary.

The two additional guardrail findings are closed. Resume now requires a complete, hash-matching manifest within that gate's own direct `artifacts-*` directory; the regression proves unchanged reuse, corruption-triggered rerun and deletion-triggered rerun. The directory helper now resolves and validates the final suite base; the fake-repository symlink regression rejects an alias into authored fixtures without creating files there. The final routing Node and three QA Python tests passed independently after these changes.

Precommit review is cleared with no remaining blockers. Complete clean-checkout qualification remains the owner's next gate; this review does not claim that pending aggregate has passed.
