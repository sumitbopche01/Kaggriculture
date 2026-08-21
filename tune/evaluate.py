"""tune/evaluate.py

Local evaluation helper for tuning.

Dual objectives (do not collapse into one mean without reporting both):
  - densify / mean30 — diverse shop/opener panel (mean15 = fast subset)
  - holdout / softfloor — maps outside the densify panel (incl. Kaggle misses)

Default opponent is starter (cheap). Use tune.ladder for real-bot WR/margin.
"""

from __future__ import annotations

import argparse
import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from kaggle_environments import make


ROOT = Path(__file__).resolve().parents[1]
AGENT = str(ROOT / "main.py")
DEFAULT_PARAMS_PATH = str(ROOT / "tune" / "params.json")


def _agent_path() -> str:
    """Override with KAGGRICULTURE_AGENT=main_v2.py for the target-design agent."""
    override = os.environ.get("KAGGRICULTURE_AGENT")
    if override:
        p = Path(override)
        if not p.is_absolute():
            p = ROOT / p
        return str(p)
    return AGENT


# ---------------------------------------------------------------------------
# Seed sets — keep MEAN_SEEDS_15 in sync with tests/test_regression.py
# ---------------------------------------------------------------------------

# Fast densify guard (CI / quick dial). Shop mixes are mostly unique but
# openers skew berry/milk; use MEAN_SEEDS_30 for diverse shop coverage.
MEAN_SEEDS_15 = [
    42,
    7,
    13,
    21,
    33,
    55,
    89,
    99,
    123,
    256,
    777,
    1024,
    2024,
    3141,
    993781610,
]

# Diverse primary densify panel = mean15 + 15 opener/shop fills.
# Fingerprinted @d16 (2026-08-21): covers pet/yarn/pizza/bakery/fm/ice/
# smoothie/brunch openers that mean15 under-samples.
MEAN_SEEDS_30 = [
    # --- mean15 anchors ---
    42,  # berry+fm+ice+milk+pet+smoothie
    7,  # berry+fm+ice+milk+pet+pizza
    13,  # bakery+berry+brunch+ice+milk+pet+smoothie
    21,  # bakery+berry+brunch+ice+milk+pizza+yarn
    33,  # bakery+milk+pet+pizza (tomato/pizza)
    55,  # bakery+berry+ice+milk+pet+smoothie+yarn
    89,  # berry+fm+milk+pizza+smoothie+yarn
    99,  # bakery+berry+milk+pizza+smoothie+yarn
    123,  # berry+brunch+fm+milk+pet+pizza+smoothie
    256,  # bakery+berry+brunch+milk+pizza+smoothie
    777,  # bakery+berry+brunch+fm+milk+pet+pizza
    1024,  # berry+brunch+fm+ice+milk+yarn (yarn opener)
    2024,  # bakery+berry+brunch+ice+milk+pizza
    3141,  # bakery+berry+brunch+fm+milk+smoothie
    993781610,  # berry+brunch+ice+milk+pet+smoothie
    # --- diversity fills (opener → d16 mix) ---
    500,  # pet opener → berry+ice+milk+pet
    111111,  # yarn opener → berry+milk+pizza+smoothie+yarn
    2025,  # bakery+yarn → bakery+berry+brunch+pet+yarn
    195016893,  # pizza/milk → bakery+berry+ice+milk+pet+pizza
    827875246,  # late berry bakery → bakery+berry+milk+pet+smoothie+yarn
    458695376,  # bakery+pet → bakery+berry+brunch+fm+pet
    801568323,  # fm+pet (weak milk) → berry+fm+pet+yarn
    838377008,  # ice/smoothie path → berry+fm+ice+milk+smoothie
    14,  # berry+smoothie+yarn → berry+ice+milk+smoothie+yarn
    12,  # softfloor index → berry+fm+ice+milk+pet+yarn
    4,  # berry+milk+smoothie → bakery+berry+brunch+milk+smoothie
    10,  # brunch+ice+milk → berry+brunch+ice+milk+pizza
    1,  # berry+fm+yarn → bakery+berry+fm+ice+milk+pizza+yarn
    796605284,  # bakery+pizza → bakery+berry+brunch+ice+milk+pizza+smoothie
    49090797,  # ice+milk+pet → berry+brunch+ice+milk+pet+smoothie
]

