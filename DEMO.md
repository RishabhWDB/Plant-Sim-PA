# Live demo runbook

About 5 minutes: the LLM agent manages the Unity field through a drought, and its reasoning
appears on screen.

## Before you start (once)

- Unity 6000.3.10f1 is installed (Unity Hub → Installs).
- `.env` at the repo root has `DEEPINFRA_API_KEY` (a season costs about $0.0006).
- SampleScene contains SimulationServer and AgentLogPanel. If not, run
  **PlantSim → Set Up Agent Demo Scene** in the Unity menu.

## Run it

1. Open the project in Unity Hub and open `Assets/Scenes/SampleScene.unity`.
2. Press **Play**. The Console shows `SimulationServer: listening on http://localhost:8765/`.
3. In a terminal at the repo root, start the agent:

   ```bash
   ./run_agent.sh agent/run.py --policy agent --backend unity --scenario drought --tick 9
   ```

   A day lasts 3 s, so `--tick 9` gives one decision every 3 simulated days.
   The drought starts around day 15 and the crop matures around day 65 (about 3–4 minutes).
4. Point out the three moving parts:
   - the **agent log** (bottom left): the model's reasoning and the actions it takes;
   - actions the twin vetoed, listed in the terminal and in the log;
   - the **status panel** (top right): growth score, soil moisture and the forecast.

Other scenarios: `calm`, `drought`, `monsoon`, `acid_soil`, `heatwave_storm`.
`acid_soil` shows the twin vetoing pH moves in the wrong direction.
Add `--max-days 30` for a shorter run.

## If something goes wrong

| Problem | Fix |
|---|---|
| `Connection refused` | Unity isn't in Play mode, or the scene has no SimulationServer (run the menu item above) |
| `could not listen on port 8765` in the Console | Another Play session or app holds the port: stop Play, close it, press Play again |
| No internet, or DeepInfra errors | The agent takes no action that tick. Fallback run with a fake LLM: add `--dry-run` |
| Unity misbehaves | Show the same agent on the Python twin, no Unity needed: `./run_agent.sh agent/run.py --policy agent --backend local --scenario drought` |

Results and figures for the slides: `agent/results/`, `paper/agent/main.pdf`.
