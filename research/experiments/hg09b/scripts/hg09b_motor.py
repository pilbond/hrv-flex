"""HG-09B: motor CORE de la geometría candidata (HG-03 + inicio 90 s + corte 375 s) en memoria.

Aplica al build_hrv_core.py del árbol de trabajo exactamente los parches de la copia
`H3S90T375` de research/experiments/hg04_replay/scripts/run_parallel.py y lo ejecuta en
memoria. No escribe ficheros. Expone `day_metrics(rr_path)` -> fila CORE (dict).
"""
from __future__ import annotations

import hashlib
import importlib.util
import sys
import types
from pathlib import Path

import pandas as pd

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
RUN_PARALLEL = ROOT / "research/experiments/hg04_replay/scripts/run_parallel.py"
CORE_SRC = ROOT / "build_hrv_core.py"
COPY = "H3S90T375"


def _load_run_parallel():
    spec = importlib.util.spec_from_file_location("hg04_run_parallel", RUN_PARALLEL)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


_MOD = None


def engine():
    global _MOD
    if _MOD is not None:
        return _MOD
    rp = _load_run_parallel()
    src = CORE_SRC.read_text(encoding="utf-8").replace("\r\n", "\n")
    for a, b in rp.COPIES[COPY]:
        n = src.count(a)
        if n != 1:
            raise SystemExit(f"ancla encontrada {n} veces: {a[:80]!r}")
        src = src.replace(a, b)
    mod = types.ModuleType("hg09b_core")
    mod.__file__ = str(CORE_SRC)
    sys.modules["hg09b_core"] = mod
    exec(compile(src, str(CORE_SRC), "exec"), mod.__dict__)
    _MOD = mod
    return mod


def day_metrics(rr_path: Path, history: pd.DataFrame | None = None) -> dict:
    mod = engine()
    hist = history if history is not None else pd.DataFrame(columns=mod.COLS_CORE)
    row, _ = mod.compute_day_from_rr(Path(rr_path), hist, mod.CONSTANTS)
    return row


def fingerprints() -> dict:
    sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
    return {"build_hrv_core.py": sha(CORE_SRC), "run_parallel.py": sha(RUN_PARALLEL), "copia": COPY}
