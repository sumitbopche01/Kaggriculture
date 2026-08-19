"""tune/optimize.py

Optuna-based parameter tuning for the Kaggriculture heuristic agent.

Each trial:
  1) Samples a param set
  2) Writes it to `tune/params.json`
  3) Evaluates the agent on a seed list via `tune/evaluate.py`

The agent (`main.py`) reads `./tune/params.json` automatically.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import optuna
from optuna.exceptions import TrialPruned

from evaluate import TUNE_SEEDS_30, run_vs_starter, run_vs_starter_env


ROOT = Path(__file__).resolve().parents[1]
PARAMS_PATH = ROOT / "tune" / "params.json"
BEST_PATH = ROOT / "tune" / "best_params.json"
DB_PATH = ROOT / "tune" / "optuna.db"

# Regression guards (subset) to prevent brittle params.
# These match the failure modes we saw during tuning:
# - reward floors
# - day-16 empty tile ceiling when a berry shop is open and quads >= 3
REG_GUARD_REWARD: dict[int, int] = {
    827875246: 50000,  # LateBerryBakeryMap
    993781610: 50000,  # LandSprintRegression
    89: 40000,  # LandSprintRegression
}
REG_GUARD_EMPTY_SEEDS: set[int] = {993781610, 89}

_BERRY_SHOPS = {"SMOOTHIE_SHOP", "BRUNCH_SPOT", "ICE_CREAM_SHOP", "FARMERS_MARKET"}


def dawn_step(day: int) -> int:
    return day * 24


def berry_shop_open(env: object, step_i: int) -> bool:
    obs = env.steps[step_i][0]["observation"]
    unlocked = list(obs.get("town", {}).get("unlocked_shops") or [])
    return any(name in _BERRY_SHOPS for name in unlocked)


def empty_at_step(env: object, step_i: int) -> int:
    me = env.steps[step_i][0]["observation"]["farms"][0]
    return sum(1 for row in me["tiles"] for t in row if t is None)


def _write_params(params: dict) -> None:
    PARAMS_PATH.write_text(json.dumps(params, indent=2, sort_keys=True), encoding="utf-8")


def _suggest_params(trial: optuna.trial.Trial) -> dict[str, int | float]:
    """
    Search space for main.py PARAMS keys.
    Start wide enough to find direction; tighten later if needed.
    """
    return {
        # Wheat engine
        "wheat_engine_day_max": trial.suggest_int("wheat_engine_day_max", 18, 22),
        "wheat_buffer_add": trial.suggest_int("wheat_buffer_add", 1, 3),
        "wheat_min_tiles": trial.suggest_int("wheat_min_tiles", 5, 7),
        "wheat_no_mouth_tiles": trial.suggest_int("wheat_no_mouth_tiles", 3, 5),
        "wheat_filler_day_max": trial.suggest_int("wheat_filler_day_max", 16, 24),
        "late_wheat_seed_buffer_day_min": trial.suggest_int("late_wheat_seed_buffer_day_min", 14, 20),
        "late_wheat_seed_buffer": trial.suggest_int("late_wheat_seed_buffer", 0, 4),

        # Herd ramp / cash gates
        "cow_day_max": trial.suggest_int("cow_day_max", 18, 22),
        "cow_milk_px_min": trial.suggest_int("cow_milk_px_min", 60, 95),
        "cow_floor_day_max": trial.suggest_int("cow_floor_day_max", 18, 22),
        "cow_floor": trial.suggest_int("cow_floor", 1, 3),
        "cow_expand_cap": trial.suggest_int("cow_expand_cap", 8, 12),

        "sheep_day_max": trial.suggest_int("sheep_day_max", 18, 22),
        "sheep_wool_px_min": trial.suggest_int("sheep_wool_px_min", 60, 95),
        "sheep_floor_day_max": trial.suggest_int("sheep_floor_day_max", 18, 22),
        "sheep_floor": trial.suggest_int("sheep_floor", 1, 3),
        "sheep_expand_cap": trial.suggest_int("sheep_expand_cap", 2, 6),

        # Land timing / guardrails
        "land_day_min": trial.suggest_int("land_day_min", 4, 8),
        "land_day_max": trial.suggest_int("land_day_max", 20, 26),
        "max_quads_for_land": 3,  # keep fixed to avoid massive structural changes
        "land2_day_min": trial.suggest_int("land2_day_min", 9, 13),
        "land2_money_min": trial.suggest_int("land2_money_min", 3000, 6000),
        "land2_empty_max": trial.suggest_int("land2_empty_max", 3, 6),
        "land2_strawberry_min": trial.suggest_int("land2_strawberry_min", 12, 24),

        # Sell-hold heuristic
        "sell_hold_price_factor": trial.suggest_float("sell_hold_price_factor", 0.70, 0.90),
        "sell_hold_days_left_min": 7,  # keep fixed for stability

        # Animal buy caps / cash floors
        "animal_buy_day_max": trial.suggest_int("animal_buy_day_max", 18, 22),
        "animal_buy_day_min": 3,
        "mouth_cap_1q": 6,
        "mouth_cap_2qplus": trial.suggest_int("mouth_cap_2qplus", 12, 16),
        "animal_cash_floor_2qplus": trial.suggest_int("animal_cash_floor_2qplus", 200, 800),
        "animal_cash_floor_1q": 1200,

        # Melon filler
        "melon_leftover_min": trial.suggest_int("melon_leftover_min", 6, 10),
        "melon_n_quads_min": 3,
        "melon_day_max": trial.suggest_int("melon_day_max", 14, 18),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--trials", type=int, default=200)
    p.add_argument("--seedCount", type=int, default=30)
    p.add_argument("--episodeSteps", type=int, default=720)
    p.add_argument("--studyName", type=str, default="kaggriculture_param_tune")
    p.add_argument("--nStartupTrials", type=int, default=10)
    args = p.parse_args()

    seeds = TUNE_SEEDS_30[: args.seedCount]

    def objective(trial: optuna.trial.Trial) -> float:
        params = _suggest_params(trial)
        _write_params(params)

        # Quick regression guards first: if we violate floors/empty constraints,
        # prune immediately before spending time on the full mean objective.
        for seed, floor in REG_GUARD_REWARD.items():
            env, us, _starter = run_vs_starter_env(seed, episode_steps=args.episodeSteps)
            if us < floor:
                raise TrialPruned()

            if seed in REG_GUARD_EMPTY_SEEDS:
                d16 = dawn_step(16)
                quads = len(env.steps[d16][0]["observation"]["farms"][0]["unlocked_quadrants"])
                if quads >= 3 and berry_shop_open(env, d16):
                    empty16 = empty_at_step(env, d16)
                    if empty16 > 24:
                        raise TrialPruned()

        # Sequential seed evaluation with pruning.
        total = 0
        for i, seed in enumerate(seeds):
            us, _starter = run_vs_starter(seed, episode_steps=args.episodeSteps)
            total += us
            mean_so_far = total / (i + 1)
            trial.report(mean_so_far, step=i)
            if trial.should_prune():
                raise TrialPruned()
        return total / len(seeds)

    storage = f"sqlite:///{DB_PATH}"
    study = optuna.create_study(
        direction="maximize",
        study_name=args.studyName,
        storage=storage,
        load_if_exists=True,
        sampler=optuna.samplers.TPESampler(seed=0),
        pruner=optuna.pruners.MedianPruner(
            n_startup_trials=args.nStartupTrials,
            n_warmup_steps=5,
        ),
    )

    # Enqueue a known-good starting point so we always have at least one
    # completed trial when regression guards are strict.
    # Enqueue a known-good starting point so we always have at least one
    # completed trial when regression guards are strict.
    try:
        import sys

        # Ensure `main.py` is importable when running `python tune/optimize.py`.
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        import main as kaggriculture_main

        baseline = kaggriculture_main.DEFAULT_PARAMS
        trial_keys = {
            # wheat engine
            "wheat_engine_day_max",
            "wheat_buffer_add",
            "wheat_min_tiles",
            "wheat_no_mouth_tiles",
            "wheat_filler_day_max",
            "late_wheat_seed_buffer_day_min",
            "late_wheat_seed_buffer",
            # herd ramp / cash gates
            "cow_day_max",
            "cow_milk_px_min",
            "cow_floor_day_max",
            "cow_floor",
            "cow_expand_cap",
            "sheep_day_max",
            "sheep_wool_px_min",
            "sheep_floor_day_max",
            "sheep_floor",
            "sheep_expand_cap",
            # land timing / guardrails
            "land_day_min",
            "land_day_max",
            "land2_day_min",
            "land2_money_min",
            "land2_empty_max",
            "land2_strawberry_min",
            # sell-hold heuristic
            "sell_hold_price_factor",
            # animal buy caps / cash floors
            "animal_buy_day_max",
            "mouth_cap_2qplus",
            "animal_cash_floor_2qplus",
            # melon filler
            "melon_leftover_min",
            "melon_day_max",
        }
        baseline_trial = {k: baseline[k] for k in trial_keys if k in baseline}
        if len(baseline_trial) == len(trial_keys):
            study.enqueue_trial(baseline_trial)
    except Exception:
        pass

    study.optimize(objective, n_trials=args.trials, show_progress_bar=True)

    complete = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
    if not complete:
        print("No completed trials (all pruned by regression guards). Nothing to write.")
        return

    best_params = study.best_params
    _write_params(best_params)
    BEST_PATH.write_text(json.dumps(best_params, indent=2, sort_keys=True), encoding="utf-8")

    print("best_mean", study.best_value)
    print("best_params", best_params)


if __name__ == "__main__":
    main()

