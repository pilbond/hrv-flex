"""HG-04 replay, paso 2: ejecutar un brazo en copia aislada (fuera del repo).

Brazos:
  C   control: build_hrv_core.py sin cambios (debe reproducir CORE/FINAL actuales)
  H3  HG-03 candidato: RMSSD/Poincare/cola/ventanas del detector solo con pares
      originalmente consecutivos por indice de fila fuente (no por distancia temporal)
  H4  HG-04 candidato: recorte fijo 180 s, ventana [180,360], cola [240,360],
      Calidad sin condicion de latencia (opcion a); ambas rutas (completa y rescate)
  H34 ambos
  H4e inicio fijo 180 s, fin al final del registro; cola y Calidad vigentes
  E0/E60/E90/E120 y H3E*: inicio fijo temprano, fin al final; con/sin HG-03
  E180/H3E180: sensibilidad tardia con el mismo final variable
  H4w solo ventana HG-04 (Calidad con la regla de latencia vigente)
Nunca escribe en data/. Uso: python run_arm.py <arm> prepare|core|final|collect
"""
from __future__ import annotations
import hashlib, json, os, shutil, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]
EXP = ROOT / "research/experiments/hg04_replay"
WORK = Path(os.environ.get("HG04_REPLAY_WORK", Path.home() / "hg04_replay_work")).resolve()
DATA_FILES = ["ENDURANCE_HRV_master_CORE.csv", "ENDURANCE_HRV_master_BETA_AUDIT.csv",
              "ENDURANCE_HRV_master_CORE_manifest.json", "ENDURANCE_HRV_sleep.csv",
              "ENDURANCE_HRV_sessions_day.csv", "ENDURANCE_HRV_ssm_shadow.csv",
              "ENDURANCE_HRV_ssm_shadow_metadata.json"]
OUTPUTS = ["ENDURANCE_HRV_master_CORE.csv", "ENDURANCE_HRV_master_BETA_AUDIT.csv",
           "ENDURANCE_HRV_master_FINAL.csv", "ENDURANCE_HRV_master_DASHBOARD.csv"]

