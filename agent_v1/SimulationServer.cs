using System;
using System.Collections;
using System.Collections.Concurrent;
using System.IO;
using System.Net;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;

/// <summary>
/// Local HTTP API that lets an external agent observe and control the simulation.
///
/// Endpoints (all JSON):
///   GET  /health        server check
///   GET  /state         plant status + environment + prediction
///   GET  /environment   current environment values
///   POST /environment   {"parameter": "soil_moisture", "value": 60}
///   POST /advance       {"days": 1}   steps the simulation forward day by day
///   POST /reset         resets plants and clock (clock stays paused)
///   POST /pause         pauses real-time clock (agent controls time)
///   POST /resume        resumes real-time clock
///   POST /predict       {"soil_moisture": 60, "ph": 6.5}  what-if score, nothing is changed
///   POST /log           {"message": "..."}  shows the agent's reasoning on screen
///
/// Requests arrive on a background thread and are executed on Unity's main thread.
/// </summary>
public class SimulationServer : MonoBehaviour
{
    [Header("Server")]
    public int   port = 8765;
    [Tooltip("Real seconds between each day when the agent advances time, so growth stays visible")]
    public float secondsPerAdvancedDay = 0.25f;

    [Header("References")]
    public SimulationClock clock;
    public GrowthEngine    growthEngine;
    public FarmGrid        farmGrid;
    public SlidersPanel    slidersPanel;

    [Header("Agent Log (optional)")]
    public TMPro.TextMeshProUGUI agentLogText;
    public int maxLogLines = 6;
    private readonly System.Collections.Generic.Queue<string> logLines = new System.Collections.Generic.Queue<string>();

    private HttpListener listener;
    private Thread       listenThread;
    private volatile bool running;
    private readonly ConcurrentQueue<Action> mainThreadQueue = new ConcurrentQueue<Action>();

    private float peakProgress = 0f;
    private bool  advancing    = false;

    private static readonly string[] StageNames =
        { "Seed", "Germination", "Sprout", "Seedling", "Vegetative", "Flowering", "Mature" };

    // ===================== JSON data classes =====================

    [Serializable] private class SetRequest     { public string parameter; public float value; }
    [Serializable] private class AdvanceRequest { public int days = 1; }
    [Serializable] private class ErrorData      { public string error; }
    [Serializable] private class OkData         { public bool ok = true; public string message; }
    [Serializable] private class LogRequest     { public string message; }

    // -999 means "not supplied, use the current value"
    [Serializable]
    private class PredictRequest
    {
        public float ph = -999f, soil_moisture = -999f, sunlight_hours = -999f,
                     temperature = -999f, humidity = -999f, rainfall = -999f;
    }

    [Serializable]
    private class PredictData
    {
        public float  growth_score;
        public string health_zone;
        public float  growth_rate_percent_per_day;
        public EnvironmentData environment;
    }

    [Serializable]
    public class EnvironmentData
    {
        public float ph;
        public float soil_moisture;
        public float sunlight_hours;
        public float temperature;
        public float humidity;
        public float rainfall;
    }

    [Serializable]
    public class StatusData
    {
        public int    day;
        public float  growth_score;
        public string health_zone;
        public float  growth_rate_percent_per_day;
        public float  average_progress_percent;
        public float  min_progress_percent;
        public float  max_progress_percent;
        public int    stage;
        public string stage_name;
        public string outcome;
        public int    predicted_days;
        public EnvironmentData environment;
    }

    // ===================== Lifecycle =====================

    void Start()
    {
        // Keep simulating while the terminal running the agent has focus
        Application.runInBackground = true;

        listener = new HttpListener();
        listener.Prefixes.Add($"http://localhost:{port}/");
        listener.Prefixes.Add($"http://127.0.0.1:{port}/");
        listener.Start();

        running = true;
        listenThread = new Thread(ListenLoop) { IsBackground = true };
        listenThread.Start();

        Debug.Log($"SimulationServer: listening on http://localhost:{port}/");
    }

