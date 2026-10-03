# Documentation migration record (2026-10-02)

Approval: the owner answered "full migration please" to the question asked at the end of initialization. Scope: all ordinary project documentation. Status carries the current outcome; this file is optional evidence.

## Recovery and comparison base

- **Recovery location:** git commit `3d6a6fc` ("V1 Release"). All ten originals were tracked and had no uncommitted edits when migration began (`git status` clean for those paths). Restore one with `git show 3d6a6fc:<old path>`. This lasts as long as that commit exists in the repository. No separate backup was made, and no commit was created.
- **Comparison method:** each new file was diffed against `git show HEAD:<old path>`.
- **Allowed differences:** the inserted relocation note (blank line plus one blockquote line directly under the title), and repaired relative links. Every other line was unchanged (no other differences were found).

## Per-file inventory

| Old path | Lines | New path | State before | Differences from the original | Outcome |
| --- | --- | --- | --- | --- | --- |
| `DevGuide/architecture.md` | 160 | [developer/air-architecture.md](../../developer/air-architecture.md) | tracked, clean | note only | moved |
| `DevGuide/external-dependencies.md` | 161 | [developer/external-dependencies.md](../../developer/external-dependencies.md) | tracked, clean | note only | moved |
| `DevGuide/web-console.md` | 134 | [developer/web-console.md](../../developer/web-console.md) | tracked, clean | note, plus 1 link repaired (`web/README.md` → `user/web-console.md`) | moved |
| `DevGuide/MARINE/README.md` | 64 | [developer/marine/overview.md](../../developer/marine/overview.md) | tracked, clean | note, plus 1 link repaired (AIR architecture path) | moved |
| `DevGuide/MARINE/architecture.md` | 237 | [developer/marine/architecture.md](../../developer/marine/architecture.md) | tracked, clean | note, plus 1 link repaired (AIR architecture path) | moved |
| `DevGuide/MARINE/external-dependencies.md` | 166 | [developer/marine/external-dependencies.md](../../developer/marine/external-dependencies.md) | tracked, clean | note only | moved |
| `hardware/README.md` | 78 | [developer/hardware.md](../../developer/hardware.md) | tracked, clean | note only | moved |
| `web/README.md` | 62 | [user/web-console.md](../../user/web-console.md) | tracked, clean | note, plus 1 link repaired (`DevGuide/web-console.md` → `developer/web-console.md`) | moved |
| `README.md` (root) | 184 | [user/api.md](../../user/api.md) | tracked, clean | note only | content moved; the root file was replaced by a short landing page (below) |
| `DevGuide/README.md` | 21 | none | tracked, clean | — | **Removed without a destination.** It was only an index of the DevGuide files plus a sentence on the AIR and MARINE split, and the same navigation is in [continuity/README.md](../../README.md) and the marine overview. Approved omission; recoverable from `3d6a6fc`. |

Totals: 10 originals. 9 were transferred with their content intact and 1 (the DevGuide index) was removed without a destination. Of the 10 files, 9 were deleted and the root `README.md` was rewritten in place. The now-empty `DevGuide/` and `DevGuide/MARINE/` directories were removed with `rmdir`. There was no `docs/` directory and there were no other assets (no images or diagrams).

## Retained entry points and other exceptions

| File | Why kept | State |
| --- | --- | --- |
| `README.md` (root) | Required repository landing page. | Rewritten to a short overview, quick-start commands, and links into `continuity/`. |
| `AGENTS.md`, `CLAUDE.md` | Agent instruction/discovery files (protected). | Unchanged by migration; they point to Continuity. |
| `hardware/include/config.example.h`, `.env.example` | Configuration templates, not documentation. | Untouched. |
| `continuity/migrate.md` | Prompt used for this migration. | Removed at the end of the run (see Cleanup). |

No locked specifications, legal notices, CI, or documentation builders exist in the repository.

## Reference repairs

- Source comments: `hardware/platformio.ini` (pin-map pointer, now `continuity/developer/hardware.md`) and `app/aircraft_db.py` (docstring, now `continuity/user/api.md`). Both are comment-only edits with no executable change; `compileall` on `app` passed afterwards.
- Continuity documents: 32 links to the old paths were rewritten mechanically, and their labels and surrounding prose were then edited by hand ([README](../../README.md), [status](../../status.md), [map](../../agent/map.md), [architecture](../../developer/architecture.md), [setup](../../developer/setup.md)).
- Remaining mentions of the old paths are intentional history: the relocation notes, this file, [initialization evidence](../documentation/initialization.md) (annotated as historical), and the "was `…`" labels in status.

## Reconciliation limits

Migrated files keep their original text. The known disagreements with source (stale marine status line, "cosmetic" MODE, hardware TODO table and touch-bus note, README model precedence, missing marine endpoints) were **not** rewritten; each file's note says so and [status → Documentation drift](../../status.md#documentation-drift) lists them.

## Verification

- Link, anchor, and source-path checker over `continuity/**`, `AGENTS.md`, and `CLAUDE.md` after migration: all relative links and anchors resolve. The only flagged items were backticked old doc paths in historical prose (checker false positives).
- Routing walkthrough (post-migration), "where do I find the endpoint example and the caching rules?": [map → AIR nearby endpoint](../../agent/map.md#air-nearby-endpoint) → [user/api.md](../../user/api.md#endpoints) → `app/main.py` `nearby` for the real parameters. Resolved. A second, "how do I flash the device?": [map → Device firmware](../../agent/map.md#device-firmware) → [developer/hardware.md](../../developer/hardware.md#build--flash). Resolved.
- Not run: a live middleware, console, or firmware build. Migration touched documentation and two comments only. Tested code state: `3d6a6fc` plus the working-tree changes listed in `git status`.

## Cleanup

`continuity/migrate.md` was removed after the checks passed, as its final step requires. Future migrations need a fresh copy from the [Continuity source repository](https://github.com/NicolasCapparelli/continuity/blob/main/template/continuity/migrate.md).
