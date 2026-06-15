from __future__ import annotations
import json
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
    SSM_SHADOW_METADATA_PATH,
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


def _row_value(row, key):
    if row is None:
        return None
    if hasattr(row, "get"):
        return row.get(key)
    try:
        return row[key]
    except (KeyError, TypeError, IndexError):
        return None


def _maybe_float(value):
    if value is None or (PANDAS_AVAILABLE and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _load_ssm_daily_summary(expected_date=None):
    if not SSM_SHADOW_METADATA_PATH.exists():
        return None
    try:
        payload = json.loads(SSM_SHADOW_METADATA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    summary = payload.get("daily_user_summary")
    if not isinstance(summary, dict) or summary.get("status") != "ok":
        return None
    if expected_date is not None and str(summary.get("date")) != str(expected_date):
        return None
    return summary


def _format_gate_reason(value, row=None):
    """Traduce el código interno del gate a un mensaje más humano."""
    raw = str(value or "").strip()
    if not raw or raw == "N/A":
        return "N/A"

    mapping = {
        "CAL/STAB/ART/NaN": (
            "La toma de hoy no fue lo bastante fiable para usarla. "
            "Suele pasar por artefactos, señal inestable o una medición "
            "incompleta."
        ),
        "ROLL3_INSUF": (
            "Aún faltan días limpios seguidos para construir una referencia "
            "fiable."
        ),
        "BASE60_INSUF": (
            "Todavía no hay suficientes datos limpios en la ventana de 60 días "
            "para comparar con confianza."
        ),
        "SWC_NAN/0": (
            "La referencia estadística de hoy salió vacía o demasiado plana, "
            "así que no conviene sacar conclusiones."
        ),
        "RAW_NAN/0": (
            "La señal bruta llegó vacía o inválida, por eso hoy no se pudo "
            "evaluar."
        ),
        "2D_OK": (
            "La señal quedó dentro de tu rango reciente; si el resto del "
            "contexto también acompaña, puedes seguir con el plan previsto."
        ),
        "2D_LN": (
            "La señal suavizada bajó respecto a tu base reciente; conviene "
            "no apretar más de la cuenta y vigilar recuperación y carga."
        ),
        "2D_HR": (
            "La frecuencia cardiaca suavizada subió respecto a tu base reciente; "
            "mejor mantener prudencia hoy y evitar subir demasiado la intensidad."
        ),
        "2D_AMBOS": (
            "La señal suavizada bajó y la frecuencia cardiaca suavizada subió "
            "respecto a tu base reciente; trata hoy como un día más delicado: "
            "baja un punto la exigencia."
        ),
    }
    if raw in mapping:
        text = mapping[raw]
        if raw == "CAL/STAB/ART/NaN":
            clues: list[str] = []
            artifact_pct = _maybe_float(_row_value(row, "Artifact_pct"))
            if artifact_pct is not None:
                if artifact_pct >= 15:
                    clues.append(f"artefactos altos ({artifact_pct:.1f}%)")
                else:
                    clues.append(f"artefactos presentes ({artifact_pct:.1f}%)")

            stability = str(_row_value(row, "HRV_Stability") or "").strip()
            if stability and stability.upper() not in {"OK", "ALTA", "HIGH", "GOOD"}:
                clues.append(f"estabilidad de señal {stability}")

            subtype = str(_row_value(row, "Stability_Subtype") or "").strip()
            if subtype and subtype.upper() not in {"OK", "N/A", "NONE", "NAN"}:
                clues.append(f"subtipo de estabilidad {subtype}")

            tiemp_est = _maybe_float(_row_value(row, "Tiempo_Estabilizacion"))
            if tiemp_est is not None:
                clues.append(f"estabilización de {tiemp_est:.0f}s")

            if clues:
                return text + " Pistas del registro: " + "; ".join(clues) + "."
            return text + " Causas típicas: artefactos, estabilidad insuficiente o medición incompleta."
        return text

    if raw.startswith("CAL/"):
        return (
            "La toma de hoy no fue lo bastante fiable para usarla (calidad, "
            "estabilidad o artefactos)."
        )
    if raw.endswith("_INSUF"):
        return (
            "Aún no hay suficientes datos limpios para hacer una comparación "
            "fiable."
        )
    if raw.endswith("/0") or "NAN" in raw:
        return (
            "La referencia o la señal no tienen suficiente información válida "
            "para comparar hoy."
        )

    return f"{raw} (motivo interno no traducido)"


def _format_gate_next_step(value):
    """Sugerencia práctica breve asociada al motivo del gate."""
    raw = str(value or "").strip()
    if not raw or raw == "N/A":
        return "N/A"

    mapping = {
        "CAL/STAB/ART/NaN": "Repite la toma en un momento más tranquilo, sin moverte y con el sensor bien colocado.",
        "ROLL3_INSUF": "Sigue midiendo de forma constante hasta reunir más días limpios.",
        "BASE60_INSUF": "Mantén la rutina: aún falta base para comparar con seguridad.",
        "SWC_NAN/0": "No tomes decisiones fuertes solo con este dato; espera una lectura con referencia estable.",
        "RAW_NAN/0": "Repite la medición o revisa si la señal llegó bien al sistema.",
        "2D_OK": "Puedes seguir con el plan previsto si el resto del contexto también acompaña.",
        "2D_LN": "Conviene no apretar más de la cuenta y vigilar recuperación y carga.",
        "2D_HR": "Mejor mantener prudencia hoy y evitar subir demasiado la intensidad.",
        "2D_AMBOS": "Trata hoy como un día más delicado: baja un punto la exigencia.",
    }
    if raw in mapping:
        return mapping[raw]
    if raw.startswith("CAL/"):
        return "Repite la toma en un momento más tranquilo y con el sensor bien colocado."
    if raw.endswith("_INSUF"):
        return "Sigue midiendo de forma constante hasta reunir más datos limpios."
    if raw.endswith("/0") or "NAN" in raw:
        return "No tomes decisiones fuertes con este dato; primero necesitas una lectura más fiable."
    return "Consulta el motivo interno si quieres más detalle técnico."


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


def _print_sync_completed(updated_date=None):
    if QUIET:
        return
    print("\n✅ SINCRONIZACIÓN COMPLETADA")
    if updated_date:
        print(f"📊 CORE actualizado hasta hoy ({updated_date})")
    else:
        print("📊 CORE actualizado hasta hoy")
    print("💡 No hay RR nuevos que procesar")


def _print_no_local_rr_files():
    if QUIET:
        print("⚠️  No hay RR locales para reprocesar")
        return
    print("\n⚠️  No hay archivos RR locales para reprocesar")
    print("   - rr_downloads/ está vacío")
    print("   - --all no descarga nada nuevo; usa el modo automático o --days N para traer RR desde Dropbox")


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
            degraded_best = str(last_row.get("degraded_vs_best", False)).strip().lower() in {"true", "1", "yes"}
            degraded_current = str(last_row.get("degraded_vs_current_normal", False)).strip().lower() in {"true", "1", "yes"}
            ln_base60 = last_row.get("ln_base60", "N/A")
            n_base60 = last_row.get("n_base60", "N/A")
            healthy_rmssd = last_row.get("healthy_rmssd", "N/A")
            warning_threshold = last_row.get("warning_threshold", "N/A")
            warning_threshold_best = last_row.get("warning_threshold_best", "N/A")
            warning_threshold_current = last_row.get("warning_threshold_current_normal", "N/A")
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
            print(f"🧾 Qué pasó:        {_format_gate_reason(reason, last_row)}")
            print(f"🧾 Qué hacer:       {_format_gate_next_step(reason)}")
            if _has_value(decision_path) and str(decision_path).strip() != "BASE60_ONLY":
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
                print(f"⚠️  Límite inferior de referencia: {_format_metric(warning_threshold)} ms")
            if bool(degraded):
                print("⚠️  Base 60d por debajo de tu referencia habitual")
            if _has_value(warning_threshold_best) and _has_value(warning_threshold_current):
                print(
                    "🧭 Baseline largo: "
                    f"best={'sí' if degraded_best else 'no'} / current={'sí' if degraded_current else 'no'}"
                )
            ln_rmssd_today = _maybe_float(last_row.get("lnRMSSD_today"))
            ln_rmssd_used = _maybe_float(last_row.get("lnRMSSD_used"))
            swc_ln = _maybe_float(last_row.get("SWC_ln"))
            if (
                _has_value(ln_base60)
                and ln_rmssd_used is not None
                and swc_ln is not None
            ):
                try:
                    ln_base60_f = float(ln_base60)
                    rmssd_base60 = math.exp(ln_base60_f)
                    rmssd_used = math.exp(ln_rmssd_used)
                    delta_ln = ln_rmssd_used - ln_base60_f
                    delta_ms = rmssd_used - rmssd_base60
                    raw_note = ""
                    if ln_rmssd_today is not None and abs(ln_rmssd_today - ln_rmssd_used) > 1e-6:
                        raw_note = f"; bruto hoy {_format_metric(rmssd)} ms"
                    print(
                        "🔎 Gate 2D:        "
                        f"usado {_format_metric(rmssd_used)} ms vs base60 {_format_metric(rmssd_base60)} ms "
                        f"(Δln {delta_ln:+.3f}; Δ≈{delta_ms:+.1f} ms; SWC_ln {_format_metric(swc_ln)})"
                        f"{raw_note}"
                    )
                except (ValueError, TypeError, OverflowError):
                    pass
            print(f"🧠 Reason text:     {reason_text}")
            ssm_summary = _load_ssm_daily_summary(expected_date=fecha)
            if ssm_summary:
                print("🧠 SSM estado:      "
                      f"{ssm_summary.get('state_label', 'N/A')} / confianza {ssm_summary.get('confidence_label', 'N/A')}")
                print(f"🧠 SSM lectura:     {ssm_summary.get('interpretive_text', 'N/A')}")
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