    void Update()
    {
        while (mainThreadQueue.TryDequeue(out Action action))
            action();

        UpdatePeak();
    }

    void OnDisable()
    {
        running = false;
        try { listener?.Stop(); listener?.Close(); } catch { }
    }

    // ===================== Networking (background thread) =====================

    void ListenLoop()
    {
        while (running)
        {
            try
            {
                HttpListenerContext ctx = listener.GetContext();
                ThreadPool.QueueUserWorkItem(_ => Handle(ctx));
            }
            catch (HttpListenerException) { break; }
            catch (ObjectDisposedException) { break; }
            catch (InvalidOperationException) { break; }
        }
    }

    void Handle(HttpListenerContext ctx)
    {
        string body;
        using (var reader = new StreamReader(ctx.Request.InputStream, Encoding.UTF8))
            body = reader.ReadToEnd();

        string path   = ctx.Request.Url.AbsolutePath.TrimEnd('/');
        string method = ctx.Request.HttpMethod;
        if (path == "") path = "/";

        var tcs = new TaskCompletionSource<(int code, string json)>();

        mainThreadQueue.Enqueue(() =>
        {
            try { Route(method, path, body, (code, json) => tcs.TrySetResult((code, json))); }
            catch (Exception e) { tcs.TrySetResult((500, Err(e.Message))); }
        });

        (int code, string json) result = tcs.Task.Wait(TimeSpan.FromSeconds(120))
            ? tcs.Task.Result
            : (504, Err("Timed out waiting for Unity main thread. Is Play mode running?"));

        byte[] bytes = Encoding.UTF8.GetBytes(result.json);
        ctx.Response.StatusCode      = result.code;
        ctx.Response.ContentType     = "application/json";
        ctx.Response.ContentLength64 = bytes.Length;
        ctx.Response.OutputStream.Write(bytes, 0, bytes.Length);
        ctx.Response.OutputStream.Close();
    }

    // ===================== Routing (main thread) =====================

    void Route(string method, string path, string body, Action<int, string> respond)
    {
        switch (path)
        {
            case "/health":
                respond(200, JsonUtility.ToJson(new OkData { message = "Plant simulation server running" }));
                return;

            case "/state":
                respond(200, JsonUtility.ToJson(BuildStatus()));
                return;

            case "/environment":
                if (method == "GET")
                {
                    respond(200, JsonUtility.ToJson(GetEnvironment()));
                    return;
                }
                var setReq = JsonUtility.FromJson<SetRequest>(body);
                if (setReq == null || string.IsNullOrEmpty(setReq.parameter))
                {
                    respond(400, Err("Body must be {\"parameter\": name, \"value\": number}"));
                    return;
                }
                if (!SetParameter(setReq.parameter, setReq.value))
                {
                    respond(400, Err($"Unknown parameter '{setReq.parameter}'"));
                    return;
                }
                respond(200, JsonUtility.ToJson(GetEnvironment()));
                return;

            case "/advance":
                if (advancing)
                {
                    respond(409, Err("Simulation is already advancing"));
                    return;
                }
                var advReq = string.IsNullOrEmpty(body) ? new AdvanceRequest() : JsonUtility.FromJson<AdvanceRequest>(body);
                int days = Mathf.Clamp(advReq.days, 1, 30);
                StartCoroutine(AdvanceRoutine(days, respond));
                return;

            case "/reset":
                ResetSimulation();
                respond(200, JsonUtility.ToJson(BuildStatus()));
                return;

            case "/pause":
                clock.Pause();
                respond(200, JsonUtility.ToJson(new OkData { message = "Clock paused" }));
                return;

            case "/resume":
                clock.Resume();
                respond(200, JsonUtility.ToJson(new OkData { message = "Clock resumed" }));
                return;

            case "/predict":
                respond(200, JsonUtility.ToJson(Predict(body)));
                return;

            case "/log":
                var logReq = JsonUtility.FromJson<LogRequest>(body);
                AddLogLine(logReq != null ? logReq.message : "");
                respond(200, JsonUtility.ToJson(new OkData { message = "Logged" }));
                return;

            default:
                respond(404, Err($"Unknown endpoint {method} {path}"));
                return;
        }
    }

