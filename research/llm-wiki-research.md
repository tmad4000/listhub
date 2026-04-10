# LLM Wiki Book on ListHub — Research & Plan

**Date:** 2026-04-06
**Author:** Claude (autonomous research session)
**Status:** Research complete, plan drafted, no implementation yet

---

## TL;DR

1. **"LLM Wiki" is five overlapping concepts**, not one. Karpathy's April 3, 2026 gist crystallized one sense (personal markdown KB maintained by an LLM). The other four are AI-generated public encyclopedias, agent-readable knowledge, traditional wikis-about-LLMs, and human+AI collaborative wikis.
2. **No "LLM Wiki Book" exists.** No archive, no awesome-list, no Hugging Face dataset that catalogs LLM wiki communities. The term is days old. First-mover window is open and measured in **weeks**.
3. **No Moltbook-style preemptive archive of LLM wikis exists.** Closest analogue is `ronantakizawa/moltbook` on Hugging Face. The `{topic}book` naming pattern is a one-off — recommend NOT using "llmwikibook" as a name (reads derivative).
4. **ListHub is structurally a perfect substrate.** Git-backed per-user markdown wikis + REST API + llms.txt = it already IS an LLM wiki platform (senses 1, 3, 5). A directory hosted on ListHub dogfoods the thing it catalogs.
5. **Recommended action:** Build the directory on ListHub, lead with the five-sense taxonomy, ship within 2 weeks.

---

## Part 1 — What is an "LLM Wiki"?

The term is **not a single thing**. As of early April 2026 it umbrellas five distinct meanings, which blog posts and tweets routinely conflate:

| # | Sense | Who writes it | Who reads it | Example |
|---|---|---|---|---|
| 1 | **Personal LLM wiki (Karpathy sense)** | LLM, on demand | The user | Karpathy's gist |
| 2 | **AI-generated public encyclopedia** | LLM, at scale | The public | Grokipedia, Endless Wiki |
| 3 | **Wiki FOR LLMs to consume** | Humans (mostly) | Other LLMs | llms.txt sites, DeepWiki |
| 4 | **Wiki ABOUT LLMs** | Humans | Humans | Wikipedia "Large language model" |
| 5 | **Human + AI collaborative wiki** | Both | Both | Semiont, AgentWiki |

The April 2026 Karpathy post (sense 1) is currently capturing the term. A directory project should pick which senses it covers and say so explicitly. The five-sense taxonomy is itself a contribution — most blog posts on the topic don't draw the distinction.

---

## Part 2 — Concrete examples (with URLs)

### Sense 1 — Karpathy-style personal LLM wikis (the new hotness)
- **Karpathy's gist** — https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f — three-layer architecture (raw / wiki / schema), markdown-first, ~100 articles / 400k words. The canonical reference, posted 2026-04-03.
- **Astro-Han/karpathy-llm-wiki** — https://github.com/Astro-Han/karpathy-llm-wiki — packaged "skill" to build your own.
- **knowledge-engine (tashisleepy)** — https://github.com/tashisleepy/knowledge-engine — Karpathy pattern + Memvid, dual human/machine layer.
- **kfchou/wiki-skills** — https://github.com/kfchou/wiki-skills
- **hellohejinyu/llm-wiki** — https://github.com/hellohejinyu/llm-wiki
- **llmwiki.app** — https://llmwiki.app/

### Sense 2 — AI-generated public encyclopedias
- **Grokipedia** — https://grokipedia.com/ — xAI, 885k articles, launched Oct 2025. Bias and hallucination criticism.
- **Endless Wiki** — https://www.endlesswiki.com/ — Kimi K2 via Groq, 62k+ pages, on-demand generation.
- **STORM (Stanford)** — https://github.com/stanford-oval/storm — research system for automated Wikipedia article generation.
- **LLMpedia** — https://arxiv.org/html/2603.24080 — academic framework for materializing LLM parametric knowledge.

### Sense 3 — Wikis FOR LLMs
- **llms.txt ecosystem** — https://llmstxt.org/ — adopted by 780+ companies (Anthropic, Cursor, Cloudflare, Vercel).
- **DeepWiki (Cognition)** — https://deepwiki.com/ — 50,000+ AI-generated repo wikis. URL trick: `github.com` → `deepwiki.com`.

### Sense 5 — Human + AI collaborative
- **Semiont (AI Alliance)** — https://github.com/The-AI-Alliance/semiont — graph-based, W3C Web Annotation, MCP-exposed.
- **AgentWiki** — https://agentwiki.org/ — DokuWiki + JSON-RPC for agent read/write.

### Sense 4 — Wikis ABOUT LLMs (for completeness)
- Wikipedia: Large language model, List of large language models
- Wikiversity: Large language models course
- (Note: Wikipedia banned LLM-generated article content in March 2026 — the traditional and LLM-wiki worlds are diverging right now.)

---

## Part 3 — Existing directories / meta-resources

Every directory I could find covers exactly **one** sense, mostly sense 3:

