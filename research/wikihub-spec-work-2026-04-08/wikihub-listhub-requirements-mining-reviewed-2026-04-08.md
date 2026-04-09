# wikihub — requirements mining from listhub (REVIEWED)

> **Status:** REVIEWED. This is the reviewed version of the requirements mining pass, with user decisions locked in. The raw unreviewed research is in `wikihub-listhub-requirements-mining-unreviewed-2026-04-08.md` — consult it for the full inventory of ~55 aligned tickets, the theme analysis, and the "things I looked for and did not find" section, which are unchanged and not restated here.

**Date:** 2026-04-08
**Scope:** Captures which findings from the unreviewed mining doc are now locked into v1 scope, which were redirected or dropped, and which remain open for discussion.

---

## What was reviewed

The unreviewed doc identified ~20 genuine gaps between the wikihub spec and listhub's implied requirements (as expressed in 162 commits + 90 beads tickets). The user reviewed that list and made the following decisions:

- **All 5 "v1 should be added before implementation" items: accepted and locked.**
- **All 4 "v1 refinements" items: accepted and locked.**
- **Binary file storage (gap #1): resolved** — in-repo, no quota in v1, globalbr.ai S3 as future escape hatch.
- **`.folder.yaml` per-folder metadata defaults (gap #15): dropped** — not important. **Replaced** with Quartz-style folder index files (`index.md` in subfolders renders as the folder landing page).
- **Visibility labels + badges (gaps #20, #21): accepted and locked.**
- **Cascade-by-default-at-creation (theme E): locked as a UX rule.**
- **Milkdown editor (convention #24): OPEN** — user wants to discuss before deciding.
- **Two new requirements surfaced during review:** mobile-friendly-v1, and mockup-first workflow.

---

## Locked for v1 — add these to the spec

### The five primary additions

**1. Binary file storage architecture — RESOLVED.**

Decision (2026-04-08 review):
- **v1 default: binaries live in the git repo alongside markdown**, the same way Obsidian treats attachments. Small images, inline PDFs, diagrams, etc. get committed as normal git blobs. The "everything in one repo" story stays intact.
- **No quota in v1.** User explicitly said "not worried about giant binary files for v1." Ship naked, trust users, add caps reactively if storage abuse shows up. Consistent with the broader v1 philosophy of no anti-abuse machinery.
- **Future escape hatch: globalbr.ai has an existing S3 bucket** that can serve as the external object store when a wiki outgrows the in-repo approach. This is v2+ work — no integration needed now, just reserve the design space. Likely mechanism: markdown links to `s3://globalbr-wikihub/...` URLs get rewritten server-side to signed HTTPS URLs, and the upload flow can opt certain files out of git.
- **Git LFS: not used in v1.** Adds client-side friction (users need git-lfs installed) for no win the in-repo approach doesn't already provide.

Implication for the spec:
- Drop the "open question" framing — this is now resolved.
- Add a single sentence to the "Ingestion (v1)" and "Page REST API" sections: "Binary files (images, PDFs, attachments) are stored in the wiki's bare git repo as normal blobs, no quotas."
- Reserve a line in the v2 list: "External object store integration via globalbr.ai S3 bucket when a wiki outgrows in-repo binaries."

**2. Inline image support — LOCKED.**

- Renderer must handle standard markdown images (`![alt](path.png)`) and **Obsidian embed syntax** (`![[image.png]]`).
- Implementation: add `markdown-it-image-figures` (or equivalent) plus a small custom plugin for the `![[...]]` syntax that rewrites to `<img>` tags.
- Image paths resolve relative to the page they're embedded in, same as wikilinks.
- On the renderer: support width specifiers Obsidian-style (`![[image.png|300]]` → 300px width).
- Covered files: png, jpg, jpeg, gif, webp, svg, avif.
- PDFs inline via `<object>` or link-to-download — decision deferrable.

Add to the renderer stack definition in the spec: "markdown-it + markdown-it-footnote + markdown-it-katex + highlight.js + markdown-it-image-figures + custom wikilink plugin + custom Obsidian-embed plugin."

**3. File rename / move REST endpoint — LOCKED.**

- Endpoint: `PATCH /api/v1/wikis/:owner/:slug/pages/*path` with body `{new_path: "..."}`.
- Server performs the equivalent of `git mv` via plumbing: read the blob at the old path, add it at the new path, remove it from the old path, write the new tree, commit with message `Rename <old> → <new>`.
- **Wikilink rewriting in the same commit:** scan all pages for `[[old-title]]` / `[[old/path]]` references and rewrite them to the new path before committing. Atomic — one commit for both the rename and the link updates.
- Git's rename detection handles blame and history continuity for the renamed file.
- MCP tool: add `move_page(old_path, new_path)` to the server-hosted MCP surface.

**4. Machine-readable permission error bodies — LOCKED.**

Convention for all 403 responses from the REST API:

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
      "endpoint": "/api/v1/wikis/:owner/:slug/fork",
      "method": "POST"
    },
    {
      "verb": "request_access",
      "description": "Ask the owner for edit access",
      "endpoint": "/api/v1/wikis/:owner/:slug/access-requests",
      "method": "POST"
    }
  ]
}
```

- Every 403/401 returns this shape.
- Agents can parse `suggested_actions` and offer the user a menu.
- Add a section to the spec: "Error response conventions."

**5. ZIP download of wiki — LOCKED.**

- Endpoint: `GET /@alice/wiki.zip` (mirrors `/@alice/wiki.git` in structure).
- Flask dispatches based on auth: owner gets a zip of the authoritative repo's working tree; non-owners get a zip of the public mirror's working tree.
- Implementation: server runs `git archive --format=zip HEAD` on whichever repo the dispatch routes to.
- Streaming response — works even for large wikis without loading into memory.
- **Tiny endpoint, large UX win.** Matches the authoritative-vs-public-mirror architecture perfectly.
- Add to the v1 API section and mention in the spec's ingestion section.

### The four refinements

**6. Tag index pages — LOCKED.**
- `/@user/wiki/tag/:name` renders a list of every page in the wiki with that tag.
- Tag filters available in Cmd+K (`tag:research` prefix).
- Tag counts shown on the wiki's landing page.
- Tags come from frontmatter's `tags:` field (Obsidian-compatible).

**7. Search-or-create in Cmd+K — LOCKED.**
- When cross-wiki search returns zero hits, Cmd+K offers "Create `<query>`" as the first action.
- Creates a new page in the currently-focused wiki with the query as the title, drops the user into the editor.
- Matches Obsidian and Notion expectations exactly.

**8. External links open in new tab — LOCKED.**
- markdown-it config: add `target="_blank" rel="noopener noreferrer"` to all external anchors.
- Internal wikilinks stay in the current tab.
- One-liner in the renderer setup.

**9. Visibility labels as `public (read)` / `public (edit)` etc. — LOCKED.**
- Internal mode names stay short (`public`, `public-edit`, `unlisted`, `unlisted-edit`).
- User-facing labels in the web UI use the longer disambiguated forms: `public (read)`, `public (edit)`, `unlisted (read)`, `unlisted (edit)`.
- ACL file also accepts the short forms as the canonical on-disk names.
- Spec addition: a table mapping internal modes → UI labels for consistency across templates.

**10. Visibility badges everywhere — LOCKED.**
- Every page/wiki card, search result, explore entry, profile item, and sidebar entry shows a small visibility icon.
- Icons: lock (private), globe (public), eye (unlisted), pencil-in-circle (public-edit / unlisted-edit), lock-with-check (signed-in), share-arrow (shared).
- Badge is clickable and opens the visibility panel for the item (if the user has admin).
- Add to the spec as an explicit UX requirement for every surface that renders an item.

### The two replacements

**11. Folder index files (Quartz-style) — LOCKED, replaces the dropped `.folder.yaml` idea.**

- Any sub-folder within a wiki can contain an `index.md` (or `README.md` as a fallback convention).
- When browsing to `/@user/wiki/folder/`, the renderer looks for `folder/index.md` first and renders it as the folder's landing page.
- If no `index.md` exists, an auto-generated file listing is rendered (GitHub-style).
- This extends the existing convention (wiki root already has `index.md` per Karpathy's scaffold) into arbitrary subfolders.
- No extra file format, no new metadata — just "markdown files can act as folder landings."
- Cascading applies: `folder/index.md` inherits visibility from the folder's ACL glob unless its own frontmatter overrides.
- This was called out as the thing from Quartz the user specifically wanted to preserve.

What this replaces (dropped): the `.folder.yaml` / `.wikihub/defaults.yaml` idea for per-folder metadata defaults. The user deemed it not important. Folder index files are the thing they wanted instead.

### Two new requirements surfaced during review

**12. Mobile-friendly v1 — LOCKED.**

New requirement from the review. Wikihub v1 must be mobile-responsive from day one, not "polish it up later."

Implications:
- **Server-rendered Jinja is fine** (it's how listhub works and listhub is mobile-usable). No SPA needed.
- **CSS must use a mobile-first approach**: design for narrow viewport, widen breakpoints up to desktop. `@media (min-width: ...)` rather than `(max-width: ...)`.
- **Touch targets**: all interactive elements ≥44×44px (iOS guideline).
- **Sidebar**: collapses to a hamburger menu on narrow viewports. The three-section pattern from listhub needs to work in a drawer.
- **Cmd+K**: keyboard shortcut on desktop, tap-to-open on mobile. The search modal must be full-screen on mobile.
- **Editor**: Milkdown-or-whatever editor must work on mobile (virtual keyboard friendly, no hover-dependent UI).
- **Tables and code blocks**: horizontal-scroll overflow handling, not clipping.
- **Images**: responsive, max-width 100%.
- **Font sizes**: minimum 16px body text to avoid iOS zoom-on-focus.

Add to the spec as a top-level non-functional requirement: "wikihub is mobile-responsive from v1. Every page works on a 375px-wide viewport."

**13. Mockup-first workflow — LOCKED.**

New process rule from the review. Before writing implementation code for any significant UI surface, we make an HTML mockup first — same pattern listhub uses (`mockups/` directory with static HTML files).

Implications:
- Wikihub gets a `mockups/` directory from day one.
- Each mockup is a standalone HTML file with inline CSS/JS, no backend dependencies.
- Mockups cover at minimum: landing page, `/@user` profile, wiki reader view, wiki edit view, Cmd+K search, `/explore`, folder view, visibility panel, permissions error page, mobile versions of all of the above.
- Mockups get reviewed before coding begins on each surface.
- The mockup process applies retroactively to this spec: **we should produce a first mockup before starting implementation**, not after.

This is a workflow decision, not a spec decision, but it shapes how the spec gets turned into code. Document it in the project's AGENTS.md file when the repo is scaffolded.

---

## Still open after review

**14. Milkdown editor — NEEDS DISCUSSION.**

User flagged this as "lets chat about this." The tension:
- **Pro Milkdown**: WYSIWYG editing with round-trip-clean markdown, plugin architecture, proven from listhub's use, strategic code reuse.
- **Pro simpler (markdown textarea + wikilink autocomplete)**: smaller bundle, simpler to debug, no dependency on Milkdown's plugin ecosystem, avoids the "our editor choice is locked to Milkdown's evolution" risk.

Decision deferred to the next session. Flagged as an open fork in the spec.

---

## Dropped during review

**15. Per-folder metadata defaults via `.folder.yaml` / `.wikihub/defaults.yaml`.**

User said "not that important actually." Replaced by folder index files (item #11 above). The ACL glob pattern already handles folder-scoped access control; folder-scoped non-ACL metadata defaults are not a real need for v1 or beyond.

---

## Summary of what changes in the spec docs

If someone were to apply the locked decisions from this review to the handoff doc and delta doc, the changes would be:

1. Resolve "binary file storage" as a **locked decision**, not an open question. In-repo, no quota v1, globalbr.ai S3 future.
2. Add inline image rendering (standard + Obsidian embed) to the renderer stack line.
3. Add file rename/move endpoint to the API surface list.
4. Add the permission error body convention to a new "Error responses" section.
5. Add ZIP download endpoint to the social / API section.
6. Add tag index pages to the search / discovery section.
7. Add search-or-create to the Cmd+K bullet.
8. Add external-links-new-tab to the renderer config.
9. Add the mode-name → UI-label table for visibility labels.
10. Add visibility badges as an explicit UX requirement on every item-rendering surface.
11. Add folder index files (Quartz-style `index.md` in subfolders) to the renderer behavior.
12. Add **mobile-friendly v1** as a top-level non-functional requirement.
13. Add **mockup-first workflow** as a process rule, with a mockups/ directory.
14. Leave Milkdown as an open question.
15. Remove / never-add the `.folder.yaml` metadata defaults idea.

The unreviewed mining doc remains the authoritative full inventory of *why* these items came up. This reviewed doc is the authoritative source for *what was locked*.

---

## Traceability back to source tickets

For each locked item, the originating listhub beads ticket(s):

| Locked item | Source ticket(s) |
|---|---|
| Binary file storage | `listhub-2zv` |
| Inline image support | `listhub-c6x` |
| File rename/move endpoint | `listhub-xrx` |
| Permission error bodies | `listhub-n5g` |
| ZIP download | `listhub-a3e`, `listhub-ev1` |
| Tag index pages | `listhub-l91` |
| Search-or-create in Cmd+K | `listhub-3wv` |
| External links new tab | `listhub-ary` |
| Visibility label consistency | `listhub-9nm` |
| Visibility badges everywhere | `listhub-an8`, `listhub-1c7`, `listhub-3cm` |
| Folder index files (Quartz-style) | user instruction during review; adjacent to `listhub-wn4` (folder view) |
| Mobile-friendly v1 | user instruction during review (no prior ticket) |
| Mockup-first workflow | pattern from listhub's `mockups/` dir; user instruction during review |
| Milkdown editor (open) | commit `7569f04`, ticket `listhub-iz1` (closed) |
| Dropped: folder metadata defaults | `listhub-r62.1` (per-folder YAML) |

---

*End of reviewed mining report. This is the decision record for the review pass; the unreviewed doc is the research record.*
