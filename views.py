import os
import re
import subprocess

import markdown
from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import login_required, current_user
from nanoid import generate as nanoid

from db import get_db, reindex_item
from api import slugify, VALID_VISIBILITIES
from git_sync import sync_item_to_repo, remove_from_repo

views_bp = Blueprint('views', __name__)


def build_folder_tree(items_list):
    """Build a nested tree from items based on file_path, then flatten for rendering."""
    root = {'name': '', 'files': [], 'children': {}}
    for item in items_list:
        path = item.get('file_path') or f"{item['slug']}.md"
        parts = path.split('/')
        dirs = parts[:-1]
        node = root
        for d in dirs:
            if d not in node['children']:
                node['children'][d] = {'name': d, 'files': [], 'children': {}}
            node = node['children'][d]
        node['files'].append(item)

    def count_files(node):
        total = len(node['files'])
        for child in node['children'].values():
            total += count_files(child)
        return total

    def collect_visibilities(node):
        s = set()
        for f in node['files']:
            v = f.get('visibility')
            if v:
                s.add(v)
        for child in node['children'].values():
            s |= collect_visibilities(child)
        return s

    def folder_visibility_summary(node):
        vis = collect_visibilities(node)
        if not vis:
            return None
        if len(vis) == 1:
            return next(iter(vis))
        return 'mixed'

    def tree_to_list(node, depth=0, prefix=''):
        result = []
        for name in sorted(node['children'].keys()):
            child = node['children'][name]
            file_count = count_files(child)
            full_path = f"{prefix}{name}" if prefix else name
            result.append({
                'type': 'folder',
                'name': name,
                'depth': depth,
                'count': file_count,
                'path': full_path,
                'visibility_summary': folder_visibility_summary(child),
            })
            result.extend(tree_to_list(child, depth + 1, full_path + '/'))
        for f in node['files']:
            result.append({'type': 'file', 'item': f, 'depth': depth})
        return result

    return tree_to_list(root)


# Private content block pattern:
#   <!-- private --> ... <!-- /private -->
# Content inside these HTML comment markers is stripped from rendered output
# for everyone except the item owner. Non-greedy, DOTALL, case-insensitive.
# See also: /llms.txt and the API docs page for the agent-facing convention.
_PRIVATE_BLOCK_RE = re.compile(
    r'<!--\s*private\s*-->.*?<!--\s*/\s*private\s*-->',
    re.DOTALL | re.IGNORECASE,
)


def strip_private_blocks(text):
    """Remove <!-- private --> ... <!-- /private --> blocks from markdown.

    Used to hide per-section private content when rendering for non-owners.
    The content is only stripped from the rendered view — the raw markdown
    still contains the block, so editing (via the API or web UI) preserves it.
    """
    if not text:
        return text
    return _PRIVATE_BLOCK_RE.sub('', text)


def render_md(text, is_owner=False):
    """Render markdown to HTML. If is_owner is False, strip <!-- private -->
    blocks first so non-owners never see per-section private content."""
    if not is_owner:
        text = strip_private_blocks(text)
    html = markdown.markdown(
        text or '',
        extensions=['tables', 'fenced_code', 'toc', 'nl2br', 'sane_lists']
    )
    # Open external links in new tab
    html = re.sub(
        r'<a\s+href="(https?://[^"]*)"',
        r'<a href="\1" target="_blank" rel="noopener noreferrer"',
        html
    )
    return html




# Cap leaf files per folder rendered in the sidebar tree. Folders are
# always shown in full; truncated files become a 'more' sentinel node
# that the template renders as a link to the folder view. Keeps the
# rendered HTML small for accounts with thousands of items.
MAX_FILES_PER_FOLDER = 100


def _sidebar_build_user_tree_from_items(items):
    """Build a nested sidebar tree from a list of DB item rows.

    Behaviors:
    - The item with slug `home` at the root is hoisted to the top of the
      root listing and marked is_home=True so the template can render it
      with a special icon.
    - Folders get an aggregated `visibility_summary` derived from the
      visibilities of their descendant files (single value if uniform,
      "mixed" if multiple).
    """
    root = {"__files": []}
    for item in items:
        path = (item["file_path"] or f'{item["slug"]}.md').strip("/")
        parts = path.split("/")
        node = root
        for p in parts[:-1]:
            if p not in node:
                node[p] = {"__files": []}
            node = node[p]
        node["__files"].append(dict(item))

    def count_recursive(n):
        c = len(n.get("__files", []))
        for k, v in n.items():
            if k != "__files":
                c += count_recursive(v)
        return c

    def collect_visibilities(n):
        """Gather the set of visibility values for all descendant files."""
        s = set()
        for f in n.get("__files", []):
            v = f.get("visibility")
            if v:
                s.add(v)
        for k, v in n.items():
            if k != "__files":
                s |= collect_visibilities(v)
        return s

    def folder_visibility_summary(n):
        vis_set = collect_visibilities(n)
        if not vis_set:
            return None
        if len(vis_set) == 1:
            return next(iter(vis_set))
        return "mixed"

    def file_node(f, is_home=False):
        return {
            "type": "file",
            "name": f.get("title") or f["slug"],
            "slug": f["slug"],
            "visibility": f["visibility"],
            "item_type": f["item_type"],
            "is_home": is_home,
        }

    def to_nodes(node, prefix=""):
        result = []
        # Hoist root-level `home` slug to the very top
        home_files = []
        other_files = []
        for f in node.get("__files", []):
            if prefix == "" and (f.get("slug") or "").lower() == "home":
                home_files.append(f)
            else:
                other_files.append(f)
        for f in home_files:
            result.append(file_node(f, is_home=True))

        folders = sorted(k for k in node if k != "__files")
        for folder in folders:
            child_path = f"{prefix}{folder}" if prefix else folder
            result.append({
                "type": "folder",
                "name": folder,
                "path": child_path,
                "count": count_recursive(node[folder]),
                "visibility_summary": folder_visibility_summary(node[folder]),
                "children": to_nodes(node[folder], child_path + "/"),
            })
        sorted_files = sorted(
            other_files,
            key=lambda x: ((x.get("title") or x["slug"]) or "").lower(),
        )
        # PERF: cap files per folder to keep the rendered tree small
        # for accounts with thousands of items. Folders are still listed
        # in full so navigation isn't broken; the truncated leaf files
        # become a "more" sentinel that the template renders as a link
        # to the folder view.
        if len(sorted_files) > MAX_FILES_PER_FOLDER:
            for f in sorted_files[:MAX_FILES_PER_FOLDER]:
                result.append(file_node(f))
            result.append({
                "type": "more",
                "count": len(sorted_files) - MAX_FILES_PER_FOLDER,
                "parent_path": prefix.rstrip("/"),
            })
        else:
            for f in sorted_files:
                result.append(file_node(f))
        return result

    return to_nodes(root)


