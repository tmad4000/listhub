# ListHub

Agent-native list and note publishing platform.

**Live:** https://listhub.globalbr.ai
**API Docs:** https://listhub.globalbr.ai/api/docs

## What is this?

ListHub is a place to create, share, and publish lists, notes, and documents. It has a REST API and two-way git sync, making it usable by both humans and AI agents.

## Quick Start

### Web
Visit https://listhub.globalbr.ai and sign up, or sign in with Noos OAuth.

### API
```bash
# Get an API key (exchange credentials for a token)
curl -X POST https://listhub.globalbr.ai/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username": "you", "password": "..."}'

# Create a list
curl -X POST https://listhub.globalbr.ai/api/v1/items/new \
  -H "Authorization: Bearer <your-key>" \
  -H "Content-Type: application/json" \
  -d '{"title": "My List", "slug": "my-list", "item_type": "list", "visibility": "public", "content": "- Item 1\n- Item 2"}'

# Search
curl https://listhub.globalbr.ai/api/v1/search?q=agent \
  -H "Authorization: Bearer <your-key>"
```

### Git
```bash
# Clone your items as markdown files
git clone https://listhub.globalbr.ai/git/USERNAME

# Push changes back
git push
```

## Feature Status

| Feature | API | UI |
|---|---|---|
| **Items** | | |
| Create item | ✅ | ✅ |
| Edit content | ✅ | ✅ (WYSIWYG + raw) |
| Edit metadata (title, slug, type, visibility, tags) | ✅ | ✅ |
| Delete item | ✅ | ✅ |
| List own items | ✅ | ✅ |
| Get/upsert item by slug | ✅ | ❌ |
| Append entry to list | ✅ | ❌ |
| Version history | ❌ no endpoint (stored in DB) | ❌ |
| **Visibility** | | |
| Set visibility on create/edit | ✅ | ✅ |
| Filter own items by visibility | ✅ | ✅ |
| Visibility badge — dashboard list view | n/a | ✅ |
| Visibility badge — dashboard folder view | n/a | ❌ |
| Visibility badge — profile page | n/a | ✅ owner only |
| Visibility badge — item detail page | n/a | ❌ |
| **Sharing** | | |
| Share item with specific user (read/edit) | ✅ | ❌ |
| Revoke share | ✅ | ❌ |
| List who item is shared with | ❌ | ❌ |
| View a shared item (as recipient) | ✅ | n/a |
| Edit shared item (write permission) | ❌ owner only | ❌ |
| **Save / Favorite** | | |
| Save/favorite someone's item | ❌ no table | ❌ |
| View saved items | ❌ | ❌ |
| **Search & Discovery** | | |
| Full-text search own items | ✅ | ✅ |
| Full-text search public items | ✅ | ✅ |
| Filter by tag | ✅ | ❌ |
| Filter by type | ✅ | ❌ |
| Explore public items | n/a | ✅ |
| User profile page | n/a | ✅ |
| People directory | n/a | ✅ |
| **Auth** | | |
| Register (local) | ❌ | ✅ |
| Login via Ideaflow ID (OIDC, silent SSO, explicit account link) | n/a | ✅ |
| Login via Noos OAuth | n/a | ✅ |
| Login via local password | n/a | ✅ (fallback) |
| Create/list/revoke API key | ✅ (revoke is session-only, see listhub-bnr) | ✅ |
| Bootstrap token (password → API key) | ✅ | ❌ |
| **Git** | | |
| Clone/pull via HTTP | ✅ | n/a |
| Push via HTTP | ✅ | n/a |
| DB→Git sync | ✅ | n/a |
| Git→DB sync (post-receive hook) | ✅ | n/a |
| View git history | ❌ | ❌ |
| **Misc** | | |
| Auto-generate slug from title | ✅ server-side | ❌ no JS autofill |
| Short link `/i/<id>` | n/a | ✅ |
| Folder/tree view | n/a | ✅ |
| Featured (curated shared repo) | n/a | ✅ |

## Stack

Flask + SQLite + Gunicorn, server-rendered Jinja2 templates, no JS framework.

## Development

See [CLAUDE.md](CLAUDE.md) for full architecture, conventions, and deploy instructions.

## Deploy

```bash
ssh noos-prod "cd /home/ubuntu/listhub && git pull origin main && sudo systemctl restart listhub"
```

## Docs &amp; history

- **[docs/looms.md](docs/looms.md)** — index of Loom walkthroughs (pre-sidebar checkpoint, pitch pages, feature demos). Add new Looms here as they are recorded.
- **[docs/history-pre-sidebar.md](docs/history-pre-sidebar.md)** — state of ListHub before the three-section sidebar shipped; Google Sites / Wikispaces / sub-wiki context.
- **[docs/investor-blurb.md](docs/investor-blurb.md)** — intro blurbs (short/medium/long) for investors forwarding the IdeaFlow Memory pitch to portfolio founders.
- **`/mockups/`** — design mockups served at `https://listhub.globalbr.ai/mockups/`. Includes the agent-first web standard page, the company LLM wiki pitch pages, and the IdeaFlow Memory brand direction.

## Shared Ideaflow sign-in

Set `LISTHUB_IDEAFLOW_CONFIG` to a mode-600 server-only JSON file with the registered `issuer`, `client_id`, `client_secret` and `redirect_uris` (the sole callback must be `https://listhub.globalbr.ai/auth/ideaflow/callback`). No client secret goes to a browser. Without this setting the existing Noos login remains active.

The login route first attempts `prompt=none` once per local session. Normal sign-in then uses the shared provider; sign-out suppresses silent re-entry and the next sign-in chooses an account. Switch account explicitly invokes that chooser. OAuth requests use a single-use five-minute state, nonce and S256 PKCE; ID tokens require signature, issuer, audience, expiry and nonce validation.

Identity mappings key on issuer and subject, preserving ListHub IDs, content, API keys and git repos. Existing accounts are never linked on email alone. Sign in with existing Noos/local credentials, then choose **Connect Ideaflow account**; the selected identity can map to only that local account. Old Noos callbacks and agent registration/API authentication remain supported.

Validate: `.venv/bin/python -m unittest discover -s tests -v`.
