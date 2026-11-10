"""HG-04 / HG-03: copias paralelas del historico (2026-10-22).

Copias (todas en copia aislada fuera del repo; data/ no se modifica):
  C       control: build_hrv_core.py sin cambios
  H3      solo HG-03: RMSSD, Poincare, cola y ventanas del detector usan solo
          pares originalmente consecutivos (rr_pair_diffs + original_idx_eff,
          implementacion ya presente en build_hrv_core.py). Detector y Calidad vigentes.
  H3S90   HG-03 + inicio fijo 90 s (tramo [90, t_end_eff]) en ambas rutas
  H3S120  HG-03 + inicio fijo 120 s
  H3S90T375  HG-03 + inicio fijo 90 s + grabacion cortada a 375 s (simula registros
          de 375 s: se conservan los latidos completos antes de 375 s; tail-trim deja
          t_end_eff = 360 s y tramo [90, 360]). Registros mas cortos no cambian.
  H3S90T375NL  igual que H3S90T375 pero sin la regla LAT_NAN -> FLAG_mecanico
          (build_hrv_core.py:470-475). Solo para medir el peso de esa regla cuando el
          detector ya no decide el tramo; no es una propuesta de contrato.
En H3S90/H3S120 el detector se sigue calculando (Tiempo_Estabilizacion y la regla de
Calidad vigentes) pero ya no decide el tramo.

Uso: python run_parallel.py extract | <copia> core|final | all
Directorio de trabajo: $HG04_REPLAY_WORK o $HOME/hg04_replay_work
"""
from __future__ import annotations
import os, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
WORK = Path(os.environ.get("HG04_REPLAY_WORK", Path.home() / "hg04_replay_work")).resolve()
RR = WORK / "rr_src"
DATA_FILES = ["ENDURANCE_HRV_master_CORE.csv", "ENDURANCE_HRV_master_BETA_AUDIT.csv",
              "ENDURANCE_HRV_master_CORE_manifest.json", "ENDURANCE_HRV_sleep.csv",
              "ENDURANCE_HRV_sessions_day.csv", "ENDURANCE_HRV_ssm_shadow.csv",
              "ENDURANCE_HRV_ssm_shadow_metadata.json"]

HELPERS = '''

def _rmssd_pairs_ms(rr_ms, idx) -> float:
    """HG-03 replay: RMSSD (ms) solo con pares originalmente consecutivos."""
    d = rr_pair_diffs(rr_ms, idx)
    if d.size == 0:
        return np.nan
    return float(np.sqrt(np.mean(d * d)))


def _poincare_pairs(rr_ms, idx):
    """HG-03 replay: SD1 con pares consecutivos; SD2 con la varianza de todos los RR."""
    rr = np.asarray(rr_ms, dtype=float)
    diff = rr_pair_diffs(rr, idx)
    if rr.size < 10 or diff.size < 2:
        return np.nan, np.nan, np.nan
    sd1 = float(np.std(diff, ddof=0) / np.sqrt(2.0))
    sd2_sq = 2.0 * float(np.var(rr, ddof=0)) - (sd1 ** 2)
    sd2 = float(np.sqrt(sd2_sq)) if sd2_sq > 0 else 0.0
    ratio = float(np.round(sd1 / sd2, 3)) if sd2 > 0 else np.nan
    return float(np.round(sd1, 2)), float(np.round(sd2, 2)), ratio
'''

