# wikihub spec — branch 2 conversation log

**Session:** branch `c3b72e99` forked from `bed5f0f2` at 2026-04-09 01:04 UTC
**Participants:** Jacob (user) + Claude (Opus 4.6, 1M context)
**Mode:** spec discussion only — no implementation code written
**Purpose:** exports the progression of topics, positions, user responses, and locked decisions from this branch session

---

## 1. Pack filtering — what it is and why we rejected it

**Context:** before the fork, the parent session had proposed three options for how non-owners clone a wiki with private files. One option was "custom pack filtering per request." User asked what that means.

**Claude explained:** git clone works by the server building a "packfile" — a compressed bundle of all objects (commits, trees, blobs) the client needs, streamed in one round-trip. "Pack filtering" would mean dynamically rewriting this bundle per request, removing private blobs and rewriting every tree/commit hash that references them. This is theoretically possible with libgit2 but:
- Trees reference blobs by SHA; removing a blob breaks the tree, which breaks the commit, which rewrites the entire history per viewer
- Git's partial clone (`--filter=blob:none`) defers but doesn't hide — the client still knows blobs exist
- No production system (GitHub, GitLab, Bitbucket, Gitea) does per-blob per-viewer filtering
- Classified it as "a research project dressed as a feature" and vetoed it for v1

**User response:** "Couldn't we generate a limited version of the repo that excludes the private files if you are not the owner, so it would only show the public files you have access to? Why do we need to do some fancy?"

**Claude's reaction:** user's reframe is correct and cleaner. The key insight: **precompute the filtered view at write time, not at read time.** This is the cache-it-don't-compute-it pattern. Two repos per wiki: authoritative (owner only, all files) and public mirror (derived, regenerated on every push, only public files). Flask dispatches clone requests by auth — owner gets authoritative, everyone else gets the mirror. Both are stock git repos served by stock `git-http-backend`. No custom pack logic.

**Locked:** two-repo public mirror architecture. Two separate bare repos (not two refs in one repo) for auditability. Public mirror has linearized history (rolling force-update). Private pages never enter git at all (live in Postgres only).

---

## 2. Postgres confirmed (not SQLite)

**Context:** parent session had drifted toward SQLite on scope-cut grounds. User corrected this.

**User response:** "We decided to go with Postgres."

**Locked:** Postgres as the derived index store. Reasons: concurrent writes on shared tables (stars, forks, ACL grants), `jsonb` for frontmatter, `tsvector` for cross-wiki search, room for row-level security later.

*Note: a separate Branch 1 session on 2026-04-09 later re-questioned this and argued for SQLite v1. As of this branch session, Postgres was explicitly confirmed by the user.*

---

## 3. ACL storage design — `.wikihub/acl` with CODEOWNERS pattern

**Context:** user asked about git-friendly access control. Specifically asked about several options: per-file YAML sidecars, frontmatter, matching the Claude/local-memory folder convention, an index file.

**Claude walked through five options:**

| Option | Verdict |
|---|---|
| Per-file YAML sidecar (`page.md` + `page.md.acl.yaml`) | Rejected — doubles tree entries, orphan risk, rename drift |
| Frontmatter only (`visibility: public` in YAML header) | Rejected as sole mechanism — markdown-only, can't handle PDFs/images/binary files |
| Match Claude memory folder (`.claude/` convention) | Useful for the dotfolder NAME (`.wikihub/`) but doesn't answer what goes inside it |
| Flat enumeration index (one file listing every path) | Rejected — merge conflicts, doesn't scale, no glob patterns |
| **CODEOWNERS-style single file with glob patterns** | **Selected** — git-native, diffable, blameable, file-type agnostic, private-by-default is one line (`* private`), scales tiny-to-huge, safe failure modes |

**User response:** accepted the CODEOWNERS pattern. Asked follow-up questions (covered in sections 4-5 below).

**Locked:** `.wikihub/acl` as the ACL storage mechanism. Git-tracked in the authoritative repo. Glob rules, most-specific wins. Self-documenting header comment block in the scaffolded file so LLMs can parse it cold without a skill. `.wikihub/` as the platform dotfolder, peer to `.git/`, `.github/`, `.claude/`.

**Agents understand it through three layers** (no skill needed):
1. MCP tools — `set_visibility(path, visibility)` and `share(path, principal, role)` handle it programmatically
2. AGENTS.md — site-root prose explaining the format
3. In-file header comment — the scaffolded `.wikihub/acl` includes a format spec + examples in the comments

---

## 4. Frontmatter and the ACL file — specificity, not redundancy

**User question:** "Is there a benefit to redundantly adding front matter on the files or something like that? The front matter could be the more definitive source of truth if it exists."

