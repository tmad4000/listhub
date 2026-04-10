import re
import secrets

import bcrypt
from flask import Blueprint, request, jsonify
from flask_login import current_user, login_required
from nanoid import generate as nanoid

from db import get_db, reindex_item
from models import User
from auth import require_api_auth, get_current_api_user, api_has_scope, hash_api_key
from git_sync import sync_item_to_repo, remove_from_repo

api_bp = Blueprint('api', __name__, url_prefix='/api/v1')

VALID_VISIBILITIES = ('private', 'shared', 'public', 'public_edit', 'unlisted')


def slugify(text):
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text)
    return text.strip('-') or 'untitled'


def item_to_dict(item, include_content=True):
    d = {
        'id': item['id'],
        'slug': item['slug'],
        'title': item['title'],
        'item_type': item['item_type'],
        'visibility': item['visibility'],
        'revision': item['revision'],
        'created_at': item['created_at'],
        'updated_at': item['updated_at'],
    }
    if include_content:
        d['content'] = item['content']
    return d


def _resolve_item_for_edit(item_id):
    """Resolve an item and check edit permission.
    Returns (item, owner_username, is_owner, error_response_or_none).
    For public_edit items, any authenticated user can edit.
    For shared items with edit permission, the shared user can edit.
    """
    user = get_current_api_user()
    db = get_db()

    # Try as owner first
    item = db.execute("SELECT * FROM item WHERE id = ? AND owner_id = ?", (item_id, user.id)).fetchone()
    if item:
        return item, user.username, True, None

    # Check if item exists and is public_edit
    item = db.execute("SELECT * FROM item WHERE id = ?", (item_id,)).fetchone()
    if item and item['visibility'] == 'public_edit':
        owner = User.get(db, item['owner_id'])
        return item, owner.username if owner else 'unknown', False, None

    # Check shared edit permission
    if item and item['visibility'] == 'shared':
        share = db.execute(
            "SELECT * FROM share WHERE item_id = ? AND shared_with IN (?, ?) AND permission = 'edit'",
            (item['id'], user.id, user.email or '')
        ).fetchone()
        if share:
            owner = User.get(db, item['owner_id'])
            return item, owner.username if owner else 'unknown', False, None

    return None, None, False, (jsonify({"error": "Not found"}), 404)


@api_bp.route('/items', methods=['GET'])
@require_api_auth
def list_items():
    user = get_current_api_user()
    db = get_db()

    query = "SELECT * FROM item WHERE owner_id = ?"
    params = [user.id]

    q = request.args.get('q')
    tag = request.args.get('tag')
    item_type = request.args.get('type')
    visibility = request.args.get('visibility')

    if visibility:
        query += " AND visibility = ?"
        params.append(visibility)
    if item_type:
        query += " AND item_type = ?"
        params.append(item_type)

    query += " ORDER BY updated_at DESC"

    items = db.execute(query, params).fetchall()
    result = []

    for item in items:
        d = item_to_dict(item, include_content=False)
        # Get tags
        tags = db.execute(
            "SELECT tag FROM item_tag WHERE item_id = ?", (item['id'],)
        ).fetchall()
        d['tags'] = [t['tag'] for t in tags]
        result.append(d)

    # Filter by tag in Python (simpler than SQL join filtering)
    if tag:
        result = [i for i in result if tag in i.get('tags', [])]

    # Filter by search query using FTS5 (title 10x, content 1x, tags 5x)
    if q:
        fts_rows = db.execute(
            "SELECT rowid, bm25(item_fts, 10.0, 1.0, 5.0) AS rank "
            "FROM item_fts WHERE item_fts MATCH ? ORDER BY rank",
            (q,)
        ).fetchall()
        fts_ordered_ids = []
        for row in fts_rows:
            real = db.execute(
                "SELECT id FROM item WHERE rowid = ?", (row['rowid'],)
            ).fetchone()
            if real:
                fts_ordered_ids.append(real['id'])
        id_set = set(fts_ordered_ids)
        item_map = {i['id']: i for i in result if i['id'] in id_set}
        result = [item_map[iid] for iid in fts_ordered_ids if iid in item_map]

    return jsonify(result)


@api_bp.route('/items/<item_id>', methods=['GET'])
@require_api_auth
def get_item(item_id):
    user = get_current_api_user()
    db = get_db()

    item = db.execute("SELECT * FROM item WHERE id = ? AND owner_id = ?", (item_id, user.id)).fetchone()
    if not item:
        return jsonify({"error": "Not found"}), 404

    d = item_to_dict(item)
    tags = db.execute("SELECT tag FROM item_tag WHERE item_id = ?", (item_id,)).fetchall()
    d['tags'] = [t['tag'] for t in tags]
    return jsonify(d)


