# Evaluation Metrics

Runs: 75  |  Seeds per cell: 5  |  Policies: No intervention, Rule-based, LLM agent

Seed 0 is the canonical scenario; other seeds shift event timing by up to 3 days and scale event intensity by up to 15%. Values are mean ± std across seeds.

## Overall

| Policy | Runs | Success | Death | Days to maturity | Mean score | Stress days | Interventions |
|---|---|---|---|---|---|---|---|
| No intervention | 25 | 40% | 60% | 71.5 | 0.599 | 16.1 | 0 |
| Rule-based | 25 | 100% | 0% | 70.4 | 0.877 | 3.4 | 10.2 |
| LLM agent | 25 | 88% | 0% | 81 | 0.816 | 5.6 | 16.0 |

## By scenario

| Scenario | Policy | Success | Days to maturity | Final progress % | Mean score | Stress days | Interventions | Days saved vs none | Gap vs rule |
|---|---|---|---|---|---|---|---|---|---|
| acid_soil | No intervention | 0% | - | 0.1 ± 0.0 | 0.421 ± 0.003 | 14.4 ± 1.1 | 0.0 | - | - |
| acid_soil | Rule-based | 100% | 68.2 ± 4.0 | 98.3 ± 0.2 | 0.881 ± 0.019 | 0.6 ± 0.9 | 16.2 ± 2.6 | - | 0.0 |
| acid_soil | LLM agent | 40% | 118.0 ± 2.8 | 86.3 ± 17.5 | 0.689 ± 0.051 | 3.8 ± 4.1 | 22.6 ± 6.0 | - | 49.8 |
| calm | No intervention | 100% | 54.6 ± 0.5 | 98.2 ± 0.2 | 0.967 ± 0.000 | 0.0 | 0.0 | 0.0 | 1.0 |
| calm | Rule-based | 100% | 53.6 ± 0.5 | 98.3 ± 0.2 | 0.976 ± 0.001 | 0.0 | 1.0 | 1.0 | 0.0 |
| calm | LLM agent | 100% | 54.6 ± 0.5 | 98.3 ± 0.1 | 0.968 ± 0.006 | 0.0 | 3.4 ± 1.7 | 0.0 | 1.0 |
| drought | No intervention | 0% | - | 0.0 ± 0.0 | 0.407 ± 0.002 | 38.6 ± 3.5 | 0.0 | - | - |
| drought | Rule-based | 100% | 66.6 ± 1.1 | 98.3 ± 0.2 | 0.890 ± 0.004 | 0.0 | 8.2 ± 0.4 | - | 0.0 |
| drought | LLM agent | 100% | 78.2 ± 9.0 | 98.3 ± 0.1 | 0.835 ± 0.036 | 3.4 ± 4.2 | 15.0 ± 3.4 | - | 11.6 |
| heatwave_storm | No intervention | 100% | 88.4 ± 4.7 | 98.2 ± 0.1 | 0.799 ± 0.015 | 2.6 ± 1.8 | 0.0 | 0.0 | 18.8 |
| heatwave_storm | Rule-based | 100% | 69.6 ± 1.1 | 98.3 ± 0.1 | 0.874 ± 0.005 | 0.0 | 10.0 ± 1.2 | 18.8 | 0.0 |
| heatwave_storm | LLM agent | 100% | 75.4 ± 2.3 | 98.3 ± 0.1 | 0.848 ± 0.009 | 0.2 ± 0.4 | 13.8 ± 3.8 | 13.0 | 5.8 |
| monsoon | No intervention | 0% | - | 0.0 ± 0.0 | 0.401 ± 0.002 | 25.0 ± 3.1 | 0.0 | - | - |
| monsoon | Rule-based | 100% | 94.0 ± 5.1 | 98.2 ± 0.2 | 0.763 ± 0.021 | 16.4 ± 5.0 | 15.4 ± 0.5 | - | 0 |
| monsoon | LLM agent | 100% | 101.0 ± 6.2 | 98.3 ± 0.2 | 0.741 ± 0.027 | 20.8 ± 2.4 | 25.4 ± 3.5 | - | 7 |

## Resilience to weather events

Reaction = days from event start to first action. Recovery = days from event start until score stays ≥ 0.6 for 3 days.

| Scenario | Event | Policy | Score drop | Progress lost % | Stress days in event | Reaction (days) | Recovery (days) | Recovered |
|---|---|---|---|---|---|---|---|---|
| acid_soil | acid_rain | No intervention | 0.600 | 9.5 | 1.8 | - | - | 0% |
| acid_soil | acid_rain | Rule-based | 0.410 | 0.4 | 0.6 | 1 | 1 | 100% |
| acid_soil | acid_rain | LLM agent | 0.590 | 4.6 | 1.6 | 1 | 9.2 | 100% |
| drought | drought | No intervention | 0.950 | 1.8 | 7.6 | - | - | 0% |
| drought | drought | Rule-based | 0.230 | 0.0 | 0 | 7 | 0 | 100% |
| drought | drought | LLM agent | 0.640 | 0.0 | 2.6 | 2.2 | 14.8 | 100% |
| heatwave_storm | heatwave | No intervention | 0.810 | 0.0 | 2.6 | - | 13.6 | 100% |
| heatwave_storm | heatwave | Rule-based | 0.330 | 0.0 | 0 | 5.8 | 0 | 100% |
| heatwave_storm | heatwave | LLM agent | 0.450 | 0.0 | 0.2 | 3.4 | 13.6 | 100% |
| heatwave_storm | storm | No intervention | 0.270 | 0.0 | 0 | - | 9.4 | 100% |
| heatwave_storm | storm | Rule-based | 0.210 | 0.0 | 0 | 1.4 | 0 | 100% |
| heatwave_storm | storm | LLM agent | 0.160 | 0.0 | 0 | 1.4 | 1.4 | 100% |
| monsoon | monsoon | No intervention | 0.960 | 29.8 | 25 | - | - | 0% |
| monsoon | monsoon | Rule-based | 0.950 | 12.9 | 16.4 | 2.4 | 30.6 | 100% |
| monsoon | monsoon | LLM agent | 0.960 | 18.2 | 20.8 | 1.2 | 31.2 | 100% |

## Agent behaviour

| Scenario | LLM calls | Rejected by twin | Error rate | What-if per action | Prompt tokens per call | Input tokens | Output tokens | Latency (s) | Cost (USD) |
|---|---|---|---|---|---|---|---|---|---|
| acid_soil | 39.8 ± 0.4 | 14.6 | 0% | 2.83 | 728 | 28976 | 2707 | 2.04 | 0.00070 |
| calm | 18.6 ± 0.5 | 14.6 | 2% | 11.53 | 732 | 13617 | 1374 | 3.02 | 0.00030 |
| drought | 26.4 ± 3.0 | 15.4 | 8% | 3.43 | 738 | 19487 | 1948 | 1.49 | 0.00050 |
| heatwave_storm | 25.6 ± 0.9 | 14.4 | 5% | 3.58 | 739 | 18907 | 1902 | 2.91 | 0.00050 |
| monsoon | 34.2 ± 1.9 | 14.2 | 2% | 2.52 | 740 | 25303 | 2494 | 1.44 | 0.00060 |

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
| What-if per action | Twin next-day predictions used to check plans, per equipment action (agent) |
| Rejected by twin | Decisions whose plan the twin predicted would lower tomorrow's score by more than 0.02 |
| Error rate | Share of agent decisions with an LLM failure or an invalid reply |
