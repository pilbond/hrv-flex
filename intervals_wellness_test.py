#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test local de subida de wellness a intervals.icu.

Uso:
  INTERVALS_API_KEY=... INTERVALS_ATHLETE_ID=... \
    python intervals_wellness_test.py --date 2024-01-30 --field colorTest --value Verde

Notas:
- Usa PUT /api/v1/athlete/{id}/wellness/{date}
- No guarda datos locales; solo envía el payload y muestra la respuesta.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date
from typing import Any, Dict, Optional

import requests
from requests.auth import _basic_auth_str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test de wellness en intervals.icu")
    parser.add_argument(
        "--date",
        default=date.today().isoformat(),
        help="Fecha en formato YYYY-MM-DD (default: hoy)",
    )
    parser.add_argument(
        "--field",
        default="colorTest",
        help="ID del campo custom de wellness (default: colorTest)",
    )
    parser.add_argument(
        "--value",
        default="",
        help="Valor a enviar para el campo indicado",
    )
    parser.add_argument(
        "--base-url",
        default="https://intervals.icu",
        help="Base URL de intervals.icu (default: https://intervals.icu)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="No envía request; solo imprime el payload",
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
        default="bearer",
        choices=["bearer", "api-key", "basic"],
        help=(
            "Modo de auth: bearer (Authorization: Bearer), api-key (X-API-Key) "
            "o basic (HTTP Basic con api_key como usuario)"
        ),
    )
    return parser.parse_args()


def build_payload(field_id: str, value: str) -> Dict[str, Any]:
    """
    Construye el payload para wellness.

    Nota: intervals.icu espera valores en el objeto de wellness. Para campos
    custom, se usa el ID del campo como clave.
    """
    return {field_id: value}


def main() -> int:
    args = parse_args()
    api_key = (args.api_key or os.environ.get("INTERVALS_API_KEY") or "").strip()
    athlete_id = (args.athlete_id or os.environ.get("INTERVALS_ATHLETE_ID") or "").strip()

    if not api_key or not athlete_id:
        print("❌ Faltan variables de entorno INTERVALS_API_KEY o INTERVALS_ATHLETE_ID")
        return 1

    payload = build_payload(args.field, args.value)
    url = f"{args.base_url.rstrip('/')}/api/v1/athlete/{athlete_id}/wellness/{args.date}"
    headers = {"Content-Type": "application/json"}
    auth_header: Optional[str] = None
    if args.auth_mode == "api-key":
        headers["X-API-Key"] = api_key
    elif args.auth_mode == "basic":
        auth_header = _basic_auth_str("API_KEY", api_key)
    else:
        headers["Authorization"] = f"Bearer {api_key}"
    if auth_header:
        headers["Authorization"] = auth_header

    if args.dry_run:
        print("DRY RUN")
        print(f"PUT {url}")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    try:
        response = requests.put(url, headers=headers, json=payload, timeout=30)
    except requests.RequestException as exc:
        print(f"❌ Error de red: {exc}")
        return 1

    print(f"Status: {response.status_code}")
    if response.headers.get("content-type", "").startswith("application/json"):
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    else:
        print(response.text)

    return 0 if response.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