def _sidebar_user_tree(user):
    """Build a nested-dict tree for the sidebar from a user items."""
    if not user:
        return []
    db = get_db()
    items = db.execute(
        "SELECT id, slug, title, file_path, item_type, visibility FROM item WHERE owner_id = ? ORDER BY file_path, slug",
        (user.id,),
    ).fetchall()
    return _sidebar_build_user_tree_from_items(items)


def _sidebar_community_tree():
    """Build a nested sidebar tree from the community directory git repo."""
    repo = _directory_repo()
    if not os.path.isdir(repo):
        return []
    head = _git_read(repo, "rev-parse", "--verify", "HEAD")
    if not head:
        return []
    ls = _git_read(repo, "ls-tree", "-r", "--name-only", "HEAD")
    if not ls:
        return []
    files = [f for f in ls.strip().split("\n") if f and f.endswith(".md")]
    raw = {}
    for fp in files:
        parts = fp.strip().split("/")
        node = raw
        for part in parts[:-1]:
            if part not in node:
                node[part] = {"__files": []}
            node = node[part]
        fn = parts[-1]
        node.setdefault("__files", []).append(fn)

    def count_items(n):
        c = sum(1 for f in n.get("__files", []) if f.endswith(".md"))
        for k, v in n.items():
            if k != "__files":
                c += count_items(v)
        return c

    def to_nodes(node, prefix=""):
        items = []
        folders = sorted(k for k in node if k != "__files" and isinstance(node[k], dict))
        for folder in folders:
            path = f"{prefix}{folder}" if prefix else folder
            child_node = node[folder]
            items.append({
                "type": "folder",
                "name": folder,
                "path": path,
                "count": count_items(child_node),
                "children": to_nodes(child_node, path + "/"),
            })
        # Build list of leaf files (skipping index.md), then cap at MAX_FILES_PER_FOLDER
        leaf_files = [f for f in sorted(node.get("__files", [])) if f != "index.md"]
        if len(leaf_files) > MAX_FILES_PER_FOLDER:
            visible = leaf_files[:MAX_FILES_PER_FOLDER]
        else:
            visible = leaf_files
        for f in visible:
            path = f"{prefix}{f}" if prefix else f
            items.append({
                "type": "file",
                "name": f[:-3] if f.endswith(".md") else f,
                "path": path,
            })
        if len(leaf_files) > MAX_FILES_PER_FOLDER:
            items.append({
                "type": "more",
                "count": len(leaf_files) - MAX_FILES_PER_FOLDER,
                "parent_path": prefix.rstrip("/"),
            })
        return items

    return to_nodes(raw)


def _sidebar_focused_user():
    """Return {username, tree} if the current URL is viewing another user content."""
    from flask import request
    import re as _re
    path = request.path
    m = _re.match(r"^/@([a-zA-Z0-9_-]+)(?:/.*)?$", path)
    if not m:
        return None
    username = m.group(1)
    if current_user.is_authenticated and current_user.username == username:
        return None
    db = get_db()
    from models import User as UserModel
    user = UserModel.get_by_username(db, username)
    if not user:
        return None
    items = db.execute(
        "SELECT id, slug, title, file_path, item_type, visibility FROM item "
        "WHERE owner_id = ? AND visibility IN ('public', 'public_edit') "
        "ORDER BY file_path, slug",
        (user.id,),
    ).fetchall()
    return {"username": username, "tree": _sidebar_build_user_tree_from_items(items)}


# Routes that never render the sidebar - skip the expensive tree build.
# Includes API endpoints, static assets, git smart-http, mockups (static
# HTML files served via send_from_directory), and well-known text files.
SIDEBAR_SKIP_PREFIXES = (
    "/api/",
    "/static/",
    "/git/",
    "/mockups/",
)
SIDEBAR_SKIP_EXACT = {
    "/llms.txt",
    "/robots.txt",
    "/favicon.ico",
}


@views_bp.app_context_processor
def inject_sidebar_data():
    """Inject sidebar tree data into every template render.

    Skips the expensive tree build for routes that never render the
    sidebar (API, static, git, mockups, well-known text files). For
    accounts with thousands of items this saves ~60ms per request, plus
    avoids serializing/sending megabytes of HTML on requests that don't
    use it.
    """
    from flask import request
    path = request.path or ""
    if path in SIDEBAR_SKIP_EXACT or path.startswith(SIDEBAR_SKIP_PREFIXES):
        return {
            "sidebar_your_tree": [],
            "sidebar_community_tree": [],
            "sidebar_focused": None,
            "sidebar_current_username": None,
        }

    try:
        your_tree = _sidebar_user_tree(current_user) if current_user.is_authenticated else []
    except Exception:
        your_tree = []
    try:
        community_tree = _sidebar_community_tree()
    except Exception:
        community_tree = []
    try:
        focused = _sidebar_focused_user()
    except Exception:
        focused = None
    return {
        "sidebar_your_tree": your_tree,
        "sidebar_community_tree": community_tree,
        "sidebar_focused": focused,
        "sidebar_current_username": current_user.username if current_user.is_authenticated else None,
    }


