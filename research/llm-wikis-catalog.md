# LLM Wikis — Catalog

**Date:** 2026-04-06
**Scope:** Public, accessible wikis in the "LLM wiki" ecosystem across all 5 senses of the term. Companion to `research/llm-wiki-research.md`.
**Total entries:** ~85

The five senses (from the research doc):

1. **Personal LLM wiki (Karpathy sense)** — LLM curates a markdown knowledge base for one user
2. **AI-generated public encyclopedia** — LLM writes articles at scale for a public audience
3. **Wikis FOR LLMs to consume** — docs shaped to be ingested by LLMs (llms.txt, DeepWiki)
4. **Wikis ABOUT LLMs** — traditional human-written reference content about LLMs
5. **Human + AI collaborative wikis** — shared surfaces where humans and agents both read/write

---

## Sense 1 — Personal LLM wikis (Karpathy-style)

### Named personal wikis (the people who actually built one)

Most builders keep their wiki private — same reason as Farza below. This is the short list of real, named, verified instances. The interesting research subject is **the people**, not the tooling.

- **Farzapedia** — Farza Majeed (@FarzaTV), buildspace founder. Tweeted April 4, 2026; boosted by Karpathy same day. ~400 articles, ~2500 source entries. **Explicitly private** — "Considering it made an entire 'Relationship History' article, some things should remain between me and my LLM." Lukewarm landing page: https://farza.com/knowledge — Twitter announcement: https://x.com/FarzaTV/status/2040563939797504467 — Karpathy boost: https://x.com/karpathy/status/2040572272944324650
- **Commonplace** — `zby` (HN: zbyforgotpass) — https://zby.github.io/commonplace/ — A wiki *about* LLM agent memory systems, maintained by LLM agents (recursive). ~30+ system reviews, hundreds of notes. GitHub Pages. The most rigorous publicly-browsable example.
- **Grimoire** — sprites.app dev (HN: 0123456789ABCDE) — https://grimoire-pt5.sprites.app/ — Self-described "LLM-maintained personal knowledge base" following Karpathy. Themes: AI research, infra, security. "Spells/scrolls/grimoire" framing. Active April 2026 commits.
- **Karpathy's own research wiki** — Andrej Karpathy. ~100 articles, ~400k words on an ML research topic. Described in the gist; **not linked publicly**. Private.
- **Louis Wang's KB** — https://louiswang524.github.io/blog/llm-knowledge-base/ — KB itself is private, but the writeup contains the best scaling analysis publicly available ("~100-200 articles is the index-first ceiling"). Maintainer: Louis Wang.

**Pattern observations:**
- "{Name}pedia" is unclaimed as a naming convention — Farzapedia put it on the map but no product owns it.
- `index.md` at root is the universal entry pattern (Farzapedia, Karpathy, Commonplace).
- The unit of value is the navigable filesystem, not the rendered HTML — 3 of 4 verified wikis are agent-first; humans browse second.
- The publishing gap is real: no popular product exists for "publish my LLM-maintained wiki to a public URL with selective visibility." Obsidian Publish isn't LLM-aware; Quartz isn't packaged with an agent loop. Real practitioners (zby, the grimoire owner) are obvious early-adopter targets for a publish-my-LLM-wiki feature.

### Canonical & tooling

- **Karpathy's llm-wiki gist** — https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f — The original 2026-04-03 "idea file" describing the three-layer raw/wiki/schema pattern. ~8200 stars.
- **llmwiki.app** — https://llmwiki.app/ — Hosted free open-source implementation that builds a compounding wiki via Claude.

### Implementations (GitHub)

