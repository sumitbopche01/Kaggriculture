"""Expand vs stay — long-term land profit."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brain.turn_budget import (
    expand_vs_stay_advantage,
    hollow_expand_window,
    land_fillable_tiles,
    live_tiles_for_hollow_expand,
)


class ExpandVsStayTests(unittest.TestCase):
    def test_fat_stand_still_fillable_full_horizon(self) -> None:
        fill = land_fillable_tiles(
            workers=8,
            hungry=0,
            live_tiles=20,
            productive_days=18,
            new_empty=25,
            short_horizon=False,
        )
        self.assertGreaterEqual(fill, 10)

    def test_packed_printer_prefers_stay(self) -> None:
        # Fat stand, little empty, crew busy watering → stay (seed 89 pattern).
        adv = expand_vs_stay_advantage(
            workers=8,
            hungry=0,
            live_tiles=22,
            productive_days=18,
            tile_ev=40.0,
            land_cost=2500,
            seed_cost=100,
            empty=4,
            stand_factor=1.0,
            realize=0.7,
        )
        self.assertLessEqual(adv, 0)

    def test_hollow_spare_crew_prefers_expand(self) -> None:
        # Softfloor-ish: modest stand, hollow board, spare plant rate.
        adv = expand_vs_stay_advantage(
            workers=12,
            hungry=0,
            live_tiles=12,
            productive_days=18,
            tile_ev=40.0,
            land_cost=2500,
            seed_cost=100,
            empty=22,
            stand_factor=1.0,
            realize=0.7,
        )
        self.assertGreater(adv, 0)

    def test_no_spare_labor_no_expand(self) -> None:
        adv = expand_vs_stay_advantage(
            workers=6,
            hungry=0,
            live_tiles=20,
            productive_days=18,
            tile_ev=40.0,
            land_cost=2500,
            seed_cost=100,
            empty=30,
            stand_factor=1.0,
            realize=0.7,
        )
        # plant_per_day = 6 - 10 = 0 → no expand
        self.assertLessEqual(adv, 0)

    def test_late_engine_broke_expand_nonpositive(self) -> None:
        adv = expand_vs_stay_advantage(
            workers=10,
            hungry=0,
            live_tiles=8,
            productive_days=2,
            tile_ev=20.0,
            land_cost=5000,
            seed_cost=100,
            empty=20,
            stand_factor=0.5,
            realize=0.7,
        )
        self.assertLessEqual(adv, 0)

    def test_hire_can_unlock_expand(self) -> None:
        kw = dict(
            hungry=0,
            live_tiles=10,
            productive_days=20,
            tile_ev=50.0,
            land_cost=2500,
            seed_cost=80,
            empty=25,
            stand_factor=1.0,
            realize=0.7,
        )
        base = expand_vs_stay_advantage(workers=8, **kw)
        hired = expand_vs_stay_advantage(
            workers=8, hire_n=3, hire_cost_total=8, **kw
        )
        self.assertGreater(hired, base)


class HollowExpandTests(unittest.TestCase):
    def test_hollow_window_excludes_packed(self) -> None:
        self.assertFalse(
            hollow_expand_window(n_quads=2, empty=4, soft_cap=14, hollow_max=45)
        )
        self.assertTrue(
            hollow_expand_window(n_quads=2, empty=22, soft_cap=14, hollow_max=45)
        )

    def test_live_cap_restores_spare_labor_npv(self) -> None:
        # Fat mid-ramp stand on hollow board: raw live zeros spare; capped live expands.
        raw = expand_vs_stay_advantage(
            workers=10,
            hungry=0,
            live_tiles=22,
            productive_days=18,
            tile_ev=40.0,
            land_cost=2500,
            seed_cost=100,
            empty=22,
            stand_factor=1.0,
            realize=0.7,
        )
        capped_live = live_tiles_for_hollow_expand(
            live_tiles=22, workers=10, hungry=0, live_cap_factor=1.35
        )
        capped = expand_vs_stay_advantage(
            workers=10,
            hungry=0,
            live_tiles=capped_live,
            productive_days=18,
            tile_ev=40.0,
            land_cost=2500,
            seed_cost=100,
            empty=22,
            stand_factor=1.0,
            realize=0.7,
            animal_unlock_ev=800.0,
        )
        self.assertLessEqual(raw, 0)
        self.assertGreater(capped, 0)
        self.assertLess(capped_live, 22)

    def test_packed_still_stays_without_hollow_cap(self) -> None:
        # empty=4 is outside hollow window — use full live, stay.
        adv = expand_vs_stay_advantage(
            workers=8,
            hungry=0,
            live_tiles=22,
            productive_days=18,
            tile_ev=40.0,
            land_cost=2500,
            seed_cost=100,
            empty=4,
            stand_factor=1.0,
            realize=0.7,
            animal_unlock_ev=2000.0,
        )
        self.assertLessEqual(adv, 0)


if __name__ == "__main__":
    unittest.main()