def _build_user_breadcrumbs(username, file_path=None, is_folder=False, folder_path=None):
    """Build breadcrumb crumbs for a user content page.

    For an item at file_path "research/ai/transformers.md" viewed at
    /@jacob/transformers, returns crumbs:
      [@jacob (link)] [research (link)] [ai (link)] [transformers (current)]

    For a folder at folder_path "research/ai" viewed at /@jacob/research/ai/,
    returns:
      [@jacob (link)] [research (link)] [ai (current)]

    Args:
      username: the profile username
      file_path: the item file_path for item pages (e.g. 'research/ai/x.md')
      is_folder: if True, folder_path is used and there is no filename
      folder_path: the folder path (used when is_folder=True)
    """
    crumbs = [{"name": "@" + username, "url": "/@" + username}]
    if is_folder and folder_path:
        parts = [p for p in folder_path.strip("/").split("/") if p]
        for i, part in enumerate(parts):
            current = (i == len(parts) - 1)
            sub = "/".join(parts[: i + 1])
            crumbs.append({
                "name": part,
                "url": None if current else f"/@{username}/{sub}/",
            })
    elif file_path:
        # Strip the trailing filename; use slug for display of the last crumb
        parts = [p for p in file_path.strip("/").split("/") if p]
        # The last element is the filename (e.g. transformers.md)
        # Intermediate parts are folders.
        folders = parts[:-1]
        for i, folder in enumerate(folders):
            sub = "/".join(folders[: i + 1])
            crumbs.append({"name": folder, "url": f"/@{username}/{sub}/"})
        # Current page (item) — use the filename stem
        last = parts[-1] if parts else ""
        if last.endswith(".md"):
            last = last[:-3]
        crumbs.append({"name": last, "url": None})
    return crumbs



@views_bp.route("/@<username>/<path:subpath>/")
def user_folder(username, subpath):
    """Folder view: show children (folders + items) at file_path prefix.

    GitHub-style auto-listing. If a child item has slug 'README', its content
    is rendered below the listing.
    """
    from models import User as UserModel
    db = get_db()
    user = UserModel.get_by_username(db, username)
    if not user:
        abort(404)

    is_owner = current_user.is_authenticated and current_user.id == user.id
    folder_path = subpath.strip("/")
    if not folder_path:
        return redirect(url_for("views.user_profile", username=username))

    prefix = folder_path + "/"

    # Fetch all items under this prefix
    rows = db.execute(
        "SELECT id, slug, title, file_path, item_type, visibility, updated_at, content "
        "FROM item WHERE owner_id = ? AND file_path LIKE ? ORDER BY file_path",
        (user.id, prefix + "%"),
    ).fetchall()

    # Filter visibility for non-owner
    if not is_owner:
        rows = [r for r in rows if r["visibility"] in ("public", "public_edit")]

    if not rows:
        abort(404)

    # Group into direct children: folders (immediate subdirs) and files (items
    # whose file_path has exactly one more path segment after the prefix)
    folders_map = {}  # name -> list of item rows under that subfolder
    direct_files = []
    prefix_len = len(prefix)
    for r in rows:
        fp = r["file_path"] or f'{r["slug"]}.md'
        rel = fp[prefix_len:] if fp.startswith(prefix) else fp
        if "/" in rel:
            # Nested: belongs to a subfolder
            sub = rel.split("/", 1)[0]
            folders_map.setdefault(sub, []).append(r)
        else:
            # Direct file in this folder
            direct_files.append(r)

    # Find README (case-insensitive slug match for "readme", but only the one
    # directly in this folder)
    readme_html = None
    readme_item_id = None
    readme_is_editable = False
    for r in direct_files:
        if (r["slug"] or "").lower() == "readme":
            readme_html = render_md(r["content"] or "", is_owner=is_owner)
            readme_item_id = r["id"]
            readme_is_editable = is_owner
            break

    # Find index item to show above the folder listing.
    # Match by slug OR by file_path basename. Priority: index > home > readme.
    index_content = None
    index_item_id = None
    index_is_editable = False
    for candidate in ("index", "home", "readme"):
        for r in direct_files:
            slug_lower = (r["slug"] or "").lower()
            fp = (r["file_path"] or "").lower()
            fp_stem = fp.rsplit("/", 1)[-1].replace(".md", "") if "/" in fp else fp.replace(".md", "")
            if slug_lower == candidate or fp_stem == candidate:
                index_content = render_md(r["content"] or "", is_owner=is_owner)
                index_item_id = r["id"]
                index_is_editable = is_owner
                break
        if index_content:
            break

    # Build children list for the template: folders first, then files (sans README)
    children = []
    for subname in sorted(folders_map.keys()):
        sub_rows = folders_map[subname]
        # Aggregate visibility of descendants
        vis_set = set(r["visibility"] for r in sub_rows)
        if len(vis_set) == 1:
            vis_summary = next(iter(vis_set))
        else:
            vis_summary = "mixed"
        children.append({
            "type": "folder",
            "name": subname,
            "path": f"{folder_path}/{subname}",
            "count": len(sub_rows),
            "visibility_summary": vis_summary,
        })
    for r in sorted(direct_files, key=lambda x: ((x["title"] or x["slug"]) or "").lower()):
        if (r["slug"] or "").lower() == "readme":
            continue  # skip README in the listing; it gets rendered separately
        children.append({
            "type": "file",
            "name": r["title"] or r["slug"],
            "title": r["title"],
            "slug": r["slug"],
            "item_type": r["item_type"],
            "visibility": r["visibility"],
            "updated_at": r["updated_at"],
        })

    # Build breadcrumbs
    breadcrumbs = _build_user_breadcrumbs(username, is_folder=True, folder_path=folder_path)

    folder_name = folder_path.split("/")[-1]

    return render_template(
        "folder.html",
        profile_user=user,
        folder_path=folder_path,
        folder_name=folder_name,
        children=children,
        readme_html=readme_html,
        readme_item_id=readme_item_id,
        readme_is_editable=readme_is_editable,
        index_content=index_content,
        index_item_id=index_item_id,
        index_is_editable=index_is_editable,
        breadcrumbs=breadcrumbs,
        is_owner=is_owner,
    )


@views_bp.route('/api/docs')
def api_docs():
    return render_template('api_docs.html')


def _get_directory_topics():
    """Get top-level directory topics with descriptions from index.md files."""
    repo = _directory_repo()
    if not os.path.isdir(repo):
        return []
    ls_output = _git_read(repo, 'ls-tree', '-r', '--name-only', 'HEAD')
    if not ls_output:
        return []
    all_files = [f for f in ls_output.strip().split('\n') if f]
    tree = _build_full_tree(all_files)
    topics = [t for t in tree if t['type'] == 'folder']

    # Extract one-line description from each topic's index.md
    for topic in topics:
        raw = _git_read(repo, 'show', f"HEAD:{topic['path']}/index.md")
        desc = ''
        if raw:
            _, body = _extract_frontmatter(raw)
            # Find first non-heading, non-empty line as description
            for line in body.split('\n'):
                line = line.strip()
                if line and not line.startswith('#') and not line.startswith('-') and not line.startswith('*'):
                    desc = line
                    break
        topic['description'] = desc

    return topics


