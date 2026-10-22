#!/usr/bin/env bash
# Runs a Python script with the project's virtual environment, from any directory.
#   ./run_agent.sh agent/live_agent.py --backend local --scenario drought
# Relative script paths are taken from the repository root.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$ROOT/ml/.venv/bin/python"

if [ ! -x "$PY" ]; then
    echo "No virtual environment at ml/.venv. Create it with:" >&2
    echo "  python3 -m venv ml/.venv && ml/.venv/bin/pip install -r ml/requirements.txt" >&2
    exit 1
fi
if [ $# -eq 0 ]; then
    echo "Usage: ./run_agent.sh <script.py> [args...]" >&2
    exit 1
fi

cd "$ROOT"
exec "$PY" "$@"
