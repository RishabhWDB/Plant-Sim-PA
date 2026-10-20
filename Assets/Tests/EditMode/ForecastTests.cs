using NUnit.Framework;

/// <summary>
/// GrowthEngine.ComputeForecast must agree with forecast() in agent/sim_backends.py, because the
/// agent sees the forecast from either backend. Expected values come from the Python function,
/// rounded to 0.1 day; -1 means unbounded.
/// </summary>
public class ForecastTests
{
    [TestCase(0.3f, 0.90f, 0.044f, false, 42.5f, 38.3f, 47.8f,  TestName = "Forecast_Maturity")]
    [TestCase(0.4f, 0.20f, 0.044f, true,  44.4f, 38.8f, 52.1f,  TestName = "Forecast_Death")]
    [TestCase(0.4f, 0.52f, 0.044f, false, 725.0f, 226.6f, -1f,  TestName = "Forecast_MaturityBandReachesDeath")]
    [TestCase(0.4f, 0.48f, 0.044f, true,  666.7f, 208.3f, -1f,  TestName = "Forecast_DeathBandReachesGrowth")]
    [TestCase(0.5f, 0.50f, 0f,     false, -1f,    -1f,    -1f,  TestName = "Forecast_NoNetGrowth")]
    public void ComputeForecastMatchesPython(float progress, float score, float q, bool expectedDeath,
                                             float expectedDays, float expectedLow, float expectedHigh)
    {
        float days = GrowthEngine.ComputeForecast(progress, score, q, out float low, out float high, out bool death);
        Assert.AreEqual(expectedDeath, death);
        AssertDays(expectedDays, days);
        AssertDays(expectedLow, low);
        AssertDays(expectedHigh, high);
    }

    static void AssertDays(float expected, float actual)
    {
        if (expected < 0f)
            Assert.IsTrue(float.IsPositiveInfinity(actual), $"expected unbounded, got {actual}");
        else
            Assert.AreEqual(expected, actual, 0.06f);
    }
}
