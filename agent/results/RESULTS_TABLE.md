# Results table

Rows used in the paper and slides. Mean health is the mean daily growth score; reaction is days from a weather event's start to the first equipment action (policies that never act have none); what-if per action is twin predictions per equipment action (agent only).

## All scenarios

| Policy | Seasons | Success rate | Mean health | Reaction (days) | Actions per season | What-if per action |
|---|---|---|---|---|---|---|
| No intervention | 25 | 40% | 0.599 | - | 0 | - |
| Rule-based | 25 | 100% | 0.877 | 3.5 | 10.2 | - |
| LLM agent | 25 | 96% | 0.843 | 3.6 | 13.7 | 45.88 |
| Agent, no probes | 25 | 88% | 0.835 | 3.2 | 15.8 | 6.74 |
| Agent, no twin check | 25 | 52% | 0.657 | 1.0 | 40 | 7.27 |
| Agent, Mistral 24B | 25 | 96% | 0.869 | 2.3 | 11.6 | 47.54 |

## acid_soil

| Policy | Seasons | Success rate | Mean health | Reaction (days) | Actions per season | What-if per action |
|---|---|---|---|---|---|---|
| No intervention | 5 | 0% | 0.421 | - | 0 | - |
| Rule-based | 5 | 100% | 0.881 | 1 | 16.2 | - |
| LLM agent | 5 | 100% | 0.807 | 2.8 | 21.8 | 14.21 |
| Agent, no probes | 5 | 40% | 0.729 | 1.6 | 21 | 3.65 |
| Agent, no twin check | 5 | 40% | 0.729 | 1 | 45.4 | 7.34 |
| Agent, Mistral 24B | 5 | 100% | 0.893 | 1.6 | 19.2 | 12.05 |

## calm

| Policy | Seasons | Success rate | Mean health | Reaction (days) | Actions per season | What-if per action |
|---|---|---|---|---|---|---|
| No intervention | 5 | 100% | 0.967 | - | 0 | - |
| Rule-based | 5 | 100% | 0.976 | - | 1 | - |
| LLM agent | 5 | 100% | 0.975 | - | 1.6 | 159.85 |
| Agent, no probes | 5 | 100% | 0.969 | - | 4.4 | 17.08 |
| Agent, no twin check | 5 | 40% | 0.624 | - | 27.6 | 7.41 |
| Agent, Mistral 24B | 5 | 100% | 0.982 | - | 1 | 166.80 |

## drought

| Policy | Seasons | Success rate | Mean health | Reaction (days) | Actions per season | What-if per action |
|---|---|---|---|---|---|---|
| No intervention | 5 | 0% | 0.407 | - | 0 | - |
| Rule-based | 5 | 100% | 0.890 | 7 | 8.2 | - |
| LLM agent | 5 | 100% | 0.891 | 3.4 | 12.8 | 19.30 |
| Agent, no probes | 5 | 100% | 0.882 | 5.2 | 13.8 | 4.85 |
| Agent, no twin check | 5 | 100% | 0.783 | 1.6 | 42.2 | 6.61 |
| Agent, Mistral 24B | 5 | 100% | 0.908 | 2.2 | 9.8 | 22.19 |

## heatwave_storm

| Policy | Seasons | Success rate | Mean health | Reaction (days) | Actions per season | What-if per action |
|---|---|---|---|---|---|---|
| No intervention | 5 | 100% | 0.799 | - | 0 | - |
| Rule-based | 5 | 100% | 0.874 | 3.6 | 10 | - |
| LLM agent | 5 | 100% | 0.858 | 4.8 | 14.4 | 18.76 |
| Agent, no probes | 5 | 100% | 0.852 | 3.3 | 17 | 4.03 |
| Agent, no twin check | 5 | 20% | 0.511 | 1 | 35 | 8.10 |
| Agent, Mistral 24B | 5 | 100% | 0.880 | 2.7 | 13.6 | 17.14 |

## monsoon

| Policy | Seasons | Success rate | Mean health | Reaction (days) | Actions per season | What-if per action |
|---|---|---|---|---|---|---|
| No intervention | 5 | 0% | 0.401 | - | 0 | - |
| Rule-based | 5 | 100% | 0.763 | 2.4 | 15.4 | - |
| LLM agent | 5 | 80% | 0.681 | 2.4 | 18 | 17.29 |
| Agent, no probes | 5 | 100% | 0.742 | 2.4 | 23 | 4.08 |
| Agent, no twin check | 5 | 60% | 0.636 | 0.6 | 49.8 | 6.89 |
| Agent, Mistral 24B | 5 | 80% | 0.681 | 2.4 | 14.4 | 19.54 |