- **llms-txt-hub** — https://llmstxthub.com/ (David Dias, PR-based, 500+ entries — most credible)
- **llmtxt.app** — https://llmtxt.app/ (~13,000 entries, crawl-based — largest)
- **directory.llmstxt.cloud** — ~1,000 entries, Tally form submissions
- **llms-txt.io (directory page)** — 90+ companies, curated by category
- **llmstxt.site**, **llmsdirectory.com**, **llmstxtdirectory.org** — smaller variants
- **DeepWiki Directory** — https://deepwiki.directory/ (sense 2 narrowly, repo wikis only)
- **SecretiveShell/Awesome-llms-txt** — GitHub awesome-list

**Nothing spans all five senses.** Nothing catalogues Karpathy-style personal wikis (the trend is 3 days old). Nothing catalogues sense-5 collaborative wikis as a category.

---

## Part 4 — Has anyone built an "LLM Wiki Book"?

**Direct answer: No.** Searches for "LLM Wiki Book", "LLMWikiBook", "llmwikibook" return nothing. There is no Moltbook-style preemptive archive of the LLM wiki ecosystem, no Archive Team effort, no Hugging Face dataset.

### Why nothing exists yet
- The Karpathy post is **3 days old** (2026-04-03). There is not yet anything to shut down.
- Archive Team is not engaged with AI-native content preservation as of 2026.
- The traditional wiki world and the LLM wiki world only began diverging in March 2026 (Wikipedia LLM ban).

### Closest analogue
- **ronantakizawa/moltbook** on Hugging Face — community-collected dataset of Moltbook posts. This is the format template to copy: snapshot the corpus + publish as a HF dataset for permanence.

### About the `{topic}book` naming pattern
- "Moltbook" is a one-off. Etymology: Clawd → Moltbot → Moltbook (lobster molting + Facebook). No other AI archive uses the `*book` suffix.
- **Recommendation: do NOT name this "llmwikibook".** It reads derivative, signals nothing functional. Better names: `awesome-llm-wikis`, `llmwiki-archive`, `wikiark`, `llm-wiki-index`, or simply hosting it as a ListHub item titled "LLM Wikis".

---

## Part 5 — Adjacent landscape: agent-friendly app directories

Relevant because the LLM Wiki Book is one instance of a broader pattern ListHub should occupy.

- **MCP server directories** are the most active scene: mcp.so, Smithery, mcpservers.org (claims 20k), ToolSDK (~4.5k), GitHub MCP Registry (~44, official but tiny), plus 5+ awesome-mcp-servers GitHub lists.
- **Agent-API directories** are thin: agentsapis.com is the only real one.
- **PKM directories** (awesome-pkm, awesome-note-taking) are mature but completely agent-unaware — no entry tagged "has llms.txt / has MCP server / has REST API".
- **Has ListHub itself been catalogued?** No. Zero hits. Note: name collides with Move, Inc.'s real-estate MLS service — branding risk worth noting.

**Biggest unfilled category:** A cross-protocol directory that indexes "has llms.txt AND MCP server AND public REST API". Whoever builds it defines the category. ListHub is structurally suited to host it because it IS a list publishing platform.

---

## Part 6 — Plan: LLM Wiki Book on ListHub

### Should this live on ListHub? — **Yes.**

Reasons:
1. **Dogfooding.** ListHub is a markdown-list publishing platform with git backing and llms.txt. The directory of LLM wikis is itself an LLM wiki (sense 1 + 3). Hosting it elsewhere would be a missed proof point.
2. **Distribution.** ListHub already has `/@jacobreal/agent-friendly-apps`. The new list slots into the same surface and benefits from the existing agent-first-web positioning (mockups/agentfirst-standard.html, beads ticket listhub-7aw).
3. **Permanence story.** Git-backed → `git clone`-able → can be mirrored to GitHub and Hugging Face later for archive permanence (the Moltbook angle).

### Structure

A single ListHub list with the **five-sense taxonomy as section headers**, not a flat collection. Each entry has:

```yaml
title: <name>
url: <primary URL>
sense: 1 | 2 | 3 | 4 | 5    # which kind of LLM wiki
type: implementation | spec | example | directory | research
maintainer: <person/org>
first_seen: <date>
status: live | archived | research
description: <1-2 sentences>
notes: <optional commentary>
```

The "sense" field is the key contribution — it forces the taxonomy on the reader.

### Relationship to existing work

- **`/@jacobreal/agent-friendly-apps`** — that list catalogs *apps that work well with agents*. The LLM Wiki list catalogs *wikis in the LLM ecosystem*. Different scope. Cross-link both ways.
- **`listhub-7aw.2`** (llms-txt.io directory bi-directional link, 788+ sites) — overlaps sense 3 only. Reference the integration but don't duplicate; the LLM Wiki list should NOT try to be a 13,000-entry llms.txt directory. It should be a ~50-entry curated index across all five senses.
- **`listhub-bd1`** (publishable curated directory UI like flowtools.directory) — the LLM Wiki Book is a natural first customer for that template once it ships.

### What "aspects public" means here

