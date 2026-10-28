"""Traces assets/illustration.jpg (black ink on a white sticker over a grey
backdrop) into vector paths in assets/portrait.json, which build_profile.py
places on the card.

Only needs re-running when the illustration changes:
    pip install opencv-python-headless numpy
    python scripts/make_portrait.py
"""
import json
import os

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOP = 250              # crop the empty backdrop above the sticker
INK_CUT = 128          # grey level below which a pixel is ink
PAPER_CUT = 238        # grey level above which a pixel is white sticker paper


def to_path(binary):
    # Lossless tracing: simplifying thin ink lines makes them self-intersect,
    # which flips whole regions under the even-odd fill rule.
    contours, _ = cv2.findContours(binary, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    parts = []
    for c in contours:
        c = c.reshape(-1, 2)
        if len(c) >= 3:
            parts.append("M" + "L".join(f"{x} {y}" for x, y in c) + "Z")
    return "".join(parts)


def main():
    gray = cv2.imread(os.path.join(ROOT, "assets", "illustration.jpg"), cv2.IMREAD_GRAYSCALE)[TOP:]

    # Paper: everything not reachable from the border through the grey backdrop
    # (ink is excluded so lines touching the crop edge don't leak into it).
    blur = cv2.GaussianBlur(gray, (0, 0), 3)
    backdrop = ((blur > INK_CUT + 40) & (blur < PAPER_CUT)).astype(np.uint8)
    _, labels = cv2.connectedComponents(backdrop)
    border = set(np.unique(np.concatenate([labels[0], labels[:, 0], labels[:, -1]]))) - {0}
    paper = (~np.isin(labels, list(border))).astype(np.uint8) * 255
    paper = cv2.morphologyEx(paper, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    paper = ((cv2.GaussianBlur(paper, (0, 0), 3) > 127) * 255).astype(np.uint8)
    outer, _ = cv2.findContours(paper, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cv2.drawContours(paper, outer, -1, 255, cv2.FILLED)  # fill grey shading enclosed by the sticker

    # Ink: lightly smoothed so JPEG edges trace as clean curves.
    ink = ((cv2.GaussianBlur(gray, (0, 0), 0.8) < INK_CUT) * 255).astype(np.uint8)
    ink = cv2.bitwise_and(ink, paper)

    h, w = gray.shape
    out = {"width": w, "height": h, "paper": to_path(paper), "ink": to_path(ink)}
    with open(os.path.join(ROOT, "assets", "portrait.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"Saved assets/portrait.json ({os.path.getsize(os.path.join(ROOT, 'assets', 'portrait.json')) // 1024} KB)")


if __name__ == "__main__":
    main()
