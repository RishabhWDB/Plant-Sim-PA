# Evaluation Metrics

Runs: 150  |  Seeds per cell: 5  |  Policies: No intervention, Rule-based, LLM agent, Agent, no probes, Agent, no twin check, Agent, Mistral 24B

Seed 0 is the canonical scenario; other seeds shift event timing by up to 3 days and scale event intensity by up to 15%. Values are mean ± std across seeds.

## Overall

| Policy | Runs | Success | Death | Days to maturity | Mean score | Stress days | Interventions |
|---|---|---|---|---|---|---|---|
| No intervention | 25 | 40% | 60% | 71.5 | 0.599 | 16.1 | 0 |
| Rule-based | 25 | 100% | 0% | 70.4 | 0.877 | 3.4 | 10.2 |
| LLM agent | 25 | 96% | 4% | 74.7 | 0.843 | 5.8 | 13.7 |
| Agent, no probes | 25 | 88% | 0% | 77.2 | 0.835 | 5.0 | 15.8 |
| Agent, no twin check | 25 | 52% | 16% | 93.7 | 0.657 | 19.9 | 40 |
| Agent, Mistral 24B | 25 | 96% | 4% | 68.8 | 0.869 | 4.9 | 11.6 |

## By scenario

| Scenario | Policy | Success | Days to maturity | Final progress % | Mean score | Stress days | Interventions | Days saved vs none | Gap vs rule |
|---|---|---|---|---|---|---|---|---|---|
| acid_soil | No intervention | 0% | - | 0.1 ± 0.0 | 0.421 ± 0.003 | 14.4 ± 1.1 | 0.0 | - | - |
| acid_soil | Rule-based | 100% | 68.2 ± 4.0 | 98.3 ± 0.2 | 0.881 ± 0.019 | 0.6 ± 0.9 | 16.2 ± 2.6 | - | 0.0 |
| acid_soil | LLM agent | 100% | 86.2 ± 12.2 | 98.1 ± 0.1 | 0.807 ± 0.043 | 2.6 ± 3.8 | 21.8 ± 4.4 | - | 18.0 |
| acid_soil | Agent, no probes | 40% | 108.0 ± 7.1 | 96.9 ± 1.7 | 0.729 ± 0.023 | 2.4 ± 2.5 | 21.0 ± 2.2 | - | 39.8 |
| acid_soil | Agent, no twin check | 40% | 95.5 ± 13.4 | 94.8 ± 3.7 | 0.729 ± 0.050 | 6.8 ± 4.0 | 45.4 ± 7.7 | - | 27.3 |
| acid_soil | Agent, Mistral 24B | 100% | 65.8 ± 3.1 | 98.3 ± 0.1 | 0.893 ± 0.017 | 0.6 ± 0.9 | 19.2 ± 2.0 | - | -2.4 |
| calm | No intervention | 100% | 54.6 ± 0.5 | 98.2 ± 0.2 | 0.967 ± 0.000 | 0.0 | 0.0 | 0.0 | 1.0 |
| calm | Rule-based | 100% | 53.6 ± 0.5 | 98.3 ± 0.2 | 0.976 ± 0.001 | 0.0 | 1.0 | 1.0 | 0.0 |
| calm | LLM agent | 100% | 53.8 ± 0.8 | 98.4 ± 0.2 | 0.975 ± 0.004 | 0.0 | 1.6 ± 1.3 | 0.8 | 0.2 |
| calm | Agent, no probes | 100% | 54.6 ± 1.1 | 98.4 ± 0.2 | 0.969 ± 0.009 | 0.0 | 4.4 ± 2.9 | 0.0 | 1.0 |
| calm | Agent, no twin check | 40% | 70.0 | 50.2 ± 49.1 | 0.624 ± 0.234 | 17.4 ± 19.5 | 27.6 ± 15.2 | -15.4 | 16.4 |
| calm | Agent, Mistral 24B | 100% | 53.2 ± 0.4 | 98.5 ± 0.2 | 0.982 ± 0.000 | 0.0 | 1.0 | 1.4 | -0.4 |
| drought | No intervention | 0% | - | 0.0 ± 0.0 | 0.407 ± 0.002 | 38.6 ± 3.5 | 0.0 | - | - |
| drought | Rule-based | 100% | 66.6 ± 1.1 | 98.3 ± 0.2 | 0.890 ± 0.004 | 0.0 | 8.2 ± 0.4 | - | 0.0 |
| drought | LLM agent | 100% | 66.4 ± 1.9 | 98.3 ± 0.2 | 0.891 ± 0.009 | 0.0 | 12.8 ± 1.8 | - | -0.2 |
| drought | Agent, no probes | 100% | 68.2 ± 2.0 | 98.3 ± 0.2 | 0.882 ± 0.011 | 0.0 | 13.8 ± 2.4 | - | 1.6 |
| drought | Agent, no twin check | 100% | 92.0 ± 15.0 | 98.0 ± 0.0 | 0.783 ± 0.053 | 9.2 ± 7.5 | 42.2 ± 6.9 | - | 25.4 |
| drought | Agent, Mistral 24B | 100% | 63.6 ± 0.5 | 98.4 ± 0.1 | 0.908 ± 0.002 | 0.0 | 9.8 ± 1.5 | - | -3.0 |
| heatwave_storm | No intervention | 100% | 88.4 ± 4.7 | 98.2 ± 0.1 | 0.799 ± 0.015 | 2.6 ± 1.8 | 0.0 | 0.0 | 18.8 |
| heatwave_storm | Rule-based | 100% | 69.6 ± 1.1 | 98.3 ± 0.1 | 0.874 ± 0.005 | 0.0 | 10.0 ± 1.2 | 18.8 | 0.0 |
| heatwave_storm | LLM agent | 100% | 73.0 ± 5.1 | 98.3 ± 0.2 | 0.858 ± 0.023 | 1.6 ± 2.2 | 14.4 ± 2.4 | 15.4 | 3.4 |
| heatwave_storm | Agent, no probes | 100% | 74.2 ± 3.2 | 98.2 ± 0.2 | 0.852 ± 0.013 | 0.2 ± 0.4 | 17.0 ± 2.9 | 14.2 | 4.6 |
| heatwave_storm | Agent, no twin check | 20% | 106.0 | 28.9 ± 41.6 | 0.511 ± 0.140 | 34.6 ± 22.8 | 35.0 ± 18.9 | -17.6 | 36.4 |
| heatwave_storm | Agent, Mistral 24B | 100% | 68.6 ± 1.1 | 98.4 ± 0.2 | 0.880 ± 0.005 | 0.0 | 13.6 ± 0.9 | 19.8 | -1.0 |
| monsoon | No intervention | 0% | - | 0.0 ± 0.0 | 0.401 ± 0.002 | 25.0 ± 3.1 | 0.0 | - | - |
| monsoon | Rule-based | 100% | 94.0 ± 5.1 | 98.2 ± 0.2 | 0.763 ± 0.021 | 16.4 ± 5.0 | 15.4 ± 0.5 | - | 0 |
| monsoon | LLM agent | 80% | 98.8 ± 5.0 | 78.6 ± 43.9 | 0.681 ± 0.151 | 24.6 ± 5.8 | 18.0 ± 3.4 | - | 4.8 |
| monsoon | Agent, no probes | 100% | 99.6 ± 2.7 | 98.3 ± 0.2 | 0.742 ± 0.018 | 22.2 ± 2.5 | 23.0 ± 3.2 | - | 5.6 |
| monsoon | Agent, no twin check | 60% | 107.0 ± 6.2 | 70.1 ± 41.2 | 0.636 ± 0.127 | 31.6 ± 17.4 | 49.8 ± 5.9 | - | 13 |
| monsoon | Agent, Mistral 24B | 80% | 98.8 ± 1.0 | 78.7 ± 44.0 | 0.681 ± 0.150 | 24.0 ± 4.1 | 14.4 ± 2.7 | - | 4.8 |

## Resilience to weather events

Reaction = days from event start to first action. Recovery = days from event start until score stays ≥ 0.6 for 3 days.

| Scenario | Event | Policy | Score drop | Progress lost % | Stress days in event | Reaction (days) | Recovery (days) | Recovered |
|---|---|---|---|---|---|---|---|---|
| acid_soil | acid_rain | No intervention | 0.600 | 9.5 | 1.8 | - | - | 0% |
| acid_soil | acid_rain | Rule-based | 0.410 | 0.4 | 0.6 | 1 | 1 | 100% |
| acid_soil | acid_rain | LLM agent | 0.550 | 2.5 | 1 | 2.8 | 3 | 100% |
| acid_soil | acid_rain | Agent, no probes | 0.560 | 3.2 | 1.4 | 1.6 | 2.6 | 100% |
| acid_soil | acid_rain | Agent, no twin check | 0.600 | 3.9 | 1.4 | 1 | 5 | 100% |
| acid_soil | acid_rain | Agent, Mistral 24B | 0.430 | 0.4 | 0.6 | 1.6 | 1 | 100% |
| drought | drought | No intervention | 0.950 | 1.8 | 7.6 | - | - | 0% |
| drought | drought | Rule-based | 0.230 | 0.0 | 0 | 7 | 0 | 100% |
| drought | drought | LLM agent | 0.280 | 0.0 | 0 | 3.4 | 0 | 100% |
| drought | drought | Agent, no probes | 0.310 | 0.0 | 0 | 5.2 | 0 | 100% |
| drought | drought | Agent, no twin check | 0.730 | 2.1 | 7 | 1.6 | 14.2 | 100% |
| drought | drought | Agent, Mistral 24B | 0.200 | 0.0 | 0 | 2.2 | 0 | 100% |
| heatwave_storm | heatwave | No intervention | 0.810 | 0.0 | 2.6 | - | 13.6 | 100% |
| heatwave_storm | heatwave | Rule-based | 0.330 | 0.0 | 0 | 5.8 | 0 | 100% |
| heatwave_storm | heatwave | LLM agent | 0.530 | 0.0 | 1.6 | 8.2 | 5.8 | 100% |
| heatwave_storm | heatwave | Agent, no probes | 0.400 | 0.0 | 0.2 | 4 | 8.4 | 100% |
| heatwave_storm | heatwave | Agent, no twin check | 0.850 | 8.0 | 9 | 1 | 14.2 | 100% |
| heatwave_storm | heatwave | Agent, Mistral 24B | 0.300 | 0.0 | 0 | 4 | 0 | 100% |
| heatwave_storm | storm | No intervention | 0.270 | 0.0 | 0 | - | 9.4 | 100% |
| heatwave_storm | storm | Rule-based | 0.210 | 0.0 | 0 | 1.4 | 0 | 100% |
| heatwave_storm | storm | LLM agent | 0.280 | 0.0 | 0 | 1.4 | 1.4 | 100% |
| heatwave_storm | storm | Agent, no probes | 0.290 | 0.0 | 0 | 2.6 | 2.6 | 100% |
| heatwave_storm | storm | Agent, no twin check | 0.240 | 0.0 | 0 | 1 | 2.2 | 100% |
| heatwave_storm | storm | Agent, Mistral 24B | 0.270 | 0.0 | 0 | 1.4 | 0 | 100% |
| monsoon | monsoon | No intervention | 0.960 | 29.8 | 25 | - | - | 0% |
| monsoon | monsoon | Rule-based | 0.950 | 12.9 | 16.4 | 2.4 | 30.6 | 100% |
| monsoon | monsoon | LLM agent | 0.960 | 21.3 | 24.6 | 2.4 | 30.8 | 80% |
| monsoon | monsoon | Agent, no probes | 0.960 | 20.2 | 22.2 | 2.4 | 31 | 100% |
| monsoon | monsoon | Agent, no twin check | 0.870 | 18.1 | 20.2 | 0.6 | 31 | 100% |
| monsoon | monsoon | Agent, Mistral 24B | 0.960 | 22.4 | 24 | 2.4 | 30.8 | 80% |

