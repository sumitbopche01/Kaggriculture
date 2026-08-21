"""Map archetype classification — locked per episode around day 8 with provisional + reclassify."""

from __future__ import annotations

from typing import Any, Literal

from brain.playbook import engine_of

MapStrategy = Literal["UNKNOWN", "EARLY_BERRY", "LATE_BERRY", "MILK_STACK", "LAND_SPRINT"]

EGG_SHOPS = frozenset({"BAKERY", "BRUNCH_SPOT"})

# Archetypes that may take softfloor schedule steals (herd / speculative berry).
# EARLY_BERRY densify printers are explicitly excluded.
SOFTFLOOR_STRATEGIES = frozenset({"LATE_BERRY", "LAND_SPRINT", "UNKNOWN", "MILK_STACK"})


def _shop_counts(
    shops: set[str],
    *,
    berry_shops: frozenset[str],
    milk_shops: frozenset[str],
) -> tuple[int, int, int, int, int]:
    berry_n = sum(1 for name in shops if name in berry_shops)
    milk_n = sum(1 for name in shops if name in milk_shops)
    egg_n = sum(1 for name in shops if name in EGG_SHOPS)
    pure_milk_n = sum(
        1 for name in shops if name in milk_shops and name not in berry_shops
    )
    dual_milk_berry_n = sum(
        1 for name in shops if name in milk_shops and name in berry_shops
    )
    return berry_n, milk_n, egg_n, pure_milk_n, dual_milk_berry_n


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
    berry_n, _milk_n, egg_n, pure_milk_n, dual_milk_berry_n = _shop_counts(
        shops, berry_shops=berry_shops, milk_shops=milk_shops
    )
    first_berry = track.get("first_berry_day")
    early_max = int(params.get("map_early_berry_day_max", 8))
    late_min = int(params.get("map_late_berry_day_min", 12))
    milk_pure_min = int(params.get("map_milk_stack_pure_min", 1))
    milk_dual_min = int(params.get("map_milk_stack_dual_min", 1))

    if first_berry is not None and first_berry <= early_max:
        return "EARLY_BERRY"
    if berry_n == 0 and egg_n >= 1:
        return "LATE_BERRY"
    if first_berry is not None and first_berry >= late_min:
        return "LATE_BERRY"
    milk_stack = berry_n <= 1 and (
        pure_milk_n >= 2
        or (
            pure_milk_n >= milk_pure_min
            and dual_milk_berry_n >= milk_dual_min
        )
    )
    if milk_stack:
        return "MILK_STACK"
    if berry_n >= 1:
        return "LAND_SPRINT"
    return "UNKNOWN"


def resolve_strategy(
    s: dict[str, Any],
    track: dict[str, Any],
    params: dict[str, int | float],
    *,
    berry_shops: frozenset[str],
    milk_shops: frozenset[str],
) -> MapStrategy:
    """Locked archetype, or provisional classification before lock day."""
    if track.get("archetype_locked"):
        return track.get("archetype", "UNKNOWN")  # type: ignore[return-value]

    first_berry = track.get("first_berry_day")
    early_max = int(params.get("map_early_berry_day_max", 8))
    if first_berry is not None and first_berry <= early_max:
        return "EARLY_BERRY"

    prov_min = int(params.get("map_provisional_day_min", 5))
    if s.get("day", 0) >= prov_min:
        return classify_archetype(
            s,
            track,
            params,
            berry_shops=berry_shops,
            milk_shops=milk_shops,
        )
    return "UNKNOWN"


def maybe_reclassify_archetype(
    s: dict[str, Any],
    track: dict[str, Any],
    params: dict[str, int | float],
    *,
    berry_shops: frozenset[str],
    milk_shops: frozenset[str],
    new_berry_today: bool,
) -> None:
    """One-way upgrades after lock when the first berry shop opens late."""
    if not track.get("archetype_locked") or not new_berry_today:
        return
    first_berry = track.get("first_berry_day")
    early_max = int(params.get("map_early_berry_day_max", 8))
    late_min = int(params.get("map_late_berry_day_min", 12))
    current = track.get("archetype", "UNKNOWN")
    fresh = classify_archetype(
        s,
        track,
        params,
        berry_shops=berry_shops,
        milk_shops=milk_shops,
    )

    if first_berry is not None and first_berry <= early_max:
        track["archetype"] = "EARLY_BERRY"
        return
    if first_berry is not None and first_berry >= late_min:
        track["archetype"] = "LATE_BERRY"
        return
    if current in ("LATE_BERRY", "MILK_STACK", "UNKNOWN") and fresh == "LAND_SPRINT":
        track["archetype"] = "LAND_SPRINT"


def strategy_allows_berry_prep(strategy: MapStrategy) -> bool:
    # MILK_STACK is a pizza/milk town — prep strawberries there starves cows.
    return strategy in ("LATE_BERRY", "LAND_SPRINT", "UNKNOWN")


