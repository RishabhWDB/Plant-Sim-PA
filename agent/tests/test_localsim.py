"""
LocalSim must step exactly like the v4 twin. These tests run it against ml/twin_core.simulate,
the loop that produced every result in the paper, on the same weather and the same plants.

  cd agent && ../ml/.venv/bin/python -m unittest discover tests
"""

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sim_backends import GrowthScorer, LocalSim, tc  # noqa: E402

DAYS = 30


def weather(days=DAYS):
    """Changing weather that exercises every part of the water balance: a wet start (drainage
    above field capacity), a hot dry spell (stress coefficient), then rain again."""
    rng = np.random.default_rng(5)
    rain = np.where(np.arange(days) < 5, 25.0, np.where(np.arange(days) < 20, 0.0, 8.0))
    return {
        "rain": rain[None, :],
        "temperature": (24 + 10 * (np.arange(days) >= 8) + rng.normal(0, 1, days))[None, :],
        "humidity": (60 - 20 * (np.arange(days) >= 8) + rng.normal(0, 2, days))[None, :],
        "sunlight_hours": (8 + 2 * (np.arange(days) >= 8))[None, :].astype(float),
        "pH": np.full((1, days), 6.3),
    }


class LocalSimMatchesTwinCore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scorer = GrowthScorer()

    def score_fn(self, env, stage):
        return np.array([self.scorer(env["pH"][i], env["soil_moisture"][i], env["sunlight_hours"][i],
                                     env["temperature"][i], env["humidity"][i], stage[i])
                         for i in range(len(stage))])

    def test_thirty_days_step_for_step(self):
        wx = weather()
        ref = tc.simulate(wx, self.score_fn, n_plants=144, offset=0.05, seed=0, record=True)
        eps = np.random.default_rng(0).uniform(-0.05, 0.05, 144)   # the plants twin_core uses

        sim = LocalSim(offsets=eps, scorer=self.scorer)
        sim.set_parameter("ph", 6.3)
        for t in range(DAYS):
            for name, key in (("rainfall", "rain"), ("temperature", "temperature"),
                              ("humidity", "humidity"), ("sunlight_hours", "sunlight_hours")):
                sim.set_parameter(name, wx[key][0, t])
            sim.step()
            r = ref["records"][t]
            self.assertEqual(sim.day, r["day"])
            self.assertAlmostEqual(sim.env["soil_moisture"], float(r["sm"][0]), places=10)
            self.assertAlmostEqual(sim.etc, float(r["etc"][0]), places=10)
            self.assertAlmostEqual(sim.score, float(r["s"][0]), places=10)
            self.assertAlmostEqual(float(sim.progress.mean()), float(r["p_mean"][0]), places=10)

    def test_soil_moisture_action_is_irrigate_to_level(self):
        sim = LocalSim(scorer=self.scorer)
        sim.set_parameter("rainfall", 0.0)
        sim.advance(3)
        sim.set_parameter("soil_moisture", 60.0)
        stage = sim.stage
        expected, _ = tc.water_step(60.0, 0.0, 0.0, sim.env["temperature"], sim.env["humidity"],
                                    sim.env["sunlight_hours"], stage)
        sim.step()
        self.assertAlmostEqual(sim.env["soil_moisture"], float(expected), places=10)

    def test_predict_changes_nothing_and_matches_next_day(self):
        sim = LocalSim(scorer=self.scorer)
        sim.advance(5)
        before = sim.state()
        p = sim.predict({"soil_moisture": 45.0})
        self.assertEqual(sim.state(), before)
        sim.set_parameter("soil_moisture", 45.0)
        sim.step()
        self.assertAlmostEqual(p["growth_score"], round(sim.score, 4), places=6)
        self.assertAlmostEqual(p["soil_moisture_percent"], round(sim.env["soil_moisture"], 2), places=6)

    def test_json_fallback_matches_pickle(self):
        if self.scorer.kind != "pickle":
            self.skipTest("surrogate_v4.pkl not available; run ml/train_model.py")
        json_scorer = GrowthScorer(use_pickle=False)
        self.assertEqual(json_scorer.kind, "json")
        rng = np.random.default_rng(1)
        for _ in range(40):
            x = [rng.uniform(3.5, 9.5), rng.uniform(5, 100), rng.uniform(0, 16),
                 rng.uniform(0, 45), rng.uniform(10, 100), int(rng.integers(0, 7))]
            self.assertAlmostEqual(self.scorer(*x), json_scorer(*x), places=9)


if __name__ == "__main__":
    unittest.main()
