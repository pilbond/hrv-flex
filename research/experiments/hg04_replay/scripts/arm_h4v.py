"""HG-04 replay: brazo H4v = valores de H4w (solo ventana) con Calidad y HRV_Stability
del control C. Separa el efecto de los valores del efecto de la composicion de dias clean."""
import os, shutil, subprocess, sys
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[4]
W = Path(os.environ.get("HG04_REPLAY_WORK", Path.home()/"hg04_replay_work"))
src, dst = W/"H4w", W/"H4v"
if dst.exists(): shutil.rmtree(dst)
shutil.copytree(src/"data", dst/"data")
f = dst/"data/ENDURANCE_HRV_master_CORE.csv"
x = pd.read_csv(f); c = pd.read_csv(W/"C/data/ENDURANCE_HRV_master_CORE.csv").set_index("Fecha")
for k in ("Calidad", "HRV_Stability"): x[k] = x.Fecha.map(c[k])
x.to_csv(f, index=False)
env = dict(os.environ, HRV_DATA_DIR=str(dst/"data"), HRV_DISABLE_BACKUP="1", HRV_QUIET="1", PYTHONPATH=str(ROOT))
p = subprocess.run([sys.executable, str(ROOT/"build_hrv_final_dashboard.py"), "--data-dir", str(dst/"data")], env=env, capture_output=True, text=True)
print("H4v final rc", p.returncode, p.stderr[-300:] if p.returncode else "")
