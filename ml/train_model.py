"""
Train and select the growth-score surrogate (v4)
================================================
  python train_model.py

1. Builds the training set from three sources (see ablation.py for why): uniform samples over
   the full input space, states the twin actually visits in simulated seasons, and samples
   concentrated near the optimal band centres.
2. Compares six models with 5-fold cross validation and a held-out test set.
3. Validates every model on 400 simulated seasons against the true response function
   (trajectory-level validation), because small pointwise biases accumulate over a season.
4. Tunes the selected model, adds isotonic calibration and split-conformal intervals.
5. Exports the selected model to outputs/growth_model.json for the Unity C# evaluator.

Install: pip install numpy scikit-learn
"""

import json
import os
import time

import numpy as np
from sklearn.ensemble import (GradientBoostingRegressor, HistGradientBoostingRegressor,
                              RandomForestRegressor)
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import KFold, cross_val_score, train_test_split

import twin_core as tc

SEED = 42
rng = np.random.default_rng(SEED)
os.makedirs("outputs", exist_ok=True)
results = {}

# =============================================================================
# 1. Dataset: 12,000 uniform + 8,000 twin states + 4,000 near-optimal (24,000)
# =============================================================================
LIMITS = {v: tc.PARAMS[v][:4] for v in tc.VARS}


def sample_stratum(kind, n):
    cols = {}
    for v in tc.VARS:
        a, b, l, u = LIMITS[v]
        if kind == "uniform":
            x = rng.uniform(l, u, n)
        elif kind == "optimal":
            m, h = (a + b) / 2, (b - a) / 2
            core = rng.random(n) < 0.3                       # densify the band centre
            x = np.where(core, rng.uniform(m - 0.2 * h, m + 0.2 * h, n),
                         rng.uniform(a - 0.1 * (a - l), b + 0.1 * (u - b), n))
        elif kind == "moderate":                             # shoulders just outside the band
            x = rng.uniform(a - 0.6 * (a - l), b + 0.6 * (u - b), n)
        elif kind == "stressed":                             # each variable stressed with p = 0.5
            low = rng.uniform(l, a - 0.6 * (a - l), n)
            high = rng.uniform(b + 0.6 * (u - b), u, n)
            tail = np.where(rng.random(n) < 0.5, low, high)
            x = np.where(rng.random(n) < 0.5, tail, rng.uniform(l, u, n))
        cols[v] = x
    if kind == "stressed":                                   # guarantee at least one stressed variable
        pick = rng.integers(0, len(tc.VARS), n)
        for j, v in enumerate(tc.VARS):
            a, b, l, u = LIMITS[v]
            low = rng.uniform(l, a - 0.6 * (a - l), n)
            high = rng.uniform(b + 0.6 * (u - b), u, n)
            cols[v] = np.where(pick == j, np.where(rng.random(n) < 0.5, low, high), cols[v])
    cols["growth_stage"] = rng.integers(0, 7, n).astype(float)
    return cols


def stratum_X(kind, n):
    cols = sample_stratum(kind, n)
    return np.column_stack([cols[c] for c in tc.RAW_FEATURES])


def twin_states(n, seed):
    """Environment and stage on the days the twin actually simulates: rainfed seasons under the
    stochastic weather generator, driven by the true response function."""
    wx = tc.weather_generator(600, n_days=120, seed=seed)
    sim = tc.simulate(wx, lambda e, st: tc.growth_score(e, st), record=True)
    pool = np.vstack([np.column_stack([r["env"][v][r["active"]] for v in tc.VARS] + [r["stage"][r["active"]]])
                      for r in sim["records"]])
    return pool[np.random.default_rng(seed).choice(len(pool), n, replace=False)]


X_raw = np.vstack([stratum_X("uniform", 12000), twin_states(8000, 301), stratum_X("optimal", 4000)])
env = {v: X_raw[:, j] for j, v in enumerate(tc.VARS)}
y_clean = tc.growth_score(env, X_raw[:, -1].astype(int))
y = np.clip(y_clean + rng.normal(0, 0.012, len(y_clean)), 0, 1)
perm = rng.permutation(len(y))
X_raw, y = X_raw[perm], y[perm]
X_eng = tc.engineered(X_raw)

