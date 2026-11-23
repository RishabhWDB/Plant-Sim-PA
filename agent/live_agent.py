"""
Periodic LLM farm manager: one LLM call per tick, no tool loop, no conversation history.

Each tick the agent reads the twin's state, probes the twin with what-if predictions for every
control (each moved to either end of its reach), asks the model for at most two control changes,
clips them to the actuator limits, checks each one and then the plan with the twin's next-day
prediction (no extra LLM call), and applies what passes. The model is NOT told the crop's optimal
ranges.

The probes stand in for the simulate_change tool of the earlier tool-use agent: the model sees
which direction helps each control without a second round trip. VARIANTS switches the probes and
the twin check off one at a time for the ablation in evaluate.py.

  python agent/live_agent.py --backend unity --scenario drought            # live, real time
  python agent/live_agent.py --backend local --scenario drought --dry-run  # instant, no API calls

Modes
  unity   Unity's clock runs normally; the loop applies the scenario's weather as days pass and
          the agent decides every --tick seconds of wall time (default 12).
  local   no sleeping; the agent decides every --days-per-tick simulated days (default 3).
"""

import json
import math
import time

from farm_env import CONTROLLABLE, WEATHER_ONLY
from llm_client import FakeLLM, estimate_tokens
from sim_backends import clamp_param, tc

REJECT_MARGIN = 0.02     # reject a plan whose next-day score is this much below doing nothing
MAX_ACTIONS = 2
HISTORY = 3
PROMPT_BUDGET = 1200     # tokens, system plus user

# Policy names accepted by run.py and evaluate.py, with their LiveAgent options
VARIANTS = {
    "agent":         {},                                  # probes and twin check
    "agent_noprobe": {"probes": False},                   # the design without probes
    "agent_nocheck": {"twin_check": False},               # plans applied without the twin check
    "agent_mistral": {"model": "mistralai/Mistral-Small-24B-Instruct-2501"},
}

API_NAMES = {"pH": "ph", "soil_moisture": "soil_moisture", "sunlight_hours": "sunlight_hours",
             "temperature": "temperature", "humidity": "humidity"}

SYSTEM_PROMPT = """You manage a field of 144 tomato-like plants in a digital twin. Every few days you \
see the farm state and decide whether to change the controls. Goals, in order: keep the crop alive, \
bring it to maturity quickly, use few equipment actions.

Controls, with the most each action can move them:
- soil_moisture (%): irrigate or drain to the value today, at most 20 per action. Rain adds water \
and the crop uses it, so it keeps changing every day.
- ph: lime or sulfur, at most 0.5 per action.
- sunlight_hours (h/day): grow lights or shade netting, at most 3 per action.
- humidity (%): misting or ventilation, at most 15 per action.
temperature and rainfall (mm/day) are weather: you cannot change them, only compensate.
You are NOT told the crop's ideal ranges; use your agronomy knowledge and the twin's feedback.

growth_score is yesterday's score from 0 to 1: above 0.5 the crop grows, below 0.5 it loses \
progress. forecast gives days to maturity or to crop death if conditions persist, with a 90% range \
(-1 means unbounded). limiting_factor is the variable currently holding growth back, if any.

The state lists each control's current value ("now") and the range you can set it to this time ("can_set_to", the current value plus or minus the per-action limit). When present, "twin_tomorrow" maps levels you could set that control to (lowest reachable, current, highest reachable) to the growth_score the twin predicts for tomorrow if only that control changes: pick the level with the highest score. "value" in an action is the NEW LEVEL you want, not a change: to raise humidity from 30 to 45, send {"parameter": "humidity", "value": 45}. Every action is checked with the twin first, and an action the twin predicts would lower tomorrow's score is not applied (rejected_by_twin in recent_decisions lists them).

Reply with JSON only:
{"reasoning": "at most 2 sentences", "advice": "1 or 2 short remedies or precautions a real farmer should take now (e.g. mulch, check drainage, scout for pests, protect from heat)", "actions": [{"parameter": "<control>", "value": <new level>}]}
Use at most 2 actions. An empty actions list means wait."""


