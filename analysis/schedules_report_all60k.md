# Corpus: replays, replays/top5, replays/v2, replays/ladder_elites (n=29)

# Replay schedule priors

Episodes mined: **29** from `replays/`.

## By archetype

### BERRY (n=29, median $=93650)
- Land1 day median **6.0**; Land2 **11.0**; 3+ quads share **86%**
- Full crew (≥10 hires) by day **8.0**; peak hands **12.0**
- Dump day median **28.0**; late(24–29) sell share **35%**
- Peaks — cows **10.0**, berry **22.0**, tomato **0.0**, wheat **20.0**
- Melon seeds on day0: **69%** of winners
- Hire curve (median): d0:5, d3:5, d6:6, d8:9, d10:10, d12:11, d15:12, d18:12

## Policy takeaways

- **Berry maps**: land1≈6.0, land2≈11.0, crew full≈d8.0, berry peak≈22.0, dump≈d28.0.
- Prefer **schedule priors by archetype** over starter-mean tuning; hire ramp and dump window are the transferable stolen schedules.
