"""Schedule priors mined from strong ladder replays.

`analysis/mine_schedules.py` writes `schedules_by_archetype.json`.
This module loads those medians so policy can steal hire/land/dump/herd
timing instead of only tuning against starter.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
# Prefer elite external winners (top5 + $70k+ non-self) over the
# self-polluted ladder dump when both exist.
_ELITE = ROOT / "analysis" / "schedules_by_archetype_elite.json"
_DEFAULT = ROOT / "analysis" / "schedules_by_archetype.json"
DEFAULT_PATH = _ELITE if _ELITE.is_file() else _DEFAULT


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
    p = prior_for("BERRY")
    d = p.get("median_dump_day")
    if d is None:
        return default
    return int(round(float(d)))


def hire_target_day(day: int, default: int = 5) -> int:
    """Median winner hires on this day (berry corpus)."""
    p = prior_for("BERRY")
    curve = p.get("hire_curve_median") or {}
    v = curve.get(str(int(day)))
    if v is None:
        return default
    return max(0, int(round(float(v))))
