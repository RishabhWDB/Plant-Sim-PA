using System;
using System.Globalization;
using System.IO;
using UnityEngine;
using UnityEngine.InputSystem;

/// <summary>
/// Frame-time measurement for the paper. Press P: after a warm-up it records a fixed number of
/// frames, logs median and p95 frame time and median FPS, and appends a row to
/// Application.persistentDataPath/perf.csv. At startup it also appends the model load time.
/// </summary>
public class PerfRecorder : MonoBehaviour
{
    [Header("References")]
    public GrowthEngine    growthEngine;
    public FarmGrid        farmGrid;
    public SimulationClock clock;

    [Header("Recording")]
    public float warmupSeconds  = 5f;
    public int   framesToRecord = 300;
    [Tooltip("Turn off VSync and the frame cap so FPS is not limited to the display refresh rate")]
    public bool  uncapFrameRate = true;

    const string Header = "timestamp,kind,plants,sim_speed,median_ms,p95_ms,median_fps,model_load_ms," +
                          "learned_model,device_model,processor,gpu,resolution,vsync,build";

    private float[] frameTimes;
    private int     recorded  = 0;
    private float   warmupLeft = 0f;
    private bool    warmingUp = false;
    private bool    recording = false;

    string CsvPath => Path.Combine(Application.persistentDataPath, "perf.csv");

    void Awake()
    {
        if (uncapFrameRate)
        {
            QualitySettings.vSyncCount  = 0;
            Application.targetFrameRate = -1;
        }
    }

    void Start()
    {
        // GrowthEngine loads the model in Awake, so the load time is known here
        if (growthEngine != null)
        {
            AppendRow("model_load", "", "", "", "", "", growthEngine.modelLoadMs.ToString("F1", CultureInfo.InvariantCulture));
            Debug.Log($"PerfRecorder: model load {growthEngine.modelLoadMs:F1} ms written to {CsvPath}");
        }
    }

    void Update()
    {
        if (!warmingUp && !recording && Keyboard.current != null && Keyboard.current.pKey.wasPressedThisFrame)
        {
            warmingUp  = true;
            warmupLeft = warmupSeconds;
            Debug.Log($"PerfRecorder: warming up for {warmupSeconds:F0} s, then recording {framesToRecord} frames");
            return;
        }

        if (warmingUp)
        {
            warmupLeft -= Time.unscaledDeltaTime;
            if (warmupLeft <= 0f)
            {
                warmingUp  = false;
                recording  = true;
                recorded   = 0;
                frameTimes = new float[framesToRecord];
            }
            return;
        }

        if (recording)
        {
            frameTimes[recorded++] = Time.unscaledDeltaTime * 1000f;
            if (recorded == framesToRecord)
            {
                recording = false;
                Report();
            }
        }
    }

    void Report()
    {
        float[] sorted = (float[])frameTimes.Clone();
        Array.Sort(sorted);
        float median = Percentile(sorted, 0.5f);
        float p95    = Percentile(sorted, 0.95f);
        float fps    = 1000f / median;

        int   plants = CountPlants();
        float speed  = clock != null ? clock.timeScale : 0f;

        Debug.Log($"PerfRecorder: {framesToRecord} frames, median {median:F2} ms, p95 {p95:F2} ms, " +
                  $"median {fps:F1} FPS | {plants} plants, sim speed {speed:F1}x | " +
                  $"{SystemInfo.deviceModel}, {SystemInfo.processorType}, {SystemInfo.graphicsDeviceName}");

        var c = CultureInfo.InvariantCulture;
        AppendRow("frames", plants.ToString(c), speed.ToString("F1", c), median.ToString("F2", c),
                  p95.ToString("F2", c), fps.ToString("F1", c),
                  growthEngine != null ? growthEngine.modelLoadMs.ToString("F1", c) : "");
    }

    // Linear interpolation between the two nearest ranks
    static float Percentile(float[] sorted, float q)
    {
        float pos = q * (sorted.Length - 1);
        int   lo  = Mathf.FloorToInt(pos);
        int   hi  = Mathf.Min(lo + 1, sorted.Length - 1);
        return Mathf.Lerp(sorted[lo], sorted[hi], pos - lo);
    }

    int CountPlants()
    {
        if (farmGrid == null || farmGrid.GetAllPlants() == null) return 0;
        int n = 0;
        foreach (Plant plant in farmGrid.GetAllPlants())
            if (plant != null) n++;
        return n;
    }

    // Frame columns are left empty on the model_load row
    void AppendRow(string kind, string plants, string speed, string medianMs, string p95Ms, string fps,
                   string loadMs)
    {
        string build = Application.isEditor ? "editor" : (Debug.isDebugBuild ? "development" : "release");
        string row = string.Join(",",
            DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture), kind, plants, speed,
            medianMs, p95Ms, fps, loadMs,
            growthEngine != null && growthEngine.usingLearnedModel ? "1" : "0",
            Csv(SystemInfo.deviceModel), Csv(SystemInfo.processorType), Csv(SystemInfo.graphicsDeviceName),
            $"{Screen.width}x{Screen.height}", QualitySettings.vSyncCount.ToString(), build);

        try
        {
            bool newFile = !File.Exists(CsvPath);
            using (var writer = new StreamWriter(CsvPath, true))
            {
                if (newFile) writer.WriteLine(Header);
                writer.WriteLine(row);
            }
        }
        catch (Exception e)
        {
            Debug.LogWarning($"PerfRecorder: could not write {CsvPath}. {e.Message}");
        }
    }

    static string Csv(string s)
    {
        return "\"" + (s ?? "").Replace("\"", "\"\"") + "\"";
    }
}
