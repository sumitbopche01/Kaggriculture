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
        choices=["mean15", "tune30", "tune60"],
    )
    p.add_argument("--seedCount", type=int, default=60)
    args = p.parse_args()

    if args.seedSet == "mean15":
        seeds_src = MEAN_SEEDS_15
    elif args.seedSet == "tune30":
        seeds_src = TUNE_SEEDS_30
    else:
        seeds_src = TUNE_SEEDS_60
    seeds = seeds_src[: args.seedCount]
    mean, rows = evaluate_seeds(seeds, episode_steps=args.episodeSteps)
    for seed, us, starter in rows:
        print(seed, us, starter)
    print("mean", mean)


if __name__ == "__main__":
    main()

