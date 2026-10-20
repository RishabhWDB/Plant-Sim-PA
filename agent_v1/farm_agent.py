"""
LLM farm manager agent.

The agent runs an observe -> diagnose -> plan -> act -> wait loop using tool calls.
It is NOT given the crop's optimal ranges. It has to use its own agronomy knowledge
and the digital twin's what-if tool (simulate_change) to work out what to do.
"""

import json
import os

TOOLS = [
    {
        "name": "get_farm_status",
        "description": (
            "Observe the farm. Returns the day, growth score (0 to 1, below 0.5 means plants are "
            "losing health), health zone, growth rate, average crop progress, growth stage, "
            "predicted outcome and days to it, current environment values and active weather."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "simulate_change",
        "description": (
            "Ask the digital twin what growth score the crop WOULD have under changed conditions, "
            "without changing anything. Use it to test hypotheses before acting, or to diagnose "
            "which parameter is hurting the crop by trying each one at a better value. "
            "You may include weather parameters to understand their effect, but you cannot change them."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "changes": {
                    "type": "object",
                    "description": "Parameter name to hypothetical value, e.g. {\"soil_moisture\": 55}",
                    "additionalProperties": {"type": "number"},
                }
            },
            "required": ["changes"],
        },
    },
    {
        "name": "adjust_control",
        "description": (
            "Change one controllable parameter using farm equipment. Each action is limited in how "
            "far it can move the value; if the limit is hit the value moves as far as allowed and "
            "you can act again. Controllable: soil_moisture (irrigation/drainage, max 20 per action), "
            "ph (lime/sulfur, max 0.5 per action), sunlight_hours (grow lights/shade netting, "
            "max 3 per action), humidity (misting/ventilation, max 15 per action). "
            "temperature and rainfall are weather and cannot be changed. "
            "Every action has a real-world cost, so avoid unnecessary changes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "parameter": {"type": "string",
                              "enum": ["soil_moisture", "ph", "sunlight_hours", "humidity"]},
                "value": {"type": "number", "description": "Target value"},
                "reason": {"type": "string", "description": "One short sentence explaining why"},
            },
            "required": ["parameter", "value", "reason"],
        },
    },
    {
        "name": "advance_days",
        "description": (
            "Let time pass for 1 to 10 days and see what happened. Weather can change without "
            "warning while time passes, and it keeps acting every day (for example soil drying out "
            "during a drought), so use short steps when conditions are unstable."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"days": {"type": "integer", "minimum": 1, "maximum": 10}},
            "required": ["days"],
        },
    },
]

SYSTEM_PROMPT = """You are an autonomous farm manager responsible for a field of 144 tomato-like plants \
in a digital twin simulation. A season lasts {max_days} days.

Goal, in priority order:
1. Keep the crop alive.
2. Bring it to full maturity as quickly as possible.
3. Use as few equipment actions as you reasonably can.

How the world works:
- Each day the crop gets a growth score from 0 to 1. Above 0.5 the plants grow, below 0.5 they \
lose progress. Higher is faster. If progress falls to zero after the crop has established, it dies.
- You control soil_moisture, ph, sunlight_hours and humidity, with limited change per action.
- temperature and rainfall are weather. You cannot change them, but you can compensate with the \
controls you do have (for example irrigating during a drought, draining during floods).
- Weather events arrive without warning and keep acting every day while they last.
- You are not told the crop's ideal ranges. Use your agronomy knowledge and the simulate_change \
tool to find out what helps. simulate_change is free; equipment actions are not.

Work in a loop: observe, diagnose what is limiting growth, test fixes with simulate_change, act, \
then advance time. Advance in larger steps (5 to 10 days) when conditions are stable and the score \
is high, and in small steps (1 to 3 days) during weather events or when the score is below 0.6. \
Before each action, state your reasoning in one or two short sentences."""


