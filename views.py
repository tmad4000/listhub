import markdown
from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import login_required, current_user
from nanoid import generate as nanoid

from db import get_db, reindex_item
from api import slugify

views_bp = Blueprint('views', __name__)


def render_md(text):
    return markdown.markdown(
        text or '',
        extensions=['tables', 'fenced_code', 'toc', 'nl2br', 'sane_lists']
    )


@views_bp.route('/')
def landing():
    if current_user.is_authenticated:
        return redirect(url_for('views.dashboard'))

    db = get_db()
    public_items = db.execute(
        "SELECT i.*, u.username FROM item i JOIN user u ON i.owner_id = u.id "
        "WHERE i.visibility = 'public' ORDER BY i.updated_at DESC LIMIT 20"
    ).fetchall()

    return render_template('landing.html', items=public_items)


@views_bp.route('/explore')
def explore():
    db = get_db()
    q = request.args.get('q', '').strip()

    public_items = db.execute(
        "SELECT i.*, u.username FROM item i JOIN user u ON i.owner_id = u.id "
        "WHERE i.visibility = 'public' ORDER BY i.updated_at DESC LIMIT 50"
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

    return render_template('explore.html', items=items, q=q)


@views_bp.route('/dash')
@login_required
def dashboard():
    db = get_db()
    visibility_filter = request.args.get('visibility')
    q = request.args.get('q', '').strip()

    query = "SELECT * FROM item WHERE owner_id = ?"
    params = [current_user.id]

    if visibility_filter:
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

    return render_template('dash.html', items=items_with_tags, q=q, visibility_filter=visibility_filter)


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

        return redirect(url_for('views.dashboard'))

    tags = db.execute("SELECT tag FROM item_tag WHERE item_id = ?", (item_id,)).fetchall()
    tags_str = ', '.join(t['tag'] for t in tags)

    return render_template('edit.html', item=item, tags_str=tags_str)


@views_bp.route('/dash/delete/<item_id>', methods=['POST'])
@login_required
def delete_item(item_id):
    db = get_db()
    db.execute("DELETE FROM item WHERE id = ? AND owner_id = ?", (item_id, current_user.id))
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

    items = db.execute(
        "SELECT * FROM item WHERE owner_id = ? AND visibility = 'public' ORDER BY updated_at DESC",
        (user.id,)
    ).fetchall()

    items_with_tags = []
    for item in items:
        tags = db.execute("SELECT tag FROM item_tag WHERE item_id = ?", (item['id'],)).fetchall()
        items_with_tags.append({**dict(item), 'tags': [t['tag'] for t in tags]})

    return render_template('profile.html', profile_user=user, items=items_with_tags)


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
    if item['visibility'] == 'public':
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
    rendered_content = render_md(item['content'])

    return render_template(
        'item.html',
        item=item,
        profile_user=user,
        tags=[t['tag'] for t in tags],
        rendered_content=rendered_content
    )


@views_bp.route('/i/<item_id>')
def short_link(item_id):
    db = get_db()
    item = db.execute("SELECT i.*, u.username FROM item i JOIN user u ON i.owner_id = u.id WHERE i.id = ?", (item_id,)).fetchone()
    if not item:
        abort(404)

    if item['visibility'] == 'public':
        return redirect(url_for('views.public_item', username=item['username'], slug=item['slug']))

    if current_user.is_authenticated and current_user.id == item['owner_id']:
        return redirect(url_for('views.public_item', username=item['username'], slug=item['slug']))

    abort(404)
