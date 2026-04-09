# wikihub spec state — from the side session (2026-04-08)

Everything below was decided in a branched ("side") session discussing the wikihub spec. Paste this to get a fork up to speed.

## Name and shape

- **Name locked:** wikihub
- **One-liner:** GitHub for LLM wikis — a hosting platform for Karpathy-style markdown knowledge bases with Google-Drive-style per-file access control, native agent API (MCP + REST + content negotiation), and social features (fork, star, suggested edits).
- **First users (v1):** Yourselves via dogfood migrations (admitsphere, RSI wiki, systematic altruism wiki, jacobcole.net/labs, the CRM); the Karpathy-gist wave of early adopters who have their own LLM wikis and no shared place to publish; Obsidian vault owners looking for an agent-aware publish target better than Obsidian Publish or Quartz.
- **Distribution goal (not a design persona):** get Boris / team at Anthropic using wikihub. Surfaced in a Granola meeting transcript as a partnership angle. Do not design v1 around Boris; design around the three first-user groups above and treat the Anthropic pitch as a post-launch outreach move.
- **Future target (architecture must not preclude):** Anthropic intranet — LLM wikis for companies. Implies multi-tenancy / org support later; the principal abstraction in the ACL model reserves space for this at zero current cost.
- **Built from scratch** in a new repo. Not grafted onto listhub. Copies listhub's git plumbing patterns verbatim (`git_backend.py`, `git_sync.py`, `hooks/post-receive`) — those files are battle-tested and should be ported with path generalization, not rewritten.
- **Reader aesthetic bar:** KaTeX, code highlighting, footnotes, clean dark typography. Justification: the Karpathy-wave audience expects a real reader (many of them run ML research wikis with math and code). Not because of any individual imagined judge.

## Stack

- **Backend:** Flask + **Postgres** (confirmed — earlier drift toward SQLite was overruled) + Jinja + bare git
- **Renderer:** markdown-it + markdown-it-footnote + markdown-it-katex + highlight.js + markdown-it-image-figures + custom wikilink plugin + custom Obsidian-embed plugin (for `![[image.png]]` and `![[image.png|300]]` syntax) + external-links-in-new-tab config.
- **No JS framework.** Server-rendered dark-theme templates, CSS variables. Minimal vanilla JS where needed.
- **Mobile-friendly from v1** — see "Non-functional requirements" section below. Not polish; a day-one hard requirement.
- **Web editor: OPEN.** Milkdown (WYSIWYG, proven from listhub, plugin architecture) vs. simpler markdown textarea + wikilink autocomplete. Open question pending discussion.
- **Deploy:** TBD (open question: cohabit with listhub on the same Lightsail box under a new systemd unit + nginx vhost, or new instance?)

## Non-functional requirements

- **Mobile-friendly v1.** Every page works on a 375px-wide viewport. Mobile-first CSS (`min-width` breakpoints, not `max-width`). Touch targets ≥44×44px. Sidebar collapses to a hamburger drawer on narrow viewports. Cmd+K is full-screen modal on mobile. Editor is virtual-keyboard friendly, no hover-dependent UI. Tables and code blocks scroll horizontally, not clip. Images responsive (`max-width: 100%`). Body font minimum 16px to avoid iOS zoom-on-focus.
- **Mockup-first workflow.** Wikihub has a `mockups/` directory from day one. Every significant UI surface gets a standalone HTML mockup (inline CSS/JS, no backend dependencies) before any implementation code is written. Required surfaces before coding: landing, `/@user` profile, wiki reader view, wiki edit view, Cmd+K search, `/explore`, folder view, visibility panel, permission error page, plus mobile versions of all of these. Pattern ported from listhub's `mockups/` directory workflow.

## Data architecture — the load-bearing invariant

**Bare git repo = source of truth. Postgres = derived index, rebuildable from repos.**