@api_bp.route('/items/<item_id>', methods=['PUT'])
@require_api_auth
def update_item_metadata(item_id):
    if not api_has_scope('write'):
        return jsonify({"error": "Write scope required"}), 403

    item, owner_username, is_owner, err = _resolve_item_for_edit(item_id)
    if err:
        return err

    db = get_db()
    data = request.get_json(silent=True) or {}

    updates = []
    params = []

    if 'visibility' in data and data['visibility'] in VALID_VISIBILITIES:
        if not is_owner:
            return jsonify({"error": "Only the owner can change visibility"}), 403
        updates.append("visibility = ?")
        params.append(data['visibility'])
    if 'slug' in data:
        if not is_owner:
            return jsonify({"error": "Only the owner can change the slug"}), 403
        new_slug = slugify(data['slug'])
        existing = db.execute(
            "SELECT id FROM item WHERE owner_id = ? AND slug = ? AND id != ?",
            (item['owner_id'], new_slug, item_id)
        ).fetchone()
        if existing:
            return jsonify({"error": "Slug already in use"}), 409
        updates.append("slug = ?")
        params.append(new_slug)
    if 'title' in data:
        updates.append("title = ?")
        params.append(data['title'])
    if 'item_type' in data and data['item_type'] in ('note', 'list', 'document'):
        updates.append("item_type = ?")
        params.append(data['item_type'])

    if updates:
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(item_id)
        db.execute(
            f"UPDATE item SET {', '.join(updates)} WHERE id = ?",
            params
        )

    # Handle tags
    if 'tags' in data:
        db.execute("DELETE FROM item_tag WHERE item_id = ?", (item_id,))
        for tag in data['tags']:
            tag = tag.strip().lower()
            if tag:
                db.execute("INSERT OR IGNORE INTO item_tag (item_id, tag) VALUES (?, ?)", (item_id, tag))

    db.commit()
    reindex_item(db, item_id)
    db.commit()

    try:
        sync_item_to_repo(owner_username, item_id)
    except Exception:
        pass

    updated = db.execute("SELECT * FROM item WHERE id = ?", (item_id,)).fetchone()
    return jsonify(item_to_dict(updated))


@api_bp.route('/items/new', methods=['POST'])
@require_api_auth
def create_item():
    if not api_has_scope('write'):
        return jsonify({"error": "Write scope required"}), 403

    user = get_current_api_user()
    db = get_db()
    data = request.get_json(silent=True) or {}

    title = data.get('title', 'Untitled')
    content = data.get('content', '')
    slug = slugify(data.get('slug', title))
    item_type = data.get('item_type', 'note')
    visibility = data.get('visibility', 'private')
    tags = data.get('tags', [])
    file_path = data.get('file_path', f"{slug}.md")

    if item_type not in ('note', 'list', 'document'):
        item_type = 'note'
    if visibility not in VALID_VISIBILITIES:
        visibility = 'private'

    # Ensure unique slug
    base_slug = slug
    counter = 1
    while db.execute(
        "SELECT id FROM item WHERE owner_id = ? AND slug = ?", (user.id, slug)
    ).fetchone():
        slug = f"{base_slug}-{counter}"
        counter += 1

    item_id = nanoid()

    db.execute(
        "INSERT INTO item (id, owner_id, slug, title, content, file_path, item_type, visibility) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (item_id, user.id, slug, title, content, file_path, item_type, visibility)
    )

    for tag in tags:
        tag = tag.strip().lower()
        if tag:
            db.execute("INSERT OR IGNORE INTO item_tag (item_id, tag) VALUES (?, ?)", (item_id, tag))

    # Save initial version
    db.execute(
        "INSERT INTO item_version (item_id, content, revision) VALUES (?, ?, 1)",
        (item_id, content)
    )

    db.commit()
    reindex_item(db, item_id)
    db.commit()

    try:
        sync_item_to_repo(user.username, item_id)
    except Exception:
        pass

    item = db.execute("SELECT * FROM item WHERE id = ?", (item_id,)).fetchone()
    d = item_to_dict(item)
    d['tags'] = tags
    return jsonify(d), 201


