import re
import secrets

from flask import Blueprint, request, jsonify
from flask_login import current_user, login_required
from nanoid import generate as nanoid

from db import get_db, reindex_item
from auth import require_api_auth, get_current_api_user, api_has_scope, hash_api_key
from security import validate_item_input

api_bp = Blueprint('api', __name__, url_prefix='/api/v1')


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

    # Filter by search query using FTS5
    if q:
        fts_ids = set()
        fts_rows = db.execute(
            "SELECT rowid FROM item_fts WHERE item_fts MATCH ?", (q,)
        ).fetchall()
        for row in fts_rows:
            real = db.execute(
                "SELECT id FROM item WHERE rowid = ?", (row['rowid'],)
            ).fetchone()
            if real:
                fts_ids.add(real['id'])
        result = [i for i in result if i['id'] in fts_ids]

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

    user = get_current_api_user()
    db = get_db()

    item = db.execute("SELECT * FROM item WHERE id = ? AND owner_id = ?", (item_id, user.id)).fetchone()
    if not item:
        return jsonify({"error": "Not found"}), 404

    data = request.get_json(silent=True) or {}

    updates = []
    params = []

    if 'visibility' in data and data['visibility'] in ('private', 'shared', 'public'):
        updates.append("visibility = ?")
        params.append(data['visibility'])
    if 'slug' in data:
        new_slug = slugify(data['slug'])
        existing = db.execute(
            "SELECT id FROM item WHERE owner_id = ? AND slug = ? AND id != ?",
            (user.id, new_slug, item_id)
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
        params.append(user.id)
        db.execute(
            f"UPDATE item SET {', '.join(updates)} WHERE id = ? AND owner_id = ?",
            params
        )

    # Handle tags
    if 'tags' in data:
        db.execute("DELETE FROM item_tag WHERE item_id = ?", (item_id,))
        for tag in data['tags']:
            tag = tag.strip().lower()
            if tag and len(tag) <= 50:  # Limit tag length
                db.execute("INSERT OR IGNORE INTO item_tag (item_id, tag) VALUES (?, ?)", (item_id, tag))

    db.commit()
    reindex_item(db, item_id)
    db.commit()

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

    # Validate inputs
    is_valid, error = validate_item_input(title, content, slug)
    if not is_valid:
        return jsonify({"error": error}), 400

    if item_type not in ('note', 'list', 'document'):
        item_type = 'note'
    if visibility not in ('private', 'shared', 'public'):
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
        if tag and len(tag) <= 50:  # Limit tag length
            db.execute("INSERT OR IGNORE INTO item_tag (item_id, tag) VALUES (?, ?)", (item_id, tag))

    # Save initial version
    db.execute(
        "INSERT INTO item_version (item_id, content, revision) VALUES (?, ?, 1)",
        (item_id, content)
    )

    db.commit()
    reindex_item(db, item_id)
    db.commit()

    item = db.execute("SELECT * FROM item WHERE id = ?", (item_id,)).fetchone()
    d = item_to_dict(item)
    d['tags'] = [t.strip().lower() for t in tags if t.strip() and len(t.strip()) <= 50]
    return jsonify(d), 201


@api_bp.route('/items/<item_id>/edit', methods=['POST'])
@require_api_auth
def edit_item_content(item_id):
    if not api_has_scope('write'):
        return jsonify({"error": "Write scope required"}), 403

    user = get_current_api_user()
    db = get_db()

    item = db.execute("SELECT * FROM item WHERE id = ? AND owner_id = ?", (item_id, user.id)).fetchone()
    if not item:
        return jsonify({"error": "Not found"}), 404

    data = request.get_json(silent=True) or {}
    content = data.get('content')
    if content is None:
        return jsonify({"error": "content field required"}), 400

    # Validate content size
    if len(content) > 1_000_000:
        return jsonify({"error": "Content must be 1MB or less"}), 400

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

    updated = db.execute("SELECT * FROM item WHERE id = ?", (item_id,)).fetchone()
    return jsonify(item_to_dict(updated))


@api_bp.route('/items/<item_id>', methods=['DELETE'])
@require_api_auth
def delete_item(item_id):
    if not api_has_scope('write'):
        return jsonify({"error": "Write scope required"}), 403

    user = get_current_api_user()
    db = get_db()

    item = db.execute("SELECT *, rowid FROM item WHERE id = ? AND owner_id = ?", (item_id, user.id)).fetchone()
    if not item:
        return jsonify({"error": "Not found"}), 404

    # Delete FTS entry before deleting item
    db.execute("DELETE FROM item_fts WHERE rowid = ?", (item['rowid'],))
    db.execute("DELETE FROM item WHERE id = ?", (item_id,))
    db.commit()

    return jsonify({"ok": True})


@api_bp.route('/items/<item_id>/append', methods=['POST'])
@require_api_auth
def append_to_list(item_id):
    if not api_has_scope('write'):
        return jsonify({"error": "Write scope required"}), 403

    user = get_current_api_user()
    db = get_db()

    item = db.execute("SELECT * FROM item WHERE id = ? AND owner_id = ?", (item_id, user.id)).fetchone()
    if not item:
        return jsonify({"error": "Not found"}), 404

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
            "SELECT rowid FROM item_fts WHERE item_fts MATCH ?", (q,)
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
