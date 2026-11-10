"""HG-04 replay: en los dias que salen de ROJO con H4w, ¿de que tramo del registro
sale la diferencia? lnRMSSD por segmento: [t_start_C,180), [180,360], (360,te].
Pares originalmente consecutivos. Solo lectura sobre la copia de trabajo."""
import sys, os, json
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[4]; sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT/"research/scripts"))
import build_hrv_core as B
from hg04_transient_overlap_check import ln_rmssd
W = Path(os.environ.get("HG04_REPLAY_WORK", Path.home()/"hg04_replay_work"))
C = pd.read_csv(W/"C/data/ENDURANCE_HRV_master_FINAL.csv").set_index("Fecha"); X = pd.read_csv(W/"H4w/data/ENDURANCE_HRV_master_FINAL.csv").set_index("Fecha")
CC = pd.read_csv(W/"C/data/ENDURANCE_HRV_master_CORE.csv").set_index("Fecha")
idx = json.load(open(W/"rr_src/_index.json"))
ch = C.index[(C.gate_final != X.gate_final) & (C.gate_final == "ROJO")]
allok = CC.index[CC.Calidad == "OK"]
def seg(d):
    f = W/"rr_src"/idx[d]["file"].replace(" (1)", "")
    c = B._parse_and_filter_rr(f, B.CONSTANTS); rr, t, te = c.rr_eff.astype(float), c.t_eff.astype(float), c.t_end_eff
    ts = float(CC.loc[d, "Notes"].split("t_start_eff=")[1].split("s")[0])
    return dict(fecha=d, ts=ts, te=round(te), pre=ln_rmssd(rr, t, ts, 180), win=ln_rmssd(rr, t, 180, 360), post=ln_rmssd(rr, t, 360, te+1),
                lnC=CC.loc[d, "lnRMSSD"])
R = pd.DataFrame([seg(d) for d in ch])
R["post_menos_win"] = R.post - R.win; R["pre_menos_win"] = R.pre - R.win
print(R.round(3).to_string(index=False))
print("\nmedianas:", R[["ts","te","post_menos_win","pre_menos_win"]].median().round(3).to_dict())
ref = pd.DataFrame([seg(d) for d in np.random.default_rng(1).choice(list(allok), 120, replace=False)])
print("referencia 120 dias OK al azar, mediana post-win:", round((ref.post-ref.win).median(),3), "| pre-win:", round((ref.pre-ref.win).median(),3), "| ts mediana:", ref.ts.median())
