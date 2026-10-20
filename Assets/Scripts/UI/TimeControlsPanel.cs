using UnityEngine;
using UnityEngine.UI;
using TMPro;

public class TimeControlsPanel : MonoBehaviour
{
    [Header("References")]
    public SimulationClock clock;

    [Header("UI Elements")]
    public Button          pauseButton;
    public Slider          speedSlider;
    public Button          resetButton;
    public TextMeshProUGUI dayCounter;
    public TextMeshProUGUI pauseButtonText;

    private bool isPaused = false;

    void Start()
    {
        speedSlider.minValue = 0.5f;
        speedSlider.maxValue = 20f;
        speedSlider.value    = 1f;

        pauseButton.onClick.AddListener(OnPauseClicked);
        resetButton.onClick.AddListener(OnResetClicked);
        speedSlider.onValueChanged.AddListener(OnSpeedChanged);

        clock.OnDayPassed += UpdateDayCounter;
    }

    void OnPauseClicked()
    {
        isPaused = !isPaused;

        if (isPaused)
        {
            clock.Pause();
            pauseButtonText.text = "Resume";
        }
        else
        {
            clock.Resume();
            pauseButtonText.text = "Pause";
        }
    }

    void OnSpeedChanged(float value)
    {
        clock.SetSpeed(value);
    }

    void OnResetClicked()
    {
        clock.Reset();
        isPaused             = false;
        pauseButtonText.text = "Pause";
        dayCounter.text      = "Day 0";

        // Reset all plants
        FarmGrid farmGrid = FindFirstObjectByType<FarmGrid>();
        if (farmGrid != null)
        {
            foreach (Plant plant in farmGrid.GetAllPlants())
                if (plant != null) plant.ResetGrowth();
        }

        // Reset soil moisture and the forecast
        GrowthEngine growthEngine = FindFirstObjectByType<GrowthEngine>();
        if (growthEngine != null)
            growthEngine.ResetState();
    }

    void UpdateDayCounter()
    {
        dayCounter.text = $"Day {clock.currentDay}";
    }

    void OnDestroy()
    {
        if (clock != null)
            clock.OnDayPassed -= UpdateDayCounter;
    }
}