#!/usr/bin/env python3
"""
Import a tree of markdown files into ListHub as items.

Walks a directory of .md files, creates one ListHub item per file using
the upsert-by-slug endpoint (PUT /api/v1/items/by-slug/:slug), preserving
the folder hierarchy via the item's file_path field.

Slug collisions across subfolders are avoided by including parent-folder
segments in the slug (e.g. foodslist/tea.md → foodslist-tea).

Safe to re-run — each call is an idempotent upsert (content updated,
revision bumped). Set --visibility and --tag-prefix as needed.

Examples:

    # Dry run — show what would happen, don't hit the API
    import_markdown.py --data-dir ~/code/DataExports/markdown-by-hierarchy --dry-run

    # Actual import, private visibility, tag everything
    LISTHUB_ADMIN_TOKEN=ec51... import_markdown.py \\
        --data-dir ~/code/DataExports/markdown-by-hierarchy \\
        --visibility private \\
        --tag systematicawesome --tag google-docs-import

    # Run against a different user or instance
    import_markdown.py --data-dir ./docs \\
        --username alice --api-base https://listhub.example.com/api/v1
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def slugify(text: str) -> str:
    s = text.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-") or "untitled"


def strip_frontmatter(content: str) -> str:
    """Strip YAML frontmatter block if present."""
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            return parts[2].lstrip()
    return content


def extract_title(content: str, fallback: str) -> str:
    """Extract title from first markdown heading, or fall back."""
    for line in content.splitlines()[:20]:
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()[:200]
    for line in content.splitlines()[:20]:
        line = line.strip()
        if line.startswith("## ") or line.startswith("### "):
            return line.lstrip("#").strip()[:200]
    return fallback


def detect_type(content: str, stem: str) -> str:
    """Guess item_type from content shape."""
    if "list" in stem.lower():
        return "list"
    bullet_lines = sum(1 for line in content.splitlines() if line.lstrip().startswith("- "))
    total_lines = max(1, len([l for l in content.splitlines() if l.strip()]))
    if bullet_lines / total_lines > 0.4 and bullet_lines >= 5:
        return "list"
    return "document"


def build_slug(rel_path: Path) -> str:
    """Flatten a nested relative path into a single slug.

    foodslist/tea.md            → foodslist-tea
    burningman.md               → burningman
    a/b/c/deeply-nested.md      → a-b-c-deeply-nested
    """
    if rel_path.parent == Path("."):
        base = rel_path.stem
    else:
        base = str(rel_path.with_suffix("")).replace("/", "-").replace("_", "-")
    return slugify(base)


def build_tags(rel_path: Path, tag_prefix: list[str]) -> list[str]:
    """Build tag list: prefix tags + top-level folder if nested."""
    tags = list(tag_prefix)
    if rel_path.parent != Path("."):
        top_folder = str(rel_path).split("/")[0]
        if top_folder not in tags:
            tags.append(top_folder)
    return tags


def put_item(api_base: str, slug: str, payload: dict, headers: dict, timeout: int = 60) -> tuple[int, str]:
    """PUT an item via upsert-by-slug. Returns (status_code, body)."""
    url = f"{api_base}/items/by-slug/{slug}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers=headers,
        method="PUT",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode(errors="replace")


def main() -> int:
    p = argparse.ArgumentParser(
        description="Import markdown files into ListHub.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--data-dir", type=Path, required=True,
                   help="Root directory to walk for .md files")
    p.add_argument("--api-base", default="https://listhub.globalbr.ai/api/v1",
                   help="ListHub API base URL (default: prod)")
    p.add_argument("--username", default="jacobreal",
                   help="Owner username to import as (default: jacobreal)")
    p.add_argument("--token", default=os.environ.get("LISTHUB_ADMIN_TOKEN", ""),
                   help="Admin bearer token (default: $LISTHUB_ADMIN_TOKEN)")
    p.add_argument("--visibility", default="private",
                   choices=["private", "public", "public_edit", "shared"],
                   help="Visibility for imported items (default: private)")
    p.add_argument("--tag", action="append", default=[],
                   help="Tag to apply to every item (repeatable)")
    p.add_argument("--skip-root-index", action="store_true", default=True,
                   help="Skip root-level index.md (default: true)")
    p.add_argument("--delay", type=float, default=0.05,
                   help="Seconds between requests (default: 0.05)")
    p.add_argument("--dry-run", action="store_true",
                   help="Print what would happen, don't hit the API")
    p.add_argument("--user-agent", default="Mozilla/5.0 listhub-import",
                   help="User-Agent header (bypass CDN bot filters)")
    args = p.parse_args()

    if not args.data_dir.exists() or not args.data_dir.is_dir():
        print(f"error: --data-dir {args.data_dir} does not exist or is not a directory", file=sys.stderr)
        return 2

    if not args.dry_run and not args.token:
        print("error: --token is required (or set LISTHUB_ADMIN_TOKEN)", file=sys.stderr)
        return 2

    headers = {
        "Authorization": f"Bearer {args.token}",
        "X-ListHub-User": args.username,
        "Content-Type": "application/json",
        "User-Agent": args.user_agent,
    }

    files = sorted(args.data_dir.rglob("*.md"))
    print(f"Found {len(files)} markdown files under {args.data_dir}")
    if args.dry_run:
        print("[DRY RUN] no API calls will be made")
    print()

    stats = {"created": 0, "updated": 0, "skipped": 0, "errors": 0}
    errors: list[str] = []

    for i, f in enumerate(files, 1):
        rel_path = f.relative_to(args.data_dir)
        rel_str = str(rel_path)

        if args.skip_root_index and rel_str == "index.md":
            stats["skipped"] += 1
            continue

        try:
            content = f.read_text(errors="replace")
        except Exception as e:
            errors.append(f"{rel_str}: read failed — {e}")
            stats["errors"] += 1
            continue

        content = strip_frontmatter(content)
        if not content.strip():
            stats["skipped"] += 1
            print(f"[{i:4d}/{len(files)}] skip (empty) {rel_str}")
            continue

        stem = f.stem
        slug = build_slug(rel_path)
        title = extract_title(content, stem.replace("-", " ").replace("_", " ").title())
        tags = build_tags(rel_path, args.tag)
        item_type = detect_type(content, stem)

        payload = {
            "title": title,
            "content": content,
            "item_type": item_type,
            "visibility": args.visibility,
            "file_path": rel_str,
            "tags": tags,
        }

        marker = "dry" if args.dry_run else "new"
        line = (
            f"[{i:4d}/{len(files)}] {marker} {slug:50s} "
            f"({len(content):6d} B, {item_type:8s}) — {rel_str}"
        )

        if args.dry_run:
            stats["created"] += 1  # assume it would create
            print(line)
            continue

        try:
            code, _body = put_item(args.api_base, slug, payload, headers)
            if code == 201:
                stats["created"] += 1
            else:
                stats["updated"] += 1
                line = line.replace(" new ", " upd ")
            print(line)
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:300]
            errors.append(f"{rel_str} ({slug}): HTTP {e.code} — {body}")
            stats["errors"] += 1
            print(f"[{i:4d}/{len(files)}] ERR {e.code:3d} {slug:50s} — {body[:80]}")
        except Exception as e:
            errors.append(f"{rel_str} ({slug}): {e}")
            stats["errors"] += 1
            print(f"[{i:4d}/{len(files)}] ERR EXC {slug:50s} — {e}")

        time.sleep(args.delay)

    print()
    print("=" * 80)
    print(
        f"Summary: created={stats['created']} updated={stats['updated']} "
        f"skipped={stats['skipped']} errors={stats['errors']}"
    )
    if errors:
        print()
        print("Errors:")
        for e in errors:
            print(f"  {e}")

    return 0 if stats["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
