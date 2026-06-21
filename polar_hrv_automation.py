#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
POLAR HRV AUTOMATION - Railway/Render Compatible
=================================================
Funciona con .env (local) O variables de entorno (Railway/Render)

Uso:
    python polar_hrv_automation.py --auth         # Primera vez
    python polar_hrv_automation.py                # Después (desde última fecha CORE; si CORE está vacío, reintenta RR locales y luego últimos 7 días)
    python polar_hrv_automation.py --days 30      # Últimos 30 días
    python polar_hrv_automation.py --all          # Reprocesa RR ya descargados localmente (sin descargar nada nuevo)
    python polar_hrv_automation.py --process      # + ejecutar build_hrv_core.py + build_hrv_final_dashboard.py
"""

import sys
import argparse
from hrv_app.config import (
    IS_PRODUCTION,
    get_production_url,
)
from hrv_app.pipeline_runner import (
    run_build_hrv_ssm_outcome_battery_only,
    run_build_hrv_ssm_shadow_only,
    run_build_hrv_ssm_validation_only,
)
from hrv_app.hrv_sync_flow import sync_hrv_range
from hrv_app.backup_dropbox import auto_restore_if_empty, run_backup as run_dropbox_backup


def _configure_stdio() -> None:
    """Evita fallos por caracteres no representables en consolas Windows legacy."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None or not hasattr(stream, "reconfigure"):
            continue
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            continue


def run_ssm_audit() -> int:
    """Ejecuta manualmente la auditoría SSM completa sobre los datos actuales."""
    print("[RUN] Ejecutando build_hrv_ssm.py...")
    if not run_build_hrv_ssm_shadow_only():
        print("[ERROR] Falló build_hrv_ssm.py; no se ejecuta la auditoría SSM.", file=sys.stderr)
        return 1

    print("[RUN] Ejecutando build_hrv_ssm_validation.py...")
    if not run_build_hrv_ssm_validation_only():
        print("[ERROR] Falló build_hrv_ssm_validation.py; no se ejecuta la batería de outcomes.", file=sys.stderr)
        return 1

    print("[RUN] Ejecutando build_hrv_ssm_outcome_battery.py...")
    if not run_build_hrv_ssm_outcome_battery_only():
        print("[ERROR] Falló build_hrv_ssm_outcome_battery.py.", file=sys.stderr)
        return 1

    print("[OK] Auditoria SSM completada")
    return 0


def _debug_sports_v4() -> None:
    """Muestra deportes de las sesiones v4 de los últimos 7 días (diagnóstico)."""
    from datetime import date, timedelta
    from hrv_app.polar_client_v4 import V4Client, PolarV4Error

    today = date.today().isoformat()
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    client = V4Client()
    try:
        sessions = client.list_training_sessions(date_from=week_ago, date_to=today)
    except PolarV4Error as exc:
        print(f"❌ No se pudo obtener sesiones v4: {exc}", file=sys.stderr)
        return

    if not sessions:
        print(f"No hay sesiones v4 en los últimos 7 días ({week_ago} – {today}).")
        return

    print(f"Sesiones v4 ({week_ago} – {today}):")
    for s in sessions:
        start = s.get("startTime") or s.get("start_time") or "?"
        sport = s.get("sport") or {}
        sport_id = sport.get("id") if isinstance(sport, dict) else sport
        dur_ms = s.get("durationMillis") or 0
        dur_min = round(dur_ms / 60000) if dur_ms else "?"
        print(f"  {start}  sport_id={sport_id}  duration={dur_min} min")


def main():
    _configure_stdio()
    parser = argparse.ArgumentParser(description='Polar HRV Automation')
    parser.add_argument('--auth', action='store_true', help='Forzar re-autenticación')
    parser.add_argument('--days', type=int, help='Días hacia atrás (ignora --auto)')
    parser.add_argument('--all', action='store_true', help='Reprocesa RR ya existentes en rr_downloads/, sin descargar nada nuevo (ignora --days y --auto)')
    parser.add_argument('--auto', action='store_true', help='Detectar automáticamente días faltantes desde último registro')
    parser.add_argument('--process', action='store_true', help='Ejecutar build_hrv_core.py + build_hrv_final_dashboard.py después')
    parser.add_argument('--ssm-audit', action='store_true', help='Ejecutar manualmente SSM shadow + validación + outcome battery')
    parser.add_argument('--debug-sports', action='store_true', help='Mostrar deportes de todas las sesiones encontradas')
    parser.add_argument('--verbose', action='store_true', help='Mostrar detalles de cada archivo procesado')
    args = parser.parse_args()

    if args.ssm_audit:
        incompatible = [
            flag
            for enabled, flag in [
                (args.auth, "--auth"),
                (args.days is not None, "--days"),
                (args.all, "--all"),
                (args.auto, "--auto"),
                (args.process, "--process"),
                (args.debug_sports, "--debug-sports"),
                (args.verbose, "--verbose"),
            ]
            if enabled
        ]
        if incompatible:
            parser.error(f"--ssm-audit no se puede combinar con: {', '.join(incompatible)}")
        return run_ssm_audit()

    # _print_header("  POLAR HRV AUTOMATION")

    if args.debug_sports:
        _debug_sports_v4()
        return 0
    if args.auth:
        public_url = get_production_url()
        hint = f"{public_url.rstrip('/')}/auth" if public_url else "/auth"
        print(f"❌ --auth no aplica con v4. Autoriza vía {hint}.", file=sys.stderr)
        sys.exit(3)

    try:
        auto_restore_if_empty()
    except RuntimeError as exc:
        print(f"❌ Auto-restore falló: {exc}", file=sys.stderr)
        return 1

    sync_hrv_range(args, None, None, [])

    # Backup opcional del histórico fuera del volumen (opt-in, nunca rompe el sync)
    run_dropbox_backup()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nInterrumpido por el usuario.")
    except Exception as e:
        print(f"\n❌ ERROR INESPERADO: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


