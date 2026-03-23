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

## Stack

Flask + SQLite + Gunicorn, server-rendered Jinja2 templates, no JS framework.

## Development

See [CLAUDE.md](CLAUDE.md) for full architecture, conventions, and deploy instructions.

## Deploy

```bash
ssh noos-prod "cd /home/ubuntu/listhub && git pull origin main && sudo systemctl restart listhub"
```
