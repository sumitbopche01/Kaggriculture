# Elite miss-seed analysis (last 3 Kaggle submissions)

## Elite pattern (kay 162k, yindujuxi 122k, Tergel 108k, …)
1. Melon densify through ~d10 (17–23 melons) *alongside* early berries
2. 6–10 cows by day 10 (before berry EV clears)
3. Plot 3 (often 4) by day 10–13, sometimes with low cash / loose empty
4. Then scale strawberries on 3–4 quads (33–53 berries midgame)

## What we lacked
- Stuck at 2 cows + 2 quads on the same seeds (need_land / cow_beats_seeds / empty_max)
- Melon planting stopped at first berry shop (`STRAWBERRY demand == 0` gate)
- LATE_BERRY hard-blocked plot-3
- Loosening plot-3 empty/money or blanket cow bridges **collapsed winners** (seed 55 → 49k, 100/777 −5–10k)

## Shipped (safe slice)
Melon→cow bridge **only** on ICE_CREAM/SMOOTHIE maps, cap 5 cows, day≤12.
- mean15 ~75.2k (flat/slightly up)
- 42/100/777/55 flat; seed 4 −4.3k (acceptable trade)
- miss seed 677151940 +9k; most 100k+ opp gaps remain

## Next levers (need more careful NPV/crew gates)
- Plot-3 when cows≥6 AND money≥land_cost AND crew can water new tiles
- Parallel melons with berry demand day≤10, capped, only if empty after berry plan
- max_quads 4 only after plot-3 pays back
