# What is Continuity?

Continuity standards adopted: 1.3.0 (2026-10-02).

Continuity is this project's primary documentation framework. It keeps the knowledge needed to understand, run, change, and resume the project in one organized home. It is maintained project knowledge, including implementation meaning, decisions, uncertainty, and the current stopping point.

Its purpose is continuity for people and agents: someone returning after months should find the right commands and context, and an agent should find relevant source without wasting reads. Token savings are a goal, not a guarantee. There is no service or agent runtime to install.

## Find the right context

| Document | Responsibility |
| --- | --- |
| [README](README.md) | Project purpose and human navigation |
| [Status](status.md) | Current state, stopping point, next steps, and actual verification |
| [Setup](developer/setup.md) | Prerequisites, commands, configuration, and troubleshooting |
| [Architecture](developer/architecture.md) | Components, flows, boundaries, and design reasoning |
| [Data model](data/model.md) | Data meaning, invariants, relationships, and authoritative schema routes |
| [Agent map](agent/map.md) | Request vocabulary and precise routes to relevant source/details/tests |
| [Agent contract](agent/instructions.md) | Reading and documentation-maintenance requirements |

Humans start at README or status. Agents read the contract, status, and complete map, then the relevant details and actual source. Read this explanation when adopting the framework or when its role is unclear; it need not be reloaded at every task. The eight durable documents include this page; optional detail grows only where useful.

## Authority and maintenance

Continuity is more than a routing index: setup, architecture, models, decisions, and status carry project knowledge. Links keep each fact in one authoritative place. Existing locked specifications may remain outside this directory until an approved migration relocates them; preserve their authority and record source/spec disagreements. Source establishes implemented behavior; specifications establish required behavior where repository rules say so. Neither justifies silently inventing intent or resolving contradictions.

Current state/issues, plans, and dated historical claims have distinct homes. Review a link's destination role as well as its existence. Qualify intended invariants with known implementation limitations beside the claim. Completed documentation-installation evidence stays in linked optional detail; status keeps the current stopping point and unresolved work.

Before every otherwise-authorized commit and every handoff, review changes, update affected documentation alongside implementation, and review status and changed routes. Unchanged documents need no ceremonial edit. See the contract for the full routine. Root agent instruction files remain discovery entry points and preserve their existing rules. Adding Continuity does not waive those rules or their required reads.

## Initialization and optional migration

Initialization can derive documentation from an undocumented codebase or reconcile existing documentation. A temporary `initialize.md` is bundled with the starter and removed after successful initialization; interrupted work keeps it for resumption.

After initialization, the agent asks whether to fully migrate existing documentation or keep both. Full consolidation is optional: an explicit full-migration answer authorizes transfer and cleanup through `continuity/migrate.md`; reading the prompt alone does not. A keep-both answer preserves old docs with clear ownership and removes the installed migration prompt. Successful full migration removes it too. Pending decisions, interrupted migrations or incomplete required verification retain it for resumption. For future migration, obtain the prompt from [Continuity's source repository](https://github.com/NicolasCapparelli/continuity/blob/main/template/continuity/migrate.md).

Migration preserves agent-specific instruction files, legal notices, required public entry points, locked decisions, and unique historical evidence. Agent instructions may need updated documentation paths, but their rules and files survive. No migration or cleanup is authorized merely because old documentation overlaps Continuity.
