"""Validate and safely extract a downloaded ZIP, without inline-shell quoting."""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
from pathlib import Path, PurePosixPath
import stat
import zipfile


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--sha256")
    parser.add_argument("--sha1")
    parser.add_argument("--exclude", action="append", default=[])
    args = parser.parse_args()
    archive = args.archive.resolve(strict=True)
    destination = args.destination.resolve()
    if args.sha256 or args.sha1:
        algorithm = "sha256" if args.sha256 else "sha1"
        expected = args.sha256 or args.sha1
        with archive.open("rb") as stream:
            actual = hashlib.file_digest(stream, algorithm).hexdigest()
        if actual != expected.lower():
            raise ValueError("Archive checksum mismatch")
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError("Refusing to overwrite a nonempty extraction directory")
    with zipfile.ZipFile(archive) as source:
        if source.testzip() is not None:
            raise ValueError("ZIP integrity check failed")
        selected = []
        for entry in source.infolist():
            path = PurePosixPath(entry.filename.replace("\\", "/"))
            if path.is_absolute() or ".." in path.parts or ":" in entry.filename:
                raise ValueError("Unsafe archive path")
            target = (destination / str(path)).resolve()
            if not target.is_relative_to(destination):
                raise ValueError("Archive entry escapes extraction directory")
            if stat.S_ISLNK(entry.external_attr >> 16):
                raise ValueError("Unexpected symlink in toolchain/source archive")
            if any(fnmatch.fnmatch(entry.filename, pattern) for pattern in args.exclude):
                continue
            selected.append(entry)
        destination.mkdir(parents=True, exist_ok=True)
        for entry in selected:
            source.extract(entry, destination)
    print(f"Extracted {len(selected)} verified entries to {destination}", flush=True)


if __name__ == "__main__":
    main()
