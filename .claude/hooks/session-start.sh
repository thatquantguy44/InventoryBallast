#!/bin/bash
# SessionStart hook for Claude Code on the web (remote sessions only).
#
# Two jobs, both because a fresh remote checkout otherwise starts without
# them and a session has to redo this by hand every time:
#
# 1. Wire this repo's local Git hooks (setup-hooks.sh -> .githooks/). Without
#    this, a fresh session's git identity is whatever the harness assigns
#    (often an AI-agent identity), and nothing stops a commit from being
#    created under it -- this repo's own CI gate (agent-attribution) rejects
#    that, but only after the fact. The local pre-commit/pre-push hooks catch
#    it before the commit exists / before the push leaves the machine.
# 2. Install the Python dev environment (docs/handoff.md's own documented
#    command) so pytest/ruff/mypy work immediately, matching this repo's
#    convention that .venv/ is gitignored and recreated fresh per checkout.

set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"

sh setup-hooks.sh

if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install -q --upgrade pip

# dev+highs cover the default test suite (pytest/ruff/mypy, HiGHS solver
# backend) -- fatal if this fails, since almost nothing works without it.
.venv/bin/python -m pip install -q -e ".[dev,highs]"

# dataframe (pandas, 2 currently-skipped tests) and agentic (a pinned-commit
# git dependency on QuantSmith) are narrower-use and one is a slower network
# fetch -- best-effort, never block the session over either.
.venv/bin/python -m pip install -q -e ".[dataframe,agentic]" \
  || echo "warning: dataframe/agentic extras failed to install (non-critical, retry manually if needed)"

echo "export PATH=\"$CLAUDE_PROJECT_DIR/.venv/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"

echo "Session start: git hooks wired, Python environment ready."
