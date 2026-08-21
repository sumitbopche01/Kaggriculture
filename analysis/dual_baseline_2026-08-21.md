# Dual baseline + step-2 herd attempt (2026-08-21)

## Dual scorecard (pre step-2 policy; current agent)

| Panel | mean | plot3+ | ≥90k | cows@d10 |
|-------|-----:|-------:|-----:|---------:|
| densify / mean30 | **81165** | 6/30 | 4 | 3.6 |
| holdout | **74099** | 5/20 | 2 | 3.8 |

Gap densify−holdout ≈ **7.1k**.

### Holdout focus: 1827862996
- score **74496**, plot3=0, cows@d10=**4**, empty@d16=4 (packed densify)
- Herd reaches 8 cows only by ~d15; softfloor wants ~8 by d10
- Blocker found: `animal_cash_floor_1q=1200` blocks 1q cow buys even when want_cows=3 and money~1176

## Step 2 levers tried → reverted

| Lever | Effect on 1827 | Densify |
|-------|----------------|---------|
| Mid-day berry herd_push | plot3↑ score↓ | **crash** 7/89/42 |
| Dawn bias berry + empty≥14 | no change | OK |
| 1q melon→cow + cash_floor relax + cow>land | cows earlier, score 55–75k | **crash** 7/89/42 |
| 1q cow>seeds only, cap 3 | ~75.7k, cows@d10=3 | still hurts 7/89 |

**Conclusion:** Early herd on berry 1q shares the densify failure mode. Need a holdout-selective gate (not all berry opens), or post-land2 multi-buy while empty still high — next session.

## Next step 2 attempt (recommended)
Post-land2 only: when `n_quads>=2`, `berry_sink>=1`, `empty>=14`, `cows<6`, `day<=10`, allow **one extra cow capital pick** (dawn followup or second hour) without 1q changes.
