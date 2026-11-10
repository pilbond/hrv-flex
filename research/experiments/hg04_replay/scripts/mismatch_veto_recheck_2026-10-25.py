"""HG-04: recomprobacion tras revision critica del usuario (2026-10-25).

Exploratorio. No recalcula CORE ni repite el replay de RR. Corrige y reproduce:
  (1) "dia anterior" = vispera de calendario, no la medicion anterior
      (fallo detectado en mismatch_veto_tables_2026-10-25.py:34).
  (2) Pruebas de permutacion de los indicadores independientes con la vispera corregida.
  (3) Correlacion RMSSD-FC y su permutacion, antes calculadas fuera de script.
  (4) Cobertura de bienestar en los dias que pasan a VERDE (contradiccion U3).
  (5) Huellas sha256 de los archivos RR de origen, no solo del CSV de diagnostico.

Criterios en research/reports/hg04_protocolo_mismatch_veto_2026-10-25.md (escrito antes).
Escribe research/experiments/hg04_replay/results/mismatch_veto_recheck_2026-10-25.json
y out/hg04_evidencia_mismatch_veto_2026-10-25/vispera_corregida.csv
"""
from __future__ import annotations
import glob, hashlib, json, os, re
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[4]
WORK = Path(os.environ.get("HG04_REPLAY_WORK", Path.home() / "hg04_replay_work")) / "rr_src"
INC = ROOT / "out/hg04_calidad_semaforo_incremental_2026-10-23/comparacion_incremental.csv"
OUT = ROOT / "out/hg04_evidencia_mismatch_veto_2026-10-25"
RES = ROOT / "research/experiments/hg04_replay/results/mismatch_veto_recheck_2026-10-25.json"
PROT = ROOT / "research/reports/hg04_protocolo_mismatch_veto_2026-10-25.md"
SEED = 20261025
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def perm_median(a, b, n=20000, seed=SEED):
    """Permutacion bilateral sobre la diferencia de medianas. Omite ausentes."""
    a = np.asarray([x for x in a if np.isfinite(x)], float)
    b = np.asarray([x for x in b if np.isfinite(x)], float)
    if len(a) < 3 or len(b) < 3:
        return {"n_a": len(a), "n_b": len(b), "med_a": None, "med_b": None, "p": None,
                "nota": "muestras insuficientes"}
    obs = np.median(a) - np.median(b)
    pool = np.concatenate([a, b]); k = len(a)
    rng = np.random.default_rng(seed)
    cnt = sum(abs(np.median(p[:k]) - np.median(p[k:])) >= abs(obs) - 1e-12
              for p in (rng.permutation(pool) for _ in range(n)))
    return {"n_a": len(a), "n_b": len(b), "med_a": round(float(np.median(a)), 3),
            "med_b": round(float(np.median(b)), 3), "dif": round(float(obs), 3),
            "p": round((cnt + 1) / (n + 1), 4)}


def perm_corr(x, y, n=20000, seed=SEED):
    """Permutacion bilateral sobre la correlacion de Pearson de los rangos (Spearman)."""
    m = np.isfinite(x) & np.isfinite(y)
    x, y = np.asarray(x)[m], np.asarray(y)[m]
    if len(x) < 5:
        return {"n": int(len(x)), "rho": None, "p": None, "nota": "muestra insuficiente"}
    rk = lambda v: pd.Series(v).rank().to_numpy()
    rx, ry = rk(x), rk(y)
    obs = np.corrcoef(rx, ry)[0, 1]
    rng = np.random.default_rng(seed)
    cnt = sum(abs(np.corrcoef(rx, rng.permutation(ry))[0, 1]) >= abs(obs) - 1e-12 for _ in range(n))
    return {"n": int(len(x)), "rho": round(float(obs), 4), "p": round((cnt + 1) / (n + 1), 4)}


