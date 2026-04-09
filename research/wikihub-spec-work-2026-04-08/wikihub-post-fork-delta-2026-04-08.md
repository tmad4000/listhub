# wikihub — post-fork delta (2026-04-08)

This is the **delta** from a `/branch` point on 2026-04-09 01:04 UTC. Paste into the parent session to bring it up to the branch's current state without re-opening closed questions. Everything below is *new* since the fork — it does not restate decisions the parent session already knows.

Parent session started its branch with the user asking "what is pack filtering?" — the answer and everything after are what this document captures.

## 1. Pack filtering rejected. Public-mirror pattern adopted.

We discussed "dynamically filter a git pack per request" (rewriting tree/commit hashes at clone time via libgit2) and rejected it as a research-project-in-the-wrong-shape. The user offered a cleaner reframe that became load-bearing:

**Every wiki exists as two bare git repos.**

- `repos/<user>/<slug>.git` — authoritative. Owner only. Contains everything including `.wikihub/acl` and any files marked private for the owner.
- `repos/<user>/<slug>-public.git` — derived public mirror. Regenerated on every push. Contains only public files; `<!-- private -->` sections stripped from markdown; `.wikihub/acl` itself omitted.

**Flask dispatches clone requests by auth:**

```
GET /@alice/crm.git/info/refs?service=git-upload-pack
  owner?  → git-http-backend on repos/alice/crm.git
  else?   → git-http-backend on repos/alice/crm-public.git
```

Stock `git-http-backend`, stock `git-upload-pack`. `git clone`, `fetch`, `push`, `blame`, `bisect`, LFS, partial clone — all work unchanged on both repos. No custom libgit2, no wire-protocol surgery. The cleverness happens once per push in the regeneration hook, not per clone.

**Public mirror history is linearized.** Each regeneration force-updates `HEAD` to a single new commit `Public snapshot @ <source-sha>`. No history preservation on the mirror. `git blame` on the mirror is deliberately useless; authorship surfaces from Postgres on rendered pages. Mirror is a publishing artifact, not a parallel history.

**Two separate bare repos (not two refs in one repo)** — chosen for auditability. Filesystem permissions separate them, and you can `ls -R` the public mirror on disk to confirm no private content leaked.

**Private pages never enter git at all.** They live in Postgres only. The `git` layer is coarse (owner-or-not); the Postgres layer is fine-grained per-file. This is the honest answer to "git can't filter packs per-user" — stop trying, and split storage by access tier.

## 2. Postgres confirmed (not SQLite)

Parent session had drifted toward SQLite on scope-cut grounds. The branch overruled that — Postgres is locked. Reasons: concurrent writes on shared tables (stars, forks, ACL grants), `jsonb` for frontmatter and ACL rows, `tsvector` for cross-wiki full-text search, room for row-level security later. The "1-week scope" worry is not load-bearing for Postgres-vs-SQLite because coding agents don't feel that choice as a velocity difference.

## 3. ACL storage: `.wikihub/acl` (CODEOWNERS pattern)

The single biggest design decision in the branch. Access control lives in a git-tracked file at `.wikihub/acl` that uses the same pattern git itself uses for `.gitignore`, `.gitattributes`, and `CODEOWNERS`: **glob rules, most-specific wins, private by default, `#` comments**.

Example (this is what every new wiki scaffolds to, header included so LLMs reading the file cold understand the format without a skill):

```
# wikihub ACL — declarative access control for this wiki.
#
# Rules are glob patterns. Most-specific pattern wins. Default is `private`.
#
# Visibility: public | unlisted | public-edit | unlisted-edit | private | signed-in
# Grants:     @user:role | group:name:role | link:token:role
# Roles:      read | comment | edit | admin

* private

wiki/**                   public
wiki/karpathy-private.md  private
private-crm/**            @alice:edit
drafts/**                 unlisted
community/**              public-edit
legal-review/**           link:r4nd0m-t0k3n:read
```

**Why this pattern won over alternatives:**
- **Per-file YAML sidecars** (`page.md` + `page.md.acl`): doubles tree entries, orphan risk, rename drift. Rejected.
- **Frontmatter only**: markdown-only, can't express bulk rules or non-markdown files (PDFs, images). Rejected as sole mechanism.
- **Flat enumeration index** (one file listing every path): merge conflicts, doesn't express folder patterns, doesn't scale. Rejected.
- **CODEOWNERS pattern**: git-native, diffable, blameable, file-type agnostic, private-by-default is one line, scales tiny-to-huge, safe failure modes (missing → all private, malformed → reject push). Selected.

