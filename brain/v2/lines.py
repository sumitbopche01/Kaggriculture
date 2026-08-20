"""brain/v2/lines.py — crop_line + herd_line locks (target agent design).

crop_line: OPEN | STRAWBERRY | TOMATO | FEED
herd_line: PETS | SCALE

Locks once from the first real lock shop. Pet café / yarn never lock.
No day-8 FEED timeout — stay OPEN until a lock shop appears.

Same-day ice cream + pizza → STRAWBERRY (berry at or before milk).
Pizza before any berry family → TOMATO + SCALE.
Bakery before berry/pizza → FEED + PETS.

Slice 1: ice cream / smoothie openers use PETS (SCALE-on-berry is a
hypothesis; enable with scale_berry_opener=True).
"""

from __future__ import annotations

from typing import Any, Literal

CropLine = Literal["OPEN", "STRAWBERRY", "TOMATO", "FEED"]
HerdLine = Literal["PETS", "SCALE"]

BERRY_LOCK = frozenset(
    {"ICE_CREAM_SHOP", "SMOOTHIE_SHOP", "BRUNCH_SPOT", "FARMERS_MARKET"}
)
PIZZA_LOCK = frozenset({"PIZZA_SHOP"})
FEED_LOCK = frozenset({"BAKERY"})
SCALE_BERRY_SHOPS = frozenset({"ICE_CREAM_SHOP", "SMOOTHIE_SHOP"})
NON_LOCK_SHOPS = frozenset({"PET_CAFE", "YARN_STORE"})


def _herd_for_berry_shop(shop: str, *, scale_berry_opener: bool) -> HerdLine:
    if shop in SCALE_BERRY_SHOPS and scale_berry_opener:
        return "SCALE"
    return "PETS"


def resolve_lock(
    shops: list[str] | tuple[str, ...] | None,
    *,
    first_berry_day: int | None,
    first_milk_day: int | None,
    first_pizza_day: int | None = None,
    first_bakery_day: int | None = None,
    scale_berry_opener: bool = False,
) -> tuple[CropLine, HerdLine, str | None]:
    """Pick lock pair from unlock days + current shops.

    Returns (crop_line, herd_line, lock_shop_or_None).
    """
    shops = list(shops or [])
    present = set(shops)

    berry_shops = [s for s in shops if s in BERRY_LOCK]
    pizza_here = bool(present & PIZZA_LOCK)
    bakery_here = bool(present & FEED_LOCK)

    # Nothing lockable yet.
    if not berry_shops and not pizza_here and not bakery_here:
        return "OPEN", "PETS", None

    # Berry at or before first milk/pizza → STRAWBERRY.
    berry_first = False
    if first_berry_day is not None:
        milk_ref = first_milk_day
        if first_pizza_day is not None:
            milk_ref = (
                first_pizza_day
                if milk_ref is None
                else min(int(milk_ref), int(first_pizza_day))
            )
        if milk_ref is None or int(first_berry_day) <= int(milk_ref):
            berry_first = True

    if berry_first and berry_shops:
        # Prefer ice cream / smoothie in the list for herd rule; else brunch/FM.
        opener = next((s for s in berry_shops if s in SCALE_BERRY_SHOPS), berry_shops[0])
        return (
            "STRAWBERRY",
            _herd_for_berry_shop(opener, scale_berry_opener=scale_berry_opener),
            opener,
        )

    # Pizza before berries.
    if pizza_here and (
        first_berry_day is None
        or (
            first_pizza_day is not None
            and int(first_pizza_day) < int(first_berry_day)
        )
        or (first_milk_day is not None and first_berry_day is not None
            and int(first_milk_day) < int(first_berry_day) and "PIZZA_SHOP" in present)
    ):
        return "TOMATO", "SCALE", "PIZZA_SHOP"

    if pizza_here and first_berry_day is None:
        return "TOMATO", "SCALE", "PIZZA_SHOP"

    if bakery_here and not berry_shops and not pizza_here:
        return "FEED", "PETS", "BAKERY"

    # Berry shops present but milk/pizza was earlier — still no berry_first.
    # Stay with tomato if pizza exists; else strawberry if only berries.
    if pizza_here:
        return "TOMATO", "SCALE", "PIZZA_SHOP"
    if berry_shops:
        opener = next((s for s in berry_shops if s in SCALE_BERRY_SHOPS), berry_shops[0])
        return (
            "STRAWBERRY",
            _herd_for_berry_shop(opener, scale_berry_opener=scale_berry_opener),
            opener,
        )
    if bakery_here:
        return "FEED", "PETS", "BAKERY"
    return "OPEN", "PETS", None


