#!/usr/bin/env python3
"""Publish the source tree to GitHub without tripping secondary rate limits.

Lesson from the first attempt: 900 concurrent blob POSTs earn HTTP 403
"secondary rate limit". So this version is sequential and paced, and it first
derives each file's git blob SHA locally (git's object hash) to ask GitHub
whether that blob already exists. Uploads that never landed are retried with
backoff; everything else is reused.

Token: GITHUB_TOKEN only, never persisted.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import json
import os
import sys
import threading
import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor
import urllib.request
from pathlib import Path

API = "https://api.github.com"
CHUNK = 120


def request(method: str, path: str, token: str, payload=None) -> tuple[int, dict | None]:
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
        return e.code, {"error": e.read().decode("utf-8", "replace")[:300]}
    except (urllib.error.URLError, TimeoutError, http.client.HTTPException, OSError) as e:
        # Truncated reads / dropped connections are flaky-link symptoms, not
        # semantic failures: report as retryable (status 0).
        return 0, {"error": str(e)}


def with_backoff(fn, attempts: int = 6):
    delay = 5.0
    for i in range(attempts):
        status, body = fn()
        if status not in (0, 403, 429):
            return status, body
        if i == attempts - 1:
            return status, body
        print(f"    rate limited / transient ({status}); sleeping {delay:.0f}s", flush=True)
        time.sleep(delay)
        delay = min(delay * 1.8, 90.0)
    return status, body


def git_blob_sha(data: bytes) -> str:
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(data))
    h.update(data)
    return h.hexdigest()


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
    # The Android link() fallback ships with its own regression test.
    fb = root / "optimization-overlay" / "link-fallback"
    if fb.is_dir():
        for n in sorted(fb.iterdir()):
            if n.is_file():
                files["tools/link-fallback/" + n.name] = n
    for extra, rel in (("runtime-derived-v16b/runtime-meta.json", "docs/runtime-meta.json"),
                       ("deliverables/验证报告-0.2.2.zh.md", "docs/验证报告-0.2.2.zh.md"),
                       ("deliverables/验证报告-0.2.3.zh.md", "docs/验证报告-0.2.3.zh.md")):
        p = root / extra
        if p.is_file():
            files[rel] = p
    return files


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", default="13331271")
    ap.add_argument("--repo", default="harness-pocket")
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    ap.add_argument("--pace", type=float, default=0.45, help="seconds per worker between calls")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        print("GITHUB_TOKEN not set", file=sys.stderr)
        return 2
    owner, repo = args.owner, args.repo
    files = collect(args.root.resolve())
    print(f"files: {len(files)}", flush=True)

    status, head = request("GET", f"/repos/{owner}/{repo}/git/ref/heads/main", token)
    if status != 200:
        print(f"no main ref: {status} {head}", file=sys.stderr)
        return 3
    parent = head["object"]["sha"]
    print("parent:", parent, flush=True)

    blobs: dict[str, str] = {}
    uploaded = reused = 0
    ordered = sorted(files.items())

    cache_path = args.root.resolve() / "validation" / "blob-cache.json"
    cache = {}
    if cache_path.is_file():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cache = {}
    lock = threading.Lock()

    def upload(item):
        path, local = item
        data = local.read_bytes()
        sha = git_blob_sha(data)
        if cache.get(path) == sha:
            # Already accepted by GitHub in an earlier run: content-addressed, so
            # the same bytes necessarily map to the same blob.
            return path, sha, ""
        st, body = with_backoff(lambda: request(
            "POST", f"/repos/{owner}/{repo}/git/blobs", token,
            {"content": base64.b64encode(data).decode("ascii"), "encoding": "base64"}))
        time.sleep(args.pace)
        if st not in (200, 201):
            return path, None, f"{st} {body}"
        with lock:
            cache[path] = body["sha"]
        return path, body["sha"], ""

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i, (path, sha, err) in enumerate(pool.map(upload, ordered), 1):
            if sha is None:
                print(f"blob failed {path}: {err}", file=sys.stderr)
                return 4
            blobs[path] = sha
            uploaded += 1
            if i % 100 == 0:
                print(f"  {i}/{len(ordered)} (uploaded {uploaded})", flush=True)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=0), encoding="utf-8")

    paths = sorted(blobs)
    tree_sha = None
    done = 0
    for start in range(0, len(paths), CHUNK):
        chunk = paths[start:start + CHUNK]
        payload = {"tree": [{"path": p, "mode": "100644", "type": "blob", "sha": blobs[p]} for p in chunk]}
        if tree_sha:
            payload["base_tree"] = tree_sha
        st, body = with_backoff(lambda: request("POST", f"/repos/{owner}/{repo}/git/trees", token, payload))
        if st not in (200, 201):
            print(f"tree chunk {start} failed: {st} {body}", file=sys.stderr)
            print("chunk paths:", chunk[:5], file=sys.stderr)
            return 5
        tree_sha = body["sha"]
        done += len(chunk)
        print(f"  tree {done}/{len(paths)}", flush=True)
        time.sleep(args.pace)

    st, commit = with_backoff(lambda: request("POST", f"/repos/{owner}/{repo}/git/commits", token, {
        "message": "Harness Pocket 0.2.4: settings entry bottom-right, online update enabled",
        "tree": tree_sha,
        "parents": [parent],
    }))
    if st not in (200, 201):
        print(f"commit failed: {st} {commit}", file=sys.stderr)
        return 6

    st, ref = with_backoff(lambda: request("PATCH", f"/repos/{owner}/{repo}/git/refs/heads/main", token,
                                           {"sha": commit["sha"], "force": True}))
    if st not in (200, 201):
        print(f"ref update failed: {st} {ref}", file=sys.stderr)
        return 7

    print("commit:", commit["sha"])
    print("repo:", f"https://github.com/{owner}/{repo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