def limiting_factor(environment, stage):
    """The variable with the lowest factor score in the process model, if it is outside its
    optimal band (factor score below 0.85). Names only; the ranges stay hidden."""
    env = {"pH": environment["ph"], "soil_moisture": environment["soil_moisture"],
           "sunlight_hours": environment["sunlight_hours"],
           "temperature": environment["temperature"], "humidity": environment["humidity"]}
    _, detail = tc.growth_score(env, max(0, stage - 1), detail=True)
    phi = {k: float(v) for k, v in detail["phi"].items()}
    name = min(phi, key=phi.get)
    return API_NAMES[name] if phi[name] < 0.85 else "none"


class LiveAgent:
    name = "agent"

    def __init__(self, llm, days_per_tick=3, tick_seconds=12.0, verbose=True, probes=True, twin_check=True):
        self.llm = llm
        self.probes = probes
        self.twin_check = twin_check
        self.days_per_tick = days_per_tick
        self.tick_seconds = tick_seconds
        self.verbose = verbose
        self.history = []          # every decision, for the prompt and the season report
        self.llm_calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.llm_errors = 0
        self.rejected = 0
        self.latencies = []
        self.season_report = ""

    # Prompt

    def probe(self, env, status):
        """The twin's next-day score with no change, and with each control alone moved to either
        end of its reach this tick (as listed in can_set_to). Each control's table is keyed by the
        level, so a small model does not have to know which position means lower or higher."""
        live = status["environment"]
        keep = env.predict({})["growth_score"]
        table = {}
        for p, c in CONTROLLABLE.items():
            low = clamp_param(p, live[p] - c["max_step"])
            high = clamp_param(p, live[p] + c["max_step"])
            table[p] = {f"{round(low, 2):g}": round(env.predict({p: low})["growth_score"], 3),
                        f"{round(live[p], 2):g}": round(keep, 3),
                        f"{round(high, 2):g}": round(env.predict({p: high})["growth_score"], 3)}
        return keep, table

    def user_message(self, status, news, probes=None):
        f = status["forecast"]
        recent = []
        for h in self.history[-HISTORY:]:
            effect = None if h.get("score_after") is None else round(h["score_after"] - h["score_before"], 3)
            recent.append({"day": h["day"], "proposed": h["planned"] or "wait",
                           "rejected_by_twin": h["rejected"], "score_change": effect})
        env = status["environment"]
        controls = {}
        for p, c in CONTROLLABLE.items():
            now, step = env[p], c["max_step"]
            controls[p] = {"now": now, "can_set_to": [round(clamp_param(p, now - step), 2),
                                                      round(clamp_param(p, now + step), 2)]}
            if probes:
                controls[p]["twin_tomorrow"] = probes[1][p]
        msg = {
            "day": status["day"],
            "days_left": status.get("days_remaining_in_season"),
            "growth_score": status["growth_score"],
            "progress_percent": status["average_progress_percent"],
            "stage": status["stage_name"],
            "soil_moisture": status["soil_moisture_percent"],
            "crop_water_use_mm_per_day": status["evapotranspiration_mm_per_day"],
            "forecast": {"kind": f["kind"], "days": f["days"], "range_90": [f["low_days"], f["high_days"]]},
            "limiting_factor": limiting_factor(status["environment"], status["stage"]),
            "controls": controls,
            "weather": {"temperature": env["temperature"], "rainfall_mm_per_day": env["rainfall"]},
            "active_weather": status.get("active_weather", []),
            "weather_news": news[-3:],
            "recent_decisions": recent,
        }
        return json.dumps(msg, separators=(",", ":"))

    # One decision

    def decide(self, env, status, news=()):
        if self.history and self.history[-1].get("score_after") is None:
            self.history[-1]["score_after"] = status["growth_score"]

        probes = self.probe(env, status) if self.probes else None
        user = self.user_message(status, list(news), probes)
        prompt_tokens = estimate_tokens(SYSTEM_PROMPT + user)
        reply, info = self.llm.complete(SYSTEM_PROMPT, user)
        self.llm_calls += 1
        self.input_tokens += info["prompt_tokens"]
        self.output_tokens += info["completion_tokens"]
        self.latencies.append(info["latency_s"])

        error = info["error"]
        reasoning, advice, proposed = "", "", []
        if reply is None:
            self.llm_errors += 1
            self._say(f"Day {status['day']}: LLM call failed, no action ({error})")
        else:
            reasoning = str(reply.get("reasoning", ""))[:300]
            advice = str(reply.get("advice", ""))[:200]
            proposed, problems = self._validate(reply.get("actions", []))
            if problems:
                error = "; ".join(problems)

        # Clip to the actuator limits from today's live values; drop changes that do nothing
        live = status["environment"]
        planned = {}
        for p, v in proposed:
            step = CONTROLLABLE[p]["max_step"]
            target = clamp_param(p, v)
            value = max(live[p] - step, min(live[p] + step, target))
            if abs(value - live[p]) >= 0.05 * step:
                planned[p] = round(value, 3)

        # What-if with the twin: tomorrow's score with each action alone, then with what is left of
        # the plan, versus doing nothing. Checking actions one by one keeps a harmful action from
        # riding along with a helpful one.
        applied, rejected, score_nothing, score_plan = dict(planned), [], None, None
        if planned and self.twin_check:
            score_nothing = probes[0] if probes else env.predict({})["growth_score"]
            if len(planned) > 1:
                for p, v in planned.items():
                    if env.predict({p: v})["growth_score"] < score_nothing - REJECT_MARGIN:
                        rejected.append(p)
                        del applied[p]
            if applied:
                score_plan = env.predict(applied)["growth_score"]
                if score_plan < score_nothing - REJECT_MARGIN:
                    rejected += list(applied)
                    applied = {}

        if reasoning:
            env.sim.log(reasoning)
        if advice:
            env.sim.log(f"Remedy: {advice}")
        if rejected:
            self.rejected += 1
            blocked = {p: planned[p] for p in rejected}
            env.sim.log(f"Rejected by twin: {blocked} (tomorrow below {score_nothing:.2f})")
            self._say(f"Day {status['day']}: rejected by twin {blocked}")
        for p, v in applied.items():
            env.adjust(p, v, reason=reasoning, source="agent")

        if self.verbose and reasoning:
            print(f"[agent day {status['day']}] {reasoning}")
        if self.verbose and advice:
            print(f"[agent day {status['day']}] Remedy: {advice}")
        self.history.append({"day": status["day"], "planned": planned, "applied": applied, "rejected": rejected,
                             "score_before": status["growth_score"], "score_after": None})
        env.record({
            "type": "tick", "day": status["day"],
            "state": {"growth_score": status["growth_score"],
                      "progress_percent": status["average_progress_percent"],
                      "soil_moisture": status["soil_moisture_percent"],
                      "forecast": status["forecast"], "environment": status["environment"]},
            "prompt_tokens": info["prompt_tokens"] or prompt_tokens,
            "completion_tokens": info["completion_tokens"],
            "reasoning": reasoning, "advice": advice, "actions_proposed": [{"parameter": p, "value": v} for p, v in proposed],
            "actions_applied": applied, "rejected_by_twin": bool(rejected), "rejected_actions": rejected,
            "predicted_score_nothing": score_nothing, "predicted_score_plan": score_plan,
            "latency_s": info["latency_s"], "error": error,
        })

    def _validate(self, actions):
        if not isinstance(actions, list):
            return [], ["actions is not a list"]
        out, problems = [], []
        for a in actions[:MAX_ACTIONS]:
            if not isinstance(a, dict):
                problems.append(f"bad action {a!r}")
                continue
            p, v = a.get("parameter"), a.get("value")
            if p in WEATHER_ONLY:
                problems.append(f"{p} is weather")
            elif p not in CONTROLLABLE:
                problems.append(f"unknown parameter {p!r}")
            elif not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v):
                problems.append(f"bad value for {p}: {v!r}")
            elif p not in [q for q, _ in out]:
                out.append((p, float(v)))
        if len(actions) > MAX_ACTIONS:
            problems.append(f"{len(actions)} actions, only the first {MAX_ACTIONS} considered")
        return out, problems

    # Seasons

    def run(self, env):
        """Local mode: decide every days_per_tick simulated days, no sleeping."""
        news = []
        while not env.done:
            self.decide(env, env.status(), news)
            news = env.advance(self.days_per_tick)["weather_news"]
        return self._finish(env)

    def run_realtime(self, env, poll_seconds=0.5):
        """Unity mode: the clock runs in real time, weather is applied as days pass, and the
        agent decides every tick_seconds of wall time."""
        env.sim.resume()
        next_tick = time.monotonic()
        news = []
        try:
            while True:
                status, new = env.sync()
                news += new
                if env.done:
                    break
                if time.monotonic() >= next_tick:
                    self.decide(env, env.status(), news)
                    news = []
                    next_tick += self.tick_seconds
                time.sleep(poll_seconds)
        finally:
            env.sim.pause()
        return self._finish(env)

    def _finish(self, env):
        if self.history and self.history[-1].get("score_after") is None:
            self.history[-1]["score_after"] = env.last_status["growth_score"]
        summary = env.summary()
        self.season_report = self._report(summary)   # first, so its tokens are counted below
        summary.update({
            "llm_calls": self.llm_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "llm_errors": self.llm_errors,
            "rejected_by_twin": self.rejected,
            "mean_latency_s": round(sum(self.latencies) / max(1, len(self.latencies)), 3),
            "model": self.llm.model,
        })
        return summary

    def _report(self, summary):
        decisions = [f"day {h['day']}: score {h['score_before']:.2f}, "
                     + (", ".join(f"{p}->{v}" for p, v in h["applied"].items()) or "wait")
                     + (f" ({', '.join(h['rejected'])} blocked by the twin check)" if h["rejected"] else "")
                     for h in self.history]
        user = json.dumps({"result": {k: summary[k] for k in (
            "scenario", "outcome", "final_day", "final_progress_percent", "days_with_score_below_0_5",
            "mean_growth_score", "interventions", "irrigation_mm")}, "plans_blocked_by_twin": self.rejected,
            "decisions": decisions}, separators=(",", ":"))
        system = ("You managed a farm for one season in a digital twin. Write a short season report "
                  "(at most 150 words): what happened, your key decisions, and what you would do "
                  "differently next season. Plain text.")
        report, info = self.llm.complete(system, user, json_reply=False)
        self.llm_calls += 1
        self.input_tokens += info["prompt_tokens"]
        self.output_tokens += info["completion_tokens"]
        if report is None:
            self.llm_errors += 1
            report = f"(Could not generate report: {info['error']})"
        if self.verbose:
            print("\nAgent season report\n" + report)
        return report

    def _say(self, msg):
        if self.verbose:
            print(msg)


def main():
    import argparse
    from run import run_season
    from scenarios import SCENARIOS

    p = argparse.ArgumentParser()
    p.add_argument("--backend", choices=["unity", "local"], default="unity")
    p.add_argument("--scenario", choices=list(SCENARIOS), default="drought")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--tick", type=float, default=12.0, help="seconds between decisions (unity)")
    p.add_argument("--days-per-tick", type=int, default=3, help="simulated days between decisions (local)")
    p.add_argument("--max-days", type=int, default=120)
    p.add_argument("--model", default=None)
    p.add_argument("--url", default="http://localhost:8765")
    p.add_argument("--dry-run", action="store_true", help="fake LLM, no API calls")
    args = p.parse_args()

    summary = run_season("agent", args.scenario, args.backend, args.url, args.max_days, args.seed,
                         agent_options={"model": args.model, "dry_run": args.dry_run,
                                        "tick_seconds": args.tick, "days_per_tick": args.days_per_tick})
    print("\nSummary")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
