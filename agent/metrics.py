"""
Computes evaluation metrics from run logs.

  python agent/evaluate.py --seeds 5 [--include-agent]
  python agent/metrics.py                 # reads agent/results/runs, writes agent/results

Outputs (in agent/results):
  metrics_runs.csv       one row per run, every metric
  metrics_summary.csv    mean and std per policy and scenario
  metrics_events.csv     one row per weather event per run (resilience)
  METRICS.md             report-ready tables
  RESULTS_TABLE.md       the rows used in the paper and slides (also results_table.csv)
  metrics_overview.png   success, speed, stress and effort per scenario
  metrics_resilience.png reaction and recovery after weather events

Metric groups
  Outcome      success (matured), days to maturity, final progress
  Crop health  mean growth score, minimum score, stress days (score < 0.5), critical days (< 0.2)
  Resilience   per event: score drop, progress lost, stress days during event,
               reaction time (first action after event start), recovery time
               (days until score >= 0.6 for 3 consecutive days)
  Efficiency   interventions, interventions per 100 days, irrigation and drainage (mm),
               actuator-limited actions
  Relative     days saved vs no intervention, gap vs rule baseline
  Agent only   LLM calls, tokens, cost, decisions rejected by the twin, LLM errors,
               latency, what-if queries (twin predictions) per action
"""

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

RECOVERY_SCORE = 0.6
RECOVERY_HOLD = 3

POLICY_ORDER = ["none", "rule", "agent", "agent_noprobe", "agent_nocheck", "agent_mistral"]
POLICY_LABEL = {"none": "No intervention", "rule": "Rule-based", "agent": "LLM agent",
                "agent_noprobe": "Agent, no probes", "agent_nocheck": "Agent, no twin check",
                "agent_mistral": "Agent, Mistral 24B"}
# Categorical slots 1-6 of the reference palette, fixed order by policy
POLICY_COLOR = {"none": "#2a78d6", "rule": "#eb6834", "agent": "#1baf7a",
                "agent_noprobe": "#8a5cc2", "agent_nocheck": "#d4a21f", "agent_mistral": "#d6457a"}

from llm_client import PRICES  # noqa: E402

HERE = Path(__file__).resolve().parent

def season_cost(summary):
    """USD for one season at DeepInfra's prices for the model (None for dry runs)."""
    p = PRICES.get(summary.get("model"))
    if not p:
        return None
    return round((summary.get("input_tokens", 0) * p[0] + summary.get("output_tokens", 0) * p[1]) / 1e6, 6)


# Loading

def load_runs(runs_dir):
    runs = []
    for summary_path in sorted(Path(runs_dir).glob("*_summary.json")):
        summary = json.loads(summary_path.read_text())
        log_path = Path(runs_dir) / Path(summary["log_file"]).name
        records = [json.loads(l) for l in open(log_path)] if log_path.exists() else []
        runs.append((summary, records))
    return runs


# Per-run metrics

def first_sustained(days, scores, start, threshold, hold):
    """First day >= start where score >= threshold for `hold` consecutive days."""
    streak = 0
    for d, s in zip(days, scores):
        if d < start:
            continue
        streak = streak + 1 if s >= threshold else 0
        if streak >= hold:
            return d - hold + 1
    return None


