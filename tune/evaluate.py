"""tune/evaluate.py

Local evaluation helper for tuning.

It runs the current `main.py` agent against the Kaggriculture `starter`
bot over the provided seeds, and returns the agent's mean final reward.
"""

from __future__ import annotations

import argparse
import os
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

# Keep in sync with tests/test_regression.py
MEAN_SEEDS_15 = [42, 7, 13, 21, 33, 55, 89, 99, 123, 256, 777, 1024, 2024, 3141, 993781610]
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
# Extra 30: named hard/analysis maps from repo + prior chat evals, then
# unused small ints for shop-path diversity.
TUNE_SEEDS_EXTRA_30 = [
    761083594,  # playbook: early cow waste
    796605284,  # v2 pizza/bakery analysis
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
# Extra 60: Kaggle last3 / miss-seed coverage + holdout shop diversity.
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


def run_vs_starter(seed: int, *, episode_steps: int = 720) -> tuple[int, int]:
    # Kaggle runs the agent in a separate process; ensure it reads the
    # intended params file (and not a path relative to a temp working dir).
    os.environ.setdefault("KAGGRICULTURE_PARAMS_PATH", DEFAULT_PARAMS_PATH)
    env = make("kaggriculture", configuration={"episodeSteps": episode_steps, "seed": seed}, debug=False)
    env.run([_agent_path(), "starter"])
    return int(env.steps[-1][0]["reward"]), int(env.steps[-1][1]["reward"])


def run_vs_starter_env(
    seed: int, *, episode_steps: int = 720
) -> tuple[object, int, int]:
    """
    Like `run_vs_starter`, but also returns the full env so we can compute
    regression constraints (e.g., empty tile counts at day 16).
    """
    os.environ.setdefault("KAGGRICULTURE_PARAMS_PATH", DEFAULT_PARAMS_PATH)
    env = make(
        "kaggriculture", configuration={"episodeSteps": episode_steps, "seed": seed}, debug=False
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


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--episodeSteps", type=int, default=720)
    p.add_argument(
        "--seedSet",
        type=str,
        default="tune60",
        choices=["mean15", "tune30", "tune60", "tune120"],
    )
    p.add_argument("--seedCount", type=int, default=60)
    args = p.parse_args()

    if args.seedSet == "mean15":
        seeds_src = MEAN_SEEDS_15
    elif args.seedSet == "tune30":
        seeds_src = TUNE_SEEDS_30
    elif args.seedSet == "tune120":
        seeds_src = TUNE_SEEDS_120
    else:
        seeds_src = TUNE_SEEDS_60
    seeds = seeds_src[: args.seedCount or len(seeds_src)]
    mean, rows = evaluate_seeds(seeds, episode_steps=args.episodeSteps)
    for seed, us, starter in rows:
        print(seed, us, starter)
    print("mean", mean)
    scores = [us for _, us, _ in rows]
    scores_sorted = sorted(scores)
    n = len(scores_sorted)
    print("n", n)
    print("min", scores_sorted[0], "p10", scores_sorted[max(0, n // 10 - 1)], "median", scores_sorted[n // 2], "p90", scores_sorted[min(n - 1, (9 * n) // 10)], "max", scores_sorted[-1])
    worst = sorted(rows, key=lambda r: r[1])[:10]
    print("worst10", [(s, us) for s, us, _ in worst])


if __name__ == "__main__":
    main()

