using UnityEngine;

public class Plant : MonoBehaviour
{
    [Header("Growth Stages")]
    public GameObject[] stageModels = new GameObject[7];

    [Header("Simulation")]
    public float growthProgress   = 0f;
    public float individualOffset = 0f;

    [Header("Transition Settings")]
    public float transitionSpeed = 2f;

    private int   currentStage    = 0;
    private float lastScore       = -1f;
    private float stageProgress   = 0f;
    private float currentScale    = 0.05f;
    private float targetScale     = 0.05f;
    private bool  isTransitioning = false;
    private int   nextStage       = 0;
    private float transitionAlpha = 0f;

    private MaterialPropertyBlock propBlock;
    private Renderer[]            renderers;

    private float[] minScales = { 0.05f, 0.15f, 0.25f, 0.40f, 0.55f, 0.70f, 0.85f };
    private float[] maxScales = { 0.15f, 0.25f, 0.40f, 0.55f, 0.70f, 0.85f, 1.00f };

    void Start()
    {
        propBlock = new MaterialPropertyBlock();
        renderers = GetComponentsInChildren<Renderer>(true);

        // Keep parent at default scale always
        transform.localScale = Vector3.one;
        currentScale = minScales[0];
        UpdateStageVisual(0);

        if (stageModels[0] != null)
            stageModels[0].transform.localScale = Vector3.one * currentScale;
    }

    void Update()
    {
        // Smoothly lerp scale on the active stage model
        if (Mathf.Abs(currentScale - targetScale) > 0.001f)
        {
            currentScale = Mathf.Lerp(currentScale, targetScale, Time.deltaTime * transitionSpeed);
            ApplyScale(currentScale);
        }

        // Handle smooth transition between stage models
        if (isTransitioning)
        {
            transitionAlpha += Time.deltaTime * transitionSpeed;

            if (transitionAlpha >= 1f)
            {
                transitionAlpha = 1f;
                isTransitioning = false;

                if (stageModels[currentStage] != null)
                    stageModels[currentStage].SetActive(false);

                currentStage = nextStage;
            }

            // Scale new stage model in from zero
            if (stageModels[nextStage] != null)
            {
                float newStageScale = Mathf.Lerp(0f, targetScale, transitionAlpha);
                stageModels[nextStage].transform.localScale = Vector3.one * newStageScale;
            }
        }
    }

    public void UpdateGrowth(float score)
    {
        float adjustedScore = Mathf.Clamp01(score + individualOffset);

        if (adjustedScore >= 0.5f)
            growthProgress += (adjustedScore - 0.5f) * 2f * 0.02f;
        else
            growthProgress -= (0.5f - adjustedScore) * 2f * 0.015f;

        growthProgress = Mathf.Clamp01(growthProgress);

        int newStage = Mathf.Clamp(Mathf.FloorToInt(growthProgress * 7), 0, 6);

        float stageSize = 1f / 7f;
        float stageBase = newStage * stageSize;
        stageProgress   = (growthProgress - stageBase) / stageSize;

        targetScale = Mathf.Lerp(
            minScales[newStage],
            maxScales[newStage],
            stageProgress
        );

        if (newStage != currentStage && !isTransitioning)
            TriggerStageTransition(newStage);

        if (Mathf.Abs(adjustedScore - lastScore) > 0.01f)
        {
            UpdateColour(adjustedScore);
            lastScore = adjustedScore;
        }
    }

    void TriggerStageTransition(int newStageIndex)
    {
        nextStage       = newStageIndex;
        isTransitioning = true;
        transitionAlpha = 0f;

        if (stageModels[nextStage] != null)
        {
            stageModels[nextStage].SetActive(true);
            stageModels[nextStage].transform.localScale = Vector3.zero;
        }
    }

    void UpdateStageVisual(int stage)
    {
        for (int i = 0; i < stageModels.Length; i++)
        {
            if (stageModels[i] != null)
                stageModels[i].SetActive(i == stage);
        }
    }

    void ApplyScale(float scale)
    {
        // Only scale the active stage model, never the parent
        if (stageModels[currentStage] != null)
            stageModels[currentStage].transform.localScale = Vector3.one * scale;
    }

    void UpdateColour(float score)
    {
        Color targetColour;

        if (score >= 0.65f)
        {
            targetColour = Color.Lerp(
                new Color(0.4f, 0.7f, 0.2f),
                new Color(0.1f, 0.5f, 0.05f),
                (score - 0.65f) / 0.35f
            );
        }
        else if (score >= 0.35f)
        {
            targetColour = Color.Lerp(
                new Color(0.7f, 0.6f, 0.1f),
                new Color(0.4f, 0.7f, 0.2f),
                (score - 0.35f) / 0.30f
            );
        }
        else
        {
            targetColour = Color.Lerp(
                new Color(0.35f, 0.18f, 0.05f),
                new Color(0.7f,  0.60f, 0.10f),
                score / 0.35f
            );
        }

        foreach (Renderer r in renderers)
        {
            r.GetPropertyBlock(propBlock);
            propBlock.SetColor("_BaseColor", targetColour);
            r.SetPropertyBlock(propBlock);
        }
    }

    public void ResetGrowth()
    {
        growthProgress   = 0f;
        currentStage     = 0;
        currentScale     = minScales[0];
        targetScale      = minScales[0];
        isTransitioning  = false;

        transform.localScale = Vector3.one;
        UpdateStageVisual(0);

        if (stageModels[0] != null)
            stageModels[0].transform.localScale = Vector3.one * currentScale;
    }
}