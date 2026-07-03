# Handoff: Sidecar Memory Injection Stub

**Requested by:** Scott
**Date:** 2026-07-03
**Target repo:** `C:\Users\scott\Code\Obsidianify`
**Routed by:** Tess (Autonomy Engineer) — this is general build work on a shared tool, not an autonomy-config review. Tess declined to build it herself to keep her role lane (autonomy gates/roles/approval paths) from blurring into general feature work, and is handing it off for a build/general session (Bea) to implement.

## What Scott Asked For

1. A JSON "sidecar" memory file that Scott can update directly (hand-edit the file) **and** update by asking an assistant to make the edit — not something that has to be hand-maintained by re-deriving structure each time.
2. Once it exists, wire it into the existing Obsidianify memory injection pipeline so its contents are included whenever a session's memory packet is generated — not a separate, parallel mechanism Scott has to remember to check.

## Context

- Existing pipeline: `scripts/omi.py packet` generates a session context packet, delivered via the global Claude/Codex startup hook (see `docs/architecture.md`).
- Today that packet is built entirely from ranked Obsidian graph memory. This request adds a second, simpler, directly-editable memory source that should ride along in the same packet.
- No autonomy gate, trigger, or role-boundary question in the request itself — Tess's only involvement is flagging that once sidecar content is injected, it may be worth a later autonomy review (see Follow-Up below).

## Suggested Acceptance Criteria (Bea to confirm/refine)

- [ ] Sidecar JSON format and location defined (likely under `.obsidian-memory/`, consistent with the existing generated-packet convention in that directory)
- [ ] `scripts/omi.py packet` reads the sidecar JSON and merges/appends its content into the generated packet output
- [ ] Sidecar JSON is plain, hand-editable JSON — no required tooling to edit it directly
- [ ] Sidecar JSON also supports update-by-request — an assistant can append/edit an entry in the same file when Scott asks, without a separate mechanism
- [ ] Existing ranked-memory injection behavior is unchanged when the sidecar file is absent or empty (no regression)
- [ ] Tests added per the repo's existing `tests/` convention

## Key Files to Start From

- `scripts/omi.py` — packet generation entry point
- `docs/architecture.md` — describes the current injection flow (hook → packet → `.obsidian-memory/CLAUDE_SESSION_CONTEXT.md`)
- `.obsidian-memory/` (per-project, generated) — where the existing packet currently lands

## Open Questions for Bea

- One global sidecar file, or scoped per project (mirroring how ranked memory is already scoped per project)?
- Any size or entry-count limit, to avoid unbounded packet growth over time?
- How to handle overlap if both ranked memory and the sidecar reference the same topic — dedupe, both shown, sidecar takes precedence?

## Out of Scope

- No autonomy, gate, or role-boundary changes. This is additive to an existing tool, not a control-plane change.

---

**Tess Follow-Up (not part of this build):** once sidecar content feeds session context, it's worth checking whether injected content (e.g. "this repo auto-deploys on push") could change a role's *effective* authority beyond its contract — a role that sees bolder claims in its context may act bolder than intended. That's a genuine autonomy review, but it happens after this ships, as a separate pass.
