"""
Ablation: what does each part of the training-data design contribute?
  python ablation.py          (needs twin_core.py; about 2 minutes)

The tuned HistGB model is trained on four dataset designs of equal size (24,000 samples) and
evaluated on the SAME independent test set and the SAME 400 simulated seasons:
  Full design        stressed + moderate + optimal (with 30% band-centre core) + uniform
  No core            as Full, but the optimal stratum has no band-centre densification
  No moderate        stressed + optimal + uniform, 8,000 each (the v3 design)
  Uniform only       24,000 uniform samples
plus Full design without isotonic calibration. Writes outputs/ablation_v4.json.
"""

import json
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import mean_squared_error, r2_score

import twin_core as tc

PARAMS = dict(max_iter=500, learning_rate=0.05, max_leaf_nodes=127, min_samples_leaf=20,
              early_stopping=False, random_state=42)


def sample(kind, n, rng, core=True):
    cols = {}
    for v in tc.VARS:
        a, b, l, u = tc.PARAMS[v][:4]
        if kind == "uniform":
            x = rng.uniform(l, u, n)
        elif kind == "optimal":
            m, h = (a + b) / 2, (b - a) / 2
            wide = rng.uniform(a - 0.1 * (a - l), b + 0.1 * (u - b), n)
            x = np.where(rng.random(n) < 0.3, rng.uniform(m - 0.2 * h, m + 0.2 * h, n), wide) if core else wide
        elif kind == "moderate":
            x = rng.uniform(a - 0.6 * (a - l), b + 0.6 * (u - b), n)
        else:
            tail = np.where(rng.random(n) < 0.5, rng.uniform(l, a - 0.6 * (a - l), n),
                            rng.uniform(b + 0.6 * (u - b), u, n))
            x = np.where(rng.random(n) < 0.5, tail, rng.uniform(l, u, n))
        cols[v] = x
    if kind == "stressed":
        pick = rng.integers(0, len(tc.VARS), n)
        for j, v in enumerate(tc.VARS):
            a, b, l, u = tc.PARAMS[v][:4]
            t = np.where(rng.random(n) < 0.5, rng.uniform(l, a - 0.6 * (a - l), n),
                         rng.uniform(b + 0.6 * (u - b), u, n))
            cols[v] = np.where(pick == j, t, cols[v])
    X = np.column_stack([cols[v] for v in tc.VARS] + [rng.integers(0, 7, n).astype(float)])
    y = tc.growth_score({v: X[:, j] for j, v in enumerate(tc.VARS)}, X[:, -1].astype(int))
    return X, np.clip(y + rng.normal(0, 0.012, n), 0, 1)


def twin_states(n, seed):
    """States (environment + stage) the twin actually visits: daily conditions from simulated
    rainfed seasons under the stochastic weather generator, using the true response function."""
    wx = tc.weather_generator(600, n_days=120, seed=seed)
    sim = tc.simulate(wx, lambda e, s: tc.growth_score(e, s), record=True)
    rows = [np.column_stack([r["env"][v][r["active"]] for v in tc.VARS] + [r["stage"][r["active"]]])
            for r in sim["records"]]
    pool = np.vstack(rows)
    rng = np.random.default_rng(seed)
    X = pool[rng.choice(len(pool), n, replace=False)]
    y = tc.growth_score({v: X[:, j] for j, v in enumerate(tc.VARS)}, X[:, -1].astype(int))
    return X, np.clip(y + rng.normal(0, 0.012, n), 0, 1)


def build(design, seed):
    rng = np.random.default_rng(seed)
    if design == "Full design":
        parts = [sample(k, 6000, rng) for k in ("stressed", "moderate", "optimal", "uniform")]
    elif design == "No core":
        parts = [sample(k, 6000, rng, core=False) for k in ("stressed", "moderate", "optimal", "uniform")]
    elif design == "No moderate":
        parts = [sample(k, 8000, rng) for k in ("stressed", "optimal", "uniform")]
    elif design == "Uniform only":
        parts = [sample("uniform", 24000, rng)]
    elif design == "Uniform + core":
        parts = [sample("uniform", 18000, rng), sample("optimal", 6000, rng)]
    elif design == "Uniform + twin states":
        parts = [sample("uniform", 12000, rng), twin_states(12000, 300 + seed)]
    elif design == "Uniform + twin states + core":
        parts = [sample("uniform", 12000, rng), twin_states(8000, 300 + seed), sample("optimal", 4000, rng)]
    X = np.vstack([p[0] for p in parts]); y = np.concatenate([p[1] for p in parts])
    perm = rng.permutation(len(y))
    return X[perm], y[perm]


