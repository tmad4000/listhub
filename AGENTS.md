# Agent Instructions

This project uses **bd** (beads) for issue tracking. Run `bd onboard` to get started.

## Feature Parity Rule

Every feature must ship with API, UI, and docs together — no API-only or UI-only features.

When you add, change, or remove a feature:
1. Implement both the API endpoint and the UI
2. Update `templates/api_docs.html` to reflect any API changes
3. Update the Feature Status table in `README.md`

## Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --status in_progress  # Claim work
bd close <id>         # Complete work
bd sync               # Sync with git
```

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd sync
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds


## Agent-First Architecture (PRINCIPLES — KEEP THIS UP TO DATE)

ListHub is an **agent-first website**. Every code change to user-facing
features must preserve and extend the agent surfaces. When you add an
endpoint, add a tool. When you add a content surface, respect visibility.
When you add a discovery affordance, document it for agents.

### Required surfaces (do not regress)

These exist today and MUST keep working. If you change a related area,
verify each:

1. **WebMCP** &mdash; `static/webmcp.js` registers tools via
   `navigator.modelContext.registerTool()` on every page. The script is
   loaded from `templates/base.html` with `<script defer>`. When you add
   a new write endpoint to `api.py`, add a corresponding tool to
   `webmcp.js`. Tools call the REST API via
   `fetch(..., { credentials: 'include' })` so the browser session
   handles auth automatically.

2. **REST API** &mdash; `api.py` exposes the full feature surface.
   Read endpoints work for any visitor; write endpoints respect
   ownership and visibility. The API is the source of truth — UI and
   WebMCP both wrap it.

3. **`/llms.txt`** &mdash; the route is in `views.py` (`llms_txt`). It
   describes the API base URL, the registration flow, the WebMCP
   tools, the home special slug, the private content blocks pattern,
   and the visibility levels. When you add a new agent-relevant
   capability, add a section here too.

4. **`/api/docs`** &mdash; the human-readable companion. Mirror any
   `llms.txt` change here. Keep the WebMCP section accurate when tools
   change.

5. **Programmatic registration** &mdash; `POST /api/v1/auth/register`
   must keep working without browser, CAPTCHA, or email verification.
   Agents self-onboard via this endpoint.

6. **Per-item visibility** &mdash; `private`, `public`, `public_edit`,
   `shared`, and `unlisted` (when shipped). The agent that creates an
   item sets the visibility at write time via the API. Do not weaken
   this.

7. **Private content blocks** &mdash; `<!-- private -->...<!-- /private -->`
   in markdown is stripped at render time for non-owners via
   `strip_private_blocks()` in `views.py`. **Any new surface that
   exposes `item.content` to a template, API response, or log MUST
   filter it through `strip_private_blocks()` for non-owners.** This
   includes copy-to-clipboard textareas, embedded raw views, and any
   future export feature.

8. **Special slug `home`** &mdash; users can create an item with slug
   `home` that becomes their landing card on `/@username` and `/dash`.
   Treat it as agent-editable. Do not hard-code it as a separate type.

### When adding new features

- [ ] If it's a new write endpoint &rarr; add a WebMCP tool
- [ ] If it's a new content type &rarr; respect visibility on every render
- [ ] If it's a new content surface &rarr; pass content through
      `strip_private_blocks()` for non-owners
- [ ] If it's a new agent-relevant capability &rarr; document in
      `/llms.txt` AND `/api/docs`
- [ ] If it's a new auth flow &rarr; programmatic registration must
      still work

### What NOT to do

- Do **not** add a feature that requires a browser-only flow without
  also exposing it via the API
- Do **not** strip the WebMCP loader from `base.html`
- Do **not** add per-item content access without checking visibility
- Do **not** introduce captchas or human-verification on the
  registration endpoint
- Do **not** remove `data-listhub-webmcp="ready"` &mdash; agents probe it

### References

- WebMCP spec: https://github.com/webmachinelearning/webmcp
- Implementation: `static/webmcp.js`
- Standard mockup: `mockups/agentfirst-standard.html` (the
  Bronze/Silver/Gold tier definition this codebase aims for)
- Visibility code path: `views.py` &rarr; `render_md()` &rarr;
  `strip_private_blocks()`

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:ca08a54f -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

## Session Completion

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd dolt push
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
<!-- END BEADS INTEGRATION -->