**Claude reconsidered** earlier framing of frontmatter as "just a hint." Realized frontmatter and ACL file operate at different *scopes*:
- `.wikihub/acl` handles **bulk patterns** ("everything in `wiki/` is public")
- Frontmatter handles **single-file exceptions** ("this one page is different from its folder's default")

Proposed a specificity ladder (same resolution model as CSS specificity or `git config` precedence):
1. Frontmatter on the file itself (most specific, wins for that file)
2. ACL file rule matching the path, most-specific pattern first
3. Repo default (`* private`, implicit)

**User response:** accepted. No further questions on this point.

**Locked:** both frontmatter and ACL file are authoritative for their scope. Frontmatter overrides globs for individual files. No two-sources-of-truth problem because they operate at different granularities.

---

## 5. Obsidian frontmatter compatibility

**User question:** "Would our front matter conflict with Obsidian front matter format?"

**Claude analyzed** Obsidian's reserved frontmatter keys (`tags`, `aliases`, `cssclass`/`cssclasses`, `publish`, `permalink`, `description`, `image`, `cover`) and found:
- **Zero hard conflicts.** wikihub's keys (`visibility`, `share`) don't collide with any Obsidian reserved key.
- **One soft overlap:** Obsidian Publish uses `publish: true/false`. Wikihub uses `visibility: public/private`. These are semantically similar but use different key names.

**Proposed:** read `publish: true/false` as an alias for `visibility: public/private` (with `visibility:` winning on conflict). This gives Obsidian Publish migrants a zero-rewrite migration: just point their vault at wikihub and push.

**Also proposed honoring** on read: `aliases` (for wikilink resolution), `permalink` (URL slug), `description` (OG tags / llms.txt excerpts), `tags` (accept both list and flow syntax), `cssclass`/`cssclasses` (apply to rendered `<article>`). On write: only touch `visibility:` and `share:`, never clobber keys we don't own.

**Design principle:** "Read liberally, write conservatively" — Postel's Law applied to config files.

**User response:** accepted. The migration story ("point your Obsidian vault at wikihub as a git remote and push") was well-received.

**Locked:** full Obsidian frontmatter compatibility as described above.

---

## 6. Permission model — the different edit permissions

**User question:** "What about the different edit permissions like public read-only, public edit, unlisted, etc."

**Claude proposed** decomposing every permission state into three orthogonal axes:
1. Read audience (owner | grantees | link-holders | signed-in | anyone)
2. Write audience (same ladder)
3. Discoverable (indexed | hidden)

Named "visibility modes" are just shortcuts for common (read, write, discoverable) triples. Proposed full v1 vocabulary:

| Mode | Read | Write | Discoverable |
|---|---|---|---|
| `private` | owner | owner | no |
| `public` | anyone | owner | yes |
| `public-edit` | anyone | anyone | yes |
| `unlisted` | URL holders | owner | no |
| `unlisted-edit` | URL holders | anyone with URL | no |
| `signed-in` | any signed-in | owner | yes |
| `link-share` | token holders | owner | no |
| `shared` | per grants | per grants | no |

Grant syntax in the ACL file: `@user:role`, `group:name:role`, `link:token:role`. Roles: `read | comment | edit | admin`. `comment` role exists in vocab from day one, behaves as `read` until comments ship in v2.

**User response:** accepted the full model. Proceeded to the anonymous-writes question.

**Locked:** 3-axis permission model, full mode vocabulary, grant syntax, role vocabulary, principal abstraction with `user | group | link_token | anyone | org` types.

---

## 7. Anonymous writes — Google Docs link-edit model

**User instruction:** "Let's do: anyone anonymously can edit just like the Google Docs link edit for now."

**Claude asked:** does this apply to `public-edit` (indexed, discoverable) too, or only `unlisted-edit` (link-based)?

**User response:** "Both modes allow anonymous writes (maximum permissive)."

**Claude then drafted** a full anti-abuse plan: polymorphic actor column, per-IP/per-token/per-wiki layered rate limits, honeypot form field, body/link caps, revert-to-last-known-good as critical feature, owner panic button, auto-under-attack mode, owner notifications, quarantine queue, proof-of-work reactive throttling, and CAPTCHA escape hatch. Also proposed commit authors as `anonymous <anon@wikihub>` for the git-plumbing requirement.

**Locked:** both `public-edit` and `unlisted-edit` allow fully anonymous writes. No sign-in, no email, no account.

---

## 8. Security strip — ALL moderation deferred to v2/v3

**User instruction:** "Let's put all the security features into v2 and v3. For now v1 should not have any of this."

**Claude's earlier response** had proposed a full anti-vandalism stack. User explicitly cut ALL of it from v1.