@views_bp.route('/')
def landing():
    db = get_db()
    public_items = db.execute(
        "SELECT i.*, u.username FROM item i JOIN user u ON i.owner_id = u.id "
        "WHERE i.visibility IN ('public', 'public_edit') ORDER BY i.updated_at DESC LIMIT 12"
    ).fetchall()

    # Get directory topics
    directory_topics = _get_directory_topics()

    # Get active users (with public content)
    active_users = db.execute(
        "SELECT u.id, u.username, u.display_name, "
        "COUNT(CASE WHEN i.visibility IN ('public', 'public_edit') THEN 1 END) as public_count "
        "FROM user u JOIN item i ON i.owner_id = u.id "
        "WHERE i.visibility IN ('public', 'public_edit') "
        "GROUP BY u.id HAVING public_count > 0 "
        "ORDER BY public_count DESC LIMIT 8"
    ).fetchall()

    return render_template('landing.html', items=public_items,
                           directory_topics=directory_topics,
                           active_users=[dict(u) for u in active_users])


@views_bp.route('/people')
def people():
    db = get_db()
    users = db.execute(
        "SELECT u.id, u.username, u.display_name, u.created_at, "
        "COUNT(CASE WHEN i.visibility IN ('public', 'public_edit') THEN 1 END) as public_count, "
        "COUNT(i.id) as total_count "
        "FROM user u LEFT JOIN item i ON i.owner_id = u.id "
        "GROUP BY u.id ORDER BY public_count DESC, u.created_at ASC"
    ).fetchall()

    # Get publicly editable items
    editable_items = db.execute(
        "SELECT i.*, u.username FROM item i JOIN user u ON i.owner_id = u.id "
        "WHERE i.visibility = 'public_edit' ORDER BY i.updated_at DESC LIMIT 10"
    ).fetchall()

    # Users who have a publicly visible home item
    home_rows = db.execute(
        "SELECT u.username FROM item i JOIN user u ON i.owner_id = u.id "
        "WHERE i.slug = 'home' AND i.visibility IN ('public', 'public_edit', 'unlisted')"
    ).fetchall()
    users_with_home = {r['username'] for r in home_rows}

    return render_template('community.html', users=[dict(u) for u in users],
                           editable_items=editable_items,
                           users_with_home=users_with_home)


@views_bp.route('/community')
def community():
    """Legacy redirect."""
    return redirect(url_for('views.people'), 301)


@views_bp.route('/browse')
def browse():
    db = get_db()
    q = request.args.get('q', '').strip()

    public_items = db.execute(
        "SELECT i.*, u.username FROM item i JOIN user u ON i.owner_id = u.id "
        "WHERE i.visibility IN ('public', 'public_edit') ORDER BY i.updated_at DESC LIMIT 50"
    ).fetchall()

    items = []
    for item in public_items:
        tags = db.execute("SELECT tag FROM item_tag WHERE item_id = ?", (item['id'],)).fetchall()
        items.append({**dict(item), 'tags': [t['tag'] for t in tags]})

    if q:
        try:
            fts_rows = db.execute(
                "SELECT rowid FROM item_fts WHERE item_fts MATCH ?", (q,)
            ).fetchall()
            fts_ids = set()
            for row in fts_rows:
                real = db.execute("SELECT id FROM item WHERE rowid = ?", (row['rowid'],)).fetchone()
                if real:
                    fts_ids.add(real['id'])
            items = [i for i in items if i['id'] in fts_ids]
        except Exception:
            flash('Invalid search query.', 'error')

    directory_topics = _get_directory_topics()

    return render_template('browse.html', items=items, q=q, directory_topics=directory_topics)


@views_bp.route('/explore')
def explore():
    """Legacy redirect."""
    return redirect(url_for('views.browse', **request.args), 301)


@views_bp.route('/dash')
@login_required
def dashboard():
    db = get_db()
    visibility_filter = request.args.get('visibility')
    q = request.args.get('q', '').strip()

    query = "SELECT * FROM item WHERE owner_id = ?"
    params = [current_user.id]

    if visibility_filter == 'published':
        # Union of public + public_edit + shared (everything non-private)
        query += " AND visibility IN ('public', 'public_edit', 'shared')"
    elif visibility_filter:
        query += " AND visibility = ?"
        params.append(visibility_filter)

    query += " ORDER BY updated_at DESC"
    items = db.execute(query, params).fetchall()

    # Attach tags to each item
    items_with_tags = []
    for item in items:
        tags = db.execute("SELECT tag FROM item_tag WHERE item_id = ?", (item['id'],)).fetchall()
        items_with_tags.append({**dict(item), 'tags': [t['tag'] for t in tags]})

    # Search filter
    if q:
        try:
            fts_rows = db.execute(
                "SELECT rowid FROM item_fts WHERE item_fts MATCH ?", (q,)
            ).fetchall()
            fts_rowids = set()
            for row in fts_rows:
                real = db.execute("SELECT id FROM item WHERE rowid = ?", (row['rowid'],)).fetchone()
                if real:
                    fts_rowids.add(real['id'])
            items_with_tags = [i for i in items_with_tags if i['id'] in fts_rowids]
        except Exception:
            flash('Invalid search query.', 'error')

    # Build nested folder tree for folder view
    view_mode = request.args.get('view', 'folders')
    folder_tree = None
    if view_mode == 'folders':
        folder_tree = build_folder_tree(items_with_tags)

    # Does the current user have a "home" item? Used to decide whether
    # to show the Home button or "Set up home page" prompt in the header.
    has_home = db.execute(
        "SELECT 1 FROM item WHERE owner_id = ? AND slug = 'home' LIMIT 1",
        (current_user.id,)
    ).fetchone() is not None

    return render_template('dash.html', items=items_with_tags, q=q,
                           visibility_filter=visibility_filter, view_mode=view_mode,
                           folder_tree=folder_tree, has_home=has_home)


