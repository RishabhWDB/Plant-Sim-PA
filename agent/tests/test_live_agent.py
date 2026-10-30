"""
The live agent must never crash the loop and must only apply plans the twin does not expect to
hurt. These tests use scripted LLM replies; nothing calls DeepInfra.

  cd agent && ../ml/.venv/bin/python -m unittest discover tests
"""

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import llm_client  # noqa: E402
from farm_env import FarmEnvironment  # noqa: E402
from live_agent import LiveAgent  # noqa: E402
from scenarios import SCENARIOS  # noqa: E402
from sim_backends import GrowthScorer, LocalSim  # noqa: E402

SCORER = GrowthScorer()
ENVS = []    # closed after the tests, so their run logs are not left open


def tearDownModule():
    for env in ENVS:
        env.close()


class ScriptedLLM:
    model = "scripted"

    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []

    def complete(self, system, user, json_reply=True):
        self.prompts.append(user)
        info = {"prompt_tokens": 100, "completion_tokens": 10, "latency_s": 0.0, "error": None}
        if not json_reply:
            return "report", info
        r = self.replies.pop(0) if self.replies else {"reasoning": "wait", "actions": []}
        if isinstance(r, Exception):
            info["error"] = str(r)
            return None, info
        return r, info


def make_env(scenario="drought", days=None):
    tmp = tempfile.mkdtemp()
    env = FarmEnvironment(LocalSim(scorer=SCORER), SCENARIOS[scenario], log_dir=tmp, run_name="t",
                          verbose=False, max_days=days or 120)
    env.reset()
    ENVS.append(env)
    return env


def ticks(env):
    with open(env.log_path) as f:
        return [json.loads(l) for l in f if '"type": "tick"' in l]


class LiveAgentDecisions(unittest.TestCase):
    def test_harmful_plan_is_rejected_by_twin(self):
        env = make_env()
        agent = LiveAgent(ScriptedLLM([{"reasoning": "dry it out",
                                        "actions": [{"parameter": "soil_moisture", "value": 5}]}]),
                          verbose=False)
        before = env.status()["environment"]["soil_moisture"]
        agent.decide(env, env.status())
        t = ticks(env)[-1]
        self.assertTrue(t["rejected_by_twin"])
        self.assertEqual(t["actions_applied"], {})
        self.assertEqual(env.status()["environment"]["soil_moisture"], before)
        self.assertEqual(agent.rejected, 1)

    def test_failures_and_bad_replies_mean_no_action(self):
        env = make_env()
        replies = [RuntimeError("timeout"),
                   {"reasoning": "rain please", "actions": [{"parameter": "rainfall", "value": 20}]},
                   {"reasoning": "x", "actions": "not a list"},
                   {"reasoning": "x", "actions": [{"parameter": "ph", "value": "high"}]}]
        agent = LiveAgent(ScriptedLLM(replies), verbose=False)
        for _ in replies:
            agent.decide(env, env.status())
        for t in ticks(env):
            self.assertEqual(t["actions_applied"], {})
            self.assertTrue(t["error"])
        self.assertEqual(len(env.interventions), 0)
        self.assertEqual(agent.llm_errors, 1)

    def test_at_most_two_actions_clipped_to_actuator_limits(self):
        env = make_env("acid_soil")
        agent = LiveAgent(ScriptedLLM([{"reasoning": "fix soil", "actions": [
            {"parameter": "ph", "value": 6.5}, {"parameter": "sunlight_hours", "value": 8},
            {"parameter": "soil_moisture", "value": 55}]}]), verbose=False)
        agent.decide(env, env.status())
        t = ticks(env)[-1]
        self.assertEqual(set(t["actions_applied"]), {"ph", "sunlight_hours"})
        self.assertAlmostEqual(t["actions_applied"]["ph"], 4.4 + 0.5)       # actuator limit 0.5
        self.assertAlmostEqual(t["actions_applied"]["sunlight_hours"], 4.5 + 3.0)
        self.assertIn("only the first 2", t["error"])

    def test_prompt_is_compact_and_hides_the_optima(self):
        env = make_env()
        llm = ScriptedLLM([])
        agent = LiveAgent(llm, verbose=False)
        for _ in range(4):
            agent.decide(env, env.status())
            env.advance(3)
        from live_agent import SYSTEM_PROMPT
        user = llm.prompts[-1]
        self.assertLess(llm_client.estimate_tokens(SYSTEM_PROMPT + user), 1200)
        self.assertEqual(len(json.loads(user)["recent_decisions"]), 3)
        for hidden in ("40", "70", "6.0", "7.0", "optimal range"):
            self.assertNotIn(hidden, SYSTEM_PROMPT)

    def test_probes_show_the_twin_score_at_both_ends_of_each_control(self):
        env = make_env("acid_soil")
        llm = ScriptedLLM([])
        LiveAgent(llm, verbose=False).decide(env, env.status())
        msg = json.loads(llm.prompts[-1])
        keep = env.predict({})["growth_score"]
        for p, c in msg["controls"].items():
            table = c["twin_tomorrow"]
            low, high = c["can_set_to"]
            self.assertAlmostEqual(table[f"{low:g}"], env.predict({p: low})["growth_score"], places=3)
            self.assertAlmostEqual(table[f"{c['now']:g}"], keep, places=3)
            self.assertAlmostEqual(table[f"{high:g}"], env.predict({p: high})["growth_score"], places=3)
        # acid soil: raising pH helps, lowering it hurts
        ph = msg["controls"]["ph"]["twin_tomorrow"]
        self.assertEqual(list(ph), ["3.9", "4.4", "4.9"])
        self.assertGreater(ph["4.9"], ph["4.4"])
        self.assertLess(ph["3.9"], ph["4.4"])

    def test_harmful_action_cannot_ride_along_with_a_helpful_one(self):
        env = make_env("acid_soil")
        agent = LiveAgent(ScriptedLLM([{"reasoning": "irrigate, and lower pH", "actions": [
            {"parameter": "soil_moisture", "value": 50}, {"parameter": "ph", "value": 3.9}]}]), verbose=False)
        agent.decide(env, env.status())
        t = ticks(env)[-1]
        self.assertEqual(set(t["actions_applied"]), {"soil_moisture"})
        self.assertEqual(t["rejected_actions"], ["ph"])
        self.assertTrue(t["rejected_by_twin"])
        self.assertEqual(env.status()["environment"]["ph"], 4.4)

    def test_variants_switch_probes_and_twin_check_off(self):
        env = make_env()
        llm = ScriptedLLM([])
        LiveAgent(llm, verbose=False, probes=False).decide(env, env.status())
        msg = json.loads(llm.prompts[-1])
        self.assertNotIn("twin_tomorrow", msg["controls"]["ph"])

        env = make_env()
        agent = LiveAgent(ScriptedLLM([{"reasoning": "dry it out",
                                        "actions": [{"parameter": "soil_moisture", "value": 5}]}]),
                          verbose=False, twin_check=False)
        agent.decide(env, env.status())
        t = ticks(env)[-1]
        self.assertFalse(t["rejected_by_twin"])
        self.assertIn("soil_moisture", t["actions_applied"])

    def test_every_variant_builds_a_policy(self):
        from live_agent import VARIANTS
        from run import make_policy
        for name in VARIANTS:
            agent = make_policy(name, {"dry_run": True}, verbose=False)
            self.assertIsInstance(agent, LiveAgent)
        self.assertFalse(make_policy("agent_noprobe", {"dry_run": True}).probes)
        self.assertFalse(make_policy("agent_nocheck", {"dry_run": True}).twin_check)

    def test_realtime_season_applies_weather_and_finishes(self):
        class ClockedSim(LocalSim):
            """A LocalSim whose clock runs on its own: one day passes per state read."""
            running = False

            def resume(self):
                self.running = True
                return {"ok": True}

            def pause(self):
                self.running = False
                return {"ok": True}

            def state(self):
                if self.running:
                    self.step()
                return super().state()

        tmp = tempfile.mkdtemp()
        env = FarmEnvironment(ClockedSim(scorer=SCORER), SCENARIOS["drought"], log_dir=tmp,
                              run_name="rt", verbose=False)
        env.reset()
        self.addCleanup(env.close)
        agent = LiveAgent(llm_client.FakeLLM(), tick_seconds=0.0, verbose=False)
        summary = agent.run_realtime(env, poll_seconds=0.0)
        self.assertIn(summary["outcome"], ("matured", "dead", "season_ended"))
        self.assertIn("drought", env.events_seen)
        self.assertGreater(summary["llm_calls"], 1)
        self.assertFalse(env.sim.running)


