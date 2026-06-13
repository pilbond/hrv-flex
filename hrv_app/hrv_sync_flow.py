from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd
import requests

from .cli_reporting import (
    _print_divider,
    _print_header,
    _print_master_already_updated,
    _print_no_rr_files,
    _print_sync_completed,
    show_latest_hrv_summaries,
)
from .config import (
    DEBUG_PREVIEW_LIMIT,
    DROPBOX_RR_ENABLED,
    FIELD_SAMPLE_TYPE,
    FIELD_SPORT,
    FIELD_START_TIME,
    CORE_PATH,
    INTERVALS_SOURCE_PATH,
    MAX_AUTO_DAYS,
    MAX_DURATION_MINUTES,
    MAX_EXERCISES,
    OUTDIR,
    PANDAS_AVAILABLE,
    POLAR_USER_NAME,
    QUIET,
    RR_MAX_MS,
    RR_MIN_MS,
    SPORTS_FILTER,
    UNKNOWN_SESSION_ID,
    _qprint,
)
from .dropbox_rr import _compute_target_missing_dates, _run_dropbox_rr_import_for_dates
from .intervals_sync import _send_intervals_wellness_from_master
from .pipeline_runner import (
    build_hrv_core_cmd,
    run_build_hrv_core,
    run_build_hrv_final_dashboard_only,
    run_build_hrv_ssm_shadow_only,
)
from .polar_client import get_exercise_with_samples
from .polar_utils import _iso_to_dt, get_field_variant, parse_duration_to_minutes
from .sleep_store import _default_sleep_refresh_dates, _update_sleep_for_dates


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
        print(f"  ❌ Error escribiendo RR en {out_path}: {exc}")
        return False
    return True


def passes_filters(ex_item: dict, from_d, to_d, sports_set, max_duration_min, debug=False):
    if debug:
        print(f"\n  🔍 Evaluando: {ex_item.get('id', 'N/A')}")

    st = get_field_variant(ex_item, *FIELD_START_TIME)
    dt = _iso_to_dt(st)
    if dt:
        d = dt.date()
        if debug:
            print(f"     Fecha: {d} | Rango: {from_d} a {to_d}")

        if from_d and d < from_d:
            if debug:
                print(f"     ❌ Fecha < from_d ({d} < {from_d})")
            return False
        if to_d and d > to_d:
            if debug:
                print(f"     ❌ Fecha > to_d ({d} > {to_d})")
            return False

        if debug:
            print("     ✅ Fecha OK")
    else:
        if debug:
            print(f"     ⚠️  Sin fecha parseable: {st}")

    if sports_set:
        sp = get_field_variant(ex_item, *FIELD_SPORT, default="")

        if debug:
            print(f"     Sport: '{sp}' | Buscando: {sports_set}")

        if sp not in sports_set:
            if debug:
                print("     ❌ Sport no coincide")
            return False

        if debug:
            print("     ✅ Sport OK")

    if max_duration_min:
        duration_str = ex_item.get("duration", "")
        if duration_str:
            duration_min = parse_duration_to_minutes(duration_str)
            if duration_min is None:
                if debug:
                    print(f"     ⚠️  Duración no parseable: {duration_str}")
                return False

            if debug:
                print(f"     Duración: {duration_str} = {duration_min:.2f} min | Max: {max_duration_min}")

            if duration_min > max_duration_min:
                if debug:
                    print(f"     ❌ Duración excedida ({duration_min:.2f} > {max_duration_min})")
                return False

            if debug:
                print("     ✅ Duración OK")

    if debug:
        print("     ✅✅ PASA TODOS LOS FILTROS")

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
        print(f"⚠️  Error leyendo CORE: {e}")
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
        print(f"⚠️  Error leyendo fechas del CORE: {e}")
        return set()


def calculate_missing_days():
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
        _qprint("▶️  Regenerando FINAL/DASHBOARD con sleep actualizado...")
        run_build_hrv_final_dashboard_only()