idx = np.arange(len(y))
i_rest, i_test = train_test_split(idx, test_size=0.15, random_state=SEED)
i_train, i_hold = train_test_split(i_rest, test_size=0.20, random_state=SEED)
i_iso, i_conf = train_test_split(i_hold, test_size=0.40, random_state=SEED)
results["dataset"] = {"n": int(len(y)), "deteriorating": int((y < 0.5).sum()),
                      "growing": int((y >= 0.5).sum()), "train": int(len(i_train)),
                      "isotonic": int(len(i_iso)), "conformal": int(len(i_conf)),
                      "test": int(len(i_test)), "target_std": float(y[i_test].std())}
print("Dataset", results["dataset"])

# =============================================================================
# 2. Candidate models
# =============================================================================
HGB = dict(max_iter=500, learning_rate=0.05, max_leaf_nodes=31, min_samples_leaf=20,
           early_stopping=False, random_state=SEED)
CANDIDATES = {
    "Linear regression":          (LinearRegression(), "raw"),
    "Random forest":              (RandomForestRegressor(n_estimators=300, min_samples_leaf=2,
                                                         n_jobs=-1, random_state=SEED), "raw"),
    "Gradient boosting":          (GradientBoostingRegressor(n_estimators=300, max_depth=5, learning_rate=0.04,
                                                             subsample=0.8, min_samples_leaf=5,
                                                             max_features=0.8, random_state=SEED), "raw"),
    "HistGB":                     (HistGradientBoostingRegressor(**HGB), "raw"),
    "HistGB + deviations":        (HistGradientBoostingRegressor(**HGB), "eng"),
    "HistGB + deviations + mono": (HistGradientBoostingRegressor(**HGB, monotonic_cst=tc.MONOTONIC), "eng"),
}


def feats(kind, rows=None):
    X = X_raw if kind == "raw" else X_eng
    return X if rows is None else X[rows]


class Surrogate:
    """A fitted model + isotonic calibration, usable as a score function in the simulator."""

    def __init__(self, model, kind, iso=None):
        self.model, self.kind, self.iso = model, kind, iso

    def predict_X(self, Xr):
        X = Xr if self.kind == "raw" else tc.engineered(Xr)
        p = np.clip(self.model.predict(X), 0, 1)
        return np.clip(self.iso.predict(p), 0, 1) if self.iso is not None else p

    def __call__(self, env_d, stage):
        Xr = np.column_stack([np.asarray(env_d[v], float) for v in tc.VARS] + [np.asarray(stage, float)])
        return self.predict_X(Xr)


def truth(env_d, stage):
    return tc.growth_score(env_d, stage)


OPT = {"pH": 6.5, "soil_moisture": 55.0, "sunlight_hours": 8.0, "temperature": 25.0, "humidity": 62.5}
MILD = {"pH": 6.5, "soil_moisture": 30.0, "sunlight_hours": 8.0, "temperature": 33.0, "humidity": 62.5}


def probe(sur):
    """Top-end value at the optimum and share of the true stage effect that is captured."""
    st = np.arange(7)
    opt = sur({k: np.full(7, v) for k, v in OPT.items()}, st)
    mild = sur({k: np.full(7, v) for k, v in MILD.items()}, st)
    mild_true = truth({k: np.full(7, v) for k, v in MILD.items()}, st)
    return float(opt.mean()), float((mild[-1] - mild[0]) / (mild_true[-1] - mild_true[0])), mild.tolist(), mild_true.tolist()


# Trajectory validation set: 400 rainfed seasons with stochastic weather
WX = tc.weather_generator(400, n_days=120, seed=7)
TRUE_SIM = tc.simulate(WX, truth)