def event_metrics(summary, days, scores, progress, interventions):
    rows = []
    by_day = dict(zip(days, scores))
    prog_by_day = dict(zip(days, progress))
    last_day = days[-1] if days else 0

    for e in summary.get("events", []):
        start, end = e["start_day"], e["end_day"]
        if start > last_day:
            continue  # season finished before the event

        before = [by_day[d] for d in range(start - 3, start) if d in by_day]
        window = [by_day[d] for d in range(start, end + 6) if d in by_day]
        during = [by_day[d] for d in range(start, end + 1) if d in by_day]
        pre_score = statistics.mean(before) if before else None
        min_score = min(window) if window else None

        pre_prog = prog_by_day.get(start - 1, prog_by_day.get(start))
        win_prog = [prog_by_day[d] for d in range(start, end + 6) if d in prog_by_day]
        lost = max(0.0, pre_prog - min(win_prog)) if (pre_prog is not None and win_prog) else 0.0

        reactions = [i["day"] for i in interventions if i["day"] >= start - 1]
        reaction = (reactions[0] - start + 1) if reactions else None

        # Recovery: if the score dips below the threshold, days until it holds above it again
        # with the crop still alive. A dead crop never counts as recovered even if weather improves.
        dip_day = next((d for d in range(start, end + 6) if d in by_day and by_day[d] < RECOVERY_SCORE), None)
        if dip_day is None:
            recovery = 0
        else:
            rec_day = first_sustained(days, scores, dip_day, RECOVERY_SCORE, RECOVERY_HOLD)
            alive = rec_day is not None and prog_by_day.get(rec_day + RECOVERY_HOLD - 1, 0) > 0.5
            recovery = (rec_day - start) if alive else None

        rows.append({
            "policy": summary["policy"], "scenario": summary["scenario"], "seed": summary["seed"],
            "event": e["name"], "start_day": start, "end_day": end,
            "pre_event_score": round(pre_score, 4) if pre_score is not None else None,
            "min_score": round(min_score, 4) if min_score is not None else None,
            "score_drop": round(pre_score - min_score, 4) if None not in (pre_score, min_score) else None,
            "progress_lost_pct": round(lost, 2),
            "stress_days_during_event": sum(1 for s in during if s < 0.5),
            "reaction_days": reaction,
            "recovery_days": recovery,
            "recovered": recovery is not None,
        })
    return rows


def run_metrics(summary, records):
    day_rows = [r for r in records if r["type"] == "day"]
    days = [r["day"] for r in day_rows]
    scores = [r["growth_score"] for r in day_rows]
    progress = [r["average_progress_percent"] for r in day_rows]
    interventions = [r for r in records if r["type"] == "intervention"]
    ticks = [r for r in records if r["type"] == "tick"]

    sim_scores = scores[1:] if len(scores) > 1 else scores  # skip day 0 observation
    final_day = max(1, summary["final_day"])

    m = {
        "policy": summary["policy"],
        "scenario": summary["scenario"],
        "seed": summary["seed"],
        # outcome
        "matured": int(summary["matured"]),
        "died": int(summary["outcome"] == "dead"),
        "days_to_maturity": summary["days_to_maturity"],
        "final_day": summary["final_day"],
        "final_progress_pct": summary["final_progress_percent"],
        "peak_progress_pct": max(progress) if progress else 0,
        # crop health
        "mean_score": round(statistics.mean(sim_scores), 4) if sim_scores else None,
        "min_score": round(min(sim_scores), 4) if sim_scores else None,
        "stress_days": sum(1 for s in sim_scores if s < 0.5),
        "critical_days": sum(1 for s in sim_scores if s < 0.2),
        "stress_day_ratio": round(sum(1 for s in sim_scores if s < 0.5) / max(1, len(sim_scores)), 4),
        # efficiency
        "interventions": len(interventions),
        "interventions_per_100_days": round(100 * len(interventions) / final_day, 2),
        "irrigation_mm": summary.get("irrigation_mm", 0),
        "drainage_mm": summary.get("drainage_mm", 0),
        "actuator_limited_actions": sum(1 for i in interventions if i.get("limited_by_actuator")),
    }

    for p in ["soil_moisture", "ph", "sunlight_hours", "humidity"]:
        m[f"actions_{p}"] = sum(1 for i in interventions if i["parameter"] == p)

    # agent-only
    if summary.get("llm_calls"):
        n_actions = max(1, len(interventions))
        m.update({
            "llm_calls": summary.get("llm_calls"),
            "input_tokens": summary.get("input_tokens"),
            "output_tokens": summary.get("output_tokens"),
            "cost_usd": season_cost(summary),
            "tokens_per_day": round((summary.get("input_tokens", 0) + summary.get("output_tokens", 0))
                                    / final_day, 1),
            "decisions": len(ticks),
            "decisions_with_actions": sum(1 for t in ticks if t["actions_applied"]),
            "rejected_by_twin": sum(1 for t in ticks if t["rejected_by_twin"]),
            "llm_errors": summary.get("llm_errors", 0),
            "error_rate": round(sum(1 for t in ticks if t["error"]) / max(1, len(ticks)), 4),
            "mean_latency_s": summary.get("mean_latency_s"),
            "mean_prompt_tokens": round(statistics.mean([t["prompt_tokens"] for t in ticks] or [0]), 1),
            "what_if_per_action": round(summary.get("what_if_queries", 0) / n_actions, 2),
        })

    events = event_metrics(summary, days, scores, progress, interventions)
    return m, events