def apply_lock(
    state: dict[str, Any],
    shops: list[str] | tuple[str, ...] | None,
    *,
    first_berry_day: int | None = None,
    first_milk_day: int | None = None,
    first_pizza_day: int | None = None,
    first_bakery_day: int | None = None,
    scale_berry_opener: bool = False,
) -> dict[str, Any]:
    """Stamp crop_line / herd_line.

    Hard lock: TOMATO and STRAWBERRY never flip.
    Soft lock: FEED (bakery-first) may upgrade once:
    - berry shop → STRAWBERRY + PETS (late smoothie after bakery)
    - pizza → TOMATO + SCALE
    Never SCALE from a late dual shop on a berry upgrade.
    """
    crop = state.get("crop_line") or "OPEN"
    herd = state.get("herd_line") or "PETS"
    if herd not in ("PETS", "SCALE"):
        herd = "PETS"

    if crop in ("STRAWBERRY", "TOMATO"):
        state["crop_line"] = crop
        state["herd_line"] = herd
        return state

    crop_l, herd_l, shop = resolve_lock(
        shops,
        first_berry_day=first_berry_day,
        first_milk_day=first_milk_day,
        first_pizza_day=first_pizza_day,
        first_bakery_day=first_bakery_day,
        scale_berry_opener=scale_berry_opener,
    )

    # FEED is provisional until berry or pizza appears.
    if crop == "FEED":
        if crop_l == "STRAWBERRY":
            state["crop_line"] = "STRAWBERRY"
            state["herd_line"] = "PETS"
            if shop:
                state["lock_shop"] = shop
        elif crop_l == "TOMATO":
            state["crop_line"] = "TOMATO"
            state["herd_line"] = "SCALE"
            if shop:
                state["lock_shop"] = shop
        else:
            state["crop_line"] = "FEED"
            state["herd_line"] = "PETS"
        return state

    state["crop_line"] = crop_l
    state["herd_line"] = herd_l
    if shop:
        state["lock_shop"] = shop
    return state


def crop_line_of(s: dict[str, Any]) -> CropLine:
    v = s.get("crop_line") or "OPEN"
    if v in ("OPEN", "STRAWBERRY", "TOMATO", "FEED"):
        return v  # type: ignore[return-value]
    return "OPEN"


def herd_line_of(s: dict[str, Any]) -> HerdLine:
    v = s.get("herd_line") or "PETS"
    if v in ("PETS", "SCALE"):
        return v  # type: ignore[return-value]
    return "PETS"


def is_open(s: dict[str, Any]) -> bool:
    return crop_line_of(s) == "OPEN"


def lock_pair_for_shop(
    shop: str, *, scale_berry_opener: bool = False
) -> tuple[CropLine, HerdLine] | None:
    """Single-shop lookup (tests / debug). Prefer resolve_lock in agent."""
    if shop in NON_LOCK_SHOPS:
        return None
    if shop in PIZZA_LOCK:
        return "TOMATO", "SCALE"
    if shop in FEED_LOCK:
        return "FEED", "PETS"
    if shop in BERRY_LOCK:
        return "STRAWBERRY", _herd_for_berry_shop(
            shop, scale_berry_opener=scale_berry_opener
        )
    return None
