"""Multi-stream long-term profit (crops + milk/egg/wool)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brain.long_term import (
    best_animal_horizon_ev,
    blend_crop_tile_ev,
    build_streams,
    land_animal_unlock_ev,
)
from brain.turn_budget import expand_vs_stay_advantage


class LongTermStreamTests(unittest.TestCase):
    def test_blend_prefers_primary_but_credits_tomato(self) -> None:
        blended = blend_crop_tile_ev(
            primary_ev=30.0,
            berry_ev=30.0,
            tomato_ev=40.0,
            milk_sinks=2,
            secondary_weight=0.4,
        )
        self.assertGreater(blended, 30.0)
        self.assertLessEqual(blended, 40.0)

    def test_milk_unlock_boosts_expand(self) -> None:
        unlock = land_animal_unlock_ev(
            productive_days=18,
            cows=4,
            sheep=2,
            geese=0,
            cow_target=10,
            sheep_target=2,
            goose_target=0,
            milk_day=80.0,
            wool_day=0.0,
            egg_day=0.0,
            pasture_frac=0.32,
            realize=0.55,
        )
        self.assertGreater(unlock, 0.0)
        base = expand_vs_stay_advantage(
            workers=12,
            hungry=0,
            live_tiles=12,
            productive_days=18,
            tile_ev=35.0,
            land_cost=2500,
            seed_cost=100,
            empty=22,
            stand_factor=1.0,
            realize=0.7,
            animal_unlock_ev=0.0,
        )
        boosted = expand_vs_stay_advantage(
            workers=12,
            hungry=0,
            live_tiles=12,
            productive_days=18,
            tile_ev=35.0,
            land_cost=2500,
            seed_cost=100,
            empty=22,
            stand_factor=1.0,
            realize=0.7,
            animal_unlock_ev=unlock,
        )
        self.assertGreater(boosted, base)

    def test_packed_printer_still_stays_with_animal_credit(self) -> None:
        unlock = land_animal_unlock_ev(
            productive_days=18,
            cows=4,
            sheep=2,
            geese=0,
            cow_target=10,
            sheep_target=2,
            goose_target=0,
            milk_day=80.0,
            wool_day=0.0,
            egg_day=0.0,
        )
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
            animal_unlock_ev=unlock,
        )
        self.assertLessEqual(adv, 0)

    def test_egg_and_wool_streams_build(self) -> None:
        streams = build_streams(
            productive_days=20,
            primary_ev=10.0,
            berry_ev=0.0,
            tomato_ev=0.0,
            carrot_ev=25.0,
            egg_sinks=2,
            wool_demand=2,
            carrot_sinks=1,
            milk_px=0.0,
            egg_px=70.0,
            wool_px=220.0,
            cows=0,
            sheep=2,
            geese=0,
            cow_target=0,
            sheep_target=6,
            goose_target=3,
        )
        self.assertGreater(streams.egg_day, 0.0)
        self.assertGreater(streams.wool_day, 0.0)
        self.assertGreater(streams.land_animal_unlock_ev, 0.0)
        self.assertGreater(streams.fill_tile_ev, 0.0)

    def test_best_animal_picks_wool_when_rich(self) -> None:
        ev = best_animal_horizon_ev(
            productive_days=16,
            milk_day=40.0,
            wool_day=90.0,
            egg_day=30.0,
            want_cow=True,
            want_sheep=True,
            want_goose=True,
        )
        wool_only = best_animal_horizon_ev(
            productive_days=16,
            milk_day=0.0,
            wool_day=90.0,
            egg_day=0.0,
            want_cow=False,
            want_sheep=True,
            want_goose=False,
        )
        self.assertAlmostEqual(ev, wool_only)


if __name__ == "__main__":
    unittest.main()
