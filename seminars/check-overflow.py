#!/usr/bin/env python3
"""Measure how far down each slide of a rendered revealjs deck its content
actually reaches, and flag the ones that overflow the 1280x720 box or crowd
the fixed nav-icon overlay at the bottom of it.

Quarto's own render has no concept of vertical overflow: it only checks that
R chunks execute and that HTML/Pandoc output builds, not whether the result
fits inside a slide once a browser lays it out. A slide can overflow with a
completely clean `quarto render`. This script is the automated screen for
that; a full manual pass through the rendered deck is still the real check
before calling a deck finished (see seminars/CLAUDE.md's QA section).

Usage, from inside seminars/:

    quarto render seminars --output-dir ../_book/seminars   # or one deck
    python3 check-overflow.py                 # every week*.qmd found
    python3 check-overflow.py week09-comparison

Slides reading over 720px overflow the slide box outright. Slides over 655px
are inside the box but sitting in the band the menu/chalkboard icons and the
slide number occupy, which reads as cramped in the room even though nothing
is clipped. Both get a screenshot written to .overflow-check/<deck>/ so the
flagged slide can be looked at rather than guessed at.

How it measures, and what it assumes
------------------------------------
The deck is served locally with a measuring script injected into the HTML
(nothing in the output tree is modified), and one headless chromium run per
deck steps through every slide and reports the lowest laid-out pixel of each,
in slide coordinates. Stepping is required: reveal.js sets `display: none` on
every slide that is not the current one, so nothing can be measured without
navigating to it.

The URL carries `?fragments=false`, which makes reveal.js show every fragment
at once. That matters since `_quarto.yml` sets `incremental: true`: without
it, unrevealed bullets carry `visibility: hidden` and a screenshot-based
check sees an almost empty slide and reports every deck clean, which is
exactly what happened when deck-wide animation landed (2026-09-23). Showing
all fragments is also the *maximal* layout state, the union of everything the
slide ever displays, which is the state overflow should be judged in.

Two assumptions behind that, to re-check if _quarto.yml's animation settings
change: a plain `fragment` keeps its layout space whether or not it has been
revealed (verified, identical numbers with fragments on and off), and no
slide currently swaps content between fragment states or uses auto-animate
(enabled deck-wide, unused so far). A deck that starts doing either would
need measuring per fragment state, which this script does not do.
"""
import functools
import glob
import http.server
import io
import json
import os
import re
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIRS = [
    os.path.join(HERE, "..", "_book", "seminars"),
    HERE,
]
CHROME = os.path.expanduser(
    "~/.local/share/quarto/chromium/linux-869685/chrome-linux/chrome"
)

SLIDE_HEIGHT = 720   # the deck's own height, from _quarto.yml
NAV_BAND = 655       # top of the band the fixed nav icons and slide number sit in
PORT = 8794

# Injected into the served HTML, before </body>. Walks the deck one slide at a
# time and records the lowest laid-out pixel of each, converted back into slide
# coordinates (reveal scales .slides to fit the window, so measurements have to
# be divided by that scale to mean anything against SLIDE_HEIGHT).
INJECT = """
<script>
(function () {
  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
  async function run() {
    while (!(window.Reveal && window.Reveal.isReady && window.Reveal.isReady())) {
      await sleep(100);
    }
    await sleep(1500);
    try { await document.fonts.ready; } catch (e) {}
    var slidesEl = document.querySelector('.reveal .slides');
    var total = Reveal.getTotalSlides();
    var out = [];
    for (var i = 0; i < total; i++) {
      Reveal.slide(i);
      await sleep(120);
      var sec = document.querySelector('.reveal .slides section.present');
      var sr = slidesEl.getBoundingClientRect();
      var scale = sr.height / SLIDE_HEIGHT;
      var bottom = sr.top;
      var worst = null;
      var els = sec ? sec.querySelectorAll('*') : [];
      for (var j = 0; j < els.length; j++) {
        var el = els[j];
        var r = el.getBoundingClientRect();
        if (r.width <= 0 || r.height <= 0) continue;
        if (r.bottom > bottom) { bottom = r.bottom; worst = el; }
      }
      var heading = sec ? sec.querySelector('h1, h2') : null;
      out.push({
        i: i,
        title: heading ? heading.textContent.trim() : '',
        bottom: Math.round((bottom - sr.top) / scale),
        worst: worst ? (worst.tagName.toLowerCase() +
          (worst.className ? '.' + String(worst.className).split(' ')[0] : '')) : ''
      });
    }
    var pre = document.createElement('pre');
    pre.id = 'overflow-report';
    pre.textContent = JSON.stringify(out);
    document.body.appendChild(pre);
  }
  run();
})();
</script>
""".replace("SLIDE_HEIGHT", str(SLIDE_HEIGHT))


