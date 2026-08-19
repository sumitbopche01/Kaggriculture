"""Tests for map archetype classification and strategy helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import brain.plan as plan_mod
from brain.map import (
    classify_archetype,
    land_ramp_relax_active,
    maybe_reclassify_archetype,
    resolve_strategy,
    strategy_allows_berry_prep,
    strategy_defer_animals,
    strategy_land_empty_cap,
    strategy_land_ramp_relax_trigger_cap,
    strategy_quad1_empty_cap,
    strategy_spike_sell_bump,
)

TurnFlags = plan_mod.TurnFlags

BERRY = frozenset({"SMOOTHIE_SHOP", "BRUNCH_SPOT", "ICE_CREAM_SHOP"})
MILK = frozenset({"PIZZA_SHOP", "ICE_CREAM_SHOP", "SMOOTHIE_SHOP"})

PARAMS = {
    "map_early_berry_day_max": 8,
    "map_late_berry_day_min": 12,
    "map_provisional_day_min": 5,
    "land2_empty_max": 4,
    "late_ramp_land_empty_max": 24,
    "map_land_relax_empty_max": 12,
    "map_land_sprint_relax_empty_max": 14,
    "map_land1_empty_max": 11,
    "map_land1_seed_empty_max": 10,
    "map_milk_stack_pure_min": 1,
    "map_milk_stack_dual_min": 1,
    "map_early_spike_day_max": 12,
    "map_early_spike_berry_sink_max": 2,
    "map_milk_defer_milk_sink_min": 2,
    "map_milk_defer_empty_max": 14,
    "map_milk_sprint_defer_empty_max": 12,
}


def _flags(**kwargs: bool) -> TurnFlags:
    defaults = {
        "late_shop_sprint": False,
        "berry_prep": False,
        "plant_sprint": False,
        "berry_ramp": False,
        "seed_fill_push": False,
        "berry_replant_push": False,
        "in_late_ramp": False,
        "land_ramp_relax": False,
        "board_fill_pressure": False,
        "need_land": False,
        "berry_ok": False,
        "liquidity_stress": False,
        "late_ongoing": False,
        "demand_stack": False,
        "price_spike": {},
    }
    defaults.update(kwargs)
    return TurnFlags(**defaults)


class MapArchetypeTests(unittest.TestCase):
    def test_early_berry_by_first_shop_day(self):
        track = {"first_berry_day": 3}
        s = {"day": 8, "shops": ["SMOOTHIE_SHOP"]}
        self.assertEqual(
            classify_archetype(
                s, track, PARAMS, berry_shops=BERRY, milk_shops=MILK
            ),
            "EARLY_BERRY",
        )

    def test_late_berry_bakery_before_berries(self):
        track = {"first_berry_day": None}
        s = {"day": 8, "shops": ["BAKERY"]}
        self.assertEqual(
            classify_archetype(
                s, track, PARAMS, berry_shops=BERRY, milk_shops=MILK
            ),
            "LATE_BERRY",
        )

    def test_milk_stack_pure_and_dual_milk(self):
        track = {"first_berry_day": 10}
        s = {"day": 8, "shops": ["PIZZA_SHOP", "ICE_CREAM_SHOP"]}
        self.assertEqual(
            classify_archetype(
                s, track, PARAMS, berry_shops=BERRY, milk_shops=MILK
            ),
            "MILK_STACK",
        )

    def test_land_sprint_when_berry_open(self):
        track = {"first_berry_day": 9}
        s = {"day": 8, "shops": ["SMOOTHIE_SHOP", "FARMERS_MARKET"]}
        self.assertEqual(
            classify_archetype(
                s, track, PARAMS, berry_shops=BERRY, milk_shops=MILK
            ),
            "LAND_SPRINT",
        )

    def test_early_berry_beats_milk_stack(self):
        track = {"first_berry_day": 4}
        s = {
            "day": 8,
            "shops": ["PIZZA_SHOP", "ICE_CREAM_SHOP", "SMOOTHIE_SHOP"],
        }
        self.assertEqual(
            classify_archetype(
                s, track, PARAMS, berry_shops=BERRY, milk_shops=MILK
            ),
            "EARLY_BERRY",
        )

    def test_dual_only_shops_not_milk_stack(self):
        track = {"first_berry_day": None}
        s = {"day": 8, "shops": ["SMOOTHIE_SHOP", "ICE_CREAM_SHOP"]}
        self.assertEqual(
            classify_archetype(
                s, track, PARAMS, berry_shops=BERRY, milk_shops=MILK
            ),
            "LAND_SPRINT",
        )

    def test_unknown_no_shops(self):
        track = {"first_berry_day": None}
        s = {"day": 8, "shops": []}
        self.assertEqual(
            classify_archetype(
                s, track, PARAMS, berry_shops=BERRY, milk_shops=MILK
            ),
            "UNKNOWN",
        )


class ResolveStrategyTests(unittest.TestCase):
    def test_provisional_early_berry_before_lock(self):
        track = {"first_berry_day": 3, "archetype_locked": False}
        s = {"day": 4, "shops": ["SMOOTHIE_SHOP"]}
        self.assertEqual(
            resolve_strategy(s, track, PARAMS, berry_shops=BERRY, milk_shops=MILK),
            "EARLY_BERRY",
        )

    def test_locked_returns_archetype(self):
        track = {
            "first_berry_day": 3,
            "archetype_locked": True,
            "archetype": "LATE_BERRY",
        }
        s = {"day": 12, "shops": ["SMOOTHIE_SHOP"]}
        self.assertEqual(
            resolve_strategy(s, track, PARAMS, berry_shops=BERRY, milk_shops=MILK),
            "LATE_BERRY",
        )


class ReclassifyTests(unittest.TestCase):
    def test_upgrade_late_to_early_when_berry_was_early(self):
        track = {
            "archetype_locked": True,
            "archetype": "LATE_BERRY",
            "first_berry_day": 7,
        }
        s = {"day": 7, "shops": ["BAKERY", "SMOOTHIE_SHOP"]}
        maybe_reclassify_archetype(
            s,
            track,
            PARAMS,
            berry_shops=BERRY,
            milk_shops=MILK,
            new_berry_today=True,
        )
        self.assertEqual(track["archetype"], "EARLY_BERRY")

    def test_upgrade_to_land_sprint_when_berry_opens(self):
        track = {
            "archetype_locked": True,
            "archetype": "MILK_STACK",
            "first_berry_day": 9,
        }
        s = {"day": 9, "shops": ["PIZZA_SHOP", "ICE_CREAM_SHOP", "SMOOTHIE_SHOP"]}
        maybe_reclassify_archetype(
            s,
            track,
            PARAMS,
            berry_shops=BERRY,
            milk_shops=MILK,
            new_berry_today=True,
        )
        self.assertEqual(track["archetype"], "LAND_SPRINT")


class StrategyHelperTests(unittest.TestCase):
    def test_milk_stack_allows_berry_prep(self):
        self.assertTrue(strategy_allows_berry_prep("MILK_STACK"))

    def test_early_berry_blocks_spike_sell_with_berry_sink(self):
        s = {"day": 8, "berry_sink": 2}
        self.assertFalse(
            strategy_spike_sell_bump("EARLY_BERRY", s, PARAMS, berry_sink=2)
        )

    def test_land_sprint_relax_trigger_higher_than_default(self):
        self.assertEqual(
            strategy_land_ramp_relax_trigger_cap(
                "LAND_SPRINT", PARAMS, n_quads=2
            ),
            14,
        )
        self.assertEqual(
            strategy_land_ramp_relax_trigger_cap("MILK_STACK", PARAMS, n_quads=2),
            12,
        )
        self.assertEqual(
            strategy_land_ramp_relax_trigger_cap("LATE_BERRY", PARAMS, n_quads=2),
            0,
        )

    def test_land_empty_cap_consolidated(self):
        self.assertEqual(
            strategy_land_empty_cap(
                "LAND_SPRINT", PARAMS, n_quads=2, relax=True
            ),
            24,
        )
        self.assertEqual(
            strategy_land_empty_cap(
                "LATE_BERRY", PARAMS, n_quads=2, relax=True
            ),
            4,
        )

    def test_quad1_caps_from_params(self):
        self.assertEqual(
            strategy_quad1_empty_cap("LAND_SPRINT", PARAMS, relax=True), 14
        )
        self.assertEqual(
            strategy_quad1_empty_cap("MILK_STACK", PARAMS, relax=False), 11
        )

    def test_land_ramp_relax_active_respects_strategy(self):
        s = {"empty": 13}
        self.assertTrue(
            land_ramp_relax_active(
                "LAND_SPRINT",
                s,
                PARAMS,
                late_shop_sprint=True,
                berry_gap=5,
                n_quads=2,
            )
        )
        self.assertFalse(
            land_ramp_relax_active(
                "MILK_STACK",
                s,
                PARAMS,
                late_shop_sprint=True,
                berry_gap=5,
                n_quads=2,
            )
        )

    def test_milk_stack_defers_animals_less(self):
        flags = _flags(late_shop_sprint=True)
        s = {"day": 10, "empty": 10, "milk_sink": 2}
        self.assertFalse(
            strategy_defer_animals("MILK_STACK", s, flags, berry_gap=4, params=PARAMS)
        )
        self.assertTrue(
            strategy_defer_animals("LAND_SPRINT", s, flags, berry_gap=4, params=PARAMS)
        )


if __name__ == "__main__":
    unittest.main()
