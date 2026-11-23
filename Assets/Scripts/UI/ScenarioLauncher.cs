using System.Diagnostics;
using System.IO;
using TMPro;
using UnityEngine;
using UnityEngine.UI;
using Debug = UnityEngine.Debug;

/// <summary>
/// Demo panel (bottom right): one button per scenario. A click resets the field and starts the
/// Python LLM agent for that scenario in the background, so the demo needs no terminal.
/// The agent's output goes to Logs/agent_demo.log; its reasoning shows in the AgentLogPanel.
/// Editor / macOS only: it runs run_agent.sh from the project folder.
/// </summary>
public class ScenarioLauncher : MonoBehaviour
{
    public SimulationClock clock;
    public AgentLogPanel logPanel;
    public float secondsPerDecision = 13.5f;   // 4.5 s per day, so one decision every 3 days

    static readonly (string id, string label, string blurb)[] Scenarios =
    {
        ("drought",        "Drought",          "23 days of no rain at 36 °C"),
        ("monsoon",        "Flood",            "an early, very heavy monsoon waterlogs the field"),
        ("acid_soil",      "Acid soil",        "poor acidic soil, then acid rain"),
        ("heatwave_storm", "Heatwave + storm", "a heatwave, then a week-long storm"),
        ("calm",           "Normal season",    "good weather, few actions needed"),
    };

    Process agent;
    string running;
    TextMeshProUGUI statusText;
    readonly System.Collections.Generic.Dictionary<string, Image> buttons = new();

    static readonly Color Idle = new Color(0.16f, 0.36f, 0.22f, 0.95f);
    static readonly Color Active = new Color(0.85f, 0.48f, 0.12f, 0.95f);
    static readonly Color StopColor = new Color(0.45f, 0.12f, 0.12f, 0.95f);

    string Root => Directory.GetParent(Application.dataPath).FullName;

    // Adds itself to the scene's Canvas, so no scene edit is needed
    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
    static void Install()
    {
        if (FindFirstObjectByType<ScenarioLauncher>() != null) return;
        if (FindFirstObjectByType<SimulationServer>() == null) return;   // only in the demo scene
        var canvas = FindFirstObjectByType<Canvas>();
        if (canvas != null) canvas.gameObject.AddComponent<ScenarioLauncher>();
    }

    void Start()
    {
        if (clock == null) clock = FindFirstObjectByType<SimulationClock>();
        if (logPanel == null) logPanel = FindFirstObjectByType<AgentLogPanel>();
        BuildUI();
    }

    // UI, built in code so the layout lives in one place

    void BuildUI()
    {
        var panel = NewRect("ScenarioPanel", transform);
        panel.anchorMin = new Vector2(0.80f, 0.02f);
        panel.anchorMax = new Vector2(0.995f, 0.48f);
        panel.offsetMin = panel.offsetMax = Vector2.zero;
        panel.gameObject.AddComponent<Image>().color = new Color(0.05f, 0.08f, 0.06f, 0.6f);
        var layout = panel.gameObject.AddComponent<VerticalLayoutGroup>();
        layout.padding = new RectOffset(12, 12, 10, 10);
        layout.spacing = 6;
        layout.childForceExpandHeight = true;
        layout.childControlHeight = true;
        layout.childControlWidth = true;

        NewText(panel, "Run a season with the AI agent", 20, FontStyles.Bold);
        foreach (var s in Scenarios)
        {
            string id = s.id, label = s.label;
            buttons[id] = NewButton(panel, label, Idle, () => StartScenario(id, label));
        }
        NewButton(panel, "Stop agent", StopColor, StopAgent);
        statusText = NewText(panel, "Pick a scenario", 15, FontStyles.Italic);
    }

    static RectTransform NewRect(string name, Transform parent)
    {
        var go = new GameObject(name, typeof(RectTransform));
        go.transform.SetParent(parent, false);
        return (RectTransform)go.transform;
    }

    static TextMeshProUGUI NewText(Transform parent, string text, float size, FontStyles style)
    {
        var t = NewRect("Text", parent).gameObject.AddComponent<TextMeshProUGUI>();
        t.text = text;
        t.fontSize = size;
        t.fontStyle = style;
        t.color = Color.white;
        t.alignment = TextAlignmentOptions.Center;
        t.raycastTarget = false;
        return t;
    }

    static Image NewButton(Transform parent, string label, Color color, UnityEngine.Events.UnityAction onClick)
    {
        var rect = NewRect(label + " Button", parent);
        var image = rect.gameObject.AddComponent<Image>();
        image.color = color;
        rect.gameObject.AddComponent<Button>().onClick.AddListener(onClick);
        var text = NewText(rect, label, 20, FontStyles.Bold);
        var tr = (RectTransform)text.transform;
        tr.anchorMin = Vector2.zero;
        tr.anchorMax = Vector2.one;
        tr.offsetMin = tr.offsetMax = Vector2.zero;
        return image;
    }

    // Agent process

    void StartScenario(string id, string label)
    {
        StopAgent();
        string root = Root;
        string args = $"agent/run.py --policy agent --backend unity --scenario {id} --tick {secondsPerDecision}";
        bool offline = !HasApiKey(root);
        if (offline) args += " --dry-run";

        var psi = new ProcessStartInfo("/bin/bash",
            $"-c \"exec ./run_agent.sh {args} > Logs/agent_demo.log 2>&1\"")
        {
            WorkingDirectory = root,
            UseShellExecute = false,
            CreateNoWindow = true,
        };
        try
        {
            agent = Process.Start(psi);
        }
        catch (System.Exception e)
        {
            SetStatus($"Could not start the agent: {e.Message}");
            return;
        }

        running = label;
        buttons[id].color = Active;
        string blurb = System.Array.Find(Scenarios, s => s.id == id).blurb;
        if (logPanel != null)
        {
            logPanel.Clear();
            logPanel.AddLine($"{label}: {blurb}. The agent is connecting...");
        }
        SetStatus(offline ? $"Running: {label} (offline, fake LLM)" : $"Running: {label}");
    }

    void StopAgent()
    {
        if (agent != null && !agent.HasExited)
        {
            try { agent.Kill(); } catch { }
            if (clock != null) clock.Pause();
            SetStatus($"Stopped: {running}");
        }
        agent = null;
        running = null;
        foreach (var b in buttons.Values) b.color = Idle;
    }

    void Update()
    {
        if (agent != null && agent.HasExited)
        {
            int code = agent.ExitCode;
            SetStatus(code == 0 ? $"Season over: {running}" : $"Agent stopped with an error (see Logs/agent_demo.log)");
            if (code != 0) Debug.LogWarning("ScenarioLauncher: agent exited with code " + code);
            agent = null;
            running = null;
            foreach (var b in buttons.Values) b.color = Idle;
        }
    }

    void OnDisable() => StopAgent();

    void SetStatus(string text)
    {
        if (statusText != null) statusText.text = text;
    }

    static bool HasApiKey(string root)
    {
        string env = Path.Combine(root, ".env");
        if (!File.Exists(env)) return false;
        foreach (var line in File.ReadAllLines(env))
            if (line.StartsWith("DEEPINFRA_API_KEY=") && line.Length > "DEEPINFRA_API_KEY=".Length) return true;
        return false;
    }
}
