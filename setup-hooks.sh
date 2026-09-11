#!/bin/sh
# Set up local Git hooks for InventoryBallast. Run this once after cloning
# (or once per fresh checkout -- e.g. at the start of a Claude Code on the web
# session; see .claude/settings.json's SessionStart hook).
#
# Wires .githooks/ (this repo's own hooks, written against docs/
# adoption_guide.md step 6 -- not copied from QuantSmith's own .githooks/,
# which enforces SDK-repo invariants that don't apply here).

set -e

ROOT_DIR=$(git rev-parse --show-toplevel)
cd "$ROOT_DIR"

if [ ! -d ".githooks" ]; then
  echo "Error: .githooks directory not found." >&2
  exit 1
fi

chmod +x .githooks/*
git config core.hooksPath .githooks

echo "Git hooks enabled (core.hooksPath -> .githooks)."
