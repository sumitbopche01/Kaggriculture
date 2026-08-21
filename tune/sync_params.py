"""Rewrite tune/params.json from main.DEFAULT_PARAMS (+ current overlay).

Keeps all 175 knobs visible for Optuna/hand edits. Run after adding DEFAULT_PARAMS keys.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main  # noqa: E402

OUT = ROOT / "tune" / "params.json"


def main_sync() -> None:
    # PARAMS already merges DEFAULT_PARAMS with existing json overlay.
    OUT.write_text(
        json.dumps(main.PARAMS, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(main.PARAMS)} keys -> {OUT}")


if __name__ == "__main__":
    main_sync()
