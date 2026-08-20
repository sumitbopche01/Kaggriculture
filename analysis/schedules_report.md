# Replay schedule priors

Episodes mined: **20** from `replays/`.

## By archetype

### BERRY (n=20, median $=59332)
- Land1 day median **6.0**; Land2 **11.0**; 3+ quads share **100%**
- Full crew (≥10 hires) by day **8.0**; peak hands **12.0**
- Dump day median **27.0**; late(24–29) sell share **26%**
- Peaks — cows **10.0**, berry **11.0**, tomato **0.0**, wheat **16.0**
- Melon seeds on day0: **85%** of winners
- Hire curve (median): d0:5, d3:5, d6:4, d8:12, d10:12, d12:12, d15:12, d18:12

## Policy takeaways

- **Berry maps**: land1≈6.0, land2≈11.0, crew full≈d8.0, berry peak≈11.0, dump≈d27.0.
- Prefer **schedule priors by archetype** over starter-mean tuning; hire ramp and dump window are the transferable stolen schedules.

## Diff vs our agent (overlapping seeds)

- seed **1941500822** (BERRY, winner $104489 / us $57569): land [0, 9] vs us [6]; cows 8 vs 2; berry 28 vs 40; tomato 0 vs 0; hire d8 5 vs 12
- seed **456398262** (BERRY, winner $101454 / us $52118): land [6, 11] vs us [7]; cows 6 vs 2; berry 34 vs 40; tomato 0 vs 0; hire d8 11 vs 12
- seed **1012421698** (BERRY, winner $100232 / us $48749): land [6, 10] vs us [6]; cows 10 vs 4; berry 41 vs 14; tomato 0 vs 17; hire d8 10 vs 12
- seed **1571069459** (BERRY, winner $98553 / us $70947): land [7, 10] vs us [6]; cows 6 vs 6; berry 39 vs 33; tomato 0 vs 0; hire d8 9 vs 12
- seed **25138847** (BERRY, winner $93155 / us $80131): land [6, 11] vs us [6]; cows 10 vs 5; berry 16 vs 36; tomato 0 vs 0; hire d8 12 vs 12
