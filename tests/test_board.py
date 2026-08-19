"""Tests for board-fill invariant."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brain.board import (
    board_fill_land_empty_cap,
    land_blocked_by_board_fill,
    late_berry_target_met,
)

PARAMS = {
    "board_fill_land_empty_max_1q": 10,
    "board_fill_land_empty_max_2q": 8,
    "board_fill_land_empty_max_3q": 6,
    "board_fill_late_berry_cap_2q": 8,
    "board_fill_berry_gap_min": 3,
    "board_fill_berry_target_min": 8,
    "board_fill_pressure_empty": 6,
    "board_fill_berry_met_cap_2q": 12,
    "land2_strawberry_min": 16,
}


class BoardFillInvariantTests(unittest.TestCase):
    def test_blocks_land_when_too_many_empty(self):
        s = {"empty": 12, "n_quads": 2, "crops": {"STRAWBERRY": 10}, "seeds": {}}
        self.assertTrue(
            land_blocked_by_board_fill(
                s,
                PARAMS,
                berry_gap=6,
                berry_ok=True,
                late_shop_sprint=False,
                berry_ramp=False,
            )
        )

    def test_allows_land_when_empty_low(self):
        s = {"empty": 4, "n_quads": 2, "crops": {"STRAWBERRY": 20}, "seeds": {}}
        self.assertFalse(
            land_blocked_by_board_fill(
                s,
                PARAMS,
                berry_gap=0,
                berry_ok=True,
                late_shop_sprint=False,
                berry_ramp=False,
            )
        )

    def test_late_berry_target_met_bypass(self):
        s = {"empty": 12, "n_quads": 2, "crops": {"STRAWBERRY": 20}, "seeds": {}}
        self.assertTrue(late_berry_target_met(s, PARAMS, berry_gap=0, strategy="LATE_BERRY"))
        self.assertFalse(
            land_blocked_by_board_fill(
                s,
                PARAMS,
                berry_gap=0,
                berry_ok=True,
                late_shop_sprint=False,
                berry_ramp=False,
                strategy="LATE_BERRY",
            )
        )

    def test_late_berry_cap(self):
        self.assertEqual(
            board_fill_land_empty_cap(2, PARAMS, strategy="LATE_BERRY"), 8
        )


if __name__ == "__main__":
    unittest.main()
