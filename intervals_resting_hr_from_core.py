#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sube HR_stable del CORE a restingHR de wellness en intervals.icu.

Uso:
  INTERVALS_API_KEY=... INTERVALS_ATHLETE_ID=... \
    python intervals_resting_hr_from_core.py --date 2025-05-12

  # Rango de fechas (inclusive)
  INTERVALS_API_KEY=... INTERVALS_ATHLETE_ID=... \
    python intervals_resting_hr_from_core.py --from 2025-05-01 --to 2025-05-12

  # Todas las fechas del CSV
  INTERVALS_API_KEY=... INTERVALS_ATHLETE_ID=... \
    python intervals_resting_hr_from_core.py --all

Notas:
- Si la fecha no está en el CSV o HR_stable es vacío, se omite.
- No guarda datos locales; solo envía el payload y muestra el resultado.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, Optional, Tuple

import requests
from requests.auth import _basic_auth_str


DEFAULT_FIELD_ID = "restingHR"
DEFAULT_CSV_NAME = "ENDURANCE_HRV_master_CORE.csv"

# Cargar .env en local si está disponible
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def _default_csv_path() -> str:
    data_dir = (os.environ.get("HRV_DATA_DIR") or "").strip()
    if data_dir:
        return os.path.join(data_dir, DEFAULT_CSV_NAME)
    return DEFAULT_CSV_NAME


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sube HR_stable del CORE a restingHR de wellness en intervals.icu"
    )
    parser.add_argument(
        "--date",
        default=date.today().isoformat(),
        help="Fecha en formato YYYY-MM-DD (default: hoy)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Envía todas las fechas disponibles en el CSV",
    )
    parser.add_argument(
        "--from",
        dest="date_from",
        default="",
        help="Fecha inicio (YYYY-MM-DD) para rango",
    )
    parser.add_argument(
        "--to",
        dest="date_to",
        default="",
        help="Fecha fin (YYYY-MM-DD) para rango",
    )
    parser.add_argument(
        "--csv",
        default=_default_csv_path(),
        help=f"Ruta al {DEFAULT_CSV_NAME} (default: usa HRV_DATA_DIR si aplica)",
    )
    parser.add_argument(
        "--field",
        default=DEFAULT_FIELD_ID,
        help=f"ID del campo de wellness (default: {DEFAULT_FIELD_ID})",
    )
    parser.add_argument(
        "--base-url",
        default=(os.environ.get("INTERVALS_BASE_URL") or "https://intervals.icu"),
        help="Base URL de intervals.icu (default: https://intervals.icu)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="No envía requests; solo imprime el payload",
    )
    parser.add_argument(
        "--api-key",
        default="",
        help="API key de intervals.icu (si no se pasa, usa INTERVALS_API_KEY)",
    )
    parser.add_argument(
        "--athlete-id",
        default="",
        help="Athlete ID de intervals.icu (si no se pasa, usa INTERVALS_ATHLETE_ID)",
    )
    parser.add_argument(
        "--auth-mode",
        default="basic",
        choices=["bearer", "api-key", "basic"],
        help=(
            "Modo de auth: bearer (Authorization: Bearer), api-key (X-API-Key) "
            "o basic (HTTP Basic con api_key como usuario)"
        ),
    )
    return parser.parse_args()


def _parse_yyyy_mm_dd(value: str) -> Optional[date]:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _iter_dates(date_from: date, date_to: date) -> Iterable[date]:
    current = date_from
    while current <= date_to:
        yield current
        current = current + timedelta(days=1)


def _resolve_columns(fieldnames: Iterable[str]) -> Tuple[str, str]:
    lower_map = {name.lower(): name for name in fieldnames}
    date_key = lower_map.get("fecha") or lower_map.get("date")
    hr_key = lower_map.get("hr_stable") or lower_map.get("hrstable")
    if not date_key or not hr_key:
        raise KeyError(
            "No se encontraron columnas requeridas (Fecha y HR_stable) en el CSV"
        )
    return date_key, hr_key


