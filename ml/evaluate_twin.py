"""
Evaluate the digital twin (v4)
==============================
  python evaluate_twin.py        (run train_model.py first)

1. Case study: a 30-day dry spell on a rainfed field, with and without warning-triggered
   irrigation, plus a fully irrigated optimal season. Prints a day-by-day trace.
2. Forecasting benchmark: time-to-maturity forecasts on 400 stochastic seasons, comparing
   persistence, a 7-day moving average and climatology.
3. Response curves (target vs surrogate) for the paper.
Writes outputs/evaluation_v4.json.
"""

import json
import pickle

import numpy as np

import twin_core as tc

S = pickle.load(open("outputs/surrogate_v4.pkl", "rb"))
MODEL, ISO, Q90 = S["model"], S["iso"], S["q90"]


def surrogate(env, stage):
    X = np.column_stack([np.atleast_1d(np.asarray(env[v], float)) for v in tc.VARS]
                        + [np.atleast_1d(np.asarray(stage, float))])
    return np.clip(ISO.predict(np.clip(MODEL.predict(X), 0, 1)), 0, 1)


def truth(env, stage):
    return tc.growth_score(env, stage)


out = {}

# =============================================================================
# 1. Case study
# =============================================================================
DRY_START, DRY_END, IRR_MM, WARN = 15, 44, 35.0, 0.6


def weather_day(day):
    if DRY_START <= day <= DRY_END:
        return dict(rain=0.0, temperature=35.0, humidity=38.0, sunlight_hours=10.0)
    rain = 12.0 if day % 3 == 0 else 0.0
    return dict(rain=rain, temperature=25.0 if day < DRY_START else 26.0, humidity=62.0, sunlight_hours=8.0)


def run_case(policy, score_fn=surrogate, max_days=130, n_plants=144):
    eps = np.random.default_rng(0).uniform(-0.05, 0.05, n_plants)
    p = np.zeros(n_plants)
    sm, peak, prev_s = 55.0, 0.0, 1.0
    rows, outcome = [], "season_end"
    for day in range(1, max_days + 1):
        stage = int(min(6, np.floor(7 * p.mean())))
        if policy == "optimal":
            w = dict(rain=0.0, temperature=25.0, humidity=62.5, sunlight_hours=8.0)
        else:
            w = weather_day(day)
        if policy == "optimal":
            irr = max(0.0, (55.0 - sm) * tc.MM_PER_PCT + float(tc.KC[stage] * tc.et0_turc(25.0, 62.5, 8.0)))
        elif policy == "warning" and prev_s < WARN:
            irr = IRR_MM
        else:
            irr = 0.0
        sm_new, flux = tc.water_step(sm, w["rain"], irr, w["temperature"], w["humidity"],
                                     w["sunlight_hours"], stage)
        sm = float(sm_new)
        env = {"pH": 6.5, "soil_moisture": sm, "sunlight_hours": w["sunlight_hours"],
               "temperature": w["temperature"], "humidity": w["humidity"]}
        s_true, det = tc.growth_score(env, stage, detail=True)
        s_hat = float(score_fn(env, stage)[0]) if score_fn is surrogate else float(s_true)
        step = float(tc.delta(s_hat))
        p = np.clip(p + tc.delta(np.clip(s_hat + eps, 0, 1)), 0, 1)
        pm = float(p.mean())
        peak = max(peak, pm)
        fc = float(tc.forecast_days(pm, s_hat))
        lo, hi = float(tc.forecast_days(pm, min(1, s_hat + Q90))), float(tc.forecast_days(pm, max(0, s_hat - Q90)))
        rows.append(dict(day=day, rain=w["rain"], irrigation=irr, T=w["temperature"], RH=w["humidity"],
                         sun=w["sunlight_hours"], sm=sm, et0=float(flux["et0"]), etc=float(flux["etc"]),
                         ks=float(flux["ks"]), drain=float(flux["drain"]), stage=stage,
                         phi={k: float(v) for k, v in det["phi"].items()}, r=float(det["r"]),
                         c_crit=float(det["c_crit"]), c_comp=float(det["c_comp"]),
                         n_stressed=int(det["n_stressed"]), gamma=float(det["gamma"]),
                         limiting=str(det["limiting"]), s_true=float(s_true), s_hat=s_hat, delta=step,
                         p_mean=pm, p_min=float(p.min()), p_max=float(p.max()), forecast=fc,
                         forecast_lo=lo, forecast_hi=hi))
        prev_s = s_hat
        if pm >= tc.MATURE_AT:
            outcome = "matured"
            break
        if peak > 0.05 and pm <= 0.001:
            outcome = "died"
            break
    return {"outcome": outcome, "day": rows[-1]["day"], "rows": rows,
            "stress_days": sum(r["s_hat"] < 0.5 for r in rows),
            "irrigation_mm": sum(r["irrigation"] for r in rows if DRY_START <= r["day"] <= DRY_END),
            "min_progress_after_dry": min(r["p_mean"] for r in rows[DRY_START - 1:]),
            "min_progress_day": min(rows[DRY_START - 1:], key=lambda r: r["p_mean"])["day"]}


