using UnityEngine;

public class GrowthEngine : MonoBehaviour
{
    [Header("References")]
    public SimulationClock clock;
    public FarmGrid        farmGrid;

    [Header("Environment Inputs")]
    [Range(3.5f, 9.5f)]  public float pH             = 6.5f;
    [Range(5f, 100f)]    public float soilMoisture   = 55f;
    [Range(0f, 16f)]     public float sunlightHours  = 8f;
    [Range(0f, 45f)]     public float temperature    = 25f;
    [Range(10f, 100f)]   public float humidity       = 62f;
    [Range(0f, 120f)]    public float rainfall       = 40f;

    [Header("Read Only")]
    public float currentScore     = 0f;
    public float growthRatePerDay = 0f;
    public int   currentStage     = 0;

    private Plant[] allPlants;

    void Start()
{
    clock.OnDayPassed += OnDayPassed;
}

    void Update()
    {
        // Wait until plants are spawned before grabbing the array
        if (allPlants == null || allPlants.Length == 0)
        {
            allPlants = farmGrid.GetAllPlants();
        }
    }

    void OnDayPassed()
    {
        // Get score from placeholder model (swap with ONNX later)
        currentScore = PlaceholderModel(
            pH, soilMoisture, sunlightHours,
            temperature, humidity, rainfall, currentStage
        );

        // Calculate growth rate for UI display
        if (currentScore >= 0.5f)
            growthRatePerDay =  (currentScore - 0.5f) * 2f * 2f;
        else
            growthRatePerDay = -(0.5f - currentScore) * 2f * 1.5f;

        // Update all plants
        foreach (Plant plant in allPlants)
        {
            if (plant != null)
                plant.UpdateGrowth(currentScore);
        }

        // Update current stage based on average growth
        if (allPlants.Length > 0)
        {
            float avgProgress = 0f;
            foreach (Plant plant in allPlants)
                if (plant != null) avgProgress += plant.growthProgress;
            avgProgress /= allPlants.Length;
            currentStage = Mathf.Clamp(Mathf.FloorToInt(avgProgress * 7), 0, 6);
        }
    }

    float PlaceholderModel(float pH, float moisture, float sunlight,
                           float temp, float humidity, float rainfall, int stage)
    {
        // Mimics the Python bell curve scoring
        // Replace this entire method with ONNX inference later

        float pHScore       = BellScore(pH,       6.0f, 7.0f,  3.5f, 9.5f);
        float moistureScore = BellScore(moisture, 40f,  70f,   5f,   100f);
        float sunScore      = BellScore(sunlight, 6f,   10f,   0f,   16f);
        float tempScore     = BellScore(temp,     20f,  30f,   0f,   45f);
        float humidScore    = BellScore(humidity, 50f,  75f,   10f,  100f);
        float rainScore     = BellScore(rainfall, 20f,  60f,   0f,   120f);

        float raw = (pHScore       * 1.0f +
                     moistureScore * 1.4f +
                     sunScore      * 1.2f +
                     tempScore     * 1.4f +
                     humidScore    * 0.9f +
                     rainScore     * 1.1f) / 7.0f;

        // Critical failure penalty
        float minScore = Mathf.Min(pHScore,
                         Mathf.Min(moistureScore,
                         Mathf.Min(sunScore,
                         Mathf.Min(tempScore,
                         Mathf.Min(humidScore, rainScore)))));

        if (minScore < 0.2f)
            raw = raw * Mathf.Pow(minScore / 0.2f, 1.5f) * 0.5f;

        raw = Mathf.Clamp01(raw);

        // Map to 0-1 growth score
        if (raw < 0.5f)
            return (raw / 0.5f) * 0.5f;
        else
            return 0.5f + ((raw - 0.5f) / 0.5f) * 0.5f;
    }

    float BellScore(float value, float optMin, float optMax,
                    float hardMin, float hardMax)
    {
        if (value <= hardMin || value >= hardMax) return 0f;

        if (value >= optMin && value <= optMax)
        {
            float optMid  = (optMin + optMax) / 2f;
            float optHalf = (optMax - optMin) / 2f;
            float dev     = Mathf.Abs(value - optMid) / (optHalf + 1e-6f);
            return 0.85f + 0.15f * (1f - dev);
        }

        if (value < optMin)
        {
            float dist = (optMin - value) / (optMin - hardMin + 1e-6f);
            return Mathf.Clamp01(1f - Mathf.Pow(dist, 1.8f));
        }

        float distR = (value - optMax) / (hardMax - optMax + 1e-6f);
        return Mathf.Clamp01(1f - Mathf.Pow(distR, 1.8f));
    }

    void OnDestroy()
    {
        if (clock != null)
            clock.OnDayPassed -= OnDayPassed;
    }
}