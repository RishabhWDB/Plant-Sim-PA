"""
Simulation backends the agent can drive.

UnitySim  talks to SimulationServer.cs over HTTP (the live 3D simulation).
LocalSim  is a Python replica of the v4 twin: the same FAO-56 water balance, growth surrogate
          and crop dynamics as GrowthEngine.cs, built on ml/twin_core.py. It runs instantly,
          so it is used for development and batch evaluation.

Both return the same status and prediction dictionaries, so policies never know which one
they are using.

v4 semantics
  - soil_moisture is a state. The water balance moves it every day (rain in, crop
    evapotranspiration out, drainage above field capacity). Setting it means irrigating or
    draining the field to that level today; the water balance continues from there.
  - rainfall is weather in mm/day and acts only through soil moisture.
  - The growth score of a day is computed after that day's water balance, with the field
    stage at the start of the day.
"""

import json
import math
import pickle
import random
import sys
from pathlib import Path

import numpy as np

ML_DIR = Path(__file__).resolve().parents[1] / "ml"
sys.path.insert(0, str(ML_DIR))
import twin_core as tc  # noqa: E402

PARAM_RANGES = {
    "ph":             (3.5, 9.5),
    "soil_moisture":  (5.0, 100.0),
    "sunlight_hours": (0.0, 16.0),
    "temperature":    (0.0, 45.0),
    "humidity":       (10.0, 100.0),
    "rainfall":       (0.0, 120.0),     # mm/day
}

DEFAULT_ENV = {
    "ph": 6.5, "soil_moisture": 55.0, "sunlight_hours": 8.0,
    "temperature": 25.0, "humidity": 62.0, "rainfall": 3.0,
}

STAGE_NAMES = tc.STAGE_NAMES
MATURE_AT = tc.MATURE_AT


def clamp_param(name, value):
    lo, hi = PARAM_RANGES[name]
    return max(lo, min(hi, float(value)))


def health_zone(score):
    if score < 0.2:
        return "critical"
    if score < 0.5:
        return "deteriorating"
    if score < 0.75:
        return "growing"
    return "thriving"


def delta(score):
    return float(tc.delta(score))


def forecast(progress, score, q90):
    """Days to maturity or death if the score persists, with the conformal band.
    Mirrors GrowthEngine.ComputeForecast: a higher score means earlier maturity or later death,
    and a band end that crosses to the other outcome is unbounded (-1 in the output)."""
    def one(s):
        d = delta(s)
        if d > 0:
            return (MATURE_AT - progress) / d, False
        if d < 0:
            return progress / -d, True
        return math.inf, False

    days, death = one(score)
    optimistic, optimistic_death = one(min(1.0, score + q90))
    pessimistic, pessimistic_death = one(max(0.0, score - q90))
    if death:
        low, high = pessimistic, (optimistic if optimistic_death else math.inf)
    else:
        low, high = optimistic, (math.inf if pessimistic_death else pessimistic)

    def out(v):
        return -1.0 if math.isinf(v) else round(v, 1)

    kind = "death" if death else ("maturity" if not math.isinf(days) else "none")
    return {"kind": kind, "days": out(days), "low_days": out(low), "high_days": out(high)}


def outcome_of(avg, peak, fc):
    if avg >= MATURE_AT:
        return "matured"
    if peak > 0.05 and avg <= 0.001:
        return "dead"
    if fc["kind"] == "death":
        return "declining_toward_death" if peak > 0.05 else "failing_to_establish"
    if fc["kind"] == "maturity":
        return "growing_toward_maturity"
    return "stalled"


# Unity backend