    IEnumerator AdvanceRoutine(int days, Action<int, string> respond)
    {
        advancing = true;
        for (int i = 0; i < days; i++)
        {
            clock.AdvanceOneDay();
            UpdatePeak();

            string outcome = BuildStatus().outcome;
            if (outcome == "matured" || outcome == "dead") break;

            yield return new WaitForSecondsRealtime(secondsPerAdvancedDay);
        }
        advancing = false;
        respond(200, JsonUtility.ToJson(BuildStatus()));
    }

    // ===================== What-if prediction and agent log =====================

    PredictData Predict(string body)
    {
        var req = string.IsNullOrEmpty(body) ? new PredictRequest() : JsonUtility.FromJson<PredictRequest>(body);
        EnvironmentData env = GetEnvironment();

        if (req.ph             > -998f) env.ph             = Mathf.Clamp(req.ph,             3.5f, 9.5f);
        if (req.soil_moisture  > -998f) env.soil_moisture  = Mathf.Clamp(req.soil_moisture,  5f,   100f);
        if (req.sunlight_hours > -998f) env.sunlight_hours = Mathf.Clamp(req.sunlight_hours, 0f,   16f);
        if (req.temperature    > -998f) env.temperature    = Mathf.Clamp(req.temperature,    0f,   45f);
        if (req.humidity       > -998f) env.humidity       = Mathf.Clamp(req.humidity,       10f,  100f);
        if (req.rainfall       > -998f) env.rainfall       = Mathf.Clamp(req.rainfall,       0f,   120f);

        float score = growthEngine.PlaceholderModel(
            env.ph, env.soil_moisture, env.sunlight_hours,
            env.temperature, env.humidity, env.rainfall,
            growthEngine.currentStage);

        float rate = score >= 0.5f ? (score - 0.5f) * 2f * 0.02f : -(0.5f - score) * 2f * 0.015f;

        return new PredictData
        {
            growth_score                = Round(score, 4),
            health_zone                 = HealthZone(score),
            growth_rate_percent_per_day = Round(rate * 100f, 3),
            environment                 = env,
        };
    }

    void AddLogLine(string message)
    {
        if (string.IsNullOrEmpty(message)) return;
        logLines.Enqueue($"[Day {clock.currentDay}] {message}");
        while (logLines.Count > maxLogLines) logLines.Dequeue();
        if (agentLogText != null) agentLogText.text = string.Join("\n", logLines);
        Debug.Log($"Agent: {message}");
    }

    // ===================== Simulation access =====================

    EnvironmentData GetEnvironment()
    {
        return new EnvironmentData
        {
            ph             = growthEngine.pH,
            soil_moisture  = growthEngine.soilMoisture,
            sunlight_hours = growthEngine.sunlightHours,
            temperature    = growthEngine.temperature,
            humidity       = growthEngine.humidity,
            rainfall       = growthEngine.rainfall,
        };
    }

    bool SetParameter(string name, float value)
    {
        // Route through the sliders so the UI moves too
        if (slidersPanel != null)
            return slidersPanel.SetParameter(name, value);

        switch (name)
        {
            case "ph":             growthEngine.pH            = Mathf.Clamp(value, 3.5f, 9.5f); return true;
            case "soil_moisture":  growthEngine.soilMoisture  = Mathf.Clamp(value, 5f, 100f);   return true;
            case "sunlight_hours": growthEngine.sunlightHours = Mathf.Clamp(value, 0f, 16f);    return true;
            case "temperature":    growthEngine.temperature   = Mathf.Clamp(value, 0f, 45f);    return true;
            case "humidity":       growthEngine.humidity      = Mathf.Clamp(value, 10f, 100f);  return true;
            case "rainfall":       growthEngine.rainfall      = Mathf.Clamp(value, 0f, 120f);   return true;
            default: return false;
        }
    }

