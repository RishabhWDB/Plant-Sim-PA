using System;
using System.IO;
using UnityEngine;
using UnityEngine.InputSystem;

/// <summary>
/// Press F12 to save a supersampled screenshot to paper/figures/ in the repository.
/// Works in the Editor and in development builds placed inside the repository (for example
/// Builds/); does nothing in release builds.
/// </summary>
public class ScreenshotKey : MonoBehaviour
{
    [Range(1, 4)] public int supersample = 2;

#if UNITY_EDITOR || DEVELOPMENT_BUILD
    void Update()
    {
        if (Keyboard.current == null || !Keyboard.current.f12Key.wasPressedThisFrame) return;

        string folder = FiguresFolder();
        if (folder == null)
        {
            Debug.LogWarning($"ScreenshotKey: no paper/ folder found above {Application.dataPath}. " +
                             "Build into a folder inside the repository, for example Builds/.");
            return;
        }

        Directory.CreateDirectory(folder);
        string path = Path.Combine(folder, $"twin_{DateTime.Now:yyyyMMdd_HHmmss}.png");
        ScreenCapture.CaptureScreenshot(path, supersample);
        Debug.Log($"ScreenshotKey: saved {path} at {Screen.width * supersample}x{Screen.height * supersample}");
    }

    // In the Editor dataPath is <repo>/Assets; in a macOS build it is <build>/<App>.app/Contents.
    // Walk up until a folder that contains paper/main.tex.
    static string FiguresFolder()
    {
        DirectoryInfo dir = new DirectoryInfo(Application.dataPath);
        while (dir != null)
        {
            if (File.Exists(Path.Combine(dir.FullName, "paper", "main.tex")))
                return Path.Combine(dir.FullName, "paper", "figures");
            dir = dir.Parent;
        }
        return null;
    }
#endif
}