class UnitySim:
    def __init__(self, url="http://localhost:8765", timeout=120):
        import requests
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def _req(self, method, path, payload=None):
        r = self.session.request(method, self.url + path, json=payload, timeout=self.timeout)
        try:
            data = r.json()
        except ValueError:
            raise RuntimeError(f"Bad response from Unity ({r.status_code}): {r.text[:200]}")
        if r.status_code >= 400:
            raise RuntimeError(data.get("error", r.text))
        return data

    def health(self):
        return self._req("GET", "/health")

    def state(self):
        return self._req("GET", "/state")

    def set_parameter(self, name, value):
        return self._req("POST", "/environment", {"parameter": name, "value": float(value)})

    def advance(self, days=1):
        return self._req("POST", "/advance", {"days": int(days)})

    def reset(self):
        return self._req("POST", "/reset")

    def pause(self):
        return self._req("POST", "/pause")

    def resume(self):
        return self._req("POST", "/resume")

    def predict(self, overrides):
        return self._req("POST", "/predict", {k: float(v) for k, v in overrides.items()})

    def log(self, message):
        try:
            self._req("POST", "/log", {"message": str(message)[:300]})
        except Exception:
            pass  # on-screen log is cosmetic


# Growth score: the trained surrogate, as in GrowthEngine.PredictScore

class GrowthScorer:
    """Loads ml/outputs/surrogate_v4.pkl (scikit-learn). If it is missing or cannot be loaded,
    evaluates ml/outputs/growth_model.json with the same traversal as GrowthModel.cs. If that
    is missing too, falls back to the analytic response function, like GrowthEngine does."""

    def __init__(self, ml_dir=ML_DIR, use_pickle=True):
        outputs = Path(ml_dir) / "outputs"
        self.kind, self.q90 = "analytic", 0.0
        if use_pickle:
            try:
                with open(outputs / "surrogate_v4.pkl", "rb") as fh:
                    s = pickle.load(fh)
                self.model, self.iso, self.q90 = s["model"], s["iso"], float(s["q90"])
                self.kind = "pickle"
                return
            except (OSError, ImportError, AttributeError, KeyError, pickle.UnpicklingError):
                pass
        try:
            self.data = json.loads((outputs / "growth_model.json").read_text())
            self.q90 = float(self.data["conformal_q90"])
            self.kind = "json"
        except (OSError, KeyError, ValueError):
            pass

    @property
    def learned(self):
        return self.kind != "analytic"

    def __call__(self, ph, soil_moisture, sunlight, temperature, humidity, stage):
        x = [float(ph), float(soil_moisture), float(sunlight), float(temperature), float(humidity),
             float(stage)]
        if self.kind == "pickle":
            raw = np.clip(self.model.predict(np.array([x])), 0, 1)
            return float(np.clip(self.iso.predict(raw), 0, 1)[0])
        if self.kind == "json":
            return self._reference_eval(x)
        env = {"pH": x[0], "soil_moisture": x[1], "sunlight_hours": x[2],
               "temperature": x[3], "humidity": x[4]}
        return float(tc.growth_score(env, int(stage)))

    def _reference_eval(self, x):
        # Same as reference_eval() in ml/train_model.py and GrowthModel.Predict in C#
        d = self.data
        total = d["baseline"]
        for t in d["trees"]:
            n = 0
            while not t["leaf"][n]:
                n = t["left"][n] if x[t["feature"][n]] <= t["threshold"][n] else t["right"][n]
            total += t["value"][n]
        raw = min(1.0, max(0.0, total))
        xs, ys = d["isotonic_x"], d["isotonic_y"]
        if raw <= xs[0]:
            out = ys[0]
        elif raw >= xs[-1]:
            out = ys[-1]
        else:
            lo, hi = 0, len(xs) - 1
            while hi - lo > 1:
                mid = (lo + hi) // 2
                if xs[mid] <= raw:
                    lo = mid
                else:
                    hi = mid
            out = ys[lo] + (ys[hi] - ys[lo]) * (raw - xs[lo]) / (xs[hi] - xs[lo])
        return min(1.0, max(0.0, out))


# Local Python replica of GrowthEngine.OnDayPassed