def trajectory_metrics(sur):
    sim = tc.simulate(WX, sur)
    t, m = TRUE_SIM, sim
    both = (t["outcome"] == "matured") & (m["outcome"] == "matured")
    return {"outcome_agreement": float((t["outcome"] == m["outcome"]).mean()),
            "maturity_day_mae": float(np.abs(t["day"][both] - m["day"][both]).mean()) if both.any() else float("nan"),
            "maturity_day_bias": float((m["day"][both] - t["day"][both]).mean()) if both.any() else float("nan"),
            "stress_days_mae": float(np.abs(t["stress"] - m["stress"]).mean()),
            "final_progress_mae_pct": float(100 * np.abs(t["final_progress"] - m["final_progress"]).mean())}


print("\nTrue simulator outcomes:", {k: int((TRUE_SIM["outcome"] == k).sum())
                                     for k in ("matured", "died", "season_end")})
results["true_outcomes"] = {k: int((TRUE_SIM["outcome"] == k).sum()) for k in ("matured", "died", "season_end")}

cv = KFold(5, shuffle=True, random_state=SEED)
results["models"] = {}
fitted = {}
for name, (model, kind) in CANDIDATES.items():
    t0 = time.time()
    cv_rmse = -cross_val_score(model, feats(kind, i_train), y[i_train], cv=cv,
                               scoring="neg_root_mean_squared_error")
    model.fit(feats(kind, i_train), y[i_train])
    iso = None
    if name != "Linear regression":
        iso = IsotonicRegression(out_of_bounds="clip").fit(np.clip(model.predict(feats(kind, i_iso)), 0, 1), y[i_iso])
    sur = Surrogate(model, kind, iso)
    pred = sur.predict_X(X_raw[i_test])
    top, stage_cap, _, _ = probe(sur)
    traj = trajectory_metrics(sur)
    results["models"][name] = {
        "cv_rmse_mean": float(cv_rmse.mean()), "cv_rmse_std": float(cv_rmse.std()),
        "r2": float(r2_score(y[i_test], pred)), "rmse": float(np.sqrt(mean_squared_error(y[i_test], pred))),
        "mae": float(mean_absolute_error(y[i_test], pred)),
        "zone_accuracy": float(((pred >= 0.5) == (y[i_test] >= 0.5)).mean()),
        "score_at_optimum": top, "stage_effect_captured": stage_cap, **traj,
        "seconds": time.time() - t0}
    fitted[name] = sur
    r = results["models"][name]
    print(f"{name:<28} CV RMSE {r['cv_rmse_mean']:.4f}  test R2 {r['r2']:.4f}  RMSE {r['rmse']:.4f}  "
          f"opt {top:.3f}  stage {100*stage_cap:5.1f}%  outcome {100*traj['outcome_agreement']:.1f}%  "
          f"day MAE {traj['maturity_day_mae']:.2f} bias {traj['maturity_day_bias']:+.2f}  "
          f"stress MAE {traj['stress_days_mae']:.2f}  ({r['seconds']:.0f}s)")

# =============================================================================
# 3. Tune the selected model (deviation features + monotonic constraints)
# =============================================================================
# Selected family: HistGB on raw features. It matches the random forest on accuracy and
# trajectory error while exporting to a few MB (the forest's deep trees do not).
SELECTED = "HistGB"
grid = []
for lr in (0.05, 0.1):
    for leaves in (31, 63, 127):
        for iters in (500, 1000):
            m = HistGradientBoostingRegressor(**{**HGB, "learning_rate": lr, "max_leaf_nodes": leaves,
                                                 "max_iter": iters})
            s = -cross_val_score(m, X_raw[i_train], y[i_train], cv=cv, scoring="neg_root_mean_squared_error")
            grid.append({"learning_rate": lr, "max_leaf_nodes": leaves, "max_iter": iters,
                         "cv_rmse": float(s.mean()), "cv_std": float(s.std())})
            print(f"  lr {lr:<5} leaves {leaves:<4} iters {iters:<5} CV RMSE {s.mean():.4f} +/- {s.std():.4f}")