**OUT of v1 (deferred to v2/v3):**
- Per-IP/per-token/per-wiki write rate limits
- Honeypot form field
- Actor logging beyond basic nullable author field
- Moderation view
- Bulk revert tooling
- Panic button
- Auto-under-attack mode
- Owner notifications
- Quarantine queue
- Proof-of-work
- Body/link size caps
- CAPTCHA
- "Are you sure?" warnings on public-edit
- Default-off for public-edit on new wikis
- `crawl: false` per-wiki opt-out

**IN for v1 (basic plumbing only):**
- Anonymous git commits use `anonymous <anon@wikihub>` as author (git requires this)
- Pages table has a nullable author field
- Basic signup rate limit per IP (infra, not moderation — confirm status is open)

**Philosophy locked:** "trust mode, ship it, iterate when problems happen."

---

## 9. Handoff doc creation + side-session summary request

**User instruction:** "Also at this stage we really want to formalizing the spec; we don't want to be implementing." Then later: "How we can summarize everything we've concluded so I can tell it back before the fork."

**Claude wrote** a comprehensive handoff document (`wikihub-spec-state-from-side-session-2026-04-08.md`) covering all locked decisions from both the parent session and this branch. Also wrote a more limited delta doc (`wikihub-post-fork-delta-2026-04-08.md`) covering only what this branch decided since the fork point.

**User instruction:** "SAVE THIS TO AN MD FILE AND SAY IT'S FROM THE SIDE SESSION IN THE TITLE."

Both files were saved to `research/wikihub-spec-work-2026-04-08/`.

---

## 10. Boris drift correction

**User question:** "Where did we get the idea that Boris and technical readers are the first users?"

**Claude traced the source:** one bullet in a Granola meeting transcript (Tue, 07 Apr 26) said "Primary goal: get Boris and team at Anthropic using LM wiki. They need markdown reader." Claude acknowledged amplifying this from "partnership target" to "first-user design persona" to "reader UI quality bar" across successive spec turns. The drift was unwarranted.

**User response:** "YES" (fix it).

**Locked:**
- First users (v1) = dogfood migrations + Karpathy-wave adopters + Obsidian vault owners
- Boris/Anthropic = distribution goal (partnership outreach), not a design persona
- Anthropic intranet = future target (companies), not a v1 concern
- Reader quality bar justified by "Karpathy-wave audience expects real ML rendering," not by any individual

---

## 11. Beads / Yegge model research

**User instruction:** "Research how beads works re Yegge model."

**Claude found:** beads = Steve Yegge's git-friendly issue tracker, already installed in listhub's `.beads/` directory. The `bd sync` commits in listhub's git log are beads flushing SQLite→JSONL.

**Architecture:** SQLite in WAL mode as operational store, `.beads/issues.jsonl` as git-tracked export, git hooks (pre-commit, post-checkout, post-merge, pre-push, prepare-commit-msg) as sync glue, optional daemon for RPC.

**Key inversion vs. wikihub:** beads has SQLite authoritative + JSONL derived. Wikihub has git authoritative + Postgres derived. Opposite directions, deliberate (beads optimizes for agent queries over structured fields; wikihub optimizes for users cloning/editing markdown).

**Resolved:** the "Yegge model for SQLite+git" open fork from prior-session memory. It was beads all along.

---

## 12. Listhub requirements mining — git log + beads tickets

**User instruction:** "Can you go through the entire git commit history on listhub and figure out if there are any implied specs or requirements we aren't covering now or in the future. Also look at the beads ticket history in the repo."