- **Astro-Han/karpathy-llm-wiki** — https://github.com/Astro-Han/karpathy-llm-wiki — One Agent Skill for Claude Code / Cursor / Codex.
- **tashisleepy/knowledge-engine** — https://github.com/tashisleepy/knowledge-engine — Karpathy pattern + Memvid; dual human/machine layer.
- **kfchou/wiki-skills** — https://github.com/kfchou/wiki-skills — Claude Code skills (init, ingest, query, lint, update).
- **hellohejinyu/llm-wiki** — https://github.com/hellohejinyu/llm-wiki — Personal wiki CLI with multi-step ReAct query agent.
- **Ar9av/obsidian-wiki** — https://github.com/Ar9av/obsidian-wiki — Markdown skills for building an Obsidian wiki with any agent.
- **Ss1024sS/LLM-wiki** — https://github.com/Ss1024sS/LLM-wiki — Direct port of Karpathy's gist.
- **ussumant/llm-wiki-compiler** — https://github.com/ussumant/llm-wiki-compiler — Claude Code plugin; claims ~90% context-cost reduction.
- **atomicmemory/llm-wiki-compiler** — https://github.com/atomicmemory/llm-wiki-compiler — Knowledge compiler: raw sources → interlinked wiki.
- **sdyckjq-lab/llm-wiki-skill** — https://github.com/sdyckjq-lab/llm-wiki-skill — Multi-agent platform skill (Chinese readme).
- **ekadetov/llm-wiki** — https://github.com/ekadetov/llm-wiki — Claude Code plugin for Obsidian with raw/ wiki/ outputs/ schema.
- **rvk7895/llm-knowledge-bases** — https://github.com/rvk7895/llm-knowledge-bases — Compile/query/lint/evolve commands.
- **toolboxmd/karpathy-wiki** — https://github.com/toolboxmd/karpathy-wiki — Two Claude Code skills (general + project-specific).
- **luotwo/llm-wiki** — https://github.com/luotwo/llm-wiki — LLM Wiki methodology + Claude Code skill + field report (Chinese).
- **john-ver/karpathy-llm-wiki** — https://clawhub.ai/john-ver/karpathy-llm-wiki — Persistent wiki manager via ClawHub marketplace.
- **zhiwehu/second-brain** — https://github.com/zhiwehu/second-brain — AI-maintained personal KB for Claude Code.
- **labeldekho/second-brain** — https://github.com/labeldekho/second-brain — Always-on second brain compounding ideas.
- **swarajbachu/cachezero** — https://github.com/swarajbachu/cachezero — NPM CLI implementing the pattern (Show HN: CacheZero).
- **agent-wiki (originlabs-app)** — https://github.com/originlabs-app/agent-wiki — Human drops sources, any LLM compiles same files.

### Blog posts & essays ("I built one")

- **Building a Self-Improving Personal KB** (Louis Wang) — https://louiswang524.github.io/blog/llm-knowledge-base/
- **The Wiki That Writes Itself** (Extended_Brain) — https://extendedbrain.substack.com/p/the-wiki-that-writes-itself
- **Postscript — The Wiki That Writes Itself** — https://extendedbrain.substack.com/p/postscript-the-wiki-that-writes-itself
- **I Built a Knowledge Base That Writes Itself** (Fabian G. Williams) — https://www.fabswill.com/blog/building-a-second-brain-that-compounds-karpathy-obsidian-claude
- **Karpathy stopped using AI to write code** (Neural Notions, Medium) — https://medium.com/neuralnotions/andrej-karpathy-stopped-using-ai-to-write-code-hes-using-it-to-build-a-second-brain-instead-cddceadc5df5
- **What Is an LLM Wiki** (Dreamwalker, Medium) — https://medium.com/@aristojeff/what-is-an-llm-wiki-and-why-are-people-paying-attention-to-it-b7e10617967d
- **My Second Brain Setup** (Art of Lean) — https://artoflean.com/blog/posts/strange-new-world-of-ai-second-brain/
- **Karpathy's LLM Knowledge Base — Build an AI Second Brain** (Codersera) — https://ghost.codersera.com/blog/karpathy-llm-knowledge-base-second-brain/
- **How to Build an LLM Knowledge Base in Claude Code** (RoboRhythms) — https://www.roborhythms.com/how-to-build-llm-knowledge-base-claude-code-2026/
- **Karpathy's LLM Wiki — Complete Guide** (Antigravity) — https://antigravity.codes/blog/karpathy-llm-wiki-idea-file
- **Karpathy's LLM KBs — Post-Code AI Workflow** (Antigravity) — https://antigravity.codes/blog/karpathy-llm-knowledge-bases
- **LLMs That Compile Knowledge** (Pebblous) — https://blog.pebblous.ai/report/karpathy-llm-wiki/en/

