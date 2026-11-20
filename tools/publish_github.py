#!/usr/bin/env python3
"""Publish the source tree to GitHub (parallel blobs, chunked trees).

Why not one big tree: a single 900-entry tree POST failed with an opaque error
and gave no way to tell which entry was rejected. Chunking turns that into a
precise, retryable failure and also keeps each request small.

Token: read from GITHUB_TOKEN only. Never written to disk.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

API = "https://api.github.com"
CHUNK = 150


def request(method: str, path: str, token: str, payload=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(API + path, data=data, method=method)
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "harness-pocket-publisher")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = resp.read()
            return resp.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode("utf-8", "replace")[:600]}


def collect(root: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    app = root / "app-source"
    skip_dirs = {"build", ".gradle", ".git", "__pycache__", ".cxx", ".idea", "node_modules", "temp", "tmp"}
    skip_names = {"local.properties"}
    skip_suffix = (".p12", ".keystore", ".jks", ".log", ".class", ".pyc")
    for base, dirs, names in os.walk(app):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for n in names:
            p = Path(base) / n
            if n in skip_names or n.lower().endswith(skip_suffix):
                continue
            files[p.relative_to(app).as_posix()] = p
    for n in sorted((root / "build-scripts").iterdir()):
        if n.is_file() and n.suffix in {".py", ".ps1"} and not n.name.startswith("_"):
            files["tools/" + n.name] = n
    for extra, rel in (("runtime-derived/runtime-meta.json", "docs/runtime-meta.json"),
                       ("deliverables/验证报告-0.2.0.zh.md", "docs/验证报告-0.2.0.zh.md")):
        p = root / extra
        if p.is_file():
            files[rel] = p
    return files


def upload_blob(args) -> tuple[str, str | None, str]:
    owner, repo, token, path, local = args
    content = Path(local).read_bytes()
    status, body = request("POST", f"/repos/{owner}/{repo}/git/blobs", token, {
        "content": base64.b64encode(content).decode("ascii"),
        "encoding": "base64",
    })
    if status not in (200, 201):
        return path, None, f"{status} {body}"
    return path, body["sha"], ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", default="13331271")
    ap.add_argument("--repo", default="harness-pocket")
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        print("GITHUB_TOKEN not set", file=sys.stderr)
        return 2
    owner, repo = args.owner, args.repo
    files = collect(args.root.resolve())
    print(f"files: {len(files)}")

    status, head = request("GET", f"/repos/{owner}/{repo}/git/ref/heads/main", token)
    if status != 200:
        print(f"no main ref: {status} {head}", file=sys.stderr)
        return 3
    parent = head["object"]["sha"]
    print("parent:", parent)

    tasks = [(owner, repo, token, path, str(local)) for path, local in sorted(files.items())]
    blobs: dict[str, str] = {}
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i, (path, sha, err) in enumerate(pool.map(upload_blob, tasks), 1):
            if sha is None:
                errors.append(f"{path}: {err}")
            else:
                blobs[path] = sha
            if i % 100 == 0:
                print(f"  blobs {i}/{len(tasks)}")
    if errors:
        print("blob failures:", file=sys.stderr)
        for e in errors[:10]:
            print("  ", e, file=sys.stderr)
        return 4

    paths = sorted(blobs)
    tree_sha = None
    created = 0
    for start in range(0, len(paths), CHUNK):
        chunk = paths[start:start + CHUNK]
        payload = {"tree": [{"path": p, "mode": "100644", "type": "blob", "sha": blobs[p]} for p in chunk]}
        if tree_sha:
            payload["base_tree"] = tree_sha
        status, body = request("POST", f"/repos/{owner}/{repo}/git/trees", token, payload)
        if status not in (200, 201):
            print(f"tree chunk {start}-{start+len(chunk)} failed: {status} {body}", file=sys.stderr)
            print("first paths in chunk:", chunk[:5], file=sys.stderr)
            return 5
        tree_sha = body["sha"]
        created += len(chunk)
        print(f"  tree {created}/{len(paths)}")

    status, commit = request("POST", f"/repos/{owner}/{repo}/git/commits", token, {
        "message": "Harness Pocket 0.2.2: engine 0.2.2-rc.5, status island moved into settings, identity cleanup",
        "tree": tree_sha,
        "parents": [parent],
    })
    if status not in (200, 201):
        print(f"commit failed: {status} {commit}", file=sys.stderr)
        return 6

    status, ref = request("PATCH", f"/repos/{owner}/{repo}/git/refs/heads/main", token,
                          {"sha": commit["sha"], "force": True})
    if status not in (200, 201):
        print(f"ref update failed: {status} {ref}", file=sys.stderr)
        return 7

    print("commit:", commit["sha"])
    print("repo:", f"https://github.com/{owner}/{repo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