# ---- HG-03: helpers y llamadas (C sin NaN => comportamiento identico) -------------
H3 = [
 ("    d = np.diff(rr_s)\n    return float(np.sqrt(np.mean(d * d)) * 1000.0)\n",
  "    d = np.diff(rr_s)\n    d = d[~np.isnan(d)]\n    if d.size == 0:\n        return np.nan\n    return float(np.sqrt(np.mean(d * d)) * 1000.0)\n"),
 ("    rr = rr[~np.isnan(rr)]\n    if rr.size < 10:\n        return np.nan, np.nan, np.nan\n    diff = rr[1:] - rr[:-1]\n",
  "    diff = rr[1:] - rr[:-1]\n    diff = diff[~np.isnan(diff)]\n    rr = rr[~np.isnan(rr)]\n    if rr.size < 10 or diff.size < 9:\n        return np.nan, np.nan, np.nan\n"),
 ("def baevsky_stress_index(",
  "def _seg(rr, idx):\n    \"\"\"HG-03 shadow: NaN entre filas RR no consecutivas en el archivo fuente.\"\"\"\n"
  "    rr = np.asarray(rr, dtype=float); idx = np.asarray(idx, dtype=np.int64)\n"
  "    if rr.size < 2:\n        return rr\n"
  "    gap = np.diff(idx) != 1\n"
  "    out = np.insert(rr, np.nonzero(gap)[0] + 1, np.nan)\n    return out\n\n\ndef baevsky_stress_index("),
 ("    artifact_pct = ctx.artifact_pct\n    rr_eff = ctx.rr_eff\n    t_eff = ctx.t_eff\n    t_end_eff = ctx.t_end_eff\n\n    # Latencia (ventanas 60s, paso 30s)\n",
  "    artifact_pct = ctx.artifact_pct\n    rr_eff = ctx.rr_eff\n    t_eff = ctx.t_eff\n    idx_eff = ctx.original_idx_eff\n    t_end_eff = ctx.t_end_eff\n\n    # Latencia (ventanas 60s, paso 30s)\n"),
 ("        rr_w = rr_eff[m] / 1000.0\n        if rr_w.size - 1 >= 20:\n            rmssd_w[k] = rmssd_ms(rr_w)\n",
  "        rr_w = _seg(rr_eff[m], idx_eff[m]) / 1000.0\n        if np.sum(np.isfinite(np.diff(rr_w))) >= 20:\n            rmssd_w[k] = rmssd_ms(rr_w)\n"),
 ("    RMSSD = rmssd_ms(rr_tramo) if rr_tramo.size >= 2 else np.nan\n    lnRMSSD = float(np.log(RMSSD)) if (not np.isnan(RMSSD) and RMSSD > 0) else np.nan\n    SI_baevsky",
  "    RMSSD = rmssd_ms(_seg(rr_tramo_ms, idx_eff[tramo]) / 1000.0) if rr_tramo.size >= 2 else np.nan\n    lnRMSSD = float(np.log(RMSSD)) if (not np.isnan(RMSSD) and RMSSD > 0) else np.nan\n    SI_baevsky"),
 ("    SD1, SD2, SD1_SD2_ratio = poincare_sd(rr_tramo_ms)\n",
  "    SD1, SD2, SD1_SD2_ratio = poincare_sd(_seg(rr_tramo_ms, idx_eff[tramo]))\n"),
 ("    n_pairs_tail = int(rr_tail.size - 1)\n    RMSSD_last2 = rmssd_ms(rr_tail) if rr_tail.size >= 2 else np.nan\n    CV_120",
  "    _st = _seg(rr_eff[tail], idx_eff[tail]); n_pairs_tail = int(np.sum(np.isfinite(np.diff(_st)))) if _st.size > 1 else 0\n    RMSSD_last2 = rmssd_ms(_st / 1000.0) if rr_tail.size >= 2 else np.nan\n    CV_120"),
 # ruta de rescate
 ("    artifact_pct = ctx.artifact_pct\n    rr_eff = ctx.rr_eff\n    t_eff = ctx.t_eff\n    t_end_eff = ctx.t_end_eff\n\n    # Latencia simplificada (usar 45s como fallback)\n",
  "    artifact_pct = ctx.artifact_pct\n    rr_eff = ctx.rr_eff\n    t_eff = ctx.t_eff\n    idx_eff = ctx.original_idx_eff\n    t_end_eff = ctx.t_end_eff\n\n    # Latencia simplificada (usar 45s como fallback)\n"),
 ("    RMSSD = rmssd_ms(rr_tramo) if rr_tramo.size >= 2 else np.nan\n    lnRMSSD = float(np.log(RMSSD)) if (not np.isnan(RMSSD) and RMSSD > 0) else np.nan\n\n    # Cola",
  "    RMSSD = rmssd_ms(_seg(rr_eff[tramo], idx_eff[tramo]) / 1000.0) if rr_tramo.size >= 2 else np.nan\n    lnRMSSD = float(np.log(RMSSD)) if (not np.isnan(RMSSD) and RMSSD > 0) else np.nan\n\n    # Cola"),
 ("    n_pairs_tail = int(rr_tail.size - 1)\n    RMSSD_last2 = rmssd_ms(rr_tail) if rr_tail.size >= 2 else np.nan\n\n    # Calidad simplificada",
  "    _st = _seg(rr_eff[tail], idx_eff[tail]); n_pairs_tail = int(np.sum(np.isfinite(np.diff(_st)))) if _st.size > 1 else 0\n    RMSSD_last2 = rmssd_ms(_st / 1000.0) if rr_tail.size >= 2 else np.nan\n\n    # Calidad simplificada"),
]
# ---- HG-04 ----------------------------------------------------------------------
H4 = [
 ("    t_start_eff = 45.0 if np.isnan(lat) else max(lat, 45.0)\n\n    # Métricas tramo estabilizado\n    tramo = t_eff >= t_start_eff\n",
  "    t_start_eff = 180.0  # HG-04\n\n    # Métricas tramo estabilizado\n    tramo = (t_eff >= t_start_eff) & (t_eff <= 360.0)  # HG-04\n"),
 ("    # Cola (últimos 120s)\n    tail_start = t_end_eff - C[\"TAIL_S\"]\n    tail = (t_eff >= tail_start) & (t_eff <= t_end_eff)\n",
  "    # Cola HG-04: [240, 360] anidada\n    tail_start = 240.0\n    tail = (t_eff >= tail_start) & (t_eff <= 360.0)\n"),
 ("        if (not np.isnan(lat)) and artifact_pct <= C[\"ARTIFACT_OK_MAX\"] and 60.0 <= Lat_eff <= 600.0 and HRV_Stability == \"OK\":\n",
  "        if artifact_pct <= C[\"ARTIFACT_OK_MAX\"] and HRV_Stability == \"OK\":  # HG-04 opcion (a)\n"),
 ("        if np.isnan(lat):\n            Calidad = \"FLAG_mecánico\"\n", "        pass  # HG-04 opcion (a)\n"),
 # rescate
 ("    t_start_eff = 45.0\n\n    # Métricas tramo\n    tramo = t_eff >= t_start_eff\n",
  "    t_start_eff = 180.0  # HG-04\n\n    # Métricas tramo\n    tramo = (t_eff >= t_start_eff) & (t_eff <= 360.0)  # HG-04\n"),
 ("    # Cola\n    tail_start = t_end_eff - C[\"TAIL_S\"]\n    tail = (t_eff >= tail_start) & (t_eff <= t_end_eff)\n",
  "    # Cola HG-04\n    tail_start = 240.0\n    tail = (t_eff >= tail_start) & (t_eff <= 360.0)\n"),
]
H4W = [x for x in H4 if "opcion (a)" not in x[1]]  # solo ventana, Calidad vigente
H4E = [
 ("    t_start_eff = 45.0 if np.isnan(lat) else max(lat, 45.0)\n", "    t_start_eff = 180.0  # HG-04 variante E: inicio fijo, fin = final del registro\n"),
 ("    # Latencia simplificada (usar 45s como fallback)\n    t_start_eff = 45.0\n", "    # HG-04 variante E\n    t_start_eff = 180.0\n"),
]
ARMS = {"C": [], "H3": H3, "H4": H4, "H34": H3 + H4, "H4w": H4W, "H4e": H4E,
        "H4e210": [(a, b.replace("180.0", "210.0")) for a, b in H4E],
        "H4e240": [(a, b.replace("180.0", "240.0")) for a, b in H4E]}