@api_bp.route('/items/<item_id>/edit', methods=['POST'])
@require_api_auth
def edit_item_content(item_id):
    if not api_has_scope('write'):
        return jsonify({"error": "Write scope required"}), 403

    item, owner_username, is_owner, err = _resolve_item_for_edit(item_id)
    if err:
        return err

    db = get_db()
    data = request.get_json(silent=True) or {}
    content = data.get('content')
    if content is None:
        return jsonify({"error": "content field required"}), 400

    new_revision = item['revision'] + 1

    db.execute(
        "UPDATE item SET content = ?, revision = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (content, new_revision, item_id)
    )

    db.execute(
        "INSERT INTO item_version (item_id, content, revision) VALUES (?, ?, ?)",
        (item_id, content, new_revision)
    )

    db.commit()
    reindex_item(db, item_id)
    db.commit()

    try:
        sync_item_to_repo(owner_username, item_id)
    except Exception:
        pass

    updated = db.execute("SELECT * FROM item WHERE id = ?", (item_id,)).fetchone()
    return jsonify(item_to_dict(updated))


@api_bp.route('/items/<item_id>', methods=['DELETE'])
@require_api_auth
def delete_item(item_id):
    if not api_has_scope('write'):
        return jsonify({"error": "Write scope required"}), 403

    user = get_current_api_user()
    db = get_db()

    # Delete is owner-only
    item = db.execute("SELECT * FROM item WHERE id = ? AND owner_id = ?", (item_id, user.id)).fetchone()
    if not item:
        return jsonify({"error": "Not found"}), 404

    file_path = item['file_path'] or f"{item['slug']}.md"

    # Clean up FTS, tags, versions before deleting
    row = db.execute("SELECT rowid FROM item WHERE id = ?", (item_id,)).fetchone()
    if row:
        db.execute("DELETE FROM item_fts WHERE rowid = ?", (row['rowid'],))
    db.execute("DELETE FROM item_tag WHERE item_id = ?", (item_id,))
    db.execute("DELETE FROM item_version WHERE item_id = ?", (item_id,))
    db.execute("DELETE FROM item WHERE id = ?", (item_id,))
    db.commit()

    try:
        remove_from_repo(user.username, file_path)
    except Exception:
        pass

    return jsonify({"ok": True})


@api_bp.route('/items/<item_id>/append', methods=['POST'])
@require_api_auth
def append_to_list(item_id):
    if not api_has_scope('write'):
        return jsonify({"error": "Write scope required"}), 403

    item, owner_username, is_owner, err = _resolve_item_for_edit(item_id)
    if err:
        return err

    db = get_db()
    data = request.get_json(silent=True) or {}
    entry = data.get('entry', '').strip()
    if not entry:
        return jsonify({"error": "entry field required"}), 400

    content = item['content'] or ''
    if content and not content.endswith('\n'):
        content += '\n'
    content += f"- {entry}\n"

    new_revision = item['revision'] + 1

    db.execute(
        "UPDATE item SET content = ?, revision = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (content, new_revision, item_id)
    )
    db.execute(
        "INSERT INTO item_version (item_id, content, revision) VALUES (?, ?, ?)",
        (item_id, content, new_revision)
    )
    db.commit()
    reindex_item(db, item_id)
    db.commit()

    try:
        sync_item_to_repo(owner_username, item_id)
    except Exception:
        pass

    updated = db.execute("SELECT * FROM item WHERE id = ?", (item_id,)).fetchone()
    return jsonify(item_to_dict(updated))


@api_bp.route('/items/<item_id>/share', methods=['POST'])
@require_api_auth
def share_item(item_id):
    if not api_has_scope('write'):
        return jsonify({"error": "Write scope required"}), 403

    user = get_current_api_user()
    db = get_db()

    item = db.execute("SELECT * FROM item WHERE id = ? AND owner_id = ?", (item_id, user.id)).fetchone()
    if not item:
        return jsonify({"error": "Not found"}), 404

    data = request.get_json(silent=True) or {}
    shared_with = data.get('shared_with', '').strip()
    permission = data.get('permission', 'read')

    if not shared_with:
        return jsonify({"error": "shared_with required"}), 400
    if permission not in ('read', 'edit'):
        permission = 'read'

    db.execute(
        "INSERT OR REPLACE INTO share (item_id, shared_with, permission) VALUES (?, ?, ?)",
        (item_id, shared_with, permission)
    )

    if item['visibility'] != 'shared':
        db.execute("UPDATE item SET visibility = 'shared' WHERE id = ?", (item_id,))

    db.commit()
    return jsonify({"ok": True})


