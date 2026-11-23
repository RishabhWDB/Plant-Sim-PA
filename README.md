# PlantSim: Twin-in-the-Loop

**A small language model farm manager guided by a learned plant-growth digital twin.**

PlantSim simulates a 144-plant crop field in Unity 6. An LLM agent (Llama 3.1 8B) manages it
through droughts, floods, acid soil and heatwaves. The agent proposes up to two equipment actions
every three simulated days. Before any action is applied, the digital twin predicts its effect and
vetoes it if it would make the crop worse tomorrow.

> The model proposes, the twin decides.

| | |
|---|---|
| Success rate (150 test seasons, 5 scenarios) | **96%** for the agent; **52%** without the twin check |
| Reaction to a drought | 3.4 days (rule-based baseline: 7.0) |
| LLM cost | about **$0.0006 per season** |
| Paper | [*Twin-in-the-Loop*](paper/agent/main.pdf) (IEEE format, LaTeX in [paper/agent](paper/agent)) |

---

## Run the demo

**Double-click `Demo.command`** in Finder, or from a terminal:

```bash
./demo.sh
```

Unity opens straight into Play mode. Then:

1. **Explore the field.** Drag the sliders (top left) to change pH, soil moisture, sunlight,
   temperature, humidity and rainfall. The status panel (top right) shows the growth score,
   soil water and the forecast to maturity.
2. **Start a season with the agent.** Click a scenario button (bottom right): Drought, Flood,
   Acid soil, Heatwave + storm or Normal season. The field resets and the agent takes over.
3. **Watch it reason.** The agent log (bottom left) shows the model's reasoning, a practical
   remedy for the farmer, and any action the twin vetoed.
4. **Interfere.** Change a slider mid-season. The agent is told about the change and responds
   to it at its next decision.

A season lasts about 5 minutes (4.5 s per simulated day). **Stop agent** ends it; another
scenario button starts over. Talking points for a live demo: [DEMO_SCRIPT.md](DEMO_SCRIPT.md).
Troubleshooting: [DEMO.md](DEMO.md).

| Option | What it does |
|---|---|
| `./demo.sh drought` | Run a season from the terminal instead of the buttons |
| `./demo.sh --dry-run` | Fake LLM, no internet or API key needed |
| `./demo.sh --local drought` | No Unity: run the agent on the Python twin |

---

## How it works

```
                 every 3 simulated days
┌──────────────┐  state, what-ifs, actions  ┌────────────────────────────────┐
│ Python agent │ ─────────── HTTP ────────▶ │ Unity: SimulationServer :8765  │
│  (agent/)    │ ◀───────────────────────── │  GrowthEngine + learned model  │
└──────┬───────┘                            │  144 plants, weather, UI       │
       │ one call per decision              └────────────────────────────────┘
       ▼
  Llama 3.1 8B on DeepInfra (OpenAI-compatible API)
```

Each decision has five steps:

1. **Read** the field: growth score, soil water, forecast, weather and news (weather events,
   manual changes).
2. **Probe** the twin with 9 what-if questions: tomorrow's score with each control set lower,
   unchanged or higher. The agent is never told the crop's optimal ranges.
3. **Ask** the LLM once. It replies in JSON with its reasoning, a remedy and at most 2 actions.
4. **Check** each action with the twin and veto any that lowers tomorrow's predicted score.
5. **Apply** what is left, clipped to the actuator limits, and log it.

The agent controls soil moisture (irrigation or drainage), pH (lime or sulfur), sunlight (grow
lights or shade) and humidity (misting or ventilation). Temperature and rainfall are weather: it
can only compensate.

### The twin

- **Physics:** a daily soil-water balance (Turc reference evapotranspiration with the FAO-56
  stress coefficient, drainage above field capacity). Each variable is scored with a
  cardinal-point response, and the scores are combined into a growth score from 0 to 1. Above
  0.5 the crop grows; below 0.5 it loses progress.
- **Learned model:** a gradient-boosting ensemble with isotonic calibration, trained in Python on
  the physics. Unity evaluates the exported trees in C# to predict the score and forecast
  maturity.

