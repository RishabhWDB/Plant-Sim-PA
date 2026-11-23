using TMPro;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// Adds what the live agent demo needs to SampleScene and saves it:
///   - SimulationServer on the SimulationManager, wired to the clock, engine, grid and sliders,
///     so the Python agent can connect on http://localhost:8765 when the scene plays
///   - an on-screen AgentLogPanel (bottom left) that shows the agent's reasoning
/// Safe to run again: existing components are reused and only missing references are filled.
///
/// Menu: PlantSim > Set Up Agent Demo Scene
/// Batch: Unity -batchmode -quit -projectPath . -executeMethod DemoSceneSetup.Run
/// </summary>
public static class DemoSceneSetup
{
    const string ScenePath = "Assets/Scenes/SampleScene.unity";

    [MenuItem("PlantSim/Set Up Agent Demo Scene")]
    static void RunFromMenu()
    {
        if (!EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo()) return;
        Run();
    }

    public static void Run()
    {
        var scene = EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);

        var clock   = Object.FindFirstObjectByType<SimulationClock>(FindObjectsInactive.Include);
        var engine  = Object.FindFirstObjectByType<GrowthEngine>(FindObjectsInactive.Include);
        var grid    = Object.FindFirstObjectByType<FarmGrid>(FindObjectsInactive.Include);
        var sliders = Object.FindFirstObjectByType<SlidersPanel>(FindObjectsInactive.Include);
        if (clock == null || engine == null || grid == null)
        {
            Debug.LogError("DemoSceneSetup: SimulationClock, GrowthEngine or FarmGrid not found in SampleScene.");
            return;
        }

        var server = Object.FindFirstObjectByType<SimulationServer>(FindObjectsInactive.Include);
        if (server == null) server = Undo.AddComponent<SimulationServer>(clock.gameObject);
        if (server.clock == null)        server.clock = clock;
        if (server.growthEngine == null) server.growthEngine = engine;
        if (server.farmGrid == null)     server.farmGrid = grid;
        if (server.slidersPanel == null) server.slidersPanel = sliders;
        server.enabled = true;

        var log = Object.FindFirstObjectByType<AgentLogPanel>(FindObjectsInactive.Include);
        if (log == null) log = CreateLogPanel();
        if (log != null)
        {
            ApplyLogLayout(log);
            server.agentLogPanel = log;
        }

        EditorUtility.SetDirty(server);
        EditorSceneManager.MarkSceneDirty(scene);
        bool saved = EditorSceneManager.SaveScene(scene);
        Debug.Log($"DemoSceneSetup: SimulationServer on '{server.gameObject.name}' (port {server.port}), " +
                  $"log panel {(log != null ? "added" : "missing")}, scene saved: {saved}");
    }

    static AgentLogPanel CreateLogPanel()
    {
        var canvas = Object.FindFirstObjectByType<Canvas>(FindObjectsInactive.Include);
        if (canvas == null)
        {
            Debug.LogWarning("DemoSceneSetup: no Canvas in the scene, agent log panel not added.");
            return null;
        }

        var panel = new GameObject("AgentLogPanel", typeof(RectTransform), typeof(Image), typeof(AgentLogPanel));
        Undo.RegisterCreatedObjectUndo(panel, "Add agent log panel");
        panel.transform.SetParent(canvas.transform, false);
        panel.GetComponent<Image>().color = new Color(0.05f, 0.08f, 0.06f, 0.6f);

        var textObj = new GameObject("LogText", typeof(RectTransform), typeof(TextMeshProUGUI));
        textObj.transform.SetParent(panel.transform, false);
        var textRect = (RectTransform)textObj.transform;
        textRect.anchorMin = Vector2.zero;
        textRect.anchorMax = Vector2.one;
        textRect.offsetMin = new Vector2(14, 10);
        textRect.offsetMax = new Vector2(-14, -10);
        var text = textObj.GetComponent<TextMeshProUGUI>();
        text.color = Color.white;
        text.alignment = TextAlignmentOptions.BottomLeft;
        text.textWrappingMode = TextWrappingModes.Normal;
        text.overflowMode = TextOverflowModes.Truncate;
        text.raycastTarget = false;
        text.text = "Agent log: waiting for the agent";

        var log = panel.GetComponent<AgentLogPanel>();
        log.logText = text;
        return log;
    }

    /// <summary>Size and text settings, applied on every run so they can be tuned here.</summary>
    static void ApplyLogLayout(AgentLogPanel log)
    {
        // Bottom left, up to 40% of the screen height: clear of the sliders (top left),
        // the status text (top right) and the time controls (bottom centre)
        var rect = (RectTransform)log.transform;
        Undo.RecordObject(rect, "Agent log layout");
        rect.anchorMin = new Vector2(0.005f, 0.02f);
        rect.anchorMax = new Vector2(0.38f, 0.40f);
        rect.offsetMin = Vector2.zero;
        rect.offsetMax = Vector2.zero;

        Undo.RecordObject(log, "Agent log layout");
        log.maxLines = 4;   // the last two decisions (reasoning + twin verdict), readable on a projector
        if (log.logText != null)
        {
            Undo.RecordObject(log.logText, "Agent log layout");
            log.logText.enableAutoSizing = true;
            log.logText.fontSizeMin = 16;
            log.logText.fontSizeMax = 24;
            EditorUtility.SetDirty(log.logText);
        }
        EditorUtility.SetDirty(rect);
        EditorUtility.SetDirty(log);
    }

    /// <summary>Opens SampleScene, maximizes the Game view and enters Play mode (used by demo.sh).
    /// Shift+Space toggles the maximized view back.</summary>
    public static void Play()
    {
        EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
        var gameViewType = typeof(EditorWindow).Assembly.GetType("UnityEditor.GameView");
        if (gameViewType != null)
        {
            var gameView = EditorWindow.GetWindow(gameViewType);
            gameView.Focus();
            gameView.maximized = true;
        }
        EditorApplication.EnterPlaymode();
    }
}
