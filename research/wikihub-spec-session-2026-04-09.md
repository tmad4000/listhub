# WikiHub — Spec Session (2026-04-09)

**Participants:** Jacob, Harrison (via transcripts), Claude
**Status:** Spec phase — no implementation yet
**Name:** WikiHub (locked)

---

## What is WikiHub

**One-liner:** GitHub for LLM wikis. A hosting platform where humans and their coding agents collaboratively build, version, publish, and fork Karpathy-style markdown knowledge bases, with per-file visibility and a native agent API.

**Positioning:**
- Not llmwiki.app (which runs the agent for you)
- Not Obsidian Publish (no agent story, no fork)
- Not Quartz (static, solo, no collaboration)
- Is the memory layer + social graph + git host for the Karpathy pattern. We host; your agent writes.

**Core principle (from listhub):** Infrastructure, not app. The platform stands alone. Agents are clients. "We're the memory layer, bring your own brain."

---

## Decisions made

### 1. Codebase — completely from scratch
Not extending listhub, not forking it, not using it as a backend via API. New repo, new product. Structurally copies listhub's architectural DNA (per-user bare git repos, REST API, API keys, per-file visibility) but doesn't graft onto the existing codebase.

**Why:** A wiki is structurally not a list — it has a tree (folders), wikilinks (graph), an index.md root, and is forkable as a unit. Grafting those onto listhub's flat item model would fight the existing schema at every turn.

### 2. Data model — new first-class Wiki object
Each user can have N wikis. Each wiki has its own slug, settings, and a tree of pages with public/unlisted/private per file. Clean URL: `/@user/wiki-slug/page`. Forkable as a unit.

### 3. Schema — Karpathy three-layer, gentle nudges
New wikis get scaffolded with `raw/`, `wiki/`, `schema.md`, `index.md`, `log.md`. Not rigidly enforced — users can ignore it — but templates, agent hints, and the default render assume the pattern. Opinionated default, escape hatch exists.

### 4. Rendering — server-rendered Jinja with wikilink resolver
Each page rendered on request from the bare repo. `[[Wikilinks]]` resolve. Graph view + index.md as landing. Matches listhub's no-JS-framework convention. Dark theme, CSS variables.

### 5. Social layer — GitHub-for-wikis ambition (v1)
Public wikis are forkable, cloneable, star-able. Agents can open "suggested edits" (PR-like) against others' public wikis. Browse/explore public wikis.

### 6. Agent surface — client-side only for v1
MCP server + REST + API keys first-class on day one. The "point your coding agent at this and say 'make me a wiki'" flow is the core pitch. No server-side LLM in v1.

### 7. Ingestion (v1)
- **git push** existing wiki repo
- **Zip/folder upload** via web UI (drag-drop, unpacked into bare repo)
- **Scaffold blank wiki** ("Create wiki" button seeds three-layer skeleton)

### 8. Ingestion (v2 tickets)
- Paste unstructured text → LLM generates wiki (server runs coding agent or Anthropic tool-use flow with our API key; lean toward coding agent)
- Connect URL / existing public wiki (clone/scrape into a new wiki)

### 9. Server-side agent (v2 ticket)
Platform-provided key, not BYO-key. "Run ingest / lint / query against this wiki" button in the web UI. Likely a coding agent on our infra. Sub-decision deferred: headless coding agent vs raw Anthropic API with write-file tool.

---

## Architecture — source of truth model

**Bare git repo = source of truth. Database = derived index.**

```
        ┌──────────────┐     writes via REST/Web
        │  Flask API   │ ────────────────────┐
        └──────┬───────┘                     │
               │ reads                       │ git plumbing
               │ (metadata)                  │ (hash-object, update-index,
               ▼                             │  write-tree, commit-tree,
        ┌──────────────┐                     │  update-ref — NO hooks fire)
        │   Database   │                     │
        │  (derived)   │                     ▼
        │              │              ┌──────────────────┐
        │ wikis, pages │◀─── upsert ──│ repos/<u>/<w>.git│
        │ wikilinks    │   (admin     │  (source of      │
        │ search index │    API)      │   truth)         │
        └──────────────┘              └────────▲─────────┘
                                               │
                                               │ git push / pull
                                       ┌───────┴────────┐
                                       │   User / agent │
                                       └────────────────┘
```

