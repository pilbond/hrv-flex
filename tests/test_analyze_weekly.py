import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from analysis import analyze_weekly as MODULE
from analysis import sya15_continuity

# Algunos tests consumen los CSV personales reales de data/ (no versionados);
# en CI no existen y se omiten con razón explícita.
_REAL_DATA_AVAILABLE = Path("data/ENDURANCE_HRV_intensity_distribution_weekly.csv").exists()
requires_real_data = unittest.skipUnless(
    _REAL_DATA_AVAILABLE, "requiere los CSV personales de data/ (no disponibles en CI)"
)


class AnalyzeWeeklyTests(unittest.TestCase):
    def test_render_weekly_report_labels_low_load_week_as_relative_deload(self):
        week_dates = MODULE.pd.date_range("2026-05-11", periods=7, freq="D")
        context = {
            "week_start": MODULE.pd.Timestamp("2026-05-11"),
            "week_end": MODULE.pd.Timestamp("2026-05-17"),
            "weekly_coach": {"week_type": "recovery", "week_load": 120},
            "calendar": MODULE.pd.DataFrame({"Fecha": week_dates}),
            "sessions_week": MODULE.pd.DataFrame(
                [{"Fecha": MODULE.pd.Timestamp("2026-05-13"), "sport": "swim"}]
            ),
            "sessions_day_week": MODULE.pd.DataFrame(
                [
                    {"Fecha": MODULE.pd.Timestamp("2026-05-11"), "load_day": 10, "work_total_min_day": 0, "z3_min_day": 0},
                    {"Fecha": MODULE.pd.Timestamp("2026-05-12"), "load_day": 15, "work_total_min_day": 0, "z3_min_day": 0},
                    {"Fecha": MODULE.pd.Timestamp("2026-05-13"), "load_day": 12, "work_total_min_day": 0, "z3_min_day": 0},
                    {"Fecha": MODULE.pd.Timestamp("2026-05-14"), "load_day": 9, "work_total_min_day": 0, "z3_min_day": 0},
                    {"Fecha": MODULE.pd.Timestamp("2026-05-15"), "load_day": 11, "work_total_min_day": 0, "z3_min_day": 0},
                    {"Fecha": MODULE.pd.Timestamp("2026-05-16"), "load_day": 8, "work_total_min_day": 0, "z3_min_day": 0},
                    {"Fecha": MODULE.pd.Timestamp("2026-05-17"), "load_day": 10, "work_total_min_day": 0, "z3_min_day": 0},
                ]
            ),
            "dashboard_week": MODULE.pd.DataFrame(
                [{"Fecha": d, "gate_badge": "green", "Action": "GO"} for d in week_dates]
            ),
            "sleep_week": MODULE.pd.DataFrame(
                [
                    {
                        "Fecha": d,
                        "polar_sleep_duration_min": 420,
                        "polar_deep_pct": 18,
                        "polar_sleep_score": 78,
                        "polar_efficiency_pct": 92.5,
                    }
                    for d in week_dates
                ]
            ),
            "distribution_week": MODULE.pd.DataFrame(),
            "core": MODULE.pd.DataFrame(
                {
                    "Fecha": MODULE.pd.to_datetime(["2026-05-11", "2026-05-13", "2026-05-15"]),
                    "Calidad": ["OK", "OK", "OK"],
                    "RMSSD_stable": [52, 51, 53],
                    "HR_stable": [42, 43, 41],
                }
            ),
        }
        manifest = {
            "manifest_path": "C:/tmp/weekly_prep_manifest.json",
            "sidecars": [],
        }

        with mock.patch.object(
            MODULE,
            "_build_load_comparison",
            return_value=(
                MODULE.pd.DataFrame(
                    [
                        {"week_start": "2026-04-20", "load_total": 210.0},
                        {"week_start": "2026-04-27", "load_total": 205.0},
                        {"week_start": "2026-05-04", "load_total": 215.0},
                        {"week_start": "2026-05-11", "load_total": 75.0},
                    ]
                ),
                210.0,
            ),
        ):
            report = MODULE.render_weekly_report(
                today=sya15_continuity.resolve_today("2026-05-15"),
                manifest=manifest,
                context=context,
            )

        self.assertIn("Semana reducida o de descarga relativa.", report)
        self.assertNotIn("Semana exigente con pico de carga relativo.", report)

    def test_build_hrv_weekly_trend_builds_eight_weeks(self):
        core = MODULE.pd.DataFrame(
            {
                "Fecha": MODULE.pd.to_datetime(
                    [
                        "2026-03-23",
                        "2026-03-30",
                        "2026-04-06",
                        "2026-04-13",
                        "2026-04-20",
                        "2026-04-27",
                        "2026-05-04",
                        "2026-05-11",
                    ]
                ),
                "Calidad": ["OK"] * 8,
                "RMSSD_stable": [50, 51, 52, 53, 54, 55, 56, 57],
                "HR_stable": [40, 41, 42, 43, 44, 45, 46, 47],
            }
        )
        table = MODULE._build_hrv_weekly_trend(core, MODULE.pd.Timestamp("2026-05-11"))
        self.assertEqual(len(table), 8)
        self.assertEqual(table.iloc[0]["Semana"], "2026-03-23")
        self.assertEqual(table.iloc[-1]["Semana"], "2026-05-11")
        self.assertEqual(int(table.iloc[-1]["n días OK"]), 1)

    def test_build_divergences_flags_structured_load_against_easy_action(self):
        dashboard_week = MODULE.pd.DataFrame(
            [
                {"Fecha": MODULE.pd.Timestamp("2026-05-11"), "gate_badge": "yellow", "Action": "SUAVE_O_DESCANSO"},
                {"Fecha": MODULE.pd.Timestamp("2026-05-12"), "gate_badge": "green", "Action": "GO"},
            ]
        )
        sessions_day_week = MODULE.pd.DataFrame(
            [
                {"Fecha": MODULE.pd.Timestamp("2026-05-11"), "load_day": 55, "work_total_min_day": 20, "z3_min_day": 8},
                {"Fecha": MODULE.pd.Timestamp("2026-05-12"), "load_day": 30, "work_total_min_day": 0, "z3_min_day": 0},
            ]
        )
        divergences = MODULE._build_divergences(
            {
                "dashboard_week": dashboard_week,
                "sessions_day_week": sessions_day_week,
            }
        )
        self.assertEqual(len(divergences), 1)
        self.assertIn("2026-05-11", divergences[0])
        self.assertIn("SUAVE_O_DESCANSO", divergences[0])

    def test_build_divergences_degrades_if_optional_session_columns_are_missing(self):
        dashboard_week = MODULE.pd.DataFrame(
            [{"Fecha": MODULE.pd.Timestamp("2026-05-11"), "gate_badge": "yellow", "Action": "SUAVE_O_DESCANSO"}]
        )
        sessions_day_week = MODULE.pd.DataFrame(
            [{"Fecha": MODULE.pd.Timestamp("2026-05-11"), "load_day": 55}]
        )
        divergences = MODULE._build_divergences(
            {
                "dashboard_week": dashboard_week,
                "sessions_day_week": sessions_day_week,
            }
        )
        self.assertEqual(divergences, [])

    def test_build_context_payload_exposes_manifest_and_week_bounds(self):
        context = {
            "week_start": MODULE.pd.Timestamp("2026-05-11"),
            "week_end": MODULE.pd.Timestamp("2026-05-17"),
            "calendar": MODULE.pd.DataFrame({"Fecha": MODULE.pd.date_range("2026-05-11", periods=7, freq="D")}),
            "sessions_week": MODULE.pd.DataFrame({"Fecha": [MODULE.pd.Timestamp("2026-05-11")]}),
            "distribution_week": MODULE.pd.DataFrame({"window_start": [MODULE.pd.Timestamp("2026-05-11")]}),
        }
        manifest = {
            "manifest_path": "C:/tmp/weekly_prep_manifest.json",
            "sidecars": [{"sidecar": "sya15_continuity"}],
        }
        payload = MODULE._build_context_payload(context, manifest)
        self.assertEqual(payload["week_start"], "2026-05-11")
        self.assertEqual(payload["week_end"], "2026-05-17")
        self.assertEqual(payload["manifest_path"], "C:/tmp/weekly_prep_manifest.json")
        self.assertEqual(payload["sidecars"], [{"sidecar": "sya15_continuity"}])
        self.assertEqual(payload["profile_rows"], 7)
        self.assertEqual(payload["sessions_week_count"], 1)
        self.assertEqual(payload["distribution_week_count"], 1)

    def test_build_profile_table_degrades_if_optional_session_columns_are_missing(self):
        context = {
            "calendar": MODULE.pd.DataFrame({"Fecha": MODULE.pd.date_range("2026-05-11", periods=2, freq="D")}),
            "sessions_day_week": MODULE.pd.DataFrame(
                [
                    {"Fecha": MODULE.pd.Timestamp("2026-05-11"), "load_day": 42},
                    {"Fecha": MODULE.pd.Timestamp("2026-05-12"), "load_day": 0},
                ]
            ),
            "dashboard_week": MODULE.pd.DataFrame(
                [
                    {"Fecha": MODULE.pd.Timestamp("2026-05-11"), "gate_badge": "green", "Action": "GO"},
                    {"Fecha": MODULE.pd.Timestamp("2026-05-12"), "gate_badge": "yellow", "Action": "SUAVE_O_DESCANSO"},
                ]
            ),
            "sleep_week": MODULE.pd.DataFrame(
                [
                    {"Fecha": MODULE.pd.Timestamp("2026-05-11"), "polar_sleep_duration_min": 420},
                    {"Fecha": MODULE.pd.Timestamp("2026-05-12"), "polar_sleep_duration_min": 410},
                ]
            ),
            "sessions_week": MODULE.pd.DataFrame(
                [{"Fecha": MODULE.pd.Timestamp("2026-05-11"), "sport": "bike"}]
            ),
        }
        profile = MODULE._build_profile_table(context)
        self.assertEqual(list(profile.columns), ["Dia", "Fecha", "Sueño", "gate_badge", "Action", "Sesion", "load_day", "work_total_min_day", "z3_min_day"])
        self.assertEqual(profile.iloc[0]["load_day"], "42")

    @requires_real_data
    def test_weekly_prompt_and_handoff_use_repo_relative_paths(self):
        weekly_dir = MODULE.Path("C:/Pilbond/polar-hrv-automation/analysis/reports/weekly/2026-05-11_2026-05-17")
        prompt = MODULE.build_weekly_analyst_prompt_markdown(
            weekly_dir=weekly_dir,
            manifest_path=weekly_dir / "weekly_prep_manifest.json",
            context_path=weekly_dir / "weekly_analysis_context.json",
            report_auto_path=weekly_dir / "report.auto.md",
            report_sync_token="abc123def456",
            sidecars=[
                {
                    "report_md": str(weekly_dir / "artifacts" / "sya15_continuity_bike_3of4w.md"),
                    "report_json": str(weekly_dir / "artifacts" / "sya15_continuity_bike_3of4w.json"),
                }
            ],
        )
        handoff = MODULE.build_weekly_ai_handoff_markdown(
            weekly_dir=weekly_dir,
            manifest_path=weekly_dir / "weekly_prep_manifest.json",
            context_path=weekly_dir / "weekly_analysis_context.json",
            report_auto_path=weekly_dir / "report.auto.md",
            report_sync_token="abc123def456",
            sidecars=[
                {
                    "report_md": str(weekly_dir / "artifacts" / "sya15_continuity_bike_3of4w.md"),
                    "report_json": str(weekly_dir / "artifacts" / "sya15_continuity_bike_3of4w.json"),
                }
            ],
        )
        self.assertIn("analysis/WEEKLY_ANALYSIS_METHOD.md", prompt)
        self.assertIn("analysis/reports/weekly/2026-05-11_2026-05-17/report.auto.md", prompt)
        self.assertNotIn("C:\\Pilbond\\polar-hrv-automation", prompt)
        self.assertIn("analysis/WEEKLY_ANALYSIS_METHOD.md", handoff)
        self.assertNotIn("C:\\Pilbond\\polar-hrv-automation", handoff)

    @requires_real_data
    def test_analyze_weekly_generates_report_and_context(self):
        with TemporaryDirectory() as tmpdir:
            weekly_dir = Path(tmpdir) / "weekly"
            payload = MODULE.analyze_weekly(
                today=sya15_continuity.resolve_today("2026-05-15"),
                weekly_dir=weekly_dir,
                input_path=Path("data/ENDURANCE_HRV_intensity_distribution_weekly.csv"),
                focus_sport=None,
                window_size=4,
                min_positive=None,
                skip_prep=False,
            )

            report_path = Path(payload["report_auto_md"])
            context_path = Path(payload["weekly_analysis_context"])
            analyst_prompt_path = Path(payload["analyst_prompt"])
            ai_handoff_path = Path(payload["ai_handoff"])
            final_report_path = Path(payload["report_ia_md"])
            report_sync_status_path = Path(payload["report_sync_status"])
            self.assertTrue(report_path.exists())
            self.assertTrue(context_path.exists())
            self.assertTrue(analyst_prompt_path.exists())
            self.assertTrue(ai_handoff_path.exists())
            self.assertTrue(final_report_path.exists())
            self.assertTrue(report_sync_status_path.exists())
            report = report_path.read_text(encoding="utf-8")
            self.assertIn("# Informe semanal · 2026-05-11 / 2026-05-17", report)
            self.assertIn("weekly_prep_manifest.json", report)
            self.assertIn("## 1. Perfil del microciclo", report)
            analyst_prompt = analyst_prompt_path.read_text(encoding="utf-8")
            ai_handoff = ai_handoff_path.read_text(encoding="utf-8")
            final_report = final_report_path.read_text(encoding="utf-8")
            report_sync_status = json.loads(report_sync_status_path.read_text(encoding="utf-8"))
            self.assertIn("# Weekly Analyst Prompt", analyst_prompt)
            self.assertIn("report.auto.md", analyst_prompt)
            self.assertIn("# Weekly AI Handoff", ai_handoff)
            self.assertIn("weekly_prep_manifest.json", ai_handoff)
            self.assertIn("<!-- report_sync_token:", final_report)
            self.assertEqual(report_sync_status["status"], "up_to_date")
            context = json.loads(context_path.read_text(encoding="utf-8"))
            self.assertEqual(context["week_start"], "2026-05-11")
            self.assertEqual(context["week_end"], "2026-05-17")

    @requires_real_data
    def test_analyze_weekly_can_reuse_existing_manifest(self):
        with TemporaryDirectory() as tmpdir:
            weekly_dir = Path(tmpdir) / "weekly"
            MODULE.run_weekly_analysis_prep.build_weekly_prep(
                today=sya15_continuity.resolve_today("2026-05-15"),
                weekly_dir=weekly_dir,
                input_path=Path("data/ENDURANCE_HRV_intensity_distribution_weekly.csv"),
                focus_sport=None,
                window_size=4,
                min_positive=None,
            )
            payload = MODULE.analyze_weekly(
                today=sya15_continuity.resolve_today("2026-05-15"),
                weekly_dir=weekly_dir,
                input_path=Path("data/ENDURANCE_HRV_intensity_distribution_weekly.csv"),
                focus_sport=None,
                window_size=4,
                min_positive=None,
                skip_prep=True,
            )
            self.assertTrue(Path(payload["report_auto_md"]).exists())

    @requires_real_data
    def test_analyze_weekly_skip_prep_tolerates_manifest_without_sya15(self):
        with TemporaryDirectory() as tmpdir:
            weekly_dir = Path(tmpdir) / "weekly"
            weekly_dir.mkdir(parents=True, exist_ok=True)
            manifest_path = weekly_dir / "weekly_prep_manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "prep_kind": "weekly_analysis_prep",
                        "week_start": "2026-05-11",
                        "week_end": "2026-05-17",
                        "anchor_date": "2026-05-15",
                        "weekly_dir": str(weekly_dir),
                        "artifacts_dir": str(weekly_dir / "artifacts"),
                        "sidecars": [],
                    }
                ),
                encoding="utf-8",
            )
            payload = MODULE.analyze_weekly(
                today=sya15_continuity.resolve_today("2026-05-15"),
                weekly_dir=weekly_dir,
                input_path=Path("data/ENDURANCE_HRV_intensity_distribution_weekly.csv"),
                focus_sport=None,
                window_size=4,
                min_positive=None,
                skip_prep=True,
            )
            report = Path(payload["report_auto_md"]).read_text(encoding="utf-8")
            self.assertIn("SYA-15 no está presente en este manifest semanal", report)
            self.assertEqual(report.count("No hay sidecar SYA-15 declarado en este manifest"), 1)

    @requires_real_data
    def test_analyze_weekly_skip_prep_with_missing_sya15_keeps_single_guidance_line(self):
        with TemporaryDirectory() as tmpdir:
            weekly_dir = Path(tmpdir) / "weekly"
            weekly_dir.mkdir(parents=True, exist_ok=True)
            (weekly_dir / "weekly_prep_manifest.json").write_text(
                json.dumps(
                    {
                        "prep_kind": "weekly_analysis_prep",
                        "week_start": "2026-05-11",
                        "week_end": "2026-05-17",
                        "anchor_date": "2026-05-15",
                        "weekly_dir": str(weekly_dir),
                        "artifacts_dir": str(weekly_dir / "artifacts"),
                        "sidecars": [],
                    }
                ),
                encoding="utf-8",
            )
            payload = MODULE.analyze_weekly(
                today=sya15_continuity.resolve_today("2026-05-15"),
                weekly_dir=weekly_dir,
                input_path=Path("data/ENDURANCE_HRV_intensity_distribution_weekly.csv"),
                focus_sport=None,
                window_size=4,
                min_positive=None,
                skip_prep=True,
            )
            report = Path(payload["report_auto_md"]).read_text(encoding="utf-8")
            expected = "No hay sidecar SYA-15 declarado en este manifest; si hace falta esa capa, regenerar el prep semanal."
            self.assertEqual(report.count(expected), 1)

    @requires_real_data
    def test_analyze_weekly_skip_prep_tolerates_duplicate_sya15_entries(self):
        with TemporaryDirectory() as tmpdir:
            weekly_dir = Path(tmpdir) / "weekly"
            weekly_dir.mkdir(parents=True, exist_ok=True)
            duplicate_sidecar = {
                "sidecar": "sya15_continuity",
                "report_md": str(weekly_dir / "artifacts" / "a.md"),
                "report_json": str(weekly_dir / "artifacts" / "a.json"),
                "focus_sport": "bike",
                "min_positive": 3,
                "window_size": 4,
            }
            (weekly_dir / "weekly_prep_manifest.json").write_text(
                json.dumps(
                    {
                        "prep_kind": "weekly_analysis_prep",
                        "week_start": "2026-05-11",
                        "week_end": "2026-05-17",
                        "anchor_date": "2026-05-15",
                        "weekly_dir": str(weekly_dir),
                        "artifacts_dir": str(weekly_dir / "artifacts"),
                        "sidecars": [duplicate_sidecar, duplicate_sidecar],
                    }
                ),
                encoding="utf-8",
            )
            payload = MODULE.analyze_weekly(
                today=sya15_continuity.resolve_today("2026-05-15"),
                weekly_dir=weekly_dir,
                input_path=Path("data/ENDURANCE_HRV_intensity_distribution_weekly.csv"),
                focus_sport=None,
                window_size=4,
                min_positive=None,
                skip_prep=True,
            )
            report = Path(payload["report_auto_md"]).read_text(encoding="utf-8")
            self.assertIn("SYA-15 no está presente en este manifest semanal", report)

    def test_weekly_report_sync_token_changes_when_sidecar_parameters_change(self):
        manifest_a = {
            "manifest_path": "analysis/reports/weekly/2026-05-11_2026-05-17/weekly_prep_manifest.json",
            "sidecars": [
                {
                    "sidecar": "sya15_continuity",
                    "focus_sport": "bike",
                    "window_size": 4,
                    "min_positive": 3,
                    "report_md": "a.md",
                    "report_json": "a.json",
                }
            ],
        }
        manifest_b = {
            "manifest_path": "analysis/reports/weekly/2026-05-11_2026-05-17/weekly_prep_manifest.json",
            "sidecars": [
                {
                    "sidecar": "sya15_continuity",
                    "focus_sport": "bike",
                    "window_size": 5,
                    "min_positive": 4,
                    "report_md": "b.md",
                    "report_json": "b.json",
                }
            ],
        }
        token_a = MODULE._weekly_report_sync_token(manifest_a, "2026-05-11", "2026-05-17")
        token_b = MODULE._weekly_report_sync_token(manifest_b, "2026-05-11", "2026-05-17")
        self.assertNotEqual(token_a, token_b)

    def test_analyze_weekly_skip_prep_rejects_manifest_for_different_week(self):
        with TemporaryDirectory() as tmpdir:
            weekly_dir = Path(tmpdir) / "weekly"
            weekly_dir.mkdir(parents=True, exist_ok=True)
            (weekly_dir / "weekly_prep_manifest.json").write_text(
                json.dumps(
                    {
                        "prep_kind": "weekly_analysis_prep",
                        "week_start": "2026-05-04",
                        "week_end": "2026-05-10",
                        "anchor_date": "2026-05-09",
                        "weekly_dir": str(weekly_dir),
                        "artifacts_dir": str(weekly_dir / "artifacts"),
                        "sidecars": [],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError,
                "Provided today does not match weekly_prep_manifest week_start:",
            ):
                MODULE.analyze_weekly(
                    today=sya15_continuity.resolve_today("2026-05-15"),
                    weekly_dir=weekly_dir,
                    input_path=Path("data/ENDURANCE_HRV_intensity_distribution_weekly.csv"),
                    focus_sport=None,
                    window_size=4,
                    min_positive=None,
                    skip_prep=True,
                )

    @requires_real_data
    def test_analyze_weekly_fails_with_clear_error_if_canonical_csv_is_missing(self):
        with TemporaryDirectory() as tmpdir:
            weekly_dir = Path(tmpdir) / "weekly"
            with mock.patch.object(MODULE, "DEFAULT_SESSIONS_DAY", Path(tmpdir) / "missing_sessions_day.csv"):
                with self.assertRaisesRegex(
                    FileNotFoundError,
                    "Missing required weekly analysis input \\(sessions_day\\):",
                ):
                    MODULE.analyze_weekly(
                        today=sya15_continuity.resolve_today("2026-05-15"),
                        weekly_dir=weekly_dir,
                        input_path=Path("data/ENDURANCE_HRV_intensity_distribution_weekly.csv"),
                        focus_sport=None,
                        window_size=4,
                        min_positive=None,
                        skip_prep=False,
                    )


if __name__ == "__main__":
    unittest.main()