# Aggregation

AGG_FIELDS = ["matured", "died", "days_to_maturity", "final_progress_pct", "mean_score", "min_score",
              "stress_days", "critical_days", "interventions", "interventions_per_100_days",
              "irrigation_mm", "drainage_mm", "actuator_limited_actions",
              "llm_calls", "input_tokens", "output_tokens", "cost_usd", "rejected_by_twin",
              "llm_errors", "error_rate", "mean_latency_s", "mean_prompt_tokens", "what_if_per_action"]


def mean_std(values):
    vals = [v for v in values if v is not None]
    if not vals:
        return None, None
    if len(vals) == 1:
        return vals[0], 0.0
    return statistics.mean(vals), statistics.stdev(vals)


def aggregate(rows):
    groups = defaultdict(list)
    for r in rows:
        groups[(r["policy"], r["scenario"])].append(r)

    out = []
    for (policy, scenario), rs in groups.items():
        row = {"policy": policy, "scenario": scenario, "runs": len(rs)}
        for f in AGG_FIELDS:
            mu, sd = mean_std([r.get(f) for r in rs])
            row[f"{f}_mean"] = None if mu is None else round(mu, 4)
            row[f"{f}_std"] = None if sd is None else round(sd, 4)
        row["success_rate"] = round(sum(r["matured"] for r in rs) / len(rs), 4)
        out.append(row)

    # relative metrics vs baselines on the same scenario
    by_key = {(r["policy"], r["scenario"]): r for r in out}
    for r in out:
        none = by_key.get(("none", r["scenario"]))
        rule = by_key.get(("rule", r["scenario"]))
        mine = r["days_to_maturity_mean"]
        r["days_saved_vs_none"] = (round(none["days_to_maturity_mean"] - mine, 2)
                                   if none and mine is not None and none["days_to_maturity_mean"] is not None
                                   else None)
        r["days_gap_vs_rule"] = (round(mine - rule["days_to_maturity_mean"], 2)
                                 if rule and mine is not None and rule["days_to_maturity_mean"] is not None
                                 else None)
        r["stress_days_saved_vs_none"] = (round(none["stress_days_mean"] - r["stress_days_mean"], 2)
                                          if none else None)
    return sorted(out, key=lambda r: (r["scenario"], POLICY_ORDER.index(r["policy"])
                                      if r["policy"] in POLICY_ORDER else 9))


def overall(rows):
    """One line per policy across every scenario and seed."""
    out = []
    for policy in POLICY_ORDER:
        rs = [r for r in rows if r["policy"] == policy]
        if not rs:
            continue
        dtm = [r["days_to_maturity"] for r in rs if r["days_to_maturity"] is not None]
        out.append({
            "policy": policy,
            "runs": len(rs),
            "success_rate": round(sum(r["matured"] for r in rs) / len(rs), 4),
            "death_rate": round(sum(r["died"] for r in rs) / len(rs), 4),
            "days_to_maturity_mean": round(statistics.mean(dtm), 2) if dtm else None,
            "mean_score": round(statistics.mean(r["mean_score"] for r in rs), 4),
            "stress_days_mean": round(statistics.mean(r["stress_days"] for r in rs), 2),
            "interventions_mean": round(statistics.mean(r["interventions"] for r in rs), 2),
        })
    return out