H3 = [
    # helpers tras rr_pair_diffs
    ("    adjacent = (steps == 1) & np.isfinite(rr[:-1]) & np.isfinite(rr[1:])\n    return np.diff(rr)[adjacent]\n",
     "    adjacent = (steps == 1) & np.isfinite(rr[:-1]) & np.isfinite(rr[1:])\n    return np.diff(rr)[adjacent]\n" + HELPERS),
    # contexto: indices originales en ambas rutas
    ("    t_eff = ctx.t_eff\n    t_end_eff = ctx.t_end_eff\n\n    # Latencia (ventanas",
     "    t_eff = ctx.t_eff\n    t_end_eff = ctx.t_end_eff\n    idx_eff = ctx.original_idx_eff\n\n    # Latencia (ventanas"),
    ("    t_eff = ctx.t_eff\n    t_end_eff = ctx.t_end_eff\n\n    # Latencia simplificada",
     "    t_eff = ctx.t_eff\n    t_end_eff = ctx.t_end_eff\n    idx_eff = ctx.original_idx_eff\n\n    # Latencia simplificada"),
    # ventanas del detector
    ("        if rr_w.size - 1 >= 20:\n            rmssd_w[k] = rmssd_ms(rr_w)\n",
     "        if rr_w.size - 1 >= 20:\n            rmssd_w[k] = _rmssd_pairs_ms(rr_eff[m], idx_eff[m])\n"),
    # ruta completa: tramo
    ("    RMSSD = rmssd_ms(rr_tramo) if rr_tramo.size >= 2 else np.nan\n    lnRMSSD = float(np.log(RMSSD)) if (not np.isnan(RMSSD) and RMSSD > 0) else np.nan\n    SI_baevsky",
     "    RMSSD = _rmssd_pairs_ms(rr_tramo_ms, idx_eff[tramo]) if rr_tramo.size >= 2 else np.nan\n    lnRMSSD = float(np.log(RMSSD)) if (not np.isnan(RMSSD) and RMSSD > 0) else np.nan\n    SI_baevsky"),
    ("    SD1, SD2, SD1_SD2_ratio = poincare_sd(rr_tramo_ms)\n",
     "    SD1, SD2, SD1_SD2_ratio = _poincare_pairs(rr_tramo_ms, idx_eff[tramo])\n"),
    # ruta completa: cola
    ("    n_pairs_tail = int(rr_tail.size - 1)\n    RMSSD_last2 = rmssd_ms(rr_tail) if rr_tail.size >= 2 else np.nan\n    CV_120",
     "    n_pairs_tail = int(rr_pair_diffs(rr_eff[tail], idx_eff[tail]).size)\n    RMSSD_last2 = _rmssd_pairs_ms(rr_eff[tail], idx_eff[tail]) if rr_tail.size >= 2 else np.nan\n    CV_120"),
    # ruta de rescate: tramo
    ("    RMSSD = rmssd_ms(rr_tramo) if rr_tramo.size >= 2 else np.nan\n    lnRMSSD = float(np.log(RMSSD)) if (not np.isnan(RMSSD) and RMSSD > 0) else np.nan\n\n    # Cola",
     "    RMSSD = _rmssd_pairs_ms(rr_eff[tramo], idx_eff[tramo]) if rr_tramo.size >= 2 else np.nan\n    lnRMSSD = float(np.log(RMSSD)) if (not np.isnan(RMSSD) and RMSSD > 0) else np.nan\n\n    # Cola"),
    # ruta de rescate: cola
    ("    n_pairs_tail = int(rr_tail.size - 1)\n    RMSSD_last2 = rmssd_ms(rr_tail) if rr_tail.size >= 2 else np.nan\n\n    # Calidad simplificada",
     "    n_pairs_tail = int(rr_pair_diffs(rr_eff[tail], idx_eff[tail]).size)\n    RMSSD_last2 = _rmssd_pairs_ms(rr_eff[tail], idx_eff[tail]) if rr_tail.size >= 2 else np.nan\n\n    # Calidad simplificada"),
]

def start(s: float):
    return [
        ("    t_start_eff = 45.0 if np.isnan(lat) else max(lat, 45.0)\n",
         f"    t_start_eff = {s:.1f}  # HG-04 replay: inicio fijo, fin = t_end_eff\n"),
        ("    # Latencia simplificada (usar 45s como fallback)\n    t_start_eff = 45.0\n",
         f"    # HG-04 replay: inicio fijo\n    t_start_eff = {s:.1f}\n"),
    ]

def trunc(s: float):
    return [
        ("    original_idx = original_idx[valid_mask]\n\n    N_total = int(rr_ms.size)\n",
         f"    original_idx = original_idx[valid_mask]\n\n    # HG-04 replay: grabacion cortada a {s:.0f} s (latidos completos antes de {s:.0f} s)\n"
         f"    _keep_dur = (np.cumsum(rr_ms) / 1000.0) <= {s:.1f}\n"
         "    rr_ms = rr_ms[_keep_dur]\n    offline = offline[_keep_dur]\n    original_idx = original_idx[_keep_dur]\n\n    N_total = int(rr_ms.size)\n"),
    ]

