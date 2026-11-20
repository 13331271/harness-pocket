#!/usr/bin/env python3
"""Generate the launcher icon from the supplied mascot artwork.

Adaptive icon contract: a 108dp canvas whose visible area is the inner ~72dp
circle-ish shape. The mascot is therefore placed on an 84dp square in the middle
of a white background, so launcher masks (circle / squircle / rounded square)
never cut the face.
"""
from __future__ import annotations

import os
import sys

from PIL import Image

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app-source")
RES = os.path.join(ROOT, "app", "src", "main", "res")
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "artwork", "mascot-square.png")

DENSITIES = {"mdpi": 1.0, "hdpi": 1.5, "xhdpi": 2.0, "xxhdpi": 3.0, "xxxhdpi": 4.0}
CANVAS_DP = 108
ART_DP = 88


def main() -> int:
    art = Image.open(SRC).convert("RGBA")
    for bucket, scale in DENSITIES.items():
        canvas_px = int(CANVAS_DP * scale)
        art_px = int(ART_DP * scale)
        canvas = Image.new("RGBA", (canvas_px, canvas_px), (255, 255, 255, 255))
        scaled = art.resize((art_px, art_px), Image.LANCZOS)
        offset = (canvas_px - art_px) // 2
        canvas.alpha_composite(scaled, (offset, offset))
        out_dir = os.path.join(RES, f"drawable-{bucket}")
        os.makedirs(out_dir, exist_ok=True)
        out = os.path.join(out_dir, "ic_launcher_mascot.png")
        canvas.save(out, optimize=True)
        print(f"{bucket}: {canvas_px}px -> {os.path.relpath(out, RES)}")

    # Preview for the user (xxxhdpi canvas).
    preview = os.path.join(os.path.dirname(SRC), "icon-preview-432.png")
    Image.open(os.path.join(RES, "drawable-xxxhdpi", "ic_launcher_mascot.png")).save(preview)
    print("preview:", preview)
    return 0


if __name__ == "__main__":
    sys.exit(main())