@api_bp.route('/items/<item_id>/share/<who>', methods=['DELETE'])
@require_api_auth
def revoke_share(item_id, who):
    if not api_has_scope('write'):
        return jsonify({"error": "Write scope required"}), 403

    user = get_current_api_user()
    db = get_db()

    item = db.execute("SELECT * FROM item WHERE id = ? AND owner_id = ?", (item_id, user.id)).fetchone()
    if not item:
        return jsonify({"error": "Not found"}), 404

    db.execute("DELETE FROM share WHERE item_id = ? AND shared_with = ?", (item_id, who))
    db.commit()
    return jsonify({"ok": True})


@api_bp.route('/items/by-slug/<slug>', methods=['GET'])
@require_api_auth
def get_item_by_slug(slug):
    user = get_current_api_user()
    db = get_db()

    item = db.execute("SELECT * FROM item WHERE owner_id = ? AND slug = ?", (user.id, slug)).fetchone()
    if not item:
        return jsonify({"error": "Not found"}), 404

    d = item_to_dict(item)
    tags = db.execute("SELECT tag FROM item_tag WHERE item_id = ?", (item['id'],)).fetchall()
    d['tags'] = [t['tag'] for t in tags]
    return jsonify(d)


@api_bp.route('/items/by-slug/<slug>', methods=['PUT'])
@require_api_auth
def upsert_item_by_slug(slug):
    if not api_has_scope('write'):
        return jsonify({"error": "Write scope required"}), 403

    user = get_current_api_user()
    db = get_db()
    data = request.get_json(silent=True) or {}

    existing = db.execute("SELECT * FROM item WHERE owner_id = ? AND slug = ?", (user.id, slug)).fetchone()

    if existing:
        # Update existing item
        item_id = existing['id']
        content = data.get('content', existing['content'])
        new_revision = existing['revision'] + 1

        updates = ["content = ?", "revision = ?", "updated_at = CURRENT_TIMESTAMP"]
        params = [content, new_revision]

        if 'title' in data:
            updates.append("title = ?")
            params.append(data['title'])
        if 'visibility' in data and data['visibility'] in VALID_VISIBILITIES:
            updates.append("visibility = ?")
            params.append(data['visibility'])
        if 'item_type' in data and data['item_type'] in ('note', 'list', 'document'):
            updates.append("item_type = ?")
            params.append(data['item_type'])

        params.extend([item_id, user.id])
        db.execute(
            f"UPDATE item SET {', '.join(updates)} WHERE id = ? AND owner_id = ?",
            params
        )

        db.execute(
            "INSERT INTO item_version (item_id, content, revision) VALUES (?, ?, ?)",
            (item_id, content, new_revision)
        )

        if 'tags' in data:
            db.execute("DELETE FROM item_tag WHERE item_id = ?", (item_id,))
            for tag in data['tags']:
                tag = tag.strip().lower()
                if tag:
                    db.execute("INSERT OR IGNORE INTO item_tag (item_id, tag) VALUES (?, ?)", (item_id, tag))

        db.commit()
        reindex_item(db, item_id)
        db.commit()

        try:
            sync_item_to_repo(user.username, item_id)
        except Exception:
            pass

        updated = db.execute("SELECT * FROM item WHERE id = ?", (item_id,)).fetchone()
        return jsonify(item_to_dict(updated))
    else:
        # Create new item with explicit slug
        title = data.get('title', slug.replace('-', ' ').title())
        content = data.get('content', '')
        item_type = data.get('item_type', 'note')
        visibility = data.get('visibility', 'private')
        tags = data.get('tags', [])
        file_path = data.get('file_path', f"{slug}.md")

        if item_type not in ('note', 'list', 'document'):
            item_type = 'note'
        if visibility not in VALID_VISIBILITIES:
            visibility = 'private'

        item_id = nanoid()

        db.execute(
            "INSERT INTO item (id, owner_id, slug, title, content, file_path, item_type, visibility) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (item_id, user.id, slug, title, content, file_path, item_type, visibility)
        )

        for tag in tags:
            tag = tag.strip().lower()
            if tag:
                db.execute("INSERT OR IGNORE INTO item_tag (item_id, tag) VALUES (?, ?)", (item_id, tag))

        db.execute(
            "INSERT INTO item_version (item_id, content, revision) VALUES (?, ?, 1)",
            (item_id, content)
        )

        db.commit()
        reindex_item(db, item_id)
        db.commit()

        try:
            sync_item_to_repo(user.username, item_id)
        except Exception:
            pass

        item = db.execute("SELECT * FROM item WHERE id = ?", (item_id,)).fetchone()
        d = item_to_dict(item)
        d['tags'] = tags
        return jsonify(d), 201


