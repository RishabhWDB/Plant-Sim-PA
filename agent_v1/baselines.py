"""
Baselines the LLM agent is compared against.

NoInterventionPolicy  never touches the controls (what happens if nobody manages the farm).
RuleBasedPolicy       classic threshold controller that knows the true optimal ranges and
                      pushes any out-of-range parameter back to the middle every few days.
                      This is a strong baseline: it has information the LLM agent does not.
"""

OPTIMAL_BANDS = {
    "soil_moisture":  (40, 70),
    "ph":             (6.0, 7.0),
    "sunlight_hours": (6, 10),
    "humidity":       (50, 75),
}


class NoInterventionPolicy:
    name = "none"

    def run(self, env):
        while not env.done:
            env.advance(10)
        return env.summary()


class RuleBasedPolicy:
    name = "rule"

    def __init__(self, check_every_days=3):
        self.check_every_days = check_every_days

    def run(self, env):
        while not env.done:
            for param, (lo, hi) in OPTIMAL_BANDS.items():
                value = float(env.env[param])
                if not lo <= value <= hi:
                    env.adjust(param, (lo + hi) / 2,
                               reason=f"outside band {lo}-{hi}", source="rule")
            env.advance(self.check_every_days)
        return env.summary()
