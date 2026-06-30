from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import List, Optional

import pandas as pd

from .cli_reporting import (
    build_bulleted_report,
    build_debug_session_report,
    build_lines_report,
    build_message_report,
    build_no_rr_matinales_report,
    build_pipeline_stage_report,
    _render_report,
    _print_divider,
    _print_header,
    _print_master_already_updated,
    _print_no_local_rr_files,
    _print_sync_completed,
    build_sync_completed_report,
    show_latest_hrv_summaries,
)
from .ai import run_ai_daily_brief_for_latest_date
from .config import (
    CORE_PATH,
    FIELD_SAMPLE_TYPE,
    FIELD_SPORT,
    FIELD_START_TIME,
    INTERVALS_SOURCE_PATH,
    OUTDIR,
    PANDAS_AVAILABLE,
    QUIET,
    RR_MAX_MS,
    RR_MIN_MS,
    _qprint,
)
from .dropbox_rr import (
    _compute_target_missing_dates,
    _promote_operational_rr_files,
    _run_dropbox_rr_import_for_dates,
    _scan_rr_files_by_date,
)
from .intervals_sync import _send_intervals_wellness_from_master
from .pipeline_runner import (
    run_build_hrv_core,
    run_build_hrv_final_dashboard_only,
    run_build_hrv_ssm_shadow_only,
)
from .polar_utils import _iso_to_dt, get_field_variant
from .sleep_store import _default_sleep_refresh_dates, _update_sleep_for_dates


def _run_ai_daily_brief_best_effort() -> None:
    try:
        result = run_ai_daily_brief_for_latest_date()
    except Exception as exc:
        _render_report(build_message_report(f"🤖 AI daily brief: error ({exc})"))
        return
    status = str(result.get("status") or "").strip()
    if status in {"", "disabled", "missing_final"}:
        return
    date_str = str(result.get("date") or "").strip()
    suffix = f" ({date_str})" if date_str else ""
    _render_report(build_message_report(f"🤖 AI daily brief: {status}{suffix}"))


def extract_rr_ms(exercise_json: dict):
    rr = []
    samples = exercise_json.get("samples") or []
    for s in samples:
        st = get_field_variant(s, *FIELD_SAMPLE_TYPE)
        if str(st) != "11":
            continue

        # Máscara opcional alineada con `data` (extensión del adaptador v4:
        # offline=true de Polar es la primera capa de descarte de artefactos
        # y debe respetarse aunque el RR caiga en rango fisiológico). Los
        # samples v3 no la traen y el comportamiento es el histórico.
        raw_mask = str(s.get("offline") or "")
        mask = [t.strip() for t in raw_mask.split(",")] if raw_mask else []

        data = str(s.get("data", ""))
        for i, tok in enumerate(data.split(",")):
            tok = tok.strip()
            if not tok or tok.upper() == "NULL":
                continue
            try:
                v = float(tok)
            except ValueError:
                continue
            polar_offline = i < len(mask) and mask[i] == "1"
            offline = 1 if polar_offline or not (RR_MIN_MS <= v <= RR_MAX_MS) else 0
            rr.append((v, offline))
    return rr


def write_rr_csv(rr, out_path: str) -> bool:
    try:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("duration,offline\n")
            for v, off in rr:
                f.write(f"{v:.3f},{off}\n")
    except OSError as exc:
        _render_report(build_message_report(f"  ❌ Error escribiendo RR en {out_path}: {exc}"))
        return False
    return True


def get_last_date_from_master():
    master_file = CORE_PATH

    if not master_file.exists() or not PANDAS_AVAILABLE:
        return None

    try:
        df = pd.read_csv(master_file)

        if "Fecha" not in df.columns or df.empty:
            return None

        last_date_str = df["Fecha"].max()
        last_date = datetime.strptime(last_date_str, "%Y-%m-%d").date()
        return last_date
    except (FileNotFoundError, pd.errors.EmptyDataError, ValueError, KeyError) as e:
        _render_report(build_message_report(f"⚠️  Error leyendo CORE: {e}"))
        return None


def get_existing_dates_from_master():
    master_file = CORE_PATH

    if not master_file.exists() or not PANDAS_AVAILABLE:
        return set()

    try:
        df = pd.read_csv(master_file)

        if "Fecha" not in df.columns or df.empty:
            return set()

        dates = set()
        for date_str in df["Fecha"]:
            try:
                date_obj = datetime.strptime(str(date_str), "%Y-%m-%d").date()
                dates.add(date_obj)
            except (ValueError, TypeError):
                pass

        return dates
    except (FileNotFoundError, pd.errors.EmptyDataError, KeyError) as e:
        _render_report(build_message_report(f"⚠️  Error leyendo fechas del CORE: {e}"))
        return set()


