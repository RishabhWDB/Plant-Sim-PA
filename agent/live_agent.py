"""
Periodic LLM farm manager: one LLM call per tick, no tool loop, no conversation history.

Each tick the agent reads the twin's state, asks the model for at most two control changes,
checks them with the twin's next-day prediction (the what-if step, no extra LLM call), clips
them to the actuator limits and applies them. The model is NOT told the crop's optimal ranges.

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

Reply with JSON only:
{"reasoning": "at most 2 sentences", "actions": [{"parameter": "<control>", "value": <number>}]}
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

    def __init__(self, llm, days_per_tick=3, tick_seconds=12.0, verbose=True):
        self.llm = llm
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

    def user_message(self, status, news):
        f = status["forecast"]
        recent = []
        for h in self.history[-HISTORY:]:
            effect = None if h.get("score_after") is None else round(h["score_after"] - h["score_before"], 3)
            recent.append({"day": h["day"], "actions": h["applied"] or "wait",
                           "rejected_by_twin": h["rejected"], "score_change": effect})
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
            "environment": status["environment"],
            "active_weather": status.get("active_weather", []),
            "weather_news": news[-3:],
            "recent_decisions": recent,
        }
        return json.dumps(msg, separators=(",", ":"))

    # One decision

    def decide(self, env, status, news=()):
        if self.history and self.history[-1].get("score_after") is None:
            self.history[-1]["score_after"] = status["growth_score"]

        user = self.user_message(status, list(news))
        prompt_tokens = estimate_tokens(SYSTEM_PROMPT + user)
        reply, info = self.llm.complete(SYSTEM_PROMPT, user)
        self.llm_calls += 1
        self.input_tokens += info["prompt_tokens"]
        self.output_tokens += info["completion_tokens"]
        self.latencies.append(info["latency_s"])

        error = info["error"]
        reasoning, proposed = "", []
        if reply is None:
            self.llm_errors += 1
            self._say(f"Day {status['day']}: LLM call failed, no action ({error})")
        else:
            reasoning = str(reply.get("reasoning", ""))[:300]
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

        # What-if with the twin: tomorrow's score with the plan versus doing nothing
        rejected, score_nothing, score_plan = False, None, None
        if planned:
            score_nothing = env.predict({})["growth_score"]
            score_plan = env.predict(planned)["growth_score"]
            rejected = score_plan < score_nothing - REJECT_MARGIN

        if reasoning:
            env.sim.log(reasoning)
        if rejected:
            self.rejected += 1
            env.sim.log(f"Rejected by twin: {planned} (tomorrow {score_plan:.2f} vs {score_nothing:.2f})")
            self._say(f"Day {status['day']}: rejected by twin {planned}")
            applied = {}
        else:
            applied = planned
            for p, v in applied.items():
                env.adjust(p, v, reason=reasoning, source="agent")

        if self.verbose and reasoning:
            print(f"[agent day {status['day']}] {reasoning}")
        self.history.append({"day": status["day"], "applied": applied, "rejected": rejected,
                             "score_before": status["growth_score"], "score_after": None})
        env.record({
            "type": "tick", "day": status["day"],
            "state": {"growth_score": status["growth_score"],
                      "progress_percent": status["average_progress_percent"],
                      "soil_moisture": status["soil_moisture_percent"],
                      "forecast": status["forecast"], "environment": status["environment"]},
            "prompt_tokens": info["prompt_tokens"] or prompt_tokens,
            "completion_tokens": info["completion_tokens"],
            "reasoning": reasoning, "actions_proposed": [{"parameter": p, "value": v} for p, v in proposed],
            "actions_applied": applied, "rejected_by_twin": rejected,
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
        summary.update({
            "llm_calls": self.llm_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "llm_errors": self.llm_errors,
            "rejected_by_twin": self.rejected,
            "mean_latency_s": round(sum(self.latencies) / max(1, len(self.latencies)), 3),
            "model": self.llm.model,
        })
        self.season_report = self._report(summary)
        return summary

    def _report(self, summary):
        decisions = [f"day {h['day']}: score {h['score_before']:.2f}, "
                     + ("rejected by twin" if h["rejected"] else
                        (", ".join(f"{p}->{v}" for p, v in h["applied"].items()) or "wait"))
                     for h in self.history]
        user = json.dumps({"result": {k: summary[k] for k in (
            "scenario", "outcome", "final_day", "final_progress_percent", "days_with_score_below_0_5",
            "mean_growth_score", "interventions", "irrigation_mm", "rejected_by_twin")},
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
