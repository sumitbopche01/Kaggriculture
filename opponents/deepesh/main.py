"""Kaggriculture — SELF-CONTAINED Kaggle submission (single file, stdlib only).

This is the artifact you paste into a Kaggle notebook / submit. It defines a
top-level `agent(obs)` (Kaggle also sometimes passes `config`, which we accept
and ignore). It has ZERO imports beyond the standard library and no dependency
on the rest of this repo, so it runs unchanged inside the Kaggle environment.

It is a flattened copy of `src/kaggriculture_agent/real/{protocol,brain,
submission}.py`. A parity test (tests/test_submission_parity.py) asserts this
file behaves identically to the package version, so the two never drift.

Strategy: market first (keep seeds stocked, sell the shed), then walk to the
nearest high-priority tile — harvest-ready > needs-water > weed > plantable —
and act on it. One farmer command per turn, exactly as the env expects.
"""

from __future__ import annotations

# ============================ contract constants ============================ #
NORTH, SOUTH, EAST, WEST = "NORTH", "SOUTH", "EAST", "WEST"
MOVES = (NORTH, SOUTH, EAST, WEST)
WATER, HARVEST, DIG, PLANT, PASS = "WATER", "HARVEST", "DIG", "PLANT", "PASS"
KIND_PLANT, KIND_WEED = "PLANT", "WEED"
BUY_SEED, SELL = "BUY_SEED", "SELL"

MATURE_AGE = 2  # confirmed: harvest when obs["day"] - planted_day >= 2


# ================================ helpers =================================== #
def build_action(farmer_cmd, market=None):
    return {"farmer": list(farmer_cmd), "hands": [], "market": market or []}


def step_toward(fx, fy, tx, ty):
    # x = column (EAST = +x); y = row (SOUTH = +y). Resolve x first, then y.
    if fx < tx:
        return EAST
    if fx > tx:
        return WEST
    if fy < ty:
        return SOUTH
    if fy > ty:
        return NORTH
    return PASS


def _nearest(fx, fy, cells):
    return min(cells, key=lambda c: abs(c[0] - fx) + abs(c[1] - fy))


def _as_int_qty(amount):
    return int(amount)


# ============================== the policy ================================== #
class FarmBrain:
    def __init__(self, crops=None, seed_restock_threshold=4, seed_restock_qty=4):
        self.crops = crops or ["WHEAT"]
        self.seed_restock_threshold = seed_restock_threshold
        self.seed_restock_qty = seed_restock_qty

    def decide(self, obs):
        farm = obs["farms"][obs["player"]]
        private = obs["private"]
        fx, fy = (int(v) for v in farm["farmer"])
        day = obs["day"]

        market = self._plan_market(farm, private)
        target, farmer_cmd = self._plan_farmer(farm, private, day, fx, fy)

        if target is None:
            return build_action([PASS], market)
        tx, ty = target
        if (fx, fy) == (tx, ty):
            return build_action(farmer_cmd, market)
        return build_action([step_toward(fx, fy, tx, ty)], market)

    def _plan_market(self, farm, private):
        ops = []
        seeds, shed = private["seeds"], private["shed"]
        for crop in self.crops:
            if seeds.get(crop, 0) < self.seed_restock_threshold:
                ops.append([BUY_SEED, crop, self.seed_restock_qty])
        for crop, amount in shed.items():
            qty = _as_int_qty(amount)
            if qty > 0:
                ops.append([SELL, crop, qty])
        return ops

    def _plan_farmer(self, farm, private, day, fx, fy):
        tiles = farm["tiles"]
        seeds = private["seeds"]
        size = len(tiles)

        harvest, water, weed, plant = [], [], [], []
        for y in range(size):
            for x in range(size):
                tile = tiles[y][x]
                if tile is None:
                    plant.append((x, y))
                elif isinstance(tile, dict):
                    kind = tile.get("kind")
                    if kind == KIND_PLANT:
                        if day - tile["planted_day"] >= MATURE_AGE:
                            harvest.append((x, y))
                        elif not tile.get("watered_today", False):
                            water.append((x, y))
                    elif kind == KIND_WEED:
                        weed.append((x, y))

        have_seed = any(seeds.get(c, 0) > 0 for c in self.crops)
        if harvest:
            return _nearest(fx, fy, harvest), [HARVEST]
        if water:
            return _nearest(fx, fy, water), [WATER]
        if weed:
            return _nearest(fx, fy, weed), [DIG]
        if plant and have_seed:
            crop = next(c for c in self.crops if seeds.get(c, 0) > 0)
            return _nearest(fx, fy, plant), [PLANT, crop]
        return None, [PASS]


# ========================= Kaggle entrypoint =============================== #
_BRAIN = FarmBrain()


def agent(obs, config=None):
    return _BRAIN.decide(obs)