best = min(grid, key=lambda g: g["cv_rmse"])
results["tuning"] = {"grid": grid, "best": best}
final = HistGradientBoostingRegressor(**{**HGB, "learning_rate": best["learning_rate"],
                                         "max_leaf_nodes": best["max_leaf_nodes"], "max_iter": best["max_iter"]})
final.fit(X_raw[i_train], y[i_train])
iso = IsotonicRegression(out_of_bounds="clip").fit(np.clip(final.predict(X_raw[i_iso]), 0, 1), y[i_iso])
sur = Surrogate(final, "raw", iso)

# Split-conformal 90% interval
resid = np.abs(y[i_conf] - sur.predict_X(X_raw[i_conf]))
q90 = float(np.quantile(resid, np.ceil(0.9 * (len(resid) + 1)) / len(resid)))
pred = sur.predict_X(X_raw[i_test])
coverage = float((np.abs(y[i_test] - pred) <= q90).mean())

top, stage_cap, mild_pred, mild_true = probe(sur)
traj = trajectory_metrics(sur)
t_true, t_pred = y[i_test] >= 0.5, pred >= 0.5
results["final"] = {
    "params": best, "r2": float(r2_score(y[i_test], pred)),
    "rmse": float(np.sqrt(mean_squared_error(y[i_test], pred))), "mae": float(mean_absolute_error(y[i_test], pred)),
    "zone_accuracy": float((t_true == t_pred).mean()),
    "confusion": {"tn": int((~t_true & ~t_pred).sum()), "fp": int((~t_true & t_pred).sum()),
                  "fn": int((t_true & ~t_pred).sum()), "tp": int((t_true & t_pred).sum())},
    "conformal_q90": q90, "conformal_coverage": coverage,
    "score_at_optimum": top, "stage_effect_captured": stage_cap,
    "stage_mild_pred": mild_pred, "stage_mild_true": mild_true, **traj}

# Reliability (10 bins), raw vs calibrated
raw_test = np.clip(final.predict(X_raw[i_test]), 0, 1)
rel = []
for name, p in (("raw", raw_test), ("calibrated", pred)):
    for lo in np.arange(0, 1, 0.1):
        m = (p >= lo) & ((p < lo + 0.1) if lo < 0.9 else (p <= 1))
        if m.sum():
            rel.append({"model": name, "bin": round(lo + 0.05, 2), "n": int(m.sum()),
                        "mean_pred": float(p[m].mean()), "mean_true": float(y[i_test][m].mean())})
results["reliability"] = rel

# Permutation importance of the final pipeline, grouped by original variable
base = r2_score(y[i_test], pred)
imp = {}
for j, v in enumerate(tc.RAW_FEATURES):
    drops = []
    for rep in range(10):
        Xp = X_raw[i_test].copy()
        Xp[:, j] = np.random.default_rng(rep).permutation(Xp[:, j])
        drops.append(base - r2_score(y[i_test], sur.predict_X(Xp)))
    imp[v] = {"mean": float(np.mean(drops)), "std": float(np.std(drops))}
results["importance"] = imp

# Scatter subsample for the paper
sel = np.random.default_rng(1).choice(len(i_test), 350, replace=False)
results["scatter"] = [[float(y[i_test][k]), float(pred[k])] for k in sel]

f = results["final"]
print(f"\nFinal: R2 {f['r2']:.4f} RMSE {f['rmse']:.4f} zone acc {100*f['zone_accuracy']:.2f}%  "
      f"opt {top:.3f} stage {100*stage_cap:.1f}%  conformal q90 {q90:.4f} coverage {100*coverage:.1f}%")
print(f"       outcome agreement {100*traj['outcome_agreement']:.1f}%  maturity day MAE {traj['maturity_day_mae']:.2f}  "
      f"bias {traj['maturity_day_bias']:+.2f}  stress MAE {traj['stress_days_mae']:.2f}")