@api_bp.route('/items/by-slug/<slug>', methods=['DELETE'])
@require_api_auth
def delete_item_by_slug(slug):
    if not api_has_scope('write'):
        return jsonify({"error": "Write scope required"}), 403

    user = get_current_api_user()
    db = get_db()

    item = db.execute("SELECT * FROM item WHERE owner_id = ? AND slug = ?", (user.id, slug)).fetchone()
    if not item:
        return jsonify({"error": "Not found"}), 404

    item_id = item['id']
    file_path = item['file_path'] or f"{item['slug']}.md"

    row = db.execute("SELECT rowid FROM item WHERE id = ?", (item_id,)).fetchone()
    if row:
        db.execute("DELETE FROM item_fts WHERE rowid = ?", (row['rowid'],))
    db.execute("DELETE FROM item_tag WHERE item_id = ?", (item_id,))
    db.execute("DELETE FROM item_version WHERE item_id = ?", (item_id,))
    db.execute("DELETE FROM item WHERE id = ?", (item_id,))
    db.commit()

    try:
        remove_from_repo(user.username, file_path)
    except Exception:
        pass

    return jsonify({"ok": True})


# --- Public edit endpoints (by username + slug) ---

@api_bp.route('/public/<username>/<slug>', methods=['GET'])
def get_public_item(username, slug):
    """Get a public or public_edit item by username and slug. No auth required."""
    db = get_db()
    user = User.get_by_username(db, username)
    if not user:
        return jsonify({"error": "Not found"}), 404

    item = db.execute(
        "SELECT * FROM item WHERE owner_id = ? AND slug = ?", (user.id, slug)
    ).fetchone()
    if not item or item['visibility'] not in ('public', 'public_edit'):
        return jsonify({"error": "Not found"}), 404

    d = item_to_dict(item)
    d['owner'] = username
    d['can_edit'] = item['visibility'] == 'public_edit'
    tags = db.execute("SELECT tag FROM item_tag WHERE item_id = ?", (item['id'],)).fetchall()
    d['tags'] = [t['tag'] for t in tags]
    return jsonify(d)


@api_bp.route('/public/<username>/<slug>/edit', methods=['POST'])
@require_api_auth
def edit_public_item(username, slug):
    """Edit a public_edit item by username and slug. Any authenticated user can edit."""
    if not api_has_scope('write'):
        return jsonify({"error": "Write scope required"}), 403

    db = get_db()
    owner = User.get_by_username(db, username)
    if not owner:
        return jsonify({"error": "Not found"}), 404

    item = db.execute(
        "SELECT * FROM item WHERE owner_id = ? AND slug = ?", (owner.id, slug)
    ).fetchone()
    if not item:
        return jsonify({"error": "Not found"}), 404

    # Check permission: owner or public_edit
    editor = get_current_api_user()
    is_owner = editor.id == owner.id
    if not is_owner and item['visibility'] != 'public_edit':
        return jsonify({"error": "This item is not publicly editable"}), 403

    data = request.get_json(silent=True) or {}
    content = data.get('content')
    if content is None:
        return jsonify({"error": "content field required"}), 400

    new_revision = item['revision'] + 1

    db.execute(
        "UPDATE item SET content = ?, revision = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (content, new_revision, item['id'])
    )
    db.execute(
        "INSERT INTO item_version (item_id, content, revision) VALUES (?, ?, ?)",
        (item['id'], content, new_revision)
    )
    db.commit()
    reindex_item(db, item['id'])
    db.commit()

    try:
        sync_item_to_repo(username, item['id'])
    except Exception:
        pass

    updated = db.execute("SELECT * FROM item WHERE id = ?", (item['id'],)).fetchone()
    return jsonify(item_to_dict(updated))


