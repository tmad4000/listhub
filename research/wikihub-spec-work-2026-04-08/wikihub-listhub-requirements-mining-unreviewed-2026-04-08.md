# wikihub — requirements mining from listhub git history + beads tickets (UNREVIEWED)

> **Status:** UNREVIEWED — this is the raw research pass *before* the user reviewed it. For the reviewed version with decisions locked in, see `wikihub-listhub-requirements-mining-reviewed-2026-04-08.md`. Kept as-is for traceability; do not edit.

**Date:** 2026-04-08
**Sources:** 162 commits in `listhub` main branch + 90 beads tickets in `.beads/issues.jsonl`
**Purpose:** Identify implied requirements, user stories, and features from listhub's development history that the wikihub spec does not currently cover. Organized as aligned / genuine gaps / UX and naming conventions to inherit.

## Summary

Of the 90 beads tickets scanned:

- **~55 tickets** are already covered by the wikihub spec.
- **~15 tickets** are listhub-specific (naming-of-old-features, bug fixes on current sidebar, import targets) that don't port.
- **~20 tickets** surface genuine gaps or refinements the wikihub spec does not capture today.

Nothing is catastrophically missing, but several are concrete enough to fold in before implementation.

---

## Bonus resolution from this research

**The "Yegge model" open fork from prior-session memory is resolved.** It's **beads**, Steve Yegge's git-friendly issue tracker (https://github.com/steveyegge/beads). Architecture: SQLite in WAL mode as operational store, `.beads/issues.jsonl` as the git-tracked export, git hooks (`pre-commit`, `post-checkout`, `post-merge`, `pre-push`, `prepare-commit-msg`) as the sync glue, optional daemon for RPC. The `bd sync` commit messages throughout listhub's log are beads flushing SQLite to JSONL.

**Notable inversion vs. wikihub:** beads has SQLite as source of truth with JSONL derived. Wikihub has git (markdown files) as source of truth with Postgres derived. Both patterns are valid; they optimize for different things. Beads optimizes for "agent queries need to be fast over structured data." Wikihub optimizes for "users expect to clone, edit, and push their markdown content."

**Lessons worth porting into wikihub from beads:**
1. `.wikihub/events.jsonl` mirror of beads's `events-export: true` option for a git-tracked audit log of ACL/visibility/fork/star mutations. Useful for reconstructing DB state from scratch.
2. Line-oriented formats for anything under `.wikihub/` that might merge-conflict (our CODEOWNERS-pattern `.wikihub/acl` is already aligned).
3. Hash-based IDs to prevent merge collisions in multi-agent workflows (already aligned via nanoid).

---

## Aligned — spec already covers these

Quick inventory to prove wikihub hasn't missed the obvious stuff.

| listhub ticket | covered by wikihub spec section |
|---|---|
| `listhub-a2o` Wikis as first-class objects | `Wiki` is the top-level object |
| `listhub-94f` / `listhub-95u` Global search / Cmd+K quick switcher | Cmd+K cross-wiki omnisearch v1 |
| `listhub-erm` Unlisted visibility | `unlisted` mode in vocabulary |
| `listhub-z0t` Publicly editable (closed) | `public-edit` mode |
| `listhub-xtc.1` Anonymous unauthenticated editing | Anonymous writes on both edit modes |
| `listhub-8wi` Per-user sharing with write permission | ACL grant `@user:edit` |
| `listhub-t41` Implement WebMCP | Agent surface section (WebMCP day one) |
| `listhub-2jg` Agent self-service onboarding (closed) | `POST /api/v1/accounts` |
| `listhub-u02` User account rename | `PATCH /me` with 90-day redirects |
| `listhub-rmb` Noos centralized auth | Noos OAuth SSO day one |
| `listhub-3q6` llms.txt and agent discovery | Content negotiation + llms.txt + .well-known manifests |
| `listhub-480` Agent onboarding skill / llms.txt instructions | AGENTS.md + agent surface |
| `listhub-r7u` / `listhub-bwl` API key login / recovery | API keys, Bearer auth, rotate endpoints |
| `listhub-yx1` share/publish/private as first-class API ops | MCP tools `set_visibility`, `share` |
| `listhub-ev1` Clone URL and download button | `git clone` URL (ZIP download is a gap — see below) |
| `listhub-xtc` GitHub-like repo UX (epic) | wikihub's whole thesis |
| `listhub-cuq` Real-time collaborative editing | Correctly deferred to v2+ |
| `listhub-zyc` Comments or suggested additions | Comments v2; suggested edits v1 |
| `listhub-74j` Folder-level visibility with cascade | Covered via `.wikihub/acl` globs |
| `listhub-f18` Per-line visibility | `<!-- private -->` HTML comment bands |
| `listhub-7aw` Agent-first web (epic) | Our entire agent surface section |
| `listhub-hon` LLM Wiki Book | Dogfood content, not a spec feature |
| `listhub-r62` Agent-native Google Drive replacement (epic) | wikihub's positioning |
| `listhub-16c` Agent-friendly search surface | Cmd+K + MCP `search` tool |
| `listhub-an8` Visibility badges on items | Called out as required UX |

---

## Gaps — genuine implied requirements not in the wikihub spec

Organized by v1 importance.

### v1 — should be added to the spec before implementation

**1. Binary file storage architecture (`listhub-2zv`).** This is the biggest gap. The spec talks about markdown files and hand-waves "any file type" for the ACL system, but never answers the structural question: **where do images, PDFs, and attachments actually live?**

Four options, each with real tradeoffs:
- **In the git repo as regular blobs** — works for small images (<1MB each, <100MB total per wiki). Git doesn't love large binaries; `git clone` gets expensive, blame/diff are useless, but everything-in-one-repo is conceptually clean.
- **In the git repo via Git LFS** — standard answer for binaries in git, but adds LFS server infra and clients need LFS installed.
- **External object store** (S3, Cloudflare R2, Noos bucket — `listhub-2zv` considers all three), referenced by path or URL from markdown. Decouples binary size from repo size. Breaks the "everything is in the repo" story.
- **Per-wiki quotas** on binary size, mix of in-repo small + external large.

Recommendation: **in-repo as default, quota-gated** (50MB total binaries per wiki in v1) with a clear path to LFS or object store when a wiki outgrows that. The decision has to be made, not hand-waved. **Add to spec as an open question requiring explicit resolution.**

**2. Inline image support (`listhub-c6x`).** Related to gap #1 but separable: does the renderer handle standard markdown images (`![alt](path.png)`) and Obsidian's embed syntax (`![[image.png]]`)? The spec mentions the markdown-it pipeline but doesn't list an image plugin or Obsidian-embed support. Both should be explicit. Obsidian embed syntax is cheap (a single custom markdown-it plugin) and is another compatibility win for vault migration.

**3. File rename / move endpoint (`listhub-xrx`).** Spec has `POST /pages`, `GET /pages/*path`, `PUT /pages/*path`, `DELETE /pages/*path` but no rename/move operation. Rename is common and ugly if you have to delete-and-recreate (loses git history connection, loses wikilinks that pointed to the old name). Should be an explicit first-class operation that uses git's file-rename detection and updates wikilinks in one commit.

Proposed API: `PATCH /api/v1/wikis/:owner/:slug/pages/*path` with body `{new_path: "..."}` — performs `git mv`-equivalent via plumbing, rewrites wikilinks targeting the old path across the wiki, produces a single commit.

**4. Machine-readable permission error bodies (`listhub-n5g`).** The spec says "per-key scopes" and "403 on unauthorized" but doesn't specify the error shape. For agents, the error body matters a lot — a 403 with an empty body is useless; a 403 with structured JSON is actionable. Proposed convention for the REST API:

```json
{
  "error": "insufficient_permissions",
  "reason": "This page requires edit access; you have read access.",
  "required_role": "edit",
  "your_role": "read",
  "suggested_actions": [
    {
      "verb": "fork",
      "description": "Fork this wiki and edit your copy",
      "endpoint": "/api/v1/wikis/:owner/:slug/fork"
    },
    {
      "verb": "request_access",
      "description": "Ask the owner for edit access",
      "endpoint": "/api/v1/wikis/:owner/:slug/access-requests"
    }
  ]
}
```

Agents can parse `suggested_actions` and offer the user a choice. Much better UX than "403 Forbidden."

**5. ZIP download of wiki (`listhub-a3e`).** Lots of users and some agents prefer a single ZIP over `git clone`. The ticket specifically frames it as "full for owner, filtered for others" — which maps perfectly onto the authoritative-vs-public-mirror split. It's one endpoint, `GET /@alice/wiki.zip`, that tars/zips whichever repo the Flask dispatch routes to based on auth. Probably 20 lines of code, significant UX win. **Add to v1 social layer.**

### v1 refinements — small but shouldn't be forgotten

**6. Tag index pages (`listhub-l91`).** The spec honors Obsidian's `tags:` frontmatter key but doesn't say what we do with it. For parity with Obsidian + Karpathy wiki patterns, tags should get:
- A `/@user/wiki/tag/:name` page listing every page with that tag
- Tag filters in Cmd+K search
- Tag counts in the wiki's explore surface

**7. Search-or-create in Cmd+K (`listhub-3wv`).** When cross-wiki search returns zero hits, Cmd+K should offer "Create `<query>` as a new page" as the first action. Tiny UX feature, high delight, matches Obsidian and Notion expectations.

**8. External links open in new tab (`listhub-ary`).** Trivial but meaningful. The markdown-it config should add `target="_blank" rel="noopener noreferrer"` to external links by default.

**9. Visibility labels in the UI (`listhub-9nm`).** `public` is ambiguous — does it mean "anyone can read" or "anyone can edit"? Display labels should use `public (read)`, `public (edit)`, `unlisted (read)`, `unlisted (edit)` even though internal mode names are the shorter forms. listhub learned this the hard way via `listhub-9nm`.

**10. Visibility badges everywhere (`listhub-an8`, reinforced across ~5 commits).** Every page/wiki card in search results, explore, profile, and within the wiki tree should have a small icon indicating its visibility. Table-stakes UX that listhub iterated on repeatedly and the wikihub spec didn't explicitly call out.

**11. Permissions at the top of the edit view (`listhub-1c7`, `listhub-3cm`).** UX rule from listhub: permissions are a first-rank concern, not buried in settings. Put the visibility dropdown at the top of the edit view, not in a modal. Related to the visibility-badges-everywhere lesson.

### v1.5 — next layer of refinement

**12. Git history viewer for wikis (`listhub-2lg`).** A web view of `git log` per wiki (`/@alice/wiki/history`). Useful for users who want to browse changes without cloning. Cheap — wraps libgit2 or pygit2 with a Jinja template.

**13. Public git repo directory at `/git/` (`listhub-j47`).** An index of publicly-cloneable wikis with their clone URLs, grouped by topic. Complements `/explore` by foregrounding the "these are cloneable" angle.

**14. Bulk folder drag-in UI (`listhub-67v`).** Drag a native folder into the browser (not a zip). Modern Chrome supports directory drop via the File System Access API. Better UX than requiring users to zip first.

**15. Folder-scoped default frontmatter.** This is a subset of `listhub-r62.1` (the "unified YAML metadata pattern" ticket). Our `.wikihub/acl` glob file handles ACL defaults per folder, but **folder-scoped default frontmatter for NON-ACL metadata** is not covered — e.g., "every file in `raw/` has `source_type: primary`" or "every file in `wiki/entities/` has `category: entity`." Not an ACL concern; a content metadata concern. Frontmatter handles per-file; globs handle per-folder ACL; but neither cleanly handles "folder default frontmatter that files can override."

Possible design: `.wikihub/defaults.yaml` with glob → field-defaults mappings. Merged at read time with actual file frontmatter. The file-level frontmatter wins. Small, optional feature; document but don't ship in v1 unless demand surfaces.

### v2 — captured for later

**16. Auto-push user repos to GitHub (`listhub-2zb`).** Outbound mirror to GitHub as a backup / visibility option. Lets users keep wikihub AND GitHub in sync. Potentially controversial (adds a third storage tier), but the ticket exists and was taken seriously in listhub.

**17. Google Drive connector (`listhub-7c5`).** One-click import of a Drive folder. Bigger workstream than v1.

**18. Document converter .docx/.doc/.rtf → markdown (`listhub-dwa`).** Already in wikihub's v2 omni-convert ticket. Listhub captured it separately; worth noting the specific formats for when v2 lands.

**19. Multi-sheet CSV/spreadsheet support (`listhub-4jm`).** Renders CSV as a sortable table. Not in wikihub's wheelhouse. Defer indefinitely unless demand appears.

**20. Graph DB for relationships (`listhub-d03`).** Wikilinks graph is in v1 spec. Upgrading to a real graph database (Neo4j, Dgraph) is a v3+ consideration. Defer.

**21. Central user dashboard document (`listhub-ftr`) / Profile page split layout (`listhub-dlo`) / Folder zoom (`listhub-sdw`).** UX polish tickets. wikihub already has `/@user` profiles; these refinements can follow.

---

## UX and naming conventions to inherit from listhub

These aren't individual tickets — they're patterns listhub converged on through iteration that wikihub should adopt from day one.

**22. Three-section persistent sidebar (`listhub-lav`, implemented in listhub).** "Your docs / Community / Focused @user" is listhub's current sidebar structure. Wikihub should start with the same shape: **"Your wikis / Community / Focused @user"** where Focused is a user you're currently browsing. Saves iteration cycles on sidebar architecture — and the listhub commit log has ~15 commits iterating on sidebar edge cases, suggesting it's a non-trivial component that benefits from a known-good starting structure.

**23. Rename `/community` → `/people` and `/directory` → `/featured`** (`listhub-a3p`, `listhub-bno`). listhub ran into UX clarity problems with both names and renamed. Wikihub should start with the renamed versions: `/people` for the user index, `/featured` or `/explore` for the curated slot, `/@user` for a single profile.

**24. Milkdown WYSIWYG editor** (listhub commit `7569f04`). listhub chose Milkdown as its markdown editor. Wikihub's spec suggests a simpler markdown editor with wikilink autocomplete, but **Milkdown is worth reconsidering** — WYSIWYG with round-trip-clean markdown, plugin architecture, proven choice from listhub. Potential stack upgrade from "custom markdown editor with autocomplete" to "Milkdown plus wikilink plugin."

**25. Mockups-driven design workflow.** listhub has a `mockups/` directory with HTML mockup pages used to prototype UX before coding. Commits like `feat(mockups): dynamic /mockups/all-files.html`, `feat(mockups): agent-first-web mockup`, `feat(mockups): ideaflow-memory-v3` show an active mockup-first workflow. Not a spec concern but worth porting to wikihub's dev workflow.

**26. "Cascade-by-default-at-creation"** (commit `63a1fe5`, resolved on `listhub-74j`). When a folder is created, files inside it inherit the folder's visibility by default. Wikihub's `.wikihub/acl` globs give us this for free (`wiki/** public` cascades), but when a user creates a new page under an ACL-governed folder in the web UI, the UI should **show the inherited visibility as the default** and let them explicitly override. This is a UI decision, not a data-model decision.

**27. IdeaFlow Memory branding lineage.** Several commits (`0262972`, `a21e5a4`, `7ee41be`, `0b3503a`, `7699c78`) show listhub has been pitched under the "IdeaFlow Memory" brand in investor and CoS network outreach. There may be pressure to align wikihub's branding with a larger "memory" umbrella. Flag for the product conversation, not the spec itself.

**28. Agent-first web epic is load-bearing marketing positioning.** Many commits reference the `agent-first-web` mockup, persistent agent bar, Cortex integration, llms.txt + AGENTS.md story, webmcp-ecosystem-research mockup, sitewide footer links. This is the thesis listhub has been pitching. `listhub-7aw` is the epic. **Wikihub inherits this thesis directly** — same positioning, same marketing materials should be portable.

---

## Cross-cutting themes from the git log

Patterns visible across 162 commits that aren't individual tickets but that shape how listhub evolved.

**A. Sidebar navigation is a recurring pain point.** At least 15 commits touch the sidebar: indent math, section ordering, collapse/expand, visibility icons, home button placement, headings, parent overflow bugs, flex share bugs, Finder-pattern adoption. Listhub iterated on the sidebar for days. **Lesson for wikihub:** budget real front-end time for the sidebar from day one. It is not a trivial component.

**B. Visibility surface is a recurring theme.** Multiple commits on visibility icons, visibility badges, per-level visibility, item-header badges, visibility label consistency. The lesson, consistent with gap #10 above: **when a product's core value is "fine-grained sharing," the permission surface has to be pervasive and legible, not a settings sub-page.** Wikihub's spec has the data model right but hasn't fully internalized this UX lesson; the fix is to ship visibility indicators everywhere from day one.

**C. listhub is actively iterating and not frozen.** The most recent commits are still adding tickets, fixing sidebar bugs, and adjusting names. Wikihub should not assume listhub is done and freeze a port target. If porting `git_backend.py` and `git_sync.py` verbatim, pin a specific commit SHA and track divergence from there.

**D. The gap between "v2 ticket" and "v2 ticket with granularity"** — wikihub's current v2 list has "omni-convert (PDF/DOCX/txt/video → markdown)" as a single line. listhub's beads have `listhub-dwa` (docx/doc/rtf), `listhub-7c5` (Google Drive), `listhub-67v` (drag-a-folder), `listhub-2zv` (binary storage architecture), all of which are subsets or prerequisites. **When we actually build v2 ingestion, hydrate the spec from listhub's beads granularity rather than from the one-line summary.** The one-line version loses detail the tickets captured.

**E. Iterate on naming.** Multiple commits (`cb931e1` Rename Your Lists → My Lists; `5ff5319` Community Directory → Featured Lists; `cbf1e80` Topics → Featured Lists; `c805c65` Community → People; `0bed980` items → lists) show listhub renaming things repeatedly. Wikihub should expect to iterate on naming too — `wiki`, `page`, `folder`, `share`, `collaborator`, etc. — and design URL structures with that iteration in mind (redirects for old slugs, consistent trailing-slash behavior, stable API versioning).

---

## Things I looked for and did NOT find

A few things explicitly not represented in listhub's history — suggesting wikihub shouldn't prioritize them either:

- **Real-time collaboration:** one ticket (`listhub-cuq`), P3, never worked on. Aligned with wikihub's v2+ deferral.
- **Comments / discussion:** `listhub-zyc` exists but never got built. Aligned with wikihub's v2 deferral.
- **Notifications or webhooks:** not in beads at all. Correctly cut from v1.
- **Mobile-specific UI or apps:** no tickets. Wikihub can be mobile-responsive via server-rendered Jinja without a separate mobile story.
- **Analytics / view counts / dashboards:** not in beads. No need for v1.
- **API rate-limit configuration UI:** not in beads. Consistent with the "ship naked" posture.
- **Federation / ActivityPub:** not in beads. Not a wikihub concern.
- **End-to-end encryption:** only `listhub-2zb` (encrypted items architecture) mentions it, and it's tied to the git-crypt escape hatch pattern we already have as v3.

---

## The five I'd fold into the spec right now

If updating the handoff and delta docs from this research, the **five concrete v1 additions** most worth absorbing:

1. **Binary file storage decision.** Add to open-questions list. Must be resolved, not hand-waved.
2. **Inline image support** — both standard markdown `![alt](path)` and Obsidian `![[image.png]]` embed syntax. Add to the renderer stack.
3. **File rename/move REST endpoint** — `PATCH /pages/*path {new_path}` with wikilink updates in one commit.
4. **Machine-readable permission error bodies** — structured JSON with `error`, `reason`, `required_role`, `your_role`, `suggested_actions`.
5. **ZIP download of wiki** — `GET /@user/wiki.zip`, routed to authoritative-or-public-mirror by auth. Tiny endpoint, big UX win.

Four more as explicit v1 UX refinements:
- Tag index pages (`/@user/wiki/tag/:name`)
- Search-or-create in Cmd+K when zero hits
- External links open in new tab
- Visibility labels displayed as `public (read)` / `public (edit)` / etc.

---

## Source ticket index (P1 open + P2 notable)

Preserved for traceability. "OP" = open, "CL" = closed, "IP" = in progress.

| ID | Pri | Status | Title | wikihub status |
|---|---|---|---|---|
| listhub-r7u | P1 | OP | API-key login: paste-your-key as first-class web auth | covered |
| listhub-bwl | P1 | OP | API key recovery via POST /auth/token | covered |
| listhub-wn4 | P1 | OP | Folder view (GitHub-style auto-listing + README) | covered |
| listhub-95u | P1 | OP | Global search + tag filter + sidebar search | covered (Cmd+K) |
| listhub-lav | P1 | OP | Three-section persistent sidebar | convention to inherit |
| listhub-7aw | P1 | OP | Pioneer the agent-first web (epic) | aligned thesis |
| listhub-59n | P1 | OP | Keep API docs and GUI in sync for sharing/visibility | convention |
| listhub-2jg | P1 | CL | Agent self-service onboarding | covered |
| listhub-iz1 | P1 | CL | Add Milkdown WYSIWYG editor | convention to inherit |
| listhub-rmb | P1 | OP | Migrate to Noos centralized auth | covered |
| listhub-g6t | P1 | CL | Community directory shared git repo | covered by /explore |
| listhub-94f | P2 | OP | Cmd+K quick switcher | covered |
| listhub-u02 | P2 | OP | User account rename | covered |
| listhub-a2o | P2 | OP | Wikis as first-class objects | covered |
| listhub-a3e | P2 | OP | **Download user git repo as ZIP** | **GAP v1** |
| listhub-c6x | P2 | OP | **Inline image support** | **GAP v1** |
| listhub-n5g | P2 | OP | **Better error messages for permission walls** | **GAP v1** |
| listhub-2zv | P3 | OP | **File bucket / binary storage architecture** | **GAP v1 (decision needed)** |
| listhub-xrx | P3 | OP | **file_path move API** | **GAP v1** |
| listhub-l91 | P2 | OP | **Tags as first-class feature** | **GAP v1 refinement** |
| listhub-3wv | P3 | OP | **Search-or-create fallback** | **GAP v1 refinement** |
| listhub-ary | P3 | OP | **External links in new tab** | **GAP v1 refinement** |
| listhub-9nm | P2 | OP | **Visibility label consistency** | **GAP v1 refinement** |
| listhub-1c7 | P2 | OP | **Visibility controls at top of page** | **GAP v1 UX** |
| listhub-3cm | P2 | OP | **Inline permissions on item view** | **GAP v1 UX** |
| listhub-an8 | P2 | OP | **Visibility badges on items** | **GAP v1 UX** |
| listhub-2lg | P2 | OP | Git history viewer | GAP v1.5 |
| listhub-j47 | P3 | OP | Public git repo directory at /git/ | GAP v1.5 |
| listhub-67v | P3 | OP | Bulk folder drag-in | GAP v1.5 |
| listhub-r62.1 | P2 | OP | Unified metadata YAML pattern | partially covered (.wikihub/acl supersedes) |
| listhub-74j | P2 | OP | Folder-level visibility with cascade | covered via globs |
| listhub-t41 | P2 | OP | Implement WebMCP | covered |
| listhub-f18 | P2 | OP | Public/private split + per-line visibility | covered via `<!-- private -->` |
| listhub-erm | P2 | IP | Unlisted visibility | covered |
| listhub-z0t | P2 | CL | Publicly editable | covered |
| listhub-8wi | P2 | OP | Per-user sharing with write permission | covered |
| listhub-zyc | P2 | OP | Comments or suggested additions | suggested edits v1, comments v2 |
| listhub-xtc | P2 | OP | GitHub-like repo UX (epic) | aligned |
| listhub-xtc.1 | P2 | OP | Anonymous unauthenticated editing UX | covered |
| listhub-2zb | P2 | OP | Auto-push to GitHub + encrypted items | v2 + v3 (git-crypt) |
| listhub-cuq | P3 | OP | Real-time collaborative editing | v2+ (deferred) |
| listhub-d03 | P3 | OP | Graph database for relationships | v3 (deferred) |
| listhub-dwa | P3 | OP | .docx/.doc/.rtf → markdown | v2 (omni-convert) |
| listhub-7c5 | P3 | OP | Google Drive connector | v2 |
| listhub-4jm | P3 | OP | Multi-sheet CSV/spreadsheet | defer indefinitely |
| listhub-4m2 | P2 | OP | Python/JS client library | partially covered by MCP |
| listhub-lwh | P3 | OP | Sub-wiki / legacy Google Sites hosting | covered by generic import |
| listhub-obd | P3 | OP | Username auto-suggestion endpoint | GAP v1.5 (small) |
| listhub-sxu | P2 | OP | Save/favorite lists | covered by star |

---

## Sources

- `git log --all --oneline` in `/Users/hq/github_projects/listhub` (162 commits)
- `/Users/hq/github_projects/listhub/.beads/issues.jsonl` (90 tickets)
- `/Users/hq/github_projects/listhub/.beads/README.md` (beads project reference)
- [github.com/steveyegge/beads](https://github.com/steveyegge/beads) — beads project
- [Steve Yegge — Introducing Beads](https://steve-yegge.medium.com/introducing-beads-a-coding-agent-memory-system-637d7d92514a)
- [Steve Yegge — Beads Best Practices](https://steve-yegge.medium.com/beads-best-practices-2db636b9760c)
- [Beads — A Git-Friendly Issue Tracker](https://betterstack.com/community/guides/ai/beads-issue-tracker-ai-agents/)

---

*End of mining report. This document is a research artifact for the wikihub spec; findings should be folded into the main spec docs selectively, not wholesale.*
