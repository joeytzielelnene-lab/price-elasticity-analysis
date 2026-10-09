#!/bin/bash
# Prepares cloud sessions: Python deps (uv) and Ruflo agent orchestration.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}"

# Python dependencies for the analysis
if command -v uv >/dev/null 2>&1; then
  uv sync || echo "warning: uv sync failed" >&2
fi

# Ruflo, pinned to the version in RUFLO_SETUP.md and .mcp.json
RUFLO_VERSION="3.6.27"
if ! command -v ruflo >/dev/null 2>&1; then
  npm install -g "ruflo@${RUFLO_VERSION}"
fi

# Generate the (git-ignored) agents, helpers and hooks once per fresh clone
if [ ! -f .claude/helpers/hook-handler.cjs ]; then
  cp .claude/settings.json /tmp/settings.session-start.json
  ruflo init --start-all || echo "warning: ruflo init failed" >&2
  # Make sure our SessionStart hook survives whatever init wrote
  python3 - <<'PY'
import json
mine = json.load(open("/tmp/settings.session-start.json"))
cur = json.load(open(".claude/settings.json"))
entry = mine["hooks"]["SessionStart"][0]
ss = cur.setdefault("hooks", {}).setdefault("SessionStart", [])
if not any("session-start.sh" in json.dumps(e) for e in ss):
    ss.insert(0, entry)
json.dump(cur, open(".claude/settings.json", "w"), indent=2)
PY
fi
