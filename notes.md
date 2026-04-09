
agreed with all these and all yours v1 improvements in general "  v1 — should be added to the spec before implementation". only one that we need to chat about is "
  6. .folder.yaml / per-folder metadata (subset of listhub-r62.1). listhub explored "frontmatter for markdown, .meta.yaml sidecar for binaries, .folder.yaml for folders." Our .wikihub/acl glob-pattern file handles all three
in one
  place, so we don't need the three-file pattern. But there's one thing the folder file handles that globs don't cleanly: folder-scoped defaults for NON-ACL metadata — e.g., "every file in raw/ has source_type: primary" or "
every
  file in wiki/entities/ has category: entity." Not an ACL concern; a content metadata concern. Frontmatter handles it per-file; globs handle it at the ACL layer; but neither cleanly handles "folder default frontmatter that
files
  can override." Flagging as a design question: do we want folder-default frontmatter? If yes, it's a small extension (.wikihub/defaults.yaml with globs)."
	
	
	
If I were updating the handoff/delta docs from this research, the five I'd add to v1 scope as explicit items (not just "considered and deferred"):


  1. Binary file storage decision — add as an explicit open question in the spec's open-questions list. Can't hand-wave it.

  2. Inline image support — both standard markdown and Obsidian ![[]] embed. Add to the renderer stack.
  3. File rename/move REST endpoint — add to the API surface list.

  4. Machine-readable permission error bodies — add to the error-shape convention section.

  5. ZIP download of wiki (filtered for non-owners) — add to the social layer or ingestion section. One endpoint, high-value UX, perfectly matches the public-mirror architecture.



  Four more I'd add as explicit v1 refinements (small but shouldn't be forgotten):

  - Tag index pages (/@user/wiki/tag/:name)

  - Search-or-create in Cmd+K when zero hits

  - External links open in new tab
  - Visibility labels as public (read) / public (edit) etc. in the UI




---

1. Regarding the binary file thing, I think the conclusion we do in the other project is that obsidian just includes images, attachment, binary files, etc. right in the repository we're not worried about giant binary files for version one is that ok . We can consider an external file store like an S3 bucket. We actually already have one on globalbr.ai as an alternative option in the future. Is that what you are saying with:  I'd push for in-repo as default, quota-gated (maybe 50MB total binaries per wiki in v1) with a clear path to LFS or object store when a wiki outgrows that. But the decision has to be made, not hand-waved. Add to spec as an open
  question.
	
	
	
  6. Regarding this one, I'm guessing it's not that important actually but one thing that I do want to consider is being able to put an index file in a folder like quartz wiki does.."folder.yaml / per-folder metadata (subset of listhub-r62.1). listhub explored "frontmatter for markdown, .meta.yaml sidecar for binaries, .folder.yaml for folders." Our .wikihub/acl glob-pattern file handles all three in one
  place, so we don't need the three-file pattern. But there's one thing the folder file handles that globs don't cleanly: folder-scoped defaults for NON-ACL metadata — e.g., "every file in raw/ has source_type: primary" or "every
  file in wiki/entities/ has category: entity." Not an ACL concern; a content metadata concern. Frontmatter handles it per-file; globs handle it at the ACL layer; but neither cleanly handles "folder default frontmatter that files
  can override." Flagging as a design question: do we want folder-default frontmatter? If yes, it's a small extension (.wikihub/defaults.yaml with globs). "
	
	
	
  20. Visibility label consistency (listhub-9nm). listhub learned that public is ambiguous — does it mean "anyone can read" or "anyone can edit"? They're standardizing on public view vs public edit as the human-facing labels.
  Wikihub should display public (read), public (edit), unlisted (read), unlisted (edit) in the UI even though the internal mode names are the shorter forms.

  21. Visibility badges on items (listhub-an8). Every page/wiki card in search results and explore should have a small icon indicating its visibility. Table-stakes UX that the spec didn't call out.
  
	
	lets chat about this
	  23. Milkdown WYSIWYG editor (commit 7569f04). listhub chose Milkdown as its markdown editor. I had proposed a simpler markdown editor for wikihub. Worth reconsidering — Milkdown gives WYSIWYG with round-trip-clean markdown, has
  plugin architecture, and would be a strategic copy from listhub's proven choice. Mentioning as a potential stack upgrade.
	
	
	
  E. "Cascade-by-default-at-creation" (commit 63a1fe5). When a folder is created, files inside it inherit the folder's visibility by default. Wikihub's .wikihub/acl globs give us this for free (wiki/** public cascades), but we
  should confirm that in the scaffold new-page UI, when a user creates a page under an ACL-governed folder, the UI shows the inherited visibility as the default and lets them override.
	
	
	--
	
	let's build w mobile friendly in mind
	
	
	---
	make a mockup first
	