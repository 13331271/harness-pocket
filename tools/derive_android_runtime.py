"""Produce a checksum-identified, native-fixed runtime from one pinned input.

Never modifies the publisher ZIP or extracts/executes its programs. Every original
ZIP entry/permission/link is preserved except explicit public adapter changes.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import os
import sys
from pathlib import Path
import time
import zipfile

SOURCE_SHA = "fab5cd6689840e1e86625080924c3aa0fdbcb7bee6db3ef98aaee2ecdc1b0394"
FLOCK = "lib/node_modules/@deepseek-ai/node-addon-system/lib/flock.js"
NATIVE = "lib/node_modules/@deepseek-ai/node-addon-system/lib/pocket_flock.node"
JSONL = "lib/node_modules/@deepseek-ai/dsh-session-persistence-jsonl/lib/index.js"
PTY = "lib/node_modules/node-pty/lib/index.js"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--flock-js", type=Path, required=True)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--pty-js", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expect-sha", default=SOURCE_SHA,
                        help="pinned SHA-256 of the reviewed publisher runtime")
    parser.add_argument("--expect-engine", default="0.2.2-rc.1",
                        help="DSH engine version the publisher runtime must declare")
    args = parser.parse_args()
    with args.source.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != args.expect_sha:
        raise ValueError("Unexpected publisher input: refusing an unreviewed runtime")
    if args.output.exists():
        raise FileExistsError("Refusing to overwrite an existing derived runtime")
    native = args.native.read_bytes()
    if native[:6] != b"\x7fELF\x02\x01" or native[18:20] != b"\xb7\x00":
        raise ValueError("Native locking payload is not Android ARM64 ELF64")
    changes = {FLOCK: args.flock_js.read_bytes(), NATIVE: native,
               PTY: args.pty_js.read_bytes()}
    if b"pocket_flock.node" not in changes[FLOCK] or b"LOCK_EX" not in args.native.with_name("flock.c").read_bytes():
        raise ValueError("Real native file-locking adapter evidence is missing")
    if b"child.stdout.pause()" not in changes[PTY] or b"_stdoutEnded" not in changes[PTY]:
        raise ValueError("Reviewed PTY backpressure/EOF adapter is missing")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.source) as source:
        if source.testzip() is not None:
            raise ValueError("Publisher ZIP CRC check failed")
        names = source.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate publisher ZIP entries")
        if NATIVE in names:
            raise ValueError("Publisher unexpectedly contains the local native payload")
        for name in names:
            lower = name.lower()
            if any(value in lower for value in ("dsh_alpine", "framesrv")):
                raise ValueError("Restricted container payload in runtime")
        jsonl = source.read(JSONL).decode("utf-8")
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from patch_jsonl_link_android import patch as patch_jsonl
        # Real kernel link() for no-clobber publication, plus an Android
        # fallback: SELinux denies link(2) in app data dirs (EACCES).
        changes[JSONL] = patch_jsonl(jsonl).encode("utf-8")
        build = json.loads(source.read("BUILD.json"))
        if build["engineVersion"] != args.expect_engine or build["abi"] != "arm64-v8a":
            raise ValueError("Unexpected engine or target ABI")
        content = hashlib.sha256()
        for name in sorted(set(names) | {NATIVE}):
            if name == "BUILD.json":
                continue
            data = changes[name] if name in changes else source.read(name)
            content.update(name.encode("utf-8") + b"\0")
            content.update(hashlib.sha256(data).hexdigest().encode("ascii") + b"\0")
        content_hash = content.hexdigest()
        build = {
            **build,
            "version": "2026.11.18-pocket-" + content_hash[:8],
            "builtAt": int(time.time()),
            "contentSha256": content_hash,
            "contentSha256Algorithm": "sha256(sorted zip entry names + NUL + entry content sha256 hex + NUL; BUILD.json excluded)",
            "upstreamRuntimeSha256": args.expect_sha,
            "pocketNativeFixes": {"kernelFlock": True, "noClobberPublication": True,
                                  "ptyBackpressureAndExit": True},
            "nativeFlockSha256": hashlib.sha256(native).hexdigest(),
        }
        changes["BUILD.json"] = (json.dumps(build, indent=2) + "\n").encode("utf-8")
        with zipfile.ZipFile(args.output, "w", compression=zipfile.ZIP_DEFLATED,
                             compresslevel=6, allowZip64=True) as target:
            for original in source.infolist():
                info = copy.copy(original)
                data = changes[info.filename] if info.filename in changes else source.read(info)
                target.writestr(info, data)
            info = zipfile.ZipInfo(NATIVE, (2026, 11, 18, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            target.writestr(info, native)
    with zipfile.ZipFile(args.output) as result:
        if result.testzip() is not None:
            raise ValueError("Derived ZIP CRC failed")
        unpacked = sum(entry.file_size for entry in result.infolist())
        patched_jsonl = result.read(JSONL)
        if b"rename as link" in patched_jsonl or b"void fd" in result.read(FLOCK):
            raise ValueError("Unsafe compatibility stubs remain")
        if b"publishNoClobber" not in patched_jsonl:
            raise ValueError("Android link() fallback missing from the derived runtime")
    with args.output.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    metadata = {"version": build["version"], "abi": build["abi"],
                "engineVersion": build["engineVersion"], "builtAt": build["builtAt"],
                "sha256": digest, "size": args.output.stat().st_size,
                "unpackedBytes": unpacked, "upstreamRuntimeSha256": args.expect_sha,
                "contentSha256": content_hash, "modifiedEntries": sorted(changes),
                "deviceExecution": "not yet verified"}
    meta_path = args.output.parent / "runtime-meta.json"
    if meta_path.exists():
        raise FileExistsError("Derived runtime metadata already exists")
    meta_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
