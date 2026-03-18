using UnityEngine;

public class DayNightCycle : MonoBehaviour
{
    [Header("References")]
    public Light sunLight;
    public SimulationClock clock;

    [Header("Sun Settings")]
    public float maxIntensity  = 1.8f;
    public float minIntensity  = 0.05f;

    [Header("Sun Colors")]
    public Color dawnColor    = new Color(1f,   0.5f,  0.2f);
    public Color middayColor  = new Color(1f,   0.98f, 0.9f);
    public Color duskColor    = new Color(1f,   0.4f,  0.1f);
    public Color nightColor   = new Color(0.05f,0.05f, 0.15f);

    [Header("Ambient Colors")]
    public Color dayAmbient   = new Color(0.5f, 0.5f,  0.5f);
    public Color nightAmbient = new Color(0.02f,0.02f, 0.05f);

    private float currentTimeOfDay = 0.3f;  // 0 to 1, starts at morning
    private float targetTimeOfDay  = 0.3f;
    private float smoothedTime     = 0.3f;

    void Start()
    {
        clock.OnDayPassed += OnDayPassed;
        UpdateLighting(currentTimeOfDay);
    }

    void Update()
    {
        // Smoothly advance time of day based on clock day progress
        targetTimeOfDay = clock.dayProgress;

        smoothedTime = Mathf.Lerp(
            smoothedTime,
            targetTimeOfDay,
            Time.deltaTime * 2f
        );

        UpdateLighting(smoothedTime);
    }

    void OnDayPassed()
    {
        // Reset to start of day
        smoothedTime    = 0f;
        currentTimeOfDay = 0f;
    }

    void UpdateLighting(float t)
    {
        // Rotate sun across the sky - full 360 over one day
        // 0 = dawn, 0.25 = midday, 0.5 = dusk, 0.75-1 = night
        float sunAngle = t * 360f - 90f;
        sunLight.transform.rotation = Quaternion.Euler(sunAngle, -30f, 0f);

        // Sun is above horizon between t=0.1 and t=0.9
        bool isDaytime = t > 0.1f && t < 0.9f;

        if (isDaytime)
        {
            // Normalize t to 0-1 within daytime window
            float dayT = (t - 0.1f) / 0.8f;

            // Intensity peaks at midday
            sunLight.intensity = Mathf.Sin(dayT * Mathf.PI) * maxIntensity;
            sunLight.intensity = Mathf.Max(sunLight.intensity, minIntensity);

            // Color shifts dawn -> midday -> dusk
            Color sunColor;
            if (dayT < 0.2f)
            {
                // Dawn
                sunColor = Color.Lerp(dawnColor, middayColor, dayT / 0.2f);
            }
            else if (dayT < 0.8f)
            {
                // Midday
                sunColor = middayColor;
            }
            else
            {
                // Dusk
                sunColor = Color.Lerp(middayColor, duskColor, (dayT - 0.8f) / 0.2f);
            }

            sunLight.color = sunColor;

            // Ambient light follows sun
            RenderSettings.ambientLight = Color.Lerp(
                nightAmbient,
                dayAmbient,
                Mathf.Sin(dayT * Mathf.PI)
            );
        }
        else
        {
            // Night
            sunLight.intensity  = minIntensity;
            sunLight.color      = nightColor;
            RenderSettings.ambientLight = nightAmbient;
        }
    }

    void OnDestroy()
    {
        if (clock != null)
            clock.OnDayPassed -= OnDayPassed;
    }
}