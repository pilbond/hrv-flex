"""HG-10: geometría candidata (90 s / 375 s / recorte 15 s) y contrato de pares RR
físicamente consecutivos en CORE.

Cubre la entrega técnica 1-4 de `docs/HRV/HG-10 Corte historico y contrato de
pares consecutivos.md`: pares y ventanas, geometría y material insuficiente,
Calidad y artefactos, y las dos rutas de CORE (normal y rescate).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import build_hrv_core as core

C = core.CONSTANTS
ROOT = Path(__file__).resolve().parents[1]


def test_find_rr_files_tie_is_stable_and_migration_requires_unique_date(tmp_path: Path):
    first = tmp_path / "ENDURANCE_2025-10-07_RR.csv"
    duplicate = tmp_path / "ENDURANCE_2025-10-07_(1)_RR.csv"
    for path in (first, duplicate):
        path.write_text("duration,offline\n1000,0\n", encoding="utf-8")
    files = core.find_rr_files(tmp_path)
    assert files == sorted((first, duplicate), key=lambda p: (p.name.casefold(), str(p)))
    assert core.duplicate_rr_dates(files) == ["2025-10-07"]


# ---------------------------------------------------------------- utilidades


def write_rr(tmp_path: Path, rows, fecha: str = "2026-01-05") -> Path:
    """Escribe un archivo RR `duration,offline` con el nombre canónico por fecha."""
    body = "\n".join(f"{d},{int(off)}" for d, off in rows)
    path = tmp_path / f"ENDURANCE_{fecha}_RR.csv"
    path.write_text("duration,offline\n" + body + "\n", encoding="utf-8")
    return path


def steady(n: int = 600, base: float = 1000.0, amp: float = 40.0):
    """RR alternante determinista: todos en rango y sin saltos delta-RR >20%."""
    return [(base + (amp if i % 2 else -amp), 0) for i in range(n)]


def growing(n: int = 600, base: float = 1000.0, amp0: float = 10.0, rate: float = 1.004):
    """RR cuya amplitud crece >8% cada 30 s: impide detectar estabilización."""
    return [(base + (amp0 * rate**i) * (1 if i % 2 else -1), 0) for i in range(n)]


def window_of(ctx) -> tuple[np.ndarray, np.ndarray]:
    mask = ctx.t_eff >= C["WINDOW_START_S"]
    return ctx.rr_eff[mask], ctx.original_idx_eff[mask]


# ------------------------------------------------- 1. pares físicos y RMSSD


def test_rmssd_solo_usa_pares_originalmente_consecutivos():
    rr_ms = np.array([1000.0, 1040.0, 960.0, 1040.0])
    idx = np.array([0, 1, 3, 4])

    # Pares válidos: (0,1) -> 40 ms y (3,4) -> 80 ms. El salto 1->3 no empareja.
    assert core.n_consecutive_pairs(rr_ms, idx) == 2
    assert core.rmssd_consecutive_ms(rr_ms, idx) == pytest.approx(
        np.sqrt((40.0**2 + 80.0**2) / 2)
    )
    # Sin descartes la fórmula coincide con el RMSSD clásico de la serie.
    seguidos = np.arange(4)
    assert core.rmssd_consecutive_ms(rr_ms, seguidos) == pytest.approx(
        core.rmssd_ms(rr_ms / 1000.0)
    )


def test_pares_en_huecos_centrales_extremos_y_sucesivos():
    rr_ms = np.array([1000.0, 1010.0, 1020.0, 1030.0, 1040.0])
    assert core.n_consecutive_pairs(rr_ms, np.array([0, 1, 2, 3, 4])) == 4  # sin huecos
    assert core.n_consecutive_pairs(rr_ms, np.array([0, 1, 3, 4, 5])) == 3  # central
    assert core.n_consecutive_pairs(rr_ms, np.array([0, 2, 3, 4, 5])) == 3  # inicial
    assert core.n_consecutive_pairs(rr_ms, np.array([0, 1, 2, 3, 9])) == 3  # final
    assert core.n_consecutive_pairs(rr_ms, np.array([0, 1, 4, 7, 8])) == 2  # sucesivos
    assert core.n_consecutive_pairs(rr_ms, np.array([0, 2, 4, 6, 8])) == 0  # ninguno


def test_sin_pares_el_rmssd_es_nan():
    rr_ms = np.array([1000.0, 1010.0, 1020.0])
    assert core.n_consecutive_pairs(rr_ms, np.array([0, 2, 4])) == 0
    assert np.isnan(core.rmssd_consecutive_ms(rr_ms, np.array([0, 2, 4])))
    assert np.isnan(core.rmssd_consecutive_ms(np.array([1000.0]), np.array([0])))
    assert np.isnan(core.rmssd_from_pair_diffs(np.array([])))


# ------------------------------------------------------------- 2. Poincaré


def test_poincare_exige_minimo_de_rr_y_de_pares():
    rr_ms = np.array([1000.0 + 10 * (i % 2) for i in range(10)])

    # 10 RR y 9 pares consecutivos: se publica.
    sd1, sd2, ratio = core.poincare_sd(rr_ms, np.arange(10), C)
    assert not np.isnan(sd1)

    # 10 RR pero solo 8 pares consecutivos: por debajo del mínimo -> NaN.
    idx_8 = np.array([0, 1, 2, 3, 4, 5, 6, 7, 8, 10])
    assert core.n_consecutive_pairs(rr_ms, idx_8) == 8
    assert all(np.isnan(v) for v in core.poincare_sd(rr_ms, idx_8, C))

    # 9 RR: por debajo del mínimo de material aunque todos sean consecutivos.
    assert all(np.isnan(v) for v in core.poincare_sd(rr_ms[:9], np.arange(9), C))


def test_sd1_usa_pares_consecutivos_y_sd2_conserva_su_definicion():
    rng = np.random.default_rng(20261027)
    rr_ms = 1000.0 + rng.normal(0, 30, 40)
    idx_todos = np.arange(40)
    idx_hueco = np.concatenate([np.arange(20), np.arange(21, 41)])

    sd1_a, sd2_a, _ = core.poincare_sd(rr_ms, idx_todos, C)
    sd1_b, sd2_b, _ = core.poincare_sd(rr_ms, idx_hueco, C)

    # SD1 cambia al excluir el par que cruza el descarte; SD2 no depende de pares.
    assert sd1_a != sd1_b
    assert sd2_a == pytest.approx(sd2_b, abs=0.3)

    # SD2 conserva la definición sobre la varianza de los RR individuales.
    diff = core.rr_pair_diffs(rr_ms, idx_todos)
    sd1_ref = float(np.std(diff, ddof=0) / np.sqrt(2.0))
    sd2_ref = float(np.sqrt(2.0 * float(np.var(rr_ms, ddof=0)) - sd1_ref**2))
    assert sd1_a == pytest.approx(round(sd1_ref, 2))
    assert sd2_a == pytest.approx(round(sd2_ref, 2))


def test_poincare_exige_procedencia_explicita():
    with pytest.raises(TypeError):
        core.poincare_sd(np.arange(20, dtype=float) + 1000.0)


# ------------------------------------------------------- 3. geometría 90/375/15


def test_corte_a_375_y_recorte_final_de_15_con_limites_inclusivos(tmp_path):
    # 500 latidos de exactamente 1000 ms: t_end acumulado = 1, 2, ... 500 s.
    ctx = core._parse_and_filter_rr(write_rr(tmp_path, [(1000.0, 0)] * 500), C)

    assert ctx.dur_full == pytest.approx(500.0)
    assert ctx.record_cut_applied is True
    assert ctx.N_total == 375                     # corte inclusivo en 375 s
    assert ctx.dur_raw == pytest.approx(375.0)
    assert ctx.t_end_eff == pytest.approx(360.0)  # recorte final de 15 s

    # Límite superior inclusivo: el latido que termina justo en 360 s se conserva.
    assert ctx.t_eff.max() == pytest.approx(360.0)
    # Límite inferior inclusivo: el latido que termina justo en 90 s entra al tramo.
    tramo = ctx.t_eff >= C["WINDOW_START_S"]
    assert ctx.t_eff[tramo].min() == pytest.approx(90.0)
    assert int(tramo.sum()) == 271                # de 90 s a 360 s, ambos incluidos


def test_registro_mas_corto_que_el_corte_no_se_trunca(tmp_path):
    ctx = core._parse_and_filter_rr(write_rr(tmp_path, [(1000.0, 0)] * 300), C)
    assert ctx.record_cut_applied is False
    assert ctx.dur_raw == pytest.approx(300.0)
    assert ctx.t_end_eff == pytest.approx(285.0)


def test_el_inicio_del_tramo_es_fijo_y_no_lo_decide_la_latencia(tmp_path):
    row, _ = core.compute_day_from_rr(write_rr(tmp_path, steady(600)), pd.DataFrame(), C)
    assert f"t_start_eff={C['WINDOW_START_S']:.1f}s" in row["Notes"]
    assert f"geom={C['GEOMETRY_VERSION']}" in row["Notes"]
    # La latencia se sigue publicando como diagnóstico.
    assert not np.isnan(row["Tiempo_Estabilizacion"])


def test_artifact_pct_se_calcula_sobre_el_registro_truncado(tmp_path):
    rows = steady(600)
    for i in range(500, 540):          # descartes situados más allá de los 375 s
        rows[i] = (rows[i][0], 1)
    ctx = core._parse_and_filter_rr(write_rr(tmp_path, rows), C)
    assert ctx.artifact_pct == pytest.approx(0.0)

    rows2 = steady(600)
    for i in range(100, 140):          # mismos descartes, ahora dentro del corte
        rows2[i] = (rows2[i][0], 1)
    ctx2 = core._parse_and_filter_rr(write_rr(tmp_path, rows2, "2026-01-06"), C)
    assert ctx2.artifact_pct == pytest.approx(100.0 * 40 / ctx2.N_total)


# ------------------------------------------------ 4. salidas seguras y Calidad


def test_dia_completo_y_limpio_queda_ok(tmp_path):
    row, _ = core.compute_day_from_rr(write_rr(tmp_path, steady(600)), pd.DataFrame(), C)
    assert row["Calidad"] == "OK"
    assert row["HRV_Stability"] == "OK"
    # Sin historial solo aparece el flag de beta; ninguno de los motivos HG-10.
    assert row["Flags"] == "BETA_NONE"
    assert row["RMSSD_stable"] > 0
    assert "axis=OK" in row["Notes"]


def test_rmssd_de_core_usa_los_pares_consecutivos_del_tramo(tmp_path):
    rows = steady(600)
    for i in (200, 201, 260, 300):
        rows[i] = (rows[i][0], 1)      # descartes dentro del tramo
    path = write_rr(tmp_path, rows)

    row, _ = core.compute_day_from_rr(path, pd.DataFrame(), C)
    ctx = core._parse_and_filter_rr(path, C)
    rr_win, idx_win = window_of(ctx)

    assert row["RMSSD_stable"] == pytest.approx(core.rmssd_consecutive_ms(rr_win, idx_win))
    # La fórmula sin procedencia emparejaría RR separados por los descartes.
    assert row["RMSSD_stable"] != pytest.approx(core.rmssd_ms(rr_win / 1000.0))
    assert f"pairs_tramo={core.n_consecutive_pairs(rr_win, idx_win)}" in row["Notes"]


def test_registro_demasiado_corto_no_puede_quedar_ok(tmp_path):
    # 100 s de registro: tras el recorte de 15 s el final queda antes de los 90 s.
    row, _ = core.compute_day_from_rr(
        write_rr(tmp_path, [(1000.0, 0)] * 100), pd.DataFrame(), C
    )
    assert "REC_SHORT" in row["Flags"]
    assert np.isnan(row["RMSSD_stable"])
    assert row["Calidad"] != "OK"


def test_tramo_sin_pares_consecutivos_no_puede_quedar_ok(tmp_path):
    # Un descarte de cada dos deja el tramo sin ningún par físicamente contiguo.
    rows = steady(600)
    for i in range(1, 600, 2):
        rows[i] = (rows[i][0], 1)
    row, _ = core.compute_day_from_rr(write_rr(tmp_path, rows), pd.DataFrame(), C)

    assert np.isnan(row["RMSSD_stable"])
    assert "WIN_NO_PAIRS" in row["Flags"]
    assert row["Calidad"] != "OK"


def test_duracion_no_finita_marca_el_eje_temporal_y_bloquea_ok(tmp_path):
    rows = steady(600)
    rows[10] = ("", 0)                 # duración ausente: el eje deja de ser fiable
    row, _ = core.compute_day_from_rr(write_rr(tmp_path, rows), pd.DataFrame(), C)

    assert "TIME_AXIS_UNRELIABLE" in row["Flags"]
    assert "axis=UNRELIABLE" in row["Notes"]
    assert row["Calidad"] != "OK"
    assert row["RMSSD_stable"] > 0     # el valor sigue publicándose como diagnóstico


def test_cola_con_pares_insuficientes_marca_unstable(tmp_path):
    rows = steady(600)
    for i in range(241, 375, 2):       # diezma la cola: <60 pares consecutivos
        rows[i] = (rows[i][0], 1)
    path = write_rr(tmp_path, rows)
    row, _ = core.compute_day_from_rr(path, pd.DataFrame(), C)

    ctx = core._parse_and_filter_rr(path, C)
    tail = (ctx.t_eff >= ctx.t_end_eff - C["TAIL_S"]) & (ctx.t_eff <= ctx.t_end_eff)
    assert core.n_consecutive_pairs(ctx.rr_eff[tail], ctx.original_idx_eff[tail]) < C["TAIL_MIN_PAIRS"]
    assert row["HRV_Stability"] == "Unstable"
    assert row["Stability_Subtype"] == "STAB_TAIL_SHORT"
    assert row["Calidad"] != "OK"


# --------------------------------- 5. Calidad HG-09: LAT_NAN y MISMATCH intactos


def test_lat_nan_con_inestabilidad_sigue_excluyendo_el_dia(tmp_path):
    row, _ = core.compute_day_from_rr(write_rr(tmp_path, growing(600)), pd.DataFrame(), C)
    assert np.isnan(row["Tiempo_Estabilizacion"])
    assert "LAT_NAN" in row["Flags"]
    assert row["Calidad"] == "FLAG_mecánico"


def test_stab_last2_mismatch_sigue_excluyendo_el_dia(tmp_path):
    # Tramo con amplitud 40 ms y cola (últimos ~120 s) con amplitud 5 ms.
    rows = [(1000.0 + (40 if i % 2 else -40), 0) for i in range(240)]
    rows += [(1000.0 + (5 if i % 2 else -5), 0) for i in range(360)]
    row, _ = core.compute_day_from_rr(write_rr(tmp_path, rows), pd.DataFrame(), C)

    assert row["Stability_Subtype"] == "STAB_LAST2_MISMATCH"
    assert row["tail_mismatch_pct"] > 15.0
    assert row["Calidad"] == "FLAG_mecánico"


def test_lat_nan_y_mismatch_combinados(tmp_path):
    row, _ = core.compute_day_from_rr(write_rr(tmp_path, growing(600)), pd.DataFrame(), C)
    assert "LAT_NAN" in row["Flags"]
    assert "STAB_LAST2_MISMATCH" in row["Flags"]
    assert row["Calidad"] == "FLAG_mecánico"


def test_artefactos_por_encima_del_20_pct_siguen_siendo_invalid(tmp_path):
    rows = steady(600)
    for i in range(0, 375, 4):
        rows[i] = (rows[i][0], 1)
    row, _ = core.compute_day_from_rr(write_rr(tmp_path, rows), pd.DataFrame(), C)
    assert row["Artifact_pct"] > 20.0
    assert row["Calidad"] == "INVALID"


# ---------------------------------------------------------- 6. ruta de rescate


def test_rescate_usa_la_misma_geometria_y_pares(tmp_path):
    rows = steady(600)
    for i in (200, 201, 260):
        rows[i] = (rows[i][0], 1)
    path = write_rr(tmp_path, rows)

    row, beta = core.compute_day_from_rr_core_only(path, C)
    ctx = core._parse_and_filter_rr(path, C)
    rr_win, idx_win = window_of(ctx)

    assert beta is None
    assert row["Calidad"] == "FLAG_mecánico"          # el rescate nunca queda OK
    assert row["Flags"].split("|")[0] == "RESCUE_MODE"
    assert row["RMSSD_stable"] == pytest.approx(core.rmssd_consecutive_ms(rr_win, idx_win))
    assert f"t_start_eff={C['WINDOW_START_S']:.1f}s" in row["Notes"]
    assert set(row) <= set(core.COLS_CORE)            # conserva sus salidas


def test_rescate_senala_el_material_insuficiente(tmp_path):
    row, _ = core.compute_day_from_rr_core_only(
        write_rr(tmp_path, [(1000.0, 0)] * 100), C
    )
    assert "RESCUE_MODE" in row["Flags"]
    assert "REC_SHORT" in row["Flags"]
    assert np.isnan(row["RMSSD_stable"])
    assert row["Calidad"] != "OK"


# -------------------------------------------------------- 7. legado no reescribe


def test_el_script_legado_no_puede_reescribir_core(tmp_path):
    script = ROOT / "scripts/python/add_ans_balance_to_core.py"
    if not script.exists():                           # copia parcial del repo
        pytest.skip("script legado no disponible en esta copia")

    rr_dir = tmp_path / "rr_downloads"
    rr_dir.mkdir()
    write_rr(rr_dir, steady(600), "2026-01-05")
    core_path = tmp_path / "ENDURANCE_HRV_master_CORE.csv"
    core_path.write_text(
        ",".join(core.COLS_CORE) + "\n"
        + "2026-01-05,OK,OK,OK,0,60,60,1.0,40,40,0,3.7,,10,20,40,0.5,src=x\n",
        encoding="utf-8",
    )
    antes = core_path.read_bytes()

    run = subprocess.run(
        [sys.executable, str(script), "--rr-dir", str(rr_dir), "--core-csv", str(core_path)],
        capture_output=True, text=True, cwd=str(tmp_path),
    )

    assert run.returncode == 2
    assert core_path.read_bytes() == antes
    assert not list(tmp_path.glob("*.bak_*.csv"))
