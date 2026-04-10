# wikihub user stories brief — 2026-04-09

Research brief on the most compelling user stories for an LLM wiki hosting platform, based on signals from HN, Twitter/X, GitHub READMEs, blog posts, and community discussions in the 6 days since Karpathy's gist dropped (2026-04-03 to 2026-04-09).

---

## Part 1 — Top user stories, ranked by signal strength

Signal strength = how many independent sources surface this need, weighted by whether they come from people who BUILT something (high) vs. people who WROTE about it (medium) vs. people who LIKED a post (low).

### Tier 1 — Strong signal, multiple independent sources

#### 1. "I built an LLM wiki and I want a URL to share it"

**Signal strength: STRONGEST.** This is the single most obvious unmet need in the ecosystem.

Every implementation (20+ GitHub repos, 12+ blog posts) produces a local folder of markdown files. NONE of them include a publishing step. The publishing gap is mentioned explicitly in the catalog research (`research/llm-wikis-catalog.md`): "no popular product exists for 'publish my LLM-maintained wiki to a public URL with selective visibility.'"

Real examples:
- Farzapedia (Farza Majeed, @FarzaTV) — built a 400-article personal wiki, made it private, but STILL wanted a landing page at farza.com/knowledge to show people it exists. He rolled his own Next.js deployment with a password gate.
- The Commonplace wiki (zby) — published via GitHub Pages because that was the only free option. No selective visibility.
- The Grimoire wiki (sprites.app) — published on a custom subdomain.
- Louis Wang — built a wiki, wrote a blog post ABOUT the wiki rather than publishing the wiki itself, noting "A public KB repo exposes everything — your raw notes, compiled wiki, synthesis articles."

The pattern is consistent: people BUILD a wiki, then hit a wall at "how do I let others see the parts I want to share?" Current options are: GitHub Pages (all-or-nothing public, no auth, no agent API), Obsidian Publish ($8-10/month, no agent API, no selective per-file visibility), Quartz (requires Node.js/Git setup, no auth), or roll your own (Farzapedia approach).

**wikihub value prop:** `git push` and you have a URL. Per-file visibility means you share what you want. Agents can read it via the API. This is the #1 user story.

#### 2. "I want my wiki to be my agent's memory, not just mine"

**Signal strength: STRONG.** The "shared brain" pattern is emerging as the killer evolution of the second-brain concept.

Tabrez Syed (Boxcars) wrote the defining essay: "From Second Brain to Shared Brain." Key quote: the vault is "a whiteboard where [I] start [my] morning knowing what [I was] working on yesterday and what changed overnight — not from being briefed, but because the agent was there." The agent logs entries, the human reviews them. The human updates project files, the agent picks up context in its next session without explanation.

This is different from "agent builds wiki" (Karpathy pattern). This is "human AND agent both read and write to the same wiki as a shared working surface."

Additional signals:
- The LLM Wiki v2 gist (rohitg00) explicitly adds "shared vs. private scoping" and "work coordination" for multi-agent scenarios.
- SwarmVault went from single-agent to multi-agent wiki orchestration.
- Rick Watson (RMW Commerce) describes using the wiki for CLIENT work — building a persistent knowledge base around client engagements that both he and Claude maintain.
- The Dume.ai article describes non-technical users wanting their agent to manage their wiki via WhatsApp.

**wikihub value prop:** MCP server + REST API means any agent can read/write. Per-file ACLs mean the human controls what the agent touches. Git history means every agent action is auditable.

#### 3. "I'm building a wiki about a topic I'm deep on, and I want others to be able to fork it or build on it"

**Signal strength: STRONG.** The "idea file" framing is key here.

Karpathy himself framed the gist as an "idea file" — you don't share code, you share intent and let someone else's agent build their own version. The Lobster Pack article crystallizes this: "You don't need to read code to use an idea file. You need to understand what you want." This is literally the fork-a-wiki use case.

The pattern already exists organically: Karpathy's gist has been forked 215+ times. But gist forks are for code — forking a WIKI (the compiled output) doesn't have a home. Nobody can fork Farzapedia and build "MyVersionOfFarzapedia" with their own additions.

The community wiki implementations already show this need:
- agent-wiki (originlabs-app) — "Human drops sources, any LLM compiles same files." The structure is forkable.
- Commonplace (zby) — a wiki ABOUT LLM agent memory systems, maintained BY LLM agents. Others want to add entries.
- The 20+ GitHub implementations of Karpathy's pattern are ALL forks of an idea, but they fork the tool, not the content.

