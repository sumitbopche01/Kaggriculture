"""Long-term multi-stream profit — crops, milk, eggs, wool, inventory.

Used by expand-vs-stay and market project scoring so land/herd/seed
decisions maximize horizon profit across shop sinks, not crop tiles alone.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LongTermStreams:
    """Per-day / horizon rates for the active map engines."""

    # Crop tile EVs (planning units — same scale as plan_ev / tile_ev).
    berry_ev: float = 0.0
    tomato_ev: float = 0.0
    carrot_ev: float = 0.0
    melon_ev: float = 0.0
    primary_ev: float = 0.0
    # Blended fill EV for new tiles (primary + secondary sinks).
    fill_tile_ev: float = 0.0
    # Animal product coins per animal per day (gross production).
    milk_day: float = 0.0
    egg_day: float = 0.0
    wool_day: float = 0.0
    # Herd gap × horizon value (already net of purchase cost credit).
    animal_gap_ev: float = 0.0
    # Extra mouths a +25 plot can unlock × horizon.
    land_animal_unlock_ev: float = 0.0
    # Shed inventory that can fund / print over the horizon.
    inventory_ev: float = 0.0
    productive_days: int = 0


def animal_day_rate(*, price: float, interval: int) -> float:
    """Expected coins/day from one live animal (sunk buy cost ignored)."""
    iv = max(1, int(interval))
    return max(0.0, float(price)) / float(iv)


def blend_crop_tile_ev(
    *,
    primary_ev: float,
    berry_ev: float = 0.0,
    tomato_ev: float = 0.0,
    carrot_ev: float = 0.0,
    melon_ev: float = 0.0,
    berry_sinks: int = 0,
    milk_sinks: int = 0,
    carrot_sinks: int = 0,
    secondary_weight: float = 0.4,
) -> float:
    """Horizon fill EV: primary dominates; secondaries get sink-weighted credit."""
    primary = max(0.0, float(primary_ev))
    w = max(0.0, min(1.0, float(secondary_weight)))
    parts: list[tuple[float, float]] = [(primary, 1.0)]
    if int(berry_sinks) > 0 and berry_ev > 0:
        parts.append((max(0.0, float(berry_ev)), 0.85 + 0.15 * min(3, int(berry_sinks))))
    if int(milk_sinks) > 0 and tomato_ev > 0:
        parts.append((max(0.0, float(tomato_ev)), 0.55 + 0.1 * min(3, int(milk_sinks))))
    if int(carrot_sinks) > 0 and carrot_ev > 0:
        parts.append((max(0.0, float(carrot_ev)), 0.5 + 0.1 * min(2, int(carrot_sinks))))
    if melon_ev > 0:
        parts.append((max(0.0, float(melon_ev)), 0.25))
    # Soft mix: best stream + weighted average of the rest.
    best = max(e for e, _ in parts)
    if len(parts) == 1:
        return best
    wsum = sum(wt for _, wt in parts)
    avg = sum(e * wt for e, wt in parts) / max(1e-6, wsum)
    return (1.0 - w) * best + w * avg


def herd_gap_horizon_ev(
    *,
    productive_days: int,
    cows: int,
    sheep: int,
    geese: int,
    cow_target: int,
    sheep_target: int,
    goose_target: int,
    milk_day: float,
    wool_day: float,
    egg_day: float,
    cow_cost: int = 400,
    sheep_cost: int = 500,
    goose_cost: int = 300,
    realize: float = 0.7,
) -> float:
    """NPV of closing the herd gap toward shop targets (purchase cost credited)."""
    days = max(0, int(productive_days))
    if days <= 0:
        return 0.0
    r = max(0.1, min(1.0, float(realize)))
    total = 0.0
    for have, tgt, day_v, cost in (
        (cows, cow_target, milk_day, cow_cost),
        (sheep, sheep_target, wool_day, sheep_cost),
        (geese, goose_target, egg_day, goose_cost),
    ):
        gap = max(0, int(tgt) - int(have))
        if gap <= 0 or day_v <= 0:
            continue
        # Half purchase cost: animals are bought later from operating cash.
        total += gap * (float(day_v) * float(days) * r - 0.5 * float(cost))
    return max(0.0, total)


def land_animal_unlock_ev(
    *,
    productive_days: int,
    cows: int,
    sheep: int,
    geese: int,
    cow_target: int,
    sheep_target: int,
    goose_target: int,
    milk_day: float,
    wool_day: float,
    egg_day: float,
    cow_cost: int = 400,
    sheep_cost: int = 500,
    goose_cost: int = 300,
    new_empty: int = 25,
    pasture_frac: float = 0.32,
    realize: float = 0.55,
) -> float:
    """Horizon value of mouths a new plot can host (pasture + feed share)."""
    days = max(0, int(productive_days))
    room = max(0, int(float(new_empty) * max(0.0, float(pasture_frac))))
    if days <= 0 or room <= 0:
        return 0.0
    r = max(0.1, min(1.0, float(realize)))
    # Prefer higher day-value products first (milk usually wins on pizza/ice).
    slots: list[tuple[float, int, int, float]] = []
    if milk_day > 0:
        slots.append((float(milk_day), max(0, int(cow_target) - int(cows)), int(cow_cost), float(milk_day)))
    if wool_day > 0:
        slots.append((float(wool_day), max(0, int(sheep_target) - int(sheep)), int(sheep_cost), float(wool_day)))
    if egg_day > 0:
        slots.append((float(egg_day), max(0, int(goose_target) - int(geese)), int(goose_cost), float(egg_day)))
    slots.sort(key=lambda t: t[0], reverse=True)
    left = room
    total = 0.0
    for _rank, gap, cost, day_v in slots:
        take = min(left, gap)
        if take <= 0:
            continue
        total += take * (day_v * float(days) * r - 0.5 * float(cost))
        left -= take
        if left <= 0:
            break
    return max(0.0, total)


def inventory_horizon_ev(
    *,
    berries: int = 0,
    milk: int = 0,
    eggs: int = 0,
    wool: int = 0,
    melons: int = 0,
    berry_px: float = 0.0,
    milk_px: float = 0.0,
    egg_px: float = 0.0,
    wool_px: float = 0.0,
    melon_px: float = 0.0,
    realize: float = 0.25,
) -> float:
    """Light credit for shed/hand products already on hand (same stay vs expand)."""
    r = max(0.0, min(1.0, float(realize)))
    return r * (
        max(0, int(berries)) * max(0.0, float(berry_px))
        + max(0, int(milk)) * max(0.0, float(milk_px))
        + max(0, int(eggs)) * max(0.0, float(egg_px))
        + max(0, int(wool)) * max(0.0, float(wool_px))
        + max(0, int(melons)) * max(0.0, float(melon_px))
    )


def build_streams(
    *,
    productive_days: int,
    primary_ev: float,
    berry_ev: float = 0.0,
    tomato_ev: float = 0.0,
    carrot_ev: float = 0.0,
    melon_ev: float = 0.0,
    berry_sinks: int = 0,
    milk_sinks: int = 0,
    carrot_sinks: int = 0,
    egg_sinks: int = 0,
    wool_demand: int = 0,
    milk_px: float = 0.0,
    egg_px: float = 0.0,
    wool_px: float = 0.0,
    cows: int = 0,
    sheep: int = 0,
    geese: int = 0,
    cow_target: int = 0,
    sheep_target: int = 0,
    goose_target: int = 0,
    cow_interval: int = 2,
    sheep_interval: int = 3,
    goose_interval: int = 1,
    cow_cost: int = 400,
    sheep_cost: int = 500,
    goose_cost: int = 300,
    shed_berries: int = 0,
    shed_milk: int = 0,
    shed_eggs: int = 0,
    shed_wool: int = 0,
    shed_melons: int = 0,
    berry_px: float = 0.0,
    melon_px: float = 0.0,
    secondary_weight: float = 0.4,
    animal_realize: float = 0.7,
    land_animal_realize: float = 0.55,
    pasture_frac: float = 0.32,
    inventory_realize: float = 0.25,
    new_empty: int = 25,
) -> LongTermStreams:
    """Assemble multi-stream snapshot for planning / expand-vs-stay."""
    milk_day = animal_day_rate(price=milk_px, interval=cow_interval) if milk_sinks > 0 else 0.0
    egg_day = animal_day_rate(price=egg_px, interval=goose_interval) if egg_sinks > 0 else 0.0
    wool_day = (
        animal_day_rate(price=wool_px, interval=sheep_interval) if wool_demand > 0 else 0.0
    )
    fill = blend_crop_tile_ev(
        primary_ev=primary_ev,
        berry_ev=berry_ev,
        tomato_ev=tomato_ev,
        carrot_ev=carrot_ev,
        melon_ev=melon_ev,
        berry_sinks=berry_sinks,
        milk_sinks=milk_sinks,
        carrot_sinks=carrot_sinks,
        secondary_weight=secondary_weight,
    )
    gap = herd_gap_horizon_ev(
        productive_days=productive_days,
        cows=cows,
        sheep=sheep,
        geese=geese,
        cow_target=cow_target,
        sheep_target=sheep_target,
        goose_target=goose_target,
        milk_day=milk_day,
        wool_day=wool_day,
        egg_day=egg_day,
        cow_cost=cow_cost,
        sheep_cost=sheep_cost,
        goose_cost=goose_cost,
        realize=animal_realize,
    )
    unlock = land_animal_unlock_ev(
        productive_days=productive_days,
        cows=cows,
        sheep=sheep,
        geese=geese,
        cow_target=cow_target,
        sheep_target=sheep_target,
        goose_target=goose_target,
        milk_day=milk_day,
        wool_day=wool_day,
        egg_day=egg_day,
        cow_cost=cow_cost,
        sheep_cost=sheep_cost,
        goose_cost=goose_cost,
        new_empty=new_empty,
        pasture_frac=pasture_frac,
        realize=land_animal_realize,
    )
    inv = inventory_horizon_ev(
        berries=shed_berries,
        milk=shed_milk,
        eggs=shed_eggs,
        wool=shed_wool,
        melons=shed_melons,
        berry_px=berry_px,
        milk_px=milk_px,
        egg_px=egg_px,
        wool_px=wool_px,
        melon_px=melon_px,
        realize=inventory_realize,
    )
    return LongTermStreams(
        berry_ev=max(0.0, float(berry_ev)),
        tomato_ev=max(0.0, float(tomato_ev)),
        carrot_ev=max(0.0, float(carrot_ev)),
        melon_ev=max(0.0, float(melon_ev)),
        primary_ev=max(0.0, float(primary_ev)),
        fill_tile_ev=fill,
        milk_day=milk_day,
        egg_day=egg_day,
        wool_day=wool_day,
        animal_gap_ev=gap,
        land_animal_unlock_ev=unlock,
        inventory_ev=inv,
        productive_days=max(0, int(productive_days)),
    )


def best_animal_horizon_ev(
    *,
    productive_days: int,
    milk_day: float,
    wool_day: float,
    egg_day: float,
    want_cow: bool,
    want_sheep: bool,
    want_goose: bool,
    cow_cost: int = 400,
    sheep_cost: int = 500,
    goose_cost: int = 300,
    setup_days: float = 2.0,
) -> float:
    """Best single animal buy over the remaining engine horizon."""
    days = max(1.0, float(productive_days) - max(0.0, float(setup_days)))
    best = 0.0
    if want_cow and milk_day > 0:
        best = max(best, float(milk_day) * days - 0.25 * float(cow_cost))
    if want_sheep and wool_day > 0:
        best = max(best, float(wool_day) * days - 0.25 * float(sheep_cost))
    if want_goose and egg_day > 0:
        best = max(best, float(egg_day) * days - 0.25 * float(goose_cost))
    return max(0.0, best)