# Softfloor / expand-path focus (subset + known hollow expand maps).
SOFTFLOOR_SEEDS = [
    12,
    21,
    33,
    123,
    2024,
    3141,
    993781610,
    49090797,
    1827862996,  # Kaggle miss / user holdout
]

# Holdouts outside MEAN_SEEDS_30 (true OOD / Kaggle misses / ladder).
# Seeds promoted into mean30 were removed from this list.
HOLDOUT_SEEDS = [
    1827862996,
    844116305,
    1286627911,
    1294758216,
    1313863753,
    1347293729,
    1742050014,
    1839364137,
    1876524520,
    1878203523,
    2107127554,
    2063069147,
    761083594,
    1571069459,
    2119622091,
    1295704409,
    1012421698,
    1060428368,
    1584566076,
    1184506744,
]

# "30 seeds" = MEAN_SEEDS (15) + EXTRA_SEEDS (13) + {2063069147, 195016893}
TUNE_SEEDS_30 = [
    42,
    7,
    13,
    21,
    33,
    55,
    89,
    99,
    123,
    256,
    777,
    1024,
    2024,
    3141,
    993781610,
    1,
    2,
    100,
    500,
    1000,
    2025,
    9999,
    12345,
    54321,
    111111,
    1918864023,
    458695376,
    827875246,
    2063069147,
    195016893,
]
TUNE_SEEDS_EXTRA_30 = [
    761083594,
    796605284,
    1012421698,
    1060428368,
    1194218470,
    1594992029,
    1763244299,
    1941500822,
    456398262,
    49090797,
    529524938,
    628776362,
    801568323,
    838377008,
    965622909,
    232697454,
    25138847,
    438977009,
    94031431,
    1584566076,
    3,
    4,
    5,
    6,
    8,
    9,
    10,
    11,
    12,
    14,
]
TUNE_SEEDS_60 = TUNE_SEEDS_30 + TUNE_SEEDS_EXTRA_30
TUNE_SEEDS_EXTRA_60 = [
    0,
    37514770,
    96823174,
    102771766,
    104793062,
    137383801,
    177371887,
    201109396,
    212801414,
    214408169,
    269540093,
    316945216,
    343635847,
    360922415,
    375954346,
    384976034,
    402898773,
    406050412,
    409488828,
    439973987,
    466183955,
    510360931,
    538446151,
    576467774,
    677151940,
    687822168,
    697247901,
    714754495,
    796493074,
    897688219,
    933171150,
    958183153,
    1042860465,
    1043041600,
    1055941047,
    1163631300,
    1210701737,
    1245111266,
    1279909885,
    1331251194,
    1360331963,
    1371318646,
    1373792371,
    1386607876,
    1396284857,
    1397505211,
    1440364774,
    1470163932,
    1493493436,
    1506490507,
    1511764748,
    1514404541,
    1532410732,
    1603554153,
    1606600003,
    1611947564,
    1613212566,
    1673247076,
    1678164798,
    1740485088,
]
TUNE_SEEDS_120 = TUNE_SEEDS_60 + TUNE_SEEDS_EXTRA_60

SEED_SETS: dict[str, list[int]] = {
    "mean15": MEAN_SEEDS_15,
    "mean30": MEAN_SEEDS_30,
    "softfloor": SOFTFLOOR_SEEDS,
    "holdout": HOLDOUT_SEEDS,
    "dual": MEAN_SEEDS_30 + [s for s in HOLDOUT_SEEDS if s not in MEAN_SEEDS_30],
    "tune30": TUNE_SEEDS_30,
    "tune60": TUNE_SEEDS_60,
    "tune120": TUNE_SEEDS_120,
}


@dataclass(frozen=True)
class PathMetrics:
    """Softfloor / densify path diagnostics — score alone hides hollow stalls."""

    seed: int
    score: int
    starter: int
    land_buys: int
    plot3: bool
    cows_d10: int
    empty_d16: int
    berry_d16: int
    tomato_d16: int
    quads_d16: int


def dawn_step(day: int) -> int:
    return day * 24


def _crop_count(obs: dict, crop: str) -> int:
    me = obs["farms"][obs["player"]]
    n = 0
    for row in me["tiles"]:
        for t in row:
            if isinstance(t, dict) and t.get("crop") == crop:
                n += 1
    return n


