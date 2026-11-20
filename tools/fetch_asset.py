"""Download a pinned public release asset with bounded, resumable HTTP ranges.

All bytes are checked against a publisher-provided SHA-256 before atomic promotion.
This script installs or executes nothing; it only downloads the requested asset.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

ALLOWED_HOSTS = {
    "github.com", "api.github.com", "release-assets.githubusercontent.com",
    "objects.githubusercontent.com", "downloads.gradle.org",
    "download.visualstudio.microsoft.com", "dl.google.com", "aka.ms",
}
CHUNK_SIZE = 4 * 1024 * 1024


def validate_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError("Only an explicitly allowed HTTPS publisher/CDN host is accepted")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Credentials in a download URL are not accepted")
    return url


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def opener():
    return urllib.request.build_opener(SafeRedirect())


def resolved_url(url: str, expected_size: int) -> tuple[str, int]:
    request = urllib.request.Request(validate_url(url), headers={
        "User-Agent": "DSH-Android-build/1.0",
        "Accept": "application/octet-stream",
        "Accept-Encoding": "identity",
        "Range": "bytes=0-0",
    })
    with opener().open(request, timeout=60) as response:
        final = validate_url(response.geturl())
        if "application/json" in response.headers.get("Content-Type", ""):
            raise ValueError("Publisher returned JSON metadata, not a binary asset")
        match = re.fullmatch(r"bytes [0-9]+-[0-9]+/([0-9]+)",
                             response.headers.get("Content-Range", ""))
        length = response.headers.get("Content-Length")
        total = int(match.group(1)) if match else (
            int(length) if response.status == 200 and length else 0)
        if total <= 0:
            raise ValueError("Publisher did not provide a complete asset size")
        if expected_size and total != expected_size:
            raise ValueError("Publisher asset length does not match pinned metadata")
        # Closing immediately avoids downloading the complete asset a second time.
        return final, total


def read_part(url: str, start: int, end: int, total: int, target: Path) -> None:
    wanted = end - start + 1
    if target.is_file() and target.stat().st_size == wanted:
        print(f"reuse {start // CHUNK_SIZE + 1}", flush=True)
        return
    temporary = target.with_suffix(".partial")
    for attempt in range(1, 5):
        try:
            request = urllib.request.Request(validate_url(url), headers={
                "User-Agent": "DSH-Android-build/1.0",
                "Accept": "application/octet-stream",
                "Accept-Encoding": "identity",
                "Range": f"bytes={start}-{end}",
            })
            with opener().open(request, timeout=90) as response:
                content_range = response.headers.get("Content-Range", "")
                expected_range = f"bytes {start}-{end}/{total}"
                if response.status != 206 or content_range != expected_range:
                    raise ValueError(f"Invalid HTTP byte range ({response.status})")
                received = 0
                with temporary.open("wb") as output:
                    while received < wanted:
                        block = response.read(min(256 * 1024, wanted - received))
                        if not block:
                            raise IOError("Asset response ended before the requested range")
                        output.write(block)
                        received += len(block)
                    if response.read(1):
                        raise IOError("Asset response exceeded the requested range")
            os.replace(temporary, target)
            print(f"downloaded chunk {start // CHUNK_SIZE + 1}", flush=True)
            return
        except (OSError, ValueError, urllib.error.URLError) as error:
            # Do not print signed CDN URLs or query parameters from HTTP exceptions.
            print(f"chunk {start // CHUNK_SIZE + 1}, attempt {attempt}: {type(error).__name__}",
                  file=sys.stderr, flush=True)
            if attempt == 4:
                raise RuntimeError(f"Chunk {start // CHUNK_SIZE + 1} failed four times") from None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--size", type=int, default=0,
                        help="Pinned size; 0 derives it from authenticated HTTPS metadata")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--resume-prefix", type=Path,
                        help="Reuse complete chunks of a failed, unverified download; final SHA-256 is still mandatory")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-fA-F0-9]{64}", args.sha256) or args.size < 0:
        raise ValueError("A pinned SHA-256 and nonnegative expected size are required")
    if not 1 <= args.workers <= 4:
        raise ValueError("Use between one and four download workers")
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        with output.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if (not args.size or output.stat().st_size == args.size) and digest == args.sha256.lower():
            print("Existing download matches the pinned digest")
            return
        raise FileExistsError("Refusing to overwrite an existing unverified output")
    parts = output.parent / (output.name + ".parts")
    parts.mkdir(exist_ok=True)
    if not parts.resolve().is_relative_to(output.parent):
        raise ValueError("Download parts directory escapes the declared output directory")
    print("Resolving public publisher asset redirect", flush=True)
    final, args.size = resolved_url(args.url, args.size)
    print(f"CDN: {urllib.parse.urlsplit(final).hostname}; size={args.size}", flush=True)
    ranges = [(start, min(start + CHUNK_SIZE, args.size) - 1)
              for start in range(0, args.size, CHUNK_SIZE)]
    if args.resume_prefix:
        prefix = args.resume_prefix.resolve(strict=True)
        prefix_size = prefix.stat().st_size
        if prefix_size > args.size:
            raise ValueError("Resume prefix is larger than the publisher asset")
        with prefix.open("rb") as stream:
            for index, (start, end) in enumerate(ranges):
                if end >= prefix_size:
                    break
                target = parts / f"{index:05d}.part"
                if target.exists():
                    continue
                if not target.resolve().is_relative_to(output.parent):
                    raise ValueError("Download chunk escapes the declared output directory")
                stream.seek(start)
                with target.open("xb") as chunk:
                    remaining = end - start + 1
                    while remaining:
                        block = stream.read(min(1024 * 1024, remaining))
                        if not block:
                            raise IOError("Resume prefix changed while reading")
                        chunk.write(block)
                        remaining -= len(block)
        print("Imported complete prefix chunks; they remain untrusted until the final SHA-256 check", flush=True)
    print(f"Downloading {len(ranges)} verified HTTP ranges", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(read_part, final, start, end, args.size,
                                   parts / f"{index:05d}.part")
                   for index, (start, end) in enumerate(ranges)]
        for future in concurrent.futures.as_completed(futures):
            future.result()
    assembled = output.with_suffix(output.suffix + ".assembling")
    digest = hashlib.sha256()
    written = 0
    with assembled.open("wb") as result:
        for index, (start, end) in enumerate(ranges):
            part = parts / f"{index:05d}.part"
            if part.stat().st_size != end - start + 1:
                raise IOError("A downloaded chunk changed after verification")
            with part.open("rb") as stream:
                while block := stream.read(1024 * 1024):
                    digest.update(block)
                    written += len(block)
                    result.write(block)
    actual = digest.hexdigest()
    if written != args.size or actual != args.sha256.lower():
        raise ValueError("Publisher SHA-256 verification failed; file was not promoted")
    os.replace(assembled, output)
    print(json.dumps({"path": str(output), "size": written, "sha256": actual}), flush=True)


if __name__ == "__main__":
    main()
