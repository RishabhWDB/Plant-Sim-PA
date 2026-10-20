using System;
using System.IO;
using NUnit.Framework;
using UnityEngine;

/// <summary>
/// Parity between the C# twin and the Python reference in ml/.
/// parity_vectors.json is written by ml/train_model.py from its reference_eval(), which matches
/// scikit-learn exactly. Re-run train_model.py and copy growth_model.json after retraining.
/// </summary>
public class GrowthModelTests
{
    [Serializable]
    class ParityCase
    {
        public double[] input;
        public double   expected;
    }

    [Serializable]
    class ParityFile
    {
        public string[]     features;
        public ParityCase[] cases;
    }

    static string ModelPath  => Path.Combine(Application.dataPath, "MLModels", "growth_model.json");
    static string VectorPath => Path.Combine(Application.dataPath, "Tests", "EditMode", "parity_vectors.json");

    [Test]
    public void PredictMatchesPythonReference()
    {
        Assert.That(File.Exists(ModelPath), $"Missing {ModelPath}");
        Assert.That(File.Exists(VectorPath), $"Missing {VectorPath}");

        GrowthModel model  = GrowthModel.Load(File.ReadAllText(ModelPath));
        ParityFile  parity = JsonUtility.FromJson<ParityFile>(File.ReadAllText(VectorPath));
        Assert.That(parity.cases.Length, Is.GreaterThanOrEqualTo(50));

        foreach (ParityCase c in parity.cases)
        {
            double[] x = c.input;
            float got = model.Predict((float)x[0], (float)x[1], (float)x[2], (float)x[3], (float)x[4], (int)x[5]);
            Assert.AreEqual(c.expected, got, 1e-5, $"input [{string.Join(", ", x)}]");
        }
    }

    // Expected values from twin_core.water_step(sm, rain, irrigation, T, RH, n, stage) in ml/
    [TestCase(55f,  0f,   0f,  25f, 62f, 8f,  0, 53.05843435f, 2.62111362f, TestName = "WaterStep_MildDay")]
    [TestCase(30f,  0f,   0f,  35f, 38f, 10f, 3, 27.23327141f, 3.73508360f, TestName = "WaterStep_HotDryDay_Stressed")]
    [TestCase(68f,  40f,  0f,  26f, 62f, 8f,  4, 81.92691846f, 5.09732016f, TestName = "WaterStep_HeavyRain_Drains")]
    [TestCase(5.5f, 0f,   0f,  40f, 20f, 12f, 5, 5.40013833f,  0.13481326f, TestName = "WaterStep_NearWiltingPoint")]
    [TestCase(44f,  12f,  35f, 30f, 45f, 9f,  6, 72.83228201f, 4.25283857f, TestName = "WaterStep_RainPlusIrrigation")]
    [TestCase(95f,  110f, 0f,  20f, 90f, 4f,  2, 100f,         2.21927643f, TestName = "WaterStep_Saturated_Clamped")]
    public void WaterStepMatchesTwinCore(float sm, float rain, float irr, float temp, float rh, float sun,
                                         int stage, float expectedSm, float expectedEtc)
    {
        float sm1 = GrowthEngine.WaterStep(sm, rain, irr, temp, rh, sun, stage, out float etc);
        Assert.AreEqual(expectedSm,  sm1, 1e-3);
        Assert.AreEqual(expectedEtc, etc, 1e-4);
    }
}
