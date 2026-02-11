import sqlite3
import os

DB_PATH = os.environ.get('LISTHUB_DB', os.path.join(os.path.dirname(__file__), 'listhub.db'))


def get_db():
    from flask import g
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


def close_db(e=None):
    from flask import g
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    conn.executescript("""
    CREATE TABLE IF NOT EXISTS user (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        display_name TEXT,
        email TEXT UNIQUE,
        password_hash TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS item (
        id TEXT PRIMARY KEY,
        owner_id TEXT NOT NULL REFERENCES user(id),
        slug TEXT NOT NULL,
        title TEXT,
        content TEXT DEFAULT '',
        file_path TEXT,
        item_type TEXT DEFAULT 'note',
        visibility TEXT DEFAULT 'private',
        revision INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(owner_id, slug)
    );

    CREATE TABLE IF NOT EXISTS item_tag (
        item_id TEXT NOT NULL REFERENCES item(id) ON DELETE CASCADE,
        tag TEXT NOT NULL,
        PRIMARY KEY (item_id, tag)
    );

    CREATE TABLE IF NOT EXISTS item_version (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id TEXT NOT NULL REFERENCES item(id) ON DELETE CASCADE,
        content TEXT,
        revision INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS share (
        item_id TEXT NOT NULL REFERENCES item(id) ON DELETE CASCADE,
        shared_with TEXT NOT NULL,
        permission TEXT DEFAULT 'read',
        PRIMARY KEY (item_id, shared_with)
    );

    CREATE TABLE IF NOT EXISTS api_key (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES user(id) ON DELETE CASCADE,
        key_hash TEXT NOT NULL,
        name TEXT,
        scopes TEXT DEFAULT 'read,write',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # FTS5 virtual table for full-text search
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='item_fts'"
    )
    if not cur.fetchone():
        conn.execute("""
        CREATE VIRTUAL TABLE item_fts USING fts5(
            title, content, tags,
            tokenize='porter unicode61'
        );
        """)

    conn.commit()
    conn.close()


def reindex_item(db, item_id):
    """Update FTS index for a single item."""
    item = db.execute("SELECT rowid, id, title, content FROM item WHERE id = ?", (item_id,)).fetchone()
    if not item:
        return
    tags_row = db.execute(
        "SELECT GROUP_CONCAT(tag, ' ') FROM item_tag WHERE item_id = ?", (item_id,)
    ).fetchone()
    tags = tags_row[0] or '' if tags_row else ''
    rowid = item['rowid']

    # Delete old entry then insert new
    db.execute("DELETE FROM item_fts WHERE rowid = ?", (rowid,))
    db.execute(
        "INSERT INTO item_fts(rowid, title, content, tags) VALUES (?, ?, ?, ?)",
        (rowid, item['title'] or '', item['content'] or '', tags)
    )
