import argparse
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import hrv_app.hrv_sync_flow as hrv_sync_flow
from hrv_app.dropbox_rr import DropboxRRResult


class _Result:
    stdout = "core ok"


class HrvSyncFlowContractTests(unittest.TestCase):
    def test_ai_daily_brief_best_effort_never_raises(self):
        with patch.object(hrv_sync_flow, "run_ai_daily_brief_for_latest_date", side_effect=ValueError("bad final csv")), patch.object(
            hrv_sync_flow, "_render_report"
        ) as render_mock:
            result = hrv_sync_flow._run_ai_daily_brief_best_effort()

        render_mock.assert_called_once()
        self.assertIn("AI daily brief: error", render_mock.call_args.args[0]["lines"][0])
        self.assertEqual(result, {"status": "error", "outcome": "request_error"})

    def test_optional_ai_and_intervals_errors_degrade_without_invalidating_canonicals(self):
        result = hrv_sync_flow.PipelineResult()
        hrv_sync_flow._record_optional_stage(
            result,
            "ai_daily",
            {"status": "validation_failed", "outcome": "validation_failed"},
        )
        with patch.object(
            hrv_sync_flow,
            "_send_intervals_wellness_from_master",
            return_value={"status": "error", "outcome": "request_error"},
        ):
            hrv_sync_flow._sync_intervals_wellness(result)

        self.assertEqual(result.status, "degraded")
        self.assertTrue(result.canonical_valid)
        self.assertEqual(
            [stage["stage"] for stage in result.degraded_stages],
            ["ai_daily", "intervals_wellness"],
        )

    def test_disabled_optional_stage_is_traced_without_affecting_health(self):
        result = hrv_sync_flow.PipelineResult()

        hrv_sync_flow._record_optional_stage(
            result,
            "ai_daily",
            {"status": "disabled", "outcome": "disabled"},
        )

        self.assertEqual(result.status, "ok")
        self.assertTrue(result.canonical_valid)
        self.assertEqual(result.stages, [{"stage": "ai_daily", "status": "not_requested", "outcome": "disabled"}])

    def test_no_new_rr_auto_flow_without_process_shows_summaries_and_skips_sleep_refresh(self):
        args = argparse.Namespace(
            all=False,
            auto=True,
            days=None,
            process=False,
            debug_sports=False,
            verbose=False,
        )

        with patch.object(hrv_sync_flow, "get_last_date_from_master", return_value=date(2026, 3, 3)), patch.object(
            hrv_sync_flow, "calculate_missing_days", return_value=(0, date(2026, 3, 3))
        ), patch.object(hrv_sync_flow, "_scan_rr_files_by_date") as scan_mock, patch.object(
            hrv_sync_flow, "_print_sync_completed"
        ) as sync_mock, patch.object(hrv_sync_flow, "show_latest_hrv_summaries") as summary_mock, patch.object(
            hrv_sync_flow, "_refresh_sleep_and_outputs"
        ) as refresh_mock, patch.object(
            hrv_sync_flow, "_send_intervals_wellness_from_master"
        ) as intervals_mock:
            hrv_sync_flow.sync_hrv_range(args, "token", "user", [])

        scan_mock.assert_not_called()
        sync_mock.assert_called_once()
        refresh_mock.assert_not_called()
        intervals_mock.assert_called_once()
        summary_mock.assert_called_once()

    def test_no_new_rr_default_flow_with_process_sends_wellness(self):
        args = argparse.Namespace(
            all=False,
            auto=False,
            days=None,
            process=True,
            debug_sports=False,
            verbose=False,
        )

        with patch.object(hrv_sync_flow, "get_last_date_from_master", return_value=date(2026, 3, 3)), patch.object(
            hrv_sync_flow, "calculate_missing_days", return_value=(0, date(2026, 3, 3))
        ), patch.object(hrv_sync_flow, "_scan_rr_files_by_date") as scan_mock, patch.object(
            hrv_sync_flow, "_print_sync_completed"
        ) as sync_mock, patch.object(hrv_sync_flow, "show_latest_hrv_summaries") as summary_mock, patch.object(
            hrv_sync_flow, "_refresh_sleep_and_outputs"
        ) as refresh_mock, patch.object(
            hrv_sync_flow, "_send_intervals_wellness_from_master"
        ) as intervals_mock:
            hrv_sync_flow.sync_hrv_range(args, "token", "user", [])

        scan_mock.assert_not_called()
        sync_mock.assert_called_once()
        refresh_mock.assert_called_once()
        intervals_mock.assert_called_once()
        summary_mock.assert_called_once()

    def test_failed_sleep_refresh_stops_before_wellness(self):
        args = argparse.Namespace(
            all=False,
            auto=False,
            days=None,
            process=True,
            debug_sports=False,
            verbose=False,
        )
        failed = hrv_sync_flow.PipelineResult().fail(
            "sleep", "sleep_write_failed", "No se pudo escribir sleep.csv"
        )

        with patch.object(hrv_sync_flow, "get_last_date_from_master", return_value=date(2026, 3, 3)), \
             patch.object(hrv_sync_flow, "calculate_missing_days", return_value=(0, date(2026, 3, 3))), \
             patch.object(hrv_sync_flow, "_refresh_sleep_and_outputs", return_value=failed), \
             patch.object(hrv_sync_flow, "_send_intervals_wellness_from_master") as intervals_mock, \
             patch.object(hrv_sync_flow, "show_latest_hrv_summaries"):
            result = hrv_sync_flow.sync_hrv_range(args, "token", "user", [])

        intervals_mock.assert_not_called()
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.stage, "sleep")

    def test_empty_core_with_local_rr_reprocesses_local_files(self):
        args = argparse.Namespace(
            all=False,
            auto=False,
            days=None,
            process=True,
            debug_sports=False,
            verbose=False,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            rr_path = Path(tmpdir) / "PolarUser_2026-04-13_07-00-00_RR.CSV"
            with patch.object(hrv_sync_flow, "OUTDIR", Path(tmpdir)), patch.object(
                hrv_sync_flow, "get_last_date_from_master", return_value=None
            ), patch.object(
                hrv_sync_flow, "_scan_rr_files_by_date", return_value={date(2026, 4, 13): rr_path}
            ), patch.object(
                hrv_sync_flow, "get_existing_dates_from_master", return_value=set()
            ), patch.object(
                hrv_sync_flow, "_run_dropbox_rr_import_for_dates"
            ) as dropbox_mock, patch.object(
                hrv_sync_flow, "run_build_hrv_core", return_value=_Result()
            ) as run_core_mock, patch.object(
                hrv_sync_flow, "run_build_hrv_final_dashboard_only"
            ) as final_mock, patch.object(
                hrv_sync_flow, "run_build_hrv_ssm_shadow_only", return_value=True
            ) as ssm_mock, patch.object(hrv_sync_flow, "_run_ai_daily_brief_best_effort") as ai_mock, patch.object(hrv_sync_flow, "_update_sleep_for_dates_result") as sleep_mock, patch.object(
                hrv_sync_flow, "_send_intervals_wellness_from_master"
            ) as intervals_mock, patch.object(hrv_sync_flow, "show_latest_hrv_summaries") as summary_mock:
                hrv_sync_flow.sync_hrv_range(args, "token", "user", [])

        dropbox_mock.assert_not_called()
        run_core_mock.assert_called_once_with([rr_path])
        final_mock.assert_called_once()
        ssm_mock.assert_called_once()
        ai_mock.assert_called_once()
        sleep_mock.assert_called_once()
        intervals_mock.assert_called_once()
        summary_mock.assert_called_once()

    def test_days_mode_with_dropbox_coverage_processes_rr(self):
        args = argparse.Namespace(
            all=False,
            auto=False,
            days=1,
            process=True,
            debug_sports=False,
            verbose=False,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            rr_path = Path(tmpdir) / "PolarUser_2026-04-13_07-00-00_RR.CSV"
            dropbox_map = {date(2026, 4, 13): rr_path}
            with patch.object(hrv_sync_flow, "OUTDIR", Path(tmpdir)), patch.object(
                hrv_sync_flow, "get_existing_dates_from_master", return_value=set()
            ), patch.object(
                hrv_sync_flow, "_run_dropbox_rr_import_for_dates", return_value=DropboxRRResult(dropbox_map, 1)
            ) as dropbox_mock, patch.object(
                hrv_sync_flow, "_promote_operational_rr_files", return_value=1
            ) as promote_mock, patch.object(
                hrv_sync_flow, "run_build_hrv_core", return_value=_Result()
            ) as run_core_mock, patch.object(
                hrv_sync_flow, "run_build_hrv_final_dashboard_only"
            ) as final_mock, patch.object(
                hrv_sync_flow, "run_build_hrv_ssm_shadow_only", return_value=True
            ) as ssm_mock, patch.object(hrv_sync_flow, "_run_ai_daily_brief_best_effort") as ai_mock, patch.object(hrv_sync_flow, "_update_sleep_for_dates_result") as sleep_mock, patch.object(
                hrv_sync_flow, "_send_intervals_wellness_from_master"
            ) as intervals_mock, patch.object(hrv_sync_flow, "show_latest_hrv_summaries") as summary_mock:
                hrv_sync_flow.sync_hrv_range(args, "token", "user", [])

        dropbox_mock.assert_called_once()
        run_core_mock.assert_called_once_with([rr_path])
        promote_mock.assert_called_once_with([rr_path], Path(tmpdir))
        final_mock.assert_called_once()
        ssm_mock.assert_called_once()
        ai_mock.assert_called_once()
        sleep_mock.assert_called_once()
        intervals_mock.assert_called_once()
        summary_mock.assert_called_once()

    def test_days_mode_without_dropbox_coverage_skips_processing(self):
        args = argparse.Namespace(
            all=False,
            auto=False,
            days=1,
            process=True,
            debug_sports=False,
            verbose=False,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(hrv_sync_flow, "OUTDIR", Path(tmpdir)), patch.object(
                hrv_sync_flow, "get_existing_dates_from_master", return_value=set()
            ), patch.object(
                hrv_sync_flow, "_run_dropbox_rr_import_for_dates", return_value=DropboxRRResult({}, 0, outcome="no_data")
            ) as dropbox_mock, patch.object(hrv_sync_flow, "run_build_hrv_core") as run_core_mock, patch.object(
                hrv_sync_flow, "_refresh_sleep_and_outputs"
            ) as refresh_mock, patch.object(
                hrv_sync_flow, "_send_intervals_wellness_from_master"
            ) as intervals_mock, patch.object(hrv_sync_flow, "show_latest_hrv_summaries") as summary_mock:
                hrv_sync_flow.sync_hrv_range(args, "token", "user", [])

        dropbox_mock.assert_called_once()
        run_core_mock.assert_not_called()
        refresh_mock.assert_called_once()
        intervals_mock.assert_called_once()
        summary_mock.assert_called_once()

    def test_days_mode_all_dates_already_in_core(self):
        args = argparse.Namespace(
            all=False,
            auto=False,
            days=1,
            process=True,
            debug_sports=False,
            verbose=False,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(hrv_sync_flow, "OUTDIR", Path(tmpdir)), patch.object(
                hrv_sync_flow, "get_existing_dates_from_master", return_value=set()
            ), patch.object(
                hrv_sync_flow, "_compute_target_missing_dates", return_value=[]
            ), patch.object(hrv_sync_flow, "_print_master_already_updated") as already_mock, patch.object(
                hrv_sync_flow, "_run_dropbox_rr_import_for_dates"
            ) as dropbox_mock, patch.object(hrv_sync_flow, "_refresh_sleep_and_outputs") as refresh_mock, patch.object(
                hrv_sync_flow, "_send_intervals_wellness_from_master"
            ) as intervals_mock, patch.object(hrv_sync_flow, "show_latest_hrv_summaries") as summary_mock:
                hrv_sync_flow.sync_hrv_range(args, "token", "user", [])

        already_mock.assert_called_once()
        dropbox_mock.assert_not_called()
        refresh_mock.assert_called_once()
        intervals_mock.assert_called_once()
        summary_mock.assert_called_once()

    def test_days_mode_process_false_sends_wellness_without_builders(self):
        args = argparse.Namespace(
            all=False,
            auto=False,
            days=1,
            process=False,
            debug_sports=False,
            verbose=False,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            rr_path = Path(tmpdir) / "PolarUser_2026-04-13_07-00-00_RR.CSV"
            dropbox_map = {date(2026, 4, 13): rr_path}
            with patch.object(hrv_sync_flow, "OUTDIR", Path(tmpdir)), patch.object(
                hrv_sync_flow, "get_existing_dates_from_master", return_value=set()
            ), patch.object(
                hrv_sync_flow, "_run_dropbox_rr_import_for_dates", return_value=DropboxRRResult(dropbox_map, 1)
            ), patch.object(hrv_sync_flow, "run_build_hrv_core") as run_core_mock, patch.object(
                hrv_sync_flow, "_send_intervals_wellness_from_master"
            ) as intervals_mock, patch.object(hrv_sync_flow, "show_latest_hrv_summaries") as summary_mock:
                hrv_sync_flow.sync_hrv_range(args, "token", "user", [])

        run_core_mock.assert_not_called()
        intervals_mock.assert_called_once()
        summary_mock.assert_called_once()

    def test_core_failure_stops_before_sleep_or_final_dashboard(self):
        args = argparse.Namespace(
            all=False,
            auto=False,
            days=1,
            process=True,
            debug_sports=False,
            verbose=False,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            rr_path = Path(tmpdir) / "PolarUser_2026-04-13_07-00-00_RR.CSV"
            dropbox_map = {date(2026, 4, 13): rr_path}
            with patch.object(hrv_sync_flow, "OUTDIR", Path(tmpdir)), patch.object(
                hrv_sync_flow, "get_existing_dates_from_master", return_value=set()
            ), patch.object(
                hrv_sync_flow, "_run_dropbox_rr_import_for_dates", return_value=DropboxRRResult(dropbox_map, 1)
            ), patch.object(hrv_sync_flow, "_promote_operational_rr_files") as promote_mock, patch.object(hrv_sync_flow, "run_build_hrv_core", return_value=None), patch.object(
                hrv_sync_flow, "run_build_hrv_final_dashboard_only"
            ) as final_mock, patch.object(hrv_sync_flow, "run_build_hrv_ssm_shadow_only") as ssm_mock, patch.object(
                hrv_sync_flow, "_run_ai_daily_brief_best_effort"
            ) as ai_mock, patch.object(
                hrv_sync_flow, "_update_sleep_for_dates_result"
            ) as sleep_mock, patch.object(
                hrv_sync_flow, "_send_intervals_wellness_from_master"
            ) as intervals_mock, patch.object(hrv_sync_flow, "show_latest_hrv_summaries") as summary_mock:
                hrv_sync_flow.sync_hrv_range(args, "token", "user", [])

        final_mock.assert_not_called()
        ssm_mock.assert_not_called()
        promote_mock.assert_not_called()
        ai_mock.assert_not_called()
        sleep_mock.assert_not_called()
        intervals_mock.assert_not_called()
        summary_mock.assert_not_called()

    def test_ssm_failure_does_not_abort_successful_hrv_processing(self):
        args = argparse.Namespace(
            all=False,
            auto=False,
            days=1,
            process=True,
            debug_sports=False,
            verbose=False,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            rr_path = Path(tmpdir) / "PolarUser_2026-04-13_07-00-00_RR.CSV"
            dropbox_map = {date(2026, 4, 13): rr_path}
            with patch.object(hrv_sync_flow, "OUTDIR", Path(tmpdir)), patch.object(
                hrv_sync_flow, "get_existing_dates_from_master", return_value=set()
            ), patch.object(
                hrv_sync_flow, "_run_dropbox_rr_import_for_dates", return_value=DropboxRRResult(dropbox_map, 1)
            ), patch.object(hrv_sync_flow, "run_build_hrv_core", return_value=_Result()), patch.object(
                hrv_sync_flow, "run_build_hrv_final_dashboard_only"
            ) as final_mock, patch.object(
                hrv_sync_flow, "run_build_hrv_ssm_shadow_only", return_value=False
            ) as ssm_mock, patch.object(hrv_sync_flow, "_run_ai_daily_brief_best_effort") as ai_mock, patch.object(hrv_sync_flow, "_update_sleep_for_dates_result") as sleep_mock, patch.object(
                hrv_sync_flow, "_send_intervals_wellness_from_master"
            ) as intervals_mock, patch.object(hrv_sync_flow, "show_latest_hrv_summaries") as summary_mock:
                hrv_sync_flow.sync_hrv_range(args, "token", "user", [])

        final_mock.assert_called_once()
        ssm_mock.assert_called_once()
        ai_mock.assert_called_once()
        sleep_mock.assert_called_once()
        intervals_mock.assert_called_once()
        summary_mock.assert_called_once()

    def test_sleep_not_ready_degrades_but_final_still_runs(self):
        args = argparse.Namespace(
            all=False,
            auto=False,
            days=1,
            process=True,
            debug_sports=False,
            verbose=False,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            rr_path = Path(tmpdir) / "PolarUser_2026-04-13_07-00-00_RR.CSV"
            dropbox_map = {date(2026, 4, 13): rr_path}
            with patch.object(hrv_sync_flow, "OUTDIR", Path(tmpdir)), patch.object(
                hrv_sync_flow, "get_existing_dates_from_master", return_value=set()
            ), patch.object(
                hrv_sync_flow, "_run_dropbox_rr_import_for_dates", return_value=DropboxRRResult(dropbox_map, 1)
            ), patch.object(hrv_sync_flow, "run_build_hrv_core", return_value=_Result()), patch.object(
                hrv_sync_flow, "_promote_operational_rr_files"
            ), patch.object(hrv_sync_flow, "_update_sleep_for_dates_result", return_value={
                "pending": [{"date": "2026-04-13", "outcome": "no_data_yet"}],
                "failed": [],
            }), patch.object(
                hrv_sync_flow, "run_build_hrv_final_dashboard_only", return_value=True
            ), patch.object(hrv_sync_flow, "run_build_hrv_ssm_shadow_only", return_value=True), patch.object(
                hrv_sync_flow, "_run_ai_daily_brief_best_effort"
            ), patch.object(hrv_sync_flow, "_run_ai_ssm_brief_best_effort"), patch.object(
                hrv_sync_flow, "_send_intervals_wellness_from_master"
            ), patch.object(hrv_sync_flow, "show_latest_hrv_summaries"):
                result = hrv_sync_flow.sync_hrv_range(args, "token", "user", [])

        self.assertEqual(result.status, "degraded")
        self.assertTrue(result.success)
        self.assertEqual(result.pending_sleep_dates, ["2026-04-13"])

    def test_sleep_transport_error_is_visible_as_degraded_source_error(self):
        result = hrv_sync_flow.PipelineResult()
        hrv_sync_flow._apply_sleep_update_result(
            result,
            {
                "pending": [{"date": "2026-04-13", "outcome": "request_error"}],
                "failed": [],
            },
        )

        self.assertEqual(result.status, "degraded")
        self.assertTrue(result.success)
        self.assertTrue(result.canonical_valid)
        self.assertEqual(result.degraded_stages[0]["outcome"], "request_error")
        self.assertEqual(result.degraded_stages[0]["error"]["code"], "sleep_transport_failed")

    def test_sleep_fetch_failure_preserves_cause_and_stays_retryable(self):
        result = hrv_sync_flow.PipelineResult()
        hrv_sync_flow._apply_sleep_update_result(
            result,
            {"pending": [], "failed": [{
                "date": "2026-04-13",
                "outcome": "request_error",
                "error": {"code": "sleep_fetch_failed", "message": "No se pudo consultar Polar sleep"},
            }]},
        )

        self.assertEqual(result.status, "degraded")
        self.assertTrue(result.canonical_valid)
        self.assertEqual(result.pending_sleep_dates, ["2026-04-13"])
        self.assertEqual(result.degraded_stages[0]["error"]["code"], "sleep_transport_failed")

    def test_sleep_write_failure_preserves_original_error(self):
        result = hrv_sync_flow.PipelineResult()
        hrv_sync_flow._apply_sleep_update_result(
            result,
            {"pending": [], "failed": [{
                "date": "2026-04-13",
                "outcome": "write_error",
                "error": {"code": "sleep_write_failed", "message": "No se pudo escribir sleep.csv"},
            }]},
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error["code"], "sleep_write_failed")

    def test_all_mode_processes_local_rr_files(self):
        args = argparse.Namespace(
            all=True,
            auto=False,
            days=None,
            process=True,
            debug_sports=False,
            verbose=False,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            rr_path = Path(tmpdir) / "PolarUser_2026-04-13_07-00-00_RR.CSV"
            with patch.object(hrv_sync_flow, "OUTDIR", Path(tmpdir)), patch.object(
                hrv_sync_flow, "_scan_rr_files_by_date", return_value={date(2026, 4, 13): rr_path}
            ), patch.object(hrv_sync_flow, "get_existing_dates_from_master", return_value=set()), patch.object(
                hrv_sync_flow, "_run_dropbox_rr_import_for_dates"
            ) as dropbox_mock, patch.object(
                hrv_sync_flow, "run_build_hrv_core", return_value=_Result()
            ) as run_core_mock, patch.object(
                hrv_sync_flow, "run_build_hrv_final_dashboard_only"
            ) as final_mock, patch.object(
                hrv_sync_flow, "run_build_hrv_ssm_shadow_only", return_value=True
            ) as ssm_mock, patch.object(hrv_sync_flow, "_run_ai_daily_brief_best_effort") as ai_mock, patch.object(hrv_sync_flow, "_update_sleep_for_dates_result") as sleep_mock, patch.object(
                hrv_sync_flow, "_send_intervals_wellness_from_master"
            ) as intervals_mock, patch.object(hrv_sync_flow, "show_latest_hrv_summaries") as summary_mock:
                hrv_sync_flow.sync_hrv_range(args, "token", "user", [])

        dropbox_mock.assert_not_called()
        run_core_mock.assert_called_once_with([rr_path])
        final_mock.assert_called_once()
        ssm_mock.assert_called_once()
        ai_mock.assert_called_once()
        sleep_mock.assert_called_once()
        intervals_mock.assert_called_once()
        summary_mock.assert_called_once()

    def test_default_mode_with_backlog_over_30_days_requests_full_dropbox_range(self):
        last_date = date.today() - timedelta(days=45)
        args = argparse.Namespace(
            all=False,
            auto=False,
            days=None,
            process=True,
            debug_sports=False,
            verbose=False,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(hrv_sync_flow, "OUTDIR", Path(tmpdir)), patch.object(
                hrv_sync_flow, "get_last_date_from_master", return_value=last_date
            ), patch.object(
                hrv_sync_flow, "get_existing_dates_from_master", return_value=set()
            ), patch.object(
                hrv_sync_flow, "_run_dropbox_rr_import_for_dates", return_value=DropboxRRResult({}, 0, outcome="no_data")
            ) as dropbox_mock, patch.object(hrv_sync_flow, "_refresh_sleep_and_outputs"), patch.object(
                hrv_sync_flow, "_send_intervals_wellness_from_master"
            ), patch.object(hrv_sync_flow, "show_latest_hrv_summaries"):
                hrv_sync_flow.sync_hrv_range(args, "token", "user", [])

        target_dates = dropbox_mock.call_args[0][0]
        self.assertEqual(len(target_dates), 45)
        self.assertEqual(min(target_dates), last_date + timedelta(days=1))
        self.assertEqual(max(target_dates), date.today())

    def test_default_mode_with_backlog_over_30_days_does_not_suggest_all(self):
        last_date = date.today() - timedelta(days=45)
        args = argparse.Namespace(
            all=False,
            auto=False,
            days=None,
            process=True,
            debug_sports=False,
            verbose=False,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(hrv_sync_flow, "OUTDIR", Path(tmpdir)), patch.object(
                hrv_sync_flow, "get_last_date_from_master", return_value=last_date
            ), patch.object(
                hrv_sync_flow, "get_existing_dates_from_master", return_value=set()
            ), patch.object(
                hrv_sync_flow, "_run_dropbox_rr_import_for_dates", return_value=DropboxRRResult({}, 0, outcome="no_data")
            ), patch.object(hrv_sync_flow, "_refresh_sleep_and_outputs"), patch.object(
                hrv_sync_flow, "_send_intervals_wellness_from_master"
            ), patch.object(hrv_sync_flow, "show_latest_hrv_summaries"), patch("builtins.print") as print_mock:
                hrv_sync_flow.sync_hrv_range(args, "token", "user", [])

        printed = " ".join(str(call.args[0]) for call in print_mock.call_args_list if call.args)
        self.assertNotIn("--all", printed)

    def test_all_mode_without_local_rr_exits_cleanly(self):
        args = argparse.Namespace(
            all=True,
            auto=False,
            days=None,
            process=True,
            debug_sports=False,
            verbose=False,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(hrv_sync_flow, "OUTDIR", Path(tmpdir)), patch.object(
                hrv_sync_flow, "_scan_rr_files_by_date", return_value={}
            ), patch.object(hrv_sync_flow, "get_existing_dates_from_master", return_value=set()), patch.object(
                hrv_sync_flow, "_print_no_local_rr_files"
            ) as no_rr_mock, patch.object(
                hrv_sync_flow, "_run_dropbox_rr_import_for_dates"
            ) as dropbox_mock, patch.object(hrv_sync_flow, "run_build_hrv_core") as run_core_mock, patch.object(
                hrv_sync_flow, "_refresh_sleep_and_outputs"
            ) as refresh_mock, patch.object(
                hrv_sync_flow, "_send_intervals_wellness_from_master"
            ) as intervals_mock, patch.object(hrv_sync_flow, "show_latest_hrv_summaries") as summary_mock:
                hrv_sync_flow.sync_hrv_range(args, "token", "user", [])

        no_rr_mock.assert_called_once()
        dropbox_mock.assert_not_called()
        run_core_mock.assert_not_called()
        refresh_mock.assert_called_once()
        intervals_mock.assert_called_once()
        summary_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