@views_bp.route('/dash/new', methods=['GET', 'POST'])
@login_required
def new_item():
    if request.method == 'POST':
        title = request.form.get('title', '').strip() or 'Untitled'
        content = request.form.get('content', '')
        slug = slugify(request.form.get('slug', '') or title)
        item_type = request.form.get('item_type', 'note')
        visibility = request.form.get('visibility', 'private')
        tags_str = request.form.get('tags', '')

        if visibility not in VALID_VISIBILITIES:
            visibility = 'private'

        db = get_db()

        # Ensure unique slug
        base_slug = slug
        counter = 1
        while db.execute(
            "SELECT id FROM item WHERE owner_id = ? AND slug = ?", (current_user.id, slug)
        ).fetchone():
            slug = f"{base_slug}-{counter}"
            counter += 1

        item_id = nanoid()
        file_path = f"{slug}.md"

        db.execute(
            "INSERT INTO item (id, owner_id, slug, title, content, file_path, item_type, visibility) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (item_id, current_user.id, slug, title, content, file_path, item_type, visibility)
        )

        # Tags
        for tag in tags_str.split(','):
            tag = tag.strip().lower()
            if tag:
                db.execute("INSERT OR IGNORE INTO item_tag (item_id, tag) VALUES (?, ?)", (item_id, tag))

        # Initial version
        db.execute(
            "INSERT INTO item_version (item_id, content, revision) VALUES (?, ?, 1)",
            (item_id, content)
        )

        db.commit()
        reindex_item(db, item_id)
        db.commit()

        try:
            sync_item_to_repo(current_user.username, item_id)
        except Exception:
            pass

        return redirect(url_for('views.dashboard'))

    return render_template('edit.html', item=None)


@views_bp.route('/dash/edit/<item_id>', methods=['GET', 'POST'])
@login_required
def edit_item(item_id):
    db = get_db()
    item = db.execute("SELECT * FROM item WHERE id = ? AND owner_id = ?", (item_id, current_user.id)).fetchone()
    if not item:
        abort(404)

    if request.method == 'POST':
        title = request.form.get('title', '').strip() or 'Untitled'
        content = request.form.get('content', '')
        slug = slugify(request.form.get('slug', '') or title)
        item_type = request.form.get('item_type', 'note')
        visibility = request.form.get('visibility', 'private')
        tags_str = request.form.get('tags', '')

        if visibility not in VALID_VISIBILITIES:
            visibility = 'private'

        # Ensure unique slug (excluding self)
        existing = db.execute(
            "SELECT id FROM item WHERE owner_id = ? AND slug = ? AND id != ?",
            (current_user.id, slug, item_id)
        ).fetchone()
        if existing:
            slug = f"{slug}-{item['revision'] + 1}"

        new_revision = item['revision'] + 1

        db.execute(
            "UPDATE item SET title=?, content=?, slug=?, item_type=?, visibility=?, revision=?, "
            "updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (title, content, slug, item_type, visibility, new_revision, item_id)
        )

        # Version history
        db.execute(
            "INSERT INTO item_version (item_id, content, revision) VALUES (?, ?, ?)",
            (item_id, content, new_revision)
        )

        # Update tags
        db.execute("DELETE FROM item_tag WHERE item_id = ?", (item_id,))
        for tag in tags_str.split(','):
            tag = tag.strip().lower()
            if tag:
                db.execute("INSERT OR IGNORE INTO item_tag (item_id, tag) VALUES (?, ?)", (item_id, tag))

        db.commit()
        reindex_item(db, item_id)
        db.commit()

        try:
            sync_item_to_repo(current_user.username, item_id)
        except Exception:
            pass

        return redirect(url_for('views.dashboard'))

    tags = db.execute("SELECT tag FROM item_tag WHERE item_id = ?", (item_id,)).fetchall()
    tags_str = ', '.join(t['tag'] for t in tags)

    return render_template('edit.html', item=item, tags_str=tags_str)


@views_bp.route('/@<username>/<slug>/edit', methods=['GET', 'POST'])
@login_required
def public_edit_item(username, slug):
    """Edit a public_edit item. Any authenticated user can edit."""
    db = get_db()
    from models import User
    owner = User.get_by_username(db, username)
    if not owner:
        abort(404)

    item = db.execute(
        "SELECT * FROM item WHERE owner_id = ? AND slug = ?", (owner.id, slug)
    ).fetchone()
    if not item:
        abort(404)

    is_owner = current_user.id == owner.id

    # If owner, redirect to the normal edit page
    if is_owner:
        return redirect(url_for('views.edit_item', item_id=item['id']))

    # Non-owner: must be public_edit
    if item['visibility'] != 'public_edit':
        abort(403)

    if request.method == 'POST':
        content = request.form.get('content', '')
        title = request.form.get('title', '').strip() or item['title']
        tags_str = request.form.get('tags', '')

        new_revision = item['revision'] + 1

        # Non-owners can update content, title, tags — not slug, visibility, or item_type
        db.execute(
            "UPDATE item SET title=?, content=?, revision=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (title, content, new_revision, item['id'])
        )

        db.execute(
            "INSERT INTO item_version (item_id, content, revision) VALUES (?, ?, ?)",
            (item['id'], content, new_revision)
        )

        # Update tags
        db.execute("DELETE FROM item_tag WHERE item_id = ?", (item['id'],))
        for tag in tags_str.split(','):
            tag = tag.strip().lower()
            if tag:
                db.execute("INSERT OR IGNORE INTO item_tag (item_id, tag) VALUES (?, ?)", (item['id'], tag))

        db.commit()
        reindex_item(db, item['id'])
        db.commit()

        try:
            sync_item_to_repo(username, item['id'])
        except Exception:
            pass

        return redirect(url_for('views.public_item', username=username, slug=slug))

    tags = db.execute("SELECT tag FROM item_tag WHERE item_id = ?", (item['id'],)).fetchall()
    tags_str = ', '.join(t['tag'] for t in tags)

    return render_template('edit.html', item=item, tags_str=tags_str,
                           public_edit_mode=True, owner_username=username)


@views_bp.route('/dash/delete/<item_id>', methods=['POST'])
@login_required
def delete_item(item_id):
    db = get_db()
    # Get item details for git sync before deleting
    item = db.execute(
        "SELECT rowid, file_path, slug FROM item WHERE id = ? AND owner_id = ?",
        (item_id, current_user.id)
    ).fetchone()
    if item:
        file_path = item['file_path'] or f"{item['slug']}.md"
        db.execute("DELETE FROM item_fts WHERE rowid = ?", (item['rowid'],))
        db.execute("DELETE FROM item_tag WHERE item_id = ?", (item_id,))
        db.execute("DELETE FROM item_version WHERE item_id = ?", (item_id,))
        db.execute("DELETE FROM item WHERE id = ? AND owner_id = ?", (item_id, current_user.id))
        db.commit()

        try:
            remove_from_repo(current_user.username, file_path)
        except Exception:
            pass
    else:
        db.commit()
    return redirect(url_for('views.dashboard'))