def main():
    I = pd.read_csv(INC, encoding="utf-8-sig")
    D = pd.read_csv(OUT / "recuperados_29_diagnostico.csv", encoding="utf-8-sig").set_index("Fecha")
    S = pd.read_csv(ROOT / "data/ENDURANCE_HRV_sessions_day.csv").set_index("Fecha")
    SL = pd.read_csv(ROOT / "data/ENDURANCE_HRV_sleep.csv").set_index("Fecha")
    W = pd.read_csv(ROOT / "data/ENDURANCE_HRV_wellness_subjective.csv").set_index("Fecha")
    I = I.set_index("Fecha")
    idx = list(I.index); pos = {d: i for i, d in enumerate(idx)}

    prev_med = lambda d: idx[pos[d] - 1] if pos[d] > 0 else None           # fallo original
    prev_cal = lambda d: (pd.Timestamp(d) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")  # correcto
    gv = lambda df, c, d: (pd.to_numeric(df[c], errors="coerce").get(d, np.nan)
                           if d is not None and c in df.columns else np.nan)
    has = lambda d: str(W.wellness_subjective_available.get(d, "")).strip().lower() == "true"

    # --- grupos del veto: ROJO con veto en NL; rebajados vs mantenidos por la regla ambar ---
    veto = I.index[(I.gate_final_NL_actual == "ROJO") &
                   (I.veto_agudo_NL_actual.astype(str).str.strip().str.lower()
                    .isin(["true", "1", "1.0"]))]
    reb = [d for d in veto if I.gate_final_NL_ambar[d] == "ÁMBAR"]
    man = [d for d in veto if I.gate_final_NL_ambar[d] == "ROJO"]

    # --- (1) impacto del fallo de fechas, dia a dia ---
    difs, rows = [], []
    for d in veto:
        pm, pc = prev_med(d), prev_cal(d)
        a, b = gv(S, "load_day", pm), gv(S, "load_day", pc)
        rows.append({"Fecha": d, "Grupo": "rebajado" if d in reb else "mantenido",
                     "Dia usado (medicion anterior)": pm, "Carga con fallo": a,
                     "Vispera de calendario": pc, "Carga corregida": b,
                     "Desfase (dias)": None if pm is None else
                     (pd.Timestamp(pc) - pd.Timestamp(pm)).days,
                     "Cambia": "SI" if (np.isfinite(a) != np.isfinite(b)) or
                     (np.isfinite(a) and np.isfinite(b) and abs(a - b) > 1e-9) else ""})
        if rows[-1]["Cambia"] == "SI" and np.isfinite(a) and np.isfinite(b):
            difs.append({"Fecha": d, "con_fallo": a, "corregido": b})
    T = pd.DataFrame(rows)
    T.to_csv(OUT / "vispera_corregida.csv", index=False, encoding="utf-8-sig")

    # --- (2) indicadores independientes, con vispera corregida ---
    IND = {"Carga día anterior": (S, "load_day", True),
           "Minutos día anterior": (S, "total_duration_min", True),
           "RPE máx día anterior": (S, "rpe_max_day", True),
           "Deriva cardiaca día anterior": (S, "cardiac_drift_worst", True),
           "Días intensos previos 3d": (S, "intense_days_prev_3d", False),
           "Sueño (min)": (SL, "polar_sleep_duration_min", False),
           "Eficiencia sueño (%)": (SL, "polar_efficiency_pct", False),
           "Interrupciones largas": (SL, "polar_interruptions_long", False)}
    pruebas = {}
    for name, (df, col, usa_prev) in IND.items():
        f = (lambda d: prev_cal(d)) if usa_prev else (lambda d: d)
        pruebas[name] = {"vispera_corregida": perm_median([gv(df, col, f(d)) for d in reb],
                                                          [gv(df, col, f(d)) for d in man])}
        if usa_prev:
            pruebas[name]["con_fallo_medicion_anterior"] = perm_median(
                [gv(df, col, prev_med(d)) for d in reb], [gv(df, col, prev_med(d)) for d in man])

    # --- (3) correlacion RMSSD-FC en los 29 recuperados, reproducible ---
    # Ambas desviaciones se construyen IGUAL (misma ventana, mismo origen). Mezclar la columna
    # almacenada del CSV con una ventana recalculada da un valor distinto y no comparable:
    # ese fue un error de la primera version de este script (daba -0,22 en lugar de -0,44).
    num = lambda c: pd.to_numeric(I[c], errors="coerce")
    rm_all, hr_all = num("RMSSD_stable"), num("HR_stable")
    ln_all = np.log(rm_all.where(rm_all > 0))

    def dev(s, d, w):
        v = s.iloc[max(0, pos[d] - (w - 1)):pos[d] + 1].dropna()
        return float(s[d] - np.median(v)) if len(v) >= 3 and np.isfinite(s[d]) else np.nan

    dias = [d for d in D.index if d in pos]
    corr = {"ln_RMSSD_vs_FC_desviaciones_locales": {
                f"ventana_{w}_mediciones": perm_corr(np.array([dev(ln_all, d, w) for d in dias]),
                                                     np.array([dev(hr_all, d, w) for d in dias]))
                for w in (7, 14, 30, 60)},
            "RMSSD_vs_FC_valores_crudos": perm_corr(np.array([rm_all[d] for d in dias]),
                                                    np.array([hr_all[d] for d in dias])),
            "nota_1": "El signo negativo reproduce en las cuatro ventanas, pero NO discrimina entre "
                      "fisiologia y artefacto: un latido no detectado alarga un RR, lo que sube el "
                      "RMSSD y baja la FC media (RMSSD+/FC-), el mismo signo que la retirada vagal "
                      "(RMSSD-/FC+). Argumento retirado como evidencia de calidad de senal.",
            "nota_2": "Ademas RMSSD y FC se derivan de la misma serie RR del mismo tramo, por lo que "
                      "su coherencia no es una verificacion independiente de la senal."}

    # --- (4) cobertura de bienestar en los cambios de color por quitar MISMATCH ---
    camb = [d for d in I.index if I.gate_final_NL_actual[d] != I.gate_final_NL_sin_mismatch[d]]
    verde = [d for d in camb if I.gate_final_NL_sin_mismatch[d] == "VERDE"]
    fat = lambda d: str(W.well_fatigue_label.get(d, "") or "").strip()
    # agregados de los dias que pasan a VERDE, con vispera de calendario y n explicito
    agg = {}
    for nm, df, col, up in [("Carga víspera", S, "load_day", True),
                            ("Sueño (min)", SL, "polar_sleep_duration_min", False),
                            ("Interrupciones largas", SL, "polar_interruptions_long", False)]:
        f = prev_cal if up else (lambda d: d)
        v = np.array([gv(df, col, f(d)) for d in verde], float); v = v[np.isfinite(v)]
        g = np.array([gv(df, col, f(d)) for d in idx], float); g = g[np.isfinite(g)]
        agg[nm] = {"mediana_VERDE": round(float(np.median(v)), 1) if len(v) else None,
                   "n_con_dato": int(len(v)), "n_dias": len(verde),
                   "mediana_global": round(float(np.median(g)), 1) if len(g) else None}

    u3 = {"cambios_color": len(camb), "pasan_a_VERDE": len(verde),
          "VERDE_con_bienestar": sum(has(d) for d in verde),
          "VERDE_sin_bienestar": sum(not has(d) for d in verde),
          "VERDE_con_fatiga_declarada_alta": [d for d in verde if fat(d).lower() in ("alta", "alto", "high")],
          "VERDE_sin_bienestar_fechas": [d for d in verde if not has(d)],
          "agregados_vispera_corregida": agg,
          "detalle": [{"Fecha": d, "bienestar": "si" if has(d) else "NO", "fatiga": fat(d)} for d in verde],
          "lectura": "La ausencia de fatiga alta en los 11 dias sin bienestar registrado es dato "
                     "AUSENTE, no observacion favorable: U3 no queda descartada. Ademas la carga de "
                     "la vispera en esos dias es mayor que la global, lo que apunta levemente en "
                     "contra de la propuesta, no a favor."}

    # --- (5) huellas de los RR de origen ---
    rrf = {}
    for f in glob.glob(str(WORK / "*")):
        m = re.search(r"(\d{4}-\d{2}-\d{2})", f)
        if m and m.group(1) in set(D.index): rrf[m.group(1)] = f
    rr_sha = {d: {"archivo": Path(p).name, "sha256": sha(p), "bytes": Path(p).stat().st_size}
              for d, p in sorted(rrf.items())}

    res = {"fecha": "2026-10-25", "motivo": "revision critica del usuario", "semilla": SEED,
           "protocolo_sha256": sha(PROT),
           "entradas_sha256": {str(p.relative_to(ROOT)): sha(p) for p in
                               [INC, OUT / "recuperados_29_diagnostico.csv",
                                ROOT / "data/ENDURANCE_HRV_sessions_day.csv",
                                ROOT / "data/ENDURANCE_HRV_sleep.csv",
                                ROOT / "data/ENDURANCE_HRV_wellness_subjective.csv"]},
           "rr_origen_sha256": rr_sha, "n_rr_con_huella": len(rr_sha),
           "n": {"veto_rojo": len(veto), "rebajados": len(reb), "mantenidos": len(man)},
           "fallo_fechas": {"descripcion": "prev() tomaba la medicion anterior, no la vispera",
                            "dias_veto_afectados": len(difs), "detalle": difs},
           "pruebas_independientes": pruebas, "correlacion": corr, "U3_cobertura": u3}
    RES.parent.mkdir(parents=True, exist_ok=True)
    RES.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"veto ROJO {len(veto)} = rebajados {len(reb)} + mantenidos {len(man)}")
    print(f"\n(1) dias del veto con carga afectada por el fallo: {len(difs)}")
    for x in difs: print("   ", x["Fecha"], x["con_fallo"], "->", x["corregido"])
    print("\n(2) carga dia anterior:")
    for k, v in pruebas["Carga día anterior"].items():
        print(f"   {k}: med {v['med_a']} vs {v['med_b']} dif {v['dif']} p {v['p']} (n {v['n_a']}/{v['n_b']})")
    print("\n    resto de indicadores (vispera corregida):")
    for k, v in pruebas.items():
        w = v["vispera_corregida"]
        if w.get("p") is not None:
            print(f"   {k}: {w['med_a']} vs {w['med_b']} p {w['p']} (n {w['n_a']}/{w['n_b']})")
    print("\n(3) correlacion ln_RMSSD vs FC (desviaciones locales, misma construccion):")
    for k, v in corr["ln_RMSSD_vs_FC_desviaciones_locales"].items():
        print(f"   {k}: rho {v['rho']} p {v['p']} (n {v['n']})")
    print("   crudos:", corr["RMSSD_vs_FC_valores_crudos"])
    print("   -> signo robusto, pero no discrimina fisiologia de artefacto (ver nota_1)")
    print(f"\n(4) U3: {u3['pasan_a_VERDE']} pasan a VERDE; con bienestar {u3['VERDE_con_bienestar']}, "
          f"sin bienestar {u3['VERDE_sin_bienestar']}; fatiga alta {u3['VERDE_con_fatiga_declarada_alta']}")
    print(f"\n(5) huellas RR de origen: {len(rr_sha)} de {len(D)} dias")
    print("\nJSON:", RES.relative_to(ROOT))


if __name__ == "__main__":
    main()
