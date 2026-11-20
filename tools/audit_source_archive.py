"""Verify the clean source ZIP manifest and reject private/restricted artifacts."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import PurePosixPath, Path
import re
import zipfile

FORBIDDEN_SUFFIXES = (".keystore", ".jks", ".p12", ".pfx", ".apk", ".aab")
FORBIDDEN_NAMES = {"local.properties", ".env", "signing-secret.json", "release.properties",
                   "debug.properties", "google-services.json"}
PRIVATE_MARKERS = (b"-----BEGIN PRIVATE KEY-----", b"-----BEGIN RSA PRIVATE KEY-----",
                   b"-----BEGIN EC PRIVATE KEY-----", b"-----BEGIN OPENSSH PRIVATE KEY-----")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args()
    expected_sha = args.expected_sha256.lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
        raise ValueError("Expected source SHA-256 must be 64 lowercase hex characters")
    with args.archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != expected_sha:
        raise ValueError("Source archive SHA-256 changed")
    with zipfile.ZipFile(args.archive) as source:
        if source.testzip() is not None:
            raise ValueError("Source ZIP CRC failure")
        names = source.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate source ZIP entries")
        manifest_name = "Harness-Pocket-source/SOURCE-MANIFEST.json"
        manifest = json.loads(source.read(manifest_name))
        declared = {row["path"]: row for row in manifest}
        checked = 0
        fixture_markers = []
        allowed_marker_sources = {
            "optimization-overlay/apk-audit/test_apk_audit.py",  # fake detection fixture
            "build-scripts/audit_mobile_bundle.py",              # scanner marker literal
            "build-scripts/audit_source_archive.py",              # scanner marker literals
        }
        for info in source.infolist():
            name = info.filename
            if name == manifest_name:
                continue
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or "\\" in name or not name.startswith("Harness-Pocket-source/"):
                raise ValueError("Unsafe source archive path")
            relative = name.removeprefix("Harness-Pocket-source/")
            lower = relative.lower()
            base = path.name.lower()
            if base in FORBIDDEN_NAMES or lower.endswith(FORBIDDEN_SUFFIXES):
                raise ValueError("Private/build artifact filename found in source archive")
            if any(value in lower for value in ("dsh_alpine", "framesrv", "build-private/", "/toolchain/", "/runtime-input/")):
                raise ValueError("Restricted/private/toolchain payload found in source archive")
            data = source.read(info)
            if any(marker in data for marker in PRIVATE_MARKERS):
                # The auditor's generated-fixture test must contain a fake marker
                # to prove detection. No other source entry may contain one.
                if relative not in allowed_marker_sources:
                    raise ValueError("Private key marker found outside scanner/test sources: " + relative)
                fixture_markers.append(relative)
            row = declared.get(relative)
            if row is None or row.get("bytes") != len(data) or row.get("sha256") != hashlib.sha256(data).hexdigest():
                raise ValueError("Source manifest mismatch")
            checked += 1
        if checked != len(declared):
            raise ValueError("Source manifest contains missing or extra entries")
        if set(fixture_markers) != allowed_marker_sources or len(fixture_markers) != len(allowed_marker_sources):
            raise ValueError("Expected only the exact private-key scanner/test marker sources")
    print(json.dumps({"sha256": digest, "entries_verified": checked,
                      "real_private_key_markers": 0, "scanner_and_fake_fixture_marker_sources": 3,
                      "restricted_components": 0, "signing_materials": 0}, indent=2))


if __name__ == "__main__":
    main()