    void ResetSimulation()
    {
        clock.Reset();
        clock.Pause();
        peakProgress = 0f;

        Plant[] plants = farmGrid.GetAllPlants();
        if (plants != null)
            foreach (Plant p in plants)
                if (p != null) p.ResetGrowth();
    }

    void ProgressStats(out float avg, out float min, out float max)
    {
        avg = 0f; min = 0f; max = 0f;
        Plant[] plants = farmGrid != null ? farmGrid.GetAllPlants() : null;
        if (plants == null) return;

        float sum = 0f; int n = 0;
        min = 1f;
        foreach (Plant p in plants)
        {
            if (p == null) continue;
            sum += p.growthProgress;
            min  = Mathf.Min(min, p.growthProgress);
            max  = Mathf.Max(max, p.growthProgress);
            n++;
        }
        if (n == 0) { min = 0f; return; }
        avg = sum / n;
    }

    void UpdatePeak()
    {
        if (farmGrid == null) return;
        ProgressStats(out float avg, out _, out _);
        peakProgress = Mathf.Max(peakProgress, avg);
    }

    StatusData BuildStatus()
    {
        EnvironmentData env = GetEnvironment();

        // Score for current conditions (requires PlaceholderModel to be public in GrowthEngine)
        float score = growthEngine.PlaceholderModel(
            env.ph, env.soil_moisture, env.sunlight_hours,
            env.temperature, env.humidity, env.rainfall,
            growthEngine.currentStage);

        ProgressStats(out float avg, out float min, out float max);

        // Same growth rule as Plant.UpdateGrowth (without per-plant offset)
        float rate = score >= 0.5f
            ?  (score - 0.5f) * 2f * 0.02f
            : -(0.5f - score) * 2f * 0.015f;

        string outcome;
        int predictedDays = -1;

        if (avg >= 0.98f)
        {
            outcome = "matured"; predictedDays = 0;
        }
        else if (peakProgress > 0.05f && avg <= 0.001f)
        {
            outcome = "dead"; predictedDays = 0;
        }
        else if (rate > 0.0005f)
        {
            outcome = "growing_toward_maturity";
            predictedDays = Mathf.CeilToInt((0.98f - avg) / rate);
        }
        else if (rate < -0.0005f)
        {
            if (peakProgress > 0.05f)
            {
                outcome = "declining_toward_death";
                predictedDays = Mathf.CeilToInt(avg / -rate);
            }
            else
            {
                outcome = "failing_to_establish";
            }
        }
        else
        {
            outcome = "stalled";
        }

        int stageIndex = Mathf.Clamp(Mathf.FloorToInt(avg * 7f), 0, 6);

        return new StatusData
        {
            day                          = clock.currentDay,
            growth_score                 = Round(score, 4),
            health_zone                  = HealthZone(score),
            growth_rate_percent_per_day  = Round(rate * 100f, 3),
            average_progress_percent     = Round(avg * 100f, 2),
            min_progress_percent         = Round(min * 100f, 2),
            max_progress_percent         = Round(max * 100f, 2),
            stage                        = stageIndex + 1,
            stage_name                   = StageNames[stageIndex],
            outcome                      = outcome,
            predicted_days               = predictedDays,
            environment                  = env,
        };
    }

    static string HealthZone(float score)
    {
        if (score < 0.2f)  return "critical";
        if (score < 0.5f)  return "deteriorating";
        if (score < 0.75f) return "growing";
        return "thriving";
    }

    static float Round(float v, int digits)
    {
        float m = Mathf.Pow(10f, digits);
        return Mathf.Round(v * m) / m;
    }

    static string Err(string msg) => JsonUtility.ToJson(new ErrorData { error = msg });
}
