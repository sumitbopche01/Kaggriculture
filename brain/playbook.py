"""Shop-sink playbooks — the berry loop, parameterized by open shops.

Strawberries already had prep / gap / ramp / late-sprint. Pizza, pet cafe,
and milk shops need the same loop: scale tiles (or cows) with stacked
demand, fill the gap, and do not spend that cash on a third land plot.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

CashCrop = Literal["STRAWBERRY", "TOMATO", "CARROT"]
Engine = Literal["BERRY", "MILK", "EGG"]

BERRY_SHOPS = frozenset(
    {"SMOOTHIE_SHOP", "BRUNCH_SPOT", "ICE_CREAM_SHOP", "FARMERS_MARKET"}
)
TOMATO_SHOPS = frozenset({"PIZZA_SHOP", "FARMERS_MARKET"})
CARROT_SHOPS = frozenset({"PET_CAFE", "FARMERS_MARKET"})
MILK_SHOPS = frozenset({"PIZZA_SHOP", "ICE_CREAM_SHOP", "SMOOTHIE_SHOP"})

# Same land-scaling as strawberries. Secondary crops keep a small cap so a
# smoothie map does not drown in tomatoes just because pizza also exists.
PRIMARY_TILE_BASE = {1: 8, 2: 28, 3: 48, 4: 60}
SECONDARY_TILE_BASE = {1: 4, 2: 8, 3: 12, 4: 16}

CROP_SINK_SHOPS: dict[str, frozenset[str]] = {
    "STRAWBERRY": BERRY_SHOPS,
    "TOMATO": TOMATO_SHOPS,
    "CARROT": CARROT_SHOPS,
}

RAMP_DAY_MIN = {"STRAWBERRY": 7, "TOMATO": 7, "CARROT": 7}
# Last plant/replant day before LIQUIDATE (liquidate_day_min = 28).
ENGINE_REPLANT_DAY_MAX = 27


@dataclass(frozen=True)
class CropSinkSpec:
    item: CashCrop
    shops: frozenset[str]
    day_min: int


CROP_SINKS: tuple[CropSinkSpec, ...] = (
    CropSinkSpec("STRAWBERRY", BERRY_SHOPS, 7),
    CropSinkSpec("TOMATO", TOMATO_SHOPS, 3),
    CropSinkSpec("CARROT", CARROT_SHOPS, 7),
)


def shop_family_count(shops: list[str] | tuple[str, ...] | None, family: frozenset[str]) -> int:
    return sum(1 for name in shops or [] if name in family)


def map_engine(
    *,
    milk_n: int = 0,
    egg_n: int = 0,
    first_berry_day: int | None = None,
    first_milk_day: int | None = None,
) -> Engine:
    """One identity for the episode.

    Milk/wheat patches must not fire on bakery towns just because two
    bakeries list WHEAT, or on a berry town because a smoothie listed MILK.
    Pizza before berries is the milk engine. Berry-first (including ice
    cream same-day) stays berries. Egg shops with no berry/milk opener
    are the egg engine.
    """
    if int(milk_n) >= 1 and not berry_opened_first(first_berry_day, first_milk_day):
        return "MILK"
    if berry_opened_first(first_berry_day, first_milk_day):
        return "BERRY"
    if int(egg_n) >= 1:
        return "EGG"
    return "BERRY"


def engine_of(s: dict[str, Any]) -> Engine:
    """Read a stamped engine, or infer from shops / first-unlock days."""
    eng = s.get("engine")
    if eng in ("BERRY", "MILK", "EGG"):
        return eng  # type: ignore[return-value]
    shops = s.get("shops")
    if shops is not None:
        milk_n = shop_family_count(shops, MILK_SHOPS)
        egg_n = shop_family_count(shops, frozenset({"BAKERY", "BRUNCH_SPOT"}))
    else:
        milk_n = int(s.get("milk_sink") or 0)
        egg_n = int(s.get("egg_sink") or 0)
    return map_engine(
        milk_n=milk_n,
        egg_n=egg_n,
        first_berry_day=s.get("first_berry_day"),
        first_milk_day=s.get("first_milk_day"),
    )


def berry_opened_first(
    first_berry_day: int | None,
    first_milk_day: int | None,
) -> bool:
    """True when a berry shop unlocked at or before the first milk shop.

    Ice cream is both families; same-day counts as berries first so a
    later pizza cannot steal the primary crop.
    """
    if first_berry_day is None:
        return False
    if first_milk_day is None:
        return True
    return int(first_berry_day) <= int(first_milk_day)


def primary_cash_crop(
    demand: dict[str, int] | None,
    *,
    viable: dict[str, bool],
    milk_n: int = 0,
    first_berry_day: int | None = None,
    first_milk_day: int | None = None,
) -> CashCrop | None:
    """Dominant shop crop.

    Whoever opened first keeps the engine. Early ice cream / farmers
    market stays strawberries even after pizza. Two pizzas before any
    berry shop stay tomatoes even after a late smoothie.
    """
    d = demand or {}
    tomato_ok = int(d.get("TOMATO", 0)) >= 1 and viable.get("TOMATO", False)
    berry_demand = int(d.get("STRAWBERRY", 0)) >= 1
    berry_ok = berry_demand and viable.get("STRAWBERRY", False)
    carrot_ok = int(d.get("CARROT", 0)) >= 1 and viable.get("CARROT", False)
    # Glut must not demote the opener to pet-cafe carrots.
    if berry_demand and berry_opened_first(first_berry_day, first_milk_day):
        return "STRAWBERRY"
    if tomato_ok and int(milk_n) >= 2:
        return "TOMATO"
    if berry_ok:
        return "STRAWBERRY"
    if tomato_ok:
        return "TOMATO"
    if carrot_ok:
        return "CARROT"
    return None


# Strawberries keep 8/28/48/60. Tomato primary denser on 2q so pizza maps
# keep a real printer (seed 13 stalled at 16-tile caps while milk shops stacked).
TOMATO_PRIMARY_BASE = {1: 6, 2: 24, 3: 36, 4: 48}


def cash_tile_base(n_quads: int, *, primary: bool, crop: str | None = None) -> int:
    n = 1 if n_quads <= 1 else min(4, n_quads)
    if crop == "STRAWBERRY":
        return int(PRIMARY_TILE_BASE[n])
    if crop == "TOMATO" and primary:
        return int(TOMATO_PRIMARY_BASE[n])
    # Pet cafe is a garnish. A 28-tile carrot field before pizza opens
    # (761083594) wastes the first two quads.
    if crop == "CARROT":
        return int(SECONDARY_TILE_BASE[n])
    if primary and n >= 2:
        return int(PRIMARY_TILE_BASE[n])
    return int(SECONDARY_TILE_BASE[n])


def cash_tile_cap(
    n_quads: int,
    demand_count: int,
    *,
    primary: bool,
    step: int,
    crop: str | None = None,
) -> int:
    """Raise the tile cap with stacked shops, same shape as berry_tile_cap."""
    base = cash_tile_base(n_quads, primary=primary, crop=crop)
    d = max(0, int(demand_count))
    if d <= 1:
        return base
    return base + int(step) * (d - 1)


def crop_gap(plan: dict[str, int], s: dict[str, Any], crop: str | None) -> int:
    """Tiles still to *buy*: plan minus planted minus pocket seeds."""
    if not crop:
        return 0
    have = int(s.get("crops", {}).get(crop, 0) or 0)
    seeds = int((s.get("seeds") or {}).get(crop, 0) or 0)
    return max(0, int(plan.get(crop, 0) or 0) - have - seeds)


def plant_gap(plan: dict[str, int], s: dict[str, Any], crop: str | None) -> int:
    """Tiles still to *plant*: plan minus planted. Pocket seeds are not tiles."""
    if not crop:
        return 0
    have = int(s.get("crops", {}).get(crop, 0) or 0)
    return max(0, int(plan.get(crop, 0) or 0) - have)


def crop_is_ramping(
    s: dict[str, Any],
    crop: str | None,
    plan: dict[str, int],
    *,
    late: bool,
) -> bool:
    """Midgame fill when the primary shop crop is short of its tile target."""
    if not crop:
        return False
    day = int(s.get("day", 0))
    day_max = 18 if late else 16
    gap_need = 2 if late else 3
    day_min = int(RAMP_DAY_MIN.get(crop, 7))
    if day < day_min or day > day_max:
        return False
    if int(s.get("empty", 0)) < 2:
        return False
    target = int(plan.get(crop, 0) or 0)
    if target <= 0:
        return False
    have = int(s.get("crops", {}).get(crop, 0) or 0) + int(
        (s.get("seeds") or {}).get(crop, 0) or 0
    )
    if have >= target:
        return False
    if int(s.get("n_quads", 1)) == 1 and have >= 8 and not late:
        return False
    return crop_gap(plan, s, crop) >= gap_need


def crop_is_replanting(
    s: dict[str, Any],
    crop: str | None,
    plan: dict[str, int],
    *,
    late: bool,
) -> bool:
    """Keep buying the primary crop after the ramp window until liquidate."""
    if not crop or int(plan.get(crop, 0) or 0) <= 0:
        return False
    gap = crop_gap(plan, s, crop)
    if gap <= 0:
        return False
    day = int(s.get("day", 0))
    if day > ENGINE_REPLANT_DAY_MAX:
        return False
    if late:
        return True
    return day >= 12


def late_crop_unlock(
    prev_shops: set[str],
    shops: set[str],
    *,
    day: int,
    late_day_min: int,
) -> bool:
    """True on the first shop of a crop family that opens at/after late_day_min."""
    if day < late_day_min:
        return False
    for family in CROP_SINK_SHOPS.values():
        new = [sh for sh in shops if sh in family and sh not in prev_shops]
        had = bool(prev_shops & family)
        if new and not had:
            return True
    return False


def milk_sink_n(s: dict[str, Any]) -> int:
    return shop_family_count(s.get("shops"), MILK_SHOPS)


def cow_target(s: dict[str, Any], params: dict[str, int | float]) -> int:
    """How many cows the milk shops justify. Scales harder on pizza stacks."""
    cows = int(s.get("cows") or 0)
    day = int(s.get("day", 0))
    milk_px = int((s.get("prices") or {}).get("MILK", 160) or 160)
    if day > int(params.get("cow_day_max", 20)) or milk_px < int(
        params.get("cow_milk_px_min", 80)
    ):
        return cows
    floor = int(params.get("cow_floor", 2)) if day <= int(params.get("cow_floor_day_max", 20)) else 0
    if engine_of(s) != "MILK":
        # Ice cream / smoothie list MILK. Two+ of those on a 2-quad berry
        # map justify a garnish herd, not a pizza-scale one (seed 42).
        dual = shop_family_count(s.get("shops"), MILK_SHOPS & BERRY_SHOPS)
        n_quads = int(s.get("n_quads", 1))
        if dual >= 2 and n_quads >= 2:
            extra = 2 * min(dual - 1, 2)
            cap = int(params.get("berry_milk_cow_cap", 6))
            mouth_cap = int(params.get("mouth_cap_2qplus", 14))
            other = int(s.get("sheep") or 0) + int(s.get("geese") or 0)
            cap = min(cap, max(0, mouth_cap - other))
            return min(cap, max(floor, floor + extra))
        return max(cows, floor)
    sink = milk_sink_n(s)
    if sink <= 0:
        return max(cows, floor)
    scale = 2 if sink >= 3 else 1
    cap = int(params.get("cow_expand_cap", 10))
    if sink >= 3:
        cap = max(cap, int(params.get("cow_stack_cap", 12)))
    n_quads = int(s.get("n_quads", 1))
    if n_quads >= 2 and sink >= 2:
        scale = 2
    mouth_cap = int(
        params.get("mouth_cap_1q", 6) if n_quads == 1 else params.get("mouth_cap_2qplus", 14)
    )
    other = int(s.get("sheep") or 0) + int(s.get("geese") or 0)
    cap = min(cap, max(0, mouth_cap - other))
    target = max(floor, int(params.get("milk_herd_base", 2)) + sink * scale)
    return min(cap, target)


def herd_tile_reserve(s: dict[str, Any], params: dict[str, int | float]) -> int:
    """Pastures are built as cows are bought; do not reserve a crop hole."""
    return 0


def skip_berry_prep_for_sinks(
    s: dict[str, Any],
    *,
    first_berry_day: int | None = None,
    first_milk_day: int | None = None,
) -> bool:
    """Pizza stacks should buy cows/tomatoes, not strawberry seeds."""
    if berry_opened_first(first_berry_day, first_milk_day):
        return False
    if milk_sink_n(s) >= 2:
        return True
    demand = s.get("demand") or {}
    return int(demand.get("TOMATO", 0) or 0) >= 2
