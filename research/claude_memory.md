# ListHub — Project Instructions

## What this is
ListHub is a personal knowledge/list management app. Users create items (notes, lists, documents) via a web UI or REST API. Items are mirrored to per-user bare git repos, enabling `git clone`/`git pull`/`git push` workflows.

**Live:** https://listhub.globalbr.ai/
**Server:** AWS Lightsail (3.216.129.34), code at `/home/ubuntu/listhub/`

## Stack
- **Backend:** Flask + SQLite + Gunicorn
- **Auth:** bcrypt passwords, SHA-256 API keys, Flask-Login sessions, Noos OAuth SSO
- **Search:** SQLite FTS5
- **Git:** Smart HTTP backend with bare repos, plumbing-based DB→git sync
- **Frontend:** Server-rendered Jinja2 templates, dark theme, no JS framework
- **Proxy:** Cloudflare → Docker nginx (`noos_nginx`) → Gunicorn on port 3200

## Architecture

```
app.py          — Flask app factory, blueprint registration
api.py          — REST API (/api/v1/*)
views.py        — Web UI routes + /api/docs
auth.py         — Auth blueprint, API key decorator, admin token, Noos OAuth
models.py       — User model
db.py           — SQLite connection, schema, FTS reindexing
git_backend.py  — Git Smart HTTP (clone/push), repo init, hook install
git_sync.py     — DB→git sync (plumbing on bare repos)
hooks/post-receive — Git→DB sync (push triggers API calls)
templates/      — Jinja2 templates (base.html, dash.html, api_docs.html, etc.)
static/style.css — All CSS (dark theme, CSS variables)
```

## Key patterns

### Two-way git sync
- **DB→Git:** `git_sync.py` writes items as .md files with YAML frontmatter using git plumbing (no working tree). Called inline after DB commits in views.py and api.py.
- **Git→DB:** `hooks/post-receive` parses pushed .md files and creates/updates items via the API using the admin token.
- **No loop:** `git update-ref` does NOT trigger post-receive hooks — only `git-receive-pack` does.

### Bare repo plumbing
- Use `GIT_INDEX_FILE` with a temp file for all index operations
- Use `git hash-object -w --stdin` to write blobs
- Use `git update-index --add --cacheinfo` to add files
- Use `git update-index --index-info` with mode `0` + null SHA to remove files (NOT `--force-remove`, which fails in bare repos)
- Use `git write-tree` → `git commit-tree` → `git update-ref`

### Auth
- API endpoints use `@require_api_auth` (Bearer token or session)
- Admin token (`LISTHUB_ADMIN_TOKEN`) with `X-ListHub-User` header for internal calls
- Key management endpoints use `@login_required` (session only)
- **Noos OAuth SSO:** Users can sign in via Noos (`globalbr.ai`). OAuth code flow with `client_id=listhub`. Users are auto-created on first login (linked by `noos_id`). Noos-only users have `password_hash='!noos-oauth'` (no local password). They use API keys for git auth.
- Git HTTP Basic Auth accepts both bcrypt passwords and API keys (industry standard PAT pattern)

### Frontmatter round-trip
Files without frontmatter are accepted on push — metadata is inferred from filename. The DB→git sync always writes frontmatter. After one round-trip, all files have explicit metadata.

## Design Philosophy

### ListHub is infrastructure, not an app
ListHub is the memory layer. It should serve *any* assistant or client — Voice Assistant, Claude Code, a phone app, a Slack bot. They're all clients. The memory system stands alone.

### Separate repos, seamless integration
Assistants and ListHub live in separate repositories because:
- Different deployment lifecycles. Iterate on assistant personality/behavior independently from storage.
- Other people using ListHub won't use your specific assistant.
- ListHub should remain unopinionated about who's using it.

But the integration should feel native because:
- External memory isn't optional — it's what makes an assistant *yours* rather than generic. An assistant without its memory is a brain without long-term storage.
- The integration should be a thin layer, not a subsystem to replicate. An assistant should need ~50 lines of code for full memory access: bootstrap a token, read/write items, search, manage visibility.

### What "native" looks like in practice
- A small client library or config block: `LISTHUB_URL`, `LISTHUB_TOKEN`. That's it.
- Commands like `/remember`, `/share`, `/publish` in assistants that map directly to API calls.
- The assistant's system prompt pulls from ListHub items tagged with `system` or `context`.
- API for writes, git pull for reads. This avoids merge conflicts and keeps the flow simple.

### Future direction
The current flat-file-with-tags model is a stepping stone toward a graph database. Tags are edges, items are nodes. When migrating, the API surface stays nearly identical — add relationship endpoints (`POST /api/v1/items/<id>/links`) but basic CRUD doesn't change. Assistants won't need to change much.

## Conventions

- **Dark theme only.** All UI uses CSS variables from `:root` in style.css.
- **No JS framework.** Minimal vanilla JS where needed. Server-rendered templates.
- **SQLite.** No ORM — raw SQL with `sqlite3.Row` for dict-like access.
- **Nanoid** for all IDs (items, users, API keys).
- **Error handling in sync:** All git sync calls are wrapped in `try/except pass` so git errors never break the main DB operation.

## IMPORTANT: Keep API docs in sync

The API documentation lives at `/api/docs` (template: `templates/api_docs.html`). **When you add, modify, or remove any API endpoint, you MUST update the API docs template to match.** This includes:
- New endpoints
- Changed request/response formats
- New query parameters or fields
- Changed authentication requirements

The docs page is publicly accessible and linked from the site header.

## Deployment

```bash
# SCP changed files to Lightsail
scp -i ~/.ssh/lightsail-noos.pem <files> ubuntu@3.216.129.34:/home/ubuntu/listhub/

# Restart service
ssh -i ~/.ssh/lightsail-noos.pem ubuntu@3.216.129.34 "sudo systemctl restart listhub"

# Run full git sync (after schema or sync logic changes)
ssh -i ~/.ssh/lightsail-noos.pem ubuntu@3.216.129.34 "cd /home/ubuntu/listhub && source venv/bin/activate && python git_sync.py"
```

## Environment variables (in systemd unit)
- `LISTHUB_SECRET` — Flask session secret
- `LISTHUB_ADMIN_TOKEN` — Internal auth token for hooks
- `LISTHUB_REPO_ROOT` — Bare repo directory (default: `/home/ubuntu/listhub/repos`)
- `LISTHUB_DB` — SQLite database path
- `LISTHUB_BASE_URL` — Base URL for hook API calls (default: `http://localhost:3200`)
- `LISTHUB_PUBLIC_URL` — Public-facing URL for OAuth callbacks (default: `https://listhub.globalbr.ai`)
- `NOOS_AUTH_URL` — Noos OAuth provider URL (default: `https://globalbr.ai`)

## Deploy Workflow (git pull)

Production now has a git repo tracking `origin/main`. Deploy with:

```bash
# From Mac mini (develop + push):
cd /Users/Jacob/listhub && git push origin main

# On production (deploy):
ssh noos-prod "cd /home/ubuntu/listhub && git pull origin main && sudo systemctl restart listhub"

# One-liner from Mac mini:
ssh noos-prod "cd /home/ubuntu/listhub && git pull origin main && sudo systemctl restart listhub"
```

**No more SCP.** All code changes go through git.

### Production Server
- **Host:** AWS Lightsail (3.216.129.34)
- **SSH:** `ssh noos-prod`
- **Code:** `/home/ubuntu/listhub/`
- **Service:** `listhub` (systemd)
- **Git remote:** `https://github.com/tmad4000/listhub.git` (main branch)
