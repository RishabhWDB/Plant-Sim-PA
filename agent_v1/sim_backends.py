"""
Simulation backends the agent can drive.

UnitySim  talks to SimulationServer.cs over HTTP (the live 3D simulation).
LocalSim  is a pure Python replica of the Unity growth logic. It runs instantly,
          so it is used for development and batch evaluation.

Both expose the same methods, so policies never know which one they are using.
"""

import random
import requests

PARAM_RANGES = {
    "ph":             (3.5, 9.5),
    "soil_moisture":  (5.0, 100.0),
    "sunlight_hours": (0.0, 16.0),
    "temperature":    (0.0, 45.0),
    "humidity":       (10.0, 100.0),
    "rainfall":       (0.0, 120.0),
}

DEFAULT_ENV = {
    "ph": 6.5, "soil_moisture": 55.0, "sunlight_hours": 8.0,
    "temperature": 25.0, "humidity": 62.0, "rainfall": 40.0,
}

STAGE_NAMES = ["Seed", "Germination", "Sprout", "Seedling", "Vegetative", "Flowering", "Mature"]


def clamp_param(name, value):
    lo, hi = PARAM_RANGES[name]
    return max(lo, min(hi, float(value)))


# =============================================================================
# Unity backend
# =============================================================================

class UnitySim:
    def __init__(self, url="http://localhost:8765", timeout=120):
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

    def predict(self, overrides):
        return self._req("POST", "/predict", {k: float(v) for k, v in overrides.items()})

    def log(self, message):
        try:
            self._req("POST", "/log", {"message": str(message)[:300]})
        except Exception:
            pass  # on-screen log is cosmetic


# =============================================================================
# Local Python replica (mirrors GrowthEngine.PlaceholderModel + Plant.UpdateGrowth)
# =============================================================================

OPTIMA = {
    #                 opt_min opt_max hard_min hard_max weight
    "ph":             (6.0,   7.0,    3.5,     9.5,    1.0),
    "soil_moisture":  (40.0,  70.0,   5.0,     100.0,  1.4),
    "sunlight_hours": (6.0,   10.0,   0.0,     16.0,   1.2),
    "temperature":    (20.0,  30.0,   0.0,     45.0,   1.4),
    "humidity":       (50.0,  75.0,   10.0,    100.0,  0.9),
    "rainfall":       (20.0,  60.0,   0.0,     120.0,  1.1),
}


def bell_score(v, opt_min, opt_max, hard_min, hard_max):
    if v <= hard_min or v >= hard_max:
        return 0.0
    if opt_min <= v <= opt_max:
        mid, half = (opt_min + opt_max) / 2, (opt_max - opt_min) / 2
        return 0.85 + 0.15 * (1 - abs(v - mid) / (half + 1e-6))
    if v < opt_min:
        d = (opt_min - v) / (opt_min - hard_min + 1e-6)
    else:
        d = (v - opt_max) / (hard_max - opt_max + 1e-6)
    return max(0.0, min(1.0, 1 - d ** 1.8))


def growth_score(env):
    scores = {k: bell_score(env[k], *OPTIMA[k][:4]) for k in OPTIMA}
    raw = sum(scores[k] * OPTIMA[k][4] for k in OPTIMA) / 7.0
    m = min(scores.values())
    if m < 0.2:
        raw = raw * (m / 0.2) ** 1.5 * 0.5
    raw = max(0.0, min(1.0, raw))
    return raw / 0.5 * 0.5 if raw < 0.5 else 0.5 + (raw - 0.5) / 0.5 * 0.5


def growth_rate(score):
    return (score - 0.5) * 2 * 0.02 if score >= 0.5 else -(0.5 - score) * 2 * 0.015


def health_zone(score):
    if score < 0.2:
        return "critical"
    if score < 0.5:
        return "deteriorating"
    if score < 0.75:
        return "growing"
    return "thriving"


class LocalSim:
    def __init__(self, rows=12, cols=12, seed=0, offset_range=0.05):
        rng = random.Random(seed)
        self.offsets = [rng.uniform(-offset_range, offset_range) for _ in range(rows * cols)]
        self.env = dict(DEFAULT_ENV)
        self.reset()

    def health(self):
        return {"ok": True, "message": "Local simulation"}

    def reset(self):
        self.day = 0
        self.progress = [0.0] * len(self.offsets)
        self.peak = 0.0
        return self.state()

    def pause(self):
        return {"ok": True}

    def set_parameter(self, name, value):
        if name not in PARAM_RANGES:
            raise RuntimeError(f"Unknown parameter '{name}'")
        self.env[name] = clamp_param(name, value)
        return dict(self.env)

    def advance(self, days=1):
        for _ in range(max(1, min(30, int(days)))):
            self.day += 1
            s = growth_score(self.env)
            for i, off in enumerate(self.offsets):
                adj = max(0.0, min(1.0, s + off))
                self.progress[i] = max(0.0, min(1.0, self.progress[i] + growth_rate(adj)))
            self.peak = max(self.peak, self._avg())
            if self.state()["outcome"] in ("matured", "dead"):
                break
        return self.state()

    def predict(self, overrides):
        env = dict(self.env)
        for k, v in overrides.items():
            env[k] = clamp_param(k, v)
        s = growth_score(env)
        return {
            "growth_score": round(s, 4),
            "health_zone": health_zone(s),
            "growth_rate_percent_per_day": round(growth_rate(s) * 100, 3),
            "environment": env,
        }

    def log(self, message):
        pass

    def _avg(self):
        return sum(self.progress) / len(self.progress)

    def state(self):
        s = growth_score(self.env)
        rate = growth_rate(s)
        avg = self._avg()
        predicted = -1

        if avg >= 0.98:
            outcome, predicted = "matured", 0
        elif self.peak > 0.05 and avg <= 0.001:
            outcome, predicted = "dead", 0
        elif rate > 0.0005:
            outcome = "growing_toward_maturity"
            predicted = int(-(-(0.98 - avg) // rate))
        elif rate < -0.0005:
            if self.peak > 0.05:
                outcome = "declining_toward_death"
                predicted = int(-(-avg // -rate))
            else:
                outcome = "failing_to_establish"
        else:
            outcome = "stalled"

        stage = max(0, min(6, int(avg * 7)))
        return {
            "day": self.day,
            "growth_score": round(s, 4),
            "health_zone": health_zone(s),
            "growth_rate_percent_per_day": round(rate * 100, 3),
            "average_progress_percent": round(avg * 100, 2),
            "min_progress_percent": round(min(self.progress) * 100, 2),
            "max_progress_percent": round(max(self.progress) * 100, 2),
            "stage": stage + 1,
            "stage_name": STAGE_NAMES[stage],
            "outcome": outcome,
            "predicted_days": predicted,
            "environment": {k: round(v, 3) for k, v in self.env.items()},
        }
