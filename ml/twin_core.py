"""
Plant-growth digital twin, core model (v4)
==========================================
Shared by train_model.py and evaluate_twin.py. Pure numpy, vectorised over seasons.

Daily process
  1. Soil water balance (FAO-56 style bucket): rain and irrigation add water, crop
     evapotranspiration removes it, water above field capacity drains.
  2. Growth response: soil moisture, pH, sunlight, temperature and humidity are scored
     against cardinal ranges and combined into a daily growth score s in [0, 1].
     Rainfall acts only through soil moisture (no double counting).
  3. Crop progress: each of 144 plants gains or loses progress depending on s.
"""

import numpy as np

# =============================================================================
# 1. Growth response function f(x, k)
# =============================================================================

#                     opt_min opt_max hard_min hard_max weight
PARAMS = {
    "pH":             (6.0,   7.0,    3.5,     9.5,     1.0),
    "soil_moisture":  (40.0,  70.0,   5.0,     100.0,   1.4),
    "sunlight_hours": (6.0,   10.0,   0.0,     16.0,    1.2),
    "temperature":    (20.0,  30.0,   0.0,     45.0,    1.4),
    "humidity":       (50.0,  75.0,   10.0,    100.0,   0.9),
}
VARS = list(PARAMS)
W_SUM = sum(p[4] for p in PARAMS.values())               # 5.9
STAGE_NAMES = ["Seed", "Germination", "Sprout", "Seedling", "Vegetative", "Flowering", "Mature"]
SIGMA = np.array([1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4])    # stress sensitivity per stage
CRITICAL, STRESSED = 0.2, 0.5


def bell(x, a, b, l, u):
    """Continuous single-factor score: 1 at band centre, 0.85 at band edges, 0 at hard limits."""
    x = np.asarray(x, dtype=float)
    m, h = (a + b) / 2, (b - a) / 2
    inside = 0.85 + 0.15 * (1 - np.abs(x - m) / h)
    d = np.where(x < a, (a - x) / (a - l), (x - b) / (u - b))
    outside = 0.85 * (1 - np.clip(d, 0, 1) ** 1.8)
    s = np.where((x >= a) & (x <= b), inside, outside)
    return np.where((x <= l) | (x >= u), 0.0, s)


def growth_score(env, stage, detail=False):
    """env: dict of arrays (or scalars) for VARS. stage: int array 0..6. Returns s in [0, 1]."""
    phi = {k: bell(env[k], *PARAMS[k][:4]) for k in VARS}
    r = sum(PARAMS[k][4] * phi[k] for k in VARS) / W_SUM
    phis = np.stack([phi[k] for k in VARS])
    phi_min = phis.min(axis=0)
    c_crit = np.where(phi_min < CRITICAL, 0.5 * (phi_min / CRITICAL) ** 1.5, 1.0)
    n_s = (phis < STRESSED).sum(axis=0)
    c_comp = np.where(n_s >= 2, 0.6 ** (n_s - 1.0), 1.0)
    gamma = 1.0 + 0.8 * SIGMA[np.asarray(stage, dtype=int)]
    s = np.clip((r * c_crit * c_comp) ** gamma, 0.0, 1.0)
    if detail:
        lim = np.array(VARS)[phis.argmin(axis=0)]
        return s, dict(phi=phi, r=r, c_crit=c_crit, c_comp=c_comp, n_stressed=n_s,
                       gamma=gamma, limiting=lim)
    return s


# =============================================================================
# 2. Features for the learned surrogate
# =============================================================================

RAW_FEATURES = VARS + ["growth_stage"]
ENG_FEATURES = [f"{v}_{side}" for v in VARS for side in ("low", "high")] + ["growth_stage"]


def engineered(X_raw):
    """Cardinal-point deviations: for each variable, how far it lies below / above the
    centre of its optimal band, normalised by the distance to the hard limit on that side.
    Uses only the band centre m and hard limits l, u, not the response shape."""
    X_raw = np.asarray(X_raw, dtype=float)
    cols = []
    for j, v in enumerate(VARS):
        a, b, l, u, _ = PARAMS[v]
        m = (a + b) / 2
        x = X_raw[:, j]
        cols.append(np.clip((m - x) / (m - l), 0, None))
        cols.append(np.clip((x - m) / (u - m), 0, None))
    cols.append(X_raw[:, -1])
    return np.column_stack(cols)


# Monotonic constraints for the engineered features: further from the centre can never help,
# a more mature crop is never more sensitive to stress.
MONOTONIC = [-1] * (2 * len(VARS)) + [1]


# =============================================================================
# 3. Soil water balance (FAO-56 inspired)
# =============================================================================

FC, WP = 70.0, 5.0            # field capacity and wilting point, % of saturation
P_DEPLETION = 0.40            # FAO-56 depletion fraction for tomato
SM_P = FC - P_DEPLETION * (FC - WP)     # 44%: below this, transpiration is reduced
MM_PER_PCT = 1.35             # mm of water per 1% saturation (0.45 porosity x 0.30 m root zone)
DRAIN_RATE = 0.5              # fraction of water above field capacity that drains per day
RA, N_DAYLIGHT = 35.0, 12.0   # extraterrestrial radiation (MJ m-2 d-1), daylength (h)
KC = np.array([0.60, 0.60, 0.75, 0.90, 1.15, 1.15, 0.80])   # FAO-56 tomato Kc by stage


