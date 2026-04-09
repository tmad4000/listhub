# wikihub spec work — 2026-04-08

A single day's worth of collaborative spec-phase research and design work on **wikihub**, a from-scratch "GitHub for LLM wikis" product being designed as a sibling to listhub. This folder collects the raw conversation logs from three parallel forks of the same seed conversation, plus the research output documents that came out of them.

No code was written during this work — it is entirely spec phase.

## Fork topology — three main sessions, all children of one trunk

The work happened across **one trunk session and three forks**. All three forks branched directly from the trunk; they are siblings of each other, not a chain. Two of the forks (B and C) ran concurrently in the final few hours.

```
bed5f0f2  ─── TRUNK (2026-04-08 18:04 PDT, 35 user msgs, 450 KB)
    │         Seed conversation. Started with "Look at Karpathy's LLM wiki..."
    │         Ended at "ok here are more thoughts on the progression..."
    │         Ran during the initial framing pass.
    │
    ├── e911cdb2  FORK A  (2026-04-08 17:57 PDT, 31 user msgs, 335 KB)
    │             Earlier exploration branch. Raised the "Yegge model" question
    │             about SQLite + git that surfaced the beads reference.
    │             Ended on: "How does the Postgres compare with Steve Yegge's model?"
    │
    ├── 3a9f8f96  FORK B  (2026-04-08 20:37 PDT, 98 user msgs, 1.5 MB)
    │             Concurrent heavy-work branch. Sibling of fork C, ran
    │             at the same time. Produced the requirements-mining docs
    │             comparing wikihub spec to listhub's git history and beads
    │             tickets.
    │             Ended on: "save this all in a new md file"
    │
    └── c3b72e99  FORK C  (2026-04-08 20:37 PDT, 98 user msgs, 1.5 MB)
                  Concurrent with fork B. The session where the CODEOWNERS-
                  pattern ACL file, the two-bare-repos public-mirror
                  architecture, the Postgres-over-SQLite confirmation,
                  Obsidian frontmatter compat, and the anonymous-writes +
                  security-cut decisions landed. Also where the beads /
                  Yegge-model question was fully resolved and where the Boris
                  drift was caught and corrected. This is the session that
                  assembled this folder.
```

All three forks start with the same user message ("Look at Karpathy's LLM wiki..."), which is the seed message from the trunk they each branched from. Each fork then diverged into its own exploration.

## What's in this folder

### Session transcripts (raw JSONL)

- **`00-trunk-bed5f0f2.jsonl`** — the trunk session. Full conversation including tool calls and tool results.
- **`01-fork-a-e911cdb2.jsonl`** — fork A, Yegge-model exploration.
- **`02-fork-b-3a9f8f96.jsonl`** — fork B, heavy-work concurrent branch.
- **`03-fork-c-c3b72e99.jsonl`** — fork C, this branch. The one that produced the final locked decisions and this README.

All four files have been **redacted** for publication: 106 thinking-block cryptographic signatures across the four files were replaced with `[REDACTED]`. These are Anthropic's opaque integrity stamps on extended-thinking content blocks, not secrets in any actionable sense, but obfuscating them silences false-positive hits from secret scanners and is the simple safe thing to do. The *actual* content of thinking blocks is already stripped at the storage layer and was never present in these files — Claude Code persists thinking metadata (type + signature) but not the thinking text itself, so there is no internal reasoning content to leak.

A narrow scan for real credentials (Anthropic keys, OpenAI keys, GitHub PATs, AWS access key IDs, SSH private keys, JWTs, Authorization headers) found nothing in any of the four files. This is expected — the conversation never asked any tool to fetch anything with auth credentials — but the scan is documented here so the next reader doesn't have to re-run it.

### Research documents (markdown)

- **`agent-first-web-brief-2026-04.md`** — authoritative brief on the state of agent-first web standards as of April 2026: WebMCP, llms.txt, `/.well-known/mcp` discovery shapes (SEP-1649 and SEP-1960), agent-native auth patterns, content negotiation via `Accept: text/markdown`, agent identity / delegation, and the loudest voices in the scene. Produced by a research subagent early in fork B / fork C. Serves as the authoritative reference for wikihub's agent surface decisions. Cross-references its siblings in the parent `research/` directory.

- **`wikihub-listhub-requirements-mining-unreviewed-2026-04-08.md`** — raw research pass mining 162 commits and 90 beads tickets from the listhub git history for implied requirements and features the wikihub spec doesn't yet cover. Identifies ~20 genuine gaps, ~55 already-aligned items, and ~15 listhub-specific bits that don't port. Unreviewed / pre-user-decision. Kept as-is for traceability.

- **`wikihub-listhub-requirements-mining-reviewed-2026-04-08.md`** — the reviewed version of the above, with Jacob's decisions locked in (which items are accepted into v1, which are redirected, which dropped). Consult this one first; the unreviewed version is for traceability only.

