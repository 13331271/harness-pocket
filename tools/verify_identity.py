#!/usr/bin/env python3
"""Identity gate for a built Harness Pocket APK.

Fails when another developer's account/handle leaks into the product, and when
the licence notices that MUST stay are missing. Re-runnable by anyone:

    python build-scripts/verify_identity.py deliverables/Harness-Pocket-0.2.0-arm64.apk

Exit codes: 0 = clean, 1 = violation, 2 = usage/read error.
"""
from __future__ import annotations

import argparse
import sys
import zipfile

# Handles that must never appear: the previous maintainer's identity and the
# community channels it advertised. Kept as separate needles so a new leak
# reports which string it found.
FORBIDDEN = [
    b"Soodok",
    b"soodok",
    b"1128769016",          # QQ group number
    b"t.me/+4VN3",          # Telegram invite
    b"dshtui",              # community forum/domain
    b"Tongyu3",             # another packaged variant's maintainer
    b"ccch1mneyyy",         # dsh-Go maintainer
]

# Files where third-party attribution is legally required (MIT/Apache-2.0) and
# therefore allowed to name the original authors.
NOTICE_FILES = ("assets/legal/LICENSE.txt", "assets/legal/NOTICE.txt")
REQUIRED_NOTICE_FILES = NOTICE_FILES

# Marketplace inventory: the plugin catalogue is a product listing, so plugin
# authors' repository names legitimately appear there. This is inventory data,
# not this app's own identity, and stripping it would break the plugin store.
INVENTORY_FILES = ("assets/market/catalog.json", "community-plugins.json")

# Attachments whose bytes are unrelated to identity (binary runtimes/models).
SKIP_SUFFIX = (".so", ".zip", ".tgz", ".png", ".jpg", ".jpeg", ".webp", ".wav", ".mp3")


def scan(apk: str) -> tuple[list[str], list[str], list[str], list[str]]:
    violations: list[str] = []
    allowed: list[str] = []
    inventory: list[str] = []
    missing: list[str] = []
    with zipfile.ZipFile(apk) as z:
        names = set(z.namelist())
        for required in REQUIRED_NOTICE_FILES:
            if required not in names:
                missing.append(required)
        for info in z.infolist():
            if info.filename.lower().endswith(SKIP_SUFFIX):
                continue
            try:
                data = z.read(info)
            except Exception:
                continue
            for needle in FORBIDDEN:
                if needle not in data:
                    continue
                label = f"{needle.decode('latin-1')} in {info.filename}"
                if info.filename in NOTICE_FILES:
                    allowed.append(label)
                elif info.filename in INVENTORY_FILES:
                    inventory.append(label)
                else:
                    violations.append(label)
    return violations, allowed, inventory, missing


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("apk")
    args = ap.parse_args()
    try:
        violations, allowed, inventory, missing = scan(args.apk)
    except (OSError, zipfile.BadZipFile) as e:
        print(f"cannot read APK: {e}", file=sys.stderr)
        return 2

    print(f"APK: {args.apk}")
    print("\nrequired notices present:")
    for name in REQUIRED_NOTICE_FILES:
        state = "MISSING" if name in missing else "ok"
        print(f"  [{state}] {name}")
    print("\nallowed (licence-required attribution):")
    for item in sorted(set(allowed)):
        print(f"  - {item}")
    print("\nallowed (marketplace inventory, not this app's identity):")
    for item in sorted(set(inventory)):
        print(f"  - {item}")
    print("\nforbidden identity hits:")
    if not violations:
        print("  none")
    for item in sorted(set(violations)):
        print(f"  ! {item}")

    if violations or missing:
        return 1
    print("\nRESULT: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
