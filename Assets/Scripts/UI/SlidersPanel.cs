using UnityEngine;
using UnityEngine.UI;
using TMPro;

/// <summary>
/// Environment controls. Soil moisture is now a state that the water balance changes every day:
/// the slider follows it automatically, and dragging it irrigates or drains the field to that level.
/// Rainfall is a weather input in mm/day that feeds the soil.
/// </summary>
public class SlidersPanel : MonoBehaviour
{
    [Header("References")]
    public GrowthEngine growthEngine;

    [Header("Sliders")]
    public Slider pHSlider;
    public Slider moistureSlider;
    public Slider sunlightSlider;
    public Slider temperatureSlider;
    public Slider humiditySlider;
    public Slider rainfallSlider;

    [Header("Value Labels")]
    public TextMeshProUGUI pHLabel;
    public TextMeshProUGUI moistureLabel;
    public TextMeshProUGUI sunlightLabel;
    public TextMeshProUGUI temperatureLabel;
    public TextMeshProUGUI humidityLabel;
    public TextMeshProUGUI rainfallLabel;

    private bool initialised = false;

    void Awake()
    {
        Initialise();
    }

    void Initialise()
    {
        if (initialised) return;
        initialised = true;

        pHSlider.minValue          = 3.5f;  pHSlider.maxValue          = 9.5f;
        moistureSlider.minValue    = 5f;    moistureSlider.maxValue    = 100f;
        sunlightSlider.minValue    = 0f;    sunlightSlider.maxValue    = 16f;
        temperatureSlider.minValue = 0f;    temperatureSlider.maxValue = 45f;
        humiditySlider.minValue    = 10f;   humiditySlider.maxValue    = 100f;
        rainfallSlider.minValue    = 0f;    rainfallSlider.maxValue    = 120f;

        pHSlider.value          = 6.5f;
        moistureSlider.value    = 55f;
        sunlightSlider.value    = 8f;
        temperatureSlider.value = 25f;
        humiditySlider.value    = 62f;
        rainfallSlider.value    = 3f;

        pHSlider.onValueChanged.AddListener(v          => OnSliderChanged());
        moistureSlider.onValueChanged.AddListener(v    => OnSliderChanged());
        sunlightSlider.onValueChanged.AddListener(v    => OnSliderChanged());
        temperatureSlider.onValueChanged.AddListener(v => OnSliderChanged());
        humiditySlider.onValueChanged.AddListener(v    => OnSliderChanged());
        rainfallSlider.onValueChanged.AddListener(v    => OnSliderChanged());

        OnSliderChanged();
    }

    /// <summary>Sets a parameter by its API name (used by SimulationServer).</summary>
    public bool SetParameter(string name, float value)
    {
        Initialise();
        Slider s = name switch
        {
            "ph"             => pHSlider,
            "soil_moisture"  => moistureSlider,
            "sunlight_hours" => sunlightSlider,
            "temperature"    => temperatureSlider,
            "humidity"       => humiditySlider,
            "rainfall"       => rainfallSlider,
            _                => null
        };
        if (s == null) return false;
        s.value = value;
        OnSliderChanged();
        return true;
    }

    /// <summary>Called by GrowthEngine after the daily water balance; moves the slider without
    /// treating it as a user change.</summary>
    public void ShowSoilMoisture(float value)
    {
        moistureSlider.SetValueWithoutNotify(value);
        UpdateLabels();
    }

    void OnSliderChanged()
    {
        growthEngine.pH            = pHSlider.value;
        growthEngine.soilMoisture  = moistureSlider.value;   // dragging = irrigate or drain to this level
        growthEngine.sunlightHours = sunlightSlider.value;
        growthEngine.temperature   = temperatureSlider.value;
        growthEngine.humidity      = humiditySlider.value;
        growthEngine.rainfall      = rainfallSlider.value;
        UpdateLabels();
    }

    void UpdateLabels()
    {
        pHLabel.text          = $"pH: {pHSlider.value:F1}";
        moistureLabel.text    = $"Soil moisture: {moistureSlider.value:F0}%";
        sunlightLabel.text    = $"Sunlight: {sunlightSlider.value:F1} hrs";
        temperatureLabel.text = $"Temp: {temperatureSlider.value:F0} C";
        humidityLabel.text    = $"Humidity: {humiditySlider.value:F0}%";
        rainfallLabel.text    = $"Rainfall: {rainfallSlider.value:F0} mm/day";
    }
}
