"""
Small LLM client for the live agent: DeepInfra through its OpenAI-compatible endpoint.

  DEEPINFRA_API_KEY   required for real calls
  DEEPINFRA_MODEL     optional, defaults to DEFAULT_MODEL
Both are read from the environment or from .env at the repository root (see .env.example).

One call per decision, JSON reply. Any failure (network, timeout, HTTP error, invalid JSON)
returns None plus an error string, so the caller can treat it as "no action" and keep going.
FakeLLM returns a fixed, sensible reply for --dry-run and never touches the network.
"""

import json
import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv

# Settings from the repo-root .env, whatever the working directory. Variables already set in the
# environment win (override=False).
REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env", override=False)

BASE_URL = "https://api.deepinfra.com/v1/openai"
DEFAULT_MODEL = "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"

# USD per million tokens (input, output), from DeepInfra's model list, October 2026
PRICES = {
    "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo": (0.02, 0.04),
    "mistralai/Mistral-Small-24B-Instruct-2501":   (0.05, 0.08),
}

TEMPERATURE = 0.2
MAX_TOKENS = 300
TIMEOUT_S = 20
RETRIES = 1


def estimate_tokens(text):
    """Rough count (about 4 characters per token) for dry runs and prompt budgeting."""
    return max(1, len(text) // 4)


def parse_json(text):
    """The reply should be a JSON object; tolerate code fences or text around it."""
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        pass
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except ValueError:
            pass
    return None


class LLMClient:
    def __init__(self, model=None):
        from openai import OpenAI

        key = os.environ.get("DEEPINFRA_API_KEY")
        if not key:
            raise SystemExit(f"Set DEEPINFRA_API_KEY in {REPO_ROOT / '.env'} or the environment, "
                             "or use --dry-run.")
        self.model = model or os.environ.get("DEEPINFRA_MODEL", DEFAULT_MODEL)
        self.client = OpenAI(api_key=key, base_url=BASE_URL, timeout=TIMEOUT_S, max_retries=RETRIES)
        self.json_mode = True   # switched off if the model rejects response_format

    def _create(self, system, user, json_reply):
        kwargs = dict(model=self.model, temperature=TEMPERATURE, max_tokens=MAX_TOKENS,
                      messages=[{"role": "system", "content": system},
                                {"role": "user", "content": user}])
        if json_reply and self.json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        return self.client.chat.completions.create(**kwargs)

    def complete(self, system, user, json_reply=True):
        """Returns (reply, info). reply is a dict (json_reply) or a string, or None on failure.
        info has prompt_tokens, completion_tokens, latency_s and error."""
        import openai

        info = {"prompt_tokens": 0, "completion_tokens": 0, "latency_s": 0.0, "error": None}
        t0 = time.monotonic()
        try:
            try:
                resp = self._create(system, user, json_reply)
            except openai.BadRequestError as e:
                if not (json_reply and self.json_mode and "response_format" in str(e)):
                    raise
                self.json_mode = False   # the prompt still asks for JSON; parse it ourselves
                resp = self._create(system, user, json_reply)
            text = resp.choices[0].message.content or ""
            if resp.usage:
                info["prompt_tokens"] = resp.usage.prompt_tokens
                info["completion_tokens"] = resp.usage.completion_tokens
        except Exception as e:
            info["latency_s"] = round(time.monotonic() - t0, 3)
            info["error"] = f"{type(e).__name__}: {e}"[:300]
            return None, info
        info["latency_s"] = round(time.monotonic() - t0, 3)

        if not json_reply:
            return text.strip(), info
        reply = parse_json(text)
        if not isinstance(reply, dict):
            info["error"] = f"invalid JSON reply: {text[:200]!r}"
            return None, info
        return reply, info


class FakeLLM:
    """Dry-run stand-in. Always proposes the same targets (typical values for a tomato crop),
    for the two parameters that are furthest from them in actuator steps. No network calls."""

    model = "dry-run"
    TARGETS = {"soil_moisture": 55.0, "ph": 6.5, "sunlight_hours": 8.0, "humidity": 62.0}
    STEPS = {"soil_moisture": 20.0, "ph": 0.5, "sunlight_hours": 3.0, "humidity": 15.0}

    def complete(self, system, user, json_reply=True):
        info = {"prompt_tokens": estimate_tokens(system + user), "completion_tokens": 0,
                "latency_s": 0.0, "error": None}
        if not json_reply:
            text = "Dry run: no season report is written without a real model."
            info["completion_tokens"] = estimate_tokens(text)
            return text, info
        env = (parse_json(user) or {}).get("environment", {})   # the prompt is a JSON document
        gap = {k: abs(env.get(k, t) - t) / self.STEPS[k] for k, t in self.TARGETS.items()}
        actions = [{"parameter": k, "value": self.TARGETS[k]}
                   for k in sorted(gap, key=lambda k: -gap[k])[:2] if gap[k] > 0.25]
        reply = {"reasoning": "Dry run: move the furthest-off controls toward typical tomato values.",
                 "actions": actions}
        info["completion_tokens"] = estimate_tokens(json.dumps(reply))
        return reply, info
