# ListHub Vision

> **Status:** Living document. Last updated 2026-04-07 by Jacob Cole.
> **Companion:** Strategic tickets in beads (see "Related work" below).

## North star

**ListHub is the publishing layer for everything Jacob knows.**

Today it's a Flask app that hosts hand-curated lists. The destination is a system where Jacob's *entire* personal knowledge corpus — `~/memory/`, research bundles, daily notes, project specs, person profiles — can be selectively projected to the public web with fine-grained per-item visibility, while the private master copies stay where they are (the filesystem, Noos, Thoughtstream, etc.).

In one sentence: **ListHub is the membrane between Jacob's private knowledge and the public internet.**

## Why this matters

Jacob accumulates knowledge in many private stores (`~/memory/`, beads tickets, Thoughtstream notes, Noos, Apple Notes, iMessage threads). Most of it is private by default, and rightly so — it contains names, phone numbers, raw quotes, family context, business-sensitive material. But meaningful chunks of it are *publishable* once sanitized: research roundups, recommended-reading lists, person directories, project documentation, distilled insights.

Right now there's no clean way to do that projection. The current workaround (see brainstorm ticket **AIB-q9h**) is to maintain *paired files* — a private master in `~/memory/research/<area>/<topic>.md` and a sanitized public sibling on ListHub at `jacobreal/<topic>`. That works for one or two topics, but it duplicates work and drifts immediately.

The vision is that ListHub takes over that drift problem.

## What "publishing the whole memory" looks like

### Layer 1 — File-system sync
Point ListHub at a directory (e.g. `~/memory/`). It walks the tree, treats each markdown file as a candidate item, and syncs them to the ListHub database.

- Default visibility: `private` (everything must be opted into publication)
- Front-matter declares the per-file publication policy:
  ```yaml
  ---
  listhub_visibility: unlisted  # private | unlisted | public | public_edit
  listhub_slug: depression-resources
  listhub_sanitize: true
  ---
  ```

### Layer 2 — Sanitization
When `listhub_sanitize: true` is set, ListHub generates a *derivative* sanitized version at publish time:

- Strip phone numbers, email addresses, full names of non-public-figure people
- Replace personal context with generic role descriptions ("a senior Iyengar teacher in Boston" instead of "[[Jarvis]] (+1 617-794-5622)")
- Detect PII at publish time and warn before going public
- The original master stays untouched in `~/memory/`

### Layer 3 — Cross-references
- Each ListHub item knows its private origin file
- Each private master file has a `public_listhub:` field pointing at the ListHub URL
- On the dashboard, show the lineage: "this public list is derived from `~/memory/research/health/depression-resources.md`"

### Layer 4 — Discovery
- Topic dashboards: "in `health/`, you have 12 private files and 3 published"
- Public/private filter on the dashboard (see **AIB-wfz** — backend already exists, just needs UI)
- Visibility badges on every item view (see **code-6gy**)

## What this enables

- **Zero-drift research bundles.** Edit the private master, publish the sanitized sibling automatically.
- **A "garden" model.** Jacob's `~/memory/` becomes a quietly-public knowledge garden — each note can be promoted with a single front-matter change.
- **PII safety net.** The system warns before publishing anything containing a phone number, address, or non-public person name.
- **Cross-store unity.** Eventually, the same model extends to Noos (knowledge graph nodes with per-node visibility), Thoughtstream notes, beads tickets — anything Jacob writes can flow through the same membrane.

## Adjacent technologies (inspiration)

- **Obsidian Publish** — but with per-note visibility instead of vault-level.
- **Quartz** — digital garden static-site generator.
- **Noos's three-layer knowledge model** — local daily logs → curated briefing → shared graph. ListHub is the "shared graph" projection layer for non-graph content.

## Near-term roadmap (concrete)

1. **Manual research-bundle convention** *(working today)* — see **AIB-q9h**. Private master in `~/memory/research/<area>/<topic>.md`, public sibling on ListHub, paired by slug, cross-linked by front-matter. Operationalized in the depression-resources bundle (2026-04-07) as the first reference implementation.
2. **Dashboard visibility filter UI** *(small, well-scoped)* — see **AIB-wfz**. Backend exists; template needs filter chips.
3. **Visibility badges on items** *(in flight)* — see **code-6gy**.
4. **Front-matter spec** *(spec only, not built)* — define `listhub_visibility`, `listhub_slug`, `listhub_sanitize`, `public_listhub` (reverse pointer).
5. **Memory → ListHub one-shot import script** — walks `~/memory/`, finds files with `listhub_visibility: public/unlisted`, creates corresponding items.

## Long-term roadmap (speculative)

6. **Live sync daemon** — `bd sync`–style sync between `~/memory/` and ListHub.
7. **Auto-sanitization pipeline** — LLM-driven PII detection + redaction, with human approval before publish.
8. **Cross-store ingestion** — same membrane for Noos nodes, Thoughtstream notes, beads tickets.
9. **Bidirectional editing** — public_edit items on ListHub flow back into `~/memory/` as patches Jacob can review.
10. **The "agent garden" model** — agents (Codex, Claude Code, future ones) can read the public layer of Jacob's memory as context, without seeing the private layer.

## Related work

| ID | Status | Title |
|---|---|---|
| **AIB-5ss** | open · P2 · feature | **ListHub vision: publish entire personal memory with selective public/private** *(this doc's master ticket)* |
| AIB-q9h | open · P3 · chore | Research-bundle convention: paired private/public files for ListHub topics |
| AIB-wfz | open · P3 · feature | ListHub: Dashboard visibility filter buttons (backend exists, UI doesn't) |
| code-6gy | open · P2 · feature | ListHub: Show visibility badges on items in explore/featured/profile |
| code-umo | open · P2 · feature | ListHub: Add 'unlisted' visibility option |
| code-gm6 | open · P2 · feature | ListHub: Per-user sharing with write permission |
| code-8kv | open · P1 · chore | ListHub: Keep API docs and GUI in sync for sharing/visibility features |
| code-47z | open · P1 · feature | ListHub: Agent self-service onboarding (signup, API key, MCP/skill) |

## When to revisit this doc

- Whenever a new ListHub feature ticket lands that touches visibility, sync, or PII
- After the depression-resources reference implementation has been used in anger (target: ≥3 research bundles built with the manual convention)
- When the front-matter spec is drafted
- When the one-shot import script is built — this doc should reflect the actual schema at that point
