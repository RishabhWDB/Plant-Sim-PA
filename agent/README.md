# Live Farm Manager Agent

A periodic LLM agent that manages the v4 plant-growth digital twin. Every few days of simulated
time it reads the farm state, asks a small LLM on DeepInfra what to change, checks the plan with
the twin, and applies it through limited farm equipment, while weather events hit the farm
without warning.

## Design

One LLM call per tick, no tool loop, no conversation history:

```
every tick
  1. read the state          GET /state (Unity) or LocalSim.state()
  2. ask the LLM             compact prompt (about 500 tokens): state, forecast and 90% band,
                             limiting factor, last 3 decisions and their score change
                             reply: {"reasoning": ..., "actions": [{"parameter", "value"}]}, at most 2
  3. check with the twin     /predict with the plan versus doing nothing; reject the plan if
                             tomorrow's score would drop by more than 0.02 (no extra LLM call)
  4. apply                   clip to actuator limits, POST /environment, POST /log (AgentLogPanel)
  5. log                     one JSON line per tick: state, tokens, actions, rejection, latency
at season end                one more call writes a short season report
```

The rules of the game (FarmEnvironment):
- only soil_moisture, ph, sunlight_hours, humidity are controllable
- each action is limited: soil moisture 20, pH 0.5, sunlight 3 h, humidity 15
- temperature and rainfall are weather: scenarios change them, the agent cannot
- the agent is **not told the crop's optimal ranges**; it gets the name of the limiting factor
  and the twin's feedback, and must rely on agronomy knowledge for the values

Any LLM failure (timeout, HTTP error, invalid JSON) means "no action" for that tick and is
logged; the loop never stops because of the model.

## The v4 twin, as the agent sees it

- **Soil moisture is a state.** Each day an FAO-56 style water balance moves it: rain (mm/day)
  adds water, crop evapotranspiration removes it, water above field capacity drains. Setting
  soil_moisture to X irrigates or drains the field to X that day (at most 20 points from today's
  value); the water balance continues from there.
- **The growth score** comes from the trained surrogate (`ml/outputs/`), evaluated after the
  day's water balance at the stage the field had that morning.
- **The forecast** gives days to maturity or death if conditions persist, with the 90% conformal
  band.

`LocalSim` (`sim_backends.py`) is a Python replica of the Unity twin built on
`ml/twin_core.py`, tested step for step against it (`tests/test_localsim.py`).

## Modes

| Mode | Time | Decisions |
|---|---|---|
| `--backend unity` | Unity's clock runs normally (3 s per day at 1x); the loop applies the scenario's weather as days pass | every `--tick` seconds of wall time (default 12) |
| `--backend local` | no sleeping, a season takes about a minute | every `--days-per-tick` simulated days (default 3) |

The baselines step Unity with `/advance`, which the server keeps for them.

## Files

```
Assets/Scripts/Core/SimulationServer.cs   HTTP API inside Unity (optional component)
Assets/Scripts/UI/AgentLogPanel.cs        on-screen agent log
agent/
  live_agent.py      the periodic agent (prompt, twin check, apply, log, season report)
  llm_client.py      DeepInfra client (OpenAI-compatible) and the dry-run fake
  farm_env.py        rules of the game, actuator limits, weather, logging
  scenarios.py       calm, drought, monsoon, acid_soil, heatwave_storm
  baselines.py       no-intervention and rule-based controllers
  sim_backends.py    UnitySim (HTTP) and LocalSim (Python replica of the v4 twin)
  run.py             run one season with any policy
  evaluate.py        every policy on every scenario
  metrics.py         metrics, report tables and charts
  results/           evaluation output (baselines committed)
  tests/             LocalSim parity and live agent tests
```

## Setup

One virtual environment serves `ml/` and `agent/` (from the repository root):

```bash
python3 -m venv ml/.venv
ml/.venv/bin/pip install -r ml/requirements.txt
cp .env.example .env          # then put your key in .env (only needed for real LLM calls)
```

Settings live in `.env` at the repository root, which is git-ignored and never committed:

```
DEEPINFRA_API_KEY=your_key_here
DEEPINFRA_MODEL=meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo
```

They are loaded automatically from any working directory. A variable exported in your shell
overrides the value in `.env`, e.g. `DEEPINFRA_MODEL=mistralai/Mistral-Small-24B-Instruct-2501 ./run_agent.sh ...`.

`./run_agent.sh` runs a script with the venv's Python without activating it; script paths are
relative to the repository root:

```bash
./run_agent.sh agent/live_agent.py --backend local --scenario drought
```

`LocalSim` loads `ml/outputs/surrogate_v4.pkl` (created by `ml/train_model.py`, not committed).
Without it, it evaluates `ml/outputs/growth_model.json` with the same tree traversal as
`GrowthModel.cs`; results are identical, only slower.

## Running

Live demo (Unity in Play mode with SimulationServer enabled):
```bash
./run_agent.sh agent/live_agent.py --backend unity --scenario drought
```

Without Unity:
```bash
./run_agent.sh agent/live_agent.py --backend local --scenario monsoon
./run_agent.sh agent/run.py --policy rule --backend local --scenario drought
```

Evaluation:
```bash
./run_agent.sh agent/evaluate.py --seeds 5                   # baselines, about 2 minutes
./run_agent.sh agent/evaluate.py --seeds 5 --include-agent   # adds the live agent (DeepInfra)
```
Outputs go to `agent/results/`: `RESULTS_TABLE.md` (success rate, mean health, reaction days,
actions per season, what-if per action), `METRICS.md`, CSVs, charts, and per-run logs, summaries
and season reports in `results/runs/`.

Without spending anything, add `--dry-run` to any agent command: a fake LLM returns a fixed,
sensible reply (typical tomato values for the two controls furthest from them). Dry-run
evaluations are written to `agent/runs/dry_run_eval/` and never overwrite `agent/results/`.
They test the plumbing, not the model.

Tests:
```bash
cd agent && ../ml/.venv/bin/python -m unittest discover tests
```

## Cost

Default model `meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo` at $0.02 / $0.04 per million input /
output tokens. A local season makes about 20 to 30 calls of about 500 to 650 prompt tokens and
up to about 100 output tokens, around 15,000 to 25,000 tokens in all: well under $0.001 per
season, and under $0.02 for the full 25-season evaluation.

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

The rule-based baseline knows the true optimal ranges and checks every three days. Seed 0 is the
canonical scenario; seeds 1+ shift event timing by up to 3 days and scale event intensity
(daily drift and event rainfall) by up to 15%.

## Metrics

| Group | Metrics |
|---|---|
| Outcome | success rate, death rate, days to maturity, final progress |
| Crop health | mean growth score, min score, stress days (< 0.5), critical days (< 0.2) |
| Resilience (per event) | score drop, progress lost, stress days in event, reaction time, recovery time, recovery rate |
| Efficiency | interventions, per 100 days, by parameter, irrigation and drainage (mm), actuator-limited actions |
| Relative | days saved vs no intervention, gap vs rule baseline |
| Agent | LLM calls, tokens, cost, decisions rejected by the twin, error rate, latency, what-if queries per action |
