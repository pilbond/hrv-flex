from __future__ import annotations

import argparse
import math
import json
from pathlib import Path

import pandas as pd
from pandas.api.types import is_scalar


DEFAULT_INPUT = Path("data/ENDURANCE_HRV_intensity_distribution_weekly.csv")
PATTERN_OK = {"pyramidal", "polarized"}
CONFIDENCE_OK = {"moderate", "high"}
WINDOW_SIZE = 4


def continuity_prefix(window_size: int) -> str:
    return f"cont{window_size}"


CONTINUITY_PREFIX = continuity_prefix(WINDOW_SIZE)


def validate_window_size(window_size: int) -> int:
    if window_size < 1:
        raise ValueError("window_size must be at least 1")
    return window_size


def validate_report_window_size(window_size: int) -> int:
    validate_window_size(window_size)
    if window_size < 2:
        raise ValueError("window_size must be at least 2")
    return window_size


def _resolve_min_positive_unchecked(window_size: int, min_positive: int | None) -> int:
    if min_positive is None:
        return positive_threshold(window_size)
    if not 1 <= min_positive <= window_size:
        raise ValueError(
            f"min_positive must be between 1 and {window_size} for a {window_size}-week window"
        )
    return min_positive


def positive_threshold(window_size: int, positive_ratio: float = 0.75) -> int:
    window_size = validate_window_size(window_size)
    if not 0 < positive_ratio <= 1:
        raise ValueError("positive_ratio must be in the (0, 1] interval")
    if window_size <= 3:
        return max(1, window_size - 1)
    return max(1, math.ceil(window_size * positive_ratio))


def resolve_min_positive(window_size: int, min_positive: int | None) -> int:
    validate_window_size(window_size)
    return _resolve_min_positive_unchecked(window_size, min_positive)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reproduce the historical continuity check documented in SYA-15."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="Path to ENDURANCE_HRV_intensity_distribution_weekly.csv",
    )
    parser.add_argument(
        "--sports",
        nargs="*",
        default=None,
        help="Optional list of sports to print detailed weekly rows for.",
    )
    parser.add_argument(
        "--show-all-details",
        action="store_true",
        help="Print detailed weekly rows for every sport.",
    )
    parser.add_argument(
        "--today",
        type=str,
        default=None,
        help="Optional YYYY-MM-DD date used to extend the weekly calendar to the current week.",
    )
    parser.add_argument(
        "--min-positive",
        type=int,
        default=None,
        help="Minimum number of Z1-dominant weeks required in each rolling window. Defaults to 75%% of the window size, but short windows (<=3) use window_size-1 to avoid a 100%% requirement.",
    )
    parser.add_argument(
        "--window-size",
        type=int,
        default=WINDOW_SIZE,
        help="Rolling window size in weeks used for the main SYA-15 analysis. Must be at least 2.",
    )
    parser.add_argument(
        "--focus-sport",
        type=str,
        default=None,
        help="Sport used to build the optional markdown/JSON review artifact. Defaults to the first sport in the summary when a report is requested.",
    )
    parser.add_argument(
        "--report-md",
        type=Path,
        default=None,
        help="Optional path to write a markdown review artifact for --focus-sport.",
    )
    parser.add_argument(
        "--report-json",
        type=Path,
        default=None,
        help="Optional path to write a machine-readable review artifact for --focus-sport.",
    )
    return parser