- Every wiki has its own bare repo at `repos/<user>/<slug>.git` (repo-per-wiki, confirmed twice — not repo-per-user).
- **Binary files (images, PDFs, attachments) live in the git repo alongside markdown**, same as Obsidian treats attachments. No quota in v1 ("ship naked, trust users"). Git LFS is NOT used in v1. Future escape hatch when a wiki outgrows in-repo binaries: globalbr.ai already has an S3 bucket that can host external blobs, with markdown links rewritten server-side to signed HTTPS URLs (v2+).
- Postgres stores: users, wikis, pages (derived), wikilinks, ACL grants, stars, forks, sessions, API keys, principals, audit rows. Social graph is ONLY in Postgres and can't be rebuilt from repos.
- **Two-way sync** copied from listhub:
  - DB→git: Flask writes via git plumbing (`GIT_INDEX_FILE`, `hash-object`, `update-index --cacheinfo`, `write-tree`, `commit-tree`, `update-ref`). This path does NOT fire hooks, which is why the loop below doesn't run forever.
  - git→DB: `post-receive` hook parses pushed .md files and calls the admin REST API. Fires on `git push`, NOT on `update-ref`.
- **Reindex commands** from day one: `wikihub reindex <wiki>`, `wikihub reindex --all`, `wikihub verify <wiki>` (diff Postgres against HEAD, report mismatches).

## Per-wiki storage: authoritative + public mirror (the big architecture call)

Every wiki exists as **two bare git repos**:

- `repos/<user>/<slug>.git` — authoritative. Owner only. All files, private + public. `.wikihub/acl` lives here.
- `repos/<user>/<slug>-public.git` — derived public mirror. Regenerated on every push to the authoritative. Contains only public files, with `<!-- private -->` bands stripped from markdown and `.wikihub/acl` itself omitted.

**Flask dispatches clones by auth:**

```
GET /@alice/crm.git/info/refs?service=git-upload-pack
  → owner? shell out to git-http-backend on repos/alice/crm.git
  → else?  shell out to git-http-backend on repos/alice/crm-public.git
```

From the client's side, **`git clone`, `git fetch`, `git push` all work as normal** — no custom pack filtering, no rewritten wire protocol. The cleverness is entirely at push time in the regeneration logic. Two separate bare repos (not two refs in one) chosen for auditability: you can inspect the public mirror on disk to confirm nothing private leaked.

The public mirror has **linearized history** (`Public snapshot @ <source-sha>` force-updated on every regen). No history preservation on the mirror — `git blame` on the mirror is useless; blame on the authoritative is fine. Rendered pages surface authorship from Postgres, not from mirror history.

**Private pages never enter git at all.** They live in Postgres only. Git is the coarse layer (owner or not); Postgres is the fine-grained layer. This is the honest resolution to "git can't filter packs per-user." We explored dynamic pack filtering via libgit2 and rejected it as a research project in the wrong shape.

## ACL storage: `.wikihub/acl` (CODEOWNERS-pattern file)

The single most important design choice of the session. Access control lives in a git-tracked file at `.wikihub/acl` using the same pattern as `.gitignore`, `.gitattributes`, and `CODEOWNERS`: **glob rules, most-specific wins, private by default, comments with `#`**.

Example:

```
# wikihub ACL — declarative access control for this wiki.
#
# Rules are glob patterns. Most-specific pattern wins. Default is `private`.
#
# Visibility: public | unlisted | public-edit | unlisted-edit | private | signed-in
# Grants:     @user:role | group:name:role | link:token:role
# Roles:      read | comment | edit | admin
#
# Examples:
#   * private                      # everything private (the default)
#   wiki/** public                 # publish the wiki/ subtree
#   wiki/secret.md private         # override: this one is private
#   raw/legal.pdf @lawyer:read     # share with one user
#   drafts/** group:team:edit      # let a group edit drafts

* private

wiki/**                   public
wiki/karpathy-private.md  private
private-crm/**            @alice:edit
drafts/**                 unlisted
community/**              public-edit
legal-review/**           link:r4nd0m-t0k3n:read
```

