# Results table

Rows used in the paper and slides. Mean health is the mean daily growth score; reaction is days from a weather event's start to the first equipment action (policies that never act have none); what-if per action is twin predictions per equipment action (agent only).

## All scenarios

| Policy | Seasons | Success rate | Mean health | Reaction (days) | Actions per season | What-if per action |
|---|---|---|---|---|---|---|
| No intervention | 25 | 40% | 0.599 | - | 0 | - |
| Rule-based | 25 | 100% | 0.877 | 3.5 | 10.2 | - |
| LLM agent | 25 | 88% | 0.816 | 1.8 | 16.0 | 4.78 |

## acid_soil

| Policy | Seasons | Success rate | Mean health | Reaction (days) | Actions per season | What-if per action |
|---|---|---|---|---|---|---|
| No intervention | 5 | 0% | 0.421 | - | 0 | - |
| Rule-based | 5 | 100% | 0.881 | 1 | 16.2 | - |
| LLM agent | 5 | 40% | 0.689 | 1 | 22.6 | 2.83 |

## calm

| Policy | Seasons | Success rate | Mean health | Reaction (days) | Actions per season | What-if per action |
|---|---|---|---|---|---|---|
| No intervention | 5 | 100% | 0.967 | - | 0 | - |
| Rule-based | 5 | 100% | 0.976 | - | 1 | - |
| LLM agent | 5 | 100% | 0.968 | - | 3.4 | 11.53 |

## drought

| Policy | Seasons | Success rate | Mean health | Reaction (days) | Actions per season | What-if per action |
|---|---|---|---|---|---|---|
| No intervention | 5 | 0% | 0.407 | - | 0 | - |
| Rule-based | 5 | 100% | 0.890 | 7 | 8.2 | - |
| LLM agent | 5 | 100% | 0.835 | 2.2 | 15 | 3.43 |

## heatwave_storm

| Policy | Seasons | Success rate | Mean health | Reaction (days) | Actions per season | What-if per action |
|---|---|---|---|---|---|---|
| No intervention | 5 | 100% | 0.799 | - | 0 | - |
| Rule-based | 5 | 100% | 0.874 | 3.6 | 10 | - |
| LLM agent | 5 | 100% | 0.848 | 2.4 | 13.8 | 3.58 |

## monsoon

| Policy | Seasons | Success rate | Mean health | Reaction (days) | Actions per season | What-if per action |
|---|---|---|---|---|---|---|
| No intervention | 5 | 0% | 0.401 | - | 0 | - |
| Rule-based | 5 | 100% | 0.763 | 2.4 | 15.4 | - |
| LLM agent | 5 | 100% | 0.741 | 1.2 | 25.4 | 2.52 |