def _animal_count(obs: dict) -> dict[str, int]:
    me = obs["farms"][obs["player"]]
    counts: Counter[str] = Counter()
    for row in me["tiles"]:
        for t in row:
            if isinstance(t, dict) and t.get("animal"):
                counts[str(t["animal"])] += 1
    return dict(counts)


def _empty_count(obs: dict) -> int:
    me = obs["farms"][obs["player"]]
    return sum(1 for row in me["tiles"] for t in row if t is None)


def _quads(obs: dict) -> int:
    me = obs["farms"][obs["player"]]
    return len(me.get("unlocked_quadrants") or [])


def path_metrics_from_env(env: object, seed: int, us: int, starter: int) -> PathMetrics:
    steps = env.steps  # type: ignore[attr-defined]
    land_buys = 0
    for i, step in enumerate(steps[:-1]):
        acts = (steps[i + 1][0].get("action") or {}).get("market") or []
        if any(a and a[0] == "BUY_LAND" for a in acts):
            land_buys += 1

    d10 = min(dawn_step(10), len(steps) - 1)
    d16 = min(dawn_step(16), len(steps) - 1)
    obs10 = steps[d10][0]["observation"]
    obs16 = steps[d16][0]["observation"]
    cows = _animal_count(obs10).get("COW", 0)
    return PathMetrics(
        seed=seed,
        score=us,
        starter=starter,
        land_buys=land_buys,
        plot3=land_buys >= 2,
        cows_d10=cows,
        empty_d16=_empty_count(obs16),
        berry_d16=_crop_count(obs16, "STRAWBERRY"),
        tomato_d16=_crop_count(obs16, "TOMATO"),
        quads_d16=_quads(obs16),
    )


def run_vs_starter(seed: int, *, episode_steps: int = 720) -> tuple[int, int]:
    # Kaggle runs the agent in a separate process; ensure it reads the
    # intended params file (and not a path relative to a temp working dir).
    os.environ.setdefault("KAGGRICULTURE_PARAMS_PATH", DEFAULT_PARAMS_PATH)
    env = make(
        "kaggriculture",
        configuration={"episodeSteps": episode_steps, "seed": seed},
        debug=False,
    )
    env.run([_agent_path(), "starter"])
    return int(env.steps[-1][0]["reward"]), int(env.steps[-1][1]["reward"])


def run_vs_starter_env(
    seed: int, *, episode_steps: int = 720
) -> tuple[object, int, int]:
    """
    Like `run_vs_starter`, but also returns the full env so we can compute
    regression constraints / path metrics.
    """
    os.environ.setdefault("KAGGRICULTURE_PARAMS_PATH", DEFAULT_PARAMS_PATH)
    env = make(
        "kaggriculture",
        configuration={"episodeSteps": episode_steps, "seed": seed},
        debug=False,
    )
    env.run([_agent_path(), "starter"])
    us = int(env.steps[-1][0]["reward"])
    starter = int(env.steps[-1][1]["reward"])
    return env, us, starter


def evaluate_seeds(
    seeds: Iterable[int], *, episode_steps: int = 720
) -> tuple[float, list[tuple[int, int, int]]]:
    rows: list[tuple[int, int, int]] = []
    scores: list[int] = []
    for seed in seeds:
        us, starter = run_vs_starter(seed, episode_steps=episode_steps)
        scores.append(us)
        rows.append((seed, us, starter))
    mean = sum(scores) / len(scores) if scores else 0.0
    return mean, rows


def evaluate_seeds_with_paths(
    seeds: Iterable[int], *, episode_steps: int = 720
) -> tuple[float, list[PathMetrics]]:
    paths: list[PathMetrics] = []
    for seed in seeds:
        env, us, starter = run_vs_starter_env(seed, episode_steps=episode_steps)
        paths.append(path_metrics_from_env(env, seed, us, starter))
    mean = sum(p.score for p in paths) / len(paths) if paths else 0.0
    return mean, paths


