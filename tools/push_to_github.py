#!/usr/bin/env python3
"""Publish the cleaned source tree to GitHub over the REST API.

No git binary is required. The token is read from the GITHUB_TOKEN environment
variable only: it is never written to any file, log or artifact.

Usage:
    set GITHUB_TOKEN=...  (PowerShell: $env:GITHUB_TOKEN="...")
    python build-scripts/push_to_github.py --owner 13331271 --repo harness-pocket --private

What gets published:
    app-source/  -> repository root (buildable Android project)
    build-scripts/ -> tools/ (debrand, packaging, signing, this script)
    runtime-derived/runtime-meta.json -> docs/runtime-meta.json
    deliverables/验证报告-0.2.0.zh.md -> docs/验证报告-0.2.0.zh.md

Excluded: build outputs, Gradle caches, keystores, signing secrets, temp files.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.github.com"
EXCLUDE_DIRS = {"build", ".gradle", ".git", "__pycache__", ".cxx", ".idea", "node_modules", "temp", "tmp"}
EXCLUDE_NAMES = {"local.properties"}
EXCLUDE_SUFFIX = (".p12", ".keystore", ".jks", ".log", ".class", ".pyc")


def request(method: str, path: str, token: str, payload=None):
    url = API + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "harness-pocket-publisher")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read()
            return resp.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        return e.code, {"error": detail}


def collect(root: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    app = root / "app-source"
    for base, dirs, names in os.walk(app):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for n in names:
            p = Path(base) / n
            if n in EXCLUDE_NAMES or n.lower().endswith(EXCLUDE_SUFFIX):
                continue
            files[p.relative_to(app).as_posix()] = p
    for n in sorted((root / "build-scripts").iterdir()):
        if n.is_file() and n.suffix in {".py", ".ps1"} and not n.name.startswith("_"):
            files["tools/" + n.name] = n
    meta = root / "runtime-derived" / "runtime-meta.json"
    if meta.is_file():
        files["docs/runtime-meta.json"] = meta
    report = root / "deliverables" / "验证报告-0.2.0.zh.md"
    if report.is_file():
        files["docs/验证报告-0.2.0.zh.md"] = report
    return files


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", default="13331271")
    ap.add_argument("--repo", default="harness-pocket")
    ap.add_argument("--private", action="store_true")
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        print("GITHUB_TOKEN is not set", file=sys.stderr)
        return 2

    files = collect(args.root.resolve())
    print(f"files to publish: {len(files)}")
    for k in list(files)[:5]:
        print("  ", k)

    if args.dry_run:
        return 0

    status, me = request("GET", "/user", token)
    if status != 200:
        print(f"token check failed: {status} {me}", file=sys.stderr)
        return 3
    login = me.get("login")
    print("authenticated as:", login)
    if login.lower() != args.owner.lower():
        print(f"warning: token owner {login} differs from --owner {args.owner}", file=sys.stderr)

    status, repo = request("GET", f"/repos/{args.owner}/{args.repo}", token)
    if status == 404:
        status, repo = request("POST", "/user/repos", token, {
            "name": args.repo,
            "description": "Harness Pocket - DeepSeek Harness local engine shell for Android (arm64)",
            "private": bool(args.private),
            "has_issues": True,
            "has_wiki": False,
            "auto_init": False,
        })
        if status not in (200, 201):
            print(f"repo create failed: {status} {repo}", file=sys.stderr)
            return 4
        print("created repository:", repo.get("full_name"))
    elif status == 200:
        print("repository exists:", repo.get("full_name"))
    else:
        print(f"repo lookup failed: {status} {repo}", file=sys.stderr)
        return 4

    # A brand-new repository has no commit, and the Git Data API rejects blob
    # creation with 409 "Git Repository is empty". Bootstrap one commit first,
    # then publish a standalone tree (no base_tree) whose parent is that commit:
    # the final tree contains exactly our files, the bootstrap file disappears.
    status, ref_probe = request("GET", f"/repos/{args.owner}/{args.repo}/git/ref/heads/main", token)
    parent_sha = None
    if status == 200:
        parent_sha = ref_probe.get("object", {}).get("sha")
        print("existing head:", parent_sha)
    else:
        status, boot = request("PUT", f"/repos/{args.owner}/{args.repo}/contents/.bootstrap", token, {
            "message": "chore: initialise repository",
            "content": base64.b64encode(b"Harness Pocket source bootstrap\n").decode("ascii"),
        })
        if status not in (200, 201):
            print(f"bootstrap commit failed: {status} {boot}", file=sys.stderr)
            return 4
        parent_sha = boot["commit"]["sha"]
        print("bootstrap commit:", parent_sha)

    # Empty repository: no refs yet. Create blobs, then one tree + commit.
    tree = []
    for i, (path, local) in enumerate(sorted(files.items()), 1):
        content = local.read_bytes()
        status, blob = request("POST", f"/repos/{args.owner}/{args.repo}/git/blobs", token, {
            "content": base64.b64encode(content).decode("ascii"),
            "encoding": "base64",
        })
        if status not in (200, 201):
            print(f"blob failed for {path}: {status} {blob}", file=sys.stderr)
            return 5
        tree.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        if i % 50 == 0:
            print(f"  uploaded {i}/{len(files)}")

    status, tree_resp = request("POST", f"/repos/{args.owner}/{args.repo}/git/trees", token, {"tree": tree})
    if status not in (200, 201):
        print(f"tree failed: {status} {tree_resp}", file=sys.stderr)
        return 6

    status, commit = request("POST", f"/repos/{args.owner}/{args.repo}/git/commits", token, {
        "message": "Harness Pocket 0.2.0: identity cleanup, remote host, licence page",
        "tree": tree_resp["sha"],
        "parents": [parent_sha] if parent_sha else [],
    })
    if status not in (200, 201):
        print(f"commit failed: {status} {commit}", file=sys.stderr)
        return 7

    if parent_sha:
        status, ref = request("PATCH", f"/repos/{args.owner}/{args.repo}/git/refs/heads/main", token, {
            "sha": commit["sha"],
            "force": True,
        })
    else:
        status, ref = request("POST", f"/repos/{args.owner}/{args.repo}/git/refs", token, {
            "ref": "refs/heads/main",
            "sha": commit["sha"],
        })
    if status not in (200, 201):
        print(f"ref failed: {status} {ref}", file=sys.stderr)
        return 8

    print("pushed commit:", commit["sha"])
    print("repository:", f"https://github.com/{args.owner}/{args.repo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
