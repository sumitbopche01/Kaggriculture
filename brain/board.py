"""Board-fill invariant — fill tiles before expanding land (fixes tail seeds)."""

from __future__ import annotations

from typing import Any

from brain.map import MapStrategy


def board_fill_land_empty_cap(
    n_quads: int,
    params: dict[str, int | float],
    *,
    strategy: MapStrategy = "UNKNOWN",
) -> int:
    """Max empty tiles allowed before land buys are blocked."""
    if n_quads <= 1:
        cap = int(params.get("board_fill_land_empty_max_1q", 10))
    elif n_quads == 2:
        cap = int(params.get("board_fill_land_empty_max_2q", 8))
    else:
        cap = int(params.get("board_fill_land_empty_max_3q", 6))
    if strategy == "LATE_BERRY" and n_quads >= 2:
        cap = min(cap, int(params.get("board_fill_late_berry_cap_2q", 8)))
    elif strategy == "MILK_STACK" and n_quads == 2:
        cap = int(params.get("board_fill_milk_stack_cap_2q", 10))
    elif strategy == "EARLY_BERRY" and n_quads == 2:
        cap = int(params.get("board_fill_early_berry_cap_2q", 10))
    return cap


def berry_gap_closing(
    s: dict[str, Any],
    params: dict[str, int | float],
    *,
    berry_gap: int,
    berry_ok: bool,
    late_shop_sprint: bool,
    berry_ramp: bool,
) -> bool:
    """True when the agent is actively closing a strawberry tile gap."""
    if not berry_ok:
        return False
    min_gap = int(params.get("board_fill_berry_gap_min", 3))
    if berry_gap < min_gap:
        return False
    if int(s.get("seeds", {}).get("STRAWBERRY", 0) or 0) > 0:
        return True
    if late_shop_sprint or berry_ramp:
        return True
    have = int(s.get("crops", {}).get("STRAWBERRY", 0) or 0)
    target_min = int(params.get("board_fill_berry_target_min", 8))
    return have < target_min and berry_gap >= min_gap


def late_berry_target_met(
    s: dict[str, Any],
    params: dict[str, int | float],
    *,
    berry_gap: int,
    strategy: MapStrategy,
) -> bool:
    """LATE_BERRY maps may buy the next quad once strawberries hit the land gate."""
    if strategy != "LATE_BERRY" or berry_gap > 0:
        return False
    if int(s.get("n_quads", 1)) != 2:
        return False
    have = int(s.get("crops", {}).get("STRAWBERRY", 0) or 0)
    berry_min = int(params.get("land2_strawberry_min", 16))
    met_cap = int(params.get("board_fill_berry_met_cap_2q", 12))
    return have >= berry_min and int(s.get("empty", 0)) <= met_cap


def land_blocked_by_board_fill(
    s: dict[str, Any],
    params: dict[str, int | float],
    *,
    berry_gap: int,
    berry_ok: bool,
    late_shop_sprint: bool,
    berry_ramp: bool,
    strategy: MapStrategy = "UNKNOWN",
) -> bool:
    """Hard rule: no land while too many tiles sit empty unless closing berry gap."""
    if late_berry_target_met(s, params, berry_gap=berry_gap, strategy=strategy):
        return False
    empty = int(s.get("empty", 0))
    n_quads = int(s.get("n_quads", 1))
    cap = board_fill_land_empty_cap(n_quads, params, strategy=strategy)
    if empty <= cap:
        return False
    if berry_gap_closing(
        s,
        params,
        berry_gap=berry_gap,
        berry_ok=berry_ok,
        late_shop_sprint=late_shop_sprint,
        berry_ramp=berry_ramp,
    ):
        return False
    return True


def board_fill_pressure(
    s: dict[str, Any],
    params: dict[str, int | float],
    *,
    berry_gap: int,
    berry_ok: bool,
    late_shop_sprint: bool,
    berry_ramp: bool,
    plant_sprint: bool,
    strategy: MapStrategy = "UNKNOWN",
) -> bool:
    """Field/market should prioritize planting and weeding over expansion."""
    if plant_sprint or berry_ramp:
        return True
    empty = int(s.get("empty", 0))
    n_quads = int(s.get("n_quads", 1))
    cap = board_fill_land_empty_cap(n_quads, params, strategy=strategy)
    warn = int(params.get("board_fill_pressure_empty", max(4, cap - 2)))
    if empty > warn:
        return True
    if land_blocked_by_board_fill(
        s,
        params,
        berry_gap=berry_gap,
        berry_ok=berry_ok,
        late_shop_sprint=late_shop_sprint,
        berry_ramp=berry_ramp,
        strategy=strategy,
    ):
        return True
    return False
