"""Dynamic scores — shop/fill signals instead of engine name hard-rules.

`milk_led` in main = milk shops present and no berry shops yet (pizza densify).
Berry / ice-cream boards use cow-vs-seed EV and leave pasture holes.
"""

from __future__ import annotations


def fill_ratio(*, have: int, target: int) -> float:
    """Planted tiles vs plan target. 1.0 = on plan; soft-caps at 2.0."""
    t = max(1, int(target))
    return max(0.0, min(2.0, float(have) / float(t)))


def feed_cover(
    *,
    planted_wheat: int,
    wheat_stock: int,
    mouths: int,
    buffer: int = 2,
) -> float:
    """0–1 how well wheat covers the herd (planted mouths + stock buffer)."""
    m = max(0, int(mouths))
    if m <= 0:
        return 1.0
    need = m + max(0, int(buffer))
    planted_ok = min(1.0, float(planted_wheat) / float(m))
    stock_ok = min(1.0, float(wheat_stock) / float(max(1, need)))
    return 0.5 * planted_ok + 0.5 * stock_ok


def land_after_printer(
    *,
    fill: float,
    empty: int,
    day_plantable: int,
) -> bool:
    """True when 1→2 land is allowed given printer fill and labor residual."""
    if int(day_plantable) <= 0 and int(empty) <= 2:
        return False
    if fill < 0.45 and int(empty) >= 4:
        return False
    return True


def prefer_plant_over_pasture(
    *,
    plant_gap: int,
    tile_ev: float,
    waiting_animals: int,
    animal_day_ev: float,
    at_risk: int,
    empty: int,
    primary_fill: float = 1.0,
) -> bool:
    """True when empties should go to the cash crop, not new pastures."""
    if int(waiting_animals) > 0:
        return False
    if int(at_risk) > 0:
        return True
    gap = max(0, int(plant_gap))
    if gap <= 0 or int(empty) <= 0:
        return False
    if float(primary_fill) >= 0.55:
        return False
    marginal = min(gap, int(empty), 6)
    plant_value = marginal * max(0.0, float(tile_ev))
    pasture_option = max(0.0, float(animal_day_ev))
    return plant_value > pasture_option * 2.5