def calculate_missing_days(last_date=None):
    if last_date is None:
        last_date = get_last_date_from_master()
    today = datetime.now().date()

    if last_date is None:
        return 7, None

    days_missing = (today - last_date).days
    if days_missing <= 0:
        return 0, last_date

    return days_missing, last_date


def _refresh_sleep_and_outputs(
    access_token: str,
    x_user_id: Optional[str],
    run_final_dashboard: bool = False,
    dates: Optional[List] = None,
) -> None:
    target_dates = dates if dates is not None else _default_sleep_refresh_dates()
    _update_sleep_for_dates(access_token, x_user_id, target_dates)
    if run_final_dashboard:
        _render_report(build_message_report("▶️  Regenerando FINAL/DASHBOARD con sleep actualizado..."))
        final_ok = run_build_hrv_final_dashboard_only()
        if final_ok:
            _run_ai_daily_brief_best_effort()


def _resolve_date_range(args, last_date=None):
    if args.days is not None:
        to_d = datetime.now().date()
        from_d = (datetime.now() - timedelta(days=args.days)).date()
        _render_report(build_message_report(f"📅 Últimos {args.days} días: {from_d} → {to_d}"))
        return from_d, to_d, None, None

    days_missing, last_date = calculate_missing_days(last_date=last_date)
    if days_missing == 0:
        return None, None, last_date, "no_missing"

    to_d = datetime.now().date()
    if last_date:
        from_d = last_date + timedelta(days=1)
        _render_report(build_lines_report([
            f"📅 Última medición: {last_date}",
            f"   Cubriendo desde {from_d} hasta {to_d} ({days_missing} días)",
        ]))
    else:
        from_d = (datetime.now() - timedelta(days=days_missing)).date()
        _render_report(build_message_report(f"📅 Master sin datos, cubriendo últimos {days_missing} días"))
    return from_d, to_d, last_date, None


def _process_rr_files(
    rr_files: List,
    pre_process_dates: set,
    access_token: str,
    x_user_id: Optional[str],
    args,
) -> None:
    """Ejecuta el pipeline HRV (CORE -> sleep -> FINAL/DASHBOARD -> SSM) para `rr_files`."""
    if not args.process:
        _send_intervals_wellness_from_master(INTERVALS_SOURCE_PATH)
        show_latest_hrv_summaries()
        return

    _print_header("🔧 PROCESANDO PIPELINE HRV")
    _render_report(build_pipeline_stage_report("Ejecutando build_hrv_core.py..."))
    result = run_build_hrv_core(rr_files)
    if result is None:
        _render_report(build_message_report("⚠️  build_hrv_core.py falló; se actualiza sleep.csv, pero no se regenera FINAL/DASHBOARD."))
        _refresh_sleep_and_outputs(access_token, x_user_id, run_final_dashboard=False)
        _send_intervals_wellness_from_master(INTERVALS_SOURCE_PATH)
        show_latest_hrv_summaries()
        return

    if result.stdout:
        stdout_lines = [line for line in result.stdout.splitlines() if line != ""]
        if stdout_lines:
            _render_report(build_lines_report(stdout_lines))

    promoted = _promote_operational_rr_files(rr_files, OUTDIR)
    if promoted:
        _render_report(build_message_report(f"☁️  RR operativos promovidos: {promoted}"))

    post_process_dates = get_existing_dates_from_master() if PANDAS_AVAILABLE else set()
    new_dates = sorted(post_process_dates - pre_process_dates) if PANDAS_AVAILABLE else []
    if new_dates:
        merged_dates = set(new_dates)
        merged_dates.update(_default_sleep_refresh_dates())
        target_dates = sorted(merged_dates)
    else:
        target_dates = _default_sleep_refresh_dates()
    _render_report(build_pipeline_stage_report(f"Actualizando sleep.csv ({len(target_dates)} fecha(s))..."))
    _update_sleep_for_dates(access_token, x_user_id, target_dates)

    _render_report(build_pipeline_stage_report("Ejecutando build_hrv_final_dashboard.py..."))
    final_ok = run_build_hrv_final_dashboard_only()

    _render_report(build_pipeline_stage_report("Ejecutando build_hrv_ssm.py..."))
    ssm_ok = run_build_hrv_ssm_shadow_only()
    if not ssm_ok:
        _render_report(build_message_report("⚠️  build_hrv_ssm.py falló; FINAL/DASHBOARD se mantienen actualizados, pero no se regenera SSM shadow."))

    if final_ok:
        _run_ai_daily_brief_best_effort()

    if not QUIET:
        _render_report(
            build_sync_completed_report()
        )
        _render_report(
            build_bulleted_report(
                "📄 Archivos actualizados:",
                [
                    "ENDURANCE_HRV_master_CORE.csv",
                    "ENDURANCE_HRV_master_BETA_AUDIT.csv",
                    "ENDURANCE_HRV_master_CORE_manifest.json",
                    "ENDURANCE_HRV_master_FINAL.csv",
                    "ENDURANCE_HRV_master_DASHBOARD.csv",
                    "ENDURANCE_HRV_master_FINAL_manifest.json",
                    "ENDURANCE_HRV_ssm_shadow.csv",
                ],
            )
        )
    _send_intervals_wellness_from_master(INTERVALS_SOURCE_PATH)
    show_latest_hrv_summaries()


