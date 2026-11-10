"""Independent aggregate audit of the 2026-10-22 report and exported replays.

Read-only inputs; writes aggregate findings, never full personal datasets.
Optional --rr-dir points to the prior extracted RR directory with _index.json.
Reconstructs the 22 newly LAT-only flagged days when those sources exist.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
SOURCE = ROOT / "out/hg04_copias_paralelas_2026-10-22"
ARMS = ["C", "H3", "H3S90", "H3S120", "H3S90T375"]
OUT = Path(__file__).resolve().parents[1] / "results/report_audit_2026-10-22.json"


def stats(v):
    v = v[np.isfinite(v)]
    return {"n": len(v), "bias": float(v.mean()),
            "loa": [float(v.mean()-1.96*v.std()), float(v.mean()+1.96*v.std())],
            "median_abs": float(v.abs().median()), "p95_abs": float(v.abs().quantile(.95))}


def rolls(x):
    out, chosen = {}, {}
    for day in x.index:
        y = x.loc[:day]
        y = y.loc[y.Calidad.eq("OK") & np.isfinite(y.lnRMSSD) & np.isfinite(y.HR_stable) & np.isfinite(y.RMSSD_stable)].tail(3)
        out[day], chosen[day] = y.lnRMSSD.mean(), tuple(y.index)
    return pd.Series(out), chosen


def reconstruct(rrdir, dates, truncated):
    sys.path.insert(0, str(ROOT))
    from build_hrv_core import CONSTANTS as c
    index = json.loads((rrdir / "_index.json").read_text())
    values = []
    for day in dates:
        raw = pd.read_csv(rrdir / index[day]["file"])
        rr = pd.to_numeric(raw.duration, errors="coerce").to_numpy(float)
        off = pd.to_numeric(raw.offline, errors="coerce").fillna(0).to_numpy(int)
        ix = np.arange(len(rr)); valid = ~np.isnan(rr)
        rr, off, ix = rr[valid], off[valid], ix[valid]
        valid = np.cumsum(rr)/1000 <= 375
        rr, off, ix = rr[valid], off[valid], ix[valid]
        t = np.cumsum(rr)/1000; end = t[-1]-c["TAIL_TRIM_S"]
        valid = (off == 0) & (rr >= c["RR_MIN_MS"]) & (rr <= c["RR_MAX_MS"])
        rr, t, ix = rr[valid], t[valid], ix[valid]
        keep = np.ones(len(rr), bool); keep[1:] = abs(np.diff(rr))/rr[:-1] <= c["DELTA_RR_MAX"]
        valid = keep & (t <= end); rr, t, ix = rr[valid], t[valid], ix[valid]
        def rm(mask):
            r, ids = rr[mask], ix[mask]
            diff = np.diff(r)[np.diff(ids) == 1]
            return np.sqrt(np.mean(diff**2)) if len(diff) else np.nan
        assert np.isclose(rm(t >= 90), truncated.at[day, "RMSSD_stable"], rtol=1e-10)
        nwin = int(np.floor(end/c["LAT_STEP_S"]))+1
        ws = []
        for k in range(nwin):
            mask = (t >= k*c["LAT_STEP_S"]) & (t < k*c["LAT_STEP_S"]+c["LAT_WIN_S"])
            ws.append(rm(mask) if mask.sum()-1 >= 20 else np.nan)
        best = min(max(abs(ws[k]-ws[k-1])/ws[k-1], abs(ws[k+1]-ws[k])/ws[k])
                   for k in range(1, nwin-1) if np.isfinite(ws[k-1:k+2]).all())
        assert best >= c["LAT_REL_EPS"]
        valid_ws = np.array(ws)[np.isfinite(ws)]
        target = np.median(valid_ws[-4:])
        fallback = any(np.isfinite(ws[k:k+3]).all() and np.all(abs(np.array(ws[k:k+3])-target)/target < c["LAT_REL_EPS"])
                       for k in range(nwin-2)) if len(valid_ws) >= 4 else False
        assert not fallback
        values.append((nwin, sum(np.isfinite(ws)), best,
                       sum(k*c["LAT_STEP_S"]+c["LAT_WIN_S"] <= end for k in range(nwin)), end-(nwin-1)*c["LAT_STEP_S"]))
    z = np.array(values)
    return {"n_reproduced": len(z), "nwin_unique": np.unique(z[:,0]).tolist(),
            "valid_windows_counts": pd.Series(z[:,1]).value_counts().to_dict(),
            "best_triplet_median_min_max": [float(np.median(z[:,2])), float(z[:,2].min()), float(z[:,2].max())],
            "full_60s_windows_unique": np.unique(z[:,3]).tolist(),
            "last_window_available_s": [float(z[:,4].min()), float(z[:,4].max())]}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--rr-dir", type=Path); args = parser.parse_args()
    cs, fs, hashes = {}, {}, {}
    for arm in ARMS:
        for kind, dest in [("CORE", cs), ("FINAL", fs)]:
            path = SOURCE / arm / f"ENDURANCE_HRV_master_{kind}.csv"
            dest[arm] = pd.read_csv(path).set_index("Fecha")
            hashes[f"{arm}/{kind}"] = hashlib.sha256(path.read_bytes()).hexdigest()
    idx = cs["C"].index
    assert idx.is_unique and idx.is_monotonic_increasing
    assert all(x.index.equals(idx) for x in [*cs.values(), *fs.values()])
    result = {"n": len(idx), "range": [idx.min(),idx.max()], "sha256": hashes, "arms": {}, "comparisons": {}}
    for arm in ARMS:
        x, f = cs[arm], fs[arm]
        notes = x.Notes.fillna("")
        duration = pd.to_numeric(notes.str.extract(r"dur_tramo=([\d.]+)")[0], errors="coerce")
        result["arms"][arm] = {"quality": x.Calidad.value_counts().to_dict(), "gate": f.gate_final.value_counts().to_dict(),
                                "LAT_NAN": int(x.Tiempo_Estabilizacion.isna().sum()),
                                "geometry": {era: {"median": float(duration[(idx >= "2026-03-06") == ecg].loc[x.Calidad.ne("INVALID")].median()),
                                                   "p5": float(duration[(idx >= "2026-03-06") == ecg].loc[x.Calidad.ne("INVALID")].quantile(.05))}
                                             for era,ecg in [("Polar",False),("ECG",True)]}}
    for new,ref in [(a,"C") for a in ARMS[1:]]+[("H3S90T375","H3S90")]:
        a,b,fa,fb = cs[ref],cs[new],fs[ref],fs[new]
        changes = fa.gate_final.ne(fb.gate_final)
        entry = {"gates": int(changes.sum()), "actions": int(fa.Action.ne(fb.Action).sum()),
                 "quality": int(a.Calidad.ne(b.Calidad).sum()), "by_era": {}}
        for era,mask in [("total",pd.Series(True,index=idx)),("Polar",pd.Series(idx < "2026-03-06",index=idx)),("ECG",pd.Series(idx >= "2026-03-06",index=idx))]:
            ok = mask & a.Calidad.eq("OK") & b.Calidad.eq("OK")
            entry["by_era"][era] = {"ln": stats((b.lnRMSSD-a.lnRMSSD)[ok]), "hr": stats((b.HR_stable-a.HR_stable)[ok])}
        q = a.Calidad.ne(b.Calidad); v = fa.veto_agudo.ne(fb.veto_agudo)
        entry["priority_groups_not_causal"] = {"quality": int((changes&q).sum()), "veto": int((changes&~q&v).sum()), "remaining": int((changes&~q&~v).sum())}
        margin = pd.concat([((fa.d_ln+fa.SWC_ln)/fa.SWC_ln).abs(),((fa.d_HR-fa.SWC_HR)/fa.SWC_HR).abs()],axis=1).min(axis=1)
        valid = fa.gate_final.isin(["ROJO","ÁMBAR","VERDE"]) & np.isfinite(fa.SWC_ln) & np.isfinite(fa.SWC_HR)
        entry["threshold_distance"] = {label: {"n": int(mask.sum()), "median": float(margin[mask].median()), "pct_lt025": float(100*(margin[mask]<.25).mean()), "n_gt1": int((margin[mask]>1).sum())}
                                       for label,mask in [("changed",changes&valid),("same",~changes&valid)]}
        result["comparisons"][new+"_vs_"+ref] = entry
    a,b,fa,fb = cs["H3S90"],cs["H3S90T375"],fs["H3S90"],fs["H3S90T375"]
    ok = a.Calidad.eq("OK") & b.Calidad.eq("OK"); changes = fa.gate_final.ne(fb.gate_final)
    raw = b.lnRMSSD-a.lnRMSSD; used = fb.lnRMSSD_used-fa.lnRMSSD_used
    r1,d1 = rolls(a); r2,d2 = rolls(b); composition = pd.Series({dt:d1[dt]!=d2[dt] for dt in idx})
    amp = ok & (used.abs() > 2*raw.abs())
    result["truncation"] = {"common_OK": int(ok.sum()), "median_abs_percent_rmssd": float((100*np.expm1(raw[ok])).abs().median()),
        "p95_abs_percent_rmssd": float((100*np.expm1(raw[ok])).abs().quantile(.95)),
        "raw_gate_same_on_changed": int((changes & fa.gate_raw_today.eq(fb.gate_raw_today)).sum()),
        "used_amp": int(amp.sum()), "used_amp_nonzero_raw": int((amp&(raw.abs()>1e-9)).sum()),
        "used_amp_composition": int((amp&composition).sum()), "used_amp_changed_gate": int((amp&changes).sum()),
        "used_amp_composition_changed_gate": int((amp&composition&changes).sum()),
        "composition_changed_gate_all": int((composition&changes).sum()),
        "p95_abs_used": float(used[ok].abs().quantile(.95)), "p95_abs_pure_roll": float((r2-r1)[ok].abs().quantile(.95)),
        "median_changes_common_OK": {col:float((fb[col]-fa[col])[ok].median()) for col in ["lnRMSSD_today","ln_base60","d_ln"]},
        "new_invalid": list(idx[b.Calidad.eq("INVALID") & ~a.Calidad.eq("INVALID")])}
    only = b.Tiempo_Estabilizacion.isna() & b.Calidad.eq("FLAG_mecánico") & b.HRV_Stability.eq("OK") & (b.Artifact_pct <= 15)
    new_only = only & a.Calidad.eq("OK")
    result["latency"] = {"nan_total": int(b.Tiempo_Estabilizacion.isna().sum()), "nan_noninvalid": int((b.Tiempo_Estabilizacion.isna() & b.Calidad.ne("INVALID")).sum()),
        "sole_reason_total": int(only.sum()), "sole_reason_previously_OK": int(new_only.sum()),
        "sole_reason_previously_FLAG": int((only&a.Calidad.eq("FLAG_mecánico")).sum()),
        "predicted_quality_without_lat_rule": {"OK": int((b.Calidad.eq("OK")|only).sum()), "FLAG": int((b.Calidad.eq("FLAG_mecánico")&~only).sum()), "INVALID": int(b.Calidad.eq("INVALID").sum())},
        "full_record_latency_median": float(a.loc[new_only,"Tiempo_Estabilizacion"].median()),
        "full_record_latency_ge300": int((a.loc[new_only,"Tiempo_Estabilizacion"]>=300).sum()),
        "full_record_latency_gt360": int((a.loc[new_only,"Tiempo_Estabilizacion"]>360).sum())}
    if args.rr_dir: result["detector_reconstruction"] = reconstruct(args.rr_dir, idx[new_only], b)
    # Reconcile displayed values in the added workbook sheet against unrounded CSVs.
    x = pd.read_excel(SOURCE / "comparacion_dia_a_dia.xlsx", sheet_name="90s vs corte 375s").set_index("Fecha")
    assert x.index.equals(idx)
    checked = 0
    for suffix,c,f in [("sin corte",a,fa),("con corte",b,fb)]:
        for label,key,obj,dec in [("RMSSD","RMSSD_stable",c,1),("lnRMSSD","lnRMSSD",c,3),("FC","HR_stable",c,1),("Calidad","Calidad",c,None),("Semáforo","gate_final",f,None),("Acción","Action",f,None)]:
            name = f"{label} {suffix}"+(" (ms)" if label=="RMSSD" else "")
            expected,actual = obj[key],x[name]
            assert (np.isclose(expected.round(dec),actual,equal_nan=True).all() if dec is not None else expected.fillna("").eq(actual.fillna("")).all()), name
            checked += len(x)
    result["workbook_cells_verified"] = checked
    workbook = SOURCE / "comparacion_dia_a_dia.xlsx"
    result["sha256"]["workbook"] = hashlib.sha256(workbook.read_bytes()).hexdigest()
    result["control_vs_production"] = {}
    for kind, control in [("CORE", cs["C"]), ("FINAL", fs["C"])]:
        path = ROOT / "data" / f"ENDURANCE_HRV_master_{kind}.csv"
        if not path.exists():
            result["control_vs_production"][kind] = {"available": False}
            continue
        production = pd.read_csv(path).set_index("Fecha")
        assert production.index.equals(idx)
        differences = {}
        for col in control.columns.intersection(production.columns):
            left, right = control[col], production[col]
            if pd.api.types.is_numeric_dtype(left) and pd.api.types.is_numeric_dtype(right):
                equal = np.isclose(left, right, rtol=1e-10, atol=1e-12, equal_nan=True)
            else:
                equal = left.fillna("").eq(right.fillna(""))
            if not np.all(equal): differences[col] = list(idx[~equal])
        result["control_vs_production"][kind] = {"available": True, "differing_dates_by_column": differences}
        result["sha256"]["production/"+kind] = hashlib.sha256(path.read_bytes()).hexdigest()
    result["NL_export_available"] = (SOURCE / "H3S90T375NL/ENDURANCE_HRV_master_FINAL.csv").exists()
    OUT.write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False),encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k not in ["sha256","arms","comparisons"]},ensure_ascii=False,indent=2))
    for key,val in result["comparisons"].items():print(key, val)


if __name__ == "__main__":
    main()
