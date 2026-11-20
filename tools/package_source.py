"""Package only explicit source roots; never include build caches or signing keys."""
from __future__ import annotations
import argparse
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import zipfile

TOP_FILES = [
    "app-source/README.md", "app-source/LICENSE", "app-source/NOTICE", "app-source/community-plugins.json", "app-source/.gitignore", "app-source/.gitattributes",
    "app-source/build.gradle.kts", "app-source/settings.gradle.kts", "app-source/gradle.properties",
    "app-source/app/build.gradle.kts", "app-source/app/proguard-rules.pro",
    "app-source/scripts/apply-fork-links.py", "app-source/scripts/patch-webview-polyfill.py",
    "app-source/scripts/write-runtime-manifest.py", "runtime-derived/runtime-meta.json",
    "native-flock/flock.c", "native-flock/flock-wrapper.mjs", "native-flock/flock-wrapper.test.mjs",
    "native-flock/native-export-report.json", "native-flock/pocket_flock.node",
    "optimization-overlay/apk-audit/apk_audit.py",
    "optimization-overlay/apk-audit/test_apk_audit.py",
    "optimization-overlay/apk-audit/README.md",
]
SOURCE_DIRS = ["app-source/app/src", "app-source/vendor/mobile-layout", "native-flock/include",
               "build-scripts", "optimization-overlay/pty-fix"]
EXCLUDED_PARTS = {"build", ".gradle", ".git", "__pycache__", "temp", "tmp", "test-tmp", "fixtures-tmp"}
FORBIDDEN_PATTERNS = ["*dsh_alpine*", "*framesrv*", "*.keystore", "*.jks", "*.p12", "*.pfx",
                      "*signing-secret*", "*.env", "local.properties"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError("Source archive already exists")
    selected = {}
    def add(path):
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(root) or path.is_symlink():
            raise ValueError("Unexpected source path or symlink")
        relative = path.relative_to(root).as_posix()
        lower = relative.lower()
        if any(part in EXCLUDED_PARTS for part in Path(relative).parts):
            return
        if "app/src/main/assets/linux/" in lower:
            return
        if any(fnmatch.fnmatch(lower, pattern) for pattern in FORBIDDEN_PATTERNS):
            return
        if path.suffix.lower() in {".log", ".class", ".pyc"}:
            return
        if path.name in {"integration.diff"}:
            return
        selected[relative] = path
    for name in TOP_FILES:
        path = root / name
        if not path.is_file():
            raise FileNotFoundError("Required source artifact missing: " + name)
        add(path)
    for name in SOURCE_DIRS:
        directory = root / name
        if not directory.is_dir():
            raise FileNotFoundError("Required source directory missing: " + name)
        for parent, dirs, files in os.walk(directory):
            dirs[:] = [value for value in dirs if value not in EXCLUDED_PARTS]
            for name in files:
                add(Path(parent) / name)
    manifest = [{"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                 "bytes": path.stat().st_size} for name, path in sorted(selected.items())]
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as target:
        for name, path in sorted(selected.items()):
            target.write(path, "Harness-Pocket-source/" + name)
        target.writestr("Harness-Pocket-source/SOURCE-MANIFEST.json",
                        json.dumps(manifest, indent=2) + "\n")
    with zipfile.ZipFile(output) as result:
        if result.testzip() is not None:
            raise ValueError("Source ZIP CRC failed")
        for name in result.namelist():
            lower = name.lower()
            if any(fnmatch.fnmatch(lower, pattern) for pattern in FORBIDDEN_PATTERNS):
                raise ValueError("Forbidden artifact in source ZIP")
    with output.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    print(json.dumps({"path": str(output), "entries": len(manifest),
                      "size": output.stat().st_size, "sha256": digest}, indent=2))


if __name__ == "__main__":
    main()