X_test, y_test = build("Full design", 999)          # common independent test set (mixture)
y_test = y_test[:5000]; X_test = X_test[:5000]
X_op, y_op = twin_states(5000, 4242)                 # operational test set: states the twin visits
WX = tc.weather_generator(400, n_days=120, seed=7)
TRUE = tc.simulate(WX, lambda e, s: tc.growth_score(e, s))
OPT = {"pH": 6.5, "soil_moisture": 55.0, "sunlight_hours": 8.0, "temperature": 25.0, "humidity": 62.5}
MILD = {"pH": 6.5, "soil_moisture": 30.0, "sunlight_hours": 8.0, "temperature": 33.0, "humidity": 62.5}

results = {}
for design, calibrate in (("Full design", True), ("Full design", False), ("No core", True),
                          ("No moderate", True), ("Uniform only", True), ("Uniform + core", True),
                          ("Uniform + twin states", True), ("Uniform + twin states + core", True)):
    X, y = build(design, 1)
    n_iso = 2448
    model = HistGradientBoostingRegressor(**PARAMS).fit(X[n_iso:], y[n_iso:])
    iso = IsotonicRegression(out_of_bounds="clip").fit(np.clip(model.predict(X[:n_iso]), 0, 1), y[:n_iso]) if calibrate else None

    def score(env, stage, model=model, iso=iso):
        Xr = np.column_stack([np.asarray(env[v], float) for v in tc.VARS] + [np.asarray(stage, float)])
        p = np.clip(model.predict(Xr), 0, 1)
        return np.clip(iso.predict(p), 0, 1) if iso is not None else p

    pred = score({v: X_test[:, j] for j, v in enumerate(tc.VARS)}, X_test[:, -1])
    pred_op = score({v: X_op[:, j] for j, v in enumerate(tc.VARS)}, X_op[:, -1])
    st = np.arange(7)
    opt = score({k: np.full(7, v) for k, v in OPT.items()}, st).mean()
    mild = score({k: np.full(7, v) for k, v in MILD.items()}, st)
    mild_t = tc.growth_score({k: np.full(7, v) for k, v in MILD.items()}, st)
    sim = tc.simulate(WX, score)
    both = (TRUE["outcome"] == "matured") & (sim["outcome"] == "matured")
    name = design + ("" if calibrate else " (no isotonic)")
    results[name] = {
        "rmse": float(np.sqrt(mean_squared_error(y_test, pred))), "r2": float(r2_score(y_test, pred)),
        "rmse_operational": float(np.sqrt(mean_squared_error(y_op, pred_op))),
        "zone_accuracy": float(((pred >= 0.5) == (y_test >= 0.5)).mean()),
        "score_at_optimum": float(opt), "stage_effect_captured": float((mild[-1] - mild[0]) / (mild_t[-1] - mild_t[0])),
        "outcome_agreement": float((TRUE["outcome"] == sim["outcome"]).mean()),
        "maturity_day_mae": float(np.abs(sim["day"][both] - TRUE["day"][both]).mean()),
        "maturity_day_bias": float((sim["day"][both] - TRUE["day"][both]).mean())}
    r = results[name]
    print(f"{name:<30} RMSE {r['rmse']:.4f}  op RMSE {r['rmse_operational']:.4f}  R2 {r['r2']:.4f}  zone {100*r['zone_accuracy']:.2f}%  "
          f"opt {r['score_at_optimum']:.3f}  stage {100*r['stage_effect_captured']:5.1f}%  "
          f"outcome {100*r['outcome_agreement']:.1f}%  day MAE {r['maturity_day_mae']:.2f}  "
          f"bias {r['maturity_day_bias']:+.2f}")

json.dump(results, open("outputs/ablation_v4.json", "w"), indent=1)
print("Saved outputs/ablation_v4.json")
