"""
Run one season.

Examples (from the repository root)
  python agent/run.py --policy agent --backend unity --scenario drought   # agent drives Unity
  python agent/run.py --policy agent --scenario monsoon --backend local   # no Unity needed
  python agent/run.py --policy rule  --scenario heatwave_storm --backend local

Logs, summaries and the agent's season report go to agent/runs/.
"""

import argparse
import json
import time
from pathlib import Path

from baselines import NoInterventionPolicy, RuleBasedPolicy
from farm_env import FarmEnvironment
from scenarios import SCENARIOS, jittered
from sim_backends import LocalSim, UnitySim

RUNS_DIR = Path(__file__).resolve().parent / "runs"


def make_policy(name, model=None, verbose=True):
    if name == "none":
        return NoInterventionPolicy()
    if name == "rule":
        return RuleBasedPolicy()
    if name == "agent":
        from farm_agent import LLMFarmAgent
        return LLMFarmAgent(model=model, verbose=verbose)
    raise ValueError(name)


def make_backend(name, url, seed):
    if name == "local":
        return LocalSim(seed=seed)
    sim = UnitySim(url)
    try:
        sim.health()
    except Exception as e:
        raise SystemExit(f"Cannot reach Unity at {url}. Is the scene in Play mode?\n{e}")
    return sim


def run_season(policy_name, scenario_name, backend="unity", url="http://localhost:8765",
               max_days=120, seed=0, model=None, log_dir=RUNS_DIR, verbose=True, timestamped=True):
    scenario = jittered(SCENARIOS[scenario_name], seed)
    sim = make_backend(backend, url, seed)
    run_name = f"{policy_name}_{scenario_name}_s{seed}"
    if timestamped:
        run_name = f"{time.strftime('%Y%m%d_%H%M%S')}_{run_name}"
    env = FarmEnvironment(sim, scenario, max_days=max_days, log_dir=log_dir,
                          run_name=run_name, verbose=verbose)
    policy = make_policy(policy_name, model, verbose)

    env.reset()
    try:
        summary = policy.run(env)
    finally:
        env.close()

    summary["policy"] = policy_name
    summary["seed"] = seed
    summary["events"] = [{"name": e.name, "start_day": e.start_day, "end_day": e.end_day}
                         for e in scenario.events]
    summary["log_file"] = env.log_path.name     # next to the summary file

    out = Path(log_dir) / f"{run_name}_summary.json"
    out.write_text(json.dumps(summary, indent=2))
    report = getattr(policy, "season_report", "")
    if report:
        (Path(log_dir) / f"{run_name}_report.md").write_text(report)
    return summary


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--policy", choices=["none", "rule", "agent"], default="agent")
    p.add_argument("--scenario", choices=list(SCENARIOS), default="drought")
    p.add_argument("--backend", choices=["unity", "local"], default="unity")
    p.add_argument("--url", default="http://localhost:8765")
    p.add_argument("--max-days", type=int, default=120)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--model", default=None)
    args = p.parse_args()

    summary = run_season(args.policy, args.scenario, args.backend, args.url,
                         args.max_days, args.seed, args.model)
    print("\nSummary")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