---

## Tech stack

| Layer | Technology | Where |
|---|---|---|
| Simulation and visuals | Unity 6 (6000.3.10f1), C#, URP, uGUI and TextMeshPro | `Assets/` |
| Simulation API | HTTP server inside Unity (`HttpListener`) | `Assets/Scripts/Core/SimulationServer.cs` |
| Learned twin | Python, NumPy, scikit-learn | `ml/` |
| Agent | Python, `openai` SDK against DeepInfra, `requests`, `python-dotenv` | `agent/` |
| LLM | Llama 3.1 8B Instruct (Mistral Small 24B also evaluated) | DeepInfra |
| Figures and paper | matplotlib, LaTeX (IEEEtran) | `agent/results/`, `paper/` |

The agent harness is plain Python with no agent framework, so every step is visible and cheap.

## Repository layout

| Path | Contents |
|---|---|
| `Assets/Scripts/Core` | `GrowthEngine` (water balance, score, forecast), `GrowthModel` (C# tree evaluator), `Plant`, `FarmGrid`, `SimulationClock`, `DayNightCycle`, `SimulationServer` |
| `Assets/Scripts/UI` | Sliders, status panel, time controls, agent log, scenario buttons (`ScenarioLauncher`) |
| `Assets/Editor` | `DemoSceneSetup`: adds the server and log panel to the scene, opens Play mode for the demo |
| `Assets/Tests` | EditMode (C#/Python parity, forecast) and PlayMode (HTTP server) tests |
| `agent/` | Agent loop (`live_agent.py`), environment and scenarios, baselines, evaluation, results ([README](agent/README.md)) |
| `ml/` | Python twin core, surrogate training, ablation, twin evaluation |
| `paper/` | `agent/main.tex`: the agent paper. `main.tex`: the predictive-twin paper |
| `demo.sh`, `Demo.command` | One-command demo launcher |

## Setup

**Requirements:** macOS, Unity 6000.3.10f1 (via Unity Hub), Python 3 (tested on 3.14).

```bash
python3 -m venv ml/.venv && ml/.venv/bin/pip install -r ml/requirements.txt
cp .env.example .env        # add DEEPINFRA_API_KEY for real LLM calls
```

Without an API key the demo runs with a fake LLM.

## Reproduce the results

```bash
# One season on the Python twin (no Unity)
./run_agent.sh agent/run.py --policy agent --backend local --scenario drought

# Baselines on every scenario, 5 seeds (free, about 2 minutes)
./run_agent.sh agent/evaluate.py --seeds 5

# Add the LLM agent (uses DeepInfra credits, about $0.08)
./run_agent.sh agent/evaluate.py --seeds 5 --include-agent

# Rebuild tables and charts from the runs on disk
./run_agent.sh agent/evaluate.py --report-only
```

Results, tables and figures go to `agent/results/` ([RESULTS_TABLE.md](agent/results/RESULTS_TABLE.md)).

| Policy | Success | Mean health | Actions per season |
|---|---|---|---|
| No intervention | 40% | 0.599 | 0 |
| Rule-based (given the optimal ranges) | 100% | 0.877 | 10.2 |
| **LLM agent, Llama 3.1 8B** | **96%** | **0.843** | 13.7 |
| Agent without probes | 88% | 0.835 | 15.8 |
| Agent without the twin check | 52% | 0.657 | 40.0 |
| Agent, Mistral Small 24B | 96% | 0.869 | 11.6 |

## Tests

```bash
ml/.venv/bin/python -m unittest discover -s agent/tests
```

Unity tests run from the Test Runner window, or headless:
`Unity -batchmode -projectPath . -runTests -testPlatform EditMode` (and `PlayMode`).

## Limitations

- The field is simulated; the agent has not managed a real plot.
- The twin check looks one day ahead.
- The probes are exact by construction, because the twin is also the simulator.

Next steps: a multi-day twin rollout in the check, a conformal uncertainty band in the veto, and
a real field trial.