def load_weekly(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {
        "window_start",
        "sport",
        "distribution_confidence",
        "n_sessions_usable",
        "total_duration_min",
        "z1_pct_weighted",
        "distribution_pattern",
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    df["window_start"] = pd.to_datetime(df["window_start"])
    if not (df["window_start"].dt.weekday == 0).all():
        bad_rows = df.loc[df["window_start"].dt.weekday != 0, ["sport", "window_start"]]
        sample = bad_rows.head(5).to_dict("records")
        raise ValueError(
            "window_start must be Monday-aligned ISO weeks; sample invalid rows: "
            f"{sample}"
        )
    for col in ["n_sessions_usable", "total_duration_min", "z1_pct_weighted"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    duplicate_keys = df.duplicated(subset=["sport", "window_start"], keep=False)
    if duplicate_keys.any():
        sample = (
            df.loc[duplicate_keys, ["sport", "window_start"]]
            .sort_values(["sport", "window_start"])
            .head(5)
            .to_dict("records")
        )
        raise ValueError(
            "Duplicate sport/window_start rows are not supported; sample duplicates: "
            f"{sample}"
        )

    df["distribution_confidence"] = df["distribution_confidence"].fillna("").astype(str).str.lower()
    df["distribution_pattern"] = df["distribution_pattern"].fillna("").astype(str).str.lower()
    df["usable_week"] = (
        df["distribution_confidence"].isin(CONFIDENCE_OK)
        & (df["n_sessions_usable"] >= 2)
        & (df["total_duration_min"] >= 90)
    )
    df["z1_dominant"] = (
        df["usable_week"]
        & (df["z1_pct_weighted"] >= 75)
        & df["distribution_pattern"].isin(PATTERN_OK)
    )
    return df.sort_values(["sport", "window_start"]).reset_index(drop=True)


def resolve_today(today_arg: str | None) -> pd.Timestamp:
    if today_arg:
        return pd.Timestamp(today_arg).normalize()
    return pd.Timestamp.now().normalize()


def current_week_start(today: pd.Timestamp) -> pd.Timestamp:
    return today - pd.to_timedelta(today.weekday(), unit="D")


def expand_calendar(group: pd.DataFrame, today: pd.Timestamp) -> pd.DataFrame:
    current_week = current_week_start(today)
    calendar_end = max(group["window_start"].max(), current_week)
    idx = pd.date_range(group["window_start"].min(), calendar_end, freq="7D")
    expanded = group.set_index("window_start").reindex(idx)
    expanded.index.name = "window_start"
    expanded["row_observed"] = expanded["sport"].notna()
    expanded["sport"] = group["sport"].iloc[0]
    expanded["usable_week"] = expanded["usable_week"].fillna(False).astype(bool)
    expanded["z1_dominant"] = expanded["z1_dominant"].fillna(False).astype(bool)
    # The in-progress current week must never count as Z1-dominant, even if
    # the upstream weekly file already contains a partial row for it.
    if current_week in expanded.index:
        expanded.loc[current_week, "z1_dominant"] = False
    return expanded.reset_index()


def compute_continuity(
    calendar_df: pd.DataFrame,
    window_size: int = WINDOW_SIZE,
    min_positive: int | None = None,
) -> pd.DataFrame:
    validate_report_window_size(window_size)
    return _compute_continuity_validated(calendar_df, window_size, min_positive)


def _compute_continuity_validated(
    calendar_df: pd.DataFrame,
    window_size: int,
    min_positive: int | None,
) -> pd.DataFrame:
    min_positive = _resolve_min_positive_unchecked(window_size, min_positive)
    continuity_positive = []
    evaluable = []
    for i in range(len(calendar_df)):
        if i < window_size - 1:
            evaluable.append(False)
            continuity_positive.append(False)
            continue
        evaluable.append(True)
        window = calendar_df.iloc[i - (window_size - 1) : i + 1]
        continuity_positive.append(int(window["z1_dominant"].sum()) >= min_positive)
    out = calendar_df.copy()
    prefix = continuity_prefix(window_size)
    out[f"{prefix}_evaluable"] = evaluable
    out[f"{prefix}_positive"] = continuity_positive
    return out


def _summarize_by_sport_validated(
    df: pd.DataFrame,
    today: pd.Timestamp,
    window_size: int,
    min_positive: int | None,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    summary_rows: list[dict[str, object]] = []
    detailed: dict[str, pd.DataFrame] = {}
    prefix = continuity_prefix(window_size)
    resolved_min_positive = _resolve_min_positive_unchecked(window_size, min_positive)
    summary_columns = [
        "sport",
        "calendar_weeks",
        "rows_observed",
        "usable_weeks",
        "z1_dominant_weeks",
        f"{prefix}_evaluable_weeks",
        f"{prefix}_positive_weeks",
        f"{prefix}_positive_rate",
    ]

    for sport, group in df.groupby("sport", sort=True):
        calendar = _compute_continuity_validated(
            expand_calendar(group, today),
            window_size,
            resolved_min_positive,
        )
        detailed[sport] = calendar
        evaluable_weeks = int(calendar[f"{prefix}_evaluable"].sum())
        positive_weeks = int(calendar[f"{prefix}_positive"].sum())
        summary_rows.append(
            {
                "sport": sport,
                "calendar_weeks": int(len(calendar)),
                "rows_observed": int(calendar["row_observed"].sum()),
                "usable_weeks": int(calendar["usable_week"].sum()),
                "z1_dominant_weeks": int(calendar["z1_dominant"].sum()),
                f"{prefix}_evaluable_weeks": evaluable_weeks,
                f"{prefix}_positive_weeks": positive_weeks,
                f"{prefix}_positive_rate": round(
                    positive_weeks / evaluable_weeks, 3
                )
                if evaluable_weeks
                else 0.0,
            }
        )

    summary = pd.DataFrame(summary_rows, columns=summary_columns)
    if not summary.empty:
        summary = summary.sort_values(
            ["usable_weeks", "z1_dominant_weeks", "sport"],
            ascending=[False, False, True],
        )
    return summary, detailed


def summarize_by_sport(
    df: pd.DataFrame,
    today: pd.Timestamp,
    window_size: int = WINDOW_SIZE,
    min_positive: int | None = None,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    validate_report_window_size(window_size)
    return _summarize_by_sport_validated(df, today, window_size, min_positive)


def format_summary(summary: pd.DataFrame) -> str:
    return summary.to_string(index=False)


def format_detail(detail: pd.DataFrame, window_size: int = WINDOW_SIZE) -> str:
    validate_window_size(window_size)
    _validate_detail_columns(detail, window_size)
    prefix = continuity_prefix(window_size)
    cols = [
        "window_start",
        "row_observed",
        "usable_week",
        "z1_dominant",
        f"{prefix}_evaluable",
        f"{prefix}_positive",
    ]
    printable = detail[cols].copy()
    printable["window_start"] = printable["window_start"].dt.strftime("%Y-%m-%d")
    return printable.to_string(index=False)


def detect_positive_episodes(detail: pd.DataFrame, window_size: int = WINDOW_SIZE) -> pd.DataFrame:
    validate_window_size(window_size)
    positive_col = f"{continuity_prefix(window_size)}_positive"
    if "window_start" not in detail.columns:
        raise ValueError("Missing required column: window_start")
    if positive_col not in detail.columns:
        raise ValueError(f"Missing continuity column: {positive_col}")

    episodes: list[dict[str, object]] = []
    active_start = None
    active_end = None
    active_len = 0

    for row in detail.sort_values("window_start").itertuples(index=False):
        current_start = getattr(row, "window_start")
        current_positive = bool(getattr(row, positive_col))
        if current_positive:
            if active_start is None:
                active_start = current_start
                active_end = current_start
                active_len = 1
            else:
                active_end = current_start
                active_len += 1
        elif active_start is not None:
            episodes.append(
                {
                    "episode_start": active_start,
                    "episode_end": active_end,
                    "positive_weeks": active_len,
                }
            )
            active_start = None
            active_end = None
            active_len = 0

    if active_start is not None:
        episodes.append(
            {
                "episode_start": active_start,
                "episode_end": active_end,
                "positive_weeks": active_len,
            }
        )

    return pd.DataFrame(episodes, columns=["episode_start", "episode_end", "positive_weeks"])


def _summary_row_for_sport(summary: pd.DataFrame, sport: str) -> pd.Series:
    if sport not in set(summary["sport"]):
        raise ValueError(f"Sport not found in summary: {sport}")
    return summary.loc[summary["sport"] == sport].iloc[0]


def resolve_report_focus_sport(summary: pd.DataFrame, requested_sport: str | None) -> str:
    if requested_sport is not None:
        return requested_sport
    if summary.empty:
        raise ValueError("No sports available for report generation")
    return str(summary.iloc[0]["sport"])


def _validate_report_summary(summary: pd.DataFrame, window_size: int) -> None:
    prefix = continuity_prefix(window_size)
    required = {
        "sport",
        "calendar_weeks",
        "rows_observed",
        "usable_weeks",
        "z1_dominant_weeks",
        f"{prefix}_evaluable_weeks",
        f"{prefix}_positive_weeks",
        f"{prefix}_positive_rate",
    }
    missing = sorted(required - set(summary.columns))
    if missing:
        raise ValueError(
            "Summary columns do not match the requested window_size "
            f"{window_size}: missing {', '.join(missing)}"
        )


def _validate_detail_columns(detail: pd.DataFrame, window_size: int) -> None:
    prefix = continuity_prefix(window_size)
    required = {
        "window_start",
        "row_observed",
        "usable_week",
        "z1_dominant",
        f"{prefix}_evaluable",
        f"{prefix}_positive",
    }
    missing = sorted(required - set(detail.columns))
    if missing:
        raise ValueError(
            "Detail columns do not match the requested window_size "
            f"{window_size}: missing {', '.join(missing)}"
        )


def _json_safe_value(value: object) -> object:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if value is pd.NaT:
        return None
    if not is_scalar(value):
        return value
    if pd.isna(value):
        return None
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            return value.item()
        except (AttributeError, TypeError, ValueError):
            pass
    return value


def _json_safe_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    return [
        {key: _json_safe_value(value) for key, value in record.items()}
        for record in frame.to_dict(orient="records")
    ]


def _build_sport_report_validated(
    sport: str,
    summary: pd.DataFrame,
    details: dict[str, pd.DataFrame],
    today: pd.Timestamp,
    input_path: Path,
    window_size: int,
    min_positive: int | None,
) -> str:
    detail = details[sport]
    prefix = continuity_prefix(window_size)
    summary_row = _summary_row_for_sport(summary, sport)
    episodes = detect_positive_episodes(detail, window_size=window_size)
    detail_for_rates = detail.drop(
        columns=[f"{prefix}_evaluable", f"{prefix}_positive"],
        errors="ignore",
    )

    def _rate_for_threshold(threshold: int) -> tuple[int, int, float]:
        recalculated = _compute_continuity_validated(detail_for_rates.copy(), window_size, threshold)
        evaluable = int(recalculated[f"{prefix}_evaluable"].sum())
        positive = int(recalculated[f"{prefix}_positive"].sum())
        rate = round(positive / evaluable, 3) if evaluable else 0.0
        return positive, evaluable, rate

    lines: list[str] = [
        f"# SYA-15 {sport.replace('_', ' ').title()} Continuity Review",
        "",
        f"Fecha de anclaje: `{today.date()}`",
        "",
        "## Objetivo",
        "",
        f"Revisar si `SYA-15` aporta una lectura util para `{sport}` como señal local de `analysis`, sin promoverla al pipeline global.",
        "",
        "## Metodo",
        "",
        f"- fuente: `{Path(input_path).as_posix()}`",
        f"- definicion de semana `usable`: `distribution_confidence in {{moderate, high}}`, `n_sessions_usable >= 2`, `total_duration_min >= 90`",
        f"- definicion de semana `Z1-dominante`: semana `usable`, `z1_pct_weighted >= 75`, `distribution_pattern in {{pyramidal, polarized}}`",
        f"- continuidad evaluada sobre ventana rolling de `{window_size}` semanas calendario",
        "- la semana en curso se fuerza a `no Z1-dominante`",
        "",
        "## Resultado resumido",
        "",
        f"- `{sport}`: `{int(summary_row['z1_dominant_weeks'])}/{int(summary_row['usable_weeks'])}` semanas `usable` son `Z1-dominantes`",
        f"- continuidad `{window_size}w` positiva en `{sport}`: `{int(summary_row[f'{prefix}_positive_weeks'])}/{int(summary_row[f'{prefix}_evaluable_weeks'])}` ventanas evaluables (`{float(summary_row[f'{prefix}_positive_rate']) * 100:.0f}%`)",
        "",
        f"Sensibilidad de umbral en `{sport}`:",
        "",
    ]

    resolved_min_positive = _resolve_min_positive_unchecked(window_size, min_positive)
    threshold_start = max(1, resolved_min_positive - 1)
    threshold_candidates = range(threshold_start, window_size + 1) if window_size >= 1 else (1,)
    for threshold in threshold_candidates:
        positive, evaluable, rate = _rate_for_threshold(threshold)
        lines.append(
            f"- `{threshold}/{window_size}` activa `{positive}/{evaluable}` ventanas evaluables (`{rate * 100:.0f}%`)"
        )

    lines.extend(
        [
            "",
            f"Sensibilidad de ventana en `{sport}` con umbral relativo `75%`:",
            "",
        ]
    )

    detail_sensitivity_base = detail_for_rates.copy()
    candidate_window_sizes = sorted(
        {
            candidate
            for candidate in (window_size - 1, window_size, window_size + 1)
            if candidate >= 2
        }
    )
    for candidate_window_size in candidate_window_sizes:
        candidate_prefix = continuity_prefix(candidate_window_size)
        candidate = _compute_continuity_validated(
            detail_sensitivity_base.copy(),
            candidate_window_size,
            None,
        )
        candidate_evaluable = int(candidate[f"{candidate_prefix}_evaluable"].sum())
        candidate_positive = int(candidate[f"{candidate_prefix}_positive"].sum())
        candidate_rate = round(candidate_positive / candidate_evaluable, 3) if candidate_evaluable else 0.0
        threshold = positive_threshold(candidate_window_size)
        lines.append(
            f"- `{candidate_window_size}w` con umbral `{threshold}/{candidate_window_size}` -> "
            f"`{candidate_positive}/{candidate_evaluable}` ventanas evaluables (`{candidate_rate * 100:.0f}%`)"
        )

    lines.extend(
        [
            "",
            "## Episodios positivos",
            "",
            "Nota: estas fechas corresponden a las semanas de evaluacion de la ventana, no a la fecha exacta de entrenamiento.",
        ]
    )

    if episodes.empty:
        lines.append("No hay episodios positivos para esta combinacion de filtros.")
    else:
        for row in episodes.itertuples(index=False):
            start = pd.Timestamp(row.episode_start).strftime("%Y-%m-%d")
            end = pd.Timestamp(row.episode_end).strftime("%Y-%m-%d")
            lines.append(f"- `{start}` a `{end}` -> `{int(row.positive_weeks)}` semanas")

    lines.extend(
        [
            "",
            "## Interpretacion",
            "",
            f"`{window_size}w` con `{resolved_min_positive}/{window_size}` sigue siendo la configuracion de referencia de esta ejecucion:",
            "",
            f"- `{threshold_start}/{window_size}` es demasiado laxo y se acerca a una señal casi siempre activa",
            f"- `{window_size}/{window_size}` es demasiado estrecho y deja la señal casi muda",
            f"- umbral solicitado en esta ejecucion: `{resolved_min_positive}/{window_size}`",
            "",
            "## Recomendacion",
            "",
            "- mantener `SYA-15` en `analysis` semanal",
            "- no promover a `sidecar` global todavia",
            "- revisar de nuevo cuando haya mas historico en `trail_run` o `road_run`, o si cambian `vt1_used` / `vt2_used`",
        ]
    )
    return "\n".join(lines) + "\n"


def build_sport_report(
    sport: str,
    summary: pd.DataFrame,
    details: dict[str, pd.DataFrame],
    today: pd.Timestamp,
    input_path: Path = DEFAULT_INPUT,
    window_size: int = WINDOW_SIZE,
    min_positive: int | None = None,
) -> str:
    validate_report_window_size(window_size)
    _validate_report_summary(summary, window_size)
    if sport not in details:
        raise ValueError(f"Sport not found in details: {sport}")
    return _build_sport_report_validated(
        sport,
        summary,
        details,
        today,
        input_path,
        window_size,
        min_positive,
    )


def _build_report_payload_validated(
    sport: str,
    summary: pd.DataFrame,
    details: dict[str, pd.DataFrame],
    today: pd.Timestamp,
    input_path: Path,
    window_size: int,
    min_positive: int | None,
) -> dict[str, object]:
    summary_row = _summary_row_for_sport(summary, sport)
    detail = details[sport]
    episodes = detect_positive_episodes(detail, window_size=window_size)
    resolved_min_positive = _resolve_min_positive_unchecked(window_size, min_positive)
    detail_rows = detail.copy()
    detail_rows["window_start"] = detail_rows["window_start"].dt.strftime("%Y-%m-%d")
    detail_rows = detail_rows.astype(object).where(pd.notna(detail_rows), None)
    summary_records = _json_safe_records(summary)
    summary_row_dict = {key: _json_safe_value(value) for key, value in summary_row.to_dict().items()}

    return {
        "input": Path(input_path).as_posix(),
        "anchor_date": today.date().isoformat(),
        "window_size": window_size,
        "min_positive": resolved_min_positive,
        "focus_sport": sport,
        "summary": summary_records,
        "focus": {
            "sport": sport,
            "metrics": summary_row_dict,
            "episodes": [
                {
                    "episode_start": pd.Timestamp(row.episode_start).date().isoformat(),
                    "episode_end": pd.Timestamp(row.episode_end).date().isoformat(),
                    "positive_weeks": int(row.positive_weeks),
                }
                for row in episodes.itertuples(index=False)
            ],
            "detail": detail_rows.to_dict(orient="records"),
        },
    }


def build_report_payload(
    sport: str,
    summary: pd.DataFrame,
    details: dict[str, pd.DataFrame],
    today: pd.Timestamp,
    input_path: Path,
    window_size: int = WINDOW_SIZE,
    min_positive: int | None = None,
) -> dict[str, object]:
    validate_report_window_size(window_size)
    _validate_report_summary(summary, window_size)
    if sport not in details:
        raise ValueError(f"Sport not found in details: {sport}")
    return _build_report_payload_validated(
        sport,
        summary,
        details,
        today,
        input_path,
        window_size,
        min_positive,
    )


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    today = resolve_today(args.today)
    weekly = load_weekly(args.input)
    resolved_min_positive = resolve_min_positive(args.window_size, args.min_positive)
    summary, details = summarize_by_sport(
        weekly, today, window_size=args.window_size, min_positive=resolved_min_positive
    )

    print("SYA-15 continuity summary")
    print(f"Input: {args.input}")
    print(f"Today anchor: {today.date()}")
    print(f"Minimum positives in {args.window_size}w window: {resolved_min_positive}")
    print()
    print(format_summary(summary))

    selected_sports: list[str]
    if args.show_all_details:
        selected_sports = list(summary["sport"])
    elif args.sports:
        selected_sports = args.sports
    else:
        selected_sports = []

    for sport in selected_sports:
        if sport not in details:
            raise ValueError(f"Sport not found in input: {sport}")
        print()
        print(f"Detail for {sport}")
        print(format_detail(details[sport], window_size=args.window_size))

    if args.report_md is not None:
        report_focus_sport = resolve_report_focus_sport(summary, args.focus_sport)
        report = build_sport_report(
            report_focus_sport,
            summary,
            details,
            today,
            input_path=args.input,
            window_size=args.window_size,
            min_positive=resolved_min_positive,
        )
        args.report_md.parent.mkdir(parents=True, exist_ok=True)
        args.report_md.write_text(report, encoding="utf-8")

    if args.report_json is not None:
        report_focus_sport = resolve_report_focus_sport(summary, args.focus_sport)
        payload = build_report_payload(
            report_focus_sport,
            summary,
            details,
            today,
            args.input,
            window_size=args.window_size,
            min_positive=resolved_min_positive,
        )
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
