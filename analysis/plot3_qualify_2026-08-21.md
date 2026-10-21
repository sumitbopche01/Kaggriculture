# Plot3 qualify probe (Phase 0) — 2026-08-21

## Softfloor labels

| seed | score | cows@10 | label | mode_on d7-10 |
|-----:|------:|--------:|-------|---------------|
| 12 | 80958 | 4 | `ROUTER_OFF` | 0/4 |
| 21 | 84404 | 5 | `SHED_BLOCK` | 3/4 |
| 33 | 77217 | 8 | `OK_HERD` | 3/4 |
| 123 | 85324 | 4 | `ROUTER_OFF` | 0/4 |
| 2024 | 83219 | 6 | `OK_HERD` | 2/4 |
| 3141 | 84234 | 4 | `ROUTER_OFF` | 0/4 |
| 993781610 | 84909 | 4 | `ROUTER_OFF` | 0/4 |
| 49090797 | 74877 | 3 | `ROUTER_OFF` | 0/4 |
| 1827862996 | 74496 | 4 | `ROUTER_OFF` | 0/4 |

**Label counts:** {'ROUTER_OFF': 6, 'SHED_BLOCK': 1, 'OK_HERD': 2}

## Densify softfloor_mode (must stay mostly off)

| seed | score | cows@10 | mode_on d7-10 |
|-----:|------:|--------:|---------------|
| 42 | 90021 | 4 | 0/4 |
| 7 | 90595 | 4 | 0/4 |
| 89 | 95578 | 4 | 0/4 |
| 55 | 90897 | 3 | 0/4 |

## Dawn detail (softfloor d6–d12)

### seed 12 — `ROUTER_OFF`
- d6: q=1 empty=4 cows=2 want=2 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=0 melon=11 need=True cal=False $1508
- d7: q=1 empty=4 cows=2 want=2 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=0 melon=11 need=True cal=False $3442
- d8: q=2 empty=14 cows=3 want=4 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=13 melon=11 need=False cal=False $947
- d9: q=2 empty=14 cows=3 want=4 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=13 melon=11 need=False cal=False $511
- d10: q=2 empty=6 cows=4 want=5 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=18 melon=11 need=False cal=False $1580
- d11: q=2 empty=6 cows=4 want=5 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=18 melon=9 need=False cal=False $1573
- d12: q=2 empty=7 cows=4 want=5 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=20 melon=5 need=False cal=False $4105

### seed 21 — `SHED_BLOCK`
- d6: q=1 empty=0 cows=2 want=2 mode=False act=False strat=UNKNOWN shedC=0 past=0 berry=0 melon=12 need=True cal=False $1408
- d7: q=2 empty=22 cows=3 want=3 mode=True act=True strat=UNKNOWN shedC=1 past=0 berry=0 melon=12 need=False cal=False $814
- d8: q=2 empty=17 cows=3 want=4 mode=True act=True strat=UNKNOWN shedC=0 past=0 berry=0 melon=12 need=False cal=False $398
- d9: q=2 empty=17 cows=3 want=4 mode=True act=True strat=UNKNOWN shedC=0 past=0 berry=0 melon=12 need=False cal=False $352
- d10: q=2 empty=11 cows=5 want=6 mode=False act=False strat=UNKNOWN shedC=1 past=0 berry=3 melon=12 need=False cal=False $1548
- d11: q=2 empty=10 cows=5 want=6 mode=False act=False strat=UNKNOWN shedC=0 past=0 berry=3 melon=10 need=False cal=False $3892
- d12: q=2 empty=11 cows=5 want=6 mode=False act=False strat=UNKNOWN shedC=0 past=1 berry=4 melon=6 need=False cal=False $5747

### seed 33 — `OK_HERD`
- d6: q=1 empty=3 cows=2 want=2 mode=False act=False strat=UNKNOWN shedC=0 past=0 berry=0 melon=11 need=True cal=False $1498
- d7: q=2 empty=27 cows=3 want=4 mode=True act=True strat=UNKNOWN shedC=1 past=0 berry=0 melon=11 need=False cal=False $747
- d8: q=2 empty=17 cows=6 want=6 mode=True act=True strat=UNKNOWN shedC=0 past=0 berry=1 melon=11 need=False cal=False $439
- d9: q=2 empty=16 cows=6 want=7 mode=True act=True strat=UNKNOWN shedC=0 past=0 berry=1 melon=11 need=False cal=False $353
- d10: q=2 empty=15 cows=8 want=8 mode=False act=False strat=UNKNOWN shedC=2 past=0 berry=2 melon=11 need=False cal=False $1532
- d11: q=2 empty=15 cows=8 want=8 mode=False act=False strat=UNKNOWN shedC=0 past=0 berry=3 melon=9 need=False cal=False $2594
- d12: q=2 empty=15 cows=8 want=8 mode=False act=False strat=UNKNOWN shedC=0 past=0 berry=4 melon=5 need=False cal=False $6472

