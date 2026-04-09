(repo-per-wiki). Big fork — I'll ask below.
v2 nice-to-have. The user story: "I have a Google Doc /
  arbitrary scrap rambles / text conversation" → wikihub. Paired with a broader "omni-convert any file" pattern (PDF,
  DOCX, .txt, even video transcripts): upload anything, we markdown-ize and commit.
  3. Cloud agent — a shared headless Claude Code in print mode, sandboxed per-user via UNIX permissions on a per-user
  folder. "Cortex might be overkill, just spin up a docker container, or even simpler: one process with per-user
  folder sandbox." Explicitly: "a cloud-based interface where you can just talk to an agent we host instead of one
  that you host ... especially nice on mobile." (v3)


	
  4. Per-section privacy inside a page via HTML comments. <!-- private -->...<!-- /private --> stripped out of the
  rendered public view but kept in the raw git blob. Micro-feature, but it's the bridge between per-file ACLs and the  messy real-world case of a mostly-public wiki with a couple of spicy sentences.
  5. (v3) git-crypt escape hatch for encrypted content on otherwise public wikis. Reference: jacobcole.net/labs. Probably
  not v1, but the architecture shouldn't preclude it (keep the raw blob flow transparent — don't re-encode markdown
  server-side).
  6. Omnisearch with Cmd+K. Global + local, fuzzy across filenames and content. Listhub's current FTS is per-page;
  wikihub needs it cross-wiki from day one.
  
	
	8. Featured / community curation on the homepage. /explore is not just "recent" — it's a curated slot. There should also be recent accessible from the homepage somehow, but featured is an important thing.

9. Migration targets queued up: admitsphere, RSI wiki, systematic altruism wiki (currently on Google Sites), Jacob's
   CRM. We get 3-5 real wikis on wikihub in the first week without needing a marketing plan. This is the dogfood loop.

10. Timeline is 1 week to viral-MVP. Window-closing language is consistent across both transcripts. This hard-caps
  v1 scope — anything not on the critical path to "post on HN, Karpathy retweets" gets deferred.Also your time estimates as a coding agent are frequently incorrect. You often think things will take a week or a month, but it really is fast for coding agents, so please don't get tripped up by this instruction.

  12. Wikilink autocomplete [[...]] in the editor is a listed gap.
  13. FTP got mentioned as a desired upload path. Skeptical — git push covers it and FTP is a lot of surface for one
  user story. Flagging for veto. (v2)
  14. "Google Drive vibes" — ACLs, per-file visibility, share-with-user, view/edit/comment/admin, link-sharing,
  unlisted. This is now a v1 requirement per the direct instruction. 

Another thing that we need to make sure to be building for in the future is the ability to share files with specific people and even share wikis with specific people like Google Drive and possibly having an idea of a friends list or multiple friends lists like Facebook where you can make files that you share just with friends. I just want to make sure our architecture doesn't preclude that. Also we need to be able to support unlisted but public view and also public edit files like Google Drive and every one of those variants.

use wikihub as the name; I just pasted you a bunch of transcripts that I was talking about this project with a friend. Parse through them and get the best ideas, so half of it should probably not be relevant, but get the most important ideas and then review them with us. Send some more forks, ask us some questions about them, get clear intent. Additionally, separate from the above, this is a direct instruction to you, Mr. AI. We want to build into this architecture the ability to share arbitrary wikis. We have an access control list for them, like users that can access them. We also want to, for every file, have that. It's like Google Drive vibes. And also, there should be the idea of an unlisted file that's public, and public edit, private permissions, all the different permissions. Longer term, though, this doesn't have to be in version one. We're going to want to have some kind of good collaborative editing, but we don't need to bias towards real-time immediately yet. Creating tasks also use the continue like the research brief and continue giving our output on that, and continue looking at that and integrating that into the spec, but mostly tell us the output just like you were before I hit escape, and then also at this stage we really want to formalizing this the spec; we don't want to be implementing.



consider anthropic intranet as potential future target user (llm wikis for companies) :
---

7. Anthropic / Boris is the first-user target. "They need a markdown reader; we want them using wikihub." This
  shapes v1: the reader view has to look good to a technical ML reader on day one. It also subtly argues for the
  repo-per-user model (that's how Boris would think about his own notes).
  
	---

