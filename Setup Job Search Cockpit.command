#!/bin/zsh
set -eu

SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR"

if [[ "$(uname -s)" != "Darwin" ]]; then
  print "Job Search Cockpit Phase 1 requires macOS."
  exit 1
fi

if ! command -v python3.12 >/dev/null 2>&1 || ! command -v uv >/dev/null 2>&1; then
  print "Python 3.12 and uv are required."
  print "Install them with: brew install python@3.12 uv"
  print "Homebrew: https://brew.sh/"
  exit 1
fi

uv sync --frozen
uv run playwright install chromium
print "Job Search Cockpit setup is complete. Double-click Start Job Search Cockpit.command."