### seed 123 — `ROUTER_OFF`
- d6: q=1 empty=4 cows=2 want=2 mode=False act=False strat=LAND_SPRINT shedC=0 past=0 berry=0 melon=11 need=True cal=False $1508
- d7: q=1 empty=4 cows=2 want=2 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=0 melon=11 need=True cal=False $3442
- d8: q=2 empty=14 cows=3 want=4 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=13 melon=11 need=False cal=False $947
- d9: q=2 empty=14 cows=3 want=4 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=13 melon=11 need=False cal=False $511
- d10: q=2 empty=10 cows=4 want=5 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=15 melon=11 need=False cal=False $1586
- d11: q=2 empty=9 cows=5 want=6 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=16 melon=9 need=False cal=False $1530
- d12: q=2 empty=8 cows=6 want=7 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=19 melon=5 need=True cal=False $3313

### seed 2024 — `OK_HERD`
- d6: q=1 empty=3 cows=2 want=3 mode=False act=False strat=UNKNOWN shedC=0 past=0 berry=0 melon=11 need=True cal=False $1498
- d7: q=2 empty=25 cows=4 want=4 mode=True act=True strat=UNKNOWN shedC=2 past=0 berry=0 melon=11 need=False cal=False $433
- d8: q=2 empty=18 cows=5 want=5 mode=True act=True strat=UNKNOWN shedC=2 past=0 berry=3 melon=11 need=False cal=False $544
- d9: q=2 empty=15 cows=5 want=6 mode=False act=False strat=UNKNOWN shedC=0 past=0 berry=3 melon=11 need=False cal=False $373
- d10: q=2 empty=15 cows=6 want=7 mode=False act=False strat=LAND_SPRINT shedC=0 past=0 berry=3 melon=11 need=False cal=False $1837
- d11: q=2 empty=16 cows=7 want=8 mode=False act=False strat=LAND_SPRINT shedC=0 past=0 berry=3 melon=9 need=False cal=False $2438
- d12: q=2 empty=15 cows=7 want=8 mode=False act=False strat=LAND_SPRINT shedC=0 past=0 berry=3 melon=5 need=False cal=False $6112

### seed 3141 — `ROUTER_OFF`
- d6: q=1 empty=4 cows=2 want=2 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=0 melon=11 need=True cal=False $1508
- d7: q=1 empty=4 cows=2 want=2 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=0 melon=11 need=True cal=False $3442
- d8: q=2 empty=14 cows=3 want=4 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=13 melon=11 need=False cal=False $947
- d9: q=2 empty=14 cows=3 want=4 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=13 melon=11 need=False cal=False $511
- d10: q=2 empty=6 cows=4 want=5 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=18 melon=11 need=False cal=False $1580
- d11: q=2 empty=5 cows=5 want=6 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=18 melon=9 need=False cal=False $1552
- d12: q=2 empty=6 cows=6 want=7 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=19 melon=5 need=True cal=False $3884

### seed 993781610 — `ROUTER_OFF`
- d6: q=1 empty=4 cows=2 want=2 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=0 melon=11 need=True cal=False $1508
- d7: q=1 empty=4 cows=2 want=2 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=0 melon=11 need=True cal=False $3442
- d8: q=2 empty=14 cows=3 want=4 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=13 melon=11 need=False cal=False $947
- d9: q=2 empty=14 cows=3 want=4 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=13 melon=11 need=False cal=False $511
- d10: q=2 empty=5 cows=4 want=5 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=18 melon=11 need=False cal=False $1515
- d11: q=2 empty=5 cows=5 want=6 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=18 melon=9 need=False cal=False $1532
- d12: q=2 empty=6 cows=6 want=7 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=19 melon=5 need=True cal=False $3864