def aggregate_events(events):
    groups = defaultdict(list)
    for e in events:
        groups[(e["policy"], e["scenario"], e["event"])].append(e)
    out = []
    for (policy, scenario, event), es in groups.items():
        def m(f):
            v = mean_std([x[f] for x in es])[0]
            return None if v is None else round(v, 2)
        out.append({
            "policy": policy, "scenario": scenario, "event": event, "runs": len(es),
            "score_drop": m("score_drop"),
            "progress_lost_pct": m("progress_lost_pct"),
            "stress_days_during_event": m("stress_days_during_event"),
            "reaction_days": m("reaction_days"),
            "recovery_days": m("recovery_days"),
            "recovery_rate": round(sum(x["recovered"] for x in es) / len(es), 4),
        })
    return sorted(out, key=lambda r: (r["scenario"], r["event"],
                                      POLICY_ORDER.index(r["policy"]) if r["policy"] in POLICY_ORDER else 9))


# Output

def write_csv(path, rows):
    if not rows:
        return
    fields = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def fmt(v, digits=1, pct=False):
    if v is None:
        return "-"
    if pct:
        return f"{v * 100:.0f}%"
    if isinstance(v, int):
        return str(v)
    return f"{v:.{digits}f}"


def pm(mean, std, digits=1):
    if mean is None:
        return "-"
    return f"{mean:.{digits}f} ± {std:.{digits}f}" if std else f"{mean:.{digits}f}"