ListHub has visibility controls (public/unlisted/private). For the LLM Wiki Book, **everything public**. The whole point is discoverability. No private fields. The list itself is the artifact.

### Single big list vs community directory?

**Start as a single curated list, opt into community contributions later.** Reasons:
- The first-mover window is weeks, not months. Solo publishing is faster than coordinating.
- Curation quality matters more than breadth in the early days — 30 hand-picked entries with the taxonomy is more valuable than 300 auto-crawled URLs.
- ListHub already supports `comments / suggested additions` (listhub-zyc), so the path to community contributions exists when ready.

### Moltbook-style "archive before disappearance" angle

Apply selectively, not as the framing. The Karpathy ecosystem is too young to be at risk of disappearing yet. But:
- **Snapshot Karpathy's gist content** into the list as a preserved copy (gists can be deleted).
- **Mirror each external wiki's homepage** via the Internet Archive's Wayback Machine and link to the snapshot alongside the live URL.
- **Publish a Hugging Face dataset companion** later — `jacobcole/llm-wikis` — which is the actual `{topic}book`-shaped artifact. Use the `ronantakizawa/moltbook` format as template.

This gives a graceful "we are archiving this" story without hyperbole, and creates two independent persistence layers (ListHub + HF).

### Naming

- **List title on ListHub:** "LLM Wikis" (plural, function-signalling, no `book` suffix).
- **Slug:** `/@jacobreal/llm-wikis`
- **HF dataset (later):** `jacobcole/llm-wikis`
- **Avoid:** llmwikibook, llm-wiki-book — reads derivative.

---

## Part 7 — Concrete next steps

1. **Create the list on ListHub** (this session — API call below)
2. **Seed with ~25 entries** across the five senses, drawing from Part 2 above
3. **Write a top-of-list explainer** containing the five-sense taxonomy
4. **Submit to relevant directories**: Hacker News (Show HN), r/LocalLLaMA, llms-txt-hub PR, post to Karpathy's gist comments
5. **Add Wayback Machine snapshots** for the ~10 most-likely-to-rot entries
6. **(Stretch) Mirror to Hugging Face dataset** for permanence — the `{topic}book` artifact

### Risks and mitigations

| Risk | Mitigation |
|---|---|
| Term "LLM wiki" gets captured by Karpathy sense within a month, taxonomy looks pedantic | Title with plural ("LLM Wikis"), explicitly frame as covering a family |
| ListHub name collision with real-estate product hurts discoverability | Submit as "ListHub (globalbr.ai)" everywhere; consider rename later |
| Curation work doesn't scale | Open community contributions via existing comments system once seeded |
| First-mover window closes | Ship within 2 weeks. Don't perfect — publish and iterate. |

---

## Sources (all)

### LLM wiki research
- Karpathy's gist — https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
- VentureBeat coverage — https://venturebeat.com/data/karpathy-shares-llm-knowledge-base-architecture-that-bypasses-rag-with-an
- Sean Goedecke on Endless Wiki — https://www.seangoedecke.com/endless-wiki/
- Endless Wiki — https://www.endlesswiki.com/
- Grokipedia — https://en.wikipedia.org/wiki/Grokipedia
- llms.txt spec — https://llmstxt.org/
- llms-txt-hub — https://github.com/thedaviddias/llms-txt-hub
- DeepWiki — https://deepwiki.com/
- Semiont — https://github.com/The-AI-Alliance/semiont
- AgentWiki — https://agentwiki.org/
- knowledge-engine — https://github.com/tashisleepy/knowledge-engine
- STORM overview — https://dev.to/foxgem/overview-storm-automating-wikipedia-article-creation-with-large-language-models-1i1j
- LLMpedia — https://arxiv.org/html/2603.24080
- Medium: What Is an LLM Wiki — https://medium.com/@aristojeff/what-is-an-llm-wiki-and-why-are-people-paying-attention-to-it-b7e10617967d
- Wikipedia bans AI-generated content — https://www.404media.co/wikipedia-bans-ai-generated-content/

### Directory landscape
- llmtxt.app, directory.llmstxt.cloud, llmstxthub.com, llms-txt.io, llmstxt.site, llmsdirectory.com, llmstxtdirectory.org
- mcp.so, Smithery, mcpservers.org, ToolSDK MCP Registry, GitHub MCP Registry
- agentsapis.com, agent.ai, e2b-dev/awesome-ai-agents, Postman API Network
- doanhthong/awesome-pkm, tehtbl/awesome-note-taking, brettkromkamp/awesome-knowledge-management

### Moltbook / archival
- ronantakizawa/moltbook — https://huggingface.co/datasets/ronantakizawa/moltbook
- Simon Willison on Moltbook — https://simonwillison.net/2026/Jan/30/moltbook/

### Full subagent reports
- `/Users/Jacob/memory/research/llm-wiki-landscape-2026-04-06.md`
- `/Users/Jacob/memory/research/agent-friendly-resource-directories-2026-04-06.md`
- `/Users/Jacob/memory/research/llmwikibook-existence-check.md`