@api_bp.route('/public/<username>/<slug>/append', methods=['POST'])
@require_api_auth
def append_public_item(username, slug):
    """Append to a public_edit item by username and slug. Any authenticated user can append."""
    if not api_has_scope('write'):
        return jsonify({"error": "Write scope required"}), 403

    db = get_db()
    owner = User.get_by_username(db, username)
    if not owner:
        return jsonify({"error": "Not found"}), 404

    item = db.execute(
        "SELECT * FROM item WHERE owner_id = ? AND slug = ?", (owner.id, slug)
    ).fetchone()
    if not item:
        return jsonify({"error": "Not found"}), 404

    editor = get_current_api_user()
    is_owner = editor.id == owner.id
    if not is_owner and item['visibility'] != 'public_edit':
        return jsonify({"error": "This item is not publicly editable"}), 403

    data = request.get_json(silent=True) or {}
    entry = data.get('entry', '').strip()
    if not entry:
        return jsonify({"error": "entry field required"}), 400

    content = item['content'] or ''
    if content and not content.endswith('\n'):
        content += '\n'
    content += f"- {entry}\n"

    new_revision = item['revision'] + 1

    db.execute(
        "UPDATE item SET content = ?, revision = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (content, new_revision, item['id'])
    )
    db.execute(
        "INSERT INTO item_version (item_id, content, revision) VALUES (?, ?, ?)",
        (item['id'], content, new_revision)
    )
    db.commit()
    reindex_item(db, item['id'])
    db.commit()

    try:
        sync_item_to_repo(username, item['id'])
    except Exception:
        pass

    updated = db.execute("SELECT * FROM item WHERE id = ?", (item['id'],)).fetchone()
    return jsonify(item_to_dict(updated))


@api_bp.route('/search', methods=['GET'])
@require_api_auth
def search():
    user = get_current_api_user()
    db = get_db()

    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([])

    try:
        fts_rows = db.execute(
            "SELECT rowid, bm25(item_fts, 10.0, 1.0, 5.0) AS rank "
            "FROM item_fts WHERE item_fts MATCH ? ORDER BY rank",
            (q,)
        ).fetchall()
    except Exception:
        return jsonify({"error": "Invalid search query"}), 400

    results = []
    for row in fts_rows:
        item = db.execute(
            "SELECT * FROM item WHERE rowid = ? AND owner_id = ?",
            (row['rowid'], user.id)
        ).fetchone()
        if item:
            d = item_to_dict(item, include_content=False)
            tags = db.execute("SELECT tag FROM item_tag WHERE item_id = ?", (item['id'],)).fetchall()
            d['tags'] = [t['tag'] for t in tags]
            results.append(d)

    return jsonify(results)


# --- Auth ---

@api_bp.route('/auth/token', methods=['POST'])
def get_token():
    """
    Exchange username + password for an API key.
    Allows assistants and integrations to bootstrap without a browser session.
    """
    data = request.get_json(silent=True) or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    key_name = data.get('name', 'api-token')
    scopes = data.get('scopes', 'read,write')

    if not username or not password:
        return jsonify({"error": "username and password required"}), 400

    db = get_db()
    user = User.get_by_username(db, username)
    if not user:
        return jsonify({"error": "Invalid credentials"}), 401

    try:
        if not bcrypt.checkpw(password.encode(), user.password_hash.encode()):
            return jsonify({"error": "Invalid credentials"}), 401
    except Exception:
        return jsonify({"error": "Invalid credentials"}), 401

    # Generate a new API key
    raw_key = f"mem_{secrets.token_urlsafe(32)}"
    key_id = nanoid()
    key_h = hash_api_key(raw_key)

    db.execute(
        "INSERT INTO api_key (id, user_id, key_hash, name, scopes) VALUES (?, ?, ?, ?, ?)",
        (key_id, user.id, key_h, key_name, scopes)
    )
    db.commit()

    return jsonify({
        "id": key_id,
        "key": raw_key,
        "name": key_name,
        "scopes": scopes,
        "username": username,
    }), 201



@api_bp.route("/auth/register", methods=["POST"])
def api_register():
    """
    Programmatic account registration.
    Allows agents and integrations to create a new ListHub account
    and receive an API key in a single call - no browser needed.
    """
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip().lower()
    password = data.get("password", "")
    display_name = data.get("display_name", "").strip()
    email = data.get("email", "").strip().lower() if data.get("email") else None
    key_name = data.get("key_name", "api-token")
    scopes = data.get("scopes", "read,write")

    if not username or not password:
        return jsonify({"error": "username and password required"}), 400

    if len(username) < 2 or not username.isalnum():
        return jsonify({"error": "Username must be at least 2 alphanumeric characters"}), 400

    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400

    db = get_db()

    if User.get_by_username(db, username):
        return jsonify({"error": "Username already taken"}), 409

    if email and User.get_by_email(db, email):
        return jsonify({"error": "Email already registered"}), 409

    user_id = nanoid()
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    db.execute(
        "INSERT INTO user (id, username, display_name, email, password_hash) VALUES (?, ?, ?, ?, ?)",
        (user_id, username, display_name or username, email, pw_hash)
    )

    try:
        from git_backend import init_user_repo
        init_user_repo(username)
    except Exception:
        pass

    raw_key = f"mem_{secrets.token_urlsafe(32)}"
    key_id = nanoid()
    key_h = hash_api_key(raw_key)

    db.execute(
        "INSERT INTO api_key (id, user_id, key_hash, name, scopes) VALUES (?, ?, ?, ?, ?)",
        (key_id, user_id, key_h, key_name, scopes)
    )
    db.commit()

    return jsonify({
        "id": user_id,
        "username": username,
        "key": raw_key,
        "key_id": key_id,
        "key_name": key_name,
        "scopes": scopes,
        "message": "Account created. Save the key - it cannot be retrieved again."
    }), 201


