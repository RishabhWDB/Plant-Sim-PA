# Autonomous Farm Manager Agent

An LLM agent that manages the Unity plant growth digital twin. It observes the farm, diagnoses
what is limiting growth, tests fixes on the digital twin, acts through limited farm equipment,
and lets time pass, while weather events hit the farm without warning.

## Architecture

```
Python agent (Claude, tool use)                     Unity (Play mode)
  observe  -> get_farm_status   --HTTP-->  SimulationServer.cs  GET  /state
  plan     -> simulate_change   --HTTP-->                       POST /predict   (what-if, changes nothing)
  act      -> adjust_control    --HTTP-->                       POST /environment
  wait     -> advance_days      --HTTP-->                       POST /advance   (steps SimulationClock)
  explain  -> reasoning lines   --HTTP-->                       POST /log       (shown on screen)

FarmEnvironment (Python) sits between the agent and the sim and enforces the rules:
  - only soil_moisture, ph, sunlight_hours, humidity are controllable
  - each action has an actuator limit (e.g. pH moves at most 0.5 per action)
  - temperature and rainfall are weather: scenarios change them, the agent cannot
  - every day, intervention and weather event is logged to runs/*.jsonl
```

What makes it agentic rather than scripted:
- The agent is **not told the crop's ideal ranges**. It uses agronomy knowledge plus the
  `simulate_change` tool to discover what helps.
- It chooses its own control loop timing (big steps when stable, small steps during events).
- It reacts to unannounced weather events and partial controllability (it cannot stop a drought,
  only compensate for it).
- It writes a season report reflecting on its own decisions at the end.

## Files

```
Unity/
  SimulationServer.cs   NEW  HTTP API inside Unity
  SimulationClock.cs    UPDATED  adds AdvanceOneDay()
  GrowthEngine.cs       UPDATED  PlaceholderModel is now public, null-safe day tick
  SlidersPanel.cs       UPDATED  adds SetParameter() so agent changes move the sliders
agent/
  farm_agent.py         the LLM agent (tools, system prompt, loop, season report)
  farm_env.py           rules of the game, actuator limits, weather application, logging
  scenarios.py          calm, drought, monsoon, acid_soil, heatwave_storm
  baselines.py          no-intervention and rule-based controllers
  sim_backends.py       UnitySim (HTTP) and LocalSim (Python replica, no Unity needed)
  run.py                run one season
  evaluate.py           every policy on every scenario, CSV + charts
```

## Unity setup

1. Replace `SimulationClock.cs`, `GrowthEngine.cs`, `SlidersPanel.cs` in your project with the ones in `Unity/`.
   SimulationClock and GrowthEngine go in `Assets/Scripts/Core/`, SlidersPanel in `Assets/Scripts/UI/`.
2. Copy `SimulationServer.cs` into `Assets/Scripts/Core/`.
3. Select **SimulationManager**, Add Component, **SimulationServer**. Drag in:
   - Clock: SimulationManager
   - Growth Engine: SimulationManager
   - Farm Grid: FarmGrid
   - Sliders Panel: Canvas/SlidersPanel
4. Optional on-screen agent log: under Canvas create **UI, Text - TextMeshPro** named `AgentLog`,
   anchor it bottom left, width ~600, font size 16, and drag it into **Agent Log Text**.
5. Press Play. The Console should show `SimulationServer: listening on http://localhost:8765/`.

Quick check from a terminal while Play mode is running:
```bash
curl http://localhost:8765/state
```

## Python setup

```bash
cd agent
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r ../requirements.txt
export ANTHROPIC_API_KEY=your_key_here               # Windows: set ANTHROPIC_API_KEY=...
```

## Running

Live demo, agent driving Unity (Unity must be in Play mode):
```bash
python run.py --policy agent --scenario drought
```

Without Unity (fast, for development):
```bash
python run.py --policy agent --scenario monsoon --backend local
```

Baselines:
```bash
python run.py --policy rule --scenario drought --backend local
python run.py --policy none --scenario drought --backend local
```

Evaluation for the report:
```bash
python evaluate.py                    # baselines only
python evaluate.py --include-agent    # adds the LLM agent (uses API credits)
```
Outputs go to `runs/eval/`: `results.csv`, `progress_<scenario>.png`, per-run JSONL logs,
summaries, and the agent's season reports.

Model: defaults to `claude-sonnet-5-5`. Change with `--model` or the `AGENT_MODEL` env var.

## Scenarios

| Scenario | What happens | No intervention |
|---|---|---|
| calm | No events. Control case. | matures day 51 |
| drought | Day 15 to 38: rain stops, 36 C, soil and air dry out daily | dies |
| monsoon | Day 20 to 42: 110 mm rain, 92% humidity, overcast, soil waterlogs daily | dies |
| acid_soil | Starts acidic, dry and overcast; acid rain on day 30 | dies |
| heatwave_storm | Day 18 to 30 heatwave, day 40 to 47 storm | matures late (day 77) |

The rule-based baseline knows the true optimal ranges and matures the crop in every scenario
(days 51 to 71, 8 actions each). That is the bar for the agent: match it **without** being given the ranges.

## Metrics

```bash
python evaluate.py --seeds 5                  # baselines, then metrics automatically
python evaluate.py --seeds 5 --include-agent  # adds the agent (API credits)
python metrics.py --runs-dir runs/eval        # recompute from existing logs
```

Seed 0 is the canonical scenario; seeds 1+ shift event timing by up to 3 days and event
intensity by up to 15%, so results measure robustness rather than one fixed script.

| Group | Metrics |
|---|---|
| Outcome | success rate, death rate, days to maturity, final progress |
| Crop health | mean growth score, min score, stress days (< 0.5), critical days (< 0.2) |
| Resilience (per event) | score drop, progress lost, stress days in event, reaction time, recovery time, recovery rate |
| Efficiency | interventions, per 100 days, by parameter, irrigation used, actuator-limited actions |
| Relative | days saved vs no intervention, gap vs rule baseline |
| Agent | LLM calls, tokens, tool calls by type, tool error rate, what-if queries per action, mean days per advance |

Outputs in `runs/eval/`: `METRICS.md` (report tables), `metrics_runs.csv`, `metrics_summary.csv`,
`metrics_events.csv`, `metrics_overview.png`, `metrics_resilience.png`, `progress_<scenario>.png`.

## Ideas for extending it in class

- Give the agent memory across seasons (store season reports, load them next run).
- Multi-agent version: a weather-forecaster agent that warns the manager agent.
- Add an equipment budget so the agent must trade off cost against yield.
- Swap PlaceholderModel for the ONNX model via Sentis; the agent code doesn't change.