**`.wikihub/` is the platform dotfolder**, peer to `.git/`, `.github/`, `.claude/`. Future home of `config`, `schema.md`, `webhooks`, etc. Agents that know `.github/` will recognize `.wikihub/` immediately as "platform metadata, hands-off unless changing platform behavior."

**Safe failure modes:**
- Missing `.wikihub/acl` → whole wiki treated as private.
- Malformed file → push rejected with clear error; previous version stays in effect.
- Unknown rule types → parsed, logged as warnings, don't break the file.

## 4. Frontmatter + ACL file compose via specificity, not authority

Earlier framing had frontmatter as "just a hint." Corrected to: **both are authoritative for different scopes**, composed by specificity.

Precedence ladder (most specific wins):
1. Frontmatter on the file itself.
2. ACL file rule matching the path, most-specific pattern first.
3. Repo default (`* private`, implicit).

No two-sources-of-truth problem because they operate at different granularities. The ACL file is for **bulk patterns** ("everything in `wiki/` is public"). Frontmatter is for **single-file exceptions** ("this one page is different"). Same resolution model as `git config` (system < global < local < flags) or CSS specificity.

## 5. Obsidian frontmatter compatibility

Zero hard conflicts; several free migration wins identified.

**wikihub's own frontmatter keys** (`visibility`, `share`) don't collide with any Obsidian reserved key. They render as custom properties in Obsidian's Properties panel; Dataview queries can filter on them for free.

