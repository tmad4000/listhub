# Agent-First Web Standards Brief — April 2026

Scoped research input for a new LLM-wiki host that wants to be agent-native from day one. Not a survey — just what's actionable. Reuses prior research in `../llm-wiki-research.md` and `../llm-wikis-catalog.md` (parent research/ directory) for llms.txt adopters and MCP-wiki peers; does not re-derive those.

Verification caveat: everything below is synthesized from web search results performed 2026-04-08 from this session. Specs marked "proposed" or "SEP-####" are not yet merged into core standards. Where something is controversial I flag it explicitly.

---

## 1. WebMCP

**State of the art.** WebMCP is the current canonical answer to "how does a web page expose MCP tools to an agent in the browser." It is a W3C Web Machine Learning Community Group deliverable (accepted Sept 2025 after a Google/Microsoft unification in Aug 2025). Early preview shipped in Chrome 146 behind `chrome://flags` → "WebMCP for testing" in Feb 2026. Native Chrome/Edge support is targeted H2 2026. Not in Safari or Firefox.

Two APIs:
- **Declarative**: annotate HTML forms; browser exposes them as tools automatically.
- **Imperative**: JS side — `navigator.modelContext.registerTool({name, description, inputSchema, handler})`. The browser's built-in agent (or an extension) can then invoke the tool in-page with the user's session cookies already attached.

**Relationship to server-hosted MCP.** Orthogonal. Server MCP is for headless agents hitting your backend with their own credentials. WebMCP is for in-browser agents acting as the logged-in human, reusing the live session. Good sites will likely ship both: a server MCP for programmatic agents and WebMCP for the "Claude-in-my-browser" case. WebMCP notably sidesteps the auth problem for consumer agents because the user is already authenticated in the tab.

**Discovery conventions.** No `.well-known` for WebMCP itself — tools are registered at runtime in the page. The loose convention settling in is: register tools early on page load, gate sensitive ones behind an explicit user-visible confirmation step (the spec emphasizes human-in-the-loop).

**What "good" looks like.** A wiki page for an item would register at minimum: `read_page`, `edit_page(markdown)`, `append_section(heading, markdown)`, `add_tag(tag)`, `link_to(other_item_id)`. Input schemas are JSON Schema. Descriptions matter more than names — they're the only thing the LLM sees.

**Unsettled/controversial.** (a) Safari/Firefox have said nothing public. (b) Extension-based agents vs. browser-builtin agents will compete for the same API surface; expect permission-prompt UX churn. (c) Spec still argues about whether tools should be enumerable across tabs or strictly per-tab. (d) No standard way yet to advertise "this site has WebMCP tools" before the agent loads the page — so discovery still falls back to llms.txt / well-known.

**URLs.**
- https://webmachinelearning.github.io/webmcp/ — the spec draft
- https://github.com/webmachinelearning/webmcp — repo + issues
- https://developer.chrome.com/blog/webmcp-epp — Chrome 146 early preview announcement
- https://patrickbrosset.com/articles/2026-02-23-webmcp-updates-clarifications-and-next-steps/ — the clearest insider explainer
- https://www.scalekit.com/blog/webmcp-the-missing-bridge-between-ai-agents-and-the-web — practical write-up with code

---

## 2. llms.txt

**State of the art.** Still a proposed informal standard from AnswerDotAI. No W3C/IETF track. Directory counts as of early 2026: llmstxthub.com lists ~900 sites; llmstxt.io tracks ~780; the long tail (incl. small blogs) crosses 13,000 per catalog data in our prior research. The spec itself hasn't meaningfully changed since 2024.

**The uncomfortable adoption data.** AEO/SearchSignal analyses in Q1 2026 found (a) <1% of pages cited by major AI answer engines have llms.txt; (b) no measurable citation uplift from having one; (c) none of OpenAI/Google/Anthropic/Meta/Mistral have publicly committed to consuming it. So it is culturally important — you will look unserious without it — but it is not actually a retrieval signal.

