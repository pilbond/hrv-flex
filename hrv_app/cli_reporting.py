from __future__ import annotations
import math

try:
    import pandas as pd
except ImportError:  # pragma: no cover - exercised implicitly when pandas is absent
    pd = None

from .config import (
    COLOR_EMOJI,
    CORE_PATH,
    DATE_STRING_LENGTH,
    FINAL_PATH,
    GATE_EMOJI,
    PANDAS_AVAILABLE,
    QUIET,
    _qprint,
)


def _get_color_emoji(color_value, default="⚪"):
    """Convierte valor de color a emoji."""
    return COLOR_EMOJI.get(color_value, default)


def _get_gate_emoji(gate_value, default="⚪"):
    """Convierte gate_badge a emoji."""
    if gate_value is None:
        return default
    value = str(gate_value).strip().upper()
    if value.startswith("VERDE"):
        key = "VERDE"
    elif value.startswith("ÁMBAR") or value.startswith("AMBAR"):
        key = "ÁMBAR"
    elif value.startswith("ROJO"):
        key = "ROJO"
    elif value.startswith("NO"):
        key = "NO"
    else:
        key = value.replace("Á", "A")
    return GATE_EMOJI.get(key, default)


def _format_metric(value, decimals=1):
    """Formatea métrica numérica o devuelve N/A."""
    if PANDAS_AVAILABLE:
        is_valid = pd.notna(value) and value != "N/A"
    else:
        is_valid = value is not None and value != "N/A"
    if is_valid:
        try:
            return f"{float(value):.{decimals}f}"
        except (ValueError, TypeError):
            return "N/A"
    return "N/A"


def _has_value(value):
    if PANDAS_AVAILABLE:
        return value is not None and pd.notna(value) and str(value).strip() != "" and str(value) != "N/A"
    return value is not None and str(value).strip() != "" and str(value) != "N/A"


def _format_recovery_quality(value):
    mapping = {
        "rich": "contexto completo",
        "basic": "contexto parcial",
        "none": "sin contexto",
    }
    return mapping.get(str(value or "").strip().lower(), str(value or "N/A"))


def _format_recovery_class(value):
    mapping = {
        "supported": "senales alineadas",
        "fragile": "senales fragiles",
        "conflicted": "senales mixtas",
        "neutral": "sin senal clara",
    }
    return mapping.get(str(value or "").strip().lower(), str(value or "N/A"))


def _print_header(title: str, width: int = 25, leading_blank: bool = True, trailing_blank: bool = False):
    if QUIET:
        return
    line = "=" * width
    if leading_blank:
        _qprint("\n" + line)
    else:
        _qprint(line)
    _qprint(title)
    if trailing_blank:
        _qprint(line + "\n")
    else:
        _qprint(line)


def _print_divider(width: int = 30, leading_blank: bool = False, trailing_blank: bool = False):
    if QUIET:
        return
    line = "=" * width
    if leading_blank:
        _qprint("\n" + line)
    else:
        _qprint(line)
    if trailing_blank:
        _qprint("")


def _print_sync_completed(updated_date=None, checkmark=False):
    if QUIET:
        return
    print("\n✅ SINCRONIZACIÓN COMPLETADA")
    if updated_date:
        print(f"📊 CORE actualizado hasta hoy ({updated_date})")
    else:
        print("📊 CORE actualizado hasta hoy")
    print("💡 No nuevas sesiones")


def _print_no_rr_files():
    if QUIET:
        print("⚠️  No hay RR para procesar")
        return
    print("\n⚠️  No hay archivos RR para procesar")
    print("Causas típicas:")
    print("   - Sesiones sin RR en el periodo")
    print("   - Archivos aún no disponibles en Dropbox ni en Polar")


def _print_master_already_updated():
    if QUIET:
        return
    print("\n✅ CORE ya está actualizado con todas las sesiones")
    print("   No hay nada nuevo que procesar")