# Inicio temprano fijo y fin operativo vigente; conserva cola y regla de Calidad.
# Se evalua por separado del recorte [180,360] y de la opcion (a) de Calidad.
for start_sec in (0, 60, 90, 120):
    start_patch = [(a, b.replace("180.0", f"{start_sec:.1f}")) for a, b in H4E]
    ARMS[f"E{start_sec}"] = start_patch
    ARMS[f"H3E{start_sec}"] = H3 + start_patch
ARMS["H3H4w"] = H3 + H4W
ARMS["E180"] = H4E  # sensibilidad posterior con el mismo fin que E0..E120
ARMS["H3E180"] = H3 + H4E

def patched(arm: str, base: Path) -> Path:
    src = (ROOT / "build_hrv_core.py").read_text(encoding="utf-8")
    nl = "\r\n" if "\r\n" in src else "\n"
    src = src.replace("\r\n", "\n")
    for a, b in ARMS[arm]:
        assert src.count(a) == 1, f"{arm}: ancla no unica ({src.count(a)}): {a[:70]!r}"
        src = src.replace(a, b)
    out = base / f"build_hrv_core_{arm}.py"; out.write_text(src.replace("\n", nl), encoding="utf-8")
    return out

def prepare(arm):
    base = WORK / arm
    if base.exists(): shutil.rmtree(base)
    (base / "data").mkdir(parents=True)
    for n in DATA_FILES:
        if (ROOT / "data" / n).exists(): shutil.copy2(ROOT / "data" / n, base / "data" / n)
    print(arm, "preparado en", base)

def run(arm, step):
    base = WORK / arm
    env = dict(os.environ, HRV_DATA_DIR=str(base / "data"), HRV_DISABLE_BACKUP="1", HRV_QUIET="1", PYTHONPATH=str(ROOT))
    if step == "core":
        script = ROOT / "build_hrv_core.py" if arm == "C" else patched(arm, base)
        cmd = [sys.executable, str(script), "--data-dir", str(base / "data"), "--rr-dir", str(WORK / "rr_src")]
    else:
        cmd = [sys.executable, str(ROOT / "build_hrv_final_dashboard.py"), "--data-dir", str(base / "data")]
    p = subprocess.run(cmd, cwd=base, env=env, capture_output=True, text=True)
    (base / f"{step}.log").write_text(p.stdout + "\n--- stderr ---\n" + p.stderr)
    print(arm, step, "rc", p.returncode, p.stderr[-800:])
    if p.returncode: raise SystemExit(1)

def collect(arm):
    base = WORK / arm
    h = {n: hashlib.sha256((base / "data" / n).read_bytes()).hexdigest() for n in OUTPUTS}
    (EXP / "results" / f"arm_{arm}_manifest.json").write_text(json.dumps({"arm": arm, "sha256": h}, indent=1))
    print(json.dumps(h, indent=1))

if __name__ == "__main__":
    arm, step = sys.argv[1], sys.argv[2]
    {"prepare": lambda: prepare(arm), "collect": lambda: collect(arm)}.get(step, lambda: run(arm, step))()
