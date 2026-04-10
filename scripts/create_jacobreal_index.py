#!/usr/bin/env python3
"""Create a 'home' index item for the jacobreal account on ListHub.

Run from the listhub project root (or set LISTHUB_DB env var).
"""
import os
import sys
import sqlite3
from datetime import datetime, timezone

# Resolve DB path: env var or default sibling file
DB_PATH = os.environ.get(
    "LISTHUB_DB",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "listhub.db"),
)


def main():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: Database not found at {DB_PATH}")
        print("Set LISTHUB_DB env var or run from the listhub project root.")
        sys.exit(1)

    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row

    # Look up jacobreal user
    user = db.execute("SELECT id, username FROM user WHERE username = 'jacobreal'").fetchone()
    if not user:
        print("ERROR: User 'jacobreal' not found in the database.")
        db.close()
        sys.exit(1)

    owner_id = user["id"]
    print(f"Found user jacobreal (id={owner_id})")

    # Check if home item already exists
    existing = db.execute(
        "SELECT id, slug, title FROM item WHERE owner_id = ? AND slug = 'home'",
        (owner_id,),
    ).fetchone()

    if existing:
        print(f"Item already exists: id={existing['id']}, slug={existing['slug']}, title={existing['title']}")
        print("No changes made.")
        db.close()
        return

    # Generate a nanoid-style ID (simple fallback: use os.urandom hex)
    try:
        from nanoid import generate as nanoid
        item_id = nanoid()
    except ImportError:
        import secrets
        item_id = secrets.token_urlsafe(16)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    content = "# jacobreal\n\nWelcome to jacobreal on ListHub.\n"

    db.execute(
        "INSERT INTO item (id, owner_id, slug, title, content, file_path, item_type, visibility, revision, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (item_id, owner_id, "home", "jacobreal", content, "home.md", "note", "public", 1, now, now),
    )
    db.commit()
    print(f"Created item: id={item_id}, slug=home, title=jacobreal, visibility=public, file_path=home.md")
    db.close()


if __name__ == "__main__":
    main()
