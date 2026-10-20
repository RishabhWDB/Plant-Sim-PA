using System.Collections.Generic;
using UnityEngine;
using TMPro;

/// <summary>
/// On-screen agent log: the most recent lines the agent sent to SimulationServer's /log endpoint
/// (its reasoning, its equipment actions and weather news), newest at the bottom.
/// </summary>
public class AgentLogPanel : MonoBehaviour
{
    [Header("References")]
    public TextMeshProUGUI logText;

    [Header("Settings")]
    public int maxLines = 8;

    private readonly Queue<string> lines = new Queue<string>();

    void Start()
    {
        Refresh();
    }

    public void AddLine(string line)
    {
        if (string.IsNullOrEmpty(line)) return;
        lines.Enqueue(line);
        while (lines.Count > maxLines) lines.Dequeue();
        Refresh();
    }

    public void Clear()
    {
        lines.Clear();
        Refresh();
    }

    void Refresh()
    {
        if (logText != null)
            logText.text = lines.Count > 0 ? string.Join("\n", lines) : "Agent log: waiting for the agent";
    }
}
