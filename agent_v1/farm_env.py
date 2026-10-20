"""
FarmEnvironment wraps a simulation backend with the rules of the game:
  - which parameters the farmer can control, and how far per action (actuator limits)
  - weather events that change the environment on their own
  - logging of the full trajectory for evaluation
"""

import json
import time
from pathlib import Path

from sim_backends import clamp_param

CONTROLLABLE = {
    "soil_moisture":  {"max_step": 20.0, "actuator": "irrigation (raise) or field drainage (lower)", "unit": "%"},
    "ph":             {"max_step": 0.5,  "actuator": "lime (raise) or sulfur (lower) soil amendment", "unit": "pH"},
    "sunlight_hours": {"max_step": 3.0,  "actuator": "grow lights (raise) or shade netting (lower)", "unit": "hrs/day"},
    "humidity":       {"max_step": 15.0, "actuator": "misting (raise) or ventilation (lower)", "unit": "%"},
}
WEATHER_ONLY = ["temperature", "rainfall"]

TERMINAL = ("matured", "dead")


class FarmEnvironment:
    def __init__(self, sim, scenario, max_days=120, log_dir="runs", run_name=None, verbose=True):
        self.sim = sim
        self.scenario = scenario
        self.max_days = max_days
        self.verbose = verbose
        self.run_name = run_name or f"{int(time.time())}_{scenario.name}"
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        self.log_path = Path(log_dir) / f"{self.run_name}.jsonl"

    # ------------------------------------------------------------------ setup

    def reset(self):
        self.sim.reset()
        self.sim.pause()
        self.env = {}
        for k, v in self.scenario.initial_env.items():
            self.env = self._set(k, v)
        self.trajectory = []
        self.interventions = []
        self.events_seen = []
        self.predict_calls = 0
        self._log_file = open(self.log_path, "w")
        self.last_status = self.sim.state()
        self._record_day(self.last_status, [])
        self._say(f"Scenario '{self.scenario.name}': {self.scenario.description}")
        return self.last_status

    def close(self):
        if getattr(self, "_log_file", None):
            self._log_file.close()
            self._log_file = None

    # ------------------------------------------------------------------ observe

    @property
    def day(self):
        return self.last_status["day"]

    @property
    def done(self):
        return self.last_status["outcome"] in TERMINAL or self.day >= self.max_days

    def status(self):
        self.last_status = self.sim.state()
        s = dict(self.last_status)
        s["days_remaining_in_season"] = self.max_days - s["day"]
        s["active_weather"] = [e.name for e in self.scenario.events
                               if e.start_day <= s["day"] <= e.end_day]
        return s

    def predict(self, changes):
        self.predict_calls += 1
        bad = [k for k in changes if k not in CONTROLLABLE and k not in WEATHER_ONLY]
        if bad:
            raise ValueError(f"Unknown parameters: {bad}")
        return self.sim.predict(changes)

    # ------------------------------------------------------------------ act

    def adjust(self, parameter, value, reason="", source="policy"):
        if parameter in WEATHER_ONLY:
            raise ValueError(f"'{parameter}' is weather and cannot be controlled.")
        if parameter not in CONTROLLABLE:
            raise ValueError(f"Unknown parameter '{parameter}'. Controllable: {list(CONTROLLABLE)}")

        current = float(self.env[parameter])
        requested = clamp_param(parameter, value)
        step = CONTROLLABLE[parameter]["max_step"]
        applied = max(current - step, min(current + step, requested))
        limited = abs(applied - requested) > 1e-6

        self.env = self._set(parameter, applied)
        record = {
            "type": "intervention", "day": self.day, "source": source,
            "parameter": parameter, "from": round(current, 3), "to": round(applied, 3),
            "requested": round(requested, 3), "limited_by_actuator": limited, "reason": reason,
        }
        self.interventions.append(record)
        self._write(record)
        self._say(f"Day {self.day}: {parameter} {current:.1f} -> {applied:.1f}"
                  + (" (actuator limit)" if limited else "") + (f" | {reason}" if reason else ""))
        self.sim.log(f"{parameter} {current:.1f} -> {applied:.1f}. {reason}")
        return {"parameter": parameter, "previous": round(current, 3), "now": round(applied, 3),
                "requested": round(requested, 3), "limited_by_actuator": limited,
                "max_change_per_action": step}

    def advance(self, days):
        days = max(1, min(int(days), 10, self.max_days - self.day))
        news, scores = [], []
        for _ in range(days):
            target_day = self.day + 1
            news += self._apply_weather(target_day)
            self.last_status = self.sim.advance(1)
            scores.append(self.last_status["growth_score"])
            self._record_day(self.last_status, news)
            if self.done:
                break
        return {
            "days_advanced": len(scores),
            "weather_news": news,
            "growth_score_min": round(min(scores), 4),
            "growth_score_max": round(max(scores), 4),
            "status": self.status(),
        }

    # ------------------------------------------------------------------ results

    def summary(self):
        s = self.last_status
        by_param = {}
        for r in self.interventions:
            by_param[r["parameter"]] = by_param.get(r["parameter"], 0) + 1
        irrigation = sum(max(0.0, r["to"] - r["from"]) for r in self.interventions
                         if r["parameter"] == "soil_moisture")
        days_bad = sum(1 for t in self.trajectory if t["growth_score"] < 0.5)
        return {
            "scenario": self.scenario.name,
            "outcome": s["outcome"] if s["outcome"] in TERMINAL else "season_ended",
            "final_day": s["day"],
            "final_progress_percent": s["average_progress_percent"],
            "matured": s["outcome"] == "matured",
            "days_to_maturity": s["day"] if s["outcome"] == "matured" else None,
            "days_with_score_below_0_5": days_bad,
            "mean_growth_score": round(sum(t["growth_score"] for t in self.trajectory[1:])
                                       / max(1, len(self.trajectory) - 1), 4),
            "interventions": len(self.interventions),
            "interventions_by_parameter": by_param,
            "irrigation_units": round(irrigation, 1),
            "what_if_queries": self.predict_calls,
        }

    # ------------------------------------------------------------------ internals

    def _set(self, name, value):
        return dict(self.sim.set_parameter(name, value))

    def _apply_weather(self, day):
        news = []
        for e in self.scenario.events:
            if day == e.start_day:
                news.append(f"Day {day}: {e.message}")
                self.events_seen.append(e.name)
                self._write({"type": "event", "day": day, "event": e.name, "phase": "start"})
                for k, v in e.set.items():
                    self.env = self._set(k, v)
            if e.start_day <= day <= e.end_day:
                for k, dv in e.drift.items():
                    self.env = self._set(k, float(self.env[k]) + dv)
            if day == e.end_day + 1 and e.after:
                news.append(f"Day {day}: the {e.name} has passed.")
                self._write({"type": "event", "day": day, "event": e.name, "phase": "end"})
                for k, v in e.after.items():
                    self.env = self._set(k, v)
        for n in news:
            self._say(n)
            self.sim.log(n)
        return news

    def _record_day(self, status, news):
        row = {
            "type": "day", "day": status["day"],
            "growth_score": status["growth_score"],
            "average_progress_percent": status["average_progress_percent"],
            "stage": status["stage"], "outcome": status["outcome"],
            "environment": status["environment"],
        }
        self.trajectory.append(row)
        self._write(row)

    def record(self, record):
        """Public hook so policies can add their own records (e.g. tool calls) to the run log."""
        self._write(record)

    def _write(self, record):
        if getattr(self, "_log_file", None):
            self._log_file.write(json.dumps(record) + "\n")
            self._log_file.flush()

    def _say(self, msg):
        if self.verbose:
            print(msg)