**Rationale:**
- Git-friendly: diffable, blameable, merges cleanly, round-trips through clone→edit→push, file-type agnostic (works for .md, .pdf, images, anything).
- Private by default: one line, `* private`, at the top of every scaffolded wiki.
- Scales both ways: tiny wikis have 3 lines, huge wikis have hundreds. Rules only exist where behavior diverges from the folder default.
- Self-documenting: the scaffolded header block teaches the format so LLMs reading the file cold don't need a skill.
- Safe failure: missing file → whole wiki is private. Malformed → reject push with clear error, previous version stays in effect.

`.wikihub/` is the platform metadata dotfolder, peer to `.git/`, `.github/`, `.claude/`. Future home of `config`, `schema.md`, `webhooks`, etc.

## Frontmatter and the ACL file compose via specificity, not authority

Frontmatter is NOT "just a hint." The precedence ladder is:

1. **Frontmatter on the file** — most specific, wins for that file.
2. **ACL file rule matching the path**, most-specific pattern first.
3. **Repo default** (`* private`, implicit).

Both frontmatter and ACL file are authoritative for their scope. The ACL file handles bulk patterns ("everything in wiki/ is public"). Frontmatter handles single-file exceptions ("this one page is different"). They are orthogonal tools, not competing sources of truth.

When an agent writes `visibility: public` in a frontmatter, the server treats it as an authoritative change for that file, logs the change, and enforces it.

## Obsidian frontmatter compatibility

**Keys wikihub uses:** `visibility`, `share`, `title`, `description`. None collide with Obsidian reserved keys.

**Read liberally, write conservatively** (Postel's Law applied to config files):

- **On read:** honor Obsidian conventions for free migration wins.
  - `publish: true/false` → alias for `visibility: public/private` (wikihub-native `visibility:` wins on conflict). This gives Obsidian Publish users zero-rewrite migration.
  - `aliases` → honored for `[[wikilink]]` resolution.
  - `permalink` → honored as URL slug.
  - `description` → used for OG tags and llms.txt excerpts.
  - `tags` → honored (accept both list and flow syntax, strip leading `#`).
  - `cssclass` / `cssclasses` → applied to rendered `<article>`.
- **On write:** only touch `visibility:` and `share:`. Never clobber keys we don't own. Round-trips cleanly to Obsidian and back.

Documented migration story: "Point your Obsidian vault at wikihub as a git remote and push. Your `publish:` flags, aliases, permalinks, and tags just work."

## Permission model

Three orthogonal axes:

1. **Read audience:** owner | grantees | link-holders | signed-in | anyone
2. **Write audience:** same ladder
3. **Discoverable:** indexed | hidden

**Internal mode names stay short** (`public`, `public-edit`, `unlisted`, `unlisted-edit`) — that's what the ACL file uses and what the API returns. **User-facing UI labels disambiguate** with parentheticals: `public (read)`, `public (edit)`, `unlisted (read)`, `unlisted (edit)`, `private`, `signed-in (read)`. Lesson from listhub: `public` alone is ambiguous — does it mean anyone can read or anyone can edit? The parenthetical labels resolve it.

**Visibility badges everywhere.** Every page, wiki card, search result, explore entry, profile item, and sidebar row shows a small visibility icon (lock for private, globe for public, eye for unlisted, pencil-in-circle for edit variants, lock-with-check for signed-in, share-arrow for shared). Badges are clickable and open the visibility panel for users with admin. This is table-stakes UX, not polish.

The visibility "modes" are named shortcuts for common (read, write, discoverable) triples plus optional explicit grants. Full v1 vocabulary:

| Mode | Read | Write | Discoverable |
|---|---|---|---|
| `private` | owner | owner | no |
| `public` | anyone | owner | yes |
| `public-edit` | anyone | **anyone, anonymous OK** | yes |
| `unlisted` | URL holders | owner | no |
| `unlisted-edit` | URL holders | **anyone with URL, anonymous OK** | no |
| `signed-in` | any signed-in | owner | yes |
| `link-share` | token holders | owner | no |
| `shared` (per-grant) | as granted | as granted | no |

**Critical scope decision: both `public-edit` and `unlisted-edit` allow ANONYMOUS writes in v1. No account required. Google Docs link-edit model.**

Grant syntax in the ACL file: `@user:role`, `group:name:role`, `link:token:role`. The `commenter` role exists in the vocabulary from day one and behaves as `read` until comments ship in v2.

**Principal abstraction:** ACL grants reference a polymorphic `principals` table (types: `user | group | link_token | anyone | org`). Orgs ship later for the Anthropic-intranet target; the table shape supports them now at zero current cost.

## `<!-- private -->` HTML comment sections

Ships in v1 as a lightweight sub-file privacy tool:

- `<!-- private -->...<!-- /private -->` blocks in markdown are **stripped from the public mirror and from content-negotiated markdown responses**.
- They REMAIN in the authoritative repo. Anyone with owner access sees them.
- UI shows a visible warning on pages that contain private bands: "this page has sections visible only to editors; don't use this for real secrets, use a private file instead."
- Honest design framing: it's a **parasitic syntax** (rides on markdown's HTML-preserving rule), a **best-effort convenience feature**, not a security boundary.
- Doesn't compose with the share graph — binary public-or-owner, not share-aware. For finer control, split the private chunk into its own file under a per-file ACL.