def _resolve_date_range(args):
    if args.all:
        _qprint("📅 Procesando TODAS las sesiones")
        return None, None, None, None

    if args.auto:
        days_missing, last_date = calculate_missing_days()
        if days_missing == 0:
            return None, None, last_date, "auto_no_missing"
        to_d = datetime.now().date()
        if last_date:
            from_d = last_date + timedelta(days=1)
            _qprint(f"📅 Última medición: {last_date}")
            _qprint(f"   Descargando desde {from_d} hasta {to_d}")
        else:
            from_d = (datetime.now() - timedelta(days=days_missing)).date()
            _qprint(f"📅 Master sin datos, descargando últimos {days_missing} días")
        return from_d, to_d, last_date, None

    if args.days is not None:
        to_d = datetime.now().date()
        from_d = (datetime.now() - timedelta(days=args.days)).date()
        _qprint(f"📅 Últimos {args.days} días: {from_d} → {to_d}")
        return from_d, to_d, None, None

    days_missing, last_date = calculate_missing_days()
    if days_missing == 0:
        return None, None, last_date, "default_no_missing"
    if days_missing > MAX_AUTO_DAYS:
        print(f"⚠️  Faltan {days_missing} días (>30)")
        print("   Limitando a últimos 30 días")
        print("   Usa --all para descargar todo")
        days_missing = MAX_AUTO_DAYS

    to_d = datetime.now().date()
    if last_date:
        from_d = last_date + timedelta(days=1)
        _qprint(f"📅 Última medición: {last_date}")
        _qprint(f"   Descargando desde {from_d} hasta {to_d} ({days_missing} días)")
    else:
        from_d = (datetime.now() - timedelta(days=days_missing)).date()
        _qprint(f"📅 Descargando últimos {days_missing} días (default)")
    return from_d, to_d, last_date, None