def sync_hrv_range(args, access_token: str, x_user_id: Optional[str], exercises: list) -> None:
    if args.debug_sports:
        _print_header("🔍 DEBUG: TODAS LAS SESIONES ENCONTRADAS")
        for i, e in enumerate(exercises):
            st = get_field_variant(e, *FIELD_START_TIME, default="N/A")
            sport = get_field_variant(e, *FIELD_SPORT, default="N/A")
            duration = e.get("duration", "N/A")
            dt = _iso_to_dt(st)
            date_str = dt.strftime("%Y-%m-%d") if dt else "N/A"
            _render_report(build_debug_session_report(i, date_str, sport, duration))
        _print_divider(trailing_blank=True)

    if args.all:
        _render_report(build_message_report("📅 Reprocesando TODOS los RR locales (sin descargas nuevas)"))
        rr_map = _scan_rr_files_by_date(OUTDIR)
        rr_files = list(rr_map.values())
        pre_process_dates = get_existing_dates_from_master()

        if not rr_files:
            _print_no_local_rr_files()
            _refresh_sleep_and_outputs(access_token, x_user_id, run_final_dashboard=args.process)
            _send_intervals_wellness_from_master(INTERVALS_SOURCE_PATH)
            show_latest_hrv_summaries()
            return

        _render_report(build_message_report(f"📊 {len(rr_files)} archivo(s) RR locales para reprocesar en {OUTDIR}/", leading_blank=True))
        _process_rr_files(rr_files, pre_process_dates, access_token, x_user_id, args)
        return

    last_date = get_last_date_from_master()
    if last_date is None:
        rr_map = _scan_rr_files_by_date(OUTDIR)
        rr_files = list(rr_map.values())
        if rr_files:
            _render_report(build_message_report(f"📅 CORE vacío: reprocesando {len(rr_files)} archivo(s) RR locales en {OUTDIR}/"))
            pre_process_dates = set()
            _process_rr_files(rr_files, pre_process_dates, access_token, x_user_id, args)
            return

    from_d, to_d, last_date, exit_mode = _resolve_date_range(args, last_date=last_date)
    if exit_mode == "no_missing":
        if args.process:
            _render_report(build_message_report("▶️  Sin RR nuevos: actualizando sleep.csv (hoy)..."))
            _refresh_sleep_and_outputs(access_token, x_user_id, run_final_dashboard=True)
        _send_intervals_wellness_from_master(INTERVALS_SOURCE_PATH)
        _print_sync_completed(updated_date=last_date)
        show_latest_hrv_summaries()
        _print_divider(trailing_blank=True)
        return

    existing_dates = get_existing_dates_from_master()
    pre_process_dates = set(existing_dates)
    target_missing_dates = _compute_target_missing_dates(from_d, to_d, existing_dates)

    if not target_missing_dates:
        _print_master_already_updated()
        _refresh_sleep_and_outputs(access_token, x_user_id, run_final_dashboard=args.process)
        _send_intervals_wellness_from_master(INTERVALS_SOURCE_PATH)
        show_latest_hrv_summaries()
        return

    dropbox_rr_map, dropbox_rr_new = _run_dropbox_rr_import_for_dates(
        target_missing_dates,
        OUTDIR,
        verbose=args.verbose,
    )
    if dropbox_rr_map:
        reused = max(len(dropbox_rr_map) - dropbox_rr_new, 0)
        _render_report(build_message_report(f"☁️  Dropbox RR: {len(dropbox_rr_map)} fecha(s) cubierta(s) ({dropbox_rr_new} nuevas, {reused} ya existentes)"))

    rr_files = [path for _, path in sorted(dropbox_rr_map.items())]

    if not rr_files:
        if QUIET:
            _render_report(build_message_report("⚠️  No hay RR matinales disponibles para el periodo objetivo"))
        else:
            _render_report(build_no_rr_matinales_report(from_d, to_d))
        _refresh_sleep_and_outputs(access_token, x_user_id, run_final_dashboard=args.process)
        _send_intervals_wellness_from_master(INTERVALS_SOURCE_PATH)
        show_latest_hrv_summaries()
        return

    _render_report(build_message_report(f"📊 {len(rr_files)} archivo(s) RR desde Dropbox para procesar en {OUTDIR}/", leading_blank=True))
    _process_rr_files(rr_files, pre_process_dates, access_token, x_user_id, args)