## v1 ships WITHOUT any anti-abuse machinery (major scope cut)

A full anti-vandalism plan was drafted and then **entirely cut from v1** at user's direction. Ship anonymous-writes naked; iterate reactively when problems actually occur.

**OUT of v1 (deferred to v2/v3):**
- Per-IP / per-token / per-wiki write rate limits
- Honeypot form field
- Actor logging beyond basic author field
- Moderation view (edit history filtered for owner)
- Revert tooling beyond git native (no bulk revert, no "revert all edits by actor X")
- Panic button (instant disable of anonymous writes on a wiki)
- Auto-under-attack mode (state machine on edit rate)
- Owner notifications (email/webhook on anonymous edits)
- Quarantine queue (pending-review edits)
- Proof-of-work reactive throttling
- Body/link size caps on writes
- CAPTCHA escape hatch
- "Are you sure?" warnings when enabling public-edit
- "Default off for public-edit on new wikis" safety
- llms.txt `crawl: false` per-wiki opt-out

**IN for v1 (basic plumbing only):**
- Anonymous git commits use `anonymous <anon@wikihub>` as the git author (required by git itself).
- Pages table has a nullable author field. No elaborate polymorphic actor.
- Basic signup rate limit per IP is still in (infra, not content moderation — confirm if user is asked).

Philosophy: "trust mode, ship it, iterate when problems happen."

## Agent-first surface (from research brief)

From `agent-first-web-brief-2026-04.md` (in this subfolder) — all cheap, all shipping in v1:

- **Content negotiation** on every page URL. `Accept: text/markdown` → raw markdown with frontmatter, no chrome. `Vary: Accept` and `Link: rel=alternate; type=text/markdown` headers. Per the brief this is the single highest-leverage move for 2026 agent compatibility — Claude Code and OpenCode already send the header on every fetch. Also serve `<url>.md` as a fallback for dumb clients.
- **`/llms.txt`** and **`/llms-full.txt`** auto-generated per wiki and site-wide. Stripe pattern (curated top with an `## Optional` bucket for long tail).
- **`/AGENTS.md`** at site root. Prose, short, explains signup, API base, MCP endpoint, llms.txt location, how `.wikihub/acl` works.
- **`/.well-known/mcp/server-card.json`** (SEP-1649 shape) and **`/.well-known/mcp`** (SEP-1960 shape). Both shipped — major MCP clients implement both speculatively and they're cheap.
- **`/.well-known/wikihub.json`** site bootstrap manifest (API base, MCP URL, signup URL, docs URL) so an agent pointed at the domain can self-bootstrap.
- **Server-hosted MCP server** (`wikihub-mcp`) wrapping the REST API. Tools: `whoami`, `search`, `read_page`, `list_pages`, `create_page`, `update_page`, `append_section`, `delete_page`, `set_visibility`, `share`, `create_wiki`, `fork_wiki`, `commit_log`.
- **WebMCP** tool registration on edit pages via `navigator.modelContext.registerTool` (Chrome 146 flag-only as of April 2026, feature-detected). Reuses logged-in browser session.
- **JSON-LD** `@type: Article` on HTML responses with author, dates, license.