### seed 49090797 — `ROUTER_OFF`
- d6: q=1 empty=4 cows=2 want=2 mode=False act=False strat=LAND_SPRINT shedC=0 past=0 berry=0 melon=11 need=True cal=False $1498
- d7: q=2 empty=24 cows=2 want=3 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=4 melon=11 need=False cal=False $960
- d8: q=2 empty=11 cows=2 want=3 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=17 melon=11 need=False cal=False $574
- d9: q=2 empty=10 cows=2 want=3 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=17 melon=11 need=False cal=False $148
- d10: q=2 empty=6 cows=3 want=4 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=19 melon=11 need=False cal=False $1550
- d11: q=2 empty=6 cows=4 want=5 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=19 melon=9 need=False cal=False $714
- d12: q=2 empty=5 cows=5 want=6 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=23 melon=5 need=False cal=False $3026

### seed 1827862996 — `ROUTER_OFF`
- d6: q=1 empty=4 cows=2 want=2 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=0 melon=11 need=True cal=False $1508
- d7: q=1 empty=4 cows=2 want=2 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=0 melon=11 need=True cal=False $3442
- d8: q=2 empty=14 cows=3 want=4 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=13 melon=11 need=False cal=False $947
- d9: q=2 empty=14 cows=3 want=4 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=13 melon=11 need=False cal=False $511
- d10: q=2 empty=10 cows=4 want=5 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=15 melon=11 need=False cal=False $1586
- d11: q=2 empty=9 cows=5 want=6 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=16 melon=9 need=False cal=False $1530
- d12: q=2 empty=8 cows=6 want=7 mode=False act=False strat=EARLY_BERRY shedC=0 past=0 berry=19 melon=5 need=True cal=False $3250

## Phase 1 outcome

- **1a:** `UNKNOWN` softfloor routes at empty≥14 (`LAND_SPRINT` stays ≥20 — densify 55 safe).
- **1c:** softfloor-only shed-busy cow buy (`_softfloor_mode`). Densify flat. Scoped routed herd: 33→8 cows, 2024→6, 21→5 (2/3 ≥6).

## One-line summary

Dominant softfloor cause (Phase 0): **`ROUTER_OFF`** (6/9). Densify mode_on should stay low. Phase 1 fork: 1a router.

## Phase 2 outcome

- Added `_plot3_packed_ready` / `_plot3_hollow_ready`; `_land_cow_min` returns 4 only under `_softfloor_mode`.
- Hollow force-buy (thin cash / land_npv=1 / force pick) **reverted** — densify packed late plot3 (−15k) and softfloor mean collapse.
- Final softfloor: mean **~82.1k** (HEAD ~81k), plot3 **2/9**, cows@10 on routed seeds improved (33/2024 ≥6). Densify flat.

## Phase 3 outcome

- Post-plot3 berry sprint **reverted** (seed 33 mean crash, berry@d16 fell).
- Existing `land2` hire spike retained; no densify-safe fill change found this pass.

## Ladder keep/revert (mandatory)

| build | vs | WR | mean_margin | mean_us |
|-------|----|----|-------------|---------|
| HEAD | structured | 0/20 | −54324 | 47937 |
| WT (Phase 0–2) | structured | 0/20 | −50272 | 46700 |
| WT | boatlee_v16 | 0/20 | −73738 | 44710 |

**Keep:** densify flat, softfloor mean ≥ HEAD, ladder WR flat (0%) with slightly better margin vs structured. Do not ship hollow force-buy.

## Phase 4

Skipped — EARLY_BERRY softfloor already plants berry before/at land1; land1 pack not the blocker.

## Densify-3 fill package (attempted, reverted)

**Probe (plot3 seeds 3141/13/…):** hire spike already works (8–9 HIREs/dawn); seeds sit idle; empty stalls ~20 because water stress blocks planting on a fat berry stand (~22–30) after late land2 (~d13).

**Tried:** plant-under-stress / split-crew plant slots on `n_quads≥3`. Empty@d16 improved (20→10–16), berry↑, but scores −4–11k on those seeds; softfloor mean dipped. Phantom-hire “fix” aborted densify (−70k) — daily rehire is required by the game.

**Keep:** Phase 1–2 only (router UNKNOWN@14 + softfloor shed-buy + packed/hollow helpers). No densify-3 field change yet.

**Next package candidate:** earlier hollow buy (thinner stand at land2) so densify-3 water debt is manageable — fill after buy only works when stand isn’t already maxed.
