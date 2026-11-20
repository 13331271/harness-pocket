#!/usr/bin/env python3
"""Debrand pass for the Harness Pocket source tree.

Removes third-party developer identity (author name, personal repo, community
groups, star prompts, contributor handles) from shipped resources, and rebrands
the product name. Copyright/licence notices are intentionally preserved.

Run from anywhere: python build-scripts/debrand.py
"""
from __future__ import annotations

import io
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app-source")
RES = os.path.join(ROOT, "app", "src", "main", "res")
APP_NAME = "Harness Pocket"

# Strings that carry another developer's identity. They are deleted from every
# locale; the UI that referenced them is removed in the same pass.
DROP = [
    "about_author",
    "about_repo",
    "about_fork_badge",
    "about_qq_group",
    "about_qq_group_id",
    "about_qq_group_tap",
    "about_qq_group_copied",
    "about_telegram",
    "about_telegram_sub",
    "about_telegram_open",
    "about_telegram_url",
    "about_telegram_copied",
    "about_star_title",
    "about_star_sub",
    "about_star_action",
    "about_credits",
    "about_repos",
]

STRING_RE = re.compile(r'[ \t]*<string name="([^"]+)"[^>]*?(?:/>|>.*?</string>)[ \t]*\r?\n', re.S)


def debrand_strings(path: str) -> tuple[int, int]:
    text = io.open(path, encoding="utf-8", newline="").read()
    removed = 0

    def repl(m: re.Match) -> str:
        nonlocal removed
        if m.group(1) in DROP:
            removed += 1
            return ""
        return m.group(0)

    text = STRING_RE.sub(repl, text)
    before = text
    text = text.replace("DSH Mobile", APP_NAME)
    rebranded = sum(1 for _ in re.finditer(APP_NAME, text)) - sum(1 for _ in re.finditer(APP_NAME, before))
    io.open(path, "w", encoding="utf-8", newline="").write(text)
    return removed, rebranded


def scrub_urls(path: str) -> int:
    """Remove third-party personal repo links that are only UI hints."""
    text = io.open(path, encoding="utf-8", newline="").read()
    before = text
    # ASR help body: keep the app name, drop the personal repo URL.
    text = text.replace(" 鈥?github.com/ElishaAz/Az/Sayboard", "")
    text = re.sub(r"\s*鈥擻s*github\.com/woheller69/whisperIMEplus", "", text)
    text = re.sub(r"\s*鈥擻s*github\.com/woheller69/whisperIME", "", text)
    text = re.sub(r"\s*鈥擻s*github\.com/ElishaAz/Sayboard", "", text)
    text = text.replace("github.com/XiaoPb/dsh-pet-bridge", "dsh-pet-bridge")
    io.open(path, "w", encoding="utf-8", newline="").write(text)
    return sum(1 for a, b in zip(before.splitlines(), text.splitlines()) if a != b)


def main() -> int:
    total_removed = 0
    files = []
    for base, _dirs, names in os.walk(RES):
        for n in names:
            if n == "strings.xml":
                files.append(os.path.join(base, n))
    for f in sorted(files):
        removed, rebranded = debrand_strings(f)
        adjusted = scrub_urls(f)
        total_removed += removed
        print(f"{os.path.relpath(f, RES):40s} removed={removed:2d} url-rows={adjusted}")
    print(f"total removed strings: {total_removed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