def show_last_daily_summary():
    """Muestra el último daily summary (FINAL si existe, si no CORE)."""
    if not PANDAS_AVAILABLE:
        return

    if FINAL_PATH.exists():
        try:
            df = pd.read_csv(FINAL_PATH)
            if df.empty or "Fecha" not in df.columns:
                return
            last_row = df.sort_values("Fecha").iloc[-1]

            _print_header("💓 Última Medición HRV (V4)", leading_blank=False)

            fecha = last_row.get("Fecha", "N/A")
            hr = last_row.get("HR_today", "N/A")
            rmssd = last_row.get("RMSSD_stable", "N/A")
            gate = last_row.get("gate_badge", "N/A")
            action = last_row.get("Action", "N/A")
            action_detail = last_row.get("Action_detail", "N/A")
            reason = last_row.get("gate_razon_base60", "N/A")
            reason_text = last_row.get("reason_text", "N/A")
            decision_path = last_row.get("decision_path", "N/A")
            recovery_class = last_row.get("recovery_support_class", "N/A")
            recovery_quality = last_row.get("recovery_context_quality", "N/A")
            recovery_discordance_reason = last_row.get("recovery_discordance_reason", "N/A")
            calidad = last_row.get("Calidad", "N/A")
            stab = last_row.get("HRV_Stability", "N/A")
            degraded = str(last_row.get("baseline60_degraded", False)).strip().lower() in {"true", "1", "yes"}
            ln_base60 = last_row.get("ln_base60", "N/A")
            n_base60 = last_row.get("n_base60", "N/A")
            healthy_rmssd = last_row.get("healthy_rmssd", "N/A")
            warning_threshold = last_row.get("warning_threshold", "N/A")
            base60_rmssd = "N/A"
            if _has_value(ln_base60):
                try:
                    base60_rmssd = f"{math.exp(float(ln_base60)):.1f}"
                except (ValueError, TypeError, OverflowError):
                    base60_rmssd = "N/A"

            gate_emoji = _get_gate_emoji(gate)

            print(f"📅 Fecha:           {fecha}")
            print(f"💓 HR hoy:          {_format_metric(hr)} bpm")
            print(f"📊 RMSSD:           {_format_metric(rmssd)} ms")
            print(f"🚦 Gate:            {gate_emoji} {gate}")
            print(f"🧭 Acción:          {action} / {action_detail}")
            print(f"🧾 Razón gate:      {reason}")
            print(f"🧠 Reason text:     {reason_text}")
            print(f"🧩 Decision path:   {decision_path}")
            print(
                "🧪 Contexto recuperación: "
                f"{_format_recovery_quality(recovery_quality)} / {_format_recovery_class(recovery_class)}"
            )
            if _has_value(recovery_discordance_reason):
                print(f"⚠️  Discordancia:   {recovery_discordance_reason}")
            print(f"✅ Calidad:         {calidad}")
            print(f"📈 Estabilidad:     {stab}")
            if base60_rmssd != "N/A":
                base60_suffix = f" (n={int(float(n_base60))})" if _has_value(n_base60) else ""
                print(f"📐 Base 60d:        {base60_rmssd} ms{base60_suffix}")
            if _has_value(healthy_rmssd):
                print(f"📏 Healthy RMSSD:   {_format_metric(healthy_rmssd)} ms")
            if _has_value(warning_threshold):
                print(f"⚠️  Umbral warn.:   {_format_metric(warning_threshold)} ms")
            if bool(degraded):
                print("⚠️  Warning base:  baseline60_degraded=True")
            return
        except (FileNotFoundError, pd.errors.EmptyDataError, KeyError, IndexError) as e:
            print(f"⚠️  Error mostrando summary FINAL: {e}")

    if not CORE_PATH.exists():
        return

    try:
        df = pd.read_csv(CORE_PATH)
        if df.empty or "Fecha" not in df.columns:
            return

        last_row = df.sort_values("Fecha").iloc[-1]

        _print_header("💓 Última Medición HRV (CORE)")
        print("")

        fecha = last_row.get("Fecha", "N/A")
        hr = last_row.get("HR_stable", "N/A")
        rmssd = last_row.get("RMSSD_stable", "N/A")
        calidad = last_row.get("Calidad", "N/A")
        stab = last_row.get("HRV_Stability", "N/A")

        print(f"📅 Fecha:          {fecha}")
        print(f"💓 HR promedio:    {_format_metric(hr)} bpm")
        print(f"📊 RMSSD:          {_format_metric(rmssd)} ms")
        print(f"✅ Calidad:        {calidad}")
        print(f"📈 Estabilidad:    {stab}")

        flags = last_row.get("Flags", "")
        if pd.notna(flags) and flags:
            print(f"🚩 Flags:          {flags}")
    except (FileNotFoundError, pd.errors.EmptyDataError, KeyError, IndexError) as e:
        print(f"⚠️  Error mostrando summary CORE: {e}")


def show_last_7_days_summary():
    """Muestra resumen compacto de los últimos 7 días (FINAL si existe, si no CORE)."""
    if not PANDAS_AVAILABLE:
        return

    use_final = FINAL_PATH.exists()
    src_path = FINAL_PATH if use_final else CORE_PATH

    if not src_path.exists():
        return

    try:
        df = pd.read_csv(src_path)
        if df.empty or "Fecha" not in df.columns:
            return

        df_sorted = df.sort_values("Fecha")
        last_7 = df_sorted.tail(7)
        if len(last_7) == 0:
            return

        print("")
        title = "📊 RESUMEN ÚLTIMOS 7 DÍAS (V4)" if use_final else "📊 RESUMEN ÚLTIMOS 7 DÍAS (CORE)"
        _print_header(title)

        for _, row in last_7.iterrows():
            fecha = row.get("Fecha", "N/A")
            fecha_str = fecha
            if isinstance(fecha, str) and len(fecha) == DATE_STRING_LENGTH:
                fecha_str = fecha[2:]

            hr = row.get("HR_today", "N/A") if use_final else row.get("HR_stable", "N/A")
            rmssd = row.get("RMSSD_stable", "N/A")

            hr_str = _format_metric(hr)
            rmssd_str = _format_metric(rmssd)

            if use_final:
                gate = row.get("gate_badge", "N/A")
                action = row.get("Action", "N/A")
                gate_emoji = _get_gate_emoji(gate)
                print(f"{fecha_str}  💓{hr_str:>5}  📊{rmssd_str:>5}  {gate_emoji} {gate}  → {action}")
            else:
                print(f"{fecha_str}  💓{hr_str:>5}  📊{rmssd_str:>5}")
    except (FileNotFoundError, pd.errors.EmptyDataError, KeyError, IndexError) as e:
        print(f"⚠️  Error mostrando resumen 7 días: {e}")


def show_latest_hrv_summaries():
    """Muestra el resumen diario y el histórico corto más recientes."""
    show_last_daily_summary()
    show_last_7_days_summary()
