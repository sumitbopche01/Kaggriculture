# Elite densify-3 decode + package (2026-08-21)

## Live elite vs us (softfloor seeds 33/12/2024/3141/993781610)

Bots: structured, frontier_soil, top10_read, boatlee_v16, hamburger vs starter.

### Elite post-land2 medians (25 plot3 games)

| Signal | Median | Note |
|--------|-------:|------|
| Hire on land2 day | **12** | range 11–14 |
| Hire land2+1 | **10** | keep crew |
| Berry gain in 2d | **+16** | 20→36 typical (boatlee/frontier) |
| Empty at L2 dawn | often **0–3** | many buy packed; hollow buyers also exist |
| Empty L2+2 | **~2–4** best bots | after +25 from buy |

Best pattern (boatlee/frontier seed 33): buy at empty≈0 berry≈20, hire 14, next dawn empty=6 berry=31, d+2 empty=2 berry=36.

### Us gap (3141 / 993781610 — only seeds that plot3)

| | hire L2/L2+1 | berry +2d | empty path |
|--|-------------:|----------:|------------|
| Elite | 12–14 / 10 | +16 | →2–4 |
| Us | 13 / 13 | **+9** | 6→30→20 (stays hollow) |

Hire count was fine; **berry fill of the new plot** was the miss (tomato/leftover priority).

## Package shipped: densify-3 fill

Softfloor/post-3q only (`n_quads≥3`, `empty≥12`, `day≤15`):

1. `crop_plan` — strawberry owns leftover until target **34**
2. Seed buy — strawberry first; stockpile up to 16 after land; lower cash keep
3. Hire — target/burst **13/12** (elite land2 day); `land2_hire_empty_min` **12**
4. Field — `plant_sprint` + `berry_waiting` when densify3 (keep water stress on)

**Tried and reverted:** disabling `water_stress` under densify3 → berry@d16 40 but score −14k (underwater).

Hard guard: densify `[42,7,89,55]` ≤3k.

### Eval after package (keep)

| Panel | Result |
|-------|--------|
| Densify 42/7/89/55 | flat (~90/90/95/90k) |
| Softfloor mean | **81.7k** (prior ~82.1k) |
| Plot3 games berry@d16 | **29 / 32** (elite ~33–36) |
| Plot3 games empty@d16 | **20 / 20** (elite best ~2–4) — still the gap |

**Keep** densify-3 crop/hire/seed package. Empty pack still fails because we buy land2 late (d12) mid-day and water debt blocks plant rate; next package = earlier qualified buy + water-aware fill, not more plant-over-water.

Raw: `analysis/elite_densify3_2026-08-21.json`