**Read liberally, write conservatively** (Postel's Law applied to config):

On **read**, honor Obsidian conventions:
- `publish: true/false` → treat as alias for `visibility: public/private`. Wikihub-native `visibility:` wins on conflict. **Gives Obsidian Publish migrants a zero-rewrite migration** — just point their existing vault at wikihub as a git remote and push; pages they had publishing already become public automatically. This is specifically worth calling out in a launch post.
- `aliases` → honored for `[[wikilink]]` resolution.
- `permalink` → honored as URL slug. Migrating Obsidian Publish users keep their URLs.
- `description` → used for OG tags and llms.txt excerpts.
- `tags` → honored, both list and flow syntax accepted, leading `#` stripped.
- `cssclass` / `cssclasses` → applied to rendered `<article>`.

On **write**, only touch keys wikihub owns (`visibility`, `share`). Never clobber keys we didn't put there. Round-trips cleanly in both directions: edit in wikihub web UI → clone to Obsidian → edit there → push back → wikihub preserves all the Obsidian-specific keys.

## 6. Permission model — 3 axes + named modes

Every permission state decomposes into **three orthogonal axes**:

1. **Read audience**: owner | grantees | link-holders | signed-in | anyone
2. **Write audience**: same ladder
3. **Discoverable**: indexed | hidden

The "visibility modes" are just named shortcuts for common (read, write, discoverable) triples plus optional explicit grants — the same way `chmod 644` is a shortcut for `rw-r--r--`.

**v1 mode vocabulary:**

| Mode | Read | Write | Discoverable |
|---|---|---|---|
| `private` | owner | owner | no |
| `public` | anyone | owner | yes |
| `public-edit` | anyone | **anyone, anonymous OK** | yes |
| `unlisted` | URL holders | owner | no |
| `unlisted-edit` | URL holders | **anyone with URL, anonymous OK** | no |
| `signed-in` | any signed-in | owner | yes |
| `link-share` | token holders | owner | no |
| `shared` | per explicit grants | per grants | no |

**Grant syntax in the ACL file:** `@user:role`, `group:name:role`, `link:token:role`.

**Roles vocabulary:** `read`, `comment`, `edit`, `admin`. `comment` ships in v1 vocabulary but behaves as `read` until comments feature ships in v2 — zero-migration activation when comments land.

**Principal abstraction:** ACL grants reference a polymorphic `principals` table with types `user | group | link_token | anyone | org`. The `org` type reserves space for the Anthropic-intranet future target at zero current cost — no schema migration needed when multi-tenancy ships.

## 7. Both `public-edit` AND `unlisted-edit` allow anonymous writes

User explicit decision, overruling my recommendation to require signed-in accounts. Google Docs link-edit model extended to the indexed case. Current-Wikipedia style: anyone who hits the page can edit.

This applies to:
- `unlisted-edit` (wiki/page has an unguessable URL; anyone with the URL can read and write, no account)
- `public-edit` (wiki/page is indexed in /explore and search; anyone, anywhere, can read and write, no account)

Both modes allow **fully anonymous** writes. No sign-in, no email, no account.

## 8. ALL anti-abuse / moderation machinery cut from v1

A full anti-vandalism plan was drafted and then **entirely removed from v1** at user direction. Ship anonymous-writes naked; iterate reactively when problems actually occur. Trust mode.

**OUT of v1 (all deferred to v2/v3):**
- Per-IP / per-token / per-wiki write rate limits
- Honeypot form field on edits
- Actor logging beyond a basic nullable author field
- Moderation view (filtered edit history for owner)
- Bulk revert tooling (no "revert all edits by actor X," no "revert time range")
- Panic button (instant disable of anonymous writes on a wiki)
- Auto-under-attack detection and state machine on edit rate
- Owner notifications (email / webhook on anonymous edits)
- Quarantine queue for pending-review edits
- Proof-of-work reactive throttling
- Body size caps, link count caps on writes
- CAPTCHA escape hatch
- "Are you sure?" warnings when enabling public-edit
- Default-off policy for public-edit on new wikis
- `crawl: false` per-wiki opt-out from llms.txt / sitemap
- Edit filters, trust levels, spam heuristics

**IN for v1 (basic plumbing only, forced by git itself):**
- Anonymous git commits get `anonymous <anon@wikihub>` as the git author. Required by git; not a moderation feature.
- Pages table has a nullable author field. No elaborate polymorphic actor schema.
- Basic signup rate limit per IP is *probably* still in (infra, not content moderation — confirm if this comes up).

**Philosophy locked:** "ship it, iterate reactively when real problems happen." The inversion from fail-closed to fail-open is deliberate. Pre-launch, there's nothing to moderate; we'll learn more from watching real abuse than from speculating about mitigations.

## 9. `<!-- private -->` HTML-comment sections

Ships in v1 as a lightweight sub-file privacy convenience:

- `<!-- private -->...<!-- /private -->` blocks in markdown are **stripped from the public mirror and from `Accept: text/markdown` content-negotiated responses**.
- They REMAIN in the authoritative repo, intact. Anyone with owner-level git access sees them.
- Visible UI warning on pages containing private bands: "this page has sections visible only to editors; not a security boundary — don't use it for real secrets."
- Framed as a **parasitic syntax** (rides on markdown's HTML-preserving rule) and a **best-effort convenience**, not a security primitive.
- Does not compose with the share graph. Binary: stripped-for-public or present-for-owner. For "visible to alice but not bob," split the private chunk into its own file with a per-file ACL grant.

## 10. Cmd+K cross-wiki omnisearch promoted to v1

Prior-session memory had "Cmd+K global fuzzy search" as v2 ticket #7. The branch promoted it to v1 per the user's transcripts ("wikihub needs it cross-wiki from day one"). Implementation: Postgres `tsvector` + GIN index per page, scoped to the viewer's visible set (public + anything shared with them). Global and per-wiki scopes on the same endpoint.

## 11. Additions from listhub requirements mining (reviewed)

A research pass across listhub's 162 commits and 90 beads tickets (`.beads/issues.jsonl`) surfaced implied requirements that wikihub hadn't captured. The reviewed decision record lives in `wikihub-listhub-requirements-mining-reviewed-2026-04-08.md`. Summary of what was added to v1:

**Locked additions:**

- **Binary files live in the git repo alongside markdown** (Obsidian-style attachments). No quota in v1. Git LFS not used. Future escape hatch: globalbr.ai S3 bucket with markdown links rewritten server-side to signed URLs (v2+).
- **Inline image rendering**: standard markdown `![alt](path.png)` AND Obsidian embed `![[image.png]]` with optional width (`![[image.png|300]]`). Renderer stack adds `markdown-it-image-figures` + a custom Obsidian-embed plugin.
- **File rename/move endpoint**: `PATCH /api/v1/wikis/:owner/:slug/pages/*path {new_path}`. Performs git-mv equivalent via plumbing, rewrites all `[[wikilinks]]` pointing to the old path, single atomic commit. MCP tool `move_page(old_path, new_path)`.
- **Machine-readable permission error bodies** on every 401/403:
  ```json
  {"error": "insufficient_permissions", "reason": "...", "required_role": "edit", "your_role": "read", "suggested_actions": [{"verb": "fork", "endpoint": "...", "method": "POST"}, ...]}
  ```
- **ZIP download endpoint**: `GET /@alice/wiki.zip`, auth-dispatched to authoritative or public mirror. Server runs `git archive --format=zip HEAD` streaming.
- **Tag index pages**: `/@user/wiki/tag/:name` lists every page carrying that tag. Cmd+K `tag:<name>` filter prefix. Tag counts on wiki landing.
- **Search-or-create fallback** in Cmd+K when zero hits.
- **External links open in new tab** (`target="_blank" rel="noopener noreferrer"`).
- **Visibility UI labels**: internal names stay short (`public`, `public-edit`); UI labels disambiguate (`public (read)`, `public (edit)`, etc.).
- **Visibility badges everywhere**: every item-rendering surface shows a visibility icon. Not polish — table-stakes UX.
- **Folder index files (Quartz-style)**: any subfolder can contain `index.md` (or `README.md` fallback) which renders as the folder landing page. Auto file listing if none. Visibility cascades from the folder's ACL glob.
- **Mobile-friendly v1** as a top-level non-functional requirement. Mobile-first CSS, 44×44 touch targets, hamburger sidebar on narrow viewports, full-screen Cmd+K modal on mobile, 16px minimum body text.
- **Mockup-first workflow**: `mockups/` directory from day one. Standalone HTML mockups for every significant surface (landing, profile, reader, editor, search, explore, folder view, visibility panel, permission error page, mobile versions of each) before implementation code is written. Pattern ported from listhub.

**Still open after review:**

- **Milkdown vs. simpler markdown editor.** User flagged for discussion. Pro Milkdown: WYSIWYG, proven from listhub, plugin architecture. Pro simpler: smaller bundle, no dependency-evolution risk. Pending.

**Dropped during review:**

- `.folder.yaml` / `.wikihub/defaults.yaml` for per-folder metadata defaults. Replaced by folder index files (above).

Full traceability to source beads tickets is in the reviewed mining doc.

## 12. Boris drift correction

Earlier passes had drifted Boris (an Anthropic engineer) from "partnership goal mentioned in a Granola transcript" to "first-user design persona" to "reader-UI quality bar." That drift was unwarranted — the only source was one bullet in a meeting transcript saying "we want to get Boris using this," which is a distribution target, not a design persona.

**Corrected framing (applied to handoff doc):**

- **First users (v1)**: the dogfood migrations (admitsphere, RSI wiki, systematic altruism wiki, jacobcole.net/labs, Jacob's CRM); the Karpathy-gist wave of ~20 recent GitHub implementations and their authors; Obsidian vault owners looking for an agent-aware publish target better than Obsidian Publish or Quartz.
- **Distribution goal (not a design persona)**: get Boris / team at Anthropic using wikihub. Partnership angle, post-launch outreach. Do not design v1 around what Boris would like.
- **Future target**: Anthropic intranet — LLM wikis for companies. Drives the principal-abstraction choice above; nothing else in v1.

The reader-quality bar (KaTeX, code highlighting, footnotes, clean dark typography) still ships, but justified by "the Karpathy wave expects a real reader for ML content," not "Boris is the imagined judge."

## Open questions inherited and still open

These were open in the parent session too and are still open:

1. **Quartz — fork, style-reference, or ignore?** My proceed-unless-vetoed suggestion: use as style reference for the renderer, don't fork. Not explicitly confirmed.
2. **"Yegge model" — RESOLVED.** It's **beads** (github.com/steveyegge/beads), Steve Yegge's git-friendly AI-agent issue tracker. Already installed in listhub's `.beads/` dir — the `bd sync` commits in listhub's git log are beads flushing SQLite→JSONL. Architecture: SQLite-in-WAL as operational store, `.beads/issues.jsonl` as git-tracked export, git hooks (pre-commit / post-checkout / post-merge / pre-push / prepare-commit-msg) keep the two in sync. Beads's source of truth is SQLite; wikihub's is git. Opposite directions, deliberate (wikihub's primary content is authored markdown, not structured fields). Lessons worth porting: `.wikihub/events.jsonl` audit export mirroring beads's `events-export: true`; line-oriented formats everywhere in `.wikihub/` (CODEOWNERS-pattern ACL is already aligned); hash-based IDs (already via nanoid).
3. **Deployment domain and host** — wikihub.globalbr.ai? cohabit with listhub on the same Lightsail box? Not asked yet.
4. **Auth providers beyond Noos** — Google / GitHub OAuth for the ML crowd? Not asked.
5. **Does signup rate-limit-per-IP survive the security strip?** Infra vs moderation classification is ambiguous; default assumption is "stays" but confirm.
6. **Featured curation mechanism** — who picks featured wikis on `/explore`?
7. **Concurrent-edit resolution posture** — last-write-wins, git-merge, optimistic-lock? v1 is not realtime, but the non-realtime policy isn't specified.

---

*End of delta. Paste this into the parent session to bring it up to date with the branch. Do not re-debate the decisions above unless new information arrives — they were each made deliberately in response to a specific user instruction in the branch.*