## Agent behaviour

| Policy | Scenario | LLM calls | Rejected by twin | Error rate | What-if per action | Prompt tokens per call | Input tokens | Output tokens | Latency (s) | Cost (USD) |
|---|---|---|---|---|---|---|---|---|---|---|
| LLM agent | acid_soil | 30.0 ± 4.3 | 10.8 | 1% | 14.21 | 893 | 26594 | 2456 | 2.99 | 0.00060 |
| Agent, no probes | acid_soil | 39.6 ± 2.2 | 15.2 | 0% | 3.65 | 777 | 30830 | 2905 | 2.80 | 0.00070 |
| Agent, no twin check | acid_soil | 37.8 ± 4.9 | 0 | 0% | 7.34 | 889 | 33566 | 3010 | 3.01 | 0.00080 |
| Agent, Mistral 24B | acid_soil | 23.2 ± 1.3 | 3 | 0% | 12.05 | 995 | 22713 | 1907 | 2.62 | 0.00130 |
| LLM agent | calm | 19.2 ± 0.4 | 14.6 | 3% | 159.85 | 896 | 16850 | 1759 | 5.45 | 0.00040 |
| Agent, no probes | calm | 19.6 ± 0.5 | 15.8 | 2% | 17.08 | 793 | 15303 | 1717 | 3.47 | 0.00040 |
| Agent, no twin check | calm | 23.6 ± 12.8 | 0 | 2% | 7.41 | 875 | 20472 | 1930 | 2.89 | 0.00050 |
| Agent, Mistral 24B | calm | 19.0 | 2.8 | 0% | 166.80 | 963 | 17763 | 1225 | 1.06 | 0.00100 |
| LLM agent | drought | 23.4 ± 0.5 | 14.8 | 6% | 19.30 | 901 | 20830 | 2095 | 4.88 | 0.00050 |
| Agent, no probes | drought | 24.2 ± 0.8 | 14.8 | 8% | 4.85 | 797 | 19138 | 2099 | 3.80 | 0.00050 |
| Agent, no twin check | drought | 32.0 ± 5.1 | 0 | 6% | 6.61 | 890 | 28355 | 2590 | 3.13 | 0.00070 |
| Agent, Mistral 24B | drought | 22.6 ± 0.5 | 5 | 0% | 22.19 | 989 | 21933 | 1803 | 1.53 | 0.00120 |
| LLM agent | heatwave_storm | 25.6 ± 1.8 | 13.6 | 8% | 18.76 | 898 | 22749 | 2206 | 2.82 | 0.00050 |
| Agent, no probes | heatwave_storm | 26.0 ± 1.0 | 14.2 | 9% | 4.03 | 793 | 20518 | 2201 | 2.81 | 0.00050 |
| Agent, no twin check | heatwave_storm | 32.0 ± 15.3 | 0 | 2% | 8.10 | 875 | 27780 | 2414 | 3.49 | 0.00070 |
| Agent, Mistral 24B | heatwave_storm | 24.2 ± 0.4 | 3.8 | 3% | 17.14 | 981 | 22827 | 1840 | 4.69 | 0.00130 |
| LLM agent | monsoon | 30.6 ± 8.3 | 15.6 | 1% | 17.29 | 895 | 27322 | 2476 | 2.62 | 0.00060 |
| Agent, no probes | monsoon | 34.6 ± 1.1 | 18.6 | 1% | 4.08 | 797 | 27654 | 2750 | 2.49 | 0.00070 |
| Agent, no twin check | monsoon | 38.8 ± 2.5 | 0 | 2% | 6.89 | 886 | 34398 | 2981 | 2.48 | 0.00080 |
| Agent, Mistral 24B | monsoon | 30.4 ± 8.6 | 3 | 0% | 19.54 | 975 | 29415 | 2289 | 1.74 | 0.00170 |

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