### HN discussion threads

- **LLM Wiki — idea file** — https://news.ycombinator.com/item?id=47640875 — Front-page thread on Karpathy's gist with forks in comments.
- **Show HN: LLM Wiki OSS implementation** — https://news.ycombinator.com/item?id=47656181
- **Show HN: CacheZero** — https://news.ycombinator.com/item?id=47667723

---

## Sense 2 — AI-generated public encyclopedias

### General-purpose

- **Grokipedia** — https://grokipedia.com/ — xAI, ~885k Grok-generated articles. Launched Oct 2025.
- **Endless Wiki (The Infinite Wiki, vgel)** — https://theinfinite.wiki/ — Kimi K2 via Groq; 62k+ pages, 200k+ links. Source: https://github.com/vgel/the-infinite-wiki
- **Globe Explorer** — https://explorer.globe.engineer/ — LLM-generated visual "Wikipedia for anything" with topic tree.
- **WikiGen.ai** — https://www.wikigen.ai/ — Almost-entirely AI-generated encyclopedia with reading-level controls.
- **Mycyclopedia** — https://mycyclopedia.co — GPT-generated encyclopedia with text-selection chat.
- **Eightify Explore** — https://explore.eightify.app — AI-generated TLDR articles, Kurzgesagt-styled.
- **AIPedia (Fandom)** — https://aipedia.fandom.com/ — Fandom wiki whose pages are written by Bing AI.

### Domain-specific

- **WikiCrow** — https://wikicrow.ai/ — FutureHouse; AI-generated cited Wikipedia articles on human protein-coding genes. Rated more accurate than Wikipedia by blinded PhDs.

### Research systems / generators

- **STORM** — https://github.com/stanford-oval/storm — Live demo: https://storm.genie.stanford.edu/ — Stanford OVAL's multi-perspective question-asking pipeline. 70k+ users.
- **WikiChat** — https://github.com/stanford-oval/WikiChat — 7-stage RAG pipeline grounding LLM responses in Wikipedia.
- **WikiAutoGen** — https://wikiautogen.github.io/ — ICCV 2025; multi-agent multimodal Wikipedia-style generation.
- **OmniThink** — https://zjunlp.github.io/project/OmniThink/ — Iterative reflection/expansion for long-form articles.
- **WikiGenGPT** — https://github.com/mrconter1/WikiGenGPT — GPT-4 fictional Wikipedia article generator.
- **LLMpedia** — https://arxiv.org/html/2603.24080 — Academic framework for materializing LLM parametric knowledge.
- **AutoWiki (MxDkl)** — https://github.com/MxDkl/AutoWiki — Lightweight auto-generated wiki tool.

### Repo-docs generators (AI-generated wikis about GitHub repos)

