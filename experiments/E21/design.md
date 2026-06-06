# E21

5 reward schedules run on NT system for 100 ticks. Each should produce a distinct final state. Punishment schedule should leave more fatigue than linear-ascending.
## еп╬щ
{
  "schedules_tested": [
    "linear_asc",
    "plateau_spike",
    "inverse_u",
    "punishment_first",
    "random"
  ],
  "arousal_range": 0.658,
  "caution_range": 0.247,
  "punishment_fatigue": 0.079,
  "linear_fatigue": 0.0,
  "fatigue_ordering_correct": true,
  "paths_diverge": true,
  "final_states": {
    "linear_asc": {
      "focus": 0.0,
      "arousal": 1.0,
      "caution": 0.0,
      "exploration": 1.0,
      "fatigue": 0.0,
      "stability": 0.0
    },
    "plateau_spike": {
      "focus": 0.0,
      "arousal": 1.0,
      "caution": 0.0,
      "exploration": 1.0,
      "fatigue": 0.0,
      "stability": 0.0
    },
    "inverse_u": {
      "focus": 0.0,
      "arousal": 0.722,
      "caution": 0.0,
      "exploration": 0.513,
      "fatigue": 0.0,
      "stability": 0.0
    },
    "punishment_first": {
      "focus": 0.0,
      "arousal": 0.342,
      "caution": 0.14,
      "exploration": 0.228,
      "fatigue": 0.079,
      "stability": 0.0
    },
    "random": {
      "focus": 0.0,
      "arousal": 0.402,
      "caution": 0.247,
      "exploration": 0.268,
      "fatigue": 0.124,
      "stability": 0.0
    }
  }
}
