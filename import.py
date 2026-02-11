#!/usr/bin/env python3
"""
ListHub Markdown Importer

Reads .md files from a local directory and pushes them to ListHub via the REST API.

Usage:
    python import.py --dir ~/notes --key mem_xxxxx
    python import.py --dir ~/notes --key mem_xxxxx --recursive --tags imported,notes
    python import.py --dir ~/notes --key mem_xxxxx --url http://localhost:3200 --dry-run
"""

import argparse
import fnmatch
import os
import re
import sys

import requests


# Default patterns to exclude (credential/secret files)
DEFAULT_EXCLUDE = [
    "*.env*",
    "*credentials*",
    "*secret*",
    "*.key",
    "*.pem",
    ".git/*",
    "node_modules/*",
    "__pycache__/*",
]


def slugify(filename):
    """Derive a URL slug from a filename (without extension)."""
    name = os.path.splitext(os.path.basename(filename))[0]
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-") or "untitled"


def extract_title(content, filename):
    """Extract title from the first markdown heading, or fall back to filename."""
    for line in content.splitlines():
        line = line.strip()
        match = re.match(r"^#{1,6}\s+(.+)$", line)
        if match:
            return match.group(1).strip()
    # Fall back to filename without extension
    return os.path.splitext(os.path.basename(filename))[0]


def detect_item_type(content):
    """
    Detect item type from content:
    - 'list' if the content has 3+ lines starting with '- '
    - 'document' if the content is longer than 500 characters
    - 'note' otherwise
    """
    list_lines = sum(1 for line in content.splitlines() if line.strip().startswith("- "))
    if list_lines >= 3:
        return "list"
    if len(content) > 500:
        return "document"
    return "note"


def should_exclude(filepath, exclude_patterns):
    """Check if a file matches any exclusion pattern."""
    basename = os.path.basename(filepath)
    relpath = filepath  # patterns checked against both basename and path
    for pattern in exclude_patterns:
        if fnmatch.fnmatch(basename, pattern):
            return True
        if fnmatch.fnmatch(relpath, pattern):
            return True
    return False


def collect_files(directory, recursive=False, exclude_patterns=None):
    """Collect all .md files from the directory."""
    exclude_patterns = exclude_patterns or DEFAULT_EXCLUDE
    files = []

    if recursive:
        for root, dirs, filenames in os.walk(directory):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for name in filenames:
                if name.lower().endswith(".md"):
                    full_path = os.path.join(root, name)
                    rel_path = os.path.relpath(full_path, directory)
                    if not should_exclude(rel_path, exclude_patterns):
                        files.append(full_path)
    else:
        for name in sorted(os.listdir(directory)):
            if name.lower().endswith(".md"):
                full_path = os.path.join(directory, name)
                if os.path.isfile(full_path) and not should_exclude(name, exclude_patterns):
                    files.append(full_path)

    return sorted(files)


def import_file(filepath, base_dir, api_url, api_key, tags, visibility, dry_run=False):
    """Import a single markdown file to ListHub. Returns (success, message)."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return False, f"Failed to read: {e}"

    rel_path = os.path.relpath(filepath, base_dir)
    title = extract_title(content, filepath)
    slug = slugify(filepath)
    item_type = detect_item_type(content)
    file_path = rel_path if not rel_path.startswith("..") else os.path.basename(filepath)

    payload = {
        "title": title,
        "content": content,
        "slug": slug,
        "item_type": item_type,
        "visibility": visibility,
        "file_path": file_path,
        "tags": tags,
    }

    if dry_run:
        return True, f"[dry-run] Would create: title={title!r}, slug={slug!r}, type={item_type}, {len(content)} chars"

    try:
        url = f"{api_url.rstrip('/')}/api/v1/items/new"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=30)

        if resp.status_code == 201:
            data = resp.json()
            return True, f"Created: id={data.get('id')}, slug={data.get('slug')}, type={item_type}"
        else:
            error_msg = resp.text[:200]
            return False, f"HTTP {resp.status_code}: {error_msg}"

    except requests.ConnectionError:
        return False, f"Connection failed: {api_url}"
    except requests.Timeout:
        return False, "Request timed out (30s)"
    except Exception as e:
        return False, f"Request error: {e}"


def main():
    parser = argparse.ArgumentParser(
        description="Import markdown files into ListHub via the REST API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python import.py --dir ~/notes --key mem_xxxxx
  python import.py --dir ~/notes --key mem_xxxxx --recursive
  python import.py --dir ~/notes --key mem_xxxxx --tags imported,notes
  python import.py --dir ~/notes --key mem_xxxxx --url http://localhost:3200 --dry-run
  python import.py --dir ~/notes --key mem_xxxxx --exclude "*.draft.md" "scratch*"
        """,
    )

    parser.add_argument(
        "--dir", required=True,
        help="Directory containing markdown files to import",
    )
    parser.add_argument(
        "--key", required=True,
        help="ListHub API key (Bearer token, starts with mem_)",
    )
    parser.add_argument(
        "--url", default="https://listhub.globalbr.ai",
        help="ListHub base URL (default: https://listhub.globalbr.ai)",
    )
    parser.add_argument(
        "--recursive", action="store_true",
        help="Recursively scan subdirectories",
    )
    parser.add_argument(
        "--tags", default="",
        help="Comma-separated tags to apply to all imported items (e.g. imported,notes)",
    )
    parser.add_argument(
        "--visibility", default="private", choices=["private", "shared", "public"],
        help="Visibility for imported items (default: private)",
    )
    parser.add_argument(
        "--exclude", nargs="*", default=None,
        help="Additional glob patterns to exclude (default excludes credential files)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be imported without actually doing it",
    )

    args = parser.parse_args()

    # Validate directory
    directory = os.path.expanduser(args.dir)
    if not os.path.isdir(directory):
        print(f"Error: {directory} is not a directory", file=sys.stderr)
        sys.exit(1)

    # Build exclude patterns
    exclude_patterns = list(DEFAULT_EXCLUDE)
    if args.exclude:
        exclude_patterns.extend(args.exclude)

    # Build tags list
    tags = [t.strip().lower() for t in args.tags.split(",") if t.strip()] if args.tags else []

    # Collect files
    files = collect_files(directory, recursive=args.recursive, exclude_patterns=exclude_patterns)

    if not files:
        print("No .md files found in", directory)
        sys.exit(0)

    print(f"Found {len(files)} markdown file(s) in {directory}")
    if args.dry_run:
        print("[DRY RUN MODE -- no changes will be made]")
    print()

    # Import each file
    successes = 0
    failures = []

    for i, filepath in enumerate(files, 1):
        rel = os.path.relpath(filepath, directory)
        print(f"[{i}/{len(files)}] {rel} ... ", end="", flush=True)

        ok, msg = import_file(
            filepath, directory, args.url, args.key, tags, args.visibility, dry_run=args.dry_run
        )

        if ok:
            successes += 1
            print(msg)
        else:
            failures.append((rel, msg))
            print(f"FAILED: {msg}")

    # Summary
    print()
    print(f"Done. {successes}/{len(files)} imported successfully.")

    if failures:
        print(f"\n{len(failures)} failure(s):")
        for name, msg in failures:
            print(f"  - {name}: {msg}")
        sys.exit(1)


if __name__ == "__main__":
    main()