def et0_turc(T, RH, n):
    """Reference evapotranspiration (mm/day), Turc (1961) with Angstrom radiation."""
    T = np.maximum(np.asarray(T, dtype=float), 0.1)
    Rs = (0.25 + 0.5 * np.minimum(n, N_DAYLIGHT) / N_DAYLIGHT) * RA
    c_rh = np.where(RH < 50, 1 + (50 - RH) / 70, 1.0)
    return 0.013 * T / (T + 15) * (23.8856 * Rs + 50) * c_rh


def water_step(sm, rain, irrigation, T, RH, n, stage):
    """Advance soil moisture (% of saturation) by one day. Returns new sm and the fluxes."""
    ks = np.clip((sm - WP) / (SM_P - WP), 0, 1)
    et0 = et0_turc(T, RH, n)
    etc = KC[np.asarray(stage, dtype=int)] * et0 * ks
    w = sm * MM_PER_PCT + rain + irrigation - etc
    w_fc = FC * MM_PER_PCT
    drain = np.where(w > w_fc, DRAIN_RATE * (w - w_fc), 0.0)
    w = np.clip(w - drain, 0, 100 * MM_PER_PCT)
    return w / MM_PER_PCT, dict(et0=et0, etc=etc, ks=ks, drain=drain)


# =============================================================================
# 4. Crop dynamics
# =============================================================================

MATURE_AT = 0.98


def delta(s):
    s = np.asarray(s, dtype=float)
    return np.where(s >= 0.5, 0.04 * (s - 0.5), -0.03 * (0.5 - s))


def forecast_days(p_mean, s):
    """Days to maturity (positive) or to death (negative) if today's score persists."""
    d = delta(s)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(d > 0, (MATURE_AT - p_mean) / d, np.where(d < 0, -p_mean / -d, np.inf))


# =============================================================================
# 5. Weather
# =============================================================================

def climate_params(n, seed=0):
    """Each season (site) draws its own climate. These are the 'known climatology' used both to
    generate the weather that happens and to generate the ensemble of possible futures."""
    rng = np.random.default_rng(seed)
    return {"p_wd": rng.uniform(0.05, 0.45, n),       # P(wet | dry yesterday)
            "p_ww": rng.uniform(0.30, 0.80, n),       # P(wet | wet yesterday)
            "mean_amt": rng.uniform(3, 20, n),        # mean rain on wet days, mm
            "t_mean": rng.uniform(20, 37, n),         # mean temperature, C
            "rh_dry": rng.uniform(25, 65, n),         # humidity on dry days, %
            "ph": rng.uniform(5.2, 7.6, n)}           # soil pH of the field


def generate_weather(params, n_days, rng, wet0=None, anom0=None):
    """Daily weather in the spirit of Richardson (1981): first-order Markov rain occurrence with
    exponential amounts, AR(1) temperature anomaly, and humidity and sunshine that depend on
    whether the day is wet. Returns (S, n_days) arrays plus the wet flags and anomalies."""
    S = len(params["p_wd"])
    wet = np.zeros(S, bool) if wet0 is None else np.asarray(wet0, bool).copy()
    anom = np.zeros(S) if anom0 is None else np.asarray(anom0, float).copy()
    out = {k: np.zeros((S, n_days)) for k in ("rain", "temperature", "humidity", "sunlight_hours")}
    out["wet"] = np.zeros((S, n_days), bool)
    out["anom"] = np.zeros((S, n_days))
    for t in range(n_days):
        wet = rng.random(S) < np.where(wet, params["p_ww"], params["p_wd"])
        anom = 0.7 * anom + rng.normal(0, 1.2, S)
        out["rain"][:, t] = np.where(wet, rng.exponential(params["mean_amt"]), 0.0)
        out["temperature"][:, t] = params["t_mean"] + anom - 1.5 * wet
        out["humidity"][:, t] = np.clip(np.where(wet, params["rh_dry"] + 25, params["rh_dry"])
                                        + rng.normal(0, 4, S), 15, 98)
        out["sunlight_hours"][:, t] = np.clip(np.where(wet, 4.0, 9.0) + rng.normal(0, 1.2, S), 0.5, 12)
        out["wet"][:, t], out["anom"][:, t] = wet, anom
    out["pH"] = np.repeat(np.asarray(params["ph"])[:, None], n_days, axis=1)
    return out


def weather_generator(n_seasons, n_days=120, seed=0):
    params = climate_params(n_seasons, seed)
    wx = generate_weather(params, n_days, np.random.default_rng(seed + 1000))
    wx["params"] = params
    return wx


REP_OFFSETS = np.linspace(-0.05, 0.05, 10)[:-1] + 0.1 / 18     # 9 plants at the offset deciles