def markdown_report(overall_rows, summary_rows, event_rows, run_rows):
    seeds = sorted({r["seed"] for r in run_rows})
    lines = ["# Evaluation Metrics", "",
             f"Runs: {len(run_rows)}  |  Seeds per cell: {len(seeds)}  |  "
             f"Policies: {', '.join(POLICY_LABEL.get(p, p) for p in POLICY_ORDER if any(r['policy'] == p for r in run_rows))}",
             "", "Seed 0 is the canonical scenario; other seeds shift event timing by up to 3 days "
                 "and scale event intensity by up to 15%. Values are mean ± std across seeds.", ""]

    lines += ["## Overall", "",
              "| Policy | Runs | Success | Death | Days to maturity | Mean score | Stress days | Interventions |",
              "|---|---|---|---|---|---|---|---|"]
    for r in overall_rows:
        lines.append(f"| {POLICY_LABEL.get(r['policy'], r['policy'])} | {r['runs']} | "
                     f"{fmt(r['success_rate'], pct=True)} | {fmt(r['death_rate'], pct=True)} | "
                     f"{fmt(r['days_to_maturity_mean'])} | {fmt(r['mean_score'], 3)} | "
                     f"{fmt(r['stress_days_mean'])} | {fmt(r['interventions_mean'])} |")

    lines += ["", "## By scenario", "",
              "| Scenario | Policy | Success | Days to maturity | Final progress % | Mean score | "
              "Stress days | Interventions | Days saved vs none | Gap vs rule |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for r in summary_rows:
        lines.append(
            f"| {r['scenario']} | {POLICY_LABEL.get(r['policy'], r['policy'])} | "
            f"{fmt(r['success_rate'], pct=True)} | {pm(r['days_to_maturity_mean'], r['days_to_maturity_std'])} | "
            f"{pm(r['final_progress_pct_mean'], r['final_progress_pct_std'])} | "
            f"{pm(r['mean_score_mean'], r['mean_score_std'], 3)} | "
            f"{pm(r['stress_days_mean'], r['stress_days_std'])} | "
            f"{pm(r['interventions_mean'], r['interventions_std'])} | "
            f"{fmt(r['days_saved_vs_none'])} | {fmt(r['days_gap_vs_rule'])} |")

    lines += ["", "## Resilience to weather events", "",
              "Reaction = days from event start to first action. "
              f"Recovery = days from event start until score stays ≥ {RECOVERY_SCORE} "
              f"for {RECOVERY_HOLD} days.", "",
              "| Scenario | Event | Policy | Score drop | Progress lost % | Stress days in event | "
              "Reaction (days) | Recovery (days) | Recovered |",
              "|---|---|---|---|---|---|---|---|---|"]
    for r in event_rows:
        lines.append(f"| {r['scenario']} | {r['event']} | {POLICY_LABEL.get(r['policy'], r['policy'])} | "
                     f"{fmt(r['score_drop'], 3)} | {fmt(r['progress_lost_pct'])} | "
                     f"{fmt(r['stress_days_during_event'])} | {fmt(r['reaction_days'])} | "
                     f"{fmt(r['recovery_days'])} | {fmt(r['recovery_rate'], pct=True)} |")

    agent_rows = [r for r in summary_rows if r["policy"].startswith("agent")]
    lines += ["", "## Agent behaviour", ""]
    if agent_rows:
        lines += ["| Policy | Scenario | LLM calls | Rejected by twin | Error rate | What-if per action | "
                  "Prompt tokens per call | Input tokens | Output tokens | Latency (s) | Cost (USD) |",
                  "|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in agent_rows:
            lines.append(f"| {POLICY_LABEL.get(r['policy'], r['policy'])} | {r['scenario']} | {pm(r['llm_calls_mean'], r['llm_calls_std'])} | "
                         f"{fmt(r['rejected_by_twin_mean'])} | {fmt(r['error_rate_mean'], pct=True)} | "
                         f"{fmt(r['what_if_per_action_mean'], 2)} | {fmt(r['mean_prompt_tokens_mean'], 0)} | "
                         f"{fmt(r['input_tokens_mean'], 0)} | {fmt(r['output_tokens_mean'], 0)} | "
                         f"{fmt(r['mean_latency_s_mean'], 2)} | {fmt(r['cost_usd_mean'], 5)} |")
    else:
        lines.append("No agent runs found. Run `python agent/evaluate.py --seeds 5 --include-agent` "
                     "with DEEPINFRA_API_KEY set.")

    lines += ["", "## Metric definitions", "",
              "| Metric | Definition |", "|---|---|",
              "| Success | Crop reached 98% average progress within the season |",
              "| Days to maturity | Day the crop matured (successful runs only) |",
              "| Mean score | Mean daily growth score from the model (0 to 1) |",
              "| Stress days | Days with growth score below 0.5 (crop losing progress) |",
              "| Critical days | Days with growth score below 0.2 |",
              "| Interventions | Equipment actions taken (each irrigation, amendment, etc.) |",
              "| Irrigation / drainage | Water added or removed by soil_moisture actions, in mm (1.35 mm per percentage point) |",
              "| Score drop | Mean score in the 3 days before an event minus the lowest score in the event window |",
              "| Progress lost | Crop progress before the event minus the lowest progress during it |",
              "| Reaction | Days from event start until the first action |",
              f"| Recovery | Days from event start until score ≥ {RECOVERY_SCORE} for {RECOVERY_HOLD} straight days |",
              "| Days saved vs none | No-intervention days to maturity minus this policy's (where both matured) |",
              "| Gap vs rule | This policy's days to maturity minus the rule baseline's (negative is better) |",
              "| What-if per action | Twin next-day predictions used to check plans, per equipment action (agent) |",
              "| Rejected by twin | Decisions whose plan the twin predicted would lower tomorrow's score by more than 0.02 |",
              "| Error rate | Share of agent decisions with an LLM failure or an invalid reply |"]
    return "\n".join(lines) + "\n"


def plot(summary_rows, event_rows, out_dir):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed, skipping charts")
        return

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9,
                         "axes.edgecolor": "#c3c2b7", "axes.labelcolor": "#3d3d3a",
                         "xtick.color": "#5c5b56", "ytick.color": "#5c5b56"})

    scenarios = sorted({r["scenario"] for r in summary_rows})
    policies = [p for p in POLICY_ORDER if any(r["policy"] == p for r in summary_rows)]
    lookup = {(r["policy"], r["scenario"]): r for r in summary_rows}

    def grouped(ax, field, title, ylabel, scale=1.0, std_field=None):
        n = len(policies)
        width = 0.8 / n
        for i, p in enumerate(policies):
            xs, ys, errs = [], [], []
            for j, s in enumerate(scenarios):
                r = lookup.get((p, s))
                v = r.get(field) if r else None
                if v is None:
                    continue
                xs.append(j - 0.4 + width * (i + 0.5))
                ys.append(v * scale)
                errs.append((r.get(std_field) or 0) * scale if std_field else 0)
            ax.bar(xs, ys, width=width * 0.9, color=POLICY_COLOR[p], label=POLICY_LABEL[p],
                   yerr=errs if std_field else None, error_kw={"elinewidth": 1, "ecolor": "#5c5b56"},
                   edgecolor="white", linewidth=1)
        ax.set_title(title, loc="left", fontsize=10, color="#1a1a19")
        ax.set_ylabel(ylabel)
        ax.set_ylim(bottom=0)
        ax.set_xticks(range(len(scenarios)))
        ax.set_xticklabels([s.replace("_", "\n") for s in scenarios])
        ax.grid(axis="y", alpha=0.3)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)

    fig, axes = plt.subplots(2, 2, figsize=(11, 7))
    grouped(axes[0, 0], "success_rate", "Success rate", "% of seasons matured", scale=100)
    grouped(axes[0, 1], "days_to_maturity_mean", "Days to maturity (successful seasons)",
            "days", std_field="days_to_maturity_std")
    grouped(axes[1, 0], "stress_days_mean", "Stress days (growth score below 0.5)",
            "days", std_field="stress_days_std")
    grouped(axes[1, 1], "interventions_mean", "Equipment actions", "actions",
            std_field="interventions_std")
    axes[0, 0].set_ylim(0, 110)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=len(policies), frameon=False,
               bbox_to_anchor=(0.5, 1.0))
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(out_dir / "metrics_overview.png", dpi=160)
    plt.close(fig)

    # resilience
    events = sorted({(r["scenario"], r["event"]) for r in event_rows})
    if not events:
        return
    elookup = {(r["policy"], r["scenario"], r["event"]): r for r in event_rows}
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, field, title in [(axes[0], "progress_lost_pct", "Crop progress lost during event (%)"),
                             (axes[1], "stress_days_during_event", "Stress days during event")]:
        width = 0.8 / len(policies)
        for i, p in enumerate(policies):
            xs, ys = [], []
            for j, (s, e) in enumerate(events):
                r = elookup.get((p, s, e))
                if r and r[field] is not None:
                    xs.append(j - 0.4 + width * (i + 0.5))
                    ys.append(r[field])
            ax.bar(xs, ys, width=width * 0.9, color=POLICY_COLOR[p], label=POLICY_LABEL[p],
                   edgecolor="white", linewidth=1)
        ax.set_title(title, loc="left", fontsize=10, color="#1a1a19")
        ax.set_xticks(range(len(events)))
        ax.set_xticklabels([f"{e}\n({s})" for s, e in events], fontsize=8)
        ax.grid(axis="y", alpha=0.3)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=len(policies), frameon=False,
               bbox_to_anchor=(0.5, 1.02))
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(out_dir / "metrics_resilience.png", dpi=160)
    plt.close(fig)


