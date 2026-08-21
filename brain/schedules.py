"""Schedule priors mined from strong ladder replays.

`analysis/mine_schedules.py` writes `schedules_by_archetype.json`.
This module loads those medians so policy can steal hire/land/dump/herd
timing instead of only tuning against starter.

Live softfloor H2H curves (structured / frontier_soil / top10_read on
softfloor seeds, 2026-08-21): cows d6:3 → d7:6 → d8:7 → d9:8 → d11:10;
land2 ≈ d10; dump ≈ d28–29; berry peak ≈ 33–36 while filling empties.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
# Elite external winners for hire/dump priors. Softfloor $100k corpus is used
# for land2 day docs / calendar steal (see analysis/plot3_steal_*.md) but its
# early hire curve is thinner and crashes densify if loaded wholesale.
_ELITE = ROOT / "analysis" / "schedules_by_archetype_elite.json"
_SOFTFLOOR = ROOT / "analysis" / "schedules_by_archetype_softfloor100k.json"
_DEFAULT = ROOT / "analysis" / "schedules_by_archetype.json"
DEFAULT_PATH = _ELITE if _ELITE.is_file() else _DEFAULT

# Post-land1 herd ramp stolen from softfloor elites (median across 9 bot×seed).
# Densify printers fill empties fast; schedule only applies while empty is soft.
_SOFTFLOOR_COW_BY_DAY: dict[int, int] = {
    0: 3,
    1: 3,
    2: 3,
    3: 3,
    4: 3,
    5: 3,
    6: 3,
    7: 6,
    8: 7,
    9: 8,
    10: 8,
    11: 10,
    12: 10,
}


@lru_cache(maxsize=1)
def load_priors(path: str | None = None) -> dict[str, Any]:
    p = Path(path) if path else DEFAULT_PATH
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def prior_for(archetype: str) -> dict[str, Any]:
    data = load_priors()
    if not data:
        return {}
    return dict(data.get(archetype) or data.get("BERRY") or data.get("ALL") or {})


def berry_land2_strawberry_floor(default: int = 16) -> int:
    """Winners buy plot-3 around day 11 with ~10–12 berries planted — not 16."""
    p = prior_for("BERRY")
    peak = p.get("median_berry_peak")
    if peak is None:
        return default
    # Allow land2 slightly before the median peak stand.
    return max(8, min(int(default), int(round(float(peak) - 1))))


def berry_land2_day(default: int = 10) -> int:
    """Median day winners unlock plot-3 (ladder elites ≈ 10–11)."""
    p = prior_for("BERRY")
    d = p.get("median_land2_day")
    if d is None:
        return int(default)
    return int(round(float(d)))


def berry_cow_cap(default: int = 6) -> int:
    """Berry+milk dual maps: winners run ~6–10 cows, not a 2-cow floor."""
    p = prior_for("BERRY")
    cows = p.get("median_cows_peak")
    # Never let a soft elite median *lower* a configured cap (H2H regression).
    floor = int(default)
    if cows is None:
        return floor
    return max(floor, min(10, int(round(float(cows)))))


def late_dump_day(default: int = 27) -> int:
    """Prefer softfloor dump median (~28) when corpus exists; else elite."""
    for path in (_SOFTFLOOR, DEFAULT_PATH):
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        p = data.get("BERRY") or data.get("ALL") or {}
        d = p.get("median_dump_day")
        if d is not None:
            return int(round(float(d)))
    return int(default)


def softfloor_cow_target_day(day: int, cap: int = 8) -> int:
    """Elite softfloor cows-by-day; cap keeps densify from overshooting early."""
    d = int(day)
    raw = _SOFTFLOOR_COW_BY_DAY.get(d)
    if raw is None:
        raw = 10 if d > 12 else int(cap)
    return max(0, min(int(cap) if d <= 10 else max(int(cap), 10), int(raw)))


def hire_target_day(day: int, default: int = 5) -> int:
    """Median winner roster size on this day (berry corpus)."""
    p = prior_for("BERRY")
    curve = p.get("hire_curve_median") or {}
    v = curve.get(str(int(day)))
    if v is None:
        return default
    return max(0, int(round(float(v))))
