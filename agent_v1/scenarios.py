"""
Weather scenarios. Events hit the farm without warning; the policy only sees
their effects through the farm status (and a one-line news report when they start).

An event can:
  set    values applied once on its start day
  drift  values added every day while it is active (e.g. soil drying out)
  after  values applied the day after it ends (weather returning to normal)
"""

from dataclasses import dataclass, field


@dataclass
class WeatherEvent:
    name: str
    start_day: int
    end_day: int
    message: str
    set: dict = field(default_factory=dict)
    drift: dict = field(default_factory=dict)
    after: dict = field(default_factory=dict)


@dataclass
class Scenario:
    name: str
    description: str
    initial_env: dict
    events: list = field(default_factory=list)


def jittered(scenario, seed):
    """
    Returns a copy of the scenario with event timing shifted by up to 3 days and
    event magnitudes scaled by up to 15%. Seed 0 returns the canonical scenario.
    Used so multi-seed evaluation measures robustness, not one fixed script.
    """
    import copy
    import random

    if seed == 0:
        return scenario
    rng = random.Random(seed * 7919)
    s = copy.deepcopy(scenario)
    for e in s.events:
        shift = rng.randint(-3, 3)
        e.start_day = max(3, e.start_day + shift)
        e.end_day = max(e.start_day, e.end_day + shift + rng.randint(-2, 2))
        scale = rng.uniform(0.85, 1.15)
        e.drift = {k: v * scale for k, v in e.drift.items()}
    return s


NORMAL = {"ph": 6.5, "soil_moisture": 55, "sunlight_hours": 8,
          "temperature": 25, "humidity": 62, "rainfall": 40}

SCENARIOS = {
    "calm": Scenario(
        name="calm",
        description="Mild season with no weather events. Control case.",
        initial_env=dict(NORMAL),
    ),

    "drought": Scenario(
        name="drought",
        description="A long dry spell mid-season dries out soil and air.",
        initial_env=dict(NORMAL),
        events=[
            WeatherEvent(
                name="drought", start_day=15, end_day=38,
                message="Drought warning: rainfall has stopped and temperatures are climbing.",
                set={"rainfall": 3, "temperature": 36},
                drift={"soil_moisture": -4, "humidity": -2},
                after={"rainfall": 35, "temperature": 26},
            ),
        ],
    ),

    "monsoon": Scenario(
        name="monsoon",
        description="An early, very heavy monsoon waterlogs the field.",
        initial_env=dict(NORMAL),
        events=[
            WeatherEvent(
                name="monsoon", start_day=20, end_day=42,
                message="Heavy monsoon rain has arrived. Fields are flooding.",
                set={"rainfall": 110, "humidity": 92, "sunlight_hours": 4},
                drift={"soil_moisture": 5},
                after={"rainfall": 45, "sunlight_hours": 8},
            ),
        ],
    ),

    "acid_soil": Scenario(
        name="acid_soil",
        description="Poor acidic, dry, overcast plot, then acid rain mid-season.",
        initial_env={"ph": 4.4, "soil_moisture": 22, "sunlight_hours": 4.5,
                     "temperature": 24, "humidity": 58, "rainfall": 30},
        events=[
            WeatherEvent(
                name="acid_rain", start_day=30, end_day=30,
                message="Acid rain reported in the region overnight.",
                set={"rainfall": 70},
                drift={"ph": -1.2},
                after={"rainfall": 30},
            ),
        ],
    ),

    "heatwave_storm": Scenario(
        name="heatwave_storm",
        description="A heatwave followed by a week-long storm.",
        initial_env=dict(NORMAL),
        events=[
            WeatherEvent(
                name="heatwave", start_day=18, end_day=30,
                message="Heatwave: temperatures above 40 C expected for two weeks.",
                set={"temperature": 41, "rainfall": 8},
                drift={"soil_moisture": -3, "humidity": -3},
                after={"temperature": 27, "rainfall": 40},
            ),
            WeatherEvent(
                name="storm", start_day=40, end_day=47,
                message="Severe storm system: torrential rain and heavy cloud cover.",
                set={"rainfall": 105, "sunlight_hours": 3, "humidity": 88},
                drift={"soil_moisture": 6},
                after={"rainfall": 40, "sunlight_hours": 8},
            ),
        ],
    ),
}