def results_table(run_rows, event_rows):
    """The rows used in the paper and slides: success rate, mean health, reaction days,
    actions per season and what-if queries per action, overall and per scenario."""
    def row(scope, policy, rs, es):
        reactions = [e["reaction_days"] for e in es if e["reaction_days"] is not None]
        what_if = [r["what_if_per_action"] for r in rs if r.get("what_if_per_action") is not None]
        return {
            "scope": scope, "policy": policy, "seasons": len(rs),
            "success_rate": round(sum(r["matured"] for r in rs) / len(rs), 4),
            "mean_health": round(statistics.mean(r["mean_score"] for r in rs), 4),
            "reaction_days": round(statistics.mean(reactions), 2) if reactions else None,
            "actions_per_season": round(statistics.mean(r["interventions"] for r in rs), 2),
            "what_if_per_action": round(statistics.mean(what_if), 2) if what_if else None,
        }

    out = []
    scopes = ["all"] + sorted({r["scenario"] for r in run_rows})
    for scope in scopes:
        for policy in POLICY_ORDER:
            rs = [r for r in run_rows if r["policy"] == policy and scope in ("all", r["scenario"])]
            es = [e for e in event_rows if e["policy"] == policy and scope in ("all", e["scenario"])]
            if rs:
                out.append(row(scope, policy, rs, es))
    return out


