# PlantSim: a plant-growth digital twin with an LLM farm manager

A 144-plant, seven-stage crop simulated in Unity 6 (URP), driven by an FAO-56 style soil water
balance and a learned growth-score surrogate, and managed by a small LLM agent while weather
events hit the field.

| Folder | What it is |
|---|---|
| `Assets/Scripts/Core` | The twin: `GrowthEngine` (water balance, score, forecast), `GrowthModel` (C# evaluator for the exported tree ensemble), `Plant`, `FarmGrid`, `SimulationClock`, and `SimulationServer` (HTTP API for the agent) |
| `Assets/Scripts/UI` | Sliders, status panel, time controls, agent log panel |
| `Assets/Tests` | EditMode (C#/Python parity, forecast) and PlayMode (HTTP server) tests |
| `ml/` | Python twin core, surrogate training, ablation and twin evaluation ([paper](paper/main.tex)) |
| `agent/` | The farm-manager agent, scenarios, baselines, evaluation and results ([README](agent/README.md), [paper](paper/agent/main.tex)) |
| `paper/` | `main.tex`: the predictive-twin paper. `agent/main.tex`: the agent paper |

## Quick start

Unity: open the project in Unity 6000.3.10f1 and play `Assets/Scenes/SampleScene.unity`.

Python (one virtual environment for `ml/` and `agent/`):
```bash
python3 -m venv ml/.venv && ml/.venv/bin/pip install -r ml/requirements.txt
cp .env.example .env    # add DEEPINFRA_API_KEY for real LLM calls
./run_agent.sh agent/live_agent.py --backend local --scenario drought --dry-run
```

Tests:
```bash
cd agent && ../ml/.venv/bin/python -m unittest discover tests
```
Unity tests run from the Test Runner window, or headless with
`Unity -batchmode -projectPath . -runTests -testPlatform EditMode` (and `PlayMode`).