print("Importance:", {k: round(v['mean'], 3) for k, v in imp.items()})

# =============================================================================
# 4. Export for Unity
# =============================================================================
trees = []
for pred_list in final._predictors:
    nodes = pred_list[0].nodes
    trees.append({"feature": nodes["feature_idx"].astype(int).tolist(),
                  "threshold": nodes["num_threshold"].astype(float).tolist(),
                  "left": nodes["left"].astype(int).tolist(), "right": nodes["right"].astype(int).tolist(),
                  "leaf": nodes["is_leaf"].astype(int).tolist(), "value": nodes["value"].astype(float).tolist()})
export = {
    "version": 4,
    "features": tc.RAW_FEATURES,
    "baseline": float(np.ravel(final._baseline_prediction)[0]),
    "trees": trees,
    "isotonic_x": iso.X_thresholds_.tolist(), "isotonic_y": iso.y_thresholds_.tolist(),
    "conformal_q90": q90,
}
with open("outputs/growth_model.json", "w") as fh:
    json.dump(export, fh)


def reference_eval(model_json, x_raw):
    """Line-by-line mirror of GrowthModel.cs, used to check parity of the exported file."""
    feats_ = list(x_raw)
    total = model_json["baseline"]
    for t in model_json["trees"]:
        n = 0
        while not t["leaf"][n]:
            n = t["left"][n] if feats_[t["feature"][n]] <= t["threshold"][n] else t["right"][n]
        total += t["value"][n]
    raw = min(1.0, max(0.0, total))
    xs, ys = model_json["isotonic_x"], model_json["isotonic_y"]
    if raw <= xs[0]:
        out = ys[0]
    elif raw >= xs[-1]:
        out = ys[-1]
    else:
        k = int(np.searchsorted(xs, raw, side="right")) - 1
        out = ys[k] + (ys[k + 1] - ys[k]) * (raw - xs[k]) / (xs[k + 1] - xs[k])
    return min(1.0, max(0.0, out))


ref = np.array([reference_eval(export, X_raw[k]) for k in i_test])
results["export"] = {"trees": len(trees), "nodes": int(sum(len(t["leaf"]) for t in trees)),
                     "bytes": os.path.getsize("outputs/growth_model.json"),
                     "parity_max_abs": float(np.abs(ref - pred).max())}
print(f"Exported {len(trees)} trees, {results['export']['nodes']} nodes, "
      f"{results['export']['bytes']/1024:.0f} KB, parity max |diff| = {results['export']['parity_max_abs']:.2e}")
assert results["export"]["parity_max_abs"] < 1e-9, "reference traversal does not match scikit-learn"
print("Parity check passed: reference traversal matches scikit-learn")

# Parity vectors for the Unity EditMode test (GrowthModelTests.cs). Inputs are rounded to
# float32 first, because GrowthModel.Predict takes floats, so both sides see identical values.
PARITY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "Assets", "Tests", "EditMode", "parity_vectors.json")
pick = np.random.default_rng(7).choice(i_test, 50, replace=False)
cases = []
for k in pick:
    x32 = X_raw[k].astype(np.float32).astype(float)
    x32[-1] = round(x32[-1])
    cases.append({"input": x32.tolist(), "expected": reference_eval(export, x32)})
os.makedirs(os.path.dirname(PARITY_PATH), exist_ok=True)
with open(PARITY_PATH, "w") as fh:
    json.dump({"features": tc.RAW_FEATURES, "cases": cases}, fh, indent=1)
print(f"Saved {len(cases)} parity vectors to {os.path.normpath(PARITY_PATH)}")

with open("outputs/metrics_v4.json", "w") as fh:
    json.dump(results, fh, indent=1)
import pickle
with open("outputs/surrogate_v4.pkl", "wb") as fh:
    pickle.dump({"model": final, "iso": iso, "q90": q90}, fh)
print("Saved outputs/metrics_v4.json, outputs/growth_model.json, outputs/surrogate_v4.pkl")