- **DeepWiki (Cognition)** — https://deepwiki.com/ — 50,000+ AI-generated repo wikis. Swap `github.com` → `deepwiki.com`.
- **DeepWiki Directory** — https://deepwiki.directory/ — Browsable index of notable DeepWiki entries.
- **Auto Wiki (Mutable.ai)** — https://wiki.mutable.ai/ — Wikipedia-style repo wikis with code-line citations and Mermaid diagrams.
- **OpenDeepWiki** — https://github.com/AIDotNet/OpenDeepWiki — OSS DeepWiki clone in C#/TypeScript.
- **deepwiki-open (AsyncFuncAI)** — https://github.com/AsyncFuncAI/deepwiki-open — OSS DeepWiki for GitHub/GitLab/Bitbucket.
- **deepwiki-rs (Litho)** — https://github.com/sopaco/deepwiki-rs — Rust-based C4-model architecture wikis.
- **CodeWiki (FSoft-AI4Code)** — https://github.com/FSoft-AI4Code/CodeWiki — ACL 2026; multilingual repo documentation.
- **codewiki (quangdungluong)** — https://github.com/quangdungluong/codewiki — Wiki-style docs for GitHub or local repos.
- **CodeWiki (Muhammad Raza)** — https://muhammadraza.me/2026/building-codewiki-compiling-codebases-into-living-wikis/ — Obsidian-compatible living wikis as knowledge graph.
- **RepoWiki (zzzhizhia)** — https://github.com/zzzhizhia/repowiki — Agent skill generating REPOWIKI.md with Mermaid.
- **Qoder Repo Wiki** — https://docs.qoder.com/user-guide/repo-wiki — Built-in AI repo wiki in Qoder IDE.
- **Lingma Repo Wiki (Alibaba)** — https://www.alibabacloud.com/help/en/lingma/user-guide/repo-wiki — AI repo wiki in Alibaba Lingma.
- **PandaWiki (Chaitin)** — https://github.com/chaitin/PandaWiki — OSS AI-driven knowledge base with built-in AI Q&A.

---

## Sense 3 — Wikis FOR LLMs to consume (representative sample)

Note: 13,000+ llms.txt sites exist. This is a sample of the canonical/most-cited implementers. For the full universe, see llmstxthub.com.

- **llmstxt.org** — https://llmstxt.org/ — The specification itself.
- **Cloudflare Developers** — https://developers.cloudflare.com/llms.txt — Canonical large-scale llms.txt with per-product sub-indexes.
- **Stripe Docs** — https://docs.stripe.com/llms.txt — Product-category-organized with explicit Optional section.
- **Vercel Docs** — https://vercel.com/docs/llms.txt — ~400k-word llms-full.txt.
- **Supabase Docs** — https://supabase.com/docs/llms.txt — Early dev-docs adopter.
- **Perplexity Docs** — https://docs.perplexity.ai/llms.txt
- **Coinbase Developer Platform** — https://docs.cdp.coinbase.com/llms.txt — Mintlify-hosted; early production deployment.
- **Anthropic docs** — https://docs.anthropic.com/ — Referenced in the llms.txt canon.
- **Fern** — https://buildwithfern.com — Auto-generates llms.txt and serves markdown to detected LLM UAs.
- **GitBook** — https://gitbook.com — Added llms.txt + llms-full.txt + per-page .md serving in 2025.
- **llms-txt-hub** — https://llmstxthub.com/ — The meta-directory. Source: https://github.com/thedaviddias/llms-txt-hub
- **directory.llmstxt.cloud** — https://directory.llmstxt.cloud/ — Alternative directory, ~1000 entries.
- **llmtxt.app** — https://llmtxt.app/ — Largest (~13k sites, crawl-based).

---

## Sense 4 — Wikis ABOUT LLMs (canonical references only)

- **Wikipedia: Large language model** — https://en.wikipedia.org/wiki/Large_language_model
- **Wikipedia: List of large language models** — https://en.wikipedia.org/wiki/List_of_large_language_models
- **Wikiversity: Large language models** — https://en.wikiversity.org/wiki/Large_language_models

Note: Wikipedia banned LLM-generated article content in March 2026 — the traditional wiki world and the LLM-wiki world are actively diverging.

---

## Sense 5 — Human + AI collaborative wikis

### Designed-from-scratch as peer surfaces (the rare ones)

- **Semiont (AI Alliance)** — https://github.com/The-AI-Alliance/semiont — Graph-based AI-native wiki on W3C Web Annotation, MCP-exposed.
- **AgentWiki** — https://agentwiki.org/ — DokuWiki-based, JSON-RPC endpoint for agent read/write.
- **agent-wiki (originlabs-app)** — https://github.com/originlabs-app/agent-wiki — Karpathy-pattern shared wiki (also listed in sense 1).
- **obsidian-wiki (Ar9av)** — https://github.com/Ar9av/obsidian-wiki — Framework for agents to maintain a shared Obsidian wiki.
- **HiClaw (agentscope-ai)** — https://github.com/agentscope-ai/HiClaw — Collaborative multi-agent OS where humans/agents share state via Matrix.