@views_bp.route('/dash/settings')
@login_required
def settings():
    db = get_db()
    keys = db.execute(
        "SELECT id, name, scopes, created_at FROM api_key WHERE user_id = ? ORDER BY created_at DESC",
        (current_user.id,)
    ).fetchall()
    return render_template('settings.html', keys=keys)


# --- Public routes ---

@views_bp.route('/@<username>')
def user_profile(username):
    db = get_db()
    from models import User
    user = User.get_by_username(db, username)
    if not user:
        abort(404)

    is_owner = current_user.is_authenticated and current_user.id == user.id

    if is_owner:
        items = db.execute(
            "SELECT * FROM item WHERE owner_id = ? ORDER BY updated_at DESC",
            (user.id,)
        ).fetchall()
    else:
        items = db.execute(
            "SELECT * FROM item WHERE owner_id = ? AND visibility IN ('public', 'public_edit') ORDER BY updated_at DESC",
            (user.id,)
        ).fetchall()

    items_with_tags = []
    for item in items:
        tags = db.execute("SELECT tag FROM item_tag WHERE item_id = ?", (item['id'],)).fetchall()
        items_with_tags.append({**dict(item), 'tags': [t['tag'] for t in tags]})

    view_mode = request.args.get('view', 'folders')
    folder_tree = None
    if view_mode == 'folders':
        folder_tree = build_folder_tree(items_with_tags)

    # Look up the user's "home" item (special slug). Shows a prominent button
    # on the profile header if present. Non-owners only see it when public.
    home_item = db.execute(
        "SELECT id, slug, title, visibility FROM item WHERE owner_id = ? AND slug = 'home'",
        (user.id,)
    ).fetchone()
    if home_item and not is_owner and home_item['visibility'] not in ('public', 'public_edit', 'unlisted'):
        home_item = None

    # Build wikis: top-level folders (distinct first path segments from items
    # with file_path containing '/'). Each wiki shows folder name + item count.
    vis_filter = "" if is_owner else " AND visibility IN ('public', 'public_edit')"
    wiki_rows = db.execute(
        "SELECT SUBSTR(file_path, 1, INSTR(file_path, '/') - 1) AS folder, COUNT(*) AS cnt "
        "FROM item WHERE owner_id = ? AND file_path LIKE '%%/%%'" + vis_filter +
        " GROUP BY folder ORDER BY folder",
        (user.id,),
    ).fetchall()
    wikis = [{'name': r['folder'], 'count': r['cnt']} for r in wiki_rows if r['folder']]

    return render_template('profile.html', profile_user=user, items=items_with_tags,
                           view_mode=view_mode, folder_tree=folder_tree, is_owner=is_owner,
                           home_item=dict(home_item) if home_item else None,
                           wikis=wikis)


@views_bp.route('/@<username>/<slug>')
def public_item(username, slug):
    db = get_db()
    from models import User
    user = User.get_by_username(db, username)
    if not user:
        abort(404)

    item = db.execute(
        "SELECT * FROM item WHERE owner_id = ? AND slug = ?", (user.id, slug)
    ).fetchone()
    if not item:
        abort(404)

    # Access check
    can_view = False
    if item['visibility'] in ('public', 'public_edit', 'unlisted'):
        can_view = True
    elif current_user.is_authenticated:
        if current_user.id == user.id:
            can_view = True
        elif item['visibility'] == 'shared':
            share = db.execute(
                "SELECT * FROM share WHERE item_id = ? AND (shared_with = ? OR shared_with = ?)",
                (item['id'], current_user.id, current_user.email or '')
            ).fetchone()
            if share:
                can_view = True

    if not can_view:
        abort(404)

    tags = db.execute("SELECT tag FROM item_tag WHERE item_id = ?", (item['id'],)).fetchall()
    is_owner = current_user.is_authenticated and current_user.id == user.id
    rendered_content = render_md(item['content'], is_owner=is_owner)
    # raw_content is used by the copy-to-clipboard textarea. For non-owners,
    # strip private blocks so they never leak via that surface either.
    raw_content = item['content'] if is_owner else strip_private_blocks(item['content'])

    # Determine edit permission
    can_edit = is_owner
    if not can_edit and item['visibility'] == 'public_edit' and current_user.is_authenticated:
        can_edit = True

    item_breadcrumbs = _build_user_breadcrumbs(user.username, file_path=item['file_path'] or f"{item['slug']}.md")
    return render_template(
        'item.html',
        item=item,
        profile_user=user,
        tags=[t['tag'] for t in tags],
        rendered_content=rendered_content,
        raw_content=raw_content,
        is_owner=is_owner,
        can_edit=can_edit,
        breadcrumbs=item_breadcrumbs
    )


# --- Directory (shared community repo) ---

REPO_ROOT = os.environ.get('LISTHUB_REPO_ROOT', '/home/ubuntu/listhub/repos')


def _directory_repo():
    """Return path to the shared directory bare repo."""
    return os.path.join(REPO_ROOT, 'directory.git')


def _git_read(repo, *args):
    """Run a read-only git command on a bare repo. Returns stdout or None."""
    result = subprocess.run(
        ['git'] + list(args),
        cwd=repo, capture_output=True, text=True
    )
    if result.returncode != 0:
        return None
    return result.stdout


