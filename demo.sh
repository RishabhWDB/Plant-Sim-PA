#!/usr/bin/env bash
# One-command live demo: opens Unity in Play mode, waits for the simulation server,
# then lets the LLM agent manage the field while its reasoning shows on screen.
#
#   ./demo.sh                  open Unity in Play mode; start seasons with the buttons (bottom right)
#   ./demo.sh drought          run a season from the terminal instead: calm, drought, monsoon, acid_soil, heatwave_storm
#   ./demo.sh --short          stop after 30 simulated days (about 2 minutes)
#   ./demo.sh --dry-run        fake LLM, no internet needed
#   ./demo.sh --local          no Unity: run the same agent on the Python twin
#
# Run it again to start a new season: Unity stays open and the field is reset each time.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

UNITY="/Applications/Unity/Hub/Editor/6000.3.10f1/Unity.app/Contents/MacOS/Unity"
URL="http://localhost:8765"
SCENARIO=""
EXTRA=()
LOCAL=0
DRY=0

for arg in "$@"; do
    case "$arg" in
        calm|drought|monsoon|acid_soil|heatwave_storm) SCENARIO="$arg" ;;
        --short)   EXTRA+=(--max-days 30) ;;
        --dry-run) DRY=1 ;;
        --local)   LOCAL=1 ;;
        -h|--help) sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown option: $arg (try ./demo.sh --help)"; exit 1 ;;
    esac
done

bold() { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
fail() { printf '  \033[31m✗\033[0m %s\n' "$*"; exit 1; }

bold "PlantSim live agent demo"

# 1. Checks
[ -x ml/.venv/bin/python ] || fail "No Python environment at ml/.venv (see README)"
ok "Python environment"

if [ "$DRY" -eq 0 ]; then
    if ! grep -q '^DEEPINFRA_API_KEY=.' .env 2>/dev/null; then
        warn "No DEEPINFRA_API_KEY in .env: using the fake LLM (--dry-run)"
        DRY=1
    elif ! curl -s -o /dev/null --max-time 6 https://api.deepinfra.com; then
        warn "DeepInfra is unreachable (no internet?): using the fake LLM (--dry-run)"
        DRY=1
    else
        ok "DeepInfra key and connection"
    fi
fi
[ "$DRY" -eq 1 ] && EXTRA+=(--dry-run)

# 2. Unity in Play mode
if [ "$LOCAL" -eq 0 ]; then
    if curl -s --max-time 2 "$URL/health" >/dev/null; then
        ok "Unity is already in Play mode"
    else
        if pgrep -x Unity >/dev/null; then
            warn "Unity is open but not playing: open SampleScene and press Play"
        elif [ -x "$UNITY" ]; then
            echo "  Opening Unity (first start takes 1 to 2 minutes)..."
            nohup "$UNITY" -projectPath "$ROOT" -executeMethod DemoSceneSetup.Play \
                -logFile "$ROOT/Logs/demo_unity.log" >/dev/null 2>&1 &
        else
            fail "Unity 6000.3.10f1 not found. Use ./demo.sh --local"
        fi

        printf '  Waiting for the simulation server'
        for i in $(seq 1 120); do                       # up to 4 minutes
            curl -s --max-time 2 "$URL/health" >/dev/null && break
            printf '.'
            sleep 2
        done
        echo
        curl -s --max-time 2 "$URL/health" >/dev/null \
            || fail "No server on $URL. Is SampleScene playing? Fallback: ./demo.sh --local"
        ok "Unity is in Play mode, server on $URL"
    fi
    osascript -e 'tell application "Unity" to activate' >/dev/null 2>&1 || true
fi

# 3. The agent
if [ -z "$SCENARIO" ] && [ "$LOCAL" -eq 0 ]; then
    bold "Ready. In Unity, click a scenario button (bottom right) to start the agent."
    echo "  Agent output: Logs/agent_demo.log"
    exit 0
fi
SCENARIO="${SCENARIO:-drought}"
if [ "$LOCAL" -eq 1 ]; then
    CMD=(./run_agent.sh agent/run.py --policy agent --backend local --scenario "$SCENARIO" ${EXTRA[@]+"${EXTRA[@]}"})
else
    # A simulated day lasts 4.5 s, so one decision every 13.5 s = every 3 days
    CMD=(./run_agent.sh agent/run.py --policy agent --backend unity --scenario "$SCENARIO" --tick 13.5 ${EXTRA[@]+"${EXTRA[@]}"})
fi

bold "Ready. Press Enter to start the season (Ctrl+C stops it at any time)."
read -r _
"${CMD[@]}"
STATUS=$?

bold "Season over."
echo "  Run log and report: agent/runs/ (newest files)"
echo "  Another season:     ./demo.sh acid_soil    (twin vetoes pH moves in the wrong direction)"
[ "$LOCAL" -eq 0 ] && echo "  Unity stays open; stop Play mode when you are done."
exit $STATUS
