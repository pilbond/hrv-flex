"""HG-10: propagación a FINAL de la Calidad producida por la geometría candidata.

Comprueba que las salidas seguras de CORE (sin RMSSD utilizable) y la exclusión
de `LAT_NAN` / `STAB_LAST2_MISMATCH` decidida en HG-09 §9 siguen llegando a las
referencias (roll-3, base60), al gate y a la acción.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import build_hrv_core as core
import build_hrv_final_dashboard as final

DIA = 76  # día VERDE / INTENSIDAD_OK de la serie base, con base60 completa


def serie_base(n: int = 80) -> list[dict]:
    """Serie sintética reproducible con variación suficiente para mover el gate."""
    rng = np.random.default_rng(7)
    fechas = pd.date_range("2026-01-01", periods=n, freq="D").strftime("%Y-%m-%d")
    rmssd = 50.0 * np.exp(rng.normal(0, 0.08, n))
    hr = 55.0 + rng.normal(0, 1.5, n)
    return [
        {
            "Fecha": f,
            "Calidad": "OK",
            "HRV_Stability": "OK",
            "Stability_Subtype": "OK",
            "Artifact_pct": 1.0,
            "rejected_rr_pct_window": 1.0,
            "Tiempo_Estabilizacion": 90.0,
            "HR_stable": float(h),
            "RRbar_s": 60.0 / float(h),
            "RMSSD_stable": float(r),
            "RMSSD_stable_last2": float(r),
            "tail_mismatch_pct": 1.0,
            "lnRMSSD": float(np.log(r)),
            "Flags": "",
            "SI_baevsky": 50.0,
            "SD1": 35.0,
            "SD2": 70.0,
            "SD1_SD2_ratio": 0.5,
            "Notes": "",
        }
        for f, r, h in zip(fechas, rmssd, hr)
    ]


def run(filas: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(filas)[core.COLS_CORE]
    f, _ = final.build_final_and_dashboard(df, final.CFG)
    return f


def test_dia_limpio_de_referencia_conserva_gate_y_accion():
    f = run(serie_base())
    fila = f.iloc[DIA]
    assert bool(fila["quality_flag"]) is False
    assert fila["Color_operativo"] == "VERDE"
    assert fila["Action"] == "INTENSIDAD_OK"
    assert int(fila["n_base60"]) == 60


@pytest.mark.parametrize(
    "flags, subtipo, estabilidad, latencia",
    [
        ("LAT_NAN", "OK", "OK", np.nan),
        ("STAB_LAST2_MISMATCH", "STAB_LAST2_MISMATCH", "Unstable", 90.0),
        ("LAT_NAN|STAB_LAST2_MISMATCH", "STAB_LAST2_MISMATCH", "Unstable", np.nan),
    ],
)
def test_lat_nan_y_mismatch_excluyen_de_referencias_y_fuerzan_cautela(
    flags, subtipo, estabilidad, latencia
):
    limpio = run(serie_base())
    filas = serie_base()
    filas[DIA].update(
        Calidad="FLAG_mecánico",
        Flags=flags,
        HRV_Stability=estabilidad,
        Stability_Subtype=subtipo,
        Tiempo_Estabilizacion=latencia,
    )
    marcado = run(filas)

    fila = marcado.iloc[DIA]
    # El valor diario no cambia: solo cambia la elegibilidad y la cautela.
    assert fila["RMSSD_stable"] == pytest.approx(limpio.iloc[DIA]["RMSSD_stable"])
    assert bool(fila["quality_flag"]) is True
    assert fila["Action"] == "SUAVE_O_DESCANSO"
    assert fila["Action_detail"] == "SUAVE_QUALITY"

    # Arrastre: el día deja de contar como observación limpia de los siguientes.
    assert int(marcado.iloc[DIA + 1]["n_base60"]) == int(limpio.iloc[DIA + 1]["n_base60"]) - 1
    assert marcado.iloc[DIA + 1]["lnRMSSD_used"] != pytest.approx(
        limpio.iloc[DIA + 1]["lnRMSSD_used"]
    )


def test_dia_sin_rmssd_utilizable_sale_de_las_referencias():
    limpio = run(serie_base())
    filas = serie_base()
    # Salida segura HG-10: tramo sin pares consecutivos -> sin RMSSD publicable.
    filas[DIA].update(
        Calidad="FLAG_mecánico",
        Flags="WIN_NO_PAIRS",
        RMSSD_stable=np.nan,
        RMSSD_stable_last2=np.nan,
        lnRMSSD=np.nan,
        tail_mismatch_pct=np.nan,
    )
    marcado = run(filas)

    fila = marcado.iloc[DIA]
    # Sin valor numérico el día es INVALID para FINAL: no es un día utilizable.
    assert bool(fila["quality_flag"]) is False
    assert fila["Color_operativo"] == "NO"      # gate sin valor: no decide color
    assert fila["Action"] == "SUAVE_O_DESCANSO"
    assert int(marcado.iloc[DIA + 1]["n_base60"]) == int(limpio.iloc[DIA + 1]["n_base60"]) - 1
