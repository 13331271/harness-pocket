"""Read and verify the exact bundled mobile plugin tarball without executing it."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tarfile
import zipfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apk", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    entry = "assets/mobile-layout/xiaopb-dsh-mobile-layout-0.4.5.tgz"
    expected = "46674f3d557e93d5085d2c64de3882a6602df6113ff0fdd95ccad0d43f1c957d"
    with zipfile.ZipFile(args.apk) as apk:
        data = apk.read(entry)
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected:
        raise ValueError("Bundled plugin tarball SHA-256 mismatch")
    findings, names, manifest = [], [], None
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as source:
        members = source.getmembers()
        if len(members) > 10000:
            raise ValueError("Unexpectedly large plugin archive")
        for member in members:
            name = member.name
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
                findings.append({"path": name, "kind": "unsafe_path"})
            if name in names:
                findings.append({"path": name, "kind": "duplicate"})
            names.append(name)
            if member.issym() or member.islnk() or not (member.isdir() or member.isfile()):
                findings.append({"path": name, "kind": "unexpected_link_or_special"})
            lower = name.lower()
            if any(value in lower for value in ("dsh_alpine", "framesrv", ".keystore", "signing-secret")):
                findings.append({"path": name, "kind": "restricted_component_or_signing_file"})
            if member.isfile():
                if member.size > 10 * 1024 * 1024:
                    raise ValueError("Plugin entry exceeds bounded content scan")
                payload = source.extractfile(member).read()
                if b"-----BEGIN PRIVATE KEY-----" in payload or b"-----BEGIN RSA PRIVATE KEY-----" in payload:
                    findings.append({"path": name, "kind": "private_key"})
                if name == "package/package.json":
                    manifest = json.loads(payload)
    if manifest is None or manifest.get("name") != "@xiaopb/dsh-mobile-layout" or manifest.get("version") != "0.4.5":
        raise ValueError("Plugin identity does not match the actual tarball")
    report = {"entry": entry, "sha256": digest, "entries": len(names),
              "package": {key: manifest.get(key) for key in ("name", "version", "license", "engines", "peerDependencies")},
              "findings": findings, "contents_static_status": "pass" if not findings else "fail",
              "plugin_execution": "not verified on Android device"}
    if args.output.exists():
        raise FileExistsError("Plugin audit report already exists")
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if findings:
        raise RuntimeError("Bundled plugin content needs review")


if __name__ == "__main__":
    main()