## Agent-native auth

- `POST /api/v1/accounts {display_name?, email?}` → `201 {user_id, username, api_key}`. Email is optional, username is server-assigned if omitted, no CAPTCHA on signup, no verification required.
- `PATCH /api/v1/accounts/me` for programmatic rename (username, display_name, email independently). Username change → old slug redirects for 90 days.
- `POST /claim-email` for post-hoc email affiliation. Email is not identity; it's an optional attachment.
- `POST /api/v1/keys`, `DELETE /api/v1/keys/:id` for key management (session-auth).
- Per-key scopes (`read`, `write`, `admin`) in schema from day one, even if v1 default key is `read+write`.
- Soft `X-Agent-Name` / `X-Agent-Version` header logged; surfaced in user's dashboard ("this key was used by `claude-code@1.2.3`").
- `/api/v1/delegation` endpoint shell for future RFC 8693 token exchange; ships as no-op.
- Git HTTP Basic Auth accepts password OR API key (listhub convention).
- **Noos OAuth SSO** from day one. Google/GitHub OAuth not yet decided — flagged as open question because Anthropic targets probably want Google SSO.
- Signup rate limit per IP (infra, not moderation) probably still in v1.

## Page REST API (v1)

- `POST /api/v1/wikis/:owner/:slug/pages` — create a page at a new path.
- `GET /api/v1/wikis/:owner/:slug/pages/*path` — read (respects content negotiation for `Accept: text/markdown`).
- `PUT /api/v1/wikis/:owner/:slug/pages/*path` — full replace.
- `PATCH /api/v1/wikis/:owner/:slug/pages/*path` — partial update (frontmatter patches, append, etc.).
- **`PATCH /api/v1/wikis/:owner/:slug/pages/*path {new_path: "..."}`** — rename/move. Performs git-mv-equivalent via plumbing, scans all pages for `[[old-title]]` / `[[old/path]]` wikilinks and rewrites them to the new path, commits everything atomically with message `Rename <old> → <new>`. Git's rename detection preserves blame continuity. MCP tool: `move_page(old_path, new_path)`.
- `DELETE /api/v1/wikis/:owner/:slug/pages/*path` — remove.

## Error response convention

Every 401/403 response from the REST API returns a structured JSON body so agents can parse and react:

```json
{
  "error": "insufficient_permissions",
  "reason": "This page requires edit access; you have read access.",
  "required_role": "edit",
  "your_role": "read",
  "suggested_actions": [
    {"verb": "fork", "description": "Fork this wiki and edit your copy", "endpoint": "/api/v1/wikis/:owner/:slug/fork", "method": "POST"},
    {"verb": "request_access", "description": "Ask the owner for edit access", "endpoint": "/api/v1/wikis/:owner/:slug/access-requests", "method": "POST"}
  ]
}
```

Agents parse `suggested_actions` and offer the user a menu. This is the single biggest agent-UX lesson from listhub's `listhub-n5g` ticket.

## Ingestion (v1 only)

- **`git push`** — user has wiki locally, adds wikihub remote, pushes. Post-receive parses and syncs to Postgres.
- **Folder / zip upload** — web drag-drop. Server unpacks, commits with "Initial import from upload" message, runs through the same post-receive path.
- **Scaffold a blank wiki** — "Create wiki" button seeds the three-layer Karpathy skeleton (`schema.md`, `index.md`, `log.md`, `raw/`, `wiki/`, `.wikihub/acl` with private-default header) and one initial commit.

**v2 deferred:** paste-unstructured-text → LLM, URL/repo connect, omni-convert (PDF/DOCX/txt/video → markdown), HTML/Google Sites importer, FTP.

