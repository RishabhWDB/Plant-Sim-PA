# Autonomous Farm Manager Agent

An LLM agent that manages the v4 plant-growth digital twin. It observes the farm, diagnoses
what is limiting growth, tests fixes on the twin, acts through limited farm equipment, and lets
time pass, while weather events hit the farm without warning.

## Architecture

```
Python agent (Claude, tool use)                     Unity (Play mode)
  observe  -> get_farm_status   --HTTP-->  SimulationServer.cs  GET  /state
  plan     -> simulate_change   --HTTP-->                       POST /predict   (tomorrow, changes nothing)
  act      -> adjust_control    --HTTP-->                       POST /environment
  wait     -> advance_days      --HTTP-->                       POST /advance   (steps SimulationClock)
  explain  -> reasoning lines   --HTTP-->                       POST /log       (AgentLogPanel on screen)

FarmEnvironment (Python) sits between the agent and the twin and enforces the rules:
  - only soil_moisture, ph, sunlight_hours, humidity are controllable
  - each action has an actuator limit (soil moisture 20, pH 0.5, sunlight 3 h, humidity 15)
  - temperature and rainfall are weather: scenarios change them, the agent cannot
  - every day, intervention and weather event is logged
```

What makes it agentic rather than scripted:
- The agent is **not told the crop's ideal ranges**. It uses agronomy knowledge plus the
  `simulate_change` tool to discover what helps.
- It chooses its own control loop timing (big steps when stable, small steps during events).
- It reacts to unannounced weather events and partial controllability (it cannot stop a drought,
  only compensate for it).
- It writes a season report reflecting on its own decisions at the end.

## The v4 twin, as the agent sees it

- **Soil moisture is a state.** Each day an FAO-56 style water balance moves it: rain (mm/day)
  adds water, crop evapotranspiration removes it, water above field capacity drains.
  `adjust_control(soil_moisture, X)` irrigates or drains the field to X that day (at most 20
  points from today's value); the water balance continues from there.
- **The growth score** comes from the trained surrogate (`ml/outputs/`), evaluated after the
  day's water balance at the stage the field had that morning. Rainfall is not a direct input.
- **`get_farm_status`** includes soil moisture, crop water use (ETc), the forecast of days to
  maturity or death with its 90% conformal band, and whether the learned model is active.
- **`simulate_change`** returns tomorrow's score and soil moisture under the hypothetical
  change, plus the forecast from that score.

Both backends implement this identically: `UnitySim` drives `SimulationServer.cs`; `LocalSim`
is a Python replica built on `ml/twin_core.py` and is tested step for step against it
(`agent/tests/test_localsim.py`).

## Files

```
Assets/Scripts/Core/SimulationServer.cs   HTTP API inside Unity (optional component)
Assets/Scripts/UI/AgentLogPanel.cs        on-screen agent log
agent/
  farm_agent.py      the LLM agent (tools, system prompt, loop, season report)
  farm_env.py        rules of the game, actuator limits, weather application, logging
  scenarios.py       calm, drought, monsoon, acid_soil, heatwave_storm
  baselines.py       no-intervention and rule-based controllers
  sim_backends.py    UnitySim (HTTP) and LocalSim (Python replica of the v4 twin)
  run.py             run one season
  evaluate.py        every policy on every scenario
  metrics.py         metrics, report tables and charts
  results/           evaluation output (baselines committed)
  tests/             LocalSim parity tests
```

## Setup

One virtual environment serves `ml/` and `agent/` (from the repository root):

```bash
python3 -m venv ml/.venv
ml/.venv/bin/pip install -r ml/requirements.txt
export ANTHROPIC_API_KEY=your_key_here     # only for the LLM agent
```

`LocalSim` loads `ml/outputs/surrogate_v4.pkl` (created by `ml/train_model.py`, not committed).
Without it, it evaluates `ml/outputs/growth_model.json` with the same tree traversal as
`GrowthModel.cs`; results are identical, only slower.

## Running

Live demo, agent driving Unity (Unity must be in Play mode with SimulationServer enabled):
```bash
ml/.venv/bin/python agent/run.py --policy agent --backend unity --scenario drought
```

Without Unity:
```bash
ml/.venv/bin/python agent/run.py --policy agent --backend local --scenario monsoon
ml/.venv/bin/python agent/run.py --policy rule  --backend local --scenario drought
```

Evaluation:
```bash
ml/.venv/bin/python agent/evaluate.py --seeds 5                   # baselines, about 2 minutes
ml/.venv/bin/python agent/evaluate.py --seeds 5 --include-agent   # adds the agent (API credits)
```
Outputs go to `agent/results/`: `RESULTS_TABLE.md` (success rate, mean health, reaction days,
actions per season, what-if per action), `METRICS.md`, CSVs, charts, and per-run logs, summaries
and agent season reports in `results/runs/`.

Model: `claude-sonnet-5-5` by default; change with `--model` or the `AGENT_MODEL` env var.

Tests:
```bash
cd agent && ../ml/.venv/bin/python -m unittest discover tests
```

## Scenarios

Rainfall is in mm/day; normal weather is 25 C, 62% humidity, 8 h of sunshine and 3 mm/day of
rain. Events act on soil only through the weather and the water balance.

| Scenario | What happens | No intervention (seeds 0 to 4) | Rule-based |
|---|---|---|---|
| calm | No events. Control case. | matures, days 54 to 55 | matures, days 53 to 54 |
| drought | Days 15 to 38: no rain, 36 C, 10 h sun, air dries 2%/day | dies, days 61 to 77 | matures, days 65 to 68 |
| monsoon | Days 16 to 46: 45 mm/day, 92% humidity, 4 h sun; soil saturates | dies, days 35 to 48 | matures, days 88 to 99 |
| acid_soil | Starts at pH 4.4, soil 30%, 4.5 h sun, 1 mm/day; acid rain day 30 (pH -1.2) | dies, days 40 to 48 | matures, days 64 to 74 |
| heatwave_storm | Days 18 to 30: 41 C, no rain, air dries 3%/day; days 40 to 47: 32 mm/day, 3 h sun | matures late, days 84 to 95 | matures, days 68 to 71 |

The rule-based baseline knows the true optimal ranges and checks every three days. That is the
bar for the agent: match it **without** being given the ranges.

Seed 0 is the canonical scenario; seeds 1+ shift event timing by up to 3 days and scale event
intensity (daily drift and event rainfall) by up to 15%.

## Metrics

| Group | Metrics |
|---|---|
| Outcome | success rate, death rate, days to maturity, final progress |
| Crop health | mean growth score, min score, stress days (< 0.5), critical days (< 0.2) |
| Resilience (per event) | score drop, progress lost, stress days in event, reaction time, recovery time, recovery rate |
| Efficiency | interventions, per 100 days, by parameter, irrigation and drainage (mm), actuator-limited actions |
| Relative | days saved vs no intervention, gap vs rule baseline |
| Agent | LLM calls, tokens (incl. cache), cost, tool calls by type, tool error rate, what-if queries per action, mean days per advance |
