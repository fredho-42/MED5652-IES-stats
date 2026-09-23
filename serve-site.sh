#!/usr/bin/env bash
# Serves the already-built _book/ over local HTTP, so the rendered book and
# seminar decks can be viewed from a browser without downloading anything
# over SSH and without publishing to the live gh-pages site.
#
# This serves whatever was last rendered. It does not render or publish
# anything itself:
#
#   quarto render                                          # the book
#   quarto render seminars --output-dir ../_book/seminars   # the decks
#   ./serve-site.sh
#
# Usage:
#   ./serve-site.sh              # bind the Tailscale address, port 8800
#   ./serve-site.sh --local      # bind 127.0.0.1 instead (e.g. no Tailscale)
#   ./serve-site.sh 8900         # a different port
#   ./serve-site.sh --local 8900
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

PORT=8800
BIND=""
for arg in "$@"; do
  case "$arg" in
    --local) BIND="127.0.0.1" ;;
    *) PORT="$arg" ;;
  esac
done

if [ -z "$BIND" ]; then
  if command -v tailscale >/dev/null 2>&1 && BIND="$(tailscale ip -4 2>/dev/null)"; then
    :
  else
    echo "Tailscale IP not available (tailscale not installed, or not running)." >&2
    echo "Falling back to 127.0.0.1 -- reachable only from this machine." >&2
    BIND="127.0.0.1"
  fi
fi

if [ ! -d _book ]; then
  echo "_book/ doesn't exist yet. Render first:" >&2
  echo "  quarto render" >&2
  echo "  quarto render seminars --output-dir ../_book/seminars" >&2
  exit 1
fi

HOST="$(hostname)"
RENDERED_AT="$(stat -c '%y' _book/index.html 2>/dev/null | cut -d. -f1 || echo 'unknown time')"
echo "Serving _book/ (index.html last rendered: ${RENDERED_AT})"
echo
echo "  Book:    http://${HOST}:${PORT}/"
echo "           http://${BIND}:${PORT}/"
echo "  A deck:  http://${HOST}:${PORT}/seminars/week09-comparison.html"
echo
echo "This is a local-only viewer of whatever was last rendered. It is not"
echo "the live site, and running or stopping it never touches gh-pages."
echo "Ctrl-C to stop."
echo

exec python3 -m http.server "$PORT" --bind "$BIND" --directory _book
