"""Map archetype classification — locked once per episode around day 8."""

from __future__ import annotations

from typing import Any, Literal

MapStrategy = Literal["UNKNOWN", "EARLY_BERRY", "LATE_BERRY", "MILK_STACK", "LAND_SPRINT"]

EGG_SHOPS = frozenset({"BAKERY", "BRUNCH_SPOT"})


def classify_archetype(
    s: dict[str, Any],
    track: dict[str, Any],
    params: dict[str, int | float],
    *,
    berry_shops: frozenset[str],
    milk_shops: frozenset[str],
) -> MapStrategy:
    """Classify the town from shop unlocks observed by the lock day."""
    shops = set(s.get("shops") or [])
    berry_n = sum(1 for name in shops if name in berry_shops)
    milk_n = sum(1 for name in shops if name in milk_shops)
    egg_n = sum(1 for name in shops if name in EGG_SHOPS)
    first_berry = track.get("first_berry_day")
    early_max = int(params.get("map_early_berry_day_max", 8))
    late_min = int(params.get("map_late_berry_day_min", 12))

    if first_berry is not None and first_berry <= early_max:
        return "EARLY_BERRY"
    if berry_n == 0 and egg_n >= 1:
        return "LATE_BERRY"
    if first_berry is not None and first_berry >= late_min:
        return "LATE_BERRY"
    if milk_n >= 2 and berry_n <= 1:
        return "MILK_STACK"
    if berry_n >= 1:
        return "LAND_SPRINT"
    return "LAND_SPRINT"


def strategy_allows_berry_prep(strategy: MapStrategy) -> bool:
    return strategy in ("LATE_BERRY", "LAND_SPRINT", "UNKNOWN")


def strategy_land_empty_cap(
    strategy: MapStrategy,
    params: dict[str, int | float],
    *,
    n_quads: int,
    relax: bool,
) -> int:
    """Max empty tiles allowed before blocking land on quad 2."""
    if n_quads != 2:
        return 99
    if strategy == "LATE_BERRY":
        return int(params["land2_empty_max"])
    if relax and strategy == "LAND_SPRINT":
        return int(params["late_ramp_land_empty_max"])
    if relax:
        return int(params["late_ramp_land_empty_max"])
    return int(params["land2_empty_max"])


def strategy_spike_sell_bump(
    strategy: MapStrategy,
    s: dict[str, Any],
    params: dict[str, int | float],
    *,
    berry_sink: int,
) -> bool:
    """Whether SPIKE phase may bump sell_n for held spike inventory."""
    if strategy != "EARLY_BERRY":
        return True
    if s.get("day", 0) >= int(params.get("map_early_spike_day_max", 12)):
        return True
    if berry_sink >= int(params.get("map_early_spike_berry_sink_max", 2)):
        return False
    return True