## Social layer (v1)

- **Fork** — server-side `git clone --bare` under caller's namespace, plus a matching regen of the public mirror. Copies Page rows into Postgres, **resets visibility to `private` (the repo-default `* private` line)** — the forker explicitly republishes if they want it public. Sets `forked_from_id`. Free from the bare-repo model.
- **Star** — single counter and row. Standard.
- **Suggested edits** — `{source_wiki, source_commit, target_wiki, diff}`. v1 UI: list pending + one-click accept. Accept path: server uses git plumbing (`commit-tree` + `update-ref`) to apply the cherry-pick to the target's authoritative repo, then **directly calls the same sync path that `post-receive` calls** (not the hook itself — plumbing doesn't fire hooks, which is the two-way-sync no-loop invariant we depend on). This updates Postgres, regenerates the public mirror, and reindexes search atomically. No inline diff UI in v1.
- **ZIP download** — `GET /@alice/wiki.zip` returns a zip of the wiki's working tree. Flask dispatches by auth: owner gets the authoritative repo's tree; non-owners get the public mirror's tree. Server implementation: `git archive --format=zip HEAD` streaming. Mirrors the `/@alice/wiki.git` clone dispatch in structure.
- **`/explore`** — featured/curated slot AND a recent slot. Not just recent. Owner can mark wikis as featured (TBD how admin chooses site-wide features).
- **Star / fork count, profiles, `/@user` pages** ship in v1.

## Search

- **Cmd+K omnisearch cross-wiki from day one.** Scoped to what the viewer can see. Postgres `tsvector` + GIN index. Global and per-wiki scope options. (This overrides prior-session notes that had it as v2.)
- **Search-or-create fallback.** When cross-wiki search returns zero hits, Cmd+K offers "Create `<query>`" as the first action — creates a new page in the currently-focused wiki with the query as the title and drops the user into the editor. Matches Obsidian and Notion behavior.
- **Tag filters.** Cmd+K accepts `tag:<name>` prefix to filter by tag. Tags come from frontmatter's `tags:` field (Obsidian-compatible).
- **Tag index pages.** `/@user/wiki/tag/:name` renders a list of every page in the wiki carrying that tag. Tag counts shown on the wiki's landing page.

## Rendering behavior (v1)

- **Content negotiation** on every page URL (see Agent surfaces below).
- **Wikilinks** `[[Page]]` and `[[path/to/page]]` resolved via the custom markdown-it plugin. Unresolved wikilinks render as red-dashed with a "create" affordance for users with edit permission.
- **Inline images**: standard markdown `![alt](path.png)` AND Obsidian embed syntax `![[image.png]]`, with optional width specifier `![[image.png|300]]` → 300px. Image paths resolve relative to the page. Covered formats: png, jpg, jpeg, gif, webp, svg, avif.
- **Folder index files (Quartz-style).** Any subfolder within a wiki can contain an `index.md` (or `README.md` as a fallback). When browsing to `/@user/wiki/folder/`, the renderer renders that file as the folder's landing page. If no index file exists, an auto-generated file listing is rendered (GitHub-style). This extends the wiki-root `index.md` convention (Karpathy's scaffold) into arbitrary subfolders. Visibility cascades from the folder's ACL glob unless the index file's own frontmatter overrides.
- **External links** open in new tab (`target="_blank" rel="noopener noreferrer"`). Internal wikilinks stay in the current tab.
- **KaTeX** for `$inline$` and `$$display$$` math. **highlight.js** for fenced code blocks. **markdown-it-footnote** for `[^1]` footnotes.
- **`<!-- private -->...<!-- /private -->` bands** stripped from public-mirror serving and `Accept: text/markdown` responses, but kept in the authoritative repo. Visible UI warning on pages that contain private bands.

## Web editor (v1)

