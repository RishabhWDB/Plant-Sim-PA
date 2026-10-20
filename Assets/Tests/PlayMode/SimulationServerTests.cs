using System.Collections;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

/// <summary>
/// Runs SimulationServer in Play mode on a small field and drives it over HTTP, the way
/// agent/sim_backends.py UnitySim does.
/// </summary>
public class SimulationServerTests
{
    const string Url = "http://localhost:8765";

    GameObject root, prefab;
    SimulationClock clock;
    GrowthEngine engine;
    SimulationServer server;
    static readonly HttpClient http = new HttpClient();

    [UnitySetUp]
    public IEnumerator SetUp()
    {
        prefab = new GameObject("PlantPrefab");
        prefab.AddComponent<Plant>();
        prefab.transform.position = Vector3.down * 100f;

        root = new GameObject("Simulation");
        root.SetActive(false);
        clock  = root.AddComponent<SimulationClock>();
        var grid = root.AddComponent<FarmGrid>();
        grid.plantPrefab = prefab;
        grid.rows = 2;
        grid.columns = 2;
        engine = root.AddComponent<GrowthEngine>();
        engine.clock = clock;
        engine.farmGrid = grid;
        server = root.AddComponent<SimulationServer>();
        server.clock = clock;
        server.growthEngine = engine;
        server.farmGrid = grid;
        server.secondsPerAdvancedDay = 0f;
        root.SetActive(true);

        yield return null;
        yield return null;
    }

    [TearDown]
    public void TearDown()
    {
        Object.Destroy(root);
        Object.Destroy(prefab);
    }

    static IEnumerator Send(string method, string path, string json, System.Action<string> done)
    {
        Task<HttpResponseMessage> t = method == "GET"
            ? http.GetAsync(Url + path)
            : http.PostAsync(Url + path, new StringContent(json ?? "", Encoding.UTF8, "application/json"));
        while (!t.IsCompleted) yield return null;
        Assert.IsFalse(t.IsFaulted, t.Exception?.ToString());
        Task<string> body = t.Result.Content.ReadAsStringAsync();
        while (!body.IsCompleted) yield return null;
        Assert.IsTrue(t.Result.IsSuccessStatusCode, body.Result);
        done(body.Result);
    }

    [UnityTest]
    public IEnumerator ResetPredictAdvance_FollowsTheWaterBalance()
    {
        string json = null;
        yield return Send("POST", "/reset", "", r => json = r);
        var status = JsonUtility.FromJson<SimulationServer.StatusData>(json);
        Assert.AreEqual(0, status.day);
        StringAssert.Contains("\"forecast\"", json);
        StringAssert.Contains("\"learned_model\"", json);
        StringAssert.Contains("\"evapotranspiration_mm_per_day\"", json);

        yield return Send("POST", "/environment", "{\"parameter\":\"rainfall\",\"value\":0}", r => json = r);
        yield return Send("POST", "/environment", "{\"parameter\":\"soil_moisture\",\"value\":60}", r => json = r);
        yield return Send("GET", "/state", null, r => json = r);
        status = JsonUtility.FromJson<SimulationServer.StatusData>(json);
        Assert.AreEqual(60f, status.soil_moisture_percent, 1e-3f);

        // What-if: tomorrow's soil moisture after the water balance, and nothing changes
        float expected = GrowthEngine.WaterStep(60f, 0f, 0f, engine.temperature, engine.humidity,
                                                engine.sunlightHours, 0, out _);
        yield return Send("POST", "/predict", "{}", r => json = r);
        StringAssert.Contains("\"forecast\"", json);
        Assert.AreEqual(60f, engine.soilMoisture, 1e-4f);
        Assert.IsTrue(json.Contains($"\"soil_moisture_percent\":{Mathf.Round(expected * 100f) / 100f}"), json);

        yield return Send("POST", "/advance", "{\"days\":2}", r => json = r);
        status = JsonUtility.FromJson<SimulationServer.StatusData>(json);
        Assert.AreEqual(2, status.day);
        float day2 = GrowthEngine.WaterStep(expected, 0f, 0f, engine.temperature, engine.humidity,
                                            engine.sunlightHours, 0, out _);
        Assert.AreEqual(day2, status.soil_moisture_percent, 0.006f);
        Assert.AreEqual(engine.currentScore, status.growth_score, 1e-4f);
        Assert.IsFalse(status.learned_model);   // no model JSON assigned in this test scene
    }

    [UnityTest]
    public IEnumerator DisabledServer_DoesNotListen()
    {
        server.enabled = false;
        yield return null;
        Task<HttpResponseMessage> t = http.GetAsync(Url + "/health");
        while (!t.IsCompleted) yield return null;
        Assert.IsTrue(t.IsFaulted, "a disabled SimulationServer should not answer");
    }
}