**wikihub value prop:** Fork a public wiki in one click. Your agent gets a copy and can extend it. Suggest edits back upstream (PR-like). The social layer matters HERE — for knowledge sharing, not for vanity metrics.

#### 4. "I have raw sources scattered across tools and I want an agent to compile them into a structured wiki"

**Signal strength: STRONG.** This is the original Karpathy use case but the signal is about the PAIN of the current workflow, not the joy.

Karpathy's pattern requires: Claude Code or similar agent + Obsidian + terminal access + git. Non-technical users hit a wall. Dume.ai article: "The tools that will serve the other 60% of users — the non-developers — haven't always gotten the same attention." Knowledge workers lose 1.8 hours daily searching for information (APQC, 2024).

What people want:
- Drop PDFs, Word docs, Apple Notes exports, iMessage threads, meeting transcripts into a folder
- Agent compiles them into a wiki
- They never touch the terminal

**wikihub value prop:** The v2 ticket "paste unstructured text, get a structured wiki" is exactly this. But even v1 matters: if wikihub accepts zip upload + has an API, an agent can do the compilation remotely. The user never needs a terminal.

### Tier 2 — Moderate signal, fewer independent sources

#### 5. "My team's internal wiki is always out of date and nobody maintains it"

**Signal strength: MODERATE.** Enterprise wiki rot is a well-documented problem. The LLM wiki pattern is the first credible solution.

Signals:
- VentureBeat: "an internal wiki can be maintained by LLMs, fed by Slack threads, meeting transcripts, project documents, and customer calls."
- Slite (Notion competitor) explicitly added "auto-flag outdated content" by comparing docs against Slack/GitHub/Linear activity.
- Atlan: "When documents number in the thousands, authors in the hundreds, and access policies require enforcement, the wiki breaks at scale."
- The LLM Wiki v2 gist: "Staleness detection — articles have no freshness signal" listed as a key gap.

But this is NOT a v1 user story for wikihub. Team wikis need: org accounts, SSO, role-based access at the org level, content moderation, audit trails. The principal abstraction reserves space for it. But the first-mover window is about INDIVIDUAL and SMALL-GROUP use cases.

**wikihub value prop (future):** Agent-maintained team wiki with per-file ACLs, git history for accountability, MCP endpoint so team agents can update it. But this is a v2/v3 story. Don't design v1 around it.

#### 6. "I'm researching a topic across dozens of papers and I want a compounding knowledge base"

**Signal strength: MODERATE.** The academic use case is real but narrow.

Karpathy's own use case was ML research (~100 articles, ~400k words on a single topic). Louis Wang's scaling analysis confirms this works well up to ~100-200 articles.

LitLLMs (literature review toolkit) and STORM (Stanford) both address adjacent problems with different architectures. The wiki pattern adds: persistent, navigable, interlinked output that survives across sessions.

Specific signal: "As you read papers over months, the LLM incrementally builds out an evolving thesis, linking methodologies and noting where researchers contradict each other." (Multiple sources cite this use case.)

**wikihub value prop:** A researcher publishes their literature-review wiki, others fork it, the field compounds. This is the "GitHub for research" angle — not just hosting, but forking and collaboration on knowledge artifacts.

#### 7. "I want to selectively share parts of my wiki — some pages public, some private, some for specific people"

**Signal strength: MODERATE.** The Farzapedia privacy signal is the strongest individual data point here.

Farza built Farzapedia from diary entries, Apple Notes, and iMessage conversations. His immediate reaction: "Considering it made an entire 'Relationship History' article, some things should remain between me and my LLM." He deployed it password-protected.

Louis Wang: "A public KB repo exposes everything."

The LLM Wiki v2 gist identifies "shared vs. private knowledge" as a first-class concern: "some knowledge is personal (my preferences, my workflow) while some is shared (project architecture, team decisions)."

One GitHub implementation (obsidian-llm-wiki-local) literally markets itself as: "Zero cloud. Zero sharing. Your notes stay yours."

**wikihub value prop:** Per-file visibility is THE differentiator over GitHub Pages / Obsidian Publish / Quartz. None of them support mixed public/private content in the same wiki with per-file granularity. wikihub's `.wikihub/acl` + `<!-- private -->` inline bands is a genuine capability nobody else has.

### Tier 3 — Weak/emerging signal

#### 8. "I'm a consultant/professional and I need a knowledge base for client engagements"

