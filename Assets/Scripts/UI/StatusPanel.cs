using UnityEngine;
using TMPro;

/// <summary>
/// Read-only twin status: day, stage, soil water, crop water use, growth score, which model is
/// running, and the forecast with its 90% conformal band. Refreshed every frame from GrowthEngine.
/// </summary>
public class StatusPanel : MonoBehaviour
{
    [Header("References")]
    public GrowthEngine    growthEngine;
    public TextMeshProUGUI statusText;

    [Header("Colours")]
    public Color deathColour = new Color(1f, 0.25f, 0.25f);

    void Update()
    {
        GrowthEngine g = growthEngine;
        int day = g.clock != null ? g.clock.currentDay : 0;

        statusText.text =
            $"Day {day}\n" +
            $"Stage: {GrowthEngine.StageNames[g.currentStage]}\n" +
            $"Soil moisture: {g.soilMoisture:F1}%\n" +
            $"ETc: {g.evapotranspiration:F2} mm/day\n" +
            $"Growth score: {g.currentScore:F3}\n" +
            (g.usingLearnedModel ? "Learned model" : "Analytic fallback") + "\n" +
            ForecastLine(g, day);
    }

    string ForecastLine(GrowthEngine g, int day)
    {
        if (day == 0)
            return "Forecast after the first day";

        if (g.averageProgress >= GrowthEngine.MATURE_AT)
            return "Crop has matured";

        if (g.forecastIsDeath)
        {
            string hex = ColorUtility.ToHtmlStringRGB(deathColour);
            return $"<color=#{hex}>Crop death in {g.forecastDays:F0} days</color>";
        }

        if (float.IsInfinity(g.forecastDays))
            return "No net growth under current conditions";

        // The analytic fallback has no conformal interval, so there is no band to show
        if (!g.usingLearnedModel)
            return $"Maturity in {g.forecastDays:F0} days";

        string high = float.IsInfinity(g.forecastHigh) ? "never" : g.forecastHigh.ToString("F0");
        return $"Maturity in {g.forecastDays:F0} days (90%: {g.forecastLow:F0} to {high})";
    }
}
