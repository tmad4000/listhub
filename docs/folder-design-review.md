# Folder Design Review (Option 3: "Folders as Items")

Date: 2026-02-11

Files reviewed:
- `CLAUDE.md`
- `db.py`
- `models.py`
- `api.py`
- `views.py`
- `git_sync.py`
- Additional relevant sync touchpoint: `hooks/post-receive`

## Executive Summary

Option 3 is directionally correct for ListHub's future graph model (folders as nodes + containment edges), but it conflicts with several assumptions in the current implementation:
- `item_type` currently excludes `folder` in API validation (`api.py:147`, `api.py:199`, `api.py:463`, `api.py:505`) and in push ingest (`hooks/post-receive:182`).
- Tree/UI rendering is currently derived from `file_path` prefixes, not DB relationships (`views.py:16`, `views.py:20`).
- Git sync writes one markdown file per item and treats path as item-local metadata (`git_sync.py:123`, `git_sync.py:253`), with no notion of parent graph.
- Visibility/share checks are item-local and non-recursive (`views.py:379`, `views.py:385`, `api.py:391`).

Recommendation: proceed with Option 3, but do it in phases and choose strict inheritance first (Option **a**) for implementation safety. If you want override behavior, introduce it after the tree + ACL model is stable.

---

## 1) Does this design make sense in the existing architecture?

Yes, conceptually. It aligns with the "flat now, graph later" direction in `CLAUDE.md:79`.

But there are concrete conflicts/complications:

1. `item_type` hardcoded enum conflicts
- API allows only `note|list|document` (`api.py:147`, `api.py:199`, `api.py:463`, `api.py:505`).
- Hook normalizes unknown types back to `note` (`hooks/post-receive:182`, `hooks/post-receive:183`).
- Folder item pushes would silently lose type unless hook/API both change.

2. Current folder UX is virtual, path-based
- Dashboard/profile folder trees are computed from `file_path` string splitting (`views.py:16`-`views.py:47`).
- No DB parent relation is used today.
- Introducing `parent_id` means this code should be replaced with relationship traversal, or at least fed from canonical DB-derived paths.

3. Slug uniqueness is global per owner
- DB enforces `UNIQUE(owner_id, slug)` (`db.py:51`).
- That blocks common folder behavior like `recipes/index` and `projects/index` both using slug `index`.
- If you relax this, routes and APIs that key by slug break (`api.py:420`, `api.py:436`, `api.py:543`, `views.py:363`).

4. Visibility and share are item-local, not inherited
- Public/shared access in UI checks only the current item (`views.py:379`, `views.py:385`).
- Share table is keyed by `item_id` only (`db.py:68`), and API share endpoints mutate only one item (`api.py:368`-`api.py:417`).
- Folder inheritance needs recursive checks and/or denormalization.

5. Git path management is per-item and mostly write-only
- Sync uses `item.file_path` if present (`git_sync.py:123`, `git_sync.py:253`).
- Item updates do not currently update `file_path` when slug changes, so path can drift.
- Folder moves/renames require recomputing descendant paths and removing old paths; current incremental sync cannot do that atomically.

6. Parent constraint requires more than FK
- `parent_id REFERENCES item(id)` is easy, but "parent must be folder" requires trigger logic (not just FK).
- You also need cycle prevention (no folder can become its own ancestor).

Conclusion: design is sound, but it is not a small patch. It is a cross-cutting schema + API + access-control + sync change.

---

## 2) Visibility inheritance model recommendation

### Recommended now: **(a) children inherit and cannot override**

Why this is best for current codebase:
- Existing read paths are simple and item-local. Non-overridable inheritance can be materialized onto descendants during create/move/update, keeping queries straightforward.
- It avoids ACL-subset complexity for `shared`.
- It minimizes accidental overexposure risk.

If you must support overrides, choose **(b)** (only more restrictive), never (c). But (b) requires non-trivial ACL math for shared items.

### Practical rule set for option (a)

- Effective visibility of child is exactly parent visibility.
- Folder visibility update cascades to all descendants.
- Child visibility field becomes either:
  - removed/ignored for non-folder items, or
  - retained but forced to match inherited value.

This can later evolve toward (b) by adding explicit `visibility_override` semantics.

---

## 3) What changes are needed in `git_sync.py`?

Core changes:

1. Compute canonical path from folder ancestry, not from arbitrary stored `file_path`
- Today path comes from `item.file_path` (`git_sync.py:123`, `git_sync.py:253`).
- For folder-as-item, path should be derived from parent chain + slug.

2. Define folder representation in git
- Git cannot store empty directories.
- If folder items have content/description, map folder item to `<folder_path>/index.md`.
- If folder has no content and no children, either:
  - skip writing it to git, or
  - write a placeholder (e.g., `.keep`) (less ideal for markdown-first workflow).

3. Handle moves/renames as path rewrites
- Parent change or slug change must rewrite descendant paths.
- Incremental `sync_item_to_repo()` currently writes one file (`git_sync.py:110`-`git_sync.py:165`).
- For folder moves, either:
  - sync subtree + remove old subtree paths, or
  - fallback to `sync_user_repo()` for correctness.

4. Orphan cleanup semantics
- Full sync already removes orphaned `.md` files (`git_sync.py:268`-`git_sync.py:277`), which is useful for folder moves if using full sync.

5. Frontmatter updates
- Include `item_type: folder` support in serializer (`git_sync.py:73`) and ensure parser side supports it (`hooks/post-receive:178`-`hooks/post-receive:183`).

Important side-effect:
- `hooks/post-receive` currently identifies existing items by slug only (`hooks/post-receive:148`, `hooks/post-receive:163`).
- With folder paths and possible duplicate slugs, this must switch to a stable ID in frontmatter (recommended) or path-based identity.

---

## 4) How should `share` interact with folder sharing?

Short answer: yes, folder sharing should grant access to descendants.

Recommended model:
- Folder share grants inherited read/edit rights to descendants.
- Direct child share can further restrict, not broaden (if you later allow overrides).
- Do **not** eagerly copy folder shares to every descendant row; compute effective access from ancestor chain.

Why:
- Copying ACL rows recursively is fragile under moves/renames and expensive for deep trees.
- Current `share` schema (`db.py:68`) can still be used as explicit ACL entries at nodes.

What must change immediately:
- Read authorization for shared items currently checks only direct item share (`views.py:385`-`views.py:389`).
- Replace with ancestor-aware ACL resolution.

Schema note:
- `share.shared_with` is free text (`db.py:70`) and sometimes compared to user id or email (`views.py:387`).
- Folder-level ACL will be cleaner if principals are normalized (e.g., user_id + optional email invite table).

---

## 5) API changes needed

### Existing endpoints to change

1. `POST /api/v1/items/new` (`api.py:181`)
- Accept `item_type="folder"`.
- Accept `parent_id`.
- Enforce parent exists, same owner, and parent is folder.
- Enforce inheritance policy at create time.

2. `PUT /api/v1/items/<id>` (`api.py:113`)
- Accept `parent_id` (move operation).
- Validate no cycles.
- If folder moved/renamed, trigger subtree path recalculation and sync strategy.

3. `GET /api/v1/items` (`api.py:41`)
- Add optional tree-aware filters: `parent_id`, `root=true`, `recursive=true`.
- Return `parent_id`, and ideally `effective_visibility`.

4. Delete endpoints (`api.py:290`, `api.py:543`)
- Define behavior for deleting folders: recursive delete vs reject if non-empty.

5. Share endpoints (`api.py:368`, `api.py:402`)
- Add folder-aware semantics; either:
  - inherited ACL resolution only, or
  - explicit cascade mode for legacy clients.

### New endpoints recommended

- `POST /api/v1/folders` (or `POST /api/v1/items` if you unify create style)
- `GET /api/v1/items/<id>/children`
- `POST /api/v1/items/<id>/move` (parent change)
- `GET /api/v1/tree` (single call for nested structure)
- `POST /api/v1/items/<id>/share/inherited` (optional explicit policy endpoint)

Documentation reminder: API docs must be updated (`CLAUDE.md:91`).

---

## 6) Simpler alternatives

1. Keep DB flat; improve `file_path` first (lowest risk)
- Treat `file_path` as canonical path with stronger validation and move/rename endpoints.
- Keep virtual folder tree in UI.
- Pros: minimal schema churn.
- Cons: does not advance graph-node model much.

2. Add dedicated `folder` table (middle ground)
- `folder(id, owner_id, name, parent_folder_id, visibility)` + `item.folder_id`.
- Pros: cleaner constraints than polymorphic `item_type`.
- Cons: less "pure graph" than folders-as-items.

3. Option 3 in two phases (recommended path)
- Phase 1: add `parent_id`, `item_type=folder`, strict inheritance, keep global slug uniqueness.
- Phase 2: reconsider slug uniqueness/path routes and richer ACL overrides.

---

## 7) Migration concerns for existing data

1. Schema migration
- Add `parent_id` to `item` (nullable self-FK).
- Add indexes on `(owner_id, parent_id)` and maybe `(owner_id, item_type)`.
- Add triggers for:
  - parent must be folder,
  - same owner parent-child,
  - cycle prevention.

2. Backfill folder nodes from `file_path`
- For each item's current path (`db.py:45`), create missing folder items for path prefixes.
- Set each non-folder item's `parent_id` to deepest folder prefix.

3. Slug/path conflicts
- Decide now whether same slug in different folders is allowed.
- If yes, replace unique constraint `UNIQUE(owner_id, slug)` (`db.py:51`) and update slug-based APIs/routes (`api.py:420`, `views.py:363`).

4. Git re-sync
- After migration, run full user sync (`git_sync.py` CLI) so repos reflect folder/index model.
- Expect path churn commits.

5. Hook compatibility
- Update `hooks/post-receive` to understand folder types and parent context.
- Current slug-only matching (`hooks/post-receive:163`) is unsafe if slug uniqueness is relaxed.

6. Access control migration
- Existing `share` rows are direct-item only.
- Define whether they remain direct ACL entries or become inherited roots.
- Re-test public/shared pages (`views.py:68`, `views.py:94`, `views.py:363`) under new effective-visibility rules.

7. UI behavior
- Replace `build_folder_tree()` path-splitting (`views.py:16`) with tree from parent links.
- Decide folder item rendering (index content vs synthetic folder page).

---

## Concrete implementation order (recommended)

1. Add schema + constraints (`parent_id`, folder type support, indexes/triggers).
2. Update API validators and payloads for `folder` and `parent_id`.
3. Implement strict inherited visibility (option a) with recursive propagation on move/update.
4. Update git sync to derive paths from parent chain and write folder `index.md`.
5. Migrate existing data (`file_path` -> folder items + parent links), then full git sync.
6. Update web views/tree rendering to consume parent-based hierarchy.
7. Update post-receive hook identity strategy (prefer stable `id` in frontmatter).
8. Update `/api/docs` template.

This sequence minimizes broken intermediate states and keeps git mirror correctness as an invariant.
