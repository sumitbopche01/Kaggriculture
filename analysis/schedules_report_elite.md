# Corpus: replays/top5, replays (n=8)

# Replay schedule priors

Episodes mined: **8** from `replays/`.

## By archetype

### BERRY (n=8, median $=99392)
- Land1 day median **6.0**; Land2 **10.0**; 3+ quads share **100%**
- Full crew (≥10 hires) by day **7.5**; peak hands **12.0**
- Dump day median **28.0**; late(24–29) sell share **38%**
- Peaks — cows **6.0**, berry **35.0**, tomato **0.0**, wheat **34.5**
- Melon seeds on day0: **50%** of winners
- Hire curve (median): d0:5, d3:6, d6:6, d8:9, d10:10, d12:10, d15:12, d18:12

## Policy takeaways

- **Berry maps**: land1≈6.0, land2≈10.0, crew full≈d7.5, berry peak≈35.0, dump≈d28.0.
- Prefer **schedule priors by archetype** over starter-mean tuning; hire ramp and dump window are the transferable stolen schedules.

## Diff vs our agent (overlapping seeds)

- seed **2119622091** (BERRY, winner $125552 / us $94561): land [6, 10] vs us [6]; cows 9 vs 8; berry 36 vs 30; tomato 0 vs 0; hire d8 6 vs 12
- seed **1941500822** (BERRY, winner $104489 / us $70674): land [0, 9] vs us [7]; cows 8 vs 6; berry 28 vs 0; tomato 0 vs 19; hire d8 5 vs 12
- seed **456398262** (BERRY, winner $101454 / us $77319): land [6, 11] vs us [6]; cows 6 vs 6; berry 34 vs 31; tomato 0 vs 0; hire d8 11 vs 12
- seed **1012421698** (BERRY, winner $100232 / us $70947): land [6, 10] vs us [6]; cows 10 vs 3; berry 41 vs 30; tomato 0 vs 0; hire d8 10 vs 12
- seed **1571069459** (BERRY, winner $98553 / us $84381): land [7, 10] vs us [6]; cows 6 vs 4; berry 39 vs 34; tomato 0 vs 0; hire d8 9 vs 12
- seed **1184506744** (BERRY, winner $88272 / us $78535): land [5, 8] vs us [6]; cows 4 vs 3; berry 25 vs 34; tomato 0 vs 0; hire d8 8 vs 12
- seed **757227658** (BERRY, winner $88100 / us $76918): land [7, 9] vs us [6]; cows 4 vs 6; berry 30 vs 29; tomato 0 vs 0; hire d8 9 vs 12
- seed **1295704409** (BERRY, winner $84889 / us $52942): land [7, 10] vs us [6, 12]; cows 6 vs 2; berry 40 vs 27; tomato 0 vs 20; hire d8 9 vs 12