class Handler(http.server.SimpleHTTPRequestHandler):
    """Serves the rendered deck folder, injecting the measuring script into
    any HTML it hands out. The files on disk are never touched."""

    def send_head(self):
        path = self.translate_path(self.path)
        if path.endswith(".html") and os.path.isfile(path):
            with open(path, "rb") as f:
                body = f.read().replace(b"</body>", INJECT.encode() + b"</body>")
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return io.BytesIO(body)
        return super().send_head()

    def log_message(self, *args):
        pass


def find_output_dir(deck):
    for d in OUTPUT_DIRS:
        if os.path.isfile(os.path.join(d, deck + ".html")):
            return os.path.normpath(d)
    return None


def unescape(text):
    for a, b in (("&quot;", '"'), ("&lt;", "<"), ("&gt;", ">"), ("&amp;", "&")):
        text = text.replace(a, b)
    return text


def measure(deck, port):
    url = "http://127.0.0.1:%d/%s.html?fragments=false&transition=none" % (port, deck)
    res = subprocess.run(
        [CHROME, "--headless", "--disable-gpu", "--no-sandbox",
         "--window-size=1280,720", "--virtual-time-budget=180000",
         "--run-all-compositor-stages-before-draw", "--dump-dom", url],
        capture_output=True, text=True, timeout=600,
    )
    match = re.search(r'<pre id="overflow-report">(.*?)</pre>', res.stdout, re.S)
    if not match:
        raise RuntimeError(
            "no measurements came back for %s (chromium stderr: %s)"
            % (deck, res.stderr.strip()[-300:] or "none")
        )
    return json.loads(unescape(match.group(1)))


def screenshot(deck, index, port, out_dir):
    out = os.path.join(out_dir, "s%02d.png" % index)
    subprocess.run(
        [CHROME, "--headless", "--disable-gpu", "--no-sandbox",
         "--window-size=1280,720", "--screenshot=" + out,
         "http://127.0.0.1:%d/%s.html?fragments=false&transition=none#/%d"
         % (port, deck, index)],
        capture_output=True, timeout=120,
    )
    return out


def check(deck, port, shots):
    out_root = find_output_dir(deck)
    if out_root is None:
        print("%s: no rendered %s.html in %s -- render it first"
              % (deck, deck, " or ".join(os.path.normpath(d) for d in OUTPUT_DIRS)))
        return False
    age = (time.time() - os.path.getmtime(os.path.join(out_root, deck + ".html"))) / 60
    print("\n%s  (measuring %s/%s.html, rendered %d minutes ago)"
          % (deck, out_root, deck, age))

    srv = http.server.ThreadingHTTPServer(
        ("127.0.0.1", port), functools.partial(Handler, directory=out_root)
    )
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        slides = measure(deck, port)
        flagged = []
        for row in slides:
            note = ""
            if row["bottom"] > SLIDE_HEIGHT:
                note = "  <-- OVERFLOWS"
            elif row["bottom"] > NAV_BAND:
                note = "  <-- crowds the nav band"
            if note:
                flagged.append(row)
            print("  s%02d %4dpx  %-44s%s"
                  % (row["i"], row["bottom"], row["title"][:44], note))

        if flagged and shots != "none":
            out_dir = os.path.join(HERE, ".overflow-check", deck)
            os.makedirs(out_dir, exist_ok=True)
            wanted = slides if shots == "all" else flagged
            for row in wanted:
                screenshot(deck, row["i"], port, out_dir)
            print("  screenshots: %s/s{%s}.png"
                  % (out_dir, ",".join("%02d" % r["i"] for r in wanted)))
        print("  %d of %d slides need a look" % (len(flagged), len(slides)))
        for row in flagged:
            print("     s%02d lowest element: %s" % (row["i"], row["worst"]))
        return not flagged
    finally:
        srv.shutdown()
        srv.server_close()


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    shots = "flagged"
    for a in sys.argv[1:]:
        if a.startswith("--shots="):
            shots = a.split("=", 1)[1]
    decks = args or sorted(
        os.path.basename(p)[:-4] for p in glob.glob(os.path.join(HERE, "week*.qmd"))
    )
    if not decks:
        print(__doc__)
        sys.exit(1)
    clean = True
    for deck in decks:
        clean = check(deck, PORT, shots) and clean
    print("\nA flagged slide is a candidate, not a verdict: open the PNG. "
          "Nothing flagged is not the same as a deck that reads well.")
    sys.exit(0 if clean else 1)


if __name__ == "__main__":
    main()
