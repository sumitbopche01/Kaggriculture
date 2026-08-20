"""brain/v2/budget.py — wheat → primary → garnish tile allocation.

Target design order:
1. Wheat (SCALE: mouths+buffer; PETS: mouths)
2. Primary from crop_line
3. Garnish (carrot / late berry) at small cap
4. Pasture hole (2 empty if SCALE and cow buy imminent) — handled in field
5. Leftover: OPEN/FEED → wheat (bakery bait); STRAWBERRY empty;
   TOMATO +tomato then wheat
"""

from __future__ import annotations

from typing import Any

from brain.v2.lines import crop_line_of, herd_line_of

# Caps match playbook tables used in v1.
PRIMARY_TILE_BASE = {1: 8, 2: 28, 3: 48, 4: 60}
TOMATO_PRIMARY_BASE = {1: 4, 2: 16, 3: 28, 4: 40}
SECONDARY_TILE_BASE = {1: 4, 2: 8, 3: 12, 4: 16}


def _n(n_quads: int) -> int:
    return 1 if n_quads <= 1 else min(4, int(n_quads))


def primary_cap(crop: str, n_quads: int, demand_count: int = 1) -> int:
    n = _n(n_quads)
    if crop == "STRAWBERRY":
        base = PRIMARY_TILE_BASE[n]
        step = 4
    elif crop == "TOMATO":
        base = TOMATO_PRIMARY_BASE[n]
        step = 2
    else:
        return 0
    d = max(1, int(demand_count))
    return base + step * (d - 1) if d > 1 else base


def garnish_cap(n_quads: int) -> int:
    return SECONDARY_TILE_BASE[_n(n_quads)]


def late_berry_tiles(
    s: dict[str, Any],
    leftover: int,
    n_quads: int,
    *,
    strawberry_ok: bool,
) -> int:
    """Berry garnish on a TOMATO lock after a late berry shop opens.

    Keep the garnish small — late ice cream does not out-earn milk scale on
    pizza maps. When EV gates shut after the plant window, hold planted+seeded
    berries instead of collapsing the plan to zero.
    """
    demand = s.get("demand") or {}
    if int(demand.get("STRAWBERRY", 0) or 0) < 1:
        return 0
    have = int((s.get("crops") or {}).get("STRAWBERRY", 0) or 0) + int(
        (s.get("seeds") or {}).get("STRAWBERRY", 0) or 0
    )
    want = garnish_cap(n_quads)
    if not strawberry_ok:
        return min(leftover, have)
    return min(leftover, want)


def wheat_tiles(
    s: dict[str, Any],
    *,
    wheat_min: int = 6,
    wheat_buffer: int = 2,
    wheat_no_mouth: int = 4,
) -> int:
    mouths = int(s.get("cows") or 0) + int(s.get("sheep") or 0) + int(s.get("geese") or 0)
    if mouths <= 0:
        return wheat_no_mouth
    if herd_line_of(s) == "SCALE":
        return max(wheat_min, mouths + wheat_buffer)
    return max(wheat_min, mouths)


def build_crop_plan(
    s: dict[str, Any],
    *,
    seed_keys: tuple[str, ...] = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON"),
    wheat_min: int = 6,
    wheat_buffer: int = 2,
    wheat_no_mouth: int = 4,
    wheat_override: int | None = None,
) -> dict[str, int]:
    """Allocate tiles. OPEN → wheat only (no cash crop)."""
    tiles = int(s.get("n_quads") or 1) * 25
    plan = {c: 0 for c in seed_keys}
    if wheat_override is not None:
        w = int(wheat_override)
    else:
        w = wheat_tiles(
            s, wheat_min=wheat_min, wheat_buffer=wheat_buffer, wheat_no_mouth=wheat_no_mouth
        )
    plan["WHEAT"] = min(tiles, w)
    leftover = max(0, tiles - plan["WHEAT"])

    crop = crop_line_of(s)
    demand = s.get("demand") or {}
    n_quads = int(s.get("n_quads") or 1)

    if crop == "OPEN":
        # Fill leftover wheat while unlocked. Idle empty boards pull pet-café /
        # pizza; wheat advertises bakeries so FEED can soft-upgrade into a
        # berry lock (seed 796: pizza path ~43k vs bakery→smoothie ~50k+).
        plan["WHEAT"] += leftover
        return plan

    if crop == "FEED":
        plan["WHEAT"] += leftover
        return plan

    strawberry_ok = bool(s.get("strawberry_ok", True))
    tomato_ok = bool(s.get("tomato_ok", True))

    if crop == "STRAWBERRY":
        cap = primary_cap("STRAWBERRY", n_quads, int(demand.get("STRAWBERRY", 0) or 1))
        if not strawberry_ok:
            # Hold / replant what we have. Do not expand into glut.
            have = int((s.get("crops") or {}).get("STRAWBERRY", 0) or 0) + int(
                (s.get("seeds") or {}).get("STRAWBERRY", 0) or 0
            )
            cap = min(cap, have)
        n = min(leftover, cap)
        plan["STRAWBERRY"] = n
        leftover -= n
        # Garnish carrot only if a carrot shop is open.
        if leftover > 0 and int(demand.get("CARROT", 0) or 0) >= 1:
            g = min(leftover, garnish_cap(n_quads))
            plan["CARROT"] = g
            leftover -= g
        # Leftover stays empty on strawberry maps.
        return plan

    if crop == "TOMATO":
        cap = primary_cap("TOMATO", n_quads, int(demand.get("TOMATO", 0) or 1))
        if not tomato_ok:
            have = int((s.get("crops") or {}).get("TOMATO", 0) or 0) + int(
                (s.get("seeds") or {}).get("TOMATO", 0) or 0
            )
            cap = min(cap, have)
        # Late berry shop: reserve berry tiles *before* tomato densifies.
        berry_want = late_berry_tiles(
            s, leftover, n_quads, strawberry_ok=strawberry_ok
        )
        tomato_room = max(0, leftover - berry_want)
        n = min(tomato_room, cap)
        plan["TOMATO"] = n
        leftover -= n
        if berry_want > 0 and leftover > 0:
            g = min(leftover, berry_want)
            plan["STRAWBERRY"] = g
            leftover -= g
        if leftover > 0 and int(demand.get("CARROT", 0) or 0) >= 1:
            g = min(leftover, garnish_cap(n_quads))
            plan["CARROT"] = g
            leftover -= g
        # Tomato leftover densifies a little, then wheat — never into berry.
        if leftover > 0 and tomato_ok:
            extra = min(leftover, 8)
            plan["TOMATO"] += extra
            leftover -= extra
        if leftover > 0:
            plan["WHEAT"] += leftover
        return plan

    return plan