### MCP-exposed wikis (retrofit)

Local-first / structured-note apps with MCP bridges:
- **Anytype + anytype-mcp** — https://github.com/anyproto/anytype-mcp — Encrypted local-first collaborative wiki; official MCP.
- **Tana (Local API + MCP)** — https://outliner.tana.inc/docs/local-api-mcp — Community MCP: https://github.com/tim-mcdonnell/tana-mcp
- **Notion MCP (official)** — https://developers.notion.com/docs/mcp — Source: https://github.com/makenotion/notion-mcp-server

Traditional wiki engines with MCP bridges:
- **Wiki.js MCP Server** — https://github.com/jaalbin24/wikijs-mcp-server — Search/read/create/update via GraphQL.
- **MediaWiki MCP Server (Professional Wiki)** — https://github.com/ProfessionalWiki/MediaWikiMcpServer — OAuth-gated.
- **BookStack MCP Server** — https://github.com/oculairmedia/Bookstack-MCP — 47-58 endpoints as MCP tools.
- **Confluence MCP (mcp-atlassian)** — https://github.com/sooperset/mcp-atlassian — Read/write/append/archive Confluence Cloud.
- **Azure DevOps Wiki MCP** — https://github.com/uright/azure-devops-wiki-mcp
- **GitHub Wiki MCP** — https://github.com/andreahaku/github_wiki_mcp
- **DokuWiki MCP (doobidoo)** — https://github.com/doobidoo/dokuwiki-mcp-server — Zero-dep, JWT auth.
- **DokuWiki AIAgent plugin** — https://forum.dokuwiki.org/d/25934-plugin-introduction-aiagent-an-ai-agent-for-your-wiki
- **MediaWiki AIEditingAssistant** — https://www.mediawiki.org/wiki/Extension:AIEditingAssistant — VisualEditor-integrated; AI edits in the same history as human edits.
- **SilverBullet MCP** — https://github.com/Ahmad-A0/silverbullet-mcp — Self-hosted Markdown/Lua wiki bridge.

Personal PKM with MCP bridges:
- **Obsidian MCP Server (cyanheads)** — https://github.com/cyanheads/obsidian-mcp-server — Most comprehensive Obsidian MCP.
- **Obsidian MCP (StevenStavrakis)** — https://github.com/StevenStavrakis/obsidian-mcp
- **mcpvault (bitbonsai)** — https://github.com/bitbonsai/mcpvault — Frontmatter-safe Obsidian MCP.
- **Logseq MCP (ergut)** — https://github.com/ergut/mcp-logseq
- **logseq-mcp-tools (joelhooks)** — https://github.com/joelhooks/logseq-mcp-tools

---

## Observations

1. **Sense 1 exploded in days.** Karpathy posted April 3, 2026; this catalog found ~20 GitHub implementations and ~12 "I built one" blog posts within 72 hours. The ecosystem is moving faster than any directory can follow.

2. **Sense 2 has two distinct sub-categories**: general-purpose AI encyclopedias (Grokipedia, Endless Wiki, WikiGen) and repo-docs generators (DeepWiki and ~10 clones). Treating them together understates how different the use cases are.

3. **Sense 5 is overwhelmingly retrofit.** ~17 of the ~20 sense-5 entries are MCP adapters bolted onto pre-existing wikis. Only 5 projects are designed from scratch as peer surfaces: Semiont, AgentWiki, originlabs/agent-wiki, Ar9av/obsidian-wiki, HiClaw. The frontier is small enough to read all of them.

4. **Implication for ListHub:** Shipping an MCP server around the existing REST API is the single highest-leverage move — it adds ListHub to the sense-5 MCP-bridge category instantly (~20 peers), and because ListHub is already git-backed markdown it also qualifies structurally for senses 1 and 3.

5. **Gaps in the ecosystem:** AFFiNE, Roam, Capacities, and Outline have no notable MCP servers — open opportunity. No directory yet includes Karpathy-style personal wikis. No archival project exists.