- **`wikihub-spec-state-from-side-session-2026-04-08.md`** — the full spec handoff document. A standalone summary of every decision locked in the branch sessions, formatted as portable context that can be pasted verbatim into another Claude session to bring it up to speed. Covers name, stack, data architecture, the public-mirror pattern, ACL storage (`.wikihub/acl`), frontmatter-and-ACL precedence, Obsidian compat, permission model, `<!-- private -->` sections, the full anti-abuse-cut decision, the agent surface, and the open questions.

- **`wikihub-post-fork-delta-2026-04-08.md`** — a shorter variant of the same content, structured as a *delta* from the parent trunk session rather than a full spec. Assumes the reader already has pre-fork context and just needs the post-fork decisions. Use this instead of the full handoff when syncing another fork that already knows everything the trunk knew.

### Related research (not in this folder)

The following general-purpose LLM-wiki research docs live in the parent `research/` directory (`../`) and are referenced from the agent-first-web brief and the handoff doc. They pre-existed this day's work and stay where they are:

- `../llm-wiki-research.md` — five-sense taxonomy of "LLM wiki" (personal / AI-generated public / wikis-for-LLMs / wikis-about-LLMs / human+AI collaborative).
- `../llm-wikis-catalog.md` — ~85 concrete LLM wiki instances across the five senses.

## What the session decisions were (one-line summary per decision)

For navigation into the detailed docs:

- **Name:** wikihub. From-scratch new repo, not grafted onto listhub.
- **Stack:** Flask + Postgres + Jinja + bare git, renderer is markdown-it + footnote + katex + highlight.js + wikilink plugin.
- **Data architecture:** bare git repo = source of truth, Postgres = derived index, two-way sync copied from listhub.
- **Per-wiki storage:** two bare repos — authoritative (owner-only) + public mirror (derived, regenerated on push). Flask dispatches clones by auth; stock `git-http-backend` on both.
- **ACL storage:** `.wikihub/acl` CODEOWNERS-pattern file. Glob rules, most-specific wins, private by default, `#` comments. `.wikihub/` is the platform dotfolder peer to `.git/`, `.github/`, `.claude/`.
- **Frontmatter + ACL compose by specificity**, not authority. Frontmatter wins for its file; ACL globs below; repo default `* private` at the bottom. Obsidian frontmatter keys (`publish`, `aliases`, `permalink`, etc.) honored on read for free migration wins.
- **Permission model:** three orthogonal axes (read audience, write audience, discoverable). v1 mode vocabulary: `private | public | public-edit | unlisted | unlisted-edit | signed-in | link-share | shared`. Grant syntax `@user:role`, `group:name:role`, `link:token:role`. Principal abstraction reserves space for future org / multi-tenant.
- **Anonymous writes allowed** on both `public-edit` and `unlisted-edit` modes. Google Docs link-edit model. No account required.
- **Anti-abuse machinery entirely cut from v1.** Ship naked, iterate reactively. All of rate limits, honeypot, moderation view, revert tooling, panic button, under-attack detection, notifications, quarantine, PoW, CAPTCHA, body caps deferred to v2/v3.
- **`<!-- private -->` HTML-comment sections** in v1 as a lightweight sub-file privacy tool, with honest docs framing it as a best-effort convenience rather than a security boundary.
- **Private pages live in Postgres only, never enter git.** Coarse-grained git, fine-grained Postgres.
- **Cmd+K cross-wiki omnisearch in v1** (overrides earlier plans to defer it).
- **First users:** dogfood migrations (admitsphere, RSI wiki, systematic altruism wiki, jacobcole.net/labs, Jacob's CRM) + Karpathy-gist wave + Obsidian vault owners. Boris / Anthropic is a distribution goal, not a design persona — earlier drift caught and corrected. Anthropic intranet is a future target that drives the principal-abstraction choice only.
- **"Yegge model" resolved to beads** (github.com/steveyegge/beads), already installed in listhub's `.beads/` dir. Lessons worth porting into wikihub: `.wikihub/events.jsonl` for git-tracked audit of ACL / visibility / fork mutations; line-oriented formats for anything under `.wikihub/` that might merge-conflict; hash-based IDs (already aligned via nanoid). Wikihub's source-of-truth direction (git) is deliberately opposite to beads's (SQLite) because wikihub's primary content is authored markdown, not structured fields.

See the handoff doc for full detail on each of these.

## Open questions still on the table

- Quartz fork vs. style-reference vs. ignore (my recommendation is "style reference only, don't fork").
- Deployment domain and host (wikihub.globalbr.ai? new Lightsail? cohabit with listhub?).
- Auth providers beyond Noos (Google OAuth? GitHub OAuth?).
- Signup rate limit per IP survival post security-cut (infra vs moderation classification).
- Featured curation mechanism on `/explore`.
- Concurrent-edit posture (last-write-wins vs git-merge vs optimistic-lock).
- Whether to lock `.wikihub/events.jsonl` as a v1 feature or leave it as a v2 ticket, and if v1: scope rule (content-and-permission mutations only, not stars/views/reactions) and privacy rule (event inherits the privacy of the resource it's about).