def sync_hrv_range(args, access_token: str, x_user_id: Optional[str], exercises: list) -> None:
    from_d, to_d, _, exit_mode = _resolve_date_range(args)
    if exit_mode == "auto_no_missing":
        if args.process:
            _qprint("▶️  Sin RR nuevos: actualizando sleep.csv (hoy)...")
            _refresh_sleep_and_outputs(access_token, x_user_id, run_final_dashboard=True)
        _print_sync_completed(updated_date=datetime.now().date(), checkmark=False)
        show_latest_hrv_summaries()
        return
    if exit_mode == "default_no_missing":
        if args.process:
            _qprint("▶️  Sin RR nuevos: actualizando sleep.csv (hoy)...")
            _refresh_sleep_and_outputs(access_token, x_user_id, run_final_dashboard=True)
        _print_sync_completed(updated_date=None, checkmark=True)
        show_latest_hrv_summaries()
        _print_divider(trailing_blank=True)
        return

    if args.debug_sports:
        _print_header("🔍 DEBUG: TODAS LAS SESIONES ENCONTRADAS")
        for i, e in enumerate(exercises):
            st = get_field_variant(e, *FIELD_START_TIME, default="N/A")
            sport = get_field_variant(e, *FIELD_SPORT, default="N/A")
            duration = e.get("duration", "N/A")
            dt = _iso_to_dt(st)
            date_str = dt.strftime("%Y-%m-%d") if dt else "N/A"
            print(f"  [{i}] {date_str} | Sport: '{sport}' | Duration: {duration}")
        _print_divider(trailing_blank=True)

    sports_set = set(SPORTS_FILTER) if SPORTS_FILTER else None
    filtered = []
    for e in exercises:
        if passes_filters(e, from_d, to_d, sports_set, MAX_DURATION_MINUTES):
            filtered.append(e)
        if len(filtered) >= MAX_EXERCISES:
            break

    if not filtered and args.process:
        # When the active date window misses all eligible BODY_AND_MIND sessions,
        # fall back to the same sport/duration filters without the date bound so
        # the HRV pipeline can still complete for the latest available session.
        fallback_filtered = []
        for e in exercises:
            if passes_filters(e, None, None, sports_set, MAX_DURATION_MINUTES):
                fallback_filtered.append(e)
            if len(fallback_filtered) >= MAX_EXERCISES:
                break
        if fallback_filtered:
            _qprint(
                f"⚠️  No hay sesiones en el rango pedido; usando {len(fallback_filtered)} "
                "sesiones elegibles sin filtro de fecha para continuar el procesado."
            )
            filtered = fallback_filtered

    _qprint(f"✅ {len(filtered)} sesiones tras filtros (max {MAX_EXERCISES})")

    existing_for_dropbox = None
    target_for_dropbox = None
    dropbox_only_map: Dict = {}
    if DROPBOX_RR_ENABLED:
        existing_for_dropbox = get_existing_dates_from_master()
        target_for_dropbox = _compute_target_missing_dates(from_d, to_d, existing_for_dropbox)
        if not filtered:
            dropbox_only_map, _ = _run_dropbox_rr_import_for_dates(target_for_dropbox, OUTDIR, verbose=args.verbose)

    if not filtered:
        if dropbox_only_map:
            _qprint(
                f"☁️  Dropbox ya cubrió {len(dropbox_only_map)} fecha(s) objetivo "
                "con RR válidos. Continuando con procesamiento HRV."
            )
        else:
            if QUIET:
                print("⚠️  No hay RR matinales disponibles para el periodo objetivo")
                if args.process:
                    _refresh_sleep_and_outputs(access_token, x_user_id, run_final_dashboard=False)
                    show_latest_hrv_summaries()
                _send_intervals_wellness_from_master(INTERVALS_SOURCE_PATH)
                return

            print("\n⚠️  No hay RR matinales disponibles para el periodo objetivo")

            if not args.debug_sports and exercises:
                print("\n🔍 Mostrando TODAS las sesiones encontradas para debug:")
                _print_divider()
                for i, e in enumerate(exercises[:DEBUG_PREVIEW_LIMIT]):
                    st = get_field_variant(e, *FIELD_START_TIME, default="N/A")
                    sport = get_field_variant(e, *FIELD_SPORT, default="N/A")
                    duration = e.get("duration", "N/A")
                    dt = _iso_to_dt(st)
                    date_str = dt.strftime("%Y-%m-%d") if dt else "N/A"
                    in_range = "✓" if from_d and to_d and dt and from_d <= dt.date() <= to_d else "✗"
                    print(f"  [{i}] {date_str} {in_range} | Sport: '{sport}' | Duration: {duration}")

                if len(exercises) > DEBUG_PREVIEW_LIMIT:
                    print(f"  ... y {len(exercises) - DEBUG_PREVIEW_LIMIT} más")
                _print_divider()
                print(f"\n💡 Buscando: Sport EXACTO = '{SPORTS_FILTER[0] if SPORTS_FILTER else 'N/A'}'")
                print(f"   En rango: {from_d} a {to_d}")

                _print_header("🔍 DEBUG DETALLADO de cada sesión en rango:", leading_blank=True)
                for i, e in enumerate(exercises[:DEBUG_PREVIEW_LIMIT]):
                    st = get_field_variant(e, *FIELD_START_TIME, default="N/A")
                    dt = _iso_to_dt(st)
                    if dt and from_d and to_d and from_d <= dt.date() <= to_d:
                        print(f"\n  Sesión [{i}] - {dt.date()}:")
                        passes_filters(e, from_d, to_d, sports_set, MAX_DURATION_MINUTES, debug=True)
                _print_divider()

            print(f"\n💡 No se encontraron sesiones '{SPORTS_FILTER[0] if SPORTS_FILTER else 'N/A'}' en el periodo.")
            print(f"   Usa --days N para más días o --debug-sports para ver todas las sesiones.")
            if args.process:
                _refresh_sleep_and_outputs(access_token, x_user_id, run_final_dashboard=False)
                _print_header("📊 Aunque no hay nuevos datos, aquí está tu última medición:")
                show_latest_hrv_summaries()
            _send_intervals_wellness_from_master(INTERVALS_SOURCE_PATH)
            return

    _qprint("\n📥 Descargando datos RR...")
    OUTDIR.mkdir(exist_ok=True)
    existing_dates = get_existing_dates_from_master()
    pre_process_dates = set(existing_dates)
    if existing_dates and args.verbose:
        print(f"📋 {len(existing_dates)} fechas ya en CORE")

    exported = 0
    skipped_in_master = 0
    skipped_covered_by_dropbox = 0
    skipped_no_date = 0
    skipped_empty_rr = 0
    skipped_write_errors = 0
    rr_files = []
    pending_rr_dates = set()

    target_missing_dates = target_for_dropbox or _compute_target_missing_dates(from_d, to_d, existing_dates)
    dropbox_rr_map: Dict = {}
    dropbox_rr_new = 0
    if dropbox_only_map:
        dropbox_rr_map = dropbox_only_map
        dropbox_rr_new = len(dropbox_rr_map)
        for day, rr_path in sorted(dropbox_rr_map.items(), key=lambda x: x[0]):
            rr_files.append(rr_path)
            pending_rr_dates.add(day)
    elif DROPBOX_RR_ENABLED and target_missing_dates:
        dropbox_rr_map, dropbox_rr_new = _run_dropbox_rr_import_for_dates(
            target_missing_dates,
            OUTDIR,
            verbose=args.verbose,
        )
        for day, rr_path in sorted(dropbox_rr_map.items(), key=lambda x: x[0]):
            rr_files.append(rr_path)
            pending_rr_dates.add(day)
        if dropbox_rr_map:
            reused = max(len(dropbox_rr_map) - dropbox_rr_new, 0)
            _qprint(
                f"☁️  Dropbox RR: {len(dropbox_rr_map)} fecha(s) cubierta(s) "
                f"({dropbox_rr_new} nuevas, {reused} ya existentes)"
            )

    for idx, e in enumerate(filtered):
        ex_id = e.get("id")
        if not ex_id:
            continue

        st_hint = get_field_variant(e, *FIELD_START_TIME, default="")
        st_hint_dt = _iso_to_dt(st_hint)
        session_date_hint = st_hint_dt.date() if st_hint_dt else None
        if session_date_hint and session_date_hint in existing_dates:
            if args.verbose:
                print(f"  [{idx}] ⏭️  {session_date_hint} ya en CORE, omitiendo")
            skipped_in_master += 1
            continue
        if session_date_hint and session_date_hint in pending_rr_dates:
            if args.verbose:
                print(
                    f"  [{idx}] ⏭️  {session_date_hint} ya cubierto por RR principal en Dropbox, "
                    "no hace falta fallback Polar"
                )
            skipped_covered_by_dropbox += 1
            continue

        try:
            ex_full = get_exercise_with_samples(access_token, ex_id)
        except (requests.RequestException, RuntimeError) as ex:
            print(f"  [{idx}] ❌ Error descargando: {ex}")
            continue

        st = get_field_variant(ex_full, *FIELD_START_TIME, default="")

        if not st:
            print(f"  [{idx}] ⚠️ Sin start-time, usando del índice previo")
            st = get_field_variant(e, "start-time", "start_time", "startTime", default="")

        if not st:
            print(f"  [{idx}] ⚠️ No se puede determinar fecha/hora, usando ID")
            out_name = f"{POLAR_USER_NAME}_{UNKNOWN_SESSION_ID}_{ex_id}_RR.CSV"
            session_date = None
        else:
            st_dt = _iso_to_dt(st)

            if not st_dt:
                print(f"  [{idx}] ⚠️ Error parseando fecha, usando ID")
                out_name = f"{POLAR_USER_NAME}_{UNKNOWN_SESSION_ID}_{ex_id}_RR.CSV"
                session_date = None
            else:
                date_part = st_dt.strftime("%Y-%m-%d")
                time_part = st_dt.strftime("%H-%M-%S")
                out_name = f"{POLAR_USER_NAME}_{date_part}_{time_part}_RR.CSV"
                session_date = st_dt.date()

        if session_date is None:
            out_path = OUTDIR / out_name
            if out_path.exists():
                if args.verbose:
                    print(f"  [{idx}] ⏭️  {out_name} sin fecha, se omite procesamiento")
            else:
                rr = extract_rr_ms(ex_full)
                if not rr:
                    print(f"  [{idx}] ⚠️  Sin samples RR válidos, se omite export")
                    skipped_empty_rr += 1
                    continue
                if not write_rr_csv(rr, str(out_path)):
                    skipped_write_errors += 1
                    continue
            skipped_no_date += 1
            continue

        if session_date and session_date in existing_dates:
            if args.verbose:
                print(f"  [{idx}] ⏭️  {date_part} ya en CORE, omitiendo")
            skipped_in_master += 1
            continue
        if session_date and session_date in pending_rr_dates:
            if args.verbose:
                print(f"  [{idx}] ⏭️  {date_part} ya cubierto por RR principal en Dropbox, sin fallback Polar")
            skipped_covered_by_dropbox += 1
            continue

        out_path = OUTDIR / out_name
        if out_path.exists():
            if args.verbose:
                print(f"  [{idx}] ♻️  {out_name} existe, se procesará (no en master)")
            rr_files.append(out_path)
            pending_rr_dates.add(session_date)
            continue

        rr = extract_rr_ms(ex_full)
        if not rr:
            print(f"  [{idx}] ⚠️  Sin samples RR válidos, se omite export")
            skipped_empty_rr += 1
            continue
        if not write_rr_csv(rr, str(out_path)):
            skipped_write_errors += 1
            continue
        rr_files.append(out_path)
        pending_rr_dates.add(session_date)
        exported += 1

        offline_pct = 100.0 * sum(1 for _, off in rr if off == 1) / max(1, len(rr))
        if args.verbose:
            print(f"  [{idx}] ✅ {out_name} | {len(rr)} RR | offline: {offline_pct:.1f}%")

    _print_header("✅ EXPORT COMPLETADO")

    total_to_process = len(rr_files)
    existing = max(total_to_process - exported - dropbox_rr_new, 0)

    if exported > 0:
        _qprint(f"\n📥 {exported} archivos nuevos descargados")
    if dropbox_rr_new > 0:
        _qprint(f"☁️  {dropbox_rr_new} RR nuevos generados desde Dropbox")

    if skipped_in_master > 0:
        _qprint(f"⏭️  {skipped_in_master} sesiones omitidas (ya en CORE)")
    if skipped_covered_by_dropbox > 0:
        _qprint(f"☁️  ⏭️  {skipped_covered_by_dropbox} sesiones omitidas (RR ya cubiertos por Dropbox)")
    if skipped_no_date > 0:
        _qprint(f"⚠️  {skipped_no_date} sesiones sin fecha (no se procesan)")
    if skipped_empty_rr > 0:
        print(f"⚠️  {skipped_empty_rr} sesiones sin RR válidos (no se procesan)")
    if skipped_write_errors > 0:
        print(f"❌ {skipped_write_errors} RR no pudieron escribirse en disco")

    if total_to_process > exported:
        _qprint(f"♻️  {existing} archivos existentes para reprocesar")

    _qprint(f"\n📊 {total_to_process} archivos totales para procesar en {OUTDIR}/")

    if total_to_process == 0 and skipped_in_master == 0:
        if skipped_no_date > 0:
            print("⚠️  No hay RR con fecha válida para procesar")
        else:
            _print_no_rr_files()
        _refresh_sleep_and_outputs(access_token, x_user_id, run_final_dashboard=args.process)
        _send_intervals_wellness_from_master(INTERVALS_SOURCE_PATH)
        show_latest_hrv_summaries()
        return

    if total_to_process == 0 and skipped_in_master > 0:
        _print_master_already_updated()
        _refresh_sleep_and_outputs(access_token, x_user_id, run_final_dashboard=args.process)
        _send_intervals_wellness_from_master(INTERVALS_SOURCE_PATH)
        show_latest_hrv_summaries()
        return

    if args.process:
        _print_header("🔧 PROCESANDO PIPELINE HRV")

        cmd = build_hrv_core_cmd(rr_files)
        if len(cmd) <= 2:
            print("")
            print("⚠️  No hay archivos RR con fecha válida para procesar")
            _refresh_sleep_and_outputs(access_token, x_user_id, run_final_dashboard=True)
            _send_intervals_wellness_from_master(INTERVALS_SOURCE_PATH)
            show_latest_hrv_summaries()
            return

        _qprint("")
        _qprint("▶️  Ejecutando build_hrv_core.py...")
        _qprint("")
        result = run_build_hrv_core(rr_files)
        if result is None:
            print("⚠️  build_hrv_core.py falló; se actualiza sleep.csv, pero no se regenera FINAL/DASHBOARD.")
            _refresh_sleep_and_outputs(access_token, x_user_id, run_final_dashboard=False)
            _send_intervals_wellness_from_master(INTERVALS_SOURCE_PATH)
            show_latest_hrv_summaries()
            return

        if result.stdout:
            print(result.stdout)

        post_process_dates = get_existing_dates_from_master() if PANDAS_AVAILABLE else set()
        new_dates = sorted(post_process_dates - pre_process_dates) if PANDAS_AVAILABLE else []
        if new_dates:
            merged_dates = set(new_dates)
            merged_dates.update(_default_sleep_refresh_dates())
            target_dates = sorted(merged_dates)
        else:
            target_dates = _default_sleep_refresh_dates()
        _qprint("")
        _qprint(f"▶️  Actualizando sleep.csv ({len(target_dates)} fecha(s))...")
        _update_sleep_for_dates(access_token, x_user_id, target_dates)

        _qprint("")
        _qprint("▶️  Ejecutando build_hrv_final_dashboard.py...")
        _qprint("")
        run_build_hrv_final_dashboard_only()

        _qprint("")
        _qprint("▶️  Ejecutando build_hrv_ssm.py...")
        _qprint("")
        ssm_ok = run_build_hrv_ssm_shadow_only()
        if not ssm_ok:
            print("⚠️  build_hrv_ssm.py falló; FINAL/DASHBOARD se mantienen actualizados, pero no se regenera SSM shadow.")

        if not QUIET:
            print("")
            print("✅ Procesamiento HRV completado")
            print("")
            print("📄 Archivos actualizados:")
            print("   - ENDURANCE_HRV_master_CORE.csv")
            print("   - ENDURANCE_HRV_master_BETA_AUDIT.csv")
            print("   - ENDURANCE_HRV_master_CORE_manifest.json")
            print("   - ENDURANCE_HRV_master_FINAL.csv")
            print("   - ENDURANCE_HRV_master_DASHBOARD.csv")
            print("   - ENDURANCE_HRV_master_FINAL_manifest.json")
            print("   - ENDURANCE_HRV_ssm_shadow.csv")
        _send_intervals_wellness_from_master(INTERVALS_SOURCE_PATH)
        show_latest_hrv_summaries()
    else:
        _send_intervals_wellness_from_master(INTERVALS_SOURCE_PATH)
