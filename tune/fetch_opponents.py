"""Fetch public Kaggriculture agents into opponents/.

Pulls Kaggle kernels that embed main.py (%%writefile / %%agentfile / b85
payloads) and the deepeshumrao GitHub submission.
Does not download private competition submissions (API cannot).

Usage:
  .venv/bin/python -m tune.fetch_opponents
"""

from __future__ import annotations

import ast
import base64
import json
import os
import shutil
import subprocess
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPP = ROOT / "opponents"
DOWNLOAD = OPP / "_download"
KAGGLE = ROOT / ".venv" / "bin" / "kaggle"

# (kernel_ref, label, extract_mode)
# extract_mode: writefile | agentfile | b85_payload
KERNELS = [
    ("premaananda108/kaggriculture-ecobot-v2", "ecobot_v2", "writefile"),
    (
        "ameythakur20/kaggriculture-deterministic-farm-planning-agent",
        "deterministic",
        "writefile",
    ),
    (
        "pilkwang/kaggriculture-structured-economic-policy",
        "structured",
        "agentfile",
    ),
    (
        "prvsiyan/kaggriculture-frontier-the-soil-remembers-rain",
        "frontier_soil",
        "b85_payload",
    ),
]


def _env() -> dict[str, str]:
    env = os.environ.copy()
    for k in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "http_proxy",
        "https_proxy",
        "ALL_PROXY",
        "all_proxy",
    ):
        env.pop(k, None)
    return env


def _code_cells(nb_path: Path) -> list[str]:
    nb = json.loads(nb_path.read_text())
    out: list[str] = []
    for cell in nb.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        out.append("".join(cell.get("source") or []))
    return out


def _write_main(out_dir: Path, text: str) -> None:
    if "def agent" not in text:
        raise RuntimeError(f"extracted source missing def agent ({out_dir})")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "main.py").write_text(text)


def _extract_writefile(nb_path: Path, out_dir: Path) -> None:
    chunks: list[str] = []
    for src in _code_cells(nb_path):
        if src.lstrip().startswith("%%writefile main.py"):
            body = src.split("\n", 1)[1] if "\n" in src else ""
            chunks.append(body)
    if not chunks:
        raise RuntimeError(f"no %%writefile main.py in {nb_path}")
    _write_main(out_dir, chunks[-1])


def _extract_agentfile(nb_path: Path, out_dir: Path) -> None:
    chunks: list[str] = []
    for src in _code_cells(nb_path):
        stripped = src.lstrip()
        if stripped.startswith("%%agentfile"):
            body = src.split("\n", 1)[1] if "\n" in src else ""
            chunks.append(body)
    if not chunks:
        raise RuntimeError(f"no %%agentfile in {nb_path}")
    _write_main(out_dir, chunks[-1])


def _parse_rhs_after(src: str, marker: str):
    i = src.find(marker)
    if i < 0:
        raise RuntimeError(f"missing {marker}")
    eq = src.find("=", i + len(marker))
    buf = ""
    node = None
    for line in src[eq + 1 :].splitlines(True):
        buf += line
        try:
            node = ast.parse("x = " + buf)
            break
        except SyntaxError:
            continue
    if node is None:
        raise RuntimeError(f"could not parse assignment for {marker}")
    return node.body[0].value


def _string_parts(val) -> list[str]:
    if isinstance(val, ast.Call) and getattr(val.func, "attr", None) == "join":
        arg = val.args[0]
        return [ast.literal_eval(e) for e in arg.elts]
    if isinstance(val, (ast.List, ast.Tuple)):
        return [ast.literal_eval(e) for e in val.elts]
    if isinstance(val, ast.Constant) and isinstance(val.value, str):
        return [val.value]
    raise RuntimeError(f"unsupported payload AST: {type(val)}")


def _extract_b85_payload(nb_path: Path, out_dir: Path) -> None:
    """Decode AGENT_PAYLOAD = '...' via zlib+base85 (Frontier Soil style)."""
    src = "\n".join(_code_cells(nb_path))
    if "AGENT_PAYLOAD" not in src:
        raise RuntimeError(f"no AGENT_PAYLOAD in {nb_path}")
    parts = _string_parts(_parse_rhs_after(src, "AGENT_PAYLOAD"))
    blob = "".join(parts)
    text = zlib.decompress(base64.b85decode(blob)).decode()
    _write_main(out_dir, text)


EXTRACTORS = {
    "writefile": _extract_writefile,
    "agentfile": _extract_agentfile,
    "b85_payload": _extract_b85_payload,
}


def fetch_kernels() -> None:
    DOWNLOAD.mkdir(parents=True, exist_ok=True)
    for ref, label, mode in KERNELS:
        dest = DOWNLOAD / label
        if dest.exists():
            shutil.rmtree(dest)
        subprocess.run(
            [str(KAGGLE), "kernels", "pull", ref, "-p", str(dest)],
            cwd=ROOT,
            env=_env(),
            check=True,
        )
        nbs = list(dest.glob("*.ipynb"))
        if not nbs:
            raise RuntimeError(f"no notebook in {dest}")
        EXTRACTORS[mode](nbs[0], OPP / label)
        print(f"wrote {OPP / label / 'main.py'} ({mode})")


def fetch_deepesh() -> None:
    repo = DOWNLOAD / "deepesh"
    if repo.exists():
        shutil.rmtree(repo)
    subprocess.run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            "https://github.com/deepeshumrao/kaggriculture-agent.git",
            str(repo),
        ],
        check=True,
    )
    src = repo / "deliverables" / "kaggriculture_submission.py"
    out = OPP / "deepesh"
    out.mkdir(parents=True, exist_ok=True)
    (out / "main.py").write_text(src.read_text())
    print(f"wrote {out / 'main.py'}")


def main() -> None:
    if not KAGGLE.is_file():
        raise SystemExit(f"missing kaggle CLI at {KAGGLE}")
    fetch_kernels()
    fetch_deepesh()
    print("done")


if __name__ == "__main__":
    main()
