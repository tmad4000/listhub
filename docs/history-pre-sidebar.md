# ListHub History — Pre-Sidebar Checkpoint

This document marks the state of ListHub **before** the three-section persistent sidebar is added (the Notion/Workflowy/Google-Sites style navigation overhaul planned in early April 2026).

## Checkpoint video

**[Loom: State of ListHub before sidebar, April 2026](https://www.loom.com/share/90b46940568a459480e3e00384907749)**

Jacob recorded this walkthrough of the site as it looked before the sidebar navigation was introduced. Keep it as a reference for what the UX used to feel like, especially once the new sidebar lands and the old navigation paradigm fades from memory.

## Context: why the sidebar is coming

The sidebar is inspired by several related wiki-style tools:

### Google Sites (what Jacob currently uses)
- **admitsphere.org** → redirects to `sites.google.com/view/admitsphere/` — college admissions resource with hierarchical menu (Prime Directive, Standardized Test Prep, College Sample Essays by school, High School, Resources, Paying for College). Expandable sub-sections for each major university. Originally ran on Wikispaces.
- **rsiwiki.jacobcole.net** → redirects to `sites.google.com/view/rsi-wiki/home` — RSI resource with left sidebar (Home, Tools and Tricks, Recovery Stories, Setup, Reflection, Arms/Hands/Shoulders, Computer sub-menu with Dragon/Macros, Resources).

Both use Google Sites' left-sidebar navigation model: a hierarchical tree of pages, expandable sections, consistent across every page of the site.

### Wikispaces (the predecessor)
- Shut down 2018. admitsphere.org originally ran there.
- Same basic model: left sidebar with a page tree, edit-in-place wiki pages.

### Notion / Workflowy / Obsidian (the modern successors)
- All have persistent left-side hierarchical navigation.
- Notion: one workspace tree per account.
- Obsidian: vault file tree.
- Workflowy: single outline tree.

### The gap ListHub fills
**No existing tool combines** hierarchical sidebar navigation + agent-settable per-item visibility + git-backed markdown + public-URL-per-item. Google Sites has the sidebar but no agent API. Notion has the nav but no per-item publish-at-write-time. Obsidian has the vault but no multi-user publishing.

## Sub-wiki concept

In the long term, sites like admitsphere.org and rsiwiki.jacobcole.net could each be a **sub-wiki inside ListHub**:
- `/@jacobreal/admitsphere/` — the admissions sub-wiki with its own folder hierarchy, its own landing page, its own style
- `/@jacobreal/rsi-wiki/` — the RSI resource with its own navigation
- Each sub-wiki is just a folder at the top of a user's item tree with `item_type: "wiki"` or similar
- The sidebar shows sub-wikis as top-level expandable sections within "Your docs"
- A sub-wiki can be made entirely public (wiki) while the rest of a user's items stay private

This means ListHub doesn't just replace Google Drive or Obsidian — it's the backend for your personal knowledge AND the backend for every wiki-style site you want to publish. One nav model, many publishing surfaces.

For V1, we don't need to build special "sub-wiki" features — a folder that happens to be entirely public with a thoughtful `index.md` IS a sub-wiki. The sidebar treats it like any other folder.

## Sequencing

1. **First**: add the three-section sidebar (Your docs / Community / Focused @user) **on top of** the current navigation, not replacing it. See how it feels with real content.
2. **Then**: once the sidebar carries the navigation weight, prune the older dashboard/profile/explore navigation where it duplicates sidebar functionality.
3. **Later**: consider sub-wiki features like per-folder landing pages, custom styling, and migration tools for importing Google Sites exports.

## Related tickets

- (pending) Add persistent 3-section sidebar — the main navigation overhaul
- `listhub-hon` — LLM Wiki Book on ListHub (different but overlapping: directory of wikis vs. hosting wikis)
- `listhub-4jm` — Multi-sheet CSV support
- `listhub-xtc` epic — GitHub-like repo UX
- (pending) Sub-wiki concept: host legacy Google Sites content on ListHub
- (pending) Google Sites export importer
