#!/usr/bin/env python3
"""
Update Metadata Script for DSUComfyCG Manager.

Downloads the latest curated metadata files from the ComfyUI-Manager
GitHub repository (ltdrdata/ComfyUI-Manager) and writes them into
Manager/data/. Maintains a manifest (metadata_version.json) with sha256
hashes so subsequent runs can skip unchanged files.

Ported from _ref_downloader/update_metadata.py. Standalone CLI tool —
not wired into the Manager UI or startup sequence.

Usage:
    python Manager/tools/update_metadata.py             # update all
    python Manager/tools/update_metadata.py --check-only # diff only, no writes
    python Manager/tools/update_metadata.py --force      # overwrite regardless

Exit codes:
    0 — all targets succeeded (or nothing to do)
    1 — at least one file failed to download or write
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# --------------------------------------------------------------------------
# Paths — resolved relative to this file so the script works regardless of
# the caller's CWD. Manager/tools/update_metadata.py → Manager/data/
# --------------------------------------------------------------------------
THIS_FILE = Path(__file__).resolve()
MANAGER_DIR = THIS_FILE.parent.parent          # .../Manager
DATA_DIR = MANAGER_DIR / "data"                # .../Manager/data
MANIFEST_FILE = DATA_DIR / "metadata_version.json"

GITHUB_RAW_BASE = "https://raw.githubusercontent.com/ltdrdata/ComfyUI-Manager/main"

# Files to fetch. Each entry maps remote filename to local filename under DATA_DIR.
#
# Only the three files that actually live upstream on ltdrdata/ComfyUI-Manager
# are fetched — these mirror the ref script's METADATA_FILES exactly. The ref
# project also ships `model-aliases.json` and `popular-models.json` under its
# own `metadata/` folder but those are NOT in the upstream ComfyUI-Manager repo
# (GET /model-aliases.json and /popular-models.json both return 404). They are
# locally curated in the ref project and in DSUComfyCG — not remotely sourced —
# so this updater leaves them alone. If upstream ever publishes them, add them
# back here.
METADATA_FILES = {
    "extension-node-map.json": {
        "remote": f"{GITHUB_RAW_BASE}/extension-node-map.json",
        "local": DATA_DIR / "extension-node-map.json",
        "description": "Node to GitHub URL mapping (used by checker.py NODE_DB)",
    },
    "model-list.json": {
        "remote": f"{GITHUB_RAW_BASE}/model-list.json",
        "local": DATA_DIR / "model-list.json",
        "description": "Model filename to type/dir/url (used by checker.py EXT_MODEL_DB)",
    },
    "custom-node-list.json": {
        "remote": f"{GITHUB_RAW_BASE}/custom-node-list.json",
        "local": DATA_DIR / "custom-node-list.json",
        "description": "Custom node registry reference",
    },
}

HTTP_TIMEOUT = 30
USER_AGENT = "DSUComfyCG-MetadataUpdater/1.0"


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.2f} MB"


def fetch(url: str) -> Optional[bytes]:
    """Download URL body, return bytes or None on any error."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        print(f"    HTTP {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        print(f"    Network error: {e.reason}")
    except Exception as e:  # noqa: BLE001 — best-effort
        print(f"    Error: {e}")
    return None


def load_manifest() -> dict:
    if not MANIFEST_FILE.exists():
        return {}
    try:
        with MANIFEST_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError) as e:
        print(f"[warn] Could not read manifest {MANIFEST_FILE.name}: {e}")
    return {}


def save_manifest(manifest: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = MANIFEST_FILE.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")
    tmp.replace(MANIFEST_FILE)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------
# Main logic
# --------------------------------------------------------------------------
def update(check_only: bool, force: bool) -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()

    print("=" * 64)
    print("DSUComfyCG Metadata Updater")
    print("=" * 64)
    print(f"Source : {GITHUB_RAW_BASE}")
    print(f"Target : {DATA_DIR}")
    mode = "check-only" if check_only else ("force" if force else "update")
    print(f"Mode   : {mode}")
    print("=" * 64)

    errors: list[str] = []
    updated: list[str] = []
    unchanged: list[str] = []
    created: list[str] = []

    for name, info in METADATA_FILES.items():
        print(f"\n[{name}]")
        print(f"  {info['description']}")

        local_path: Path = info["local"]
        local_hash = sha256_file(local_path)
        local_exists = local_path.exists()

        if local_exists:
            print(f"  Local : {fmt_size(local_path.stat().st_size)}")
        else:
            print("  Local : not found")

        print(f"  Fetching {info['remote']}")
        content = fetch(info["remote"])
        if content is None:
            print("  Status: FAILED (network)")
            errors.append(name)
            continue

        remote_hash = sha256_bytes(content)
        remote_size = len(content)
        print(f"  Remote: {fmt_size(remote_size)}  sha256={remote_hash[:12]}...")

        if not force and local_exists and local_hash == remote_hash:
            print("  Status: UNCHANGED (hash match) - skipping")
            unchanged.append(name)
            # Refresh manifest entry if missing so future runs have it
            if name not in manifest:
                manifest[name] = {
                    "sha256": remote_hash,
                    "last_updated_iso": now_iso(),
                    "size": remote_size,
                }
            continue

        if check_only:
            if not local_exists:
                print("  Status: NEW (would download)")
                created.append(name)
            else:
                print("  Status: UPDATE AVAILABLE (would overwrite)")
                updated.append(name)
            continue

        # Write atomically
        try:
            tmp = local_path.with_suffix(local_path.suffix + ".tmp")
            with tmp.open("wb") as f:
                f.write(content)
            tmp.replace(local_path)
        except OSError as e:
            print(f"  Status: FAILED to write: {e}")
            errors.append(name)
            continue

        if not local_exists:
            print(f"  Status: CREATED ({fmt_size(remote_size)})")
            created.append(name)
        else:
            print(f"  Status: UPDATED (new size: {fmt_size(remote_size)})")
            updated.append(name)

        manifest[name] = {
            "sha256": remote_hash,
            "last_updated_iso": now_iso(),
            "size": remote_size,
        }

    # Persist manifest unless we did a pure dry-run
    if not check_only:
        try:
            save_manifest(manifest)
        except OSError as e:
            print(f"\n[warn] Failed to write manifest: {e}")

    # Summary
    print("\n" + "=" * 64)
    print("SUMMARY")
    print("=" * 64)
    if created:
        print(f"  Created  : {len(created)} - {', '.join(created)}")
    if updated:
        print(f"  Updated  : {len(updated)} - {', '.join(updated)}")
    if unchanged:
        print(f"  Unchanged: {len(unchanged)}")
    if errors:
        print(f"  Errors   : {len(errors)} - {', '.join(errors)}")
    if check_only and (created or updated):
        print("\nRe-run without --check-only to apply updates.")
    print("=" * 64)

    return 0 if not errors else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="update_metadata",
        description="Refresh curated ComfyUI-Manager metadata into Manager/data/.",
    )
    g = p.add_mutually_exclusive_group()
    g.add_argument(
        "--check-only",
        action="store_true",
        help="Compare remote vs local, print diff, do not write.",
    )
    g.add_argument(
        "--force",
        action="store_true",
        help="Overwrite local files even if the hash matches.",
    )
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return update(check_only=args.check_only, force=args.force)


if __name__ == "__main__":
    sys.exit(main())
