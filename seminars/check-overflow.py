#!/usr/bin/env python3
"""
Screenshot every slide of a rendered revealjs deck and flag ones whose
content sits in the bottom band shared with reveal.js's fixed nav-icon
overlay -- a fast, repeatable stand-in for eyeballing every slide by hand.

Quarto's own render has no concept of vertical overflow: it only checks
that R chunks execute and that HTML/Pandoc output builds, not whether the
resulting content fits inside a slide's fixed 1280x720 box once an actual
browser lays it out. A slide can overflow with a completely clean
`quarto render`. This script is a cheap proxy for the real check (a human
looking at the rendered slide), not a replacement for it: it flags
candidates, a person (or Claude) still looks at each flagged PNG before
deciding it's real. See seminars/CLAUDE.md's QA section.

Usage:
    quarto render seminars/weekNN-foo.qmd
    cd seminars && python3 -m http.server 8791 --bind 127.0.0.1 &
    python3 check-overflow.py weekNN-foo 44 8791
    # (44 = number of `##` slides in the .qmd, i.e. `grep -c '^## ' weekNN-foo.qmd`;
    #  total slides screenshotted = that + 1, for the title slide)

Known false positives, confirmed by hand each time this has been run:
a slide's own background-image (title/divider slides) fills the whole
band and always flags; bullet text or an axis title that merely sits
close to, but well clear of, the bottom edge can flag too (text
descenders, monospace glyphs). A flagged slide that turns out clean on
inspection is not a bug in this script, just its false-positive rate.
"""
import glob
import os
import subprocess
import sys
from PIL import Image

CHROME = os.path.expanduser(
    "~/.local/share/quarto/chromium/linux-869685/chrome-linux/chrome"
)

# Bottom band to inspect: where reveal.js's fixed menu/notes/chalkboard
# icon cluster (bottom-left) and the university logo (bottom-right) sit.
# Content in this band, outside those two zones, means either real
# clipping or crowding against the fixed overlay.
Y0, Y1 = 655, 714
EXCLUDE_X = [(0, 135), (1185, 1280)]
WHITE_THRESHOLD = 235
FLAG_THRESHOLD = 1500  # empirically: real overflow scored 2658/4700; the
                        # highest confirmed false positive scored 1234


def excluded(x):
    return any(lo <= x < hi for lo, hi in EXCLUDE_X)


def screenshot(deck, n, port, out_dir):
    for i in range(n + 1):
        out = os.path.join(out_dir, f"s{i:02d}.png")
        subprocess.run(
            [
                CHROME, "--headless", "--disable-gpu", "--no-sandbox",
                "--window-size=1280,720", f"--screenshot={out}",
                f"http://127.0.0.1:{port}/{deck}.html#/{i}",
            ],
            capture_output=True,
        )


def score(path):
    img = Image.open(path).convert("RGB")
    w, h = img.size
    px = img.load()
    bad = 0
    for y in range(Y0, min(Y1, h)):
        for x in range(w):
            if excluded(x):
                continue
            r, g, b = px[x, y]
            if r < WHITE_THRESHOLD or g < WHITE_THRESHOLD or b < WHITE_THRESHOLD:
                bad += 1
    return bad


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    deck, n, port = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    out_dir = os.path.join(os.path.dirname(__file__), ".overflow-check", deck)
    os.makedirs(out_dir, exist_ok=True)
    screenshot(deck, n, port, out_dir)
    for path in sorted(glob.glob(os.path.join(out_dir, "s*.png"))):
        s = score(path)
        flag = "  <-- CHECK" if s > FLAG_THRESHOLD else ""
        print(f"{os.path.basename(path)}: {s}{flag}")


if __name__ == "__main__":
    main()
