# Repository branch cleanup — 2026-10-14

Owner-authorized remote branch cleanup of `origin` (aungmyat1/AG-profit-trading-assit).
Base: `origin/main` = `b6ff527` (#218). Snapshot taken 2026-10-14T08:46Z.

## Method

- Lists are built from `refs/remotes/origin/*` only. Local `refs/remotes/pr/*` refs are left out because they are not on GitHub.
- Merged = tip is an ancestor of `origin/main` (79). Unmerged = not an ancestor (74, plus `wip/autodemo-b1`).
- Exclusions (KEEP): open-PR head or base, commit < 72h before the snapshot, `wip/*`, `rescue/*`, any C24/LSMC branch name (matched broadly: `lsmc`, `c24`, `v113`).
- Every unmerged branch (74, open PRs included) has a permanent tag `archive/<branch>` pushed to origin. Each tag SHA was verified equal to the recorded tip below.
- Deletion: approved by the owner. The agent's push was blocked by the local permission classifier, so deletions in the table are **PENDING_OWNER_RUN**. Run from a clone (a lease makes each delete fail if the tip moved):

```
# per row with action DELETE*:  git push origin --force-with-lease=refs/heads/<branch>:<sha> :refs/heads/<branch>
```

Restore any branch: `git push origin archive/<branch>:refs/heads/<branch>` (unmerged) or `git push origin <sha>:refs/heads/<branch>` (merged).

Note: `fix/s1-block-reason` (#220) moved ahead after the snapshot; its archive tag holds the earlier tip `e19f322`.

## Manifest

| Branch | Tip SHA | Set | Action |
|---|---|---|---|
| `agp-c3-asw-r2` | `7d5c8c7263c2f25d3c0cfd6f8b2f9be436364e97` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `agp-c3-asw-r3` | `d68e50f754ede39ca2126f828c8eec6a97192d6a` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `agp-c4-ccfd-logic` | `d91fd93971a17353430e73a2ffa3445f05840f69` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `agp/c2-symmap-final` | `986459c73076b3543be8e2c08c534363bf8421a3` | merged | DELETE (PENDING_OWNER_RUN) |
| `agp/c2-symmap` | `f2f2bcea96bd53198a617f6f295ec22b72f3cc94` | merged | DELETE (PENDING_OWNER_RUN) |
| `agp/c3-asw-gbpusd` | `976671e3fa0f94937a17a7e608378c6cb82f6cc2` | merged | DELETE (PENDING_OWNER_RUN) |
| `agp/c3-asw-ratify` | `7898dfdafa0a414e9b388dda95819967364505ba` | merged | DELETE (PENDING_OWNER_RUN) |
| `agp/d6-per-symbol-verification` | `db93ef3aecb3c446e3877b60c418c3c5c571d517` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `agp/d6-symbol-verification-followup` | `0a2f33f3f4e22332c7fe2e666a39aa2dae5f0643` | merged | DELETE (PENDING_OWNER_RUN) |
| `agp/lsmc-crypto-session-summary` | `2b24430ce0c2d9bf11eb0036b646ce1f8118735e` | unmerged | ARCHIVE_TAG + KEEP (C24/LSMC) |
| `agp/lsmc-mt5-failure-summaries` | `17cba014865ac865e085162d3007e86e5faeba7b` | merged | KEEP (C24/LSMC) |
| `arch/edge-ai-runtime-v1-foundation` | `0c576a56b1ed6a12ca35ae165468afcb8cae6e04` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `arena/01a0cfad-ag-profit-trading-assit` | `9615adaabca338b8167ec813726e8c6d46b77d34` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `arena/01a0e8f7-ag-profit-trading-assit` | `8af69ec599b73624802ec7b5e0d6b676ff5e6b82` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `arena/01a0ebe9-ag-profit-trading-assit` | `18d36cc670db0712cdbe976ea730165682d20464` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `arena/01a0fe6d-ag-profit-trading-assit` | `ad5aea9d7181ea50b124a4a5c50b506b8a6098a9` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `arena/01a0fed0-ag-profit-trading-assit` | `2a3f5641e078e79ea712bb3e1589ecb7a25cf286` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `arena/3b8a0571-ag-profit-trading-assit` | `24daa6bb91538b47cc73b8f9029ea5d49cced18e` | merged | DELETE (PENDING_OWNER_RUN) |
| `arena/422f8d69-ag-profit-trading-assit` | `da76e7a298c904c1db73782da8250ed29d1e6f10` | merged | DELETE (PENDING_OWNER_RUN) |
| `arena/61659945-ag-profit-trading-assit` | `350706d1ce9c7b417fe5c554b52f7060c8fe8c68` | merged | DELETE (PENDING_OWNER_RUN) |
| `arena/722f88fe-ag-profit-trading-assit` | `d9729cde5001827c9b4b056d8a255a2530fb15ac` | merged | DELETE (PENDING_OWNER_RUN) |
| `arena/863d367a-ag-profit-trading-assit` | `e47051901cae01dc1ca1a52802310cf0cf0ad5ac` | merged | DELETE (PENDING_OWNER_RUN) |
| `arena/863d367a-backlog-c` | `6b2dc0171d1d73d8290a5f15db2e4d195061c2da` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `arena/863d367a-crypto-r1` | `96ce1aa74f709672b71f67a115493a728fb94b74` | merged | DELETE (PENDING_OWNER_RUN) |
| `arena/863d367a-sched-r1` | `87ad4d78fe4aeffda9ee76b6a2190bb2f58969e2` | merged | DELETE (PENDING_OWNER_RUN) |
| `arena/9f23cafa-ag-profit-trading-assit` | `f50c25fcfdef205846f935a68b8160f412694462` | unmerged | ARCHIVE_TAG + KEEP (commit<72h(2026-10-12T11:35Z)) |
| `arena/ag-objective-fast-track-r1` | `dde9d7ad3008570eb4f48487987ecee727d77cc3` | merged | DELETE (PENDING_OWNER_RUN) |
| `arena/b5066ddb-ag-profit-trading-assit` | `c630dee04457bfe8b5370993895949619b7b6cad` | merged | DELETE (PENDING_OWNER_RUN) |
| `arena/bcbd6dfb-ag-profit-trading-assit` | `4b9121c09f62493cd8c4103556518efc0d09e101` | merged | DELETE (PENDING_OWNER_RUN) |
| `arena/c00891e9-ag-profit-trading-assit` | `63b8d434bba377fad304eaf00e220164bc2160ab` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `arena/ca7a6ec4-ag-profit-trading-assit` | `0fa1f3c1ed49504e785795e5327aaa49715e0eb0` | merged | DELETE (PENDING_OWNER_RUN) |
| `arena/cc31c23d-ag-profit-trading-assit` | `ea2b6c89cc40f2334e47df441a9e042d38012cf9` | merged | DELETE (PENDING_OWNER_RUN) |
| `arena/d1cea83b-ag-profit-trading-assit` | `a630a410c6bef943404540199ae4aa5c15e73c59` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `arena/db80182c-ag-profit-trading-assit` | `a20aa61bc8a3d4e5520c98c7e04b54ffb5d36719` | unmerged | ARCHIVE_TAG + KEEP (commit<72h(2026-10-11T17:19Z)) |
| `arena/e21ba5f5-ag-profit-trading-assit` | `e694b02c7eed24d721136e4d6f24a65a9c5eed34` | merged | DELETE (PENDING_OWNER_RUN) |
| `arena/eb35838a-ag-profit-trading-assit` | `914fc98b3245fde5e9992be8ea46a158bc57aa0e` | unmerged | ARCHIVE_TAG + KEEP (commit<72h(2026-10-11T15:02Z)) |
| `arena/f50ff77c-ag-profit-trading-assit` | `f68ba5ca770a1cf4374d67cfc4f43dd931c7677c` | merged | DELETE (PENDING_OWNER_RUN) |
| `arena/reference-actionability-impl` | `a70b61a18c111bead1827fc43dc0d8ab7852bb4e` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `audit/crypto-scanner-r2-1-candidate` | `761ede2715f10b2da831a88985a8fcecac9aca7e` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `audit/crypto-scanner-v1-r2` | `e675a0126ab652a7be22cb46df0c7dad5370c16e` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `audit/fx-opportunity-proposal-slice-v1` | `4d359014f7009b92738f62697e88d96b4c4d0298` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `audit/fx-stack-governance-record-v1` | `ef5708792a26e828c52b80d71d057ed453e2e02e` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `audit/main-protection-tripwire-v1` | `37141911eb99b7a119c2de720418d2211c439ff4` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `audit/oss-first-fx-ticket-discovery-v1` | `b684e7b82d6283be5eed5ca25ec3815e72c10d07` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `audit/panel-r3` | `e7b8f450d2967d8c973b0858b9c9aeb19e18b912` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `audit/panel-r5c` | `0fd1ec3eda8152a31a9c701ee65bca82e1c3c741` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `audit/tradeticket-vertical-slice-v1-r1` | `1564769ac3bd43a3b5aceaa37aa85cc662906e95` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `audit/tradeticket-vertical-slice-v1` | `e7dd985c11e00150f18925d993bca6f2f5ef53c6` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `audit/unit-f-friction-capture-r1` | `c422d9bb82e1422d5505366a9eecf2f8c5b1441a` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `audit/v1-followup-2026-10-07` | `0908eade9db040508bb913b72ee3aacdeb9ee3f1` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `audit/vt-spread-evidence-p6-r2` | `6fdc921a91bcd1913dc8804495cdcd5ed1395d7a` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `audit/vt-spread-post-asian-v1` | `476ba253dd6f578e96b8e740cdd3652c372a4bce` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `audit/vt-spread-post-london-v1` | `218b8725cd7537080a2f24e9b5c9c7763ddc2bad` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `audit/vt-vip-parity-spread-screen-v1` | `8931a7604e5f936e2caf07b0af3a9d754d8dec18` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `audit/wp7a-canonical-instrument-registry-v1-r1` | `471b1c026a04edc8ea34f61b0e6b2fce91c67000` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `audit/wp7a-canonical-instrument-registry-v1` | `9b185e7986e49b960d5b0af686834943723ca0e5` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `audit/wp7b-identity-gated-live-opportunity-v1` | `4b450ff36d9dc0940b0940613426d6e85e7c4450` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `c11/host-execution-import` | `5371ada8afec7595412e898eab659785ce9a805c` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `cf-r1` | `89200d34893b76aca2a5d8bc7eece1e8c924300e` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `claude/d6-asian-sweep-ready-off-port` | `9a355145c86d4e7e5fb761f4e2b82bde8b56112c` | merged | DELETE (PENDING_OWNER_RUN) |
| `claude/docs-live-2-next` | `e6078b88181d4d3a8bc7beeae1f12e34e10040d1` | merged | DELETE (PENDING_OWNER_RUN) |
| `claude/docs-live-2` | `b8a0b51124c820ec6b073580ff4b8ef69a496c10` | merged | DELETE (PENDING_OWNER_RUN) |
| `claude/focused-volta-yjneth` | `9826da2be6d9ec4b400c76523654fdff39bde0e0` | merged | DELETE (PENDING_OWNER_RUN) |
| `claude/merge-gate-remediation-r2` | `0f19f5ab7e5ad3b6f5789ab4eee608bfd4866dc5` | merged | DELETE (PENDING_OWNER_RUN) |
| `claude/modest-mccarthy-j0ll76` | `04c6b95974f6134ff63dda73f59899e7294530ec` | merged | DELETE (PENDING_OWNER_RUN) |
| `claude/od1011-owner-decisions` | `b0d0f9724d4c15b6372442b8bf953a36d6e1ec60` | merged | DELETE (PENDING_OWNER_RUN) |
| `claude/pr94-followup-r5` | `38c6535126e3f8c2c099030365d23968cca79a4d` | merged | DELETE (PENDING_OWNER_RUN) |
| `claude/regen-pr-contract-r5` | `2763e09e0f58f4a79bb49801cc47be8f8ac22d50` | merged | DELETE (PENDING_OWNER_RUN) |
| `claude/stale-fix-1` | `e63a82f8d3b653213765c3ed67c3cd93ce9deb25` | merged | DELETE (PENDING_OWNER_RUN) |
| `claude/stoic-cerf-tjp8xm` | `3027a665c25de3586f87ae969b8b9e4464414a73` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `claude/ticket-store-v1` | `f6f7744a40cd1c8acd6e12fe442fcb4a5046e0e9` | merged | DELETE (PENDING_OWNER_RUN) |
| `claude/vibrant-einstein-99xjfg` | `cc7e3757722fd3efcd2c573d9450b8d0afc129ee` | merged | DELETE (PENDING_OWNER_RUN) |
| `codex/ag-objective-integration-r1` | `3e7b48a92dc0c3b88978891c232066c6e2e5184b` | merged | DELETE (PENDING_OWNER_RUN) |
| `codex/agp-grade-01` | `872e5679c42af48df0e1839d4c32e40572a21cbd` | merged | DELETE (PENDING_OWNER_RUN) |
| `codex/agp-r6b-docs-01` | `32b08bf6e11968042bf38e60a5ee1572f298c04c` | merged | DELETE (PENDING_OWNER_RUN) |
| `codex/c17-asw-admission` | `761f00fa4594ee5598e810d925bbda51bf3f2985` | merged | KEEP (commit<72h(2026-10-12T19:27Z)) |
| `codex/clarify-project-status-and-objectives` | `462e6d4a836513a8858107aad2ebe5263c5ee223` | merged | DELETE (PENDING_OWNER_RUN) |
| `codex/crypto-window-gate-1` | `5e5cc9d6884de92a6fa6a12fc5a4436f17805466` | merged | DELETE (PENDING_OWNER_RUN) |
| `codex/docs-live-1-ci-fix` | `a86ed75c823949d1fbdc16a5768598b7d2b9009d` | merged | DELETE (PENDING_OWNER_RUN) |
| `codex/docs-live-1-sidecar-fix` | `a3712b2d377d679caca325cf41b13989c23c9ee8` | merged | DELETE (PENDING_OWNER_RUN) |
| `codex/docs-live-1` | `e596f4baccfd1a991a628b1574c10812be046e36` | merged | DELETE (PENDING_OWNER_RUN) |
| `codex/gen-files-ci-1` | `25b6cfe5f7520a7a72823158927a6eaac180c9d3` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `codex/market-data-contract-r2` | `942913eb820a3e3b91f8f0a4504a861263f3a8d5` | merged | DELETE (PENDING_OWNER_RUN) |
| `codex/merge-gate-1` | `59d96acf70584848126f31290dc60e5997fd6f02` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `codex/pr88-log-line-test-1` | `1861962e7b689ea34b51d28c0dfa809d62936d99` | merged | DELETE (PENDING_OWNER_RUN) |
| `codex/tg-scope-policy-1` | `7fd108b06a66de13e1daf1a18994b418e98d8b23` | merged | DELETE (PENDING_OWNER_RUN) |
| `crypto-logic-verify-r1` | `78989237593e10ef6c8a4f125ba765f9cea3e094` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `data/ccfd-recorded-60d` | `a4617677c77c8e1d96673ad8763937e7f5b53f90` | merged | DELETE (PENDING_OWNER_RUN) |
| `data/eurusd-d1-mt5` | `a44437e10edfa6b5d6f2a28db269ca1b06848f52` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `data/gbpusd-m15-recorded-fixture` | `1c07d7083ad1e933f1752ef645bb9eab390330ea` | merged | DELETE (PENDING_OWNER_RUN) |
| `data/recorded-ccfd-r2b` | `849bac21b4d0f0bca7186fe10e39af6c429efd26` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `data/recorded-m15-r2` | `ae0d4fead91ddda43d317e9e6c28232a2f2c3f2f` | merged | DELETE (PENDING_OWNER_RUN) |
| `data/vt-mt5-crypto-d1-pack-v1` | `1d78c310c4013d77c1580c0f983c72dff8d85677` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `docs-live-1-digest-fix` | `1904c8e4694c05be1080e5b585521e89acd64cc8` | merged | DELETE (PENDING_OWNER_RUN) |
| `docs-live-schedule-fix` | `18945921b2bae57d402906826e70b2466ecd9fb7` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `docs/agp-c2-decide-d1-d6-reconcile` | `07086d269f4b28642450cd8a30720492f2d271b0` | merged | DELETE (PENDING_OWNER_RUN) |
| `docs/agp-c2-decide-r2` | `ad10f1e79f2a5a89cb7bf85c4037851e26b026d2` | merged | DELETE (PENDING_OWNER_RUN) |
| `docs/agp-c6-objective-auto-demo-20261010` | `2e4371e53d02de557cabd1bd329483993578ac95` | merged | DELETE (PENDING_OWNER_RUN) |
| `docs/c14-auto-demo-ratification-20261011` | `f16014218999610d12e86088180ed71629e1a3ac` | merged | DELETE (PENDING_OWNER_RUN) |
| `docs/history-erratum-114-115` | `9a192ac6257d5a35ecb0f704730f4561e299a125` | merged | DELETE (PENDING_OWNER_RUN) |
| `docs/import-resolution-debt` | `50619902f7a8dea1a1edd6fb7cef3f25abedbc1f` | merged | DELETE (PENDING_OWNER_RUN) |
| `docs/objective-logic-verified-validation-20261007` | `6d2dfe52a2c47f392d83a604b8aa61c9fbf98b86` | merged | DELETE (PENDING_OWNER_RUN) |
| `docs/od1014-auto-demo-parallel-quality-r1` | `642bc2a3aca5f8a266e0b88dd498e7d9bb96902a` | unmerged | ARCHIVE_TAG + KEEP (open-PR,commit<72h(2026-10-14T07:56Z)) |
| `docs/od1014-objective` | `1f7ba9b67d201aafd4ecc62d0ad749e45fbdc6e2` | unmerged | ARCHIVE_TAG + KEEP (commit<72h(2026-10-13T19:12Z)) |
| `docs/register-c001-pre-result-correction` | `e04329973d33d5f10983ae842ac333a0a162b1bb` | merged | DELETE (PENDING_OWNER_RUN) |
| `docs/s1-demo-readiness-host-r1` | `252a0fdf41d3e6cb76a837af98aaa2da8697ff95` | unmerged | ARCHIVE_TAG + KEEP (open-PR,commit<72h(2026-10-14T07:23Z)) |
| `evidence/agp-c1-host-capture` | `558771860ce7f9f1c1c031ad4b3fa629829c8d73` | merged | DELETE (PENDING_OWNER_RUN) |
| `evidence/c24-lsmc-v112` | `6d9cad2bcceaa6b71c5ecef95886e1905d4f0fdb` | unmerged | ARCHIVE_TAG + KEEP (open-PR,commit<72h(2026-10-13T22:56Z),C24/LSMC) |
| `evidence/c25-oss-differential` | `1043914cefdf5c0030ff59a4c2a6490f06e93f8d` | unmerged | ARCHIVE_TAG + KEEP (commit<72h(2026-10-13T23:02Z)) |
| `feat/ag-v1-host-hardening-r1` | `ddaf83a70366935fe504807b0dd9aab46c0808f8` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `feat/agp-tg-confirm-01` | `e6691a6b786f2ad59fe425a2ae7c29d47885ab28` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `feat/c15-crypto-verification` | `3cba261b45b1ebe0c6294549b3ab955e482dd965` | unmerged | ARCHIVE_TAG + KEEP (commit<72h(2026-10-11T17:53Z)) |
| `feat/host-heartbeat-docs-live-3` | `dd5698257021471e50ad7668870ebd8e6b7f56bc` | merged | DELETE (PENDING_OWNER_RUN) |
| `feat/mt5-candles-readonly-r1` | `354b88d788b78a9aa0260f87883b69ae46f0bf10` | merged | DELETE (PENDING_OWNER_RUN) |
| `feat/mtf-control-shift-v1` | `1d1c75c92a7fda80696a56d4e1ccbe402f3ab71a` | merged | DELETE (PENDING_OWNER_RUN) |
| `feat/n-scope-authorization` | `8a7130606a6a12348bc7be87e328676966a9527f` | unmerged | ARCHIVE_TAG + KEEP (open-PR,commit<72h(2026-10-14T08:18Z)) |
| `feat/od1014-opportunity-lanes` | `4f6666f5265e6345ae8c33290a5a5489647d1f7d` | unmerged | ARCHIVE_TAG + KEEP (commit<72h(2026-10-13T19:00Z)) |
| `feat/read-only-session-scanner-v1` | `d21dc5680383b698b6104530efda3ba7afaa5d2e` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `feat/session-trade-v2-unified` | `e1ffe9f1e5ccfb9a336f1b4ae4289d41901ec5d2` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `feat/telegram-delivery` | `80dd66a16917b3e304a707e8dc492e8dafd9e062` | merged | DELETE (PENDING_OWNER_RUN) |
| `fix/145-evidence-root-test-isolation` | `62f62d65ffabacd6635dc9eb02e89cc33a31d648` | merged | DELETE (PENDING_OWNER_RUN) |
| `fix/74-merge-gate-hardening` | `6edf8ac2a2041e9a9c95c1569229ea73da6ea466` | merged | DELETE (PENDING_OWNER_RUN) |
| `fix/agp-c2-symmap-109-error-path-tests` | `48553dac6784b99e0e992ec0d6afca549c0d981b` | merged | DELETE (PENDING_OWNER_RUN) |
| `fix/agp-c2-symmap-109-isolated-remediation` | `892d2f6c63a7746ed91eaa40ab11894f62ff2961` | merged | DELETE (PENDING_OWNER_RUN) |
| `fix/agp-c2-symmap-109-mt5-lookup-contract` | `92a791cf2a6e52d3b21ca9db5ccae8b8af358102` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `fix/analyzer-fresh-computation` | `a59f0912009b47e6bc2c095b5fb31bb3e0cafbdc` | merged | DELETE (PENDING_OWNER_RUN) |
| `fix/ci-draft-pr-triggers` | `11161dd9c5db796d46e4bc1b1a1bb2baeedf1e85` | merged | DELETE (PENDING_OWNER_RUN) |
| `fix/crypto-research-labels` | `a051f9eb45d049427b147e310836c154e74d5b18` | merged | DELETE (PENDING_OWNER_RUN) |
| `fix/dst-2026-11` | `d1828b61da5aa703533c7c8e9d9f961a238bb3bf` | merged | DELETE (PENDING_OWNER_RUN) |
| `fix/heartbeat-cross-drive-commonpath` | `7aea8b16867ace2b1d32a9c6cd31f91eb8f26c7b` | merged | DELETE (PENDING_OWNER_RUN) |
| `fix/import-dependency-declarations` | `c7d6a38cf62b698400972a906e54fba4175b6dc7` | merged | DELETE (PENDING_OWNER_RUN) |
| `fix/lsmc-actionability-gates` | `f72711a9fbb82d08ac3d3ef732c38eedc8bca793` | merged | KEEP (C24/LSMC) |
| `fix/pr125-review-followup` | `70ce6d118fdbc6ab5cb76a583b82405ffe6afcdc` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `fix/r6b-default-deny` | `8a53baf94a94cbda3c5eef004bac0856652c8d45` | merged | DELETE (PENDING_OWNER_RUN) |
| `fix/r6b-step0-deny` | `4228c7819d4497ce80acd81d65a64c1e5e3f5263` | merged | DELETE (PENDING_OWNER_RUN) |
| `fix/ready-owner-binding` | `18432f0bb27f667dcd0a3fe0dfea703e13ed2b7a` | merged | DELETE (PENDING_OWNER_RUN) |
| `fix/s1-block-reason` | `e19f322f16ee4b5fdf90307a12e4577d2344d988` | unmerged | ARCHIVE_TAG + KEEP (open-PR,commit<72h(2026-10-14T08:36Z)) |
| `fix/stale-gate-trigger-close` | `34af0bfbab75d2d7bdbea3bb54297b1f54d6c792` | merged | DELETE (PENDING_OWNER_RUN) |
| `fix/symmap-reference-tests` | `89d4164046c97da9b9adc1d320825f138f56babf` | merged | DELETE (PENDING_OWNER_RUN) |
| `governance/od1012-account-999` | `3bd3cd98627e470ed73e7d861cfc51bb4a605fe7` | unmerged | ARCHIVE_TAG + KEEP (commit<72h(2026-10-11T18:27Z)) |
| `host/pass-b-evidence-b92f529-r` | `167bb2701d8193f7a6ee28af2b9d92e279da9e31` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `host/pr37-acceptance-rebased` | `3027a665c25de3586f87ae969b8b9e4464414a73` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `host/sched-r1b-always-on` | `99c30579c049771b75602a144cdec4121d30eba1` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `host/tasks-declare-v1` | `aca1060c19e8c18a23c107360c52d3a8423443f5` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `hotfix/d6-asian-sweep-ready-off` | `afbc49ab645bdad443f89fa9f1430e59c53f73a0` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `optimize/r1-deps-lint` | `8173db1533c4368ef5293ce33a6559cd51f3f129` | merged | DELETE (PENDING_OWNER_RUN) |
| `plan/edge-ai-runtime-v1` | `1ad7da4e667d3e0069d21a6a8b6c086a97b87df7` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `r3-diagnostics` | `ad3daaef62b62640453011a3431f2296584dbd63` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `research/attribution-v1` | `8703bcae28b687d9f4f98fa007a0a010f8372aa4` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `research/edge-program-v1` | `82e6e5cca329d1247f8a81aa308f25a80584c5fd` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `research/free-mt5-data-pipeline-r1` | `8570c957fc387c99704ea0d697a6e730296a3ff8` | merged | DELETE (PENDING_OWNER_RUN) |
| `research/harness-v1` | `7c306b57f6cc80394a4b94f88751eee7d2df7cfd` | unmerged | ARCHIVE_TAG + DELETE (PENDING_OWNER_RUN) |
| `test/telegram-summary-uncertain-no-resend` | `0d0783cc4c1986e36fd8d36741863a632038747b` | unmerged | ARCHIVE_TAG + KEEP (commit<72h(2026-10-12T08:47Z)) |
| `wip/autodemo-b1` | `953e9a5ea12006727050c88d924010f2af29274f` | unmerged | KEEP (wip/rescue,commit<72h(2026-10-14T08:34Z)) |
