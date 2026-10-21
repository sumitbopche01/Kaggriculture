"""Schedule priors mined from strong ladder / top-player replays.

`analysis/mine_schedules.py` writes `schedules_by_archetype_*.json`.
This module loads those medians so policy can follow hire/land/dump/herd
timing instead of only tuning against starter.

Corpora (2026-08-21):
  - elite / ladder85k: land2≈10.5, cows≈9.5, dump≈27.5, hire thick early
  - top5: land2≈10, berry≈32, dump≈29, full crew≈d7
  - softfloor $100k: land2≈10, cows≈8, berry≈35, dump≈28, hands≈13
  - Live ladder, herd-heavy: cows d6:3 → d7:6 → d8:8; land [6,10]; dump d29
  - Live ladder, berry-heavy: cows@10=6, berry≈39, land [7,10], hands@8≈11
"""

from __future__ import annotations

import json
import statistics
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
# Elite external winners for hire priors. Softfloor / top5 used for dump + land2.
_ELITE = ROOT / "analysis" / "schedules_by_archetype_elite.json"
_SOFTFLOOR = ROOT / "analysis" / "schedules_by_archetype_softfloor100k.json"
_TOP5 = ROOT / "analysis" / "schedules_by_archetype_top5.json"
_DEFAULT = ROOT / "analysis" / "schedules_by_archetype.json"
DEFAULT_PATH = _ELITE if _ELITE.is_file() else _DEFAULT

# Post-land1 herd ramp: live ladder median (5 seeds).
# Softfloor router only; densify printers stay off this curve.
_SOFTFLOOR_COW_BY_DAY: dict[int, int] = {
    0: 3,
    1: 3,
    2: 3,
    3: 3,
    4: 3,
    5: 3,
    6: 3,
    7: 6,
    8: 8,
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


def _median_prior_field(field: str, paths: tuple[Path, ...]) -> float | None:
    vals: list[float] = []
    for path in paths:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        p = data.get("BERRY") or data.get("ALL") or {}
        d = p.get(field)
        if d is not None:
            vals.append(float(d))
    if not vals:
        return None
    return float(statistics.median(vals))


def berry_land2_day(default: int = 10) -> int:
    """Median day winners unlock plot-3 (top5/softfloor/elite ≈ 10–11)."""
    d = _median_prior_field(
        "median_land2_day", (_SOFTFLOOR, _TOP5, DEFAULT_PATH)
    )
    if d is None:
        return int(default)
    return int(round(d))


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
    """Blend softfloor (~28) + top5 (~29) + elite (~27.5) dump medians."""
    d = _median_prior_field(
        "median_dump_day", (_SOFTFLOOR, _TOP5, DEFAULT_PATH)
    )
    if d is None:
        return int(default)
    return int(round(d))


def softfloor_cow_target_day(day: int, cap: int = 8) -> int:
    """Elite softfloor cows-by-day; cap keeps densify from overshooting early."""
    d = int(day)
    raw = _SOFTFLOOR_COW_BY_DAY.get(d)
    if raw is None:
        raw = 10 if d > 12 else int(cap)
    return max(0, min(int(cap) if d <= 10 else max(int(cap), 10), int(raw)))


def softfloor_hire_target_day(day: int, default: int = 9) -> int:
    """Softfloor crew target (full crew ≈ d7–8)."""
    # Prefer top5 curve (thicker than softfloor early hire which crashes densify).
    for path in (_TOP5, _ELITE):
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        p = data.get("BERRY") or data.get("ALL") or {}
        curve = p.get("hire_curve_median") or {}
        v = curve.get(str(int(day)))
        if v is not None:
            return max(0, int(round(float(v))))
    return int(default)


def hire_target_day(day: int, default: int = 5) -> int:
    """Median winner roster size on this day (berry corpus)."""
    p = prior_for("BERRY")
    curve = p.get("hire_curve_median") or {}
    v = curve.get(str(int(day)))
    if v is None:
        return default
    return max(0, int(round(float(v))))