class ClientFailures(unittest.TestCase):
    def client(self):
        c = llm_client.LLMClient.__new__(llm_client.LLMClient)
        c.model, c.json_mode = "test-model", True
        return c

    def reply(self, text):
        msg = types.SimpleNamespace(content=text)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)],
                                     usage=types.SimpleNamespace(prompt_tokens=50, completion_tokens=5))

    def test_invalid_json_is_no_action(self):
        c = self.client()
        c._create = lambda s, u, j: self.reply("I think you should irrigate.")
        reply, info = c.complete("s", "u")
        self.assertIsNone(reply)
        self.assertIn("invalid JSON", info["error"])

    def test_json_inside_text_is_accepted(self):
        c = self.client()
        c._create = lambda s, u, j: self.reply('Sure:\n```json\n{"reasoning": "ok", "actions": []}\n```')
        reply, _ = c.complete("s", "u")
        self.assertEqual(reply, {"reasoning": "ok", "actions": []})

    def test_api_errors_never_raise(self):
        c = self.client()

        def boom(s, u, j):
            raise TimeoutError("20 s timeout")
        c._create = boom
        reply, info = c.complete("s", "u")
        self.assertIsNone(reply)
        self.assertIn("TimeoutError", info["error"])

    def test_json_mode_falls_back_when_unsupported(self):
        import httpx2
        import openai
        c = self.client()
        calls = []

        def create(s, u, j):
            calls.append(c.json_mode)
            if c.json_mode:
                req = httpx2.Request("POST", "https://api.deepinfra.com/v1/openai/chat/completions")
                raise openai.BadRequestError("response_format json_object is not supported",
                                             response=httpx2.Response(400, request=req), body=None)
            return self.reply('{"reasoning": "ok", "actions": []}')
        c._create = create
        reply, info = c.complete("s", "u")
        self.assertEqual(reply["reasoning"], "ok")
        self.assertEqual(calls, [True, False])
        self.assertFalse(c.json_mode)


if __name__ == "__main__":
    unittest.main()
