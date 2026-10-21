# Plot-3 timing from top / softfloor winners (2026-08-21)

## Elite schedule (who bought 3rd land)

Corpus `schedules_raw_softfloor100k.jsonl` — **51/51** winners have land2 (3+ quads):

| Signal | Softfloor $100k+ | Named top5 | Ladder elites |
|--------|------------------|------------|---------------|
| Land1 day | **6–7** | 5–7 | ~7–8 |
| **Land2 (plot-3) day** | **10** (40×) / 11 (11×) | **8–10** | **9–11** |
| Peak cows | **8** | 4–9 | ~10 |
| Berry peak | **35** | ~32 | ~22 |
| Full crew (≥10) | **d8** | d7 | d8 |
| Dump day | **28** | 29 | ~27 |
| Melon day0 | **100%** | — | 83% |

Winners in softfloor set: `structured`, `frontier_soil`, `top10_read`, `hamburger`, `boatlee_v16`.

Named ladder examples with land2:
- **kay.liechtenstein** — land `[6,11]`, 10 cows, 34 berry, ~162k
- **ReCurSiON** — `[6,10]`, 9 cows, 36 berry, ~126k
- **yindujuxi** — `[7,10]`, 10 cows, 37 berry
- **Tergel** — `[8,10,11]` (plot-4!), 8 cows, 53 berry

Hire spike on land2 day is common (frontier: **14 hires on d10**).

## Where we stuck

Softfloor sample before fix: **plot3 2/9**, often cows@d10=4–6 but stay 2q.

**Seed 33 smoking gun** (cows=6, empty=20, melons=11, money≥3.4k, day 9):
- `need_land` pieces all green (stand, cows, empty_max)
- blocked by `land_blocked_by_board_fill` — densify rule forbids land while hollow
- Elites **buy land while hollow**; we were forced to fill first → never expand

Miss traces (`analysis/kaggle_eps/miss_traces.json`): same pattern — land1 @d6, stall 2q, cows~2–3 @d10.

## Change landed

1. `_softfloor_calendar_land_ready` — day∈[land2_min, hollow_max], empty≥20, cows≥6, melon/berry/tomato stand
2. Bypass `land_blocked_by_board_fill` when calendar ready
3. Unlock hollow `empty_max` on that path

Keep elite hire priors (softfloor early hire curve is thinner and crashed densify 42/89).

## After this change

| Panel | plot3 | notes |
|-------|------:|-------|
| Softfloor seeds | **3/9** (was 2/9) | seed **33** now plot3 |
| Densify guards 42/7/89/55 | OK | ~90k / 90k / 95k / 90k |

## Live elite decode (2026-08-21, structured/frontier/top10 × seeds 12/33/3141)

Median day curve (9 games):

| day | cows | hands | berry | empty |
|----:|-----:|------:|------:|------:|
| 6 | 3 | 5 | 5 | 22 (post-land1) |
| 7 | **6** | 9 | 8 | 10 |
| 8 | 7 | 9 | 11 | 2 |
| 9 | **8** | 12 | 11 | 2 |
| 10 | 8 | 12 | 18 | 10 (land2) |
| 12 | 10 | 11 | 34 | 4 |
| dump | | | | **28–29** (structured/frontier); top10 often **21** |

Seed **33** smoking gun (shop unlocks are path-dependent):
- **frontier**: pizza+bakery → plant berry from d6 → smoothie unlocks → 172k, empty@d16=2, cows=8
- **us**: pizza+pet → tomato densify → ice cream → ~64k, berry@d16=0, hollow

## Changes tried (this session)

1. **Post-land1 herd burst** toward 6–8 cows — raised plot3 count but crashed densify 7/55 and softfloor mean (~80k→73k). Left off (`post_land2_cow_day_max=-1`). Curve coded in `brain.schedules.softfloor_cow_target_day`.
2. **Speculative berry** before berry shops — buys+plants work on seed 33 (berry@d16→14) but densify 55 crashed and softfloor mean did not lift. Left off (`softfloor_speculative_berry=0`); code path retained for map-router.
3. **Dump prior** — softfloor median **28** preferred in `late_dump_day()` when softfloor corpus present.

## Softfloor map router (landed 2026-08-21)

`brain.map.softfloor_mode_active` gates herd + speculative berry:

| Gate | Rule |
|------|------|
| Off | `EARLY_BERRY` densify |
| Off | `LATE_BERRY` without pizza (seed 55 yarn+bakery) |
| Off | `LAND_SPRINT` / `UNKNOWN` / `MILK_STACK` unless empty≥20 |
| On | pizza `LATE_BERRY` with empty≥16; deep-hollow others |

Policy: `_softfloor_mode` adds labor gate; enables `softfloor_speculative_berry` + herd schedule (`softfloor_herd_day_max=10`) only when routed.

| Panel | before router | after router |
|-------|--------------:|-------------:|
| Densify 42/7/89/55 | 91.8k | **91.8k** (55 restored) |
| Softfloor mean | 80.6k | **~81.2k** |
| Seed 33 | ~63.8k hollow | **~74.6k** berry@d16=5 |

### Still open
1. Push seed 33 berry toward elite ~32 and restore plot3 without spending land cash
2. Herd to 8 by d9 on routed boards (currently cows@d10 still ~4)
3. Dump window already prefers softfloor d28 prior
4. Never wholesale-load softfloor hire curve

### Landed earlier: post-plot-3 crew + seed fill
- `MAX_HANDS=13`; `_land2_crew_spike` when 3q + empty≥16
- Softfloor mean was **~80.6k** plot3 **3/9** before router priors
