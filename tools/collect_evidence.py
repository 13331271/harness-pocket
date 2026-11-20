#!/usr/bin/env python3
"""Collect every verification result for a Harness Pocket build into one JSON.

The point is repeatability: anyone can re-run this after a rebuild and diff the
result instead of trusting a prose report.

    python build-scripts/collect_evidence.py --apk deliverables/Harness-Pocket-0.2.0-arm64.apk
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import verify_identity  # noqa: E402  (same directory, intentional)


def sha256(path: str) -> str:
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def test_totals(results_dir: str) -> dict:
    total = failures = skipped = suites = 0
    if os.path.isdir(results_dir):
        for name in sorted(os.listdir(results_dir)):
            if not name.endswith(".xml"):
                continue
            try:
                suite = ET.parse(os.path.join(results_dir, name)).getroot()
            except ET.ParseError:
                continue
            suites += 1
            total += int(suite.get("tests", 0))
            failures += int(suite.get("failures", 0)) + int(suite.get("errors", 0))
            skipped += int(suite.get("skipped", 0))
    return {"suites": suites, "tests": total, "failures": failures, "skipped": skipped}


def run(cmd: list[str], tail: int = 4000) -> dict:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        # aapt badging prints one line per locale label; tail must be generous
        # enough not to cut the header (package:/sdkVersion:), which is the part
        # that matters.
        return {"exit": out.returncode, "stdout": (out.stdout or "")[-tail:]}
    except (OSError, subprocess.SubprocessError) as e:
        return {"exit": None, "error": str(e)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apk", required=True)
    ap.add_argument("--output", default=None)
    ap.add_argument("--build-tools", default=os.path.join(ROOT, "toolchain", "android-sdk", "build-tools", "36.0.0"))
    ap.add_argument("--audit", default=os.path.join(ROOT, "validation", "apk-content-audit-0.2.0.json"))
    args = ap.parse_args()

    apk = os.path.abspath(args.apk)
    evidence: dict = {
        "apk": {
            "path": os.path.basename(apk),
            "bytes": os.path.getsize(apk),
            "sha256": sha256(apk),
        },
        "tests": test_totals(os.path.join(ROOT, "app-source", "app", "build", "test-results", "testReleaseUnitTest")),
    }

    with zipfile.ZipFile(apk) as z:
        names = z.namelist()
        evidence["apk"]["zip_entries"] = len(names)
        runtime = [n for n in names if n.endswith("runtime.zip")]
        evidence["runtime"] = {
            "entry": runtime[0] if runtime else None,
            "sha256": hashlib.sha256(z.read(runtime[0])).hexdigest() if runtime else None,
        }
        legal = {}
        for name in verify_identity.REQUIRED_NOTICE_FILES:
            legal[name] = hashlib.sha256(z.read(name)).hexdigest() if name in names else None
        evidence["legal_assets"] = legal

    violations, allowed, inventory, missing = verify_identity.scan(apk)
    evidence["identity_gate"] = {
        "pass": not violations and not missing,
        "violations": sorted(set(violations)),
        "allowed_notices": sorted(set(allowed)),
        "allowed_inventory": sorted(set(inventory)),
        "missing_required": missing,
    }

    aapt = os.path.join(args.build_tools, "aapt.exe" if os.name == "nt" else "aapt")
    badging = run([aapt, "dump", "badging", apk], tail=4_000_000)
    keep = ("package:", "sdkVersion:", "targetSdkVersion:", "application-label:", "native-code:")
    evidence["badging"] = {
        "exit": badging["exit"],
        "lines": [ln.strip() for ln in badging.get("stdout", "").splitlines() if ln.startswith(keep)],
    }

    java = os.path.join(ROOT, "toolchain", "jdk-full", "jdk-21.0.13.0.2+1", "bin", "java.exe")
    signer = os.path.join(args.build_tools, "lib", "apksigner.jar")
    verify = run([java, "-jar", signer, "verify", "--verbose", "--print-certs", apk])
    schemes = {}
    for line in verify.get("stdout", "").splitlines():
        if "scheme" in line and "Verified using" in line:
            key, _, value = line.partition(":")
            schemes[key.replace("Verified using", "").strip()] = value.strip() == "true"
        if "certificate SHA-256 digest" in line:
            evidence["signer_sha256"] = line.split(":")[-1].strip()
    evidence["signature"] = {"exit": verify["exit"], "schemes": schemes}

    if os.path.isfile(args.audit):
        with open(args.audit, encoding="utf-8") as f:
            audit = json.load(f)
        evidence["static_audit"] = {
            "summary": audit.get("summary"),
            "forbidden_component_violations": audit.get("forbidden_component_violations"),
            "target_elf_static_status": (audit.get("page_size_16k") or {}).get("target_elf_static_status"),
        }

    out = args.output or os.path.join(ROOT, "deliverables", "证据-0.2.0.json")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(evidence, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(json.dumps({k: v for k, v in evidence.items() if k in ("apk", "tests", "identity_gate")},
                     ensure_ascii=False, indent=2))
    print("written:", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
