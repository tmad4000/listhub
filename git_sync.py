"""
ListHub Phase 2: DB -> Git Sync

Mirror database items to per-user bare git repos as markdown files
with YAML frontmatter. Uses git plumbing commands (no working tree needed).

Usage as CLI:
    python git_sync.py              # sync all users
    python git_sync.py jacob        # sync specific user
"""

import os
import subprocess
import sqlite3
import sys
import tempfile

REPO_ROOT = os.environ.get('LISTHUB_REPO_ROOT', '/home/ubuntu/listhub/repos')
DB_PATH = os.environ.get('LISTHUB_DB', os.path.join(os.path.dirname(__file__), 'listhub.db'))


def _repo_path(username):
    """Return filesystem path for a user's bare repo."""
    safe = ''.join(c for c in username if c.isalnum())
    return os.path.join(REPO_ROOT, f'{safe}.git')


def _git(repo_path, *args, env=None, input=None):
    """Run a git command in the context of a bare repo. Returns stdout as string."""
    cmd = ['git', '-C', repo_path] + list(args)
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=merged_env,
        input=input,
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, cmd, result.stdout, result.stderr
        )
    return result.stdout.strip()


def _git_bytes(repo_path, *args, env=None, input=None):
    """Run a git command with binary input. Returns stdout as bytes."""
    cmd = ['git', '-C', repo_path] + list(args)
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    result = subprocess.run(
        cmd,
        capture_output=True,
        env=merged_env,
        input=input,
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, cmd, result.stdout, result.stderr
        )
    return result.stdout


def generate_frontmatter(item, tags):
    """Generate markdown content with YAML frontmatter from an item dict."""
    lines = ['---']
    lines.append(f'title: {item["title"]}')
    lines.append(f'slug: {item["slug"]}')
    lines.append(f'visibility: {item["visibility"]}')
    lines.append(f'type: {item["item_type"]}')
    if tags:
        tags_str = ', '.join(tags)
        lines.append(f'tags: [{tags_str}]')
    lines.append('---')
    lines.append('')

    content = item.get('content') or ''
    lines.append(content)

    return '\n'.join(lines)


def _head_tree(repo_path):
    """Get the tree hash of HEAD, or None if repo has no commits."""
    try:
        return _git(repo_path, 'rev-parse', '--verify', 'HEAD^{tree}')
    except subprocess.CalledProcessError:
        return None


def _head_commit(repo_path):
    """Get the commit hash of HEAD, or None if repo has no commits."""
    try:
        return _git(repo_path, 'rev-parse', '--verify', 'HEAD')
    except subprocess.CalledProcessError:
        return None


_AUTHOR_ENV = {
    'GIT_AUTHOR_NAME': 'ListHub',
    'GIT_AUTHOR_EMAIL': 'sync@listhub',
    'GIT_COMMITTER_NAME': 'ListHub',
    'GIT_COMMITTER_EMAIL': 'sync@listhub',
}


def sync_item_to_repo(username, item_id):
    """
    Incremental sync: write a single item to the user's bare repo.
    Call after creating or updating an item.
    """
    repo = _repo_path(username)
    if not os.path.isdir(repo):
        return

    item, tags = _get_item_with_tags(item_id)
    if not item:
        return

    file_path = item.get('file_path') or f"{item['slug']}.md"
    content = generate_frontmatter(item, tags)

    head = _head_commit(repo)
    idx = tempfile.mktemp(prefix='listhub-sync-', suffix='.idx')
    env = {'GIT_INDEX_FILE': idx}

    try:
        # Read current tree into index (if repo has commits)
        if head:
            _git(repo, 'read-tree', 'HEAD', env=env)

        # Write content as a blob
        blob = _git_bytes(
            repo, 'hash-object', '-w', '--stdin',
            input=content.encode('utf-8'),
            env=env
        ).strip().decode()

        # Update the index entry
        _git(repo, 'update-index', '--add', '--cacheinfo',
             '100644', blob, file_path, env=env)

        # Write index as tree
        new_tree = _git(repo, 'write-tree', env=env)

        # Check if tree changed
        old_tree = _head_tree(repo) if head else None
        if new_tree == old_tree:
            return  # No change

        # Create commit
        commit_args = ['commit-tree', new_tree, '-m', f'Sync: update {file_path}']
        if head:
            commit_args[2:2] = ['-p', head]

        new_commit = _git(repo, *commit_args, env={**env, **_AUTHOR_ENV})

        # Update ref
        _git(repo, 'update-ref', 'refs/heads/main', new_commit)
    finally:
        if os.path.exists(idx):
            os.unlink(idx)


def remove_from_repo(username, file_path):
    """
    Remove a single file from the user's bare repo.
    Call after deleting an item.
    """
    repo = _repo_path(username)
    if not os.path.isdir(repo):
        return

    head = _head_commit(repo)
    if not head:
        return  # No commits, nothing to remove

    idx = tempfile.mktemp(prefix='listhub-sync-', suffix='.idx')
    env = {'GIT_INDEX_FILE': idx}

    try:
        # Read current tree
        _git(repo, 'read-tree', 'HEAD', env=env)

        # Remove the file from index (--index-info works in bare repos)
        _git(repo, 'update-index', '--index-info', env=env,
             input=f'0 0000000000000000000000000000000000000000\t{file_path}\n')

        # Write new tree
        new_tree = _git(repo, 'write-tree', env=env)
        old_tree = _head_tree(repo)

        if new_tree == old_tree:
            return  # No change

        # Create commit
        new_commit = _git(
            repo, 'commit-tree', new_tree, '-p', head,
            '-m', f'Remove {file_path}',
            env={**env, **_AUTHOR_ENV}
        )

        # Update ref
        _git(repo, 'update-ref', 'refs/heads/main', new_commit)
    finally:
        if os.path.exists(idx):
            os.unlink(idx)


