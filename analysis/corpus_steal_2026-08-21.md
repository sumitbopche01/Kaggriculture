# Multi-corpus schedule steal (2026-08-21)

## Corpora compared

| Corpus | n | land1 | land2 | 3q% | crew | hands | dump | cows | berry | melon0 |
|--------|--:|------:|------:|----:|-----:|------:|-----:|-----:|------:|-------:|
| elite / ladder85k | 12 | 8 | 10.5 | 75% | d8 | 10 | 27.5 | 9.5 | 22 | 83% |
| top5 | 5 | 7 | 10 | 100% | d7 | 12 | 29 | 6 | 32 | 40% |
| softfloor $100k | 46 | 6 | 10 | 100% | d8 | 13 | 28 | 8 | 35 | 100% |
| tomato85k | 12 | 9 | 8.5 | 17% | d9 | 11 | 29 | 10 | 4 | 75% |
| all60k | 29 | 6 | 11 | 86% | d8 | 12 | 28 | 10 | 22 | 69% |

Hire early (d0/3/6/8/10): elite 5/8/9/9/9 — top5 6/7/7/9/10 — softfloor 5/5/4/9/12 (thin early).

## Live H2H (hamburger / boatlee_v16 / kaito_v27 × seeds 42/33/21/89/3141)

| Bot | land | dump | cows@10 | berry@16 | empty@16 | hands@8 |
|-----|------|------|--------:|---------:|---------:|--------:|
| hamburger | [7,10] | 12* | 6 | ~39 | 6 | 11 |
| boatlee_v16 | [6,10] | 29 | **8** | ~36 | 2 | 7 |
| kaito_v27 | [6,10] | 29 | **8** | ~36 | 0 | 7 |

\*hamburger peak sell day is early (ongoing sells), not endgame dump.

Boatlee/kaito cow median: d6:3 → d7:6 → **d8:8** (faster than prior softfloor d8:7).

## Steals applied (router-gated)

1. Softfloor cow curve → boatlee/kaito (d8=8)
2. `late_dump_day` / `berry_land2_day` median across softfloor+top5+elite
3. Softfloor-mode hire uses top5 curve (full crew ~d7) without loading softfloor thin early hire globally

## Eval

- mean30 (before this steal pass): **81,322** · plot3 6/30 · cows@d10 3.5
- After wiring (densify-safe / softfloor-routed): densify guards **91.8k** unchanged; mean30 **81,322** unchanged (most mean30 seeds are EARLY_BERRY densify and skip the router); softfloor **~81.2k**

Mean30 is densify-dominated — softfloor schedule steals barely move it. Ladder H2H / softfloor panel is the right gauge for these priors.
