using UnityEngine;

/// <summary>
/// Runs once per simulated day:
///   1. Soil water balance: rain and irrigation add water, crop evapotranspiration removes it,
///      water above field capacity drains (same equations as twin_core.py).
///   2. Growth score from the trained surrogate (GrowthModel), or the analytic response
///      function if no model file is assigned.
///   3. Every plant updates its progress; the twin computes a forecast with a 90% band.
/// </summary>
public class GrowthEngine : MonoBehaviour
{
    [Header("References")]
    public SimulationClock clock;
    public FarmGrid        farmGrid;
    public SlidersPanel    slidersPanel;           // optional: shows soil moisture as it changes
    [Tooltip("Assets/MLModels/growth_model.json from train_model.py")]
    public TextAsset       modelJson;

    [Header("Environment (set by the sliders)")]
    [Range(3.5f, 9.5f)] public float pH            = 6.5f;
    [Range(5f, 100f)]   public float soilMoisture  = 55f;   // state: updated every day by the water balance
    [Range(0f, 16f)]    public float sunlightHours = 8f;
    [Range(0f, 45f)]    public float temperature   = 25f;
    [Range(10f, 100f)]  public float humidity      = 62f;
    [Range(0f, 120f)]   public float rainfall      = 3f;    // mm/day
    [Range(0f, 60f)]    public float irrigation    = 0f;    // mm/day, applied every day while set

    [Header("Read only")]
    public float currentScore     = 0f;
    public float growthRatePerDay = 0f;    // % progress per day
    public int   currentStage     = 0;
    public float averageProgress  = 0f;    // 0 to 1
    public float evapotranspiration = 0f;  // ETc, mm/day
    public float forecastDays     = 0f;    // days to maturity, or to death if forecastIsDeath
    public float forecastLow      = 0f;    // 90% band from the conformal interval
    public float forecastHigh     = 0f;
    public bool  forecastIsDeath  = false;
    public bool  usingLearnedModel = false;

    // Water balance (FAO-56 inspired), identical to twin_core.py
    const float FC = 70f, WP = 5f, P_DEPLETION = 0.40f;
    const float MM_PER_PCT = 1.35f, DRAIN_RATE = 0.5f, RA = 35f, N_DAYLIGHT = 12f, MATURE_AT = 0.98f;
    static readonly float SM_P = FC - P_DEPLETION * (FC - WP);
    static readonly float[] KC = { 0.60f, 0.60f, 0.75f, 0.90f, 1.15f, 1.15f, 0.80f };

    // Analytic response function, identical to twin_core.growth_score
    static readonly float[,] P = {
        // opt_min, opt_max, hard_min, hard_max, weight
        { 6.0f,  7.0f,  3.5f,  9.5f,   1.0f },   // pH
        { 40f,   70f,   5f,    100f,   1.4f },   // soil moisture
        { 6f,    10f,   0f,    16f,    1.2f },   // sunlight
        { 20f,   30f,   0f,    45f,    1.4f },   // temperature
        { 50f,   75f,   10f,   100f,   0.9f },   // humidity
    };
    static readonly float[] SIGMA = { 1.0f, 0.9f, 0.8f, 0.7f, 0.6f, 0.5f, 0.4f };

    private GrowthModel model;
    private Plant[] allPlants;

    void Awake()
    {
        if (modelJson != null)
        {
            try
            {
                model = GrowthModel.Load(modelJson.text);
                usingLearnedModel = true;
                Debug.Log($"GrowthEngine: loaded learned model ({model.TreeCount} trees).");
            }
            catch (System.Exception e)
            {
                Debug.LogWarning($"GrowthEngine: could not load model, using analytic function. {e.Message}");
            }
        }
        else
        {
            Debug.LogWarning("GrowthEngine: no model JSON assigned, using analytic response function.");
        }
    }

    void Start()
    {
        clock.OnDayPassed += OnDayPassed;
    }

    void Update()
    {
        if (allPlants == null || allPlants.Length == 0)
            allPlants = farmGrid.GetAllPlants();
    }

    void OnDayPassed()
    {
        if (allPlants == null || allPlants.Length == 0)
            allPlants = farmGrid.GetAllPlants();
        if (allPlants == null) return;

        // 1. Water balance (uses the stage at the start of the day)
        soilMoisture = WaterStep(soilMoisture, rainfall, irrigation, temperature, humidity,
                                 sunlightHours, currentStage, out evapotranspiration);
        if (slidersPanel != null) slidersPanel.ShowSoilMoisture(soilMoisture);

        // 2. Growth score
        currentScore     = PredictScore(pH, soilMoisture, sunlightHours, temperature, humidity, currentStage);
        growthRatePerDay = 100f * Delta(currentScore);

        // 3. Plants
        float sum = 0f; int n = 0;
        foreach (Plant plant in allPlants)
        {
            if (plant == null) continue;
            plant.UpdateGrowth(currentScore);
            sum += plant.growthProgress; n++;
        }
        averageProgress = n > 0 ? sum / n : 0f;
        currentStage = Mathf.Clamp(Mathf.FloorToInt(averageProgress * 7f), 0, 6);

        // 4. Forecast if today's conditions persist, with the conformal band
        float q = usingLearnedModel ? model.ConformalQ90 : 0f;
        forecastDays    = Forecast(averageProgress, currentScore, out forecastIsDeath);
        forecastLow     = Forecast(averageProgress, Mathf.Clamp01(currentScore + q), out _);
        forecastHigh    = Forecast(averageProgress, Mathf.Clamp01(currentScore - q), out _);
    }