def softfloor_mode_active(
    s: dict[str, Any],
    strategy: MapStrategy,
    params: dict[str, int | float],
) -> bool:
    """Route softfloor schedule steals (herd ramp, speculative berry).

    Densify EARLY_BERRY stays off. UNKNOWN uses fill hollow (empty≥16) so
    softfloor post-land1 dawns keep routing after empty drops 25→17.
    LAND_SPRINT/MILK_STACK keep deep hollow (empty≥20) — densify seed 55
    crashed when LAND_SPRINT routed at empty≥16. LATE_BERRY needs pizza.
    """
    if int(params.get("softfloor_router_enabled", 1)) != 1:
        return False
    if strategy == "EARLY_BERRY":
        return False
    if strategy not in SOFTFLOOR_STRATEGIES:
        return False
    if int(s.get("n_quads") or 0) < 2:
        return False
    day = int(s.get("day") or 0)
    if day < int(params.get("softfloor_router_day_min", 6)):
        return False
    if day > int(params.get("softfloor_router_day_max", 18)):
        return False
    empty = int(s.get("empty") or 0)
    deep = int(params.get("hollow_herd_deep_empty", 20))
    fill = int(params.get("softfloor_fill_empty_min", 16))
    shops = set(s.get("shops") or [])

    if strategy == "LATE_BERRY":
        if "PIZZA_SHOP" not in shops:
            return False
        return empty >= fill

    if strategy == "UNKNOWN":
        # Keep routing when empty dips 16→14 overnight (seed 33 plot3 miss).
        return empty >= min(fill, int(params.get("plot3_hollow_empty_min", 14)))

    # LAND_SPRINT / MILK_STACK: deep hollow only (densify-safe).
    return empty >= deep


def strategy_land_ramp_relax_trigger_cap(
    strategy: MapStrategy,
    params: dict[str, int | float],
    *,
    n_quads: int,
) -> int:
    """Max empty tiles while land-ramp relax may activate (0 = never)."""
    if n_quads == 1:
        if strategy == "LATE_BERRY":
            return 0
        return int(params.get("map_land_sprint_relax_empty_max", 14))
    if n_quads != 2:
        return 99
    if strategy == "LATE_BERRY":
        return 0
    if strategy == "LAND_SPRINT":
        return int(params.get("map_land_sprint_relax_empty_max", 14))
    return int(params.get("map_land_relax_empty_max", 12))


def strategy_land_empty_cap(
    strategy: MapStrategy,
    params: dict[str, int | float],
    *,
    n_quads: int,
    relax: bool,
) -> int:
    """Max empty tiles allowed before blocking land buys."""
    if n_quads != 2:
        return strategy_quad1_empty_cap(strategy, params, relax=relax)
    if not relax or strategy == "LATE_BERRY":
        return int(params["land2_empty_max"])
    return int(params["late_ramp_land_empty_max"])


def strategy_quad1_empty_cap(
    strategy: MapStrategy,
    params: dict[str, int | float],
    *,
    relax: bool,
    seed_buy: bool = False,
) -> int:
    if relax and strategy != "LATE_BERRY":
        return int(params.get("map_land_sprint_relax_empty_max", 14))
    if seed_buy:
        return int(params.get("map_land1_seed_empty_max", 10))
    return int(params.get("map_land1_empty_max", 11))


def land_ramp_relax_active(
    strategy: MapStrategy,
    s: dict[str, Any],
    params: dict[str, int | float],
    *,
    late_shop_sprint: bool,
    berry_gap: int,
    n_quads: int,
) -> bool:
    if strategy == "LATE_BERRY" or not late_shop_sprint or berry_gap <= 0:
        return False
    cap = strategy_land_ramp_relax_trigger_cap(strategy, params, n_quads=n_quads)
    if cap <= 0:
        return False
    return int(s.get("empty", 0)) <= cap


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


def strategy_defer_animals(
    strategy: MapStrategy,
    s: dict[str, Any],
    flags: Any,
    berry_gap: int,
    params: dict[str, int | float],
) -> bool:
    """Whether field workers defer animal care for planting."""
    day = s.get("day", 0)
    empty = int(s.get("empty", 0))
    base = (
        (flags.berry_prep and empty >= 8)
        or (flags.late_shop_sprint and empty >= 8)
        or (empty >= 12 and 12 <= day <= 18 and berry_gap > 0)
    )
    if not base:
        return False
    milk_sink = int(s.get("milk_sink", 0) or 0)
    n_quads = int(s.get("n_quads", 1) or 1)
    # Pizza-first (MILK engine) still buys cows even if FM locked EARLY_BERRY.
    # Ice-cream-first stays BERRY and defers animals for planting.
    if engine_of(s) == "MILK" and milk_sink >= 1 and n_quads >= 2:
        return False
    if strategy != "MILK_STACK":
        return True
    milk_min = int(params.get("map_milk_defer_milk_sink_min", 2))
    empty_max = int(params.get("map_milk_defer_empty_max", 14))
    if milk_sink >= milk_min and empty < empty_max:
        return False
    if flags.late_shop_sprint and empty < int(params.get("map_milk_sprint_defer_empty_max", 12)):
        return False
    return True