# --- API Key Management ---

@api_bp.route('/keys', methods=['GET'])
@login_required
def list_keys():
    db = get_db()
    keys = db.execute(
        "SELECT id, name, scopes, created_at FROM api_key WHERE user_id = ? ORDER BY created_at DESC",
        (current_user.id,)
    ).fetchall()
    return jsonify([dict(k) for k in keys])


@api_bp.route('/keys', methods=['POST'])
@login_required
def create_key():
    db = get_db()
    data = request.get_json(silent=True) or {}
    name = data.get('name', 'default')
    scopes = data.get('scopes', 'read,write')

    raw_key = f"mem_{secrets.token_urlsafe(32)}"
    key_id = nanoid()
    key_h = hash_api_key(raw_key)

    db.execute(
        "INSERT INTO api_key (id, user_id, key_hash, name, scopes) VALUES (?, ?, ?, ?, ?)",
        (key_id, current_user.id, key_h, name, scopes)
    )
    db.commit()

    # Return the raw key ONCE — it can never be retrieved again
    return jsonify({"id": key_id, "key": raw_key, "name": name, "scopes": scopes}), 201


@api_bp.route('/keys/<key_id>', methods=['DELETE'])
@login_required
def delete_key(key_id):
    db = get_db()
    db.execute("DELETE FROM api_key WHERE id = ? AND user_id = ?", (key_id, current_user.id))
    db.commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Directory API (shared community repo)
# ---------------------------------------------------------------------------

import os
import subprocess
import tempfile


def _directory_repo_path():
    """Return path to the shared directory bare repo."""
    repo_root = os.environ.get("LISTHUB_REPO_ROOT", "/home/ubuntu/listhub/repos")
    return os.path.join(repo_root, "directory.git")


def _dir_git(repo_path, *args, env=None, input_data=None):
    """Run a git command on a repo. Returns stdout as string or None on error."""
    cmd = ["git", "-C", repo_path] + list(args)
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    result = subprocess.run(cmd, capture_output=True, text=True, env=merged_env, input=input_data)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _dir_git_bytes(repo_path, *args, env=None, input_bytes=None):
    """Run a git command with binary input. Returns stdout as bytes or None."""
    cmd = ["git", "-C", repo_path] + list(args)
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    result = subprocess.run(cmd, capture_output=True, env=merged_env, input=input_bytes)
    if result.returncode != 0:
        return None
    return result.stdout


_DIR_AUTHOR_ENV = {
    "GIT_AUTHOR_NAME": "ListHub",
    "GIT_AUTHOR_EMAIL": "directory@listhub",
    "GIT_COMMITTER_NAME": "ListHub",
    "GIT_COMMITTER_EMAIL": "directory@listhub",
}


def _dir_commit_file(repo, file_path, content, message, author_name=None, author_email=None):
    """Write a file to the directory bare repo and commit it."""
    head = _dir_git(repo, "rev-parse", "--verify", "HEAD")
    idx = tempfile.mktemp(prefix="listhub-dir-", suffix=".idx")
    env = {"GIT_INDEX_FILE": idx}

    author_env = dict(_DIR_AUTHOR_ENV)
    if author_name:
        author_env["GIT_AUTHOR_NAME"] = author_name
        author_env["GIT_COMMITTER_NAME"] = author_name
    if author_email:
        author_env["GIT_AUTHOR_EMAIL"] = author_email
        author_env["GIT_COMMITTER_EMAIL"] = author_email

    try:
        if head:
            _dir_git(repo, "read-tree", "HEAD", env=env)

        blob = _dir_git_bytes(
            repo, "hash-object", "-w", "--stdin",
            input_bytes=content.encode("utf-8"), env=env
        )
        if not blob:
            return None
        blob_hash = blob.strip().decode()

        _dir_git(repo, "update-index", "--add", "--cacheinfo",
                 "100644", blob_hash, file_path, env=env)

        new_tree = _dir_git(repo, "write-tree", env=env)
        if not new_tree:
            return None

        commit_args = ["commit-tree", new_tree, "-m", message]
        if head:
            commit_args[2:2] = ["-p", head]

        new_commit = _dir_git(repo, *commit_args, env={**env, **author_env})
        if not new_commit:
            return None

        _dir_git(repo, "update-ref", "refs/heads/main", new_commit)
        return new_commit
    finally:
        if os.path.exists(idx):
            os.unlink(idx)