NO_LAT_RULE = [
    ('        if (not np.isnan(lat)) and artifact_pct <= C["ARTIFACT_OK_MAX"] and 60.0 <= Lat_eff <= 600.0 and HRV_Stability == "OK":\n'
     '            Calidad = "OK"\n        else:\n            Calidad = "FLAG_mecánico"\n        if np.isnan(lat):\n            Calidad = "FLAG_mecánico"\n',
     '        # HG-04 replay: sin la regla LAT_NAN -> FLAG (el detector no decide el tramo)\n'
     '        if artifact_pct <= C["ARTIFACT_OK_MAX"] and HRV_Stability == "OK":\n'
     '            Calidad = "OK"\n        else:\n            Calidad = "FLAG_mecánico"\n'),
]

COPIES = {"C": [], "H3": H3, "H3S90": H3 + start(90), "H3S120": H3 + start(120),
          "H3S90T375": H3 + start(90) + trunc(375),
          "H3S90T375NL": H3 + start(90) + trunc(375) + NO_LAT_RULE}

def patched(name: str, base: Path) -> Path:
    src = (ROOT / "build_hrv_core.py").read_text(encoding="utf-8")
    nl = "\r\n" if "\r\n" in src else "\n"
    src = src.replace("\r\n", "\n")
    for a, b in COPIES[name]:
        n = src.count(a)
        if n != 1:
            raise SystemExit(f"{name}: ancla encontrada {n} veces: {a[:80]!r}")
        src = src.replace(a, b)
    out = base / f"build_hrv_core_{name}.py"
    out.write_text(src.replace("\n", nl), encoding="utf-8")
    return out

def extract():
    env = dict(os.environ, HG04_REPLAY_WORK=str(WORK))
    p = subprocess.run([sys.executable, str(Path(__file__).with_name("extract_rr.py"))], env=env, capture_output=True, text=True)
    print(p.stdout.strip(), p.stderr[-500:])
    if p.returncode: raise SystemExit(1)
    # find_rr_files() no reconoce "..._RR (1).CSV": se renombra solo en la copia de trabajo
    for f in RR.glob("* (1).*"):
        f.rename(f.with_name(f.name.replace(" (1)", "")))
    print("renombrados; restantes con '(1)':", len(list(RR.glob("* (1).*"))))

def run(name: str, step: str):
    base = WORK / name
    if step == "core":
        if base.exists(): shutil.rmtree(base)
        (base / "data").mkdir(parents=True)
        for f in DATA_FILES:
            if (ROOT / "data" / f).exists(): shutil.copy2(ROOT / "data" / f, base / "data" / f)
        script = ROOT / "build_hrv_core.py" if name == "C" else patched(name, base)
        cmd = [sys.executable, str(script), "--data-dir", str(base / "data"), "--rr-dir", str(RR)]
    else:
        cmd = [sys.executable, str(ROOT / "build_hrv_final_dashboard.py"), "--data-dir", str(base / "data")]
    env = dict(os.environ, HRV_DATA_DIR=str(base / "data"), HRV_DISABLE_BACKUP="1", HRV_QUIET="1", PYTHONPATH=str(ROOT))
    p = subprocess.run(cmd, cwd=base, env=env, capture_output=True, text=True)
    (base / f"{step}.log").write_text(p.stdout + "\n--- stderr ---\n" + p.stderr)
    ok = p.returncode == 0
    print(name, step, "rc", p.returncode, "" if ok else p.stderr[-800:])
    if not ok: raise SystemExit(1)

if __name__ == "__main__":
    a = sys.argv[1:]
    if a[0] == "extract": extract()
    elif a[0] == "patchcheck":
        for n in COPIES:
            d = WORK / "_patchcheck"; d.mkdir(parents=True, exist_ok=True)
            p = patched(n, d); import py_compile; py_compile.compile(str(p), doraise=True); print(n, "parche ok")
    else: run(a[0], a[1])