def _load_hr_stable_by_date(csv_path: str) -> Dict[str, float]:
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"No se encontró CSV: {csv_path}")

    values: Dict[str, float] = {}
    with open(csv_path, "r", encoding="utf-8", newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        if not reader.fieldnames:
            return values
        date_key, hr_key = _resolve_columns(reader.fieldnames)
        for row in reader:
            raw_date = (row.get(date_key) or "").strip()
            parsed = _parse_yyyy_mm_dd(raw_date)
            if not parsed:
                continue
            raw_hr = (row.get(hr_key) or "").strip()
            if not raw_hr:
                continue
            try:
                hr_value = float(raw_hr)
            except ValueError:
                continue
            values[parsed.isoformat()] = hr_value
    return values


def _build_headers(api_key: str, auth_mode: str) -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if auth_mode == "api-key":
        headers["X-API-Key"] = api_key
    elif auth_mode == "basic":
        headers["Authorization"] = _basic_auth_str("API_KEY", api_key)
    else:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _normalize_base_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/api/v1"):
        return base
    return base + "/api/v1"


def _send_wellness(
    base_url: str,
    athlete_id: str,
    headers: Dict[str, str],
    field_id: str,
    target_date: str,
    hr_value: float,
    dry_run: bool,
) -> bool:
    payload: Dict[str, Any] = {field_id: hr_value}
    api_root = _normalize_base_url(base_url)
    url = f"{api_root}/athlete/{athlete_id}/wellness/{target_date}"

    if dry_run:
        print("DRY RUN")
        print(f"PUT {url}")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return True

    try:
        response = requests.put(url, headers=headers, json=payload, timeout=30)
    except requests.RequestException as exc:
        print(f"❌ Error de red para {target_date}: {exc}")
        return False

    if response.ok:
        print(f"✅ Wellness actualizado para {target_date}")
        return True

    print(f"⚠️  Error {response.status_code} para {target_date}")
    try:
        print(response.json())
    except ValueError:
        print(response.text)
    return False


def main() -> int:
    args = parse_args()
    api_key = (args.api_key or os.environ.get("INTERVALS_API_KEY") or "").strip()
    athlete_id = (args.athlete_id or os.environ.get("INTERVALS_ATHLETE_ID") or "").strip()

    if not api_key or not athlete_id:
        print("❌ Faltan variables de entorno INTERVALS_API_KEY o INTERVALS_ATHLETE_ID")
        return 1

    if args.all:
        if args.date_from or args.date_to:
            print("❌ Usa --all sin combinar con --from/--to")
            return 1
        targets = []
    elif args.date_from or args.date_to:
        if not args.date_from or not args.date_to:
            print("❌ Para rango, usa --from y --to juntos")
            return 1
        start = _parse_yyyy_mm_dd(args.date_from)
        end = _parse_yyyy_mm_dd(args.date_to)
        if not start or not end:
            print("❌ Fechas inválidas en --from/--to (YYYY-MM-DD)")
            return 1
        if end < start:
            print("❌ El rango es inválido: --to es anterior a --from")
            return 1
        targets = [d.isoformat() for d in _iter_dates(start, end)]
    else:
        single = _parse_yyyy_mm_dd(args.date)
        if not single:
            print("❌ Fecha inválida en --date (YYYY-MM-DD)")
            return 1
        targets = [single.isoformat()]

    try:
        hr_by_date = _load_hr_stable_by_date(args.csv)
    except (FileNotFoundError, KeyError) as exc:
        print(f"❌ {exc}")
        return 1

    headers = _build_headers(api_key, args.auth_mode)

    if args.all:
        targets = sorted(hr_by_date.keys())
        if not targets:
            print("⏭️  El CSV no tiene fechas válidas")
            return 0
    any_sent = False
    any_failed = False
    for target in targets:
        hr_value = hr_by_date.get(target)
        if hr_value is None:
            print(f"⏭️  {target}: sin HR_stable en el CSV, se omite")
            continue
        any_sent = True
        ok = _send_wellness(
            args.base_url,
            athlete_id,
            headers,
            args.field,
            target,
            hr_value,
            args.dry_run,
        )
        if not ok:
            any_failed = True

    if not any_sent:
        print("⏭️  No hay fechas con HR_stable para enviar")
        return 0

    return 1 if any_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