**Two-way sync (copied from listhub pattern):**
- DB→git: web UI / REST writes commit via git plumbing with `GIT_INDEX_FILE` (no working tree). `git update-ref` does NOT fire hooks.
- Git→DB: `post-receive` hook parses pushed `.md` files and upserts Page rows via admin API.
- No infinite loop because `update-ref` ≠ `git-receive-pack`.

**Three CLI commands from day one:**
1. `wikihub reindex <wiki>` — rebuild DB rows for one wiki from HEAD
2. `wikihub reindex --all` — nuke-and-rebuild everything
3. `wikihub verify <wiki>` — diff DB vs HEAD, report mismatches

### Key decision: content does NOT live in the database

The DB stores metadata + search index only. Content is served from git.

**DB stores:**
- `pages` table: id, wiki_id, path, title, visibility, frontmatter_json, excerpt (~200 chars), content_hash, timestamps
- `page_fts` (FTS5 or tsvector): search tokens + snippets, treated as a cache
- `wikilinks` table: from_page_id, to_path, resolved_page_id
- Social: wikis, users, stars, forks, suggested_edits, api_keys

**Content reads:** `git cat-file` from bare repo (~3-5ms per file). Batch reads via `git cat-file --batch`.

**Why not replicate content in DB:**
1. Sync bug surface proportional to what you duplicate. Listhub wraps sync in try/except pass — that's a code smell from this exact duplication.
2. "Git is source of truth" is either true or marketing. If you serve reads from the DB, the DB is your actual source of truth.
3. Git single-blob reads are fast (~5ms). Not a performance problem.
4. FTS5 external content mode handles search without storing full content in the main table.
5. Wikis are larger than listhub items — doubling storage for every file is wasteful.
6. Reindex becomes simpler: walk HEAD, parse frontmatter, extract wikilinks, feed FTS. No content copying.

### Open fork: SQLite vs Postgres

**Recommendation: SQLite for v1.** Reasons:
- Listhub already runs on it — port code verbatim
- SQLite with WAL mode handles wiki-scale write concurrency fine
- FTS5 is excellent and simpler than tsvector
- No Postgres to run, no connection pool, no Alembic
- The derived index can be rebuilt from git at any time — migrating to Postgres later is a rebuild, not a migration

**When Postgres would matter:** 10k+ concurrent users, complex many-to-many social queries, row-level security for ACLs. Not v1 problems.

### Comparison with Steve Yegge's Beads

Beads is a distributed graph issue tracker powered by Dolt (MySQL-compatible version-controlled SQL). Yegge stores everything in the database because his content is structured records (issues with 15+ fields, dependency DAGs, threaded comments). That's SQL's sweet spot.

WikiHub's content is prose (markdown files). The primary UX is "clone my wiki, see markdown, open in Obsidian, edit, push." Storing content in a database would break this UX. Both architectures are correct for their respective data shapes.

The lesson from beads: pick the storage engine that matches your data shape. For issues → SQL. For wikis → filesystem (git).

---

## Permissions model

### Per-wiki AND per-file visibility
- Wiki-level default: public / unlisted / private
- Per-file override: public / unlisted / private (overrides wiki default)
- Google-Drive-style ACLs: per-wiki and per-file user lists (who can access)
- Unlisted = accessible by URL but not in explore/search
- Public-edit vs public-view distinction (longer term)
- Private pages in public wikis: REST-only, not git-exposed (git clone gives all blobs — no way to filter per-file without custom pack rewriting)

### Visibility storage
- Frontmatter carries a visibility *hint* that gets copied into DB on write
- DB row is authoritative (what the serving layer checks)
- On push, post-receive reads frontmatter and updates DB
- On fork, all visibility resets to fork-owner's default

### Collaborative editing (v2)
- Not real-time initially
- Suggested edits (PR-like) from forks = v1
- In-wiki collaborative editing = v2 scope

---

## Agent-first design

### Agent-native signup (no browser required)
An agent with nothing but `curl` should be able to: create account → get API key → create wiki → write pages. No human needed.

