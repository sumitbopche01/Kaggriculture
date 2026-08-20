# Corpus: replays/top5 (n=5)

# Replay schedule priors

Episodes mined: **5** from `replays/`.

## By archetype

### BERRY (n=5, median $=88100)
- Land1 day median **7.0**; Land2 **10.0**; 3+ quads share **100%**
- Full crew (≥10 hires) by day **7.0**; peak hands **12.0**
- Dump day median **29.0**; late(24–29) sell share **38%**
- Peaks — cows **6.0**, berry **32.0**, tomato **0.0**, wheat **42.0**
- Melon seeds on day0: **40%** of winners
- Hire curve (median): d0:6, d3:7, d6:7, d8:9, d10:10, d12:11, d15:12, d18:12

## Policy takeaways

- **Berry maps**: land1≈7.0, land2≈10.0, crew full≈d7.0, berry peak≈32.0, dump≈d29.0.
- Prefer **schedule priors by archetype** over starter-mean tuning; hire ramp and dump window are the transferable stolen schedules.

## Diff vs our agent (overlapping seeds)

- seed **2119622091** (BERRY, winner $125552 / us $94561): land [6, 10] vs us [6]; cows 9 vs 8; berry 36 vs 30; tomato 0 vs 0; hire d8 6 vs 12
- seed **1184506744** (BERRY, winner $88272 / us $78535): land [5, 8] vs us [6]; cows 4 vs 3; berry 25 vs 34; tomato 0 vs 0; hire d8 8 vs 12
- seed **757227658** (BERRY, winner $88100 / us $76918): land [7, 9] vs us [6]; cows 4 vs 6; berry 30 vs 29; tomato 0 vs 0; hire d8 9 vs 12
- seed **1295704409** (BERRY, winner $84889 / us $52942): land [7, 10] vs us [6, 12]; cows 6 vs 2; berry 40 vs 27; tomato 0 vs 20; hire d8 9 vs 12
- seed **2100766527** (BERRY, winner $52081 / us $51621): land [7, 10] vs us [7]; cows 6 vs 2; berry 32 vs 8; tomato 0 vs 24; hire d8 9 vs 12