def _dir_remove_file(repo, file_path, message, author_name=None):
    """Remove a file from the directory bare repo and commit."""
    head = _dir_git(repo, "rev-parse", "--verify", "HEAD")
    if not head:
        return None

    idx = tempfile.mktemp(prefix="listhub-dir-", suffix=".idx")
    env = {"GIT_INDEX_FILE": idx}

    author_env = dict(_DIR_AUTHOR_ENV)
    if author_name:
        author_env["GIT_AUTHOR_NAME"] = author_name
        author_env["GIT_COMMITTER_NAME"] = author_name

    try:
        _dir_git(repo, "read-tree", "HEAD", env=env)
        _dir_git(repo, "update-index", "--index-info", env=env,
                 input_data=f"0 0000000000000000000000000000000000000000\t{file_path}\n")

        new_tree = _dir_git(repo, "write-tree", env=env)
        old_tree = _dir_git(repo, "rev-parse", "--verify", "HEAD^{tree}")

        if new_tree == old_tree:
            return None

        new_commit = _dir_git(
            repo, "commit-tree", new_tree, "-p", head, "-m", message,
            env={**env, **author_env}
        )
        if not new_commit:
            return None

        _dir_git(repo, "update-ref", "refs/heads/main", new_commit)
        return new_commit
    finally:
        if os.path.exists(idx):
            os.unlink(idx)


@api_bp.route("/directory", methods=["GET"])
def api_directory_tree():
    """List the community directory tree structure."""
    repo = _directory_repo_path()
    if not os.path.isdir(repo):
        return jsonify({"tree": [], "message": "Directory not initialized"}), 200

    ls_output = _dir_git(repo, "ls-tree", "-r", "--name-only", "HEAD")
    if not ls_output:
        return jsonify({"tree": []}), 200

    files = [f for f in ls_output.split("\n") if f]
    return jsonify({"tree": files}), 200


@api_bp.route("/directory/<path:file_path>", methods=["GET"])
def api_directory_read(file_path):
    """Read a file from the community directory."""
    repo = _directory_repo_path()
    if not os.path.isdir(repo):
        return jsonify({"error": "Directory not initialized"}), 404

    content = _dir_git(repo, "show", f"HEAD:{file_path}")
    if content is None:
        return jsonify({"error": "File not found"}), 404

    return jsonify({"path": file_path, "content": content}), 200


@api_bp.route("/directory/<path:file_path>", methods=["PUT"])
@require_api_auth
def api_directory_write(file_path):
    """Create or update a file in the community directory. Any authenticated user can write."""
    if not api_has_scope("write"):
        return jsonify({"error": "Write scope required"}), 403

    user = get_current_api_user()
    data = request.get_json(silent=True) or {}
    content = data.get("content")
    message = data.get("message", f"Update {file_path}")

    if content is None:
        return jsonify({"error": "content field required"}), 400

    repo = _directory_repo_path()
    if not os.path.isdir(repo):
        return jsonify({"error": "Directory not initialized"}), 404

    commit = _dir_commit_file(
        repo, file_path, content, message,
        author_name=user.username,
        author_email=f"{user.username}@listhub"
    )
    if not commit:
        return jsonify({"error": "Failed to commit"}), 500

    return jsonify({"ok": True, "path": file_path, "commit": commit}), 200


@api_bp.route("/directory/<path:file_path>", methods=["DELETE"])
@require_api_auth
def api_directory_delete(file_path):
    """Remove a file from the community directory."""
    if not api_has_scope("write"):
        return jsonify({"error": "Write scope required"}), 403

    user = get_current_api_user()
    message = f"Remove {file_path} (by {user.username})"

    repo = _directory_repo_path()
    if not os.path.isdir(repo):
        return jsonify({"error": "Directory not initialized"}), 404

    commit = _dir_remove_file(repo, file_path, message, author_name=user.username)
    if not commit:
        return jsonify({"error": "File not found or already removed"}), 404

    return jsonify({"ok": True, "path": file_path, "commit": commit}), 200