- Markdown editor with `[[wikilink]]` autocomplete.
- Live preview with the full reader pipeline (KaTeX, code highlighting, footnotes).
- Visibility toggles that write to frontmatter or the ACL file as appropriate.
- Not a collaborative-editing surface — last-write-wins, git conflict on concurrent edits.
- Collaborative editing (CRDT / OT / realtime) is **v2+, not v1**. Not biased toward realtime; async-first.

## v2 / v3 deferred list

**v2:**
- Paste-unstructured-text → LLM generates wiki (server-hosted coding agent with platform key; leaning headless Claude Code over raw Anthropic tool-use)
- URL / repo connect (import from public git repos)
- Omni-convert upload (PDF/DOCX/txt/video → markdown via pandoc/tika/whisper/OCR)
- HTML / Google Sites importer (for the migration wiki targets)
- Comments on pages and wikis (comments role already in ACL vocabulary)
- D3 force-graph render of wikilinks
- Inline diff UI for suggested edits
- Friends-list / group creation UI (grant syntax is v1, the management UI is v2)
- Real-time collaborative editing
- **All anti-abuse machinery from the strip above** (rate limits, moderation view, revert tooling, panic button, under-attack mode, notifications, quarantine, PoW, CAPTCHA, body caps, honeypot, owner notifications)
- Server-hosted cloud agent (talk-to-an-agent-we-host via web UI, per-user folder sandbox via UNIX permissions — cheap version of Cortex)
- Featured curation admin surface

**v3:**
- git-crypt escape hatch for encrypted personal wikis (see jacobcole.net/labs pattern)
- Multi-human-one-agent session semantics
- Full Wikipedia-grade moderation tooling (edit filters, trust levels, auto-revert bots)
- Org / multi-tenant surface (Anthropic intranet target — principal table shape is ready for this)

## Migration targets (dogfood)

Queued for week-one launch to validate before any marketing:

- admitsphere (currently elsewhere)
- RSI wiki (currently elsewhere)
- Systematic altruism wiki (currently Google Sites)
- jacobcole.net/labs (uses git-crypt pattern)
- Jacob's CRM (markdown-based personal CRM)

Each gets a one-off Python script to scrape/transform and produce a zip we upload. Scripts are throwaway. No general-purpose importers in v1.

## Open questions still on the table

Explicitly unresolved and worth re-asking:

1. **Quartz — fork, style-reference, or ignore?** I recommended "use as style reference, don't fork" as proceed-unless-vetoed, but it was never explicitly confirmed. Quartz is a static site generator with 11k stars, used by Stanford for course materials, has a nice renderer + graph view but zero backend. Forking gets you ~20% of the codebase (render) and a Next.js/esbuild grafting tax. Using it as a style reference gets you the same 20% with zero grafting.

2. **"Yegge model" — RESOLVED.** It's **beads**, Steve Yegge's git-friendly issue tracker (github.com/steveyegge/beads), already installed in listhub's `.beads/` dir. Architecture: SQLite (WAL) as operational store + `.beads/issues.jsonl` as git-tracked export + git hooks for bidirectional sync. Beads's source-of-truth is SQLite (structured), wikihub's is git (authored markdown) — opposite directions, deliberate. Lessons worth porting into wikihub: `.wikihub/events.jsonl` for git-tracked audit of ACL/visibility/fork/star mutations (mirrors beads's `events-export: true`); line-oriented formats for anything under `.wikihub/` that might merge-conflict; hash-based IDs (already aligned via nanoid). Not in this doc's open-questions list anymore.

3. **Deployment domain and host.** wikihub.globalbr.ai? wikihub.io? Cohabit with listhub on the same Lightsail box (new systemd unit + nginx vhost)? New instance? Cloudflare setup? Not asked yet.

4. **Auth providers beyond Noos.** Boris/Anthropic targets likely want Google OAuth (for Anthropic SSO) or GitHub OAuth (the ML crowd has these). Prior session locked Noos; today's transcript didn't revisit. Worth confirming whether to add Google / GitHub OAuth in v1.