case = {}
for policy in ("optimal", "rainfed", "warning"):
    case[policy] = run_case(policy)
    case[policy + "_truth"] = run_case(policy, score_fn=truth)
    c, t = case[policy], case[policy + "_truth"]
    print(f"{policy:<8} surrogate: {c['outcome']} day {c['day']:>3}, stress {c['stress_days']:>2}, "
          f"irrigation {c['irrigation_mm']:.0f} mm, min progress {100*c['min_progress_after_dry']:.2f}% "
          f"(day {c['min_progress_day']}) | truth: {t['outcome']} day {t['day']}, stress {t['stress_days']}")
out["case"] = case

# =============================================================================
# 2. Forecasting benchmark on stochastic seasons
# =============================================================================
SEASON = 120
WX = tc.weather_generator(400, n_days=SEASON, seed=11)
sim = tc.simulate(WX, surrogate, record=True)
recs = sim["records"]
matured = sim["outcome"] == "matured"
clim_len = float(np.median(sim["day"][matured]))
s_hist = np.stack([r["s"] for r in recs], axis=1)
ISSUE = [10, 20, 30, 40, 50, 60]
METHODS = ("ensemble", "persistence", "ma7", "climatology")
rows, pooled = [], {k: [] for k in METHODS}
pooled_cov, pooled_brier, pooled_brier_clim = [], [], []
for t in ISSUE:
    r = recs[t - 1]
    cond = (sim["day"] < 0) | (sim["day"] > t)                 # crop still growing at end of day t
    if cond.sum() == 0:
        continue
    prm = {k: v[cond] for k, v in WX["params"].items()}
    ens = tc.ensemble_forecast(prm, WX["wet"][cond, t - 1], WX["anom"][cond, t - 1], r["sm"][cond],
                               r["p_q"][cond], surrogate, members=30, horizon=SEASON - t, seed=t)
    left = SEASON - t
    actual = np.where(matured[cond], sim["day"][cond] - t, np.inf)
    q10, q50, q90 = np.quantile(ens, [0.1, 0.5, 0.9], axis=1, method="inverted_cdf")
    p_mat = np.isfinite(ens).mean(axis=1)
    cap = lambda f: np.minimum(np.where(np.isfinite(f) & (f > 0), f, left + 1), left + 1)
    fc = {"ensemble": cap(q50),
          "persistence": cap(tc.forecast_days(r["p_mean"][cond], r["s"][cond])),
          "ma7": cap(tc.forecast_days(r["p_mean"][cond], s_hist[cond, max(0, t - 7):t].mean(axis=1))),
          "climatology": cap(np.full(cond.sum(), max(clim_len - t, 1.0)))}
    act = cap(actual)
    m = matured[cond]
    row = {"issue_day": t, "n": int(cond.sum()), "n_matured": int(m.sum())}
    for k in METHODS:
        e = np.abs(fc[k] - act)[m]
        row[k] = float(np.median(e)) if m.any() else float("nan")
        pooled[k].append(e)
    cov = (q10 <= actual) & (actual <= q90)
    base = m.mean()
    brier = float(np.mean((p_mat - m) ** 2))
    brier_clim = float(np.mean((base - m) ** 2))
    row.update(coverage=float(cov.mean()), brier=brier, brier_clim=brier_clim,
               width=float(np.nanmedian(np.where(np.isfinite(q90 - q10), q90 - q10, np.nan)[m])))
    pooled_cov.append(cov); pooled_brier.append((p_mat - m) ** 2); pooled_brier_clim.append((base - m) ** 2)
    rows.append(row)
    print(f"day {t:>3}  n {row['n']:>3} ({row['n_matured']:>3} matured)  median AE: ens {row['ensemble']:5.1f}  "
          f"pers {row['persistence']:5.1f}  ma7 {row['ma7']:5.1f}  clim {row['climatology']:5.1f}  | "
          f"80% cover {100*row['coverage']:5.1f}%  Brier {brier:.3f} vs clim {brier_clim:.3f}")
overall = {k: float(np.median(np.concatenate(v))) for k, v in pooled.items()}
mean_ae = {k: float(np.mean(np.concatenate(v))) for k, v in pooled.items()}
skill = {k: 1 - mean_ae[k] / mean_ae["climatology"] for k in METHODS}
bss = 1 - np.mean(np.concatenate(pooled_brier)) / np.mean(np.concatenate(pooled_brier_clim))

