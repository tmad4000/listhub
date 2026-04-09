
  1. Repo-per-user, not repo-per-wiki. Direct quote: "I like the idea of separate git repos for each user, because
  that's how people are naturally handling obsidian vaults. It's their own git repo or their agent memory. ... It's a
  repo per user." This contradicts my v1 spec (repo-per-wiki). Big fork — I'll ask below.
  2. Unstructured-text → wiki is the viral hook, not a v2 nice-to-have. The user story: "I have a Google Doc /
  arbitrary scrap rambles / text conversation" → wikihub. Paired with a broader "omni-convert any file" pattern (PDF,
  DOCX, .txt, even video transcripts): upload anything, we markdown-ize and commit.
  3. Cloud agent — a shared headless Claude Code in print mode, sandboxed per-user via UNIX permissions on a per-user
  folder. "Cortex might be overkill, just spin up a docker container, or even simpler: one process with per-user
  folder sandbox." Explicitly: "a cloud-based interface where you can just talk to an agent we host instead of one
  that you host ... especially nice on mobile."
  4. Per-section privacy inside a page via HTML comments. <!-- private -->...<!-- /private --> stripped out of the
  rendered public view but kept in the raw git blob. Micro-feature, but it's the bridge between per-file ACLs and the
  messy real-world case of a mostly-public wiki with a couple of spicy sentences.
  5. git-crypt escape hatch for encrypted content on otherwise public wikis. Reference: jacobcole.net/labs. Probably
  not v1, but the architecture shouldn't preclude it (keep the raw blob flow transparent — don't re-encode markdown
  server-side).
  6. Omnisearch with Cmd+K. Global + local, fuzzy across filenames and content. Listhub's current FTS is per-page;
  wikihub needs it cross-wiki from day one.
  7. Anthropic / Boris is the first-user target. "They need a markdown reader; we want them using wikihub." This
  shapes v1: the reader view has to look good to a technical ML reader on day one. It also subtly argues for the
  repo-per-user model (that's how Boris would think about his own notes).
  8. Featured / community curation on the homepage. /explore is not just "recent" — it's a curated slot.
  9. Migration targets queued up: admitsphere, RSI wiki, systematic altruism wiki (currently on Google Sites), Jacob's
   CRM. We get 3-5 real wikis on wikihub in the first week without needing a marketing plan. This is the dogfood loop.
  10. Timeline is 1 week to viral-MVP. Window-closing language is consistent across both transcripts. This hard-caps
  v1 scope — anything not on the critical path to "post on HN, Karpathy retweets" gets deferred.
  11. Three build options debated → from-scratch wins. DokuWiki was floated and rejected (not markdown, PHP).
  Quartz-clone floated and deprioritized. Extend-listhub deprioritized. From-scratch is locked.
  12. Wikilink autocomplete [[...]] in the editor is a listed gap.
  13. FTP got mentioned as a desired upload path. Skeptical — git push covers it and FTP is a lot of surface for one
  user story. Flagging for veto.
  14. "Google Drive vibes" — ACLs, per-file visibility, share-with-user, view/edit/comment/admin, link-sharing,
  unlisted. This is now a v1 requirement per the direct instruction. Full design below.