5. **Does signup rate-limit-per-IP survive the security strip?** The user stripped "all the security features" in the context of content-moderation for anonymous writes. Basic signup rate limiting is arguably infrastructure, not moderation. Default assumption: it stays. Confirm if asked.

6. **Featured curation mechanism.** The /explore homepage has a featured slot AND a recent slot. Who decides what's featured? Site admin via a DB flag? User-nominated? Automatic based on stars? Not specified.

7. **Exact rendering of collaborative-editing posture.** Confirmed: v1 is not realtime. But is it last-write-wins-on-save, git-merge-on-conflict, or optimistic-locking? Not specified.

8. **Milkdown vs. simpler markdown editor.** listhub chose Milkdown (WYSIWYG, round-trip-clean markdown, plugin architecture, proven from listhub's usage) — strategic copy opportunity. Alternative: simpler markdown textarea + wikilink autocomplete, smaller bundle, no dependency on Milkdown's plugin ecosystem evolution. Pending discussion.

## Things I said I'd "proceed unless vetoed" on (none were vetoed)

- **Principal abstraction** for ACL grants (user / group / link_token / anyone / org types).
- **Commenter role in v1 ACL vocabulary** (behaves as viewer until comments ship).
- **`<!-- private -->` visible UI warning** on pages containing private bands.
- **Kill FTP** (confirmed).
- **Reader stack:** markdown-it + markdown-it-footnote + markdown-it-katex + highlight.js + custom wikilink plugin, Inter / IBM Plex Mono, dark theme, CSS variables.
- **Don't fork Quartz**, use as style reference. (Still not explicitly confirmed, but I'm treating it as locked.)
- **Ship all cheap agent manifests:** AGENTS.md, llms.txt, llms-full.txt, both .well-known/mcp shapes, wikihub.json bootstrap, Accept: text/markdown content negotiation with Vary and Link headers, JSON-LD on HTML.
- **Write commit authors** use `anonymous <anon@wikihub>` for anonymous writes (required by git).

## Listhub code to port verbatim

From `listhub/CLAUDE.md` and the prior-session memory:

- `git_backend.py` — git Smart HTTP (clone/push/receive-pack/upload-pack), repo init, hook install. Generalize paths for multi-wiki.
- `git_sync.py` — DB→git plumbing using `GIT_INDEX_FILE` + `hash-object` + `update-index --cacheinfo` + `write-tree` + `commit-tree` + `update-ref`. No working tree. Does NOT fire hooks (critical invariant — prevents two-way-sync loop).
- `hooks/post-receive` — parses pushed .md files, extracts frontmatter, calls admin API to upsert Page rows.

Do a 30-minute spike to confirm no hidden coupling to listhub's flat item schema before committing to the port.

## Research docs to consult

In this subfolder (`listhub/research/wikihub-spec-work-2026-04-08/`):
- `agent-first-web-brief-2026-04.md` — authoritative source for agent-first web standards (WebMCP, llms.txt, .well-known manifests, content negotiation, agent-native auth, agent identity). Built by a subagent this session.

In `listhub/research/` (parent directory, pre-existing):
- `../llm-wiki-research.md` — five-sense taxonomy of "LLM wiki" (Karpathy personal / AI-generated encyclopedia / wikis-for-LLMs / wikis-about-LLMs / human+AI collaborative).
- `../llm-wikis-catalog.md` — ~85 concrete wikis across the five senses.

## Philosophy

- **Infrastructure, not app.** wikihub is the memory layer + git host. Agents are clients. The site stands alone and serves any LLM/agent.
- **Separate repos, seamless integration.** A coding agent should need <50 lines to fully operate a wiki here.
- **YAGNI.** Ship v1 without anti-abuse machinery. Ship v1 without comments. Ship v1 without a collaborative-editing stack. Iterate reactively.
- **API for writes, git pull for reads.** Same split as listhub.
- **Read liberally, write conservatively** (Postel's Law for frontmatter compatibility).
- **Trust the agent era on velocity.** No time estimates in weeks/months for coding-agent work.

---

*End of handoff. Everything above this line is portable context for the fork.*