**What's actually working in 2026.** The pattern that *is* getting traction is the sibling convention:
- `/llms.txt` — curated index of key pages (links only, markdown)
- `/llms-full.txt` — every page's markdown concatenated (Vercel ships ~400k words)
- **Per-page `.md`**: serve `/some/page.md` alongside `/some/page`. This is the load-bearing pattern.
- **Content negotiation**: see section 5. This is quietly eating the `.md` suffix convention's lunch because it doesn't require URL duplication.

**What "good" looks like in April 2026.**
1. `/llms.txt` as a curated table of contents grouped by section with an explicit `## Optional` bucket for low-priority pages (the Stripe pattern).
2. `/llms-full.txt` auto-generated from your markdown store at build/deploy.
3. Every canonical URL serves markdown via `Accept: text/markdown` *and* via `.md` suffix. Belt and suspenders.
4. Frontmatter on every doc so the ingested `.md` carries its own metadata.
5. **Do not** rely on llms.txt as your only agent surface. Pair it with content negotiation + a capability manifest.

**Early-adopter examples** (already in `../llm-wikis-catalog.md` — don't re-derive): Cloudflare, Stripe, Vercel, Supabase, Perplexity, Anthropic docs, Mintlify-hosted sites, GitBook, Fern.

**Unsettled/controversial.** Mintlify/llms.txt proponents say "it's about supplying clean context on request, not SEO." Skeptics (Search Engine Land, ALLMO) counter "no major AI consumer actually reads it." Both are true. Treat it as table stakes for credibility, not as a distribution channel.

**URLs.**
- https://llmstxt.org/ — the spec
- https://llmstxthub.com/ — the canonical directory
- https://github.com/thedaviddias/llms-txt-hub — directory source
- https://www.mintlify.com/blog/context-for-agents — content negotiation + llms.txt combined
- https://www.aeo.press/ai/the-state-of-llms-txt-in-2026 — the skeptical data

---

## 3. Agent-native auth

**State of the art.** No clean standard. Four patterns are in active use; pick them deliberately.

1. **Bootstrap API key via signup endpoint.** `POST /api/v1/signup` → returns `{user_id, api_key}`. No email required, username optional (server-assigned if omitted). This is what ListHub already does and is the single cleanest pattern for a wiki host. The risk is abuse; see rate limiting below.

2. **OAuth 2.0 Device Authorization Grant (RFC 8628).** The "type this code into a browser" flow. Works well for CLI agents on the user's machine. Doesn't solve headless-agent signup — the user still has to exist.

3. **WebAuthn + delegation.** Consensus in 2026 security circles (RSAC, Corbado, Bitwarden Agent Access SDK): **agents cannot and should not hold passkeys**. The pattern is human authenticates with passkey → server issues a scoped, short-lived delegation token for the agent. Bitwarden shipped an "Agent Access SDK" in early 2026 that intercepts the agent's API calls and injects keys from a vault so the LLM never sees them.

4. **Token Exchange (RFC 8693) delegation tokens.** The formal answer to "agent acts on behalf of user." Token carries both subject (user) and actor (agent) identities. Very little consumer-facing tooling yet; mostly enterprise IAM (CyberArk, Okta).

**Signup without email.** Becoming normal for agent-oriented services. Email as optional affiliation field — not required for account creation, only for "attach a human contact method later." GitHub-style username + programmatic `PATCH /users/me` to rename username/display_name/email is the emerging idiom. (ListHub already ships this — see `listhub-u02`.)

**Rate limiting that doesn't break agents.** The working pattern:
- Per-API-key quotas, not per-IP (agents share IPs with users).
- Generous burst, tight sustained. 60 req/min burst, 1000 req/hour sustained is typical for wiki-scale writes.
- `429` with `Retry-After` and a machine-readable JSON body `{error, retry_after_seconds, quota_remaining}` — agents handle this far better than HTML error pages.
- Exempt read GETs of `.md` from aggressive limits — encourage scraping, it's the point.
- Captchas on *signup* only, never on API calls. And a PoW/hashcash alternative for headless signup is worth offering as an escape hatch.

**What "good" looks like for a wiki host.**
- Signup: `POST /api/v1/signup {display_name?, email?}` → 201 `{user_id, username, api_key}`. No captcha if request carries a valid PoW token or invitation code.
- Profile rename: `PATCH /api/v1/users/me` works for username, display_name, email independently.
- Key management: `POST /api/v1/keys` (session-auth only), `DELETE /api/v1/keys/:id`, `GET /api/v1/keys`.
- Treat API keys as PATs: one per agent/device, user-named, revocable, last-used timestamp.
- Accept API key in Git HTTP Basic Auth alongside password (ListHub already does this).

**Unsettled/controversial.** The biggest live debate: should an agent have its *own* identity distinct from the user (with its own `agent_id`), or should it only ever wear the user's identity via a token? Enterprise says "separate identity, audit trail required." Consumer tools say "too much friction, just use a scoped PAT." For a wiki host, start with scoped PATs and add agent-identity metadata (`X-Agent-Name` header, logged) as a non-enforced convention.

**URLs.**
- https://nango.dev/blog/guide-to-secure-ai-agent-api-authentication — best practical 2026 overview
- https://www.corbado.com/blog/ai-agents-passkeys — why agents can't use passkeys, and the delegation pattern
- https://bitwarden.com/blog/introducing-agent-access-sdk/ — vault-mediated key injection
- https://developer.cyberark.com/blog/zero-trust-for-ai-agents-delegation-identity-and-access-control/ — RFC 8693 in practice
- https://datatracker.ietf.org/doc/html/rfc8628 — device flow

---

## 4. Agent-discoverable capability manifests

**State of the art.** Fragmented. OpenAI's `ai-plugin.json` is dead. Its replacements haven't consolidated. As of Q1 2026 there are "104,000+ agents, 15+ registries, 10+ IETF drafts, zero interoperability" (global-chat.io's phrasing — harsh but fair).

**The live candidates.**
1. **MCP SEP-1649**: `/.well-known/mcp/server-card.json` — rich metadata (name, description, homepage, tools list, auth).
2. **MCP SEP-1960**: `/.well-known/mcp` — RFC 8615 style endpoint enumeration + auth discovery, modeled on OAuth/OIDC discovery docs.
3. **JSON Agents / PAM (jsonagents.org)**: portable agent manifest — JSON-Schema-based, framework-agnostic. Some traction, no major-vendor commitment.
4. **AGENTS.md** (agents.md, adopted by OpenAI Codex, Anthropic Claude Code, Cursor): plain Markdown at the repo/site root telling *coding* agents how to work with the codebase. Not a capability manifest in the RPC sense — it's prose instructions. But it is the *one* format that has actually achieved multi-vendor adoption in 2026, so ship it.
5. **OpenAPI + `x-mcp` extensions**: some sites annotate their existing OpenAPI spec with MCP hints. Low ceremony; works today.

**Neither SEP-1649 nor SEP-1960 is merged** into core MCP spec as of Feb 2026. Discussion lives at https://github.com/modelcontextprotocol/modelcontextprotocol/discussions/1147. Major clients (Claude, Cursor, ChatGPT) are reportedly implementing both speculatively. The advice from the Ekamoira write-up is "ship both endpoints."

**What "good" looks like for a wiki host in April 2026.** Ship all of these — they're cheap:
1. `/.well-known/mcp/server-card.json` (SEP-1649 shape) — rich metadata, link to `mcp_endpoint`.
2. `/.well-known/mcp` (SEP-1960 shape) — endpoint + auth info.
3. `/AGENTS.md` at site root — prose instructions: "this is a wiki host, here's how to sign up, here's where the API is, here's llms.txt, here's the MCP server URL."
4. Existing OpenAPI at `/openapi.json` with a clear link from llms.txt.
5. Link all of these from `/llms.txt`.

**Unsettled/controversial.** (a) Whether capability discovery should be *in* MCP's domain or a separate protocol. (b) Whether agents should trust a site's self-declared capability list at all (risk of prompt injection via tool descriptions). (c) Whether the manifest should live at `/.well-known/` or be an HTTP response header. Current vibe: `.well-known` wins because it's cacheable and doesn't need per-request logic.

**URLs.**
- https://github.com/modelcontextprotocol/modelcontextprotocol/discussions/1147 — SEP discussion
- https://www.ekamoira.com/blog/mcp-server-discovery-implement-well-known-mcp-json-2026-guide — implementation guide
- https://global-chat.io/discovery-landscape — "State of Agent Discovery Q1 2026"
- https://agents.md/ — AGENTS.md standard
- https://jsonagents.org/getting-started/ — the competing PAM manifest
- https://developers.openai.com/codex/guides/agents-md — OpenAI Codex AGENTS.md adoption

---

## 5. Agent-friendly rendering conventions

**State of the art.** Content negotiation via `Accept: text/markdown` is the winning pattern of 2026. This is the single most important section of this brief — if you only do one thing, do this.

**Established as of Q1 2026:**
- **Vercel** confirmed (Feb 2026) that Claude Code and OpenCode send `Accept: text/markdown` on every fetch. Vercel now responds with markdown automatically on matching routes.
- **Cloudflare Markdown for Agents** is a zone-level feature that auto-converts HTML→markdown on the edge when the client sends `Accept: text/markdown`. Same URL, different representation. Available Pro/Biz/Enterprise.
- **Mintlify** serves per-page markdown via both content negotiation and `.md` suffix fallback.
- **Measured wins**: Cloudflare's internal measurement shows ~80% token reduction (16k → 3k tokens on a typical article). One Eleventy write-up reported 99.6% size reduction on very HTML-heavy pages.

**The URL-rewriting pattern** (r.jina.ai, deepwiki.com).
- `r.jina.ai/<url>` — prepend to any URL, get clean markdown. Agent-oblivious sites get "agentified" for free.
- `deepwiki.com/<github-path>` — auto-generated wiki view of any public GitHub repo. Used by agents as a pre-rendered summary layer.
- Emerging informal norm: in agent prompts, swap `github.com` → `deepwiki.com` and swap arbitrary URLs → `r.jina.ai/<url>` before fetching. This is a *client-side* convention, not a server one, but it exists because most sites don't serve markdown themselves.
- **Implication for a new site**: serve markdown natively and this whole indirection layer disappears. You are the authoritative agent view.

**JSON-LD / schema.org.** Still useful for structured facts (author, datePublished, license) that markdown doesn't express cleanly. Continue emitting it — LLMs do consume it, even if they prefer markdown prose.

**What "good" looks like for a wiki host.**
1. Every item URL responds to `Accept: text/markdown` with the raw item markdown + frontmatter. Zero HTML.
2. Every item URL also serves at `<url>.md` as a fallback (for clients that don't negotiate). Cheap and bulletproof.
3. HTML version includes JSON-LD with `@type: Article`, author, dates, license.
4. `Link: <...>; rel="alternate"; type="text/markdown"` header on HTML responses — formally declares the markdown alt.
5. Don't gzip markdown responses differently than HTML; agents handle both fine but HTTP caches are cleaner if you match your HTML path.
6. `Vary: Accept` header on all content routes so caches don't mix HTML and markdown.

**Unsettled/controversial.** (a) Whether to also honor `Accept: application/json` with a schema.org-shaped response. Some sites do; it adds maintenance. (b) Whether markdown should be "the authored source" or a derived view. For a wiki host, markdown IS the source — trivial. (c) Some argue for `Accept: text/x-markdown` or a `profile` parameter; the pragmatic consensus is plain `text/markdown`.

**URLs.**
- https://blog.cloudflare.com/markdown-for-agents/ — the canonical 2026 write-up
- https://vercel.com/blog/making-agent-friendly-pages-with-content-negotiation — Vercel's rollout
- https://www.checklyhq.com/blog/state-of-ai-agent-content-negotation/ — Feb 2026 state-of-the-art
- https://github.com/jina-ai/reader — r.jina.ai Reader, the universal fallback
- https://www.mintlify.com/blog/context-for-agents — llms.txt + negotiation together

---

## 6. Session/identity for agents

**State of the art.** Still forming. No "agent identity" standard has shipped. What exists:

- **RFC 8693 Token Exchange** — the formal primitive for "act on behalf of." Enterprise IAM supports it. Consumer tooling mostly doesn't.
- **Anthropic's position (Feb 2026)** — explicitly prohibits using Claude Free/Pro/Max OAuth tokens in third-party products. Developers must use API keys from Console. Translation: Anthropic is *not* shipping a consumer agent-identity layer and is actively rejecting the idea of "delegate my Claude account." This is a significant signal — it pushes the industry toward the per-site PAT model rather than a universal agent identity.
- **Signed agent assertions** — no live standard. Some drafts propose signed JWTs where the agent's public key is registered at a well-known endpoint, then the agent signs each request. Not adopted.
- **PAT vs delegation token distinction.** PAT = long-lived, user-scoped, coarse, all-or-nothing. Delegation token = short-lived, carries both subject and actor IDs, scoped to specific actions, audit-friendly. For a wiki host the pragmatic call is: ship PATs now, add a `POST /api/v1/delegation` endpoint later that mints short-lived scoped tokens from a PAT.

**What "good" looks like in April 2026.** Accept that agent identity is an open problem and design so you can add it later:
1. Ship user-scoped PATs as the default agent credential.
2. Log a soft `X-Agent-Name` / `X-Agent-Version` header on every API call. Don't enforce it, but surface it in the user's dashboard ("this key was used by `claude-code@1.2.3`"). Users love this.
3. Put an `actor` field in your audit log from day one, even if it's always null now. When RFC 8693 becomes mainstream you'll have the schema already.
4. Per-key scopes (`read`, `write`, `admin`) even if you ship with only one scope. You'll want them.
5. Per-key rate limits distinct from per-user limits.

**Unsettled/controversial.** (a) Whether the agent's identity should be visible to other users ("edited by alice via claude-code") — privacy vs. transparency tension. Recommend opt-in visibility. (b) Whether to let users create a "shared agent identity" that multiple humans can delegate to — the multi-human-one-agent case is messy and mostly unsolved.

**URLs.**
- https://datatracker.ietf.org/doc/html/rfc8693 — the primitive
- https://developer.cyberark.com/blog/zero-trust-for-ai-agents-delegation-identity-and-access-control/ — practical delegation patterns
- https://www.biometricupdate.com/202603/ai-agent-identity-and-next-gen-enterprise-authentication-prominent-at-rsac-2026 — RSAC 2026 roundup
- https://medium.com/@em.mcconnell/the-missing-piece-in-anthropics-ecosystem-third-party-oauth-ccb5addb8810 — the Anthropic OAuth restriction story
- https://nango.dev/blog/guide-to-secure-ai-agent-api-authentication — 2026 end-to-end guide

---

## 7. Directories, scenes, and voices

**The loudest voices on "agent-first web" in early 2026.**
- **Patrick Brosset** (ex-Microsoft Edge, WebMCP co-spec author) — most credible technical voice on WebMCP. https://patrickbrosset.com/
- **Alex Nahas** (Arcade.dev) — pragmatic WebMCP/tool-calling commentary. https://www.arcade.dev/blog/
- **Cloudflare blog** (Markdown for Agents, robots.txt for AI) — de facto infrastructure voice.
- **Mintlify blog** — docs-sector voice for llms.txt + content negotiation.
- **Vercel blog** — "agent-friendly pages" post is becoming the canonical "how we retrofitted" story.
- **David Dias** — runs llmstxthub, best neutral curator of llms.txt ecosystem.
- **Rob Manson** (Medium, "Re-defining the Agentic Web", Feb 2026) — the "everyone's building the wrong thing" contrarian.
- **IEEE Spectrum "The Agentic Web"** — the mainstream-press framing.

**Manifestos worth skimming.**
- https://unanimoustech.com/web-development-manifesto-2026/ — "2026 Web Development Manifesto"
- https://dev.to/xh1m/the-architects-manifesto-2026-engineering-in-the-age-of-autonomy-54dc — "Architect's Manifesto 2026"
- https://www.nxcode.io/resources/news/agentic-web-agents-md-mcp-a2a-web-4-guide-2026 — best single synthesis of AGENTS.md + MCP + A2A
- https://medium.com/data-science-collective/re-defining-the-agentic-web-cfeb49e0d4e7 — the skeptic's take
- https://spectrum.ieee.org/agentic-web — the IEEE Spectrum overview

**Standards bodies active in the space.**
- **W3C Web Machine Learning CG** — owns WebMCP draft. Most legitimate standards venue in the space.
- **Anthropic MCP governance** — the SEP process, GitHub-hosted, not a standards body but functionally setting norms.
- **IETF** — 10+ agent-discovery drafts, all early, none adopted. Don't design against any of them.
- **OpenAI** — no standards push post-ai-plugin.json except their AGENTS.md adoption.
- **Google** — pushing A2A (Agent-to-Agent) as a sibling to MCP; not directly relevant to a wiki host.

**Directories to register in when launching.**
- https://llmstxthub.com/ — for llms.txt compliance (~900 sites)
- https://mcp.so/ and https://smithery.ai/ — MCP server directories (primary)
- https://mcpservers.org/ — claims 20k, lower-quality
- https://github.com/thedaviddias/llms-txt-hub — source-of-truth for llmstxthub
- https://agents.md/ registry — AGENTS.md adopters list

---

## Recommended minimum for ListHub's new wiki host (action list)

Ordered by leverage-per-hour. Every item maps to a section above.

1. **Content negotiation on every item URL.** `Accept: text/markdown` → raw markdown. Also `<url>.md` suffix fallback. `Vary: Accept` and `Link: rel=alternate`. *(§5)* This is the highest-leverage item on the list.
2. **`/llms.txt` + `/llms-full.txt`** auto-generated from the item store. Curated top-level, optional section for long tail. *(§2)*
3. **`/AGENTS.md` at site root** explaining signup, API, MCP, llms.txt. Prose, short, link-heavy. *(§4)*
4. **`/.well-known/mcp/server-card.json`** and **`/.well-known/mcp`**. Ship both SEP shapes; they're cheap and they future-proof you. *(§4)*
5. **Server-hosted MCP server** wrapping the existing REST API. Tools: `search`, `read_item`, `create_item`, `update_item`, `tag_item`, `list_items_by_user`. *(§1, §4)*
6. **Signup endpoint that returns an API key**, email optional, PoW fallback to captcha, `X-Agent-Name` soft header logged. *(§3)*
7. **WebMCP tool registration** on item edit pages: `read_page`, `edit_page`, `append_section`, `add_tag`. Ship behind feature-detect. *(§1)*
8. **Per-API-key scopes + per-key rate limits + `actor` column in audit log**. Even if unused today. *(§3, §6)*
9. **Delegation endpoint (`POST /api/v1/delegation`)** that mints short-lived scoped tokens from a PAT. Ship the shell now, the semantics can evolve. *(§6)*
10. **Register in llmstxthub, mcp.so, Smithery** at launch. *(§7)*

---

## What I verified and what I couldn't

Verified:
- All section-level claims are backed by live Q1 2026 search results (searches run 2026-04-08 in this session).
- Existing ListHub research (`../llm-wiki-research.md`, `../llm-wikis-catalog.md`) was checked and reused for llms.txt adopter lists and MCP-wiki peer list — not re-derived.
- URLs listed were all returned by WebSearch; I did not individually WebFetch each to confirm status codes.

Not verified / gaps:
- I did **not** confirm Chrome 146 WebMCP flag behavior on a real browser. The source is a Chrome developer blog post summary.
- SEP-1649/SEP-1960 exact field schemas — I have the shape, not line-by-line spec. Before implementing, read the GitHub discussion directly (link in §4).
- Cloudflare Markdown for Agents pricing/tier details — I have "Pro/Biz/Enterprise" from one source; verify on Cloudflare's pricing page before committing.
- Exact current count of llms.txt adopters — cited figures (900, 780, 13k) come from different directories with different inclusion criteria; none are authoritative.
- Anthropic's Feb 2026 OAuth policy — I have it from a Medium post and a GitHub issue, not from the Anthropic policy page itself. Confirm before citing externally.
- WebAuthn-for-agents is described as "consensus" — it's consensus *among security vendors and RSAC speakers*, not a formal W3C position.

If you want, next step is to WebFetch the top 3-5 spec sources directly (WebMCP draft, SEP-1649/1960 discussion, llms.txt spec, Cloudflare Markdown for Agents post) and pull exact schemas/field names into a second, implementation-ready doc.