class LocalSim:
    def __init__(self, rows=12, cols=12, seed=0, offset_range=0.05, scorer=None, offsets=None):
        if offsets is None:
            rng = random.Random(seed)
            offsets = [rng.uniform(-offset_range, offset_range) for _ in range(rows * cols)]
        self.offsets = np.asarray(offsets, dtype=float)
        self.scorer = scorer or GrowthScorer()
        self.env = dict(DEFAULT_ENV)
        self.reset()

    def health(self):
        return {"ok": True, "message": f"Local simulation ({self.scorer.kind} growth model)"}

    def reset(self):
        self.day = 0
        self.progress = np.zeros(len(self.offsets))
        self.peak = 0.0
        self.stage = 0
        self.score = None          # no simulated day yet
        self.etc = 0.0
        self.env["soil_moisture"] = DEFAULT_ENV["soil_moisture"]
        return self.state()

    def pause(self):
        return {"ok": True}

    def resume(self):
        return {"ok": True}

    def set_parameter(self, name, value):
        if name not in PARAM_RANGES:
            raise RuntimeError(f"Unknown parameter '{name}'")
        self.env[name] = clamp_param(name, value)
        return dict(self.env)

    def _water_and_score(self, env, stage):
        sm, flux = tc.water_step(env["soil_moisture"], env["rainfall"], 0.0, env["temperature"],
                                 env["humidity"], env["sunlight_hours"], stage)
        sm = float(sm)
        s = self.scorer(env["ph"], sm, env["sunlight_hours"], env["temperature"], env["humidity"], stage)
        return sm, float(flux["etc"]), s

    def step(self):
        """One simulated day, in the same order as GrowthEngine.OnDayPassed."""
        self.day += 1
        sm, self.etc, self.score = self._water_and_score(self.env, self.stage)
        self.env["soil_moisture"] = sm
        adjusted = np.clip(self.score + self.offsets, 0.0, 1.0)
        self.progress = np.clip(self.progress + tc.delta(adjusted), 0.0, 1.0)
        avg = float(self.progress.mean())
        self.stage = min(6, int(math.floor(avg * 7)))
        self.peak = max(self.peak, avg)

    def advance(self, days=1):
        for _ in range(max(1, min(30, int(days)))):
            self.step()
            if self.state()["outcome"] in ("matured", "dead"):
                break
        return self.state()

    def predict(self, overrides):
        """Next-day what-if: apply the overrides (soil_moisture = irrigate or drain to that level
        first), run one day of water balance and scoring, and forecast from today's progress.
        Changes nothing."""
        env = dict(self.env)
        for k, v in overrides.items():
            if k not in PARAM_RANGES:
                raise RuntimeError(f"Unknown parameter '{k}'")
            env[k] = clamp_param(k, v)
        sm, etc, s = self._water_and_score(env, self.stage)
        avg = float(self.progress.mean())
        return {
            "growth_score": round(s, 4),
            "health_zone": health_zone(s),
            "growth_rate_percent_per_day": round(delta(s) * 100, 3),
            "soil_moisture_percent": round(sm, 2),
            "evapotranspiration_mm_per_day": round(etc, 3),
            "forecast": forecast(avg, s, self.scorer.q90),
            "environment": {k: round(v, 3) for k, v in env.items()},
        }

    def log(self, message):
        pass

    def state(self):
        avg = float(self.progress.mean())
        if self.score is None:
            # Before the first day, report what day 1 would bring under current conditions
            p = self.predict({})
            s, etc = p["growth_score"], p["evapotranspiration_mm_per_day"]
        else:
            s, etc = self.score, self.etc
        fc = forecast(avg, s, self.scorer.q90)
        return {
            "day": self.day,
            "growth_score": round(s, 4),
            "health_zone": health_zone(s),
            "growth_rate_percent_per_day": round(delta(s) * 100, 3),
            "average_progress_percent": round(avg * 100, 2),
            "min_progress_percent": round(float(self.progress.min()) * 100, 2),
            "max_progress_percent": round(float(self.progress.max()) * 100, 2),
            "stage": self.stage + 1,
            "stage_name": STAGE_NAMES[self.stage],
            "outcome": outcome_of(avg, self.peak, fc),
            "soil_moisture_percent": round(self.env["soil_moisture"], 2),
            "evapotranspiration_mm_per_day": round(etc, 3),
            "forecast": fc,
            "learned_model": self.scorer.learned,
            "environment": {k: round(v, 3) for k, v in self.env.items()},
        }