class LLMFarmAgent:
    name = "agent"

    def __init__(self, model=None, max_llm_calls=150, max_tokens=1500, verbose=True):
        try:
            import anthropic
        except ImportError:
            raise SystemExit("Install the Anthropic SDK first: pip install anthropic")
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise SystemExit("Set ANTHROPIC_API_KEY to run the LLM agent.")
        self.client = anthropic.Anthropic()
        self.model = model or os.environ.get("AGENT_MODEL", "claude-sonnet-5-5")
        self.max_llm_calls = max_llm_calls
        self.max_tokens = max_tokens
        self.verbose = verbose
        self.llm_calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.season_report = ""

    # ------------------------------------------------------------------ tools

    def _dispatch(self, env, name, args):
        if name == "get_farm_status":
            return env.status()
        if name == "simulate_change":
            return env.predict(args.get("changes", {}))
        if name == "adjust_control":
            return env.adjust(args["parameter"], args["value"], args.get("reason", ""), source="agent")
        if name == "advance_days":
            return env.advance(args.get("days", 1))
        raise ValueError(f"Unknown tool {name}")

    def _call(self, env, messages, tool_choice=None):
        kwargs = dict(
            model=self.model,
            max_tokens=self.max_tokens,
            system=SYSTEM_PROMPT.format(max_days=env.max_days),
            tools=TOOLS,
            messages=messages,
        )
        if tool_choice:
            kwargs["tool_choice"] = tool_choice
        resp = self.client.messages.create(**kwargs)
        self.llm_calls += 1
        self.input_tokens += resp.usage.input_tokens
        self.output_tokens += resp.usage.output_tokens
        return resp

    # ------------------------------------------------------------------ loop

    def run(self, env):
        status = env.status()
        messages = [{
            "role": "user",
            "content": "The season is starting. Current farm status:\n"
                       + json.dumps(status, indent=2)
                       + "\n\nManage the farm until the crop matures or the season ends.",
        }]

        while not env.done and self.llm_calls < self.max_llm_calls:
            resp = self._call(env, messages)
            messages.append({"role": "assistant", "content": resp.content})

            for block in resp.content:
                if block.type == "text" and block.text.strip():
                    thought = block.text.strip()
                    if self.verbose:
                        print(f"\n[agent] {thought}")
                    env.sim.log(thought.split("\n")[0][:200])

            if resp.stop_reason != "tool_use":
                messages.append({"role": "user", "content":
                                 "The season is still running. Keep managing the farm with your tools. "
                                 "Status: " + json.dumps(env.status())})
                continue

            results = []
            for block in resp.content:
                if block.type != "tool_use":
                    continue
                day_before = env.day
                try:
                    out = self._dispatch(env, block.name, block.input)
                    results.append({"type": "tool_result", "tool_use_id": block.id,
                                    "content": json.dumps(out)})
                    env.record({"type": "tool_call", "day": day_before, "tool": block.name,
                                "input": block.input, "error": False})
                except Exception as e:
                    results.append({"type": "tool_result", "tool_use_id": block.id,
                                    "content": f"Error: {e}", "is_error": True})
                    env.record({"type": "tool_call", "day": day_before, "tool": block.name,
                                "input": block.input, "error": True, "message": str(e)})
            messages.append({"role": "user", "content": results})

        summary = env.summary()
        self.season_report = self._final_report(env, messages, summary)

        summary.update({
            "llm_calls": self.llm_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "model": self.model,
        })
        return summary

    def _final_report(self, env, messages, summary):
        prompt = {"type": "text", "text":
                  "The season is over. Final result:\n" + json.dumps(summary, indent=2)
                  + "\n\nWrite a short season report: what happened, your key decisions and "
                    "why, and what you would do differently next season."}
        if messages[-1]["role"] == "user" and isinstance(messages[-1]["content"], list):
            messages[-1]["content"].append(prompt)
        else:
            messages.append({"role": "user", "content": [prompt]})
        try:
            resp = self._call(env, messages, tool_choice={"type": "none"})
            report = "\n".join(b.text for b in resp.content if b.type == "text")
        except Exception as e:
            report = f"(Could not generate report: {e})"
        if self.verbose:
            print("\n===== Agent season report =====\n" + report)
        return report