def _print_score_summary(label: str, rows: list[tuple[int, int, int]]) -> None:
    scores = [us for _, us, _ in rows]
    if not scores:
        print(label, "empty")
        return
    scores_sorted = sorted(scores)
    n = len(scores_sorted)
    print(f"=== {label} ===")
    for seed, us, starter in rows:
        print(seed, us, starter)
    print("mean", sum(scores) / n)
    print("n", n)
    print(
        "min",
        scores_sorted[0],
        "p10",
        scores_sorted[max(0, n // 10 - 1)],
        "median",
        scores_sorted[n // 2],
        "p90",
        scores_sorted[min(n - 1, (9 * n) // 10)],
        "max",
        scores_sorted[-1],
    )
    worst = sorted(rows, key=lambda r: r[1])[:5]
    print("worst5", [(s, us) for s, us, _ in worst])


def _print_path_summary(label: str, paths: list[PathMetrics]) -> None:
    if not paths:
        return
    print(f"=== {label} paths ===")
    print(
        "seed score lands plot3 cows@d10 empty@d16 berry@d16 tom@d16 quads@d16"
    )
    for p in paths:
        print(
            f"{p.seed} {p.score} {p.land_buys} {int(p.plot3)} "
            f"{p.cows_d10} {p.empty_d16} {p.berry_d16} {p.tomato_d16} {p.quads_d16}"
        )
    n = len(paths)
    plot3 = sum(1 for p in paths if p.plot3)
    ge90 = sum(1 for p in paths if p.score >= 90000)
    ge100 = sum(1 for p in paths if p.score >= 100000)
    print(
        f"path_summary mean={sum(p.score for p in paths) / n:.1f} "
        f"plot3+={plot3}/{n} >=90k={ge90} >=100k={ge100} "
        f"mean_cows_d10={sum(p.cows_d10 for p in paths) / n:.1f}"
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--episodeSteps", type=int, default=720)
    p.add_argument(
        "--seedSet",
        type=str,
        default="dual",
        choices=list(SEED_SETS.keys()),
        help="mean15=fast densify; mean30=diverse densify; holdout/softfloor=expand; dual=mean30+holdout",
    )
    p.add_argument("--seedCount", type=int, default=0, help="0 = all in seedSet")
    p.add_argument(
        "--paths",
        action="store_true",
        help="Print path metrics (plot3, cows@d10, empty/berry@d16)",
    )
    p.add_argument(
        "--also-ladder-hint",
        action="store_true",
        help="Print reminder to run tune.ladder after densify moves",
    )
    args = p.parse_args()

    if args.seedSet == "dual":
        # Always report densify and holdout separately — never one blended mean.
        densify = MEAN_SEEDS_30
        holdout = [s for s in HOLDOUT_SEEDS if s not in MEAN_SEEDS_30]
        if args.paths:
            m30, p30 = evaluate_seeds_with_paths(
                densify, episode_steps=args.episodeSteps
            )
            mh, ph = evaluate_seeds_with_paths(
                holdout, episode_steps=args.episodeSteps
            )
            _print_path_summary("densify/mean30", p30)
            _print_path_summary("holdout", ph)
            print(
                f"DUAL densify_mean={m30:.1f} holdout_mean={mh:.1f} "
                f"(do not average these into one north-star)"
            )
        else:
            m30, r30 = evaluate_seeds(densify, episode_steps=args.episodeSteps)
            mh, rh = evaluate_seeds(holdout, episode_steps=args.episodeSteps)
            _print_score_summary("densify/mean30", r30)
            _print_score_summary("holdout", rh)
            print(
                f"DUAL densify_mean={m30:.1f} holdout_mean={mh:.1f} "
                f"(do not average these into one north-star)"
            )
    else:
        seeds_src = SEED_SETS[args.seedSet]
        n = args.seedCount or len(seeds_src)
        seeds = list(seeds_src[:n])
        if args.paths:
            mean, paths = evaluate_seeds_with_paths(
                seeds, episode_steps=args.episodeSteps
            )
            rows = [(p.seed, p.score, p.starter) for p in paths]
            _print_score_summary(args.seedSet, rows)
            _print_path_summary(args.seedSet, paths)
        else:
            mean, rows = evaluate_seeds(seeds, episode_steps=args.episodeSteps)
            _print_score_summary(args.seedSet, rows)
        print("mean", mean)

    if args.also_ladder_hint or args.seedSet in ("mean15", "mean30", "dual"):
        print(
            "NOTE: starter-mean is a densify proxy. After policy changes, also run:\n"
            "  .venv/bin/python -m tune.ladder --seedSet ladder20 --opponents frozen_73k6"
        )


if __name__ == "__main__":
    main()
