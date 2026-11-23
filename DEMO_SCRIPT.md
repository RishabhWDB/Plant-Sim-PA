# What to say during the demo

Double-click **Demo.command** in Finder (or run `./demo.sh`). Unity opens in Play mode.
Tour the parts first (sliders, status panel, time controls, the field), then click a scenario
button at the bottom right. A season takes about 5 minutes. **Stop agent** ends it; clicking
another scenario resets the field and starts over.

## Before you click a scenario (about 30 s)

> "This is a digital twin of a crop field in Unity. It models soil water, pH, sunlight,
> temperature and humidity, and each plant grows or wilts every simulated day.
> A day passes every 4.5 seconds.
>
> An LLM, Llama 3.1 8B, manages the field. It never sees the optimal ranges. Every three
> days it reads the field, asks the twin nine what-if questions, and proposes up to two actions.
> Before anything is applied, the twin checks each action and blocks any that would make
> tomorrow worse."

## Days 0 to 15: normal weather

- Point at the **agent log** (bottom left): "This is the model's reasoning, word for word.
  The **Remedy** line is practical advice for a real farmer: precautions like mulching,
  checking drainage or scouting for pests."
- "It mostly fine-tunes or waits. Waiting is a valid decision."
- Terminal: "Each line is one decision: what it saw, what it asked for, what was applied.
  One call costs about a fiftieth of a cent."

## Around day 15: the drought starts

- "No rain, 36 °C and ten hours of sun. The agent gets this as a news item."
- Point at the **status panel** (top right): soil moisture falling, the score dropping.
- "It irrigates within a few days. The rule-based baseline waits about seven, because it
  only reacts once a variable leaves its band."

## When a veto appears (the log says vetoed or blocked)

- "Here the model proposed something the twin predicted would hurt. Only that action was
  dropped; the rest went through. The small model is cheap but sometimes wrong, and the
  twin catches it."

## Day 38 onwards: recovery

- "The drought ends. The agent relaxes its actions instead of over-correcting."

## The end: the crop matures, around day 65

- Terminal summary: success, mean crop health, number of LLM calls, cost.
- Close: "Across 150 test seasons the agent succeeded 96% of the time for about $0.0006
  a season. Without the twin check, success fell to 52%. **The model proposes, the twin decides.**"

## If you have time: `./demo.sh acid_soil`

"On acid soil the model is told pH is limiting but not which way to move it.
It sometimes tries to lower pH, and the twin vetoes it every time."

## If something breaks

Run `./demo.sh --local` (no Unity) or `./demo.sh --dry-run` (no internet).
Then say: "Same agent, same twin, running headless."