```
POST /api/v1/accounts                    # email optional, username auto-generated if omitted
  → { user_id, username, api_key }

POST /api/v1/accounts/claim-email        # optional email affiliation (not identity)
PATCH /api/v1/accounts/me                # programmatic rename (username, display_name, email)
POST /api/v1/accounts/me/api-keys        # rotate / create additional keys
DELETE /api/v1/accounts/me               # two-step deletion
```

### Anti-abuse without breaking agents
- No CAPTCHA, no email verification to sign up
- Rate limit account creation per IP (5/hour)
- Karma score: new accounts have reduced quotas, lift after N days of non-abuse
- `429` with `Retry-After` and machine-readable JSON body
- Abuse response is after-the-fact suspension, not prior restraint

### Agent-first web standards (from research brief)

**Content negotiation (highest leverage):**
- Every page URL responds to `Accept: text/markdown` with raw markdown + frontmatter
- Also serves at `<url>.md` as fallback
- `Vary: Accept` header, `Link: rel=alternate` pointing to markdown
- Claude Code and OpenCode already send `Accept: text/markdown` on every fetch

**llms.txt:**
- `/llms.txt` — curated table of contents
- `/llms-full.txt` — auto-generated from wiki store
- Table stakes for credibility (not a retrieval signal)

**Capability manifests (ship all — they're cheap):**
- `/.well-known/mcp/server-card.json` (SEP-1649 shape)
- `/.well-known/mcp` (SEP-1960 shape)
- `/AGENTS.md` at site root — prose instructions for coding agents
- `/openapi.json` — linked from llms.txt

**MCP server:**
- Thin wrapper over REST API
- Server-hosted MCP for headless agents
- WebMCP (Chrome 146+) for in-browser agents on wiki edit pages (v1 or v2 based on time)

**Agent identity:**
- User-scoped PATs as default agent credential
- Log soft `X-Agent-Name` / `X-Agent-Version` header on every API call
- `actor` column in audit log from day one (even if always null initially)
- Per-key scopes (read, write, admin) — even if v1 ships with only one scope
- Per-key rate limits distinct from per-user limits

**Discovery:**
- `GET /.well-known/wikihub.json` → `{ api_base, signup_endpoint, mcp_endpoint, docs }`
- Agent pointed at root domain can bootstrap itself without a human reading docs

---

## REST API (v1)

```
# Accounts
POST   /api/v1/accounts
POST   /api/v1/accounts/claim-email
PATCH  /api/v1/accounts/me
POST   /api/v1/accounts/me/api-keys
DELETE /api/v1/accounts/me/api-keys/:id
DELETE /api/v1/accounts/me

# Wikis
POST   /api/v1/wikis
GET    /api/v1/wikis/:owner/:slug
PATCH  /api/v1/wikis/:owner/:slug
DELETE /api/v1/wikis/:owner/:slug
POST   /api/v1/wikis/:owner/:slug/fork

# Pages
GET    /api/v1/wikis/:owner/:slug/pages
GET    /api/v1/wikis/:owner/:slug/pages/*path
PUT    /api/v1/wikis/:owner/:slug/pages/*path
PATCH  /api/v1/wikis/:owner/:slug/pages/*path
DELETE /api/v1/wikis/:owner/:slug/pages/*path

# Social
POST   /api/v1/wikis/:owner/:slug/star
DELETE /api/v1/wikis/:owner/:slug/star
POST   /api/v1/wikis/:owner/:slug/suggested-edits
GET    /api/v1/wikis/:owner/:slug/suggested-edits
POST   /api/v1/wikis/:owner/:slug/suggested-edits/:id/accept

# Search & graph
GET    /api/v1/wikis/:owner/:slug/search?q=...
GET    /api/v1/search?q=...                        # cross-wiki
GET    /api/v1/wikis/:owner/:slug/graph
POST   /api/v1/wikis/:owner/:slug/log              # append to log.md

# Explore
GET    /api/v1/explore                              # recent/popular public wikis
```

---

## Stack

- **Flask + SQLite + Jinja + bare git** (same as listhub, proven)
- Port `git_backend.py`, `git_sync.py`, `hooks/post-receive` from listhub — generalize paths for multi-wiki
- FTS5 for search
- Gunicorn + nginx + Cloudflare
- Deploy: fresh Lightsail instance or same box under different systemd unit + nginx vhost

---

## v1 milestones

1. Repo + stack skeleton (Flask app factory, SQLite schema, templates)
2. Auth (signup, API keys, Noos OAuth, admin token, agent-native endpoints)
3. Wiki CRUD + bare repo provisioning (three-layer scaffold on create)
4. Git Smart HTTP + post-receive two-way sync (port from listhub)
5. Page REST API (CRUD + frontmatter + per-file visibility via git plumbing)
6. Renderer (Jinja, markdown, wikilink resolver, index.md landing, backlinks)
7. Search (FTS5, scoped to visible wikis)
8. Social (fork, star, explore, suggested edits)
9. MCP server (thin wrapper over REST)
10. llms.txt + content negotiation + AGENTS.md + .well-known manifests
11. API docs page (`/api/docs`)
12. Deploy + full round-trip smoke test

---

## v2 tickets

1. Paste-unstructured-text → LLM generates wiki (coding agent, our key)
2. Connect URL / existing public wiki (clone/scrape)
3. Server-side agent with platform-provided key
4. Comments / discussion on wikis and pages
5. D3 force-graph rendering of wikilinks
6. Inline diff UI for suggested edits
7. Collaborative editing (not real-time initially)
8. WebMCP tool registration on wiki edit pages
9. Delegation endpoint (`POST /api/v1/delegation`) for short-lived scoped tokens

---

## Ideas from Harrison/Jacob transcripts (2026-04-07, 2026-04-08)

### High-signal ideas extracted:

**Omni-conversion upload:** Upload arbitrary files (PDF, Word, Google Doc paste, video → transcript). Server converts to markdown, commits to wiki. Not just markdown — anything in, markdown out.

**Cloud agent (v2):** Single shared Claude Code instance in prompt mode, one subscription, session per user. Simplest implementation: UNIX permission isolation per user, no Docker needed for MVP. Conceivably just a text input on the web that talks to a hosted agent.

**Cmd+K global search:** Fuzzy search over filenames and content. Global (cross-wiki) and local (within current wiki) options. Command+K keybinding in the web UI.

**Git-crypt for private content:** For users who don't trust server-side privacy, offer client-side encryption option. The `jacobcall.net` example: encrypted content in a public git repo, decrypted in-browser with a passphrase.

**HTML-comment-based privacy:** `<!-- private -->` markers in markdown that get preprocessed out before serving to unauthorized viewers. Per-line granularity within a single file.

**Viral distribution strategy:**
- 500k+ estimated people have created LLM wikis with no sharing platform
- Find GitHub users who starred/forked Karpathy's LLM wiki gist
- Email them offering easy sharing via git push
- 1-week window before competitors launch similar solutions
- Target the "Moltbook moment" for LLM wikis

**Anthropic relationship:** Getting Boris and team at Anthropic using wikihub as their markdown reader. Timing critical.

**Quartz as reference:** 11k GitHub stars, used by Stanford classes. Free alternative to Obsidian Publish ($20/mo). Consider what Quartz does well (folder index pages, Obsidian compatibility) and steal UX patterns.

**Three content types:** Lists (single markdown), wikis (multiple files), folders. (This was for listhub; wikihub focuses on the wiki type.)

---

## Research produced

- `research/llm-wiki-research.md` — five-sense taxonomy of LLM wikis, landscape, plan (2026-04-06)
- `research/llm-wikis-catalog.md` — ~85 entries across all 5 senses (2026-04-06)
- `research/agent-first-web-brief-2026-04.md` — WebMCP, llms.txt, agent-native auth, capability manifests, rendering conventions, agent identity, directories/scenes (2026-04-09)

---

## Open questions

1. **SQLite vs Postgres** — leaning SQLite for v1 speed, revisit if social features demand it
2. **Same Lightsail box vs new instance** — deploy-time decision
3. **Quartz UX patterns to steal** — need a focused review of Quartz's folder index, graph view, Obsidian compatibility
4. **Domain name** — wikihub.??? (not yet discussed)
5. **HTML-comment-based per-line privacy** — interesting but complex; v1 or v2?
6. **Git-crypt integration** — niche but differentiating; v2
