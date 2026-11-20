#!/usr/bin/env python3
"""apply-fork-links.py - rewrite the update repo baked into RepoConfig.kt.

Usage:
    python scripts/apply-fork-links.py --in <template> --out <output> [--repo OWNER/REPO]

Rules:
  * Source priority: --repo > $GITHUB_REPOSITORY > $GITHUB_REPOSITORY_OWNER > default.
  * The default is the project's own repository; a different value simply re-points
    every update URL at the repository you publish from.
  * Only the automatic-update links are touched, never documentation prose.
"""
import argparse
import os
import re
import sys

DEFAULT_REPO = "13331271/harness-pocket"
PATTERN = re.compile(r"13331271/harness-pocket")


def resolve_repo(explicit):
    raw = (explicit or os.environ.get("GITHUB_REPOSITORY") or "").strip()
    if not raw:
        owner = (os.environ.get("GITHUB_REPOSITORY_OWNER") or "").strip()
        raw = f"{owner}/harness-pocket" if owner else DEFAULT_REPO
    if "/" not in raw:
        print(f"apply-fork-links: invalid repo '{raw}', fallback to {DEFAULT_REPO}", file=sys.stderr)
        raw = DEFAULT_REPO
    return raw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", required=True)
    ap.add_argument("--out", dest="dst", required=True)
    ap.add_argument("--repo", help="OWNER/REPO (defaults to $GITHUB_REPOSITORY)")
    args = ap.parse_args()

    if not os.path.isfile(args.src):
        print(f"apply-fork-links: template not found: {args.src}", file=sys.stderr)
        return 1

    target = resolve_repo(args.repo)
    text = open(args.src, encoding="utf-8").read()
    text, n = PATTERN.subn(target, text)
    print(f"apply-fork-links: {DEFAULT_REPO} -> {target} ({n} occurrence(s))")

    os.makedirs(os.path.dirname(os.path.abspath(args.dst)), exist_ok=True)
    with open(args.dst, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
