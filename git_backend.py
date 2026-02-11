"""
Git Smart HTTP Backend for ListHub.

Provides HTTPS clone/pull/push for per-user bare repos.
Each user gets a repo at LISTHUB_REPO_ROOT/{username}.git

Usage:
    app.register_blueprint(git_bp)

Then:
    git clone https://user:password@host/git/user.git
    git push origin main

Auth: HTTP Basic Auth against ListHub username + password (bcrypt)
      or username + API key as password.
Users can only access their own repo.

Environment variables:
    LISTHUB_REPO_ROOT  - where bare repos live (default: /home/ubuntu/listhub/repos)
    LISTHUB_ADMIN_TOKEN - internal token for post-receive hook to call API
    LISTHUB_BASE_URL   - base URL for API calls from hooks (default: http://localhost:3200)
"""

import os
import subprocess
import stat
import shutil

import bcrypt
from flask import Blueprint, request, Response, abort

from db import get_db
from models import User
from auth import hash_api_key

git_bp = Blueprint('git', __name__, url_prefix='/git')

REPO_ROOT = os.environ.get('LISTHUB_REPO_ROOT', '/home/ubuntu/listhub/repos')
ADMIN_TOKEN = os.environ.get('LISTHUB_ADMIN_TOKEN', '')
BASE_URL = os.environ.get('LISTHUB_BASE_URL', 'http://localhost:3200')

# Path to the hook template (relative to this file)
HOOK_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hooks')


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _check_basic_auth():
    """
    Validate HTTP Basic Auth credentials.

    Accepts either:
      - username + account password (bcrypt)
      - username + API key as password (SHA-256 lookup)

    Returns a User object on success, or None.
    """
    auth = request.authorization
    if not auth or not auth.username or not auth.password:
        return None

    db = get_db()
    user = User.get_by_username(db, auth.username)
    if not user:
        return None

    # Try bcrypt password first
    try:
        if bcrypt.checkpw(auth.password.encode(), user.password_hash.encode()):
            return user
    except Exception:
        pass

    # Try API key: hash the provided password and look it up
    key_hash = hash_api_key(auth.password)
    key_row = db.execute(
        "SELECT user_id FROM api_key WHERE key_hash = ? AND user_id = ?",
        (key_hash, user.id)
    ).fetchone()
    if key_row:
        return user

    return None


def _require_auth(username):
    """
    Enforce that the request has valid Basic Auth for the given username.
    Returns the User on success or aborts with 401/403.
    """
    user = _check_basic_auth()
    if not user:
        return Response(
            'Authentication required\n',
            status=401,
            headers={'WWW-Authenticate': 'Basic realm="ListHub Git"'}
        )
    if user.username != username:
        abort(403)
    return user


# ---------------------------------------------------------------------------
# Repo management
# ---------------------------------------------------------------------------

def _repo_path(username):
    """Return the filesystem path for a user's bare repo."""
    # Sanitize: username is already validated as alphanumeric by registration
    safe = ''.join(c for c in username if c.isalnum())
    return os.path.join(REPO_ROOT, f'{safe}.git')


def init_user_repo(username):
    """
    Create a bare git repo for a user if it doesn't already exist.
    Installs the post-receive hook.

    Call this on user registration.
    Returns the repo path.
    """
    repo = _repo_path(username)

    if not os.path.isdir(repo):
        os.makedirs(repo, exist_ok=True)
        subprocess.run(
            ['git', 'init', '--bare', repo],
            check=True,
            capture_output=True
        )

        # Set HEAD to main instead of master
        subprocess.run(
            ['git', 'symbolic-ref', 'HEAD', 'refs/heads/main'],
            cwd=repo,
            check=True,
            capture_output=True
        )

        # Enable http.receivepack so push works over HTTP
        subprocess.run(
            ['git', 'config', 'http.receivepack', 'true'],
            cwd=repo,
            check=True,
            capture_output=True
        )

    # Install post-receive hook (always overwrite to keep it current)
    _install_hook(repo, username)

    return repo


