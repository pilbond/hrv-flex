"""Rellena las valoraciones de Nightly Recharge en filas ya guardadas de sleep.csv.

El sync diario solo vuelve a consultar Polar para su ventana de reproceso, así
que las fechas antiguas de `ENDURANCE_HRV_sleep.csv` se quedan sin las 9
columnas de valoraciones (`polar_recharge_status` ... `polar_night_rri_baseline_sd`).
Este script las recupera de Polar AccessLink v4, fecha a fecha.

Garantías:
- Solo escribe las columnas de valoraciones; el resto de cada fila se conserva
  (merge de `upsert_sleep_row`). No crea ni borra filas.
- Copia previa en `<DATA_DIR>/backup/pre_nightly_ratings/` antes de escribir.
- Idempotente: por defecto solo consulta fechas con datos Polar a las que les
  falta alguna de las tres valoraciones principales (Nightly Recharge, estado
  del SNA o carga de sueño). Las valoraciones ya guardadas no se borran si un
  reintento trae menos campos.
- No imprime tokens ni identificadores. Usa el token v4 de `POLAR_TOKEN_PATH_V4`
  (o el valor por defecto de `hrv_app.config`), que puede rotar al refrescarse.

No debe ejecutarse mientras corre un sync de la UI: sleep.csv es estado compartido.

Uso:
    python scripts/backfill_polar_nightly_ratings.py --dry-run
    python scripts/backfill_polar_nightly_ratings.py
    python scripts/backfill_polar_nightly_ratings.py --since 2026-01-01 --all-dates

En Railway, dentro del contenedor (`railway ssh`), con las mismas variables del
servicio: `python scripts/backfill_polar_nightly_ratings.py`.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from hrv_app import config  # noqa: E402
import hrv_app.sleep_store as store  # noqa: E402
from hrv_app.polar_adapters_v4 import (  # noqa: E402
    NIGHTLY_FEATURES,
    SLEEP_FEATURES,
    index_by_date,
    v4_nightly_to_internal,
    v4_sleep_to_internal,
)
from hrv_app.polar_client_v4 import PolarV4Error, V4Client  # noqa: E402

RATING_COLUMNS = [c for c in store.SLEEP_COLUMNS if c not in store.SLEEP_LEGACY_COLUMNS]
MAIN_RATING_COLUMNS = ["polar_recharge_status", "polar_ans_charge_status", "polar_sleep_charge_status"]


def candidate_dates(df: pd.DataFrame, since: date | None, all_dates: bool) -> list[str]:
    """Fechas con datos Polar de sueño o Nightly Recharge que conviene consultar."""
    has_polar = pd.Series(False, index=df.index)
    for column in ("polar_night_rmssd", "polar_sleep_score"):
        if column in df.columns:
            has_polar |= df[column].notna()
    mask = has_polar
    if not all_dates:
        missing_any = pd.Series(False, index=df.index)
        for column in MAIN_RATING_COLUMNS:
            missing_any |= df[column].isna() if column in df.columns else True
        mask &= missing_any
    dates = sorted(pd.to_datetime(df.loc[mask, "Fecha"]).dt.date)
    if since is not None:
        dates = [d for d in dates if d >= since]
    return [d.isoformat() for d in dates]


def rating_row(client: V4Client, day: str) -> dict:
    nxt = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
    # Con `features`, la API v4 solo acepta rangos de un día.
    nightly = v4_nightly_to_internal(
        index_by_date(client.fetch_nightly_recharges(day, nxt, features=NIGHTLY_FEATURES)).get(day)
    )
    sleep = v4_sleep_to_internal(index_by_date(client.fetch_sleeps(day, nxt, features=SLEEP_FEATURES)).get(day))
    row = {"Fecha": day}
    row.update({k: v for k, v in store._extract_nightly_fields(nightly).items() if k in RATING_COLUMNS})
    row.update({k: v for k, v in store._extract_sleep_fields(sleep).items() if k in RATING_COLUMNS})
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="Lista las fechas candidatas sin consultar Polar.")
    parser.add_argument("--since", type=date.fromisoformat, help="Solo fechas desde YYYY-MM-DD.")
    parser.add_argument(
        "--all-dates",
        action="store_true",
        help="Vuelve a consultar también las fechas que ya tienen las tres valoraciones principales.",
    )
    args = parser.parse_args(argv)

    path = Path(store.SLEEP_PATH)
    if not path.exists():
        print(f"No existe {path}; nada que rellenar.")
        return 1
    # Un CSV legacy de 17 columnas se amplía al primer upsert.
    df = store._ensure_sleep_schema(pd.read_csv(path))
    dates = candidate_dates(df, args.since, args.all_dates)
    print(f"{path.name}: {len(df)} filas, {len(dates)} fechas candidatas.")
    if dates:
        print(f"Rango: {dates[0]} .. {dates[-1]}")
    if args.dry_run or not dates:
        return 0

    backup_dir = path.parent / "backup" / "pre_nightly_ratings"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"{path.stem}_{datetime.now():%Y%m%d_%H%M%S}.csv"
    shutil.copy2(path, backup)
    print(f"Copia previa: {backup}")

    client = V4Client(bundle_path=config.TOKEN_FILE_V4)
    log: dict[str, list] = {"filled": [], "no_ratings": [], "errors": []}
    for day in dates:
        try:
            row = rating_row(client, day)
        except PolarV4Error as exc:
            log["errors"].append({"date": day, "error": str(exc)[:200]})
            continue
        if len(row) == 1:
            log["no_ratings"].append(day)
            continue
        store.upsert_sleep_row(row)
        log["filled"].append(day)

    log_path = backup_dir / f"backfill_log_{datetime.now():%Y%m%d_%H%M%S}.json"
    log_path.write_text(json.dumps(log, indent=1), encoding="utf-8")
    print({k: len(v) for k, v in log.items()}, f"-> {log_path}")
    print("FINAL y DASHBOARD se regeneran en el próximo sync (POST /api/sync).")
    return 0 if not log["errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