def sync_user_repo(username):
    """
    Full sync: write all DB items for a user to their bare repo.
    Idempotent -- if nothing changed, no commit is created.
    Removes orphaned .md files that don't correspond to DB items.
    Preserves non-.md files.
    """
    repo = _repo_path(username)
    if not os.path.isdir(repo):
        print(f'  No repo found for {username}, skipping')
        return

    items_with_tags = _get_all_items_for_user(username)
    if not items_with_tags:
        print(f'  No items for {username}')
        return

    head = _head_commit(repo)
    idx = tempfile.mktemp(prefix=f'listhub-sync-{username}-', suffix='.idx')
    env = {'GIT_INDEX_FILE': idx}

    try:
        # If repo has commits, read current tree to preserve non-.md files
        existing_md_files = set()
        if head:
            _git(repo, 'read-tree', 'HEAD', env=env)
            # List all .md files in current tree
            try:
                ls_output = _git(repo, 'ls-tree', '-r', '--name-only', 'HEAD')
                for f in ls_output.split('\n'):
                    f = f.strip()
                    if f and f.endswith('.md'):
                        existing_md_files.add(f)
            except subprocess.CalledProcessError:
                pass

        # Track which .md files we're writing (to detect orphans)
        written_files = set()

        for item, tags in items_with_tags:
            file_path = item.get('file_path') or f"{item['slug']}.md"
            content = generate_frontmatter(item, tags)

            # Write blob
            blob = _git_bytes(
                repo, 'hash-object', '-w', '--stdin',
                input=content.encode('utf-8'),
                env=env
            ).strip().decode()

            # Update index
            _git(repo, 'update-index', '--add', '--cacheinfo',
                 '100644', blob, file_path, env=env)
            written_files.add(file_path)

        # Remove orphaned .md files (in existing tree but not in DB)
        orphaned = existing_md_files - written_files
        if orphaned:
            # Use --index-info to remove files (works in bare repos)
            remove_input = ''.join(
                f'0 0000000000000000000000000000000000000000\t{f}\n'
                for f in orphaned
            )
            _git(repo, 'update-index', '--index-info', env=env,
                 input=remove_input)

        # Write tree
        new_tree = _git(repo, 'write-tree', env=env)
        old_tree = _head_tree(repo) if head else None

        if new_tree == old_tree:
            print(f'  {username}: no changes')
            return

        # Create commit
        n_items = len(items_with_tags)
        message = f'Sync {n_items} items from database'
        commit_args = ['commit-tree', new_tree, '-m', message]
        if head:
            commit_args[2:2] = ['-p', head]

        new_commit = _git(repo, *commit_args, env={**env, **_AUTHOR_ENV})

        # Update ref
        _git(repo, 'update-ref', 'refs/heads/main', new_commit)

        removed_str = f', removed {len(orphaned)} orphaned' if orphaned else ''
        print(f'  {username}: synced {n_items} items{removed_str} -> {new_commit[:8]}')
    finally:
        if os.path.exists(idx):
            os.unlink(idx)


# ---------------------------------------------------------------------------
# DB helpers (work in Flask context or standalone)
# ---------------------------------------------------------------------------

def _get_item_with_tags(item_id):
    """Get an item and its tags. Works in Flask context or standalone."""
    try:
        from flask import has_app_context
        if has_app_context():
            from db import get_db
            db = get_db()
            item = db.execute("SELECT * FROM item WHERE id = ?", (item_id,)).fetchone()
            if not item:
                return None, []
            tags = db.execute(
                "SELECT tag FROM item_tag WHERE item_id = ?", (item_id,)
            ).fetchall()
            return dict(item), [t['tag'] for t in tags]
    except ImportError:
        pass

    # Outside Flask context -- use direct DB connection
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        item = conn.execute("SELECT * FROM item WHERE id = ?", (item_id,)).fetchone()
        if not item:
            return None, []
        tags = conn.execute(
            "SELECT tag FROM item_tag WHERE item_id = ?", (item_id,)
        ).fetchall()
        return dict(item), [t['tag'] for t in tags]
    finally:
        conn.close()


def _get_all_items_for_user(username):
    """Get all items for a user with tags. Direct DB connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        user = conn.execute(
            "SELECT id FROM user WHERE username = ?", (username,)
        ).fetchone()
        if not user:
            return []

        items = conn.execute(
            "SELECT * FROM item WHERE owner_id = ? ORDER BY file_path",
            (user['id'],)
        ).fetchall()

        result = []
        for item in items:
            tags = conn.execute(
                "SELECT tag FROM item_tag WHERE item_id = ?", (item['id'],)
            ).fetchall()
            result.append((dict(item), [t['tag'] for t in tags]))
        return result
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    if len(sys.argv) > 1:
        usernames = sys.argv[1:]
    else:
        # Sync all users
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        users = conn.execute("SELECT username FROM user ORDER BY username").fetchall()
        usernames = [u['username'] for u in users]
        conn.close()

    print(f'Syncing {len(usernames)} user(s) to git repos...')
    for username in usernames:
        print(f'\n{username}:')
        try:
            sync_user_repo(username)
        except Exception as e:
            print(f'  ERROR: {e}', file=sys.stderr)

    print('\nDone.')