# Fan chart for one season: re-forecast every 5 days
cand = np.where(matured & (sim["day"] >= 85) & (sim["day"] <= 110))[0]
ex = int(cand[np.argmax(sim["stress"][cand])])
fan = []
for t in range(5, int(sim["day"][ex]), 5):
    r = recs[t - 1]
    prm = {k: v[[ex]] for k, v in WX["params"].items()}
    e = tc.ensemble_forecast(prm, WX["wet"][[ex], t - 1], WX["anom"][[ex], t - 1], r["sm"][[ex]],
                             r["p_q"][[ex]], surrogate, members=200, horizon=SEASON - t, seed=100 + t)[0]
    q = np.quantile(e, [0.1, 0.5, 0.9], method="inverted_cdf")
    pers = float(tc.forecast_days(r["p_mean"][ex], r["s"][ex]))
    fan.append({"issue": t, "q10": t + q[0], "q50": t + q[1], "q90": t + q[2], "p_mature": float(np.isfinite(e).mean()),
                "persistence": t + pers if np.isfinite(pers) and pers > 0 else None,
                "progress": float(r["p_mean"][ex]), "score": float(r["s"][ex])})
fan_series = {"season": ex, "actual_day": int(sim["day"][ex]),
              "progress": [float(r["p_mean"][ex]) for r in recs[:int(sim["day"][ex])]],
              "score": [float(r["s"][ex]) for r in recs[:int(sim["day"][ex])]],
              "rain": WX["rain"][ex, :int(sim["day"][ex])].tolist()}

# Early warning of crop death: first day the twin's score falls below 0.5 before a death
died = np.where(sim["outcome"] == "died")[0]
leads = []
for i in died:
    for r in recs:
        if r["active"][i] and r["s"][i] < 0.5:
            leads.append(int(sim["day"][i] - r["day"]))
            break
out["forecast"] = {"climatology_length": clim_len, "table": rows, "overall_median_ae": overall,
                   "overall_mean_ae": mean_ae, "skill_vs_climatology": skill, "brier_skill": float(bss),
                   "coverage_80": float(np.mean(np.concatenate(pooled_cov))),
                   "n_matured": int(matured.sum()), "n_died": int(len(died)), "death_warning_leads": leads,
                   "outcomes": {k: int((sim["outcome"] == k).sum()) for k in ("matured", "died", "season_end")},
                   "fan": fan, "fan_series": fan_series}
print("Overall median AE", {k: round(v, 1) for k, v in overall.items()}, " mean-AE skill vs climatology",
      {k: round(v, 3) for k, v in skill.items()}, " Brier skill", round(float(bss), 3),
      " 80% coverage", round(100 * out["forecast"]["coverage_80"], 1))
print("Death warning lead times:", sorted(leads), " outcomes:", out["forecast"]["outcomes"],
      " fan season", ex, "matures day", int(sim["day"][ex]))

# =============================================================================
# 3. Response curves at stage 3
# =============================================================================
OPT = {"pH": 6.5, "soil_moisture": 55.0, "sunlight_hours": 8.0, "temperature": 25.0, "humidity": 62.5}
curves = {}
for v in tc.VARS:
    a, b, l, u, _ = tc.PARAMS[v]
    xs = np.linspace(l, u, 61)
    env = {k: np.full(61, OPT[k]) for k in tc.VARS}
    env[v] = xs
    st = np.full(61, 3)
    curves[v] = {"x": xs.tolist(), "target": truth(env, st).tolist(), "surrogate": surrogate(env, st).tolist()}
out["curves"] = curves

json.dump(out, open("outputs/evaluation_v4.json", "w"), default=float)

# Day-by-day trace of the warning-irrigated run
short = {"pH": "pH", "soil_moisture": "SM", "sunlight_hours": "Sun", "temperature": "T", "humidity": "RH"}
print("\nWarning-irrigated run, day by day")
print(f"{'Day':>3} {'Rain':>4} {'Irr':>4} {'T':>3} {'RH':>3} {'ETc':>5} {'SM':>5}  {'Lim':<3} {'phi':>5} {'n':>1} "
      f"{'r':>5} {'pen':>5} {'s':>5} {'s_hat':>5} {'d%':>6} {'p%':>6} {'k':>1} forecast")
for r in case["warning"]["rows"]:
    print(f"{r['day']:>3} {r['rain']:>4.0f} {r['irrigation']:>4.0f} {r['T']:>3.0f} {r['RH']:>3.0f} {r['etc']:>5.2f} "
          f"{r['sm']:>5.1f}  {short[r['limiting']]:<3} {min(r['phi'].values()):>5.3f} {r['n_stressed']:>1} "
          f"{r['r']:>5.3f} {r['c_crit']*r['c_comp']:>5.3f} {r['s_true']:>5.3f} {r['s_hat']:>5.3f} "
          f"{100*r['delta']:>+6.2f} {100*r['p_mean']:>6.2f} {r['stage']:>1} {r['forecast']:>7.1f}")
print("\nSaved outputs/evaluation_v4.json")