def results_table_markdown(rows):
    lines = ["# Results table", "",
             "Rows used in the paper and slides. Mean health is the mean daily growth score; reaction is "
             "days from a weather event's start to the first equipment action (policies that never act "
             "have none); what-if per action is twin predictions per equipment action (agent only).",
             ""]
    for scope in dict.fromkeys(r["scope"] for r in rows):
        lines += [f"## {'All scenarios' if scope == 'all' else scope}", "",
                  "| Policy | Seasons | Success rate | Mean health | Reaction (days) | Actions per season | "
                  "What-if per action |", "|---|---|---|---|---|---|---|"]
        for r in rows:
            if r["scope"] != scope:
                continue
            lines.append(f"| {POLICY_LABEL.get(r['policy'], r['policy'])} | {r['seasons']} | "
                         f"{fmt(r['success_rate'], pct=True)} | {fmt(r['mean_health'], 3)} | "
                         f"{fmt(r['reaction_days'])} | {fmt(r['actions_per_season'])} | "
                         f"{fmt(r['what_if_per_action'], 2)} |")
        lines.append("")
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--runs-dir", default=str(HERE / "results" / "runs"))
    p.add_argument("--out-dir", default=str(HERE / "results"))
    args = p.parse_args()
    runs_dir, out_dir = Path(args.runs_dir), Path(args.out_dir)

    runs = load_runs(runs_dir)
    if not runs:
        raise SystemExit(f"No *_summary.json files in {runs_dir}. Run evaluate.py first.")

    run_rows, event_rows = [], []
    for summary, records in runs:
        m, ev = run_metrics(summary, records)
        run_rows.append(m)
        event_rows += ev

    summary_rows = aggregate(run_rows)
    event_summary = aggregate_events(event_rows)
    overall_rows = overall(run_rows)
    table = results_table(run_rows, event_rows)

    write_csv(out_dir / "metrics_runs.csv", run_rows)
    write_csv(out_dir / "metrics_summary.csv", summary_rows)
    write_csv(out_dir / "metrics_events.csv", event_rows)
    write_csv(out_dir / "results_table.csv", table)
    (out_dir / "METRICS.md").write_text(markdown_report(overall_rows, summary_rows, event_summary, run_rows))
    (out_dir / "RESULTS_TABLE.md").write_text(results_table_markdown(table))
    plot(summary_rows, event_summary, out_dir)

    print((out_dir / "RESULTS_TABLE.md").read_text())
    print(f"Written to {out_dir}/")


if __name__ == "__main__":
    main()