def ensemble_forecast(params, wet0, anom0, sm0, p0, score_fn, members=30, horizon=150, seed=0):
    """Probabilistic time-to-maturity forecast. For each of F crops (current soil moisture sm0,
    field progress p0 as (F,) means or (F, 9) plant quantiles, site climate params), simulate `members` weather futures with the twin and
    return days to maturity per member (np.inf if not within the horizon or the crop dies).
    The field is represented by 9 plants spanning the offset distribution, so that the field
    mean reaches maturity as slowly as the real 144-plant field does."""
    F = len(p0)
    rep = lambda a: np.repeat(np.asarray(a), members)
    prm = {k: rep(v) for k, v in params.items()}
    wx = generate_weather(prm, horizon, np.random.default_rng(seed), rep(wet0), rep(anom0))
    sm = rep(sm0).astype(float)
    p0 = np.asarray(p0, float)
    p = np.repeat(p0, members, axis=0) if p0.ndim == 2 else np.repeat(p0, members)[:, None] * np.ones(9)
    peak = p.mean(axis=1)
    days = np.full(F * members, np.inf)
    live = np.ones(F * members, bool)
    for t in range(horizon):
        if not live.any():
            break
        stage = np.minimum(6, np.floor(7 * p.mean(axis=1))).astype(int)
        sm, _ = water_step(sm, wx["rain"][:, t], 0.0, wx["temperature"][:, t], wx["humidity"][:, t],
                           wx["sunlight_hours"][:, t], stage)
        env = {"pH": prm["ph"], "soil_moisture": sm, "sunlight_hours": wx["sunlight_hours"][:, t],
               "temperature": wx["temperature"][:, t], "humidity": wx["humidity"][:, t]}
        s = np.full(F * members, 0.5)
        s[live] = score_fn({k: v[live] for k, v in env.items()}, stage[live])
        step = delta(np.clip(s[:, None] + REP_OFFSETS[None, :], 0, 1))
        p = np.where(live[:, None], np.clip(p + step, 0, 1), p)
        pm = p.mean(axis=1)
        peak = np.maximum(peak, pm)
        hit = live & (pm >= MATURE_AT)
        days[hit] = t + 1
        live &= ~hit & ~((peak > 0.05) & (pm <= 0.001))
    return days.reshape(F, members)


# =============================================================================
# 6. Season simulation (vectorised over seasons)
# =============================================================================

def simulate(weather, score_fn, irrigation=None, sm0=55.0, n_plants=144, offset=0.05, seed=0,
             max_days=None, record=False):
    """weather: dict of (S, D) arrays (rain, temperature, humidity, sunlight_hours, pH).
    score_fn(env_dict, stage_array) -> scores (S,). irrigation: (S, D) mm or None.
    Returns per-season outcome, maturity day, stress days and optional daily records."""
    S, D = weather["rain"].shape
    D = D if max_days is None else min(D, max_days)
    eps = np.random.default_rng(seed).uniform(-offset, offset, n_plants)
    p = np.zeros((S, n_plants))
    sm = np.full(S, float(sm0))
    peak = np.zeros(S)
    alive = np.ones(S, bool)
    done_day = np.full(S, -1)
    outcome = np.array(["season_end"] * S, dtype=object)
    stress = np.zeros(S, int)
    rec = []
    for t in range(D):
        stage = np.minimum(6, np.floor(7 * p.mean(axis=1))).astype(int)
        irr = 0.0 if irrigation is None else irrigation[:, t]
        sm, flux = water_step(sm, weather["rain"][:, t], irr, weather["temperature"][:, t],
                              weather["humidity"][:, t], weather["sunlight_hours"][:, t], stage)
        env = {"pH": weather["pH"][:, t], "soil_moisture": sm,
               "sunlight_hours": weather["sunlight_hours"][:, t],
               "temperature": weather["temperature"][:, t], "humidity": weather["humidity"][:, t]}
        s = score_fn(env, stage)
        active = alive & (done_day < 0)
        step = delta(np.clip(s[:, None] + eps[None, :], 0, 1))
        p = np.where(active[:, None], np.clip(p + step, 0, 1), p)
        pm = p.mean(axis=1)
        peak = np.maximum(peak, pm)
        stress += (active & (s < 0.5)).astype(int)
        matured = active & (pm >= MATURE_AT)
        died = active & (peak > 0.05) & (pm <= 0.001)
        done_day = np.where(matured | died, t + 1, done_day)
        outcome = np.where(matured, "matured", np.where(died, "died", outcome))
        alive &= ~died
        if record:
            rec.append(dict(day=t + 1, sm=sm.copy(), s=np.asarray(s).copy(), stage=stage, p_mean=pm.copy(),
                            p_q=np.quantile(p, (np.arange(9) + 0.5) / 9, axis=1).T,
                            p_min=p.min(axis=1), p_max=p.max(axis=1), etc=flux["etc"], et0=flux["et0"],
                            ks=flux["ks"], drain=flux["drain"], env={k: np.asarray(v).copy() for k, v in env.items()},
                            active=active))
        if (done_day >= 0).all():
            break
    return dict(outcome=outcome, day=done_day, stress=stress, final_progress=p.mean(axis=1), records=rec)
