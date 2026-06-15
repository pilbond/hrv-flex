import argparse
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import hrv_app.hrv_sync_flow as hrv_sync_flow


class _Result:
    stdout = "core ok"


class HrvSyncFlowContractTests(unittest.TestCase):
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
            ) as ssm_mock, patch.object(hrv_sync_flow, "_update_sleep_for_dates") as sleep_mock, patch.object(
                hrv_sync_flow, "_send_intervals_wellness_from_master"
            ) as intervals_mock, patch.object(hrv_sync_flow, "show_latest_hrv_summaries") as summary_mock:
                hrv_sync_flow.sync_hrv_range(args, "token", "user", [])

        dropbox_mock.assert_not_called()
        run_core_mock.assert_called_once_with([rr_path])
        final_mock.assert_called_once()
        ssm_mock.assert_called_once()
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
                hrv_sync_flow, "_run_dropbox_rr_import_for_dates", return_value=(dropbox_map, 1)
            ) as dropbox_mock, patch.object(
                hrv_sync_flow, "run_build_hrv_core", return_value=_Result()
            ) as run_core_mock, patch.object(
                hrv_sync_flow, "run_build_hrv_final_dashboard_only"
            ) as final_mock, patch.object(
                hrv_sync_flow, "run_build_hrv_ssm_shadow_only", return_value=True
            ) as ssm_mock, patch.object(hrv_sync_flow, "_update_sleep_for_dates") as sleep_mock, patch.object(
                hrv_sync_flow, "_send_intervals_wellness_from_master"
            ) as intervals_mock, patch.object(hrv_sync_flow, "show_latest_hrv_summaries") as summary_mock:
                hrv_sync_flow.sync_hrv_range(args, "token", "user", [])

        dropbox_mock.assert_called_once()
        run_core_mock.assert_called_once_with([rr_path])
        final_mock.assert_called_once()
        ssm_mock.assert_called_once()
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
                hrv_sync_flow, "_run_dropbox_rr_import_for_dates", return_value=({}, 0)
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
                hrv_sync_flow, "_run_dropbox_rr_import_for_dates", return_value=(dropbox_map, 1)
            ), patch.object(hrv_sync_flow, "run_build_hrv_core") as run_core_mock, patch.object(
                hrv_sync_flow, "_send_intervals_wellness_from_master"
            ) as intervals_mock, patch.object(hrv_sync_flow, "show_latest_hrv_summaries") as summary_mock:
                hrv_sync_flow.sync_hrv_range(args, "token", "user", [])

        run_core_mock.assert_not_called()
        intervals_mock.assert_called_once()
        summary_mock.assert_called_once()

    def test_core_failure_refreshes_sleep_without_final_dashboard(self):
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
                hrv_sync_flow, "_run_dropbox_rr_import_for_dates", return_value=(dropbox_map, 1)
            ), patch.object(hrv_sync_flow, "run_build_hrv_core", return_value=None), patch.object(
                hrv_sync_flow, "run_build_hrv_final_dashboard_only"
            ) as final_mock, patch.object(hrv_sync_flow, "run_build_hrv_ssm_shadow_only") as ssm_mock, patch.object(
                hrv_sync_flow, "_update_sleep_for_dates"
            ) as sleep_mock, patch.object(
                hrv_sync_flow, "_send_intervals_wellness_from_master"
            ) as intervals_mock, patch.object(hrv_sync_flow, "show_latest_hrv_summaries") as summary_mock:
                hrv_sync_flow.sync_hrv_range(args, "token", "user", [])

        final_mock.assert_not_called()
        ssm_mock.assert_not_called()
        sleep_mock.assert_called_once()
        intervals_mock.assert_called_once()
        summary_mock.assert_called_once()

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
                hrv_sync_flow, "_run_dropbox_rr_import_for_dates", return_value=(dropbox_map, 1)
            ), patch.object(hrv_sync_flow, "run_build_hrv_core", return_value=_Result()), patch.object(
                hrv_sync_flow, "run_build_hrv_final_dashboard_only"
            ) as final_mock, patch.object(
                hrv_sync_flow, "run_build_hrv_ssm_shadow_only", return_value=False
            ) as ssm_mock, patch.object(hrv_sync_flow, "_update_sleep_for_dates") as sleep_mock, patch.object(
                hrv_sync_flow, "_send_intervals_wellness_from_master"
            ) as intervals_mock, patch.object(hrv_sync_flow, "show_latest_hrv_summaries") as summary_mock:
                hrv_sync_flow.sync_hrv_range(args, "token", "user", [])

        final_mock.assert_called_once()
        ssm_mock.assert_called_once()
        sleep_mock.assert_called_once()
        intervals_mock.assert_called_once()
        summary_mock.assert_called_once()

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
            ) as ssm_mock, patch.object(hrv_sync_flow, "_update_sleep_for_dates") as sleep_mock, patch.object(
                hrv_sync_flow, "_send_intervals_wellness_from_master"
            ) as intervals_mock, patch.object(hrv_sync_flow, "show_latest_hrv_summaries") as summary_mock:
                hrv_sync_flow.sync_hrv_range(args, "token", "user", [])

        dropbox_mock.assert_not_called()
        run_core_mock.assert_called_once_with([rr_path])
        final_mock.assert_called_once()
        ssm_mock.assert_called_once()
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
                hrv_sync_flow, "_run_dropbox_rr_import_for_dates", return_value=({}, 0)
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
                hrv_sync_flow, "_run_dropbox_rr_import_for_dates", return_value=({}, 0)
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