Rick Watson (RMW Commerce) describes building wikis around client projects. The wiki accumulates meeting notes, project documents, data room exports. This is real but niche — consultants are a small market that likely won't self-organize around "LLM wiki" as a category.

#### 9. "I want my wiki to be the canonical reference for a community or open-source project"

Google Code Wiki (agent-maintained repo docs), DeepWiki (50k+ AI-generated repo wikis), and the repo-docs generator ecosystem show demand. But this is about CODE documentation, not general knowledge. Different product.

#### 10. "I'm a content creator and my wiki is my content product"

Weak signal. Buildin offers knowledge monetization. Kortex lets you publish from a PKM. But nobody in the Karpathy wave is talking about monetizing their wiki. The audience is builders, not creators. This may emerge later but is not a v1 concern.

---

## Part 2 — Features we're OVEREMPHASIZING

### 1. The Karpathy three-layer schema (raw / wiki / schema)

**Risk: medium.** The three-layer pattern is an ML-researcher workflow. Normal users don't have a "raw sources" folder of PDFs and a "schema.md" that tells the LLM how to compile.

Evidence:
- Farzapedia used diary entries and Apple Notes, not PDFs in a raw/ folder.
- The Boxcars "shared brain" uses a flat Obsidian vault with wikilinks, not a three-layer architecture.
- Rick Watson's consulting wiki has a flat structure organized by client, not raw/wiki/schema.
- The most popular implementations (second-brain, obsidian-wiki) don't enforce the three-layer pattern.

**Recommendation:** Keep the scaffold as a GENTLE NUDGE (as already specified), but don't make the UI, docs, or marketing assume users want three layers. Most users will have: a flat folder of .md files with wikilinks. That should be the primary path. The three-layer pattern is a power-user feature.

### 2. The social layer (fork / star / suggested edits) — for v1

