"""
Batch evaluation on the local replica of the v4 twin: every policy on every scenario.

  python agent/evaluate.py --seeds 5                                # baselines only (free, about 2 minutes)
  python agent/evaluate.py --seeds 5 --include-agent                # adds the live agent (DeepInfra credits)
  python agent/evaluate.py --seeds 5 --include-agent --dry-run      # fake LLM, written to agent/runs/dry_run_eval

Writes to agent/results/: results.csv, one progress chart per scenario, the metrics in
METRICS.md / metrics_*.csv, and RESULTS_TABLE.md with the rows used in the paper and slides.
Per-run logs, summaries and agent season reports go to agent/results/runs/.
"""

import argparse
import csv
import json
from pathlib import Path

from run import run_season
from scenarios import SCENARIOS

RESULTS_DIR = Path(__file__).resolve().parent / "results"

FIELDS = ["policy", "scenario", "seed", "outcome", "matured", "days_to_maturity",
          "final_progress_percent", "mean_growth_score", "days_with_score_below_0_5",
          "interventions", "irrigation_mm", "drainage_mm", "what_if_queries",
          "llm_calls", "input_tokens", "output_tokens", "llm_errors", "rejected_by_twin", "model"]


def load_curve(log_file):
    days, progress = [], []
    for line in open(log_file):
        r = json.loads(line)
        if r["type"] == "day":
            days.append(r["day"])
            progress.append(r["average_progress_percent"])
    return days, progress


def plot(results, out_dir, runs_dir):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed, skipping charts")
        return

    colors = {"none": "#9a9a9a", "rule": "#3b7dd8", "agent": "#2e9e5b"}
    for scenario in sorted({r["scenario"] for r in results}):
        fig, ax = plt.subplots(figsize=(8, 4.5))
        for r in results:
            if r["scenario"] != scenario or r["seed"] != 0:
                continue
            d, p = load_curve(runs_dir / r["log_file"])
            ax.plot(d, p, label=r["policy"], color=colors.get(r["policy"]), linewidth=2)
        for e in SCENARIOS[scenario].events:
            ax.axvspan(e.start_day, e.end_day + 1, color="#e8a33d", alpha=0.15)
            ax.text(e.start_day + 0.5, 101, e.name, fontsize=8, va="bottom")
        ax.set_title(f"Crop progress: {scenario}")
        ax.set_xlabel("Day")
        ax.set_ylabel("Average crop progress (%)")
        ax.set_ylim(0, 108)
        ax.grid(alpha=0.25)
        ax.legend()
        fig.tight_layout()
        fig.savefig(out_dir / f"progress_{scenario}.png", dpi=150)
        plt.close(fig)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--include-agent", action="store_true")
    p.add_argument("--seeds", type=int, default=1, help="plant-variation seeds per run")
    p.add_argument("--scenarios", nargs="*", default=list(SCENARIOS))
    p.add_argument("--max-days", type=int, default=120)
    p.add_argument("--dry-run", action="store_true", help="agent uses a fake LLM; results go to agent/runs")
    p.add_argument("--days-per-tick", type=int, default=3, help="simulated days between agent decisions")
    p.add_argument("--model", default=None, help="DeepInfra model (default DEEPINFRA_MODEL)")
    args = p.parse_args()

    policies = ["none", "rule"] + (["agent"] if args.include_agent else [])
    # Dry runs never overwrite the committed results
    out_dir = RESULTS_DIR.parent / "runs" / "dry_run_eval" if args.dry_run else RESULTS_DIR
    agent_options = {"dry_run": args.dry_run, "days_per_tick": args.days_per_tick, "model": args.model}
    runs_dir = out_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for scenario in args.scenarios:
        for policy in policies:
            for seed in range(args.seeds):
                print(f"Running {policy} on {scenario} (seed {seed})...")
                s = run_season(policy, scenario, backend="local", seed=seed,
                               max_days=args.max_days, log_dir=str(runs_dir), agent_options=agent_options,
                               verbose=False, timestamped=False)
                results.append(s)

    with open(out_dir / "results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(results)

    plot(results, out_dir, runs_dir)

    print(f"\n{'policy':<7} {'scenario':<15} {'outcome':<13} {'days':>5} {'progress':>9} {'actions':>8}")
    for r in results:
        print(f"{r['policy']:<7} {r['scenario']:<15} {r['outcome']:<13} {r['final_day']:>5} "
              f"{r['final_progress_percent']:>8.1f}% {r['interventions']:>8}")
    print(f"\nResults written to {out_dir}/")
    print("Computing metrics...\n")
    import metrics
    import sys
    sys.argv = ["metrics.py", "--runs-dir", str(runs_dir), "--out-dir", str(out_dir)]
    metrics.main()


if __name__ == "__main__":
    main()