def _build_full_tree(all_files):
    """
    Build a full recursive tree from file paths.
    Returns a list of nodes, each with:
      type: 'folder' or 'file'
      name: display name
      path: full path for URL
      count: number of non-index .md files in this folder (recursive)
      children: list of child nodes (folders only)
    """
    # Build raw nested dict
    raw = {}
    for filepath in all_files:
        parts = filepath.strip().split('/')
        node = raw
        for part in parts[:-1]:
            if part not in node:
                node[part] = {'__files': []}
            node = node[part]
        filename = parts[-1]
        if '__files' not in node:
            node['__files'] = []
        node['__files'].append(filename)

    def _count_items(node):
        """Count .md files recursively (including index.md as page content)."""
        count = sum(1 for f in node.get('__files', []) if f.endswith('.md'))
        for key, val in node.items():
            if key == '__files':
                continue
            count += _count_items(val)
        return count

    def _to_nodes(node, prefix=''):
        items = []
        # Folders first, sorted
        folders = sorted(k for k in node if k != '__files' and isinstance(node[k], dict))
        for folder in folders:
            path = f'{prefix}{folder}' if prefix else folder
            child_node = node[folder]
            count = _count_items(child_node)
            children = _to_nodes(child_node, path + '/')
            items.append({
                'type': 'folder',
                'name': folder,
                'path': path,
                'count': count,
                'children': children,
            })
        # Files (non-index .md)
        for f in sorted(node.get('__files', [])):
            if f == 'index.md':
                continue
            path = f'{prefix}{f}' if prefix else f
            items.append({
                'type': 'file',
                'name': f,
                'path': path,
            })
        return items

    return _to_nodes(raw)


def _extract_frontmatter(content):
    """Extract YAML-ish frontmatter. Returns (metadata, body)."""
    metadata = {}
    body = content
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            for line in parts[1].strip().split('\n'):
                if ':' in line:
                    key, val = line.split(':', 1)
                    metadata[key.strip().lower()] = val.strip()
            body = parts[2].strip()
    return metadata, body


@views_bp.route('/featured')
@views_bp.route('/featured/<path:subpath>')
def featured(subpath=''):
    repo = _directory_repo()
    if not os.path.isdir(repo):
        return render_template('directory.html', content_html=None,
                               nav_items=[], breadcrumbs=[], subpath='',
                               title='Featured', empty=True)

    # Check if repo has commits
    head = _git_read(repo, 'rev-parse', '--verify', 'HEAD')
    if not head:
        return render_template('directory.html', content_html=None,
                               nav_items=[], breadcrumbs=[], subpath='',
                               title='Featured', empty=True)

    # Get full file listing
    ls_output = _git_read(repo, 'ls-tree', '-r', '--name-only', 'HEAD')
    all_files = [f for f in (ls_output or '').strip().split('\n') if f]

    # Build breadcrumbs
    breadcrumbs = []
    if subpath:
        parts = subpath.strip('/').split('/')
        for i, part in enumerate(parts):
            breadcrumbs.append({
                'name': part,
                'path': '/'.join(parts[:i+1])
            })

    # Build full tree for sidebar
    full_tree = _build_full_tree(all_files)

    # Try to load index.md for this path
    prefix = (subpath.strip('/') + '/') if subpath else ''
    index_path = f'{prefix}index.md' if prefix else 'index.md'
    raw_content = _git_read(repo, 'show', f'HEAD:{index_path}')

    content_html = None
    title = subpath.split('/')[-1].replace('-', ' ').title() if subpath else 'Featured'

    if raw_content:
        metadata, body = _extract_frontmatter(raw_content)
        title = metadata.get('title', title)
        content_html = render_md(body)
    elif subpath and subpath.endswith('.md'):
        # Direct file view (not index.md)
        raw = _git_read(repo, 'show', f'HEAD:{subpath}')
        if raw:
            metadata, body = _extract_frontmatter(raw)
            title = metadata.get('title', subpath.split('/')[-1])
            content_html = render_md(body)

    return render_template('directory.html', content_html=content_html,
                           full_tree=full_tree, breadcrumbs=breadcrumbs,
                           subpath=subpath, title=title, empty=False)


@views_bp.route('/directory')
@views_bp.route('/directory/<path:subpath>')
def directory(subpath=''):
    """Legacy redirect."""
    return redirect(url_for('views.featured', subpath=subpath) if subpath else url_for('views.featured'), 301)


@views_bp.route('/i/<item_id>')
def short_link(item_id):
    db = get_db()
    item = db.execute("SELECT i.*, u.username FROM item i JOIN user u ON i.owner_id = u.id WHERE i.id = ?", (item_id,)).fetchone()
    if not item:
        abort(404)

    if item['visibility'] in ('public', 'public_edit', 'unlisted'):
        return redirect(url_for('views.public_item', username=item['username'], slug=item['slug']))

    if current_user.is_authenticated and current_user.id == item['owner_id']:
        return redirect(url_for('views.public_item', username=item['username'], slug=item['slug']))

    abort(404)



@views_bp.route("/directory/edit", methods=["GET", "POST"])
@views_bp.route("/directory/edit/<path:subpath>", methods=["GET", "POST"])
def directory_edit(subpath=""):
    """Web UI for editing community directory files."""
    if not current_user.is_authenticated:
        flash("Sign in to edit this page. Or use the API: POST /api/v1/auth/register to create an account, then PUT /api/v1/directory/:path to edit programmatically.", "info")
        return redirect(url_for("auth.login_local", next=request.path))
    repo = _directory_repo()
    if not os.path.isdir(repo):
        flash("Directory not initialized.", "error")
        return redirect(url_for("views.featured"))

    # Determine file path
    prefix = (subpath.strip("/") + "/") if subpath else ""
    if subpath.endswith(".md"):
        file_path = subpath
    else:
        file_path = f"{prefix}index.md"

    if request.method == "POST":
        new_content = request.form.get("content", "")
        commit_message = request.form.get("message", f"Edit {file_path}").strip()
        if not commit_message:
            commit_message = f"Edit {file_path}"

        from api import _directory_repo_path, _dir_commit_file
        api_repo = _directory_repo_path()
        commit = _dir_commit_file(
            api_repo, file_path, new_content,
            f"{commit_message} (by {current_user.username})",
            author_name=current_user.username,
            author_email=f"{current_user.username}@listhub"
        )
        if commit:
            flash("Page updated.", "success")
        else:
            flash("Failed to save changes.", "error")

        view_path = subpath if subpath else ""
        if view_path.endswith("/index.md"):
            view_path = view_path[:-9]
        elif view_path.endswith("index.md"):
            view_path = ""
        return redirect(url_for("views.featured", subpath=view_path))

    # GET: load current content
    raw_content = _git_read(repo, "show", f"HEAD:{file_path}")
    if raw_content is None:
        raw_content = ""

    title = file_path
    if subpath:
        title = subpath.split("/")[-1].replace("-", " ").title()

    return render_template("directory_edit.html",
                           file_path=file_path,
                           content=raw_content,
                           title=title,
                           subpath=subpath)