**Risk: low-medium.** The social features ARE important (see user story #3), but they're important for a SPECIFIC use case (forking knowledge bases to extend them), not for general engagement.

Evidence:
- ZERO of the 20+ LLM wiki implementations have social features. People aren't asking for them.
- The Karpathy gist has 12k+ stars and 215+ forks on GitHub — the social features exist on GitHub already. What's missing is the WIKI hosting, not the social layer.
- The Lobster Pack article about idea files focuses entirely on the CONTENT pattern, not discovery/social.

**Recommendation:** Ship fork and star in v1 (they're simple), but don't design the landing page or explore around social engagement. Design them around PUBLISHING and DISCOVERING useful wikis. Fork is a "I want to build on this" action, not a GitHub-star vanity metric.

### 3. `<!-- private -->` inline privacy bands

**Risk: medium-high.** This is an elegant technical solution to a problem most users won't have.

Evidence:
- Nobody in the Karpathy ecosystem is asking for per-section privacy within a page. They want per-FILE privacy (public/private toggle on individual pages).
- Farzapedia's privacy concern was at the article level ("Relationship History" should be private), not the paragraph level.
- The complexity of stripping `<!-- private -->` bands in the public mirror adds implementation cost.

**Recommendation:** Ship it because it's in the spec and the implementation isn't expensive (it's just regex in the mirror-gen hook). But don't MARKET it, don't put it in the onboarding flow, and don't let it shape the UI. Per-file visibility via `.wikihub/acl` is the 95% case.

### 4. Anonymous edits on public-edit pages (Wikipedia-style)

**Risk: medium.** Cool feature, but the Karpathy wave is about PERSONAL wikis. The Wikipedia-style anonymous-edit model is for COMMUNITY wikis, which are a different product with different users.

Evidence:
- Nobody in the current wave is building community wikis that accept anonymous edits.
- Wikipedia itself banned LLM-generated content in March 2026 — the traditional and LLM-wiki worlds are actively diverging.
- Every anti-abuse feature was stripped from v1, which means public-edit pages are unmoderated. This is a liability, not a feature.

**Recommendation:** Keep the mode in the vocabulary (it's already locked), but don't promote it in v1. The first users will be individual wiki owners who want per-file public/private, not community editors. public-edit matters for v2/v3 when community wikis emerge.

---

## Part 3 — Features we're UNDEREMPHASIZING

### 1. "Just give me a URL" — zero-config publishing

**HIGHEST PRIORITY gap.** The #1 user story is "I have a folder of markdown files, give me a public URL." The current spec assumes users will interact via git push, REST API, or web editor. But the true minimum-viable-interaction is:

1. Drag a folder into the browser (or `zip upload`)
2. Get back a URL like `wikihub.md/@alice/my-research`
3. Done

Evidence:
- The Obsidian Publish alternatives discussion is DOMINATED by "I just want to publish" — people are frustrated by the complexity of Quartz (requires Node.js), GitHub Pages (requires git), and Obsidian Publish (costs money, limited customization).
- The Dume.ai article explicitly calls out: non-technical users want "no terminal access required."
- HackMD succeeds because you write markdown and get a URL immediately.

**Recommendation:** The zip upload endpoint is specced (`GET /@user/wiki.zip`). Add its inverse: `POST /api/v1/wikis/:owner/:slug/upload` that accepts a .zip of markdown files and ingests them. Also add a drag-and-drop UI on the "create wiki" page. This should be the FIRST thing shown on the landing page. Not git. Not MCP. Not API. "Drop your files, get a URL."

### 2. Import from Notion / Google Docs / Obsidian

**HIGH PRIORITY gap.** The people building LLM wikis today have their knowledge scattered across these tools. The Karpathy pattern says "dump everything in a raw/ folder" but getting stuff OUT of Notion/Google Docs is painful.

Evidence:
- The Obsidian forum has multiple threads about Notion-to-Obsidian migration, showing demand.
- Karpathy's gist explicitly mentions "Apple Notes, podcast notes, journal entries" as sources.
- Farzapedia ingested "diary entries, Apple Notes, and some iMessage convos."
- Multiple blog posts (MindStudio, DAIR.AI) mention "instead of scattering knowledge across Notion, Google Docs, browser bookmarks" as the pain point.

**Recommendation:** v1 doesn't need deep integrations. It needs: (1) Obsidian vault import (literally zip upload — Obsidian vaults are already markdown), (2) Notion export import (Notion exports as markdown + images in a zip), (3) Google Docs paste (markdown conversion on ingest). The first two are already covered by zip upload if the format is supported. Document this explicitly.

### 3. Content negotiation (agents get markdown, browsers get HTML)

Already in the spec but the research confirms it's THE highest-leverage agent-first move. From the agent-first web brief: "Cloudflare/Vercel/Mintlify all ship it, Claude Code sends `Accept: text/markdown` on every fetch." Every wiki page on wikihub should serve raw markdown to agents and rendered HTML to browsers at the same URL.

**Recommendation:** This is already specced. Elevate it in marketing. The pitch is: "Your wiki has one URL. Humans see a beautiful page. Agents see raw markdown they can parse. No API key needed for public content."

### 4. Mobile reading experience

Mentioned in the spec as a non-functional requirement but signals suggest it's MORE important than the current emphasis implies.

Evidence:
- Farzapedia was built to be browsed by the user on their phone — it's a REFERENCE for daily life, not a desktop research tool.
- The Boxcars "shared brain" describes checking agent entries "the next morning" — this is a phone-in-bed workflow.
- Dume.ai mentions WhatsApp-based wiki management.

**Recommendation:** Already specced as mobile-first CSS. Good. Just make sure the READER VIEW (not just the editor) is genuinely great on mobile. This is the most common access pattern for a personal wiki.

### 5. Staleness detection and knowledge lifecycle

This emerged from Louis Wang's analysis and the LLM Wiki v2 gist as a real pain point:
- Articles have no freshness signal. A summary written from a 2024 paper looks the same as one from yesterday.
- Wikis grow but never shrink. No mechanism to archive or deprecate stale content.
- Contradictions accumulate silently.

**Recommendation:** Not v1. But add a `last_verified` timestamp in frontmatter that the agent can update. This is cheap and gives future staleness detection something to work with.

---

## Part 4 — Persona insights

### Who is actually building LLM wikis in April 2026?

Based on the ~20 GitHub implementations, ~12 blog posts, and named wiki owners:

#### Persona A: The ML/AI researcher (Karpathy archetype)
- Has 50-200 papers on a topic
- Uses Claude Code or Codex daily
- Comfortable with git, terminal, markdown
- Wants: compounding knowledge base, wikilinks, KaTeX, code highlighting
- Publishing need: share the wiki with peers, maybe publicly
- ~30% of current wave

#### Persona B: The indie developer / power user
- Built their own implementation in a weekend
- Uses Obsidian + Claude Code
- Comfortable with git, APIs, self-hosting
- Wants: a better publishing target than GitHub Pages
- Publishing need: "give me a URL and an API endpoint"
- ~40% of current wave (largest group)

#### Persona C: The knowledge worker / consultant
- Has scattered docs across Notion, Google Docs, Apple Notes
- May not use git directly but is comfortable with web UIs
- Uses Claude/ChatGPT but not Claude Code
- Wants: agent compiles my stuff into a wiki, I can share the relevant parts with clients
- Publishing need: per-file visibility, professional-looking URL
- ~15% of current wave, growing fastest

#### Persona D: The non-technical curious
- Read the Karpathy tweet (16M+ views) and wants the benefit without the tooling
- Uses Notion or Apple Notes
- Does NOT use git, terminal, or coding agents
- Wants: "I want my AI to organize my notes and let me share them"
- Publishing need: zero-config publish from a web UI
- ~15% of current wave, largest POTENTIAL audience but hardest to serve in v1

### Key insight on personas

The spec's first-user groups are exactly right:
1. Dogfood migrations (Persona B)
2. Karpathy-gist wave (Personas A + B)
3. Obsidian vault owners (Persona B, some C)

Persona D is the mass market but NOT the v1 target. The v2 ticket "paste unstructured text, get a structured wiki" is the gateway for Persona D.

---

## Part 5 — Synthesis: What wikihub should be for v1

The research converges on a clear hierarchy of what matters:

1. **Publishing** — "I have markdown files, give me a URL" is the #1 need. Everything else is secondary.
2. **Per-file visibility** — The differentiator nobody else has. Public/private/unlisted per file.
3. **Agent API** — MCP + REST + content negotiation. Agents can read AND write. Day one.
4. **Fork** — "I want to build on someone else's wiki." The social feature that actually matters.
5. **Import** — Zip upload, Obsidian vault drag-and-drop. Lower the entry barrier.
6. **Reader quality** — KaTeX, code highlighting, dark theme, mobile-first. Meet the Karpathy-wave expectations.
7. **Star / explore / suggested edits** — Nice to have, not a driver of adoption.

The features that ATTRACT users: publishing + per-file visibility + agent API.
The features that RETAIN users: fork + import + reader quality.
The features that GROW the platform: star + explore + suggested edits + team features.

Ship in that order.

---

## Sources

### Named wiki owners (real signal)
- Farzapedia — Farza Majeed (@FarzaTV): https://x.com/FarzaTV/status/2040563939797504467
- Karpathy boost of Farzapedia: https://x.com/karpathy/status/2040572272944324650
- Commonplace (zby): https://zby.github.io/commonplace/
- Grimoire (sprites.app): https://grimoire-pt5.sprites.app/
- Louis Wang: https://louiswang524.github.io/blog/llm-knowledge-base/

### Key essays and analysis
- "From Second Brain to Shared Brain" (Tabrez Syed, Boxcars): https://blog.boxcars.ai/p/from-second-brain-to-shared-brain
- Karpathy's LLM wiki gist: https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
- LLM Wiki v2 gist (rohitg00): https://gist.github.com/rohitg00/2067ab416f7bbe447c1977edaaa681e2
- Rick Watson consulting use case: https://www.rmwcommerce.com/blog/karpathys-llm-wiki-changes-how-work-is-done
- Dume.ai non-technical user analysis: https://www.dume.ai/blog/what-is-andrej-karpathys-llm-wiki-how-to-get-the-same-results-without-code-using-dume-cowork
- Lobster Pack on idea files vs code: https://www.lobsterpack.com/blog/karpathy-llm-wiki-idea-files/

### HN discussions
- LLM Wiki idea file: https://news.ycombinator.com/item?id=47640875
- Show HN: LLM Wiki OSS: https://news.ycombinator.com/item?id=47656181
- Show HN: CacheZero: https://news.ycombinator.com/item?id=47667723

### Obsidian Publish pain points
- Open-source alternatives: https://www.ssp.sh/brain/open-source-obsidian-publish-alternatives/
- Obsidian Publish alternatives roundup: https://unmarkdown.com/blog/obsidian-publish-alternatives
- Obsidian forum discussion: https://forum.obsidian.md/t/obsidian-publish-alternatives/22886

### Market/landscape
- VentureBeat coverage: https://venturebeat.com/data/karpathy-shares-llm-knowledge-base-architecture-that-bypasses-rag-with-an
- SwarmVault: https://github.com/swarmclawai/swarmvault
- Existing catalog: `/Users/hq/github_projects/listhub/research/llm-wikis-catalog.md`
- Agent-first web brief: `/Users/hq/github_projects/listhub/research/wikihub-spec-work-2026-04-08/agent-first-web-brief-2026-04.md`
