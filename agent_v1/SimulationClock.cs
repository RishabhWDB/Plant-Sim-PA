using UnityEngine;
using System;

public class SimulationClock : MonoBehaviour
{
    [Header("Time Settings")]
    public float secondsPerDay = 3f;
    public float timeScale     = 1f;
    public bool  paused        = false;

    [Header("Read Only")]
    public int   currentDay    = 0;
    public float dayProgress   = 0f;

    public event Action OnDayPassed;

    void Update()
    {
        if (paused) return;

        dayProgress += (Time.deltaTime / secondsPerDay) * timeScale;

        if (dayProgress >= 1f)
        {
            dayProgress = 0f;
            currentDay++;
            OnDayPassed?.Invoke();
        }
    }

    /// <summary>Advances exactly one day. Used by the agent while the clock is paused.</summary>
    public void AdvanceOneDay()
    {
        dayProgress = 0f;
        currentDay++;
        OnDayPassed?.Invoke();
    }

    public void Pause()  { paused = true;  }
    public void Resume() { paused = false; }

    public void SetSpeed(float speed)
    {
        timeScale = Mathf.Clamp(speed, 0.5f, 20f);
    }

    public void Reset()
    {
        currentDay  = 0;
        dayProgress = 0f;
        paused      = false;
    }
}
