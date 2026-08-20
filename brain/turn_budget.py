"""TurnBudget — labor, day capacity, and project NPV for one hour.

Hourly plantable is free workers after feed/water. Day capacity is what
the crew can plant after the live field is watered at the next dawn —
that is the number land/seed limbs may actually realize.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

ProjectKind = Literal["land", "cow", "seed", "none"]


@dataclass(frozen=True)
class TurnBudget:
    """Capacity snapshot for one agent step."""

    workers: int
    hungry: int
    unwatered: int
    at_risk: int
    live_tiles: int
    empty: int
    plantable: int
    day_plantable: int
    tile_ev: float
    productive_days: int
    hour: int


def compute_turn_budget(
    s: dict[str, Any],
    *,
    cash_crop: str,
    tile_ev: float,
    productive_days: int,
) -> TurnBudget:
    """Hour plantable + multi-dawn residual after watering the live field."""
    workers = int(s.get("workers") or 0)
    hungry = int(s.get("hungry") or 0)
    unwatered = int(s.get("unwatered") or 0)
    at_risk = int(s.get("at_risk") or 0)
    hour = int(s.get("hour") or 0)
    live = 0
    if cash_crop:
        live = int((s.get("crops") or {}).get(cash_crop, 0) or 0)
    empty = int(s.get("empty") or 0)
    free = max(0, workers - hungry)
    # This hour: after mouths and still-dry plants.
    plantable = max(0, free - unwatered)
    # Next two dawns: water live each morning, plant the residual.
    # Packed 40-tile boards with 12 hands → 0. Fresh 1→2 with 8 live → 8.
    day_plantable = max(0, 2 * free - live)
    return TurnBudget(
        workers=workers,
        hungry=hungry,
        unwatered=unwatered,
        at_risk=at_risk,
        live_tiles=live,
        empty=empty,
        plantable=plantable,
        day_plantable=day_plantable,
        tile_ev=max(0.0, float(tile_ev)),
        productive_days=max(0, int(productive_days)),
        hour=hour,
    )


def post_land_seed_cap(*, workers: int, hungry: int, live_tiles: int, empty: int) -> int:
    """Seeds after land: two-dawn residual, never more than new empties."""
    free = max(0, int(workers) - int(hungry))
    residual = max(0, 2 * free - int(live_tiles))
    return min(residual, max(0, int(empty)))


def skip_days_after_land(*, live_tiles: int, extra_empty: int, workers: int) -> float:
    """Days the live field waits if we add a new plot (dawn water first)."""
    w = max(1, int(workers))
    # Two dawns of labor before the new plot is expected full.
    backlog = max(0, int(live_tiles) + int(extra_empty) - 2 * w)
    return backlog / float(w)


def land_expansion_npv(
    *,
    plantable_new: int,
    tile_ev: float,
    productive_days: int,
    land_cost: int,
    seed_cost: int,
    live_tiles: int,
    skip_days: float,
) -> float:
    """NPV of the next quad using dawn-capacity tiles, not fantasy 25."""
    fill_n = max(0, int(plantable_new))
    ev = max(0.0, float(tile_ev))
    days = max(0, int(productive_days))
    realized = fill_n * ev * days
    fill_cost = fill_n * max(0, int(seed_cost))
    damage = max(0, int(live_tiles)) * ev * max(0.0, float(skip_days))
    return realized - int(land_cost) - fill_cost - damage


def cow_project_ev(*, cow_ev: float, cow_cost: int) -> float:
    """Net EV of spending cow_cost on one cow (already amortized in animal_score)."""
    if cow_ev <= 0 or cow_cost <= 0:
        return 0.0
    return float(cow_ev)


def seed_project_ev(
    *,
    tile_ev: float,
    productive_days: int,
    n_seeds: int,
    seed_cost: int,
) -> float:
    n = max(0, int(n_seeds))
    if n <= 0:
        return 0.0
    return n * max(0.0, float(tile_ev)) * max(0, int(productive_days)) - n * max(
        0, int(seed_cost)
    )


def choose_project(
    *,
    land_npv: float,
    can_land: bool,
    cow_ev: float,
    can_cow: bool,
    seed_ev: float,
    can_seed: bool,
) -> ProjectKind:
    """Pick the single best cash project this market hour."""
    best: ProjectKind = "none"
    best_score = 0.0
    if can_land and land_npv > best_score:
        best, best_score = "land", land_npv
    if can_cow and cow_ev > best_score:
        best, best_score = "cow", cow_ev
    if can_seed and seed_ev > best_score:
        best, best_score = "seed", seed_ev
    return best


def cow_beats_seeds(
    *,
    cow_ev: float,
    tile_ev: float,
    cow_cost: int,
    seed_cost: int,
    plantable: int,
    empty: int,
    buy_gap: int,
) -> bool:
    """True when a cow is a better leftover-cash project than engine seeds."""
    if cow_ev <= 0:
        return False
    if plantable > 0 and empty > 0 and buy_gap > 0:
        seed_c = max(1, int(seed_cost))
        alt = max(0.0, float(tile_ev)) * (int(cow_cost) / float(seed_c))
        return float(cow_ev) > alt
    return True