    // ------------------------------------------------------------------ model

    public float PredictScore(float ph, float moisture, float sunlight, float temp, float rh, int stage)
    {
        if (usingLearnedModel)
            return model.Predict(ph, moisture, sunlight, temp, rh, stage);
        return AnalyticScore(ph, moisture, sunlight, temp, rh, stage);
    }

    /// <summary>Kept for SimulationServer and older scripts. Rainfall now acts through soil moisture.</summary>
    public float PlaceholderModel(float ph, float moisture, float sunlight, float temp,
                                  float rh, float rain, int stage)
    {
        return PredictScore(ph, moisture, sunlight, temp, rh, stage);
    }

    public static float AnalyticScore(float ph, float moisture, float sunlight, float temp, float rh, int stage)
    {
        float[] x = { ph, moisture, sunlight, temp, rh };
        float weighted = 0f, weights = 0f, phiMin = 1f;
        int stressed = 0;
        for (int j = 0; j < 5; j++)
        {
            float phi = Bell(x[j], P[j, 0], P[j, 1], P[j, 2], P[j, 3]);
            weighted += P[j, 4] * phi;
            weights  += P[j, 4];
            phiMin    = Mathf.Min(phiMin, phi);
            if (phi < 0.5f) stressed++;
        }
        float r     = weighted / weights;
        float cCrit = phiMin < 0.2f ? 0.5f * Mathf.Pow(phiMin / 0.2f, 1.5f) : 1f;
        float cComp = stressed >= 2 ? Mathf.Pow(0.6f, stressed - 1) : 1f;
        float gamma = 1f + 0.8f * SIGMA[Mathf.Clamp(stage, 0, 6)];
        return Mathf.Clamp01(Mathf.Pow(r * cCrit * cComp, gamma));
    }

    static float Bell(float x, float a, float b, float l, float u)
    {
        if (x <= l || x >= u) return 0f;
        if (x >= a && x <= b)
        {
            float m = (a + b) / 2f, h = (b - a) / 2f;
            return 0.85f + 0.15f * (1f - Mathf.Abs(x - m) / h);
        }
        float d = x < a ? (a - x) / (a - l) : (x - b) / (u - b);
        return 0.85f * (1f - Mathf.Pow(Mathf.Clamp01(d), 1.8f));
    }

    // ------------------------------------------------------------------ water balance

    public static float Et0Turc(float temp, float rh, float sunlight)
    {
        float t  = Mathf.Max(temp, 0.1f);
        float rs = (0.25f + 0.5f * Mathf.Min(sunlight, N_DAYLIGHT) / N_DAYLIGHT) * RA;
        float cRh = rh < 50f ? 1f + (50f - rh) / 70f : 1f;
        return 0.013f * t / (t + 15f) * (23.8856f * rs + 50f) * cRh;
    }

    public static float WaterStep(float sm, float rain, float irr, float temp, float rh, float sunlight,
                                  int stage, out float etc)
    {
        float ks = Mathf.Clamp01((sm - WP) / (SM_P - WP));
        etc = KC[Mathf.Clamp(stage, 0, 6)] * Et0Turc(temp, rh, sunlight) * ks;
        float w   = sm * MM_PER_PCT + rain + irr - etc;
        float wFc = FC * MM_PER_PCT;
        if (w > wFc) w -= DRAIN_RATE * (w - wFc);
        w = Mathf.Clamp(w, 0f, 100f * MM_PER_PCT);
        return w / MM_PER_PCT;
    }

    // ------------------------------------------------------------------ dynamics

    public static float Delta(float s)
    {
        return s >= 0.5f ? 0.04f * (s - 0.5f) : -0.03f * (0.5f - s);
    }

    static float Forecast(float progress, float score, out bool death)
    {
        float d = Delta(score);
        death = d < 0f;
        if (d > 0f)  return (MATURE_AT - progress) / d;
        if (d < 0f)  return progress / -d;
        return float.PositiveInfinity;
    }

    void OnDestroy()
    {
        if (clock != null)
            clock.OnDayPassed -= OnDayPassed;
    }
}
