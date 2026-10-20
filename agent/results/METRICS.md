# Evaluation Metrics

Runs: 50  |  Seeds per cell: 5  |  Policies: No intervention, Rule-based

Seed 0 is the canonical scenario; other seeds shift event timing by up to 3 days and scale event intensity by up to 15%. Values are mean ± std across seeds.

## Overall

| Policy | Runs | Success | Death | Days to maturity | Mean score | Stress days | Interventions |
|---|---|---|---|---|---|---|---|
| No intervention | 25 | 40% | 60% | 71.5 | 0.599 | 16.1 | 0 |
| Rule-based | 25 | 100% | 0% | 70.4 | 0.877 | 3.4 | 10.2 |

## By scenario

| Scenario | Policy | Success | Days to maturity | Final progress % | Mean score | Stress days | Interventions | Days saved vs none | Gap vs rule |
|---|---|---|---|---|---|---|---|---|---|
| acid_soil | No intervention | 0% | - | 0.1 ± 0.0 | 0.421 ± 0.003 | 14.4 ± 1.1 | 0.0 | - | - |
| acid_soil | Rule-based | 100% | 68.2 ± 4.0 | 98.3 ± 0.2 | 0.881 ± 0.019 | 0.6 ± 0.9 | 16.2 ± 2.6 | - | 0.0 |
| calm | No intervention | 100% | 54.6 ± 0.5 | 98.2 ± 0.2 | 0.967 ± 0.000 | 0.0 | 0.0 | 0.0 | 1.0 |
| calm | Rule-based | 100% | 53.6 ± 0.5 | 98.3 ± 0.2 | 0.976 ± 0.001 | 0.0 | 1.0 | 1.0 | 0.0 |
| drought | No intervention | 0% | - | 0.0 ± 0.0 | 0.407 ± 0.002 | 38.6 ± 3.5 | 0.0 | - | - |
| drought | Rule-based | 100% | 66.6 ± 1.1 | 98.3 ± 0.2 | 0.890 ± 0.004 | 0.0 | 8.2 ± 0.4 | - | 0.0 |
| heatwave_storm | No intervention | 100% | 88.4 ± 4.7 | 98.2 ± 0.1 | 0.799 ± 0.015 | 2.6 ± 1.8 | 0.0 | 0.0 | 18.8 |
| heatwave_storm | Rule-based | 100% | 69.6 ± 1.1 | 98.3 ± 0.1 | 0.874 ± 0.005 | 0.0 | 10.0 ± 1.2 | 18.8 | 0.0 |
| monsoon | No intervention | 0% | - | 0.0 ± 0.0 | 0.401 ± 0.002 | 25.0 ± 3.1 | 0.0 | - | - |
| monsoon | Rule-based | 100% | 94.0 ± 5.1 | 98.2 ± 0.2 | 0.763 ± 0.021 | 16.4 ± 5.0 | 15.4 ± 0.5 | - | 0 |

## Resilience to weather events

Reaction = days from event start to first action. Recovery = days from event start until score stays ≥ 0.6 for 3 days.

| Scenario | Event | Policy | Score drop | Progress lost % | Stress days in event | Reaction (days) | Recovery (days) | Recovered |
|---|---|---|---|---|---|---|---|---|
| acid_soil | acid_rain | No intervention | 0.600 | 9.5 | 1.8 | - | - | 0% |
| acid_soil | acid_rain | Rule-based | 0.410 | 0.4 | 0.6 | 1 | 1 | 100% |
| drought | drought | No intervention | 0.950 | 1.8 | 7.6 | - | - | 0% |
| drought | drought | Rule-based | 0.230 | 0.0 | 0 | 7 | 0 | 100% |
| heatwave_storm | heatwave | No intervention | 0.810 | 0.0 | 2.6 | - | 13.6 | 100% |
| heatwave_storm | heatwave | Rule-based | 0.330 | 0.0 | 0 | 5.8 | 0 | 100% |
| heatwave_storm | storm | No intervention | 0.270 | 0.0 | 0 | - | 9.4 | 100% |
| heatwave_storm | storm | Rule-based | 0.210 | 0.0 | 0 | 1.4 | 0 | 100% |
| monsoon | monsoon | No intervention | 0.960 | 29.8 | 25 | - | - | 0% |
| monsoon | monsoon | Rule-based | 0.950 | 12.9 | 16.4 | 2.4 | 30.6 | 100% |

## Agent behaviour

No agent runs found. Run `python agent/evaluate.py --seeds 5 --include-agent` with ANTHROPIC_API_KEY set.

## Metric definitions

| Metric | Definition |
|---|---|
| Success | Crop reached 98% average progress within the season |
| Days to maturity | Day the crop matured (successful runs only) |
| Mean score | Mean daily growth score from the model (0 to 1) |
| Stress days | Days with growth score below 0.5 (crop losing progress) |
| Critical days | Days with growth score below 0.2 |
| Interventions | Equipment actions taken (each irrigation, amendment, etc.) |
| Irrigation / drainage | Water added or removed by soil_moisture actions, in mm (1.35 mm per percentage point) |
| Score drop | Mean score in the 3 days before an event minus the lowest score in the event window |
| Progress lost | Crop progress before the event minus the lowest progress during it |
| Reaction | Days from event start until the first action |
| Recovery | Days from event start until score ≥ 0.6 for 3 straight days |
| Days saved vs none | No-intervention days to maturity minus this policy's (where both matured) |
| Gap vs rule | This policy's days to maturity minus the rule baseline's (negative is better) |
| What-if per action | Digital-twin simulate_change calls per equipment action (agent) |
| Tool error rate | Share of agent tool calls that returned an error |