@views_bp.route("/llms.txt")
def llms_txt():
    """Machine-readable site description for AI agents (llms.txt standard)."""
    from flask import Response
    content = """# listhub

> Personal knowledge publishing platform with agent-native REST API

## Documentation

- [API docs](/api/docs): REST API reference
- [Agent setup](/AGENTS.md): Registration, authentication, MCP config

## API

- Base: /api/v1
- Auth: Bearer token (POST /api/v1/auth/register to sign up)

## Optional

- [Browse](/browse): Explore public content
- [People](/people): Community directory
"""
    return Response(content, mimetype="text/plain")


@views_bp.route("/AGENTS.md")
def agents_md():
    """Agent setup instructions in plain markdown."""
    from flask import Response
    content = """# AGENTS.md — ListHub

## Quick Start

1. **Register** (no auth required):

```bash
curl -X POST https://listhub.globalbr.ai/api/v1/auth/register \\
  -H "Content-Type: application/json" \\
  -d '{"username": "myagent", "password": "securepass123", "key_name": "default"}'
```

Response: `{"username": "myagent", "key": "mem_abc123...", ...}`

2. **Save your API key** — all subsequent requests use:

```
Authorization: Bearer mem_abc123...
```

## Create an Item

```bash
curl -X POST https://listhub.globalbr.ai/api/v1/items/new \\
  -H "Authorization: Bearer $LISTHUB_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"title": "My Note", "body": "# Hello\\nSome content.", "item_type": "note", "visibility": "public"}'
```

## Upsert by Slug (idempotent create-or-update)

```bash
curl -X PUT https://listhub.globalbr.ai/api/v1/items/by-slug/daily-log \\
  -H "Authorization: Bearer $LISTHUB_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"title": "Daily Log", "body": "Updated content", "visibility": "private"}'
```

## Read an Item

```bash
# Your own items (by ID)
curl https://listhub.globalbr.ai/api/v1/items/ITEM_ID \\
  -H "Authorization: Bearer $LISTHUB_KEY"

# Any public item (by username + slug)
curl https://listhub.globalbr.ai/api/v1/public/USERNAME/SLUG
```

## Search

```bash
curl "https://listhub.globalbr.ai/api/v1/search?q=meeting+notes" \\
  -H "Authorization: Bearer $LISTHUB_KEY"
```

## Append to a List

```bash
curl -X POST https://listhub.globalbr.ai/api/v1/items/ITEM_ID/append \\
  -H "Authorization: Bearer $LISTHUB_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"entry": "- New bullet point"}'
```

## Content Negotiation

Request `Accept: application/json` for JSON responses (default for `/api/v1/*`).
Request `Accept: text/markdown` on `/@username/slug` to get raw markdown.
Browser requests return rendered HTML.

## Visibility Levels

| Level | Who can view | Who can edit |
|-------|-------------|-------------|
| `private` | Owner only | Owner only |
| `shared` | Specific users | Specific users |
| `public` | Anyone | Owner only |
| `public_edit` | Anyone | Any authenticated user |

## MCP Configuration

Add ListHub to your MCP client config:

```json
{
  "mcpServers": {
    "listhub": {
      "url": "https://listhub.globalbr.ai/api/v1",
      "auth": { "type": "bearer", "token": "mem_abc123..." }
    }
  }
}
```

## Links

- [API reference](/api/docs)
- [llms.txt](/llms.txt)
- [Browse public content](/browse)
"""
    return Response(content, mimetype="text/plain; charset=utf-8")


@views_bp.route("/roadmap")
def roadmap():
    """Interactive roadmap page showing all beads issues."""
    import os
    from flask import send_from_directory
    mockups_dir = os.path.join(os.path.dirname(__file__), "mockups")
    return send_from_directory(mockups_dir, "roadmap.html")


@views_bp.route("/mockups/")
def mockups_index():
    import os
    from flask import send_from_directory
    mockups_dir = os.path.join(os.path.dirname(__file__), "mockups")
    return send_from_directory(mockups_dir, "index.html")


@views_bp.route("/mockups/")


def _format_bytes(n):
    """Return a human-readable file size."""
    if n < 1024:
        return f"{n} B"
    for unit in ("KB", "MB", "GB"):
        n /= 1024.0
        if n < 1024:
            return f"{n:.1f} {unit}"
    return f"{n:.1f} TB"


def _scan_mockups_dir():
    """Scan the mockups directory and return a list of entries with
    size, mtime, and extracted title/description from each HTML file."""
    import re as _re
    from datetime import datetime as _dt
    mockups_dir = os.path.join(os.path.dirname(__file__), "mockups")
    if not os.path.isdir(mockups_dir):
        return []
    entries = []
    for name in os.listdir(mockups_dir):
        if name.startswith("."):
            continue
        path = os.path.join(mockups_dir, name)
        if not os.path.isfile(path):
            continue
        try:
            st = os.stat(path)
        except OSError:
            continue
        is_html = name.lower().endswith((".html", ".htm"))
        title = ""
        description = ""
        if is_html and st.st_size < 2 * 1024 * 1024:
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    head = fh.read(12288)
                m = _re.search(r"<title[^>]*>(.*?)</title>", head, _re.IGNORECASE | _re.DOTALL)
                if m:
                    title = _re.sub(r"\s+", " ", m.group(1)).strip()
                m = _re.search(
                    r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']*)["\']',
                    head,
                    _re.IGNORECASE,
                )
                if m:
                    description = m.group(1).strip()
            except Exception:
                pass
        entries.append({
            "name": name,
            "title": title or name,
            "description": description,
            "size": st.st_size,
            "size_human": _format_bytes(st.st_size),
            "mtime": int(st.st_mtime),
            "mtime_str": _dt.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
        })
    entries.sort(key=lambda e: e["mtime"], reverse=True)
    return entries


@views_bp.route("/mockups/all-files.html")
@views_bp.route("/mockups/all-files")
def mockups_all_files():
    """Dynamic super-index of everything in the mockups directory."""
    entries = _scan_mockups_dir()
    return render_template("mockups_all_files.html", entries=entries)


@views_bp.route("/mockups/<path:filename>")
def serve_mockup(filename="index.html"):
    """Serve mockup HTML files from the mockups directory."""
    import os
    from flask import send_from_directory
    mockups_dir = os.path.join(os.path.dirname(__file__), "mockups")
    return send_from_directory(mockups_dir, filename)
