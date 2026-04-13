#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
POLAR HRV AUTOMATION - Railway/Render Compatible
=================================================
Funciona con .env (local) O variables de entorno (Railway/Render)

Uso:
    python polar_hrv_automation.py --auth         # Primera vez
    python polar_hrv_automation.py                # Después (últimos 7 días)
    python polar_hrv_automation.py --days 30      # Últimos 30 días
    python polar_hrv_automation.py --all          # Todas las sesiones
    python polar_hrv_automation.py --process      # + ejecutar build_hrv_core.py + build_hrv_final_dashboard.py
"""

import sys
import argparse
from config import (
    IS_PRODUCTION,
    get_production_url,
)
from polar_client import (
    list_exercises,
    register_user_if_needed,
)
from polar_oauth_local import do_oauth_flow, load_tokens
from hrv_sync_flow import sync_hrv_range

def main():
    parser = argparse.ArgumentParser(description='Polar HRV Automation')
    parser.add_argument('--auth', action='store_true', help='Forzar re-autenticación')
    parser.add_argument('--days', type=int, help='Días hacia atrás (ignora --auto)')
    parser.add_argument('--all', action='store_true', help='Todas las sesiones (ignora --days y --auto)')
    parser.add_argument('--auto', action='store_true', help='Detectar automáticamente días faltantes desde último registro')
    parser.add_argument('--process', action='store_true', help='Ejecutar build_hrv_core.py + build_hrv_final_dashboard.py después')
    parser.add_argument('--debug-sports', action='store_true', help='Mostrar deportes de todas las sesiones encontradas')
    parser.add_argument('--verbose', action='store_true', help='Mostrar detalles de cada archivo procesado')
    args = parser.parse_args()

    # _print_header("  POLAR HRV AUTOMATION")

    # Autenticación
    # En PRODUCCIÓN (Railway/Render/Heroku) NO se puede abrir navegador ni levantar callback server local.
    # La autorización debe hacerse vía Web UI: /auth -> /auth/callback, que guarda TOKEN_FILE.
    if args.auth:
        if IS_PRODUCTION:
            public_url = get_production_url()
            hint = f"{public_url.rstrip('/')}/auth" if public_url else "/auth"
            print(f"❌ En producción no se admite --auth interactivo. Abre {hint} para autorizar.", file=sys.stderr)
            sys.exit(3)
        access_token, x_user_id = do_oauth_flow()
    else:
        access_token, x_user_id = load_tokens()
        if not access_token:
            if IS_PRODUCTION:
                public_url = get_production_url()
                hint = f"{public_url.rstrip('/')}/auth" if public_url else "/auth"
                print(f"❌ Falta autorización. Abre {hint} para iniciar sesión en Polar y autorizar la app.", file=sys.stderr)
                sys.exit(3)
            print("⚠️  Token ausente/expirado, iniciando OAuth local...")
            access_token, x_user_id = do_oauth_flow()

    # Registrar usuario (obligatorio)
    member_id = f"local_{x_user_id or 'user'}"
    reg = register_user_if_needed(access_token, member_id, allow_transient_failure=True)
    if reg.get("status") == "temporary_failure":
        print("⚠️  Registro Polar no confirmado por error temporal del servicio. Continuando con la sync.")
    # print(f"📝 Usuario: {reg.get('status')}")

    # Listar ejercicios
    # print("\n🔍 Obteniendo ejercicios...")
    exercises = list_exercises(access_token)

    if not isinstance(exercises, list):
        raise RuntimeError(f"Respuesta inesperada: {type(exercises)}")
    sync_hrv_range(args, access_token, x_user_id, exercises)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrumpido por el usuario.")
    except Exception as e:
        print(f"\n❌ ERROR INESPERADO: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