**Claude analyzed:** 162 commits + 90 beads tickets. Found ~55 aligned (already in spec), ~15 listhub-specific (don't port), ~20 genuine gaps.

**Findings written up** in `wikihub-listhub-requirements-mining-unreviewed-2026-04-08.md`.

---

## 13. User review of mining findings

**User provided comments on the unreviewed mining doc.** Key decisions:

**Agreed with all v1 additions from the "should be added before implementation" section.**

**On binary files (gap #1):** "In the other project we concluded Obsidian just includes images, attachments, binary files right in the repository. Not worried about giant binaries for v1. External S3 bucket (globalbr.ai already has one) is a future option."
→ **Locked:** binary files in-repo, no quota v1, globalbr.ai S3 for v2+.

**On `.folder.yaml` metadata defaults (gap #15):** "Not that important actually but one thing I want to consider is being able to put an index file in a folder like Quartz wiki does."
→ **Dropped:** folder metadata defaults. **Added:** Quartz-style folder index files (`index.md` in subfolders renders as folder landing page).

**On Milkdown editor (convention #24):** "Let's chat about this."
→ **Kept as open question.** Claude provided a comparison table. Leaned toward simpler editor for v1 given the new mobile-first requirement (WYSIWYG on mobile is historically fragile), but deferred to user.

**New requirements surfaced during review:**

**"Let's build with mobile friendly in mind."**
→ **Locked:** mobile-friendly v1 as top-level non-functional requirement. Mobile-first CSS, 44×44 touch targets, hamburger sidebar, full-screen Cmd+K on mobile, 16px minimum body text.

**"Make a mockup first."**
→ **Locked:** mockup-first workflow. `mockups/` directory from day one. Standalone HTML mockups for every significant UI surface before implementation code is written. Pattern ported from listhub's `mockups/` workflow.

**Reviewed mining doc** written to `wikihub-listhub-requirements-mining-reviewed-2026-04-08.md`.

---

## 14. Audit pass and bug fixes

Claude did a comprehensive review of all three spec files (handoff doc, delta doc, memory file) and found 8 issues:

1. **Memory: Postgres vs SQLite contradiction** — header said Postgres, bullets said SQLite. Fixed.
2. **Memory: stale ACL vocabulary** — missing new modes. Fixed.
3. **Memory: stale open-forks list** — SQLite still listed as open. Fixed.
4. **Memory: stale v2 ticket** — Cmd+K still in v2. Promoted to v1. Fixed.
5. **Memory: missing branch decisions** — no mention of public mirror, `.wikihub/acl`, frontmatter specificity, Obsidian compat, 3-axis permission model. Added.
6. **Handoff: fork visibility default** — said "resets to caller's default (public)" which contradicts `* private` invariant. Fixed to default to private.
7. **Handoff: cherry-pick fires hook claim** — said "fires post-receive naturally" via plumbing. False — `update-ref` doesn't fire hooks. Fixed to "directly calls the sync path."
8. **Delta: missing Cmd+K promotion** — added as section 10.

User confirmed all fixes with "YES."

---

## 15. Session file reorganization

User moved all wikihub spec files from `research/` root into a new subdirectory `research/wikihub-spec-work-2026-04-08/`. Also saved the JSONL conversation logs from all four sessions (trunk + three forks) into the same directory.

Claude adapted by re-verifying edit paths and re-applying the delta doc edits at the new location.

---

## Open questions at end of this session

1. **Milkdown vs. simpler markdown editor** — flagged for discussion, not locked.
2. **Quartz — fork, style-reference, or ignore?** — Claude's proceed-unless-vetoed: use as style reference, don't fork. Not explicitly confirmed.
3. **Deployment domain and host** — wikihub.globalbr.ai? Cohabit with listhub? New instance? Not asked.
4. **Auth providers beyond Noos** — Google / GitHub OAuth? Not asked.
5. **Does signup rate-limit-per-IP survive the security strip?** — classification is ambiguous.
6. **Featured curation mechanism** — who picks featured wikis on `/explore`?
7. **Concurrent-edit resolution posture** — last-write-wins, git-merge, optimistic-lock?
8. **SQLite vs Postgres tension** — Postgres was locked in this session. A parallel Branch 1 session re-questioned it. User needs to explicitly re-confirm.
9. **Public content in DB or git-only** — Branch 1 proposed dual-storage model (public content in git only, private in Postgres only). User seemed aligned but didn't explicitly lock.

---

## Files created or modified during this session

| File | Status |
|---|---|
| `research/wikihub-spec-work-2026-04-08/wikihub-spec-state-from-side-session-2026-04-08.md` | Created + updated multiple times (handoff doc) |
| `research/wikihub-spec-work-2026-04-08/wikihub-post-fork-delta-2026-04-08.md` | Created + updated (delta doc) |
| `research/wikihub-spec-work-2026-04-08/wikihub-listhub-requirements-mining-unreviewed-2026-04-08.md` | Created (raw mining research) |
| `research/wikihub-spec-work-2026-04-08/wikihub-listhub-requirements-mining-reviewed-2026-04-08.md` | Created (reviewed decisions) |
| `research/wikihub-spec-work-2026-04-08/agent-first-web-brief-2026-04.md` | Created by subagent (agent-first web standards research) |
| `~/.claude/projects/.../memory/project_wikihub.md` | Updated multiple times (persistent memory) |
| `~/.claude/projects/.../memory/feedback_time_estimates.md` | Created (standing instruction: don't estimate in weeks/months) |
| `~/.claude/projects/.../memory/MEMORY.md` | Updated (index entry for feedback file) |

---

*End of conversation log. This is a research/archival artifact capturing what happened in this branch session. For the spec itself, see the handoff doc and delta doc in the same directory.*
