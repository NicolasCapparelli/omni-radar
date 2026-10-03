# Agent contract

Continuity is this project's primary documentation home for understanding, changing, and resuming work. Read [what Continuity is](../about.md) when unfamiliar with it. Full documentation migration is optional and requires explicit user approval; discovering its prompt is not authorization.

Follow applicable repository instructions. At task/session start read this file, [status](../status.md), and the complete [map](map.md); reuse unchanged loaded context. Match request vocabulary/boundaries, then read only relevant model sections, local guides, source, and tests. Follow dependencies and expand investigation when evidence warrants it.

Inspect actual source before changing behavior. Missing/stale routes: search source, establish ownership, repair the map. Routing never prohibits investigation. Read user guides for affected user behavior and decisions/history only when their reasoning matters. Avoid recursive documentation/schema reads and vendor/generated/build/dependency orientation unless needed; use map exclusions.

Initialization is the broad-coverage exception: inventory/search first, then inspect substantive source across capabilities. Never blindly ingest every file.

## Every commit and handoff

Commit only when otherwise authorized. Before each commit and every handoff, including uncommitted work:

1. Review the relevant diff; update affected docs with implementation. For partial commits, describe committed behavior accurately and distinguish outstanding working-tree changes. Intermediate edits may defer updates until this boundary.
2. Review status; update changed state, stopping point, next steps, blockers, or verification. State no active work/no established next task when applicable. History alone does not establish human intent.
3. Check changed links/routes. Report actual checks, results, scope, tested code state, and uncertainty. Source inspection is not runtime verification; never claim an unrun check or identify a future documentation commit as tested.

| Change | Documentation / investigation |
| --- | --- |
| Component added/moved/removed/reassigned | Map/local guide; architecture if overall design changes |
| Data access/validation/serialization/identity/relationship/lifecycle | Model/schema routes; producers, consumers, conversions, migrations |
| User behavior | Affected usage/troubleshooting |
| Setup/commands/configuration/verification | Setup and verification routes |
| Consequential durable decision | Architecture or optional decision record |
| State/unfinished work | Status |

No ceremonial edits: review can require no change. Keep one home per fact; label plans, inferences, unknowns. Preserve existing rules and discovery pointers. Tools without root-file discovery need an explicit instruction pointing here; compliance is not guaranteed.

Review destination roles and obsolete active reading instructions, not only link existence. Qualify intended invariants with known implementation limits beside the claim. Keep completed documentation evidence optional; status retains current blockers and outcomes, and map dependencies select precise route anchors.