def _install_hook(repo_path, username):
    """
    Install the post-receive hook into the bare repo.
    The hook is a self-contained Python script that syncs pushed .md files
    into the ListHub database via the API.
    """
    hooks_dir = os.path.join(repo_path, 'hooks')
    os.makedirs(hooks_dir, exist_ok=True)

    hook_src = os.path.join(HOOK_DIR, 'post-receive')
    hook_dst = os.path.join(hooks_dir, 'post-receive')

    # Copy the template
    shutil.copy2(hook_src, hook_dst)

    # Make it executable
    st = os.stat(hook_dst)
    os.chmod(hook_dst, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    # Write a small config file next to the hook so it knows who it belongs to
    config_path = os.path.join(hooks_dir, 'listhub.conf')
    with open(config_path, 'w') as f:
        f.write(f'LISTHUB_USERNAME={username}\n')
        f.write(f'LISTHUB_BASE_URL={BASE_URL}\n')
        f.write(f'LISTHUB_ADMIN_TOKEN={ADMIN_TOKEN}\n')


# ---------------------------------------------------------------------------
# Git Smart HTTP routes
# ---------------------------------------------------------------------------

def _git_command_path(cmd):
    """
    Find the full path to a git sub-command binary.
    Git smart HTTP needs to invoke git-upload-pack / git-receive-pack directly.
    """
    # Try git --exec-path first
    result = subprocess.run(
        ['git', '--exec-path'],
        capture_output=True, text=True
    )
    exec_path = result.stdout.strip()
    candidate = os.path.join(exec_path, cmd)
    if os.path.isfile(candidate):
        return candidate

    # Fall back to just the command name (relies on PATH)
    return cmd


@git_bp.route('/<username>.git/info/refs')
def info_refs(username):
    """
    Smart HTTP discovery endpoint.
    Git clients hit this first to discover what the server supports.
    """
    auth_result = _require_auth(username)
    if isinstance(auth_result, Response):
        return auth_result

    service = request.args.get('service', '')
    if service not in ('git-upload-pack', 'git-receive-pack'):
        abort(400)

    repo = _repo_path(username)
    if not os.path.isdir(repo):
        # Auto-create repo on first access
        init_user_repo(username)

    cmd = _git_command_path(service)

    proc = subprocess.Popen(
        [cmd, '--stateless-rpc', '--advertise-refs', repo],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout, stderr = proc.communicate()

    if proc.returncode != 0:
        return Response(f'Git error: {stderr.decode()}\n', status=500)

    # Build the smart HTTP response:
    # First line is a pkt-line with "# service=git-upload-pack\n"
    # then a flush-pkt (0000), then the actual refs from git
    service_line = f'# service={service}\n'
    pkt_len = len(service_line) + 4  # 4 hex digits for the length prefix
    pkt = f'{pkt_len:04x}{service_line}'

    body = pkt.encode() + b'0000' + stdout

    content_type = f'application/x-{service}-advertisement'
    return Response(
        body,
        status=200,
        content_type=content_type,
        headers={
            'Cache-Control': 'no-cache',
        }
    )


@git_bp.route('/<username>.git/git-upload-pack', methods=['POST'])
def upload_pack(username):
    """Handle git clone / fetch / pull."""
    auth_result = _require_auth(username)
    if isinstance(auth_result, Response):
        return auth_result

    repo = _repo_path(username)
    if not os.path.isdir(repo):
        abort(404)

    cmd = _git_command_path('git-upload-pack')
    return _run_git_service(cmd, repo, 'application/x-git-upload-pack-result')


@git_bp.route('/<username>.git/git-receive-pack', methods=['POST'])
def receive_pack(username):
    """Handle git push."""
    auth_result = _require_auth(username)
    if isinstance(auth_result, Response):
        return auth_result

    repo = _repo_path(username)
    if not os.path.isdir(repo):
        # Auto-create on push too
        init_user_repo(username)

    cmd = _git_command_path('git-receive-pack')
    return _run_git_service(cmd, repo, 'application/x-git-receive-pack-result')


def _run_git_service(cmd, repo, content_type):
    """
    Run a git service command (upload-pack or receive-pack) in stateless-rpc mode.
    Pipes the HTTP request body to the command's stdin and streams stdout back.
    """
    input_data = request.get_data()

    proc = subprocess.Popen(
        [cmd, '--stateless-rpc', repo],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout, stderr = proc.communicate(input=input_data)

    if proc.returncode != 0 and not stdout:
        return Response(f'Git error: {stderr.decode()}\n', status=500)

    return Response(
        stdout,
        status=200,
        content_type=content_type,
        headers={
            'Cache-Control': 'no-cache',
        }
    )
