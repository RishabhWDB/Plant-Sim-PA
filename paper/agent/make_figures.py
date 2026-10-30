"""
Figures for the agent paper, from the evaluation logs in agent/results/runs.

  ./run_agent.sh paper/agent/make_figures.py

Writes to paper/agent/figures/
  progress.pdf        crop progress over the season (seed 0) for the baselines and two agent
                      designs, one panel per scenario, with the weather events shaded
  results_table.tex   success and mean health per scenario, plus totals, for every policy
  agent_table.tex     LLM calls, twin rejections, errors, tokens, latency and cost per season
Every number in the tables comes from agent/metrics.py applied to the run logs.
"""

import json
import statistics
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "agent" / "results" / "runs"
OUT = Path(__file__).resolve().parent / "figures"
sys.path.insert(0, str(ROOT / "agent"))
from metrics import POLICY_LABEL, POLICY_ORDER, load_runs, run_metrics  # noqa: E402
from scenarios import SCENARIOS  # noqa: E402

SCENARIO_ORDER = ["calm", "drought", "monsoon", "acid_soil", "heatwave_storm"]
SCENARIO_LABEL = {"calm": "Calm", "drought": "Drought", "monsoon": "Monsoon",
                  "acid_soil": "Acid soil", "heatwave_storm": "Heat+storm"}

POLICIES = [("none", "No intervention", "#9a9a9a", "-"),
            ("rule", "Rule-based (knows optima)", "#eb6834", "-"),
            ("agent_noprobe", "Agent, no probes", "#8a5cc2", "--"),
            ("agent", "Agent (probes + check)", "#1baf7a", "-")]
PANELS = ["acid_soil", "drought", "monsoon"]


def curve(policy, scenario, seed=0):
    path = RUNS / f"{policy}_{scenario}_s{seed}.jsonl"
    days, progress = [], []
    for line in open(path):
        r = json.loads(line)
        if r["type"] == "day":
            days.append(r["day"])
            progress.append(r["average_progress_percent"])
    return days, progress


def mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.mean(xs) if xs else None


def tables():
    rows, events = [], []
    for summary, records in load_runs(RUNS):
        m, ev = run_metrics(summary, records)
        rows.append(m)
        events += ev
    policies = [p for p in POLICY_ORDER if any(r["policy"] == p for r in rows)]

    out = [r"\begin{tabular}{@{}l" + "c" * len(SCENARIO_ORDER) + r"cccc@{}}", r"\toprule",
           r"& \multicolumn{%d}{c}{Matured seasons / mean health $H$} & \multicolumn{4}{c}{All 25 seasons} \\"
           % len(SCENARIO_ORDER),
           r"\cmidrule(lr){2-%d}\cmidrule(l){%d-%d}" % (len(SCENARIO_ORDER) + 1, len(SCENARIO_ORDER) + 2,
                                                        len(SCENARIO_ORDER) + 5),
           "Policy & " + " & ".join(SCENARIO_LABEL[s] for s in SCENARIO_ORDER)
           + r" & Success & $H$ & Actions & React. (d) \\", r"\midrule"]
    for p in policies:
        cells = []
        for sc in SCENARIO_ORDER:
            rs = [r for r in rows if r["policy"] == p and r["scenario"] == sc]
            cells.append(f"{sum(r['matured'] for r in rs)}/{len(rs)}, {mean(r['mean_score'] for r in rs):.2f}")
        rs = [r for r in rows if r["policy"] == p]
        react = mean(e["reaction_days"] for e in events if e["policy"] == p)
        cells += [f"{100 * mean(r['matured'] for r in rs):.0f}\\%", f"{mean(r['mean_score'] for r in rs):.3f}",
                  f"{mean(r['interventions'] for r in rs):.1f}", "--" if react is None else f"{react:.1f}"]
        out.append(POLICY_LABEL[p] + " & " + " & ".join(cells) + r" \\")
        if p == "rule":
            out.append(r"\midrule")
    out += [r"\bottomrule", r"\end{tabular}"]
    (OUT / "results_table.tex").write_text("\n".join(out) + "\n")

    agent = [p for p in policies if p.startswith("agent")]
    out = [r"\begin{tabular}{@{}lcccccc@{}}", r"\toprule",
           r"Variant & Calls & Vetoed & Errors & Tokens/call & Latency (s) & USD \\", r"\midrule"]
    for p in agent:
        rs = [r for r in rows if r["policy"] == p]
        cost = mean(r.get("cost_usd") for r in rs)
        out.append(f"{POLICY_LABEL[p].replace('Agent, ', '')} & {mean(r['llm_calls'] for r in rs):.1f} & "
                   f"{mean(r['rejected_by_twin'] for r in rs):.1f} & {100 * mean(r['error_rate'] for r in rs):.1f}\\% & "
                   f"{mean(r['mean_prompt_tokens'] for r in rs):.0f} & {mean(r['mean_latency_s'] for r in rs):.2f} & "
                   f"{cost:.5f} \\\\")
    out += [r"\bottomrule", r"\end{tabular}"]
    (OUT / "agent_table.tex").write_text("\n".join(out) + "\n")
    print(f"Written {OUT / 'results_table.tex'} and {OUT / 'agent_table.tex'}")


def main():
    plt.rcParams.update({"font.family": "serif", "font.size": 7, "axes.linewidth": 0.6,
                         "xtick.major.width": 0.6, "ytick.major.width": 0.6})
    OUT.mkdir(exist_ok=True)
    fig, axes = plt.subplots(1, len(PANELS), figsize=(7.0, 1.9), sharey=True)
    for ax, scenario in zip(axes, PANELS):
        for e in SCENARIOS[scenario].events:
            ax.axvspan(e.start_day, e.end_day + 1, color="#e8a33d", alpha=0.18, lw=0)
        for policy, label, color, style in POLICIES:
            d, p = curve(policy, scenario)
            ax.plot(d, p, style, color=color, lw=1.1, label=label)
        ax.axhline(98, color="#555555", lw=0.5, ls=":")
        ax.set_title(scenario.replace("_", " "), fontsize=7.5)
        ax.set_xlabel("Day")
        ax.set_xlim(0, 120)
        ax.set_xticks([0, 30, 60, 90, 120])
        ax.set_ylim(0, 102)
        ax.grid(alpha=0.25, lw=0.4)
    axes[0].set_ylabel("Mean crop progress (%)")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=4, frameon=False, fontsize=7,
               bbox_to_anchor=(0.5, 1.04))
    fig.tight_layout(rect=(0, 0, 1, 0.9), w_pad=0.6)
    fig.savefig(OUT / "progress.pdf", bbox_inches="tight")
    print(f"Written {OUT / 'progress.pdf'}")
    tables()


if __name__ == "__main__":
    main()
