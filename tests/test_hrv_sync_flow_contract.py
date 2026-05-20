import argparse
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import hrv_app.hrv_sync_flow as hrv_sync_flow


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

        with patch.object(hrv_sync_flow, "calculate_missing_days", return_value=(0, date(2026, 3, 3))), patch.object(
            hrv_sync_flow, "_print_sync_completed"
        ) as sync_mock, patch.object(hrv_sync_flow, "show_latest_hrv_summaries") as summary_mock, patch.object(
            hrv_sync_flow, "_refresh_sleep_and_outputs"
        ) as refresh_mock:
            hrv_sync_flow.sync_hrv_range(args, "token", "user", [])

        sync_mock.assert_called_once()
        refresh_mock.assert_not_called()
        summary_mock.assert_called_once()

    def test_all_mode_processes_without_date_bounds(self):
        args = argparse.Namespace(
            all=True,
            auto=False,
            days=None,
            process=False,
            debug_sports=False,
            verbose=False,
        )
        exercises = [
            {
                "id": "abc123",
                "start-time": "2026-04-13T07:00:00",
                "duration": "PT5M",
                "detailed-sport-info": "BODY_AND_MIND",
            }
        ]
        sample_session = {
            "id": "abc123",
            "start-time": "2026-04-13T07:00:00",
            "samples": [{"sample-type": "11", "data": "800,810,820"}],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(hrv_sync_flow, "OUTDIR", Path(tmpdir)), patch.object(
                hrv_sync_flow, "get_existing_dates_from_master", return_value=set()
            ) as existing_mock, patch.object(hrv_sync_flow, "get_exercise_with_samples") as samples_mock, patch.object(
                hrv_sync_flow, "write_rr_csv"
            ) as write_mock, patch.object(
                hrv_sync_flow, "_run_dropbox_rr_import_for_dates", return_value=({}, 0)
            ) as dropbox_mock, patch.object(
                hrv_sync_flow, "_send_intervals_wellness_from_master"
            ) as intervals_mock, patch.object(
                hrv_sync_flow, "show_latest_hrv_summaries"
            ) as summary_mock:
                samples_mock.return_value = sample_session
                hrv_sync_flow.sync_hrv_range(args, "token", "user", exercises)

        self.assertGreaterEqual(existing_mock.call_count, 1)
        samples_mock.assert_called_once_with("token", "abc123")
        write_mock.assert_called_once()
        dropbox_mock.assert_not_called()
        intervals_mock.assert_called_once()
        summary_mock.assert_not_called()

    def test_auto_mode_with_missing_days_enters_processing_flow(self):
        args = argparse.Namespace(
            all=False,
            auto=True,
            days=None,
            process=False,
            debug_sports=False,
            verbose=False,
        )
        exercises = [
            {
                "id": "abc123",
                "start-time": "2026-04-13T07:00:00",
                "duration": "PT5M",
                "detailed-sport-info": "BODY_AND_MIND",
            }
        ]
        sample_session = {
            "id": "abc123",
            "start-time": "2026-04-13T07:00:00",
            "samples": [{"sample-type": "11", "data": "800,810,820"}],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(hrv_sync_flow, "OUTDIR", Path(tmpdir)), patch.object(
                hrv_sync_flow, "calculate_missing_days", return_value=(3, date(2026, 4, 10))
            ), patch.object(hrv_sync_flow, "get_existing_dates_from_master", return_value=set()) as existing_mock, patch.object(
                hrv_sync_flow, "_run_dropbox_rr_import_for_dates", return_value=({}, 0)
            ) as dropbox_mock, patch.object(
                hrv_sync_flow, "get_exercise_with_samples", return_value=sample_session
            ) as samples_mock, patch.object(hrv_sync_flow, "write_rr_csv") as write_mock, patch.object(
                hrv_sync_flow, "_update_sleep_for_dates"
            ) as sleep_mock, patch.object(
                hrv_sync_flow, "_send_intervals_wellness_from_master"
            ) as intervals_mock, patch.object(hrv_sync_flow, "show_latest_hrv_summaries") as summary_mock:
                hrv_sync_flow.sync_hrv_range(args, "token", "user", exercises)

        self.assertGreaterEqual(existing_mock.call_count, 1)
        dropbox_mock.assert_called_once()
        samples_mock.assert_called_once_with("token", "abc123")
        write_mock.assert_called_once()
        sleep_mock.assert_not_called()
        intervals_mock.assert_called_once()
        summary_mock.assert_not_called()

    def test_process_false_with_rr_new_skips_core_and_final(self):
        args = argparse.Namespace(
            all=False,
            auto=False,
            days=1,
            process=False,
            debug_sports=False,
            verbose=False,
        )
        exercises = [
            {
                "id": "abc123",
                "start-time": "2026-04-13T07:00:00",
                "duration": "PT5M",
                "detailed-sport-info": "BODY_AND_MIND",
            }
        ]
        sample_session = {
            "id": "abc123",
            "start-time": "2026-04-13T07:00:00",
            "samples": [{"sample-type": "11", "data": "800,810,820"}],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(hrv_sync_flow, "OUTDIR", Path(tmpdir)), patch.object(
                hrv_sync_flow, "get_existing_dates_from_master", return_value=set()
            ), patch.object(hrv_sync_flow, "_run_dropbox_rr_import_for_dates", return_value=({}, 0)), patch.object(
                hrv_sync_flow, "get_exercise_with_samples", return_value=sample_session
            ), patch.object(hrv_sync_flow, "build_hrv_core_cmd") as build_core_mock, patch.object(
                hrv_sync_flow, "run_build_hrv_core"
            ) as run_core_mock, patch.object(hrv_sync_flow, "run_build_hrv_final_dashboard_only") as final_mock, patch.object(
                hrv_sync_flow, "_update_sleep_for_dates"
            ) as sleep_mock, patch.object(
                hrv_sync_flow, "_send_intervals_wellness_from_master"
            ) as intervals_mock, patch.object(hrv_sync_flow, "show_latest_hrv_summaries") as summary_mock:
                hrv_sync_flow.sync_hrv_range(args, "token", "user", exercises)

        build_core_mock.assert_not_called()
        run_core_mock.assert_not_called()
        final_mock.assert_not_called()
        sleep_mock.assert_not_called()
        intervals_mock.assert_called_once()
        summary_mock.assert_not_called()

    def test_process_flow_with_rr_new_runs_core_and_final(self):
        args = argparse.Namespace(
            all=False,
            auto=False,
            days=1,
            process=True,
            debug_sports=False,
            verbose=False,
        )
        exercises = [
            {
                "id": "abc123",
                "start-time": "2026-04-13T07:00:00",
                "duration": "PT5M",
                "detailed-sport-info": "BODY_AND_MIND",
            }
        ]

        class _Result:
            stdout = "core ok"

        sample_session = {
            "id": "abc123",
            "start-time": "2026-04-13T07:00:00",
            "samples": [{"sample-type": "11", "data": "800,810,820"}],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(hrv_sync_flow, "OUTDIR", Path(tmpdir)), patch.object(
                hrv_sync_flow, "get_existing_dates_from_master", return_value=set()
            ), patch.object(hrv_sync_flow, "_run_dropbox_rr_import_for_dates", return_value=({}, 0)), patch.object(
                hrv_sync_flow, "get_exercise_with_samples", return_value=sample_session
            ), patch.object(hrv_sync_flow, "build_hrv_core_cmd", return_value=["python", "build_hrv_core.py", "rr.csv"]
            ) as build_core_mock, patch.object(hrv_sync_flow, "run_build_hrv_core", return_value=_Result()) as run_core_mock, patch.object(
                hrv_sync_flow, "run_build_hrv_final_dashboard_only"
            ) as final_mock, patch.object(
                hrv_sync_flow, "run_build_hrv_ssm_shadow_only", return_value=True
            ) as ssm_mock, patch.object(
                hrv_sync_flow, "run_build_hrv_ssm_validation_only", return_value=True
            ) as validation_mock, patch.object(hrv_sync_flow, "_update_sleep_for_dates") as sleep_mock, patch.object(
                hrv_sync_flow, "_send_intervals_wellness_from_master"
            ) as intervals_mock, patch.object(hrv_sync_flow, "show_latest_hrv_summaries") as summary_mock:
                hrv_sync_flow.sync_hrv_range(args, "token", "user", exercises)

        build_core_mock.assert_called_once()
        run_core_mock.assert_called_once()
        final_mock.assert_called_once()
        ssm_mock.assert_called_once()
        validation_mock.assert_called_once()
        sleep_mock.assert_called_once()
        intervals_mock.assert_called_once()
        summary_mock.assert_called_once()

    def test_empty_rr_samples_are_skipped_before_pipeline(self):
        args = argparse.Namespace(
            all=False,
            auto=False,
            days=1,
            process=True,
            debug_sports=False,
            verbose=False,
        )
        exercises = [
            {
                "id": "abc123",
                "start-time": "2026-04-13T07:00:00",
                "duration": "PT5M",
                "detailed-sport-info": "BODY_AND_MIND",
            }
        ]
        sample_session = {
            "id": "abc123",
            "start-time": "2026-04-13T07:00:00",
            "samples": [{"sample-type": "10", "data": "1,2,3"}],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(hrv_sync_flow, "OUTDIR", Path(tmpdir)), patch.object(
                hrv_sync_flow, "get_existing_dates_from_master", return_value=set()
            ), patch.object(hrv_sync_flow, "_run_dropbox_rr_import_for_dates", return_value=({}, 0)), patch.object(
                hrv_sync_flow, "get_exercise_with_samples", return_value=sample_session
            ), patch.object(hrv_sync_flow, "write_rr_csv") as write_mock, patch.object(
                hrv_sync_flow, "build_hrv_core_cmd"
            ) as build_core_mock, patch.object(hrv_sync_flow, "run_build_hrv_core") as run_core_mock, patch.object(
                hrv_sync_flow, "run_build_hrv_final_dashboard_only"
            ) as final_mock, patch.object(
                hrv_sync_flow, "run_build_hrv_ssm_shadow_only", return_value=True
            ) as ssm_mock, patch.object(hrv_sync_flow, "_update_sleep_for_dates") as sleep_mock, patch.object(
                hrv_sync_flow, "_send_intervals_wellness_from_master"
            ) as intervals_mock, patch.object(hrv_sync_flow, "show_latest_hrv_summaries") as summary_mock:
                hrv_sync_flow.sync_hrv_range(args, "token", "user", exercises)

        write_mock.assert_not_called()
        build_core_mock.assert_not_called()
        run_core_mock.assert_not_called()
        final_mock.assert_called_once()
        ssm_mock.assert_not_called()
        sleep_mock.assert_called_once()
        intervals_mock.assert_called_once()
        summary_mock.assert_called_once()

    def test_dropbox_only_flow_processes_rr_files_when_no_polar_sessions_match(self):
        args = argparse.Namespace(
            all=False,
            auto=False,
            days=1,
            process=True,
            debug_sports=False,
            verbose=False,
        )
        exercises = [
            {
                "id": "abc123",
                "start-time": "2026-04-13T07:00:00",
                "duration": "PT30M",
                "detailed-sport-info": "RUNNING",
            }
        ]

        class _Result:
            stdout = "core ok"

        with tempfile.TemporaryDirectory() as tmpdir:
            rr_path = Path(tmpdir) / "dropbox_rr.csv"
            dropbox_map = {date(2026, 4, 13): rr_path}
            with patch.object(hrv_sync_flow, "OUTDIR", Path(tmpdir)), patch.object(
                hrv_sync_flow, "DROPBOX_RR_ENABLED", True
            ), patch.object(
                hrv_sync_flow, "get_existing_dates_from_master", return_value=set()
            ), patch.object(
                hrv_sync_flow, "_run_dropbox_rr_import_for_dates", return_value=(dropbox_map, 1)
            ) as dropbox_mock, patch.object(
                hrv_sync_flow, "build_hrv_core_cmd", return_value=["python", "build_hrv_core.py", str(rr_path)]
            ) as build_core_mock, patch.object(
                hrv_sync_flow, "run_build_hrv_core", return_value=_Result()
            ) as run_core_mock, patch.object(
                hrv_sync_flow, "run_build_hrv_final_dashboard_only"
            ) as final_mock, patch.object(
                hrv_sync_flow, "run_build_hrv_ssm_shadow_only", return_value=True
            ) as ssm_mock, patch.object(
                hrv_sync_flow, "run_build_hrv_ssm_validation_only", return_value=True
            ) as validation_mock, patch.object(
                hrv_sync_flow, "_update_sleep_for_dates"
            ) as sleep_mock, patch.object(
                hrv_sync_flow, "_send_intervals_wellness_from_master"
            ) as intervals_mock, patch.object(
                hrv_sync_flow, "show_latest_hrv_summaries"
            ) as summary_mock:
                hrv_sync_flow.sync_hrv_range(args, "token", "user", exercises)

        dropbox_mock.assert_called_once()
        build_core_mock.assert_called_once_with([rr_path])
        run_core_mock.assert_called_once_with([rr_path])
        final_mock.assert_called_once()
        ssm_mock.assert_called_once()
        validation_mock.assert_called_once()
        sleep_mock.assert_called_once()
        intervals_mock.assert_called_once()
        summary_mock.assert_called_once()

    def test_rr_write_error_is_handled_without_crashing_pipeline(self):
        args = argparse.Namespace(
            all=False,
            auto=False,
            days=1,
            process=True,
            debug_sports=False,
            verbose=False,
        )
        exercises = [
            {
                "id": "abc123",
                "start-time": "2026-04-13T07:00:00",
                "duration": "PT5M",
                "detailed-sport-info": "BODY_AND_MIND",
            }
        ]
        sample_session = {
            "id": "abc123",
            "start-time": "2026-04-13T07:00:00",
            "samples": [{"sample-type": "11", "data": "800,810,820"}],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(hrv_sync_flow, "OUTDIR", Path(tmpdir)), patch.object(
                hrv_sync_flow, "get_existing_dates_from_master", return_value=set()
            ), patch.object(hrv_sync_flow, "_run_dropbox_rr_import_for_dates", return_value=({}, 0)), patch.object(
                hrv_sync_flow, "get_exercise_with_samples", return_value=sample_session
            ), patch.object(hrv_sync_flow, "open", side_effect=OSError("disk full")), patch.object(
                hrv_sync_flow, "build_hrv_core_cmd"
            ) as build_core_mock, patch.object(hrv_sync_flow, "run_build_hrv_core") as run_core_mock, patch.object(
                hrv_sync_flow, "run_build_hrv_final_dashboard_only"
            ) as final_mock, patch.object(hrv_sync_flow, "_update_sleep_for_dates") as sleep_mock, patch.object(
                hrv_sync_flow, "_send_intervals_wellness_from_master"
            ) as intervals_mock, patch.object(hrv_sync_flow, "show_latest_hrv_summaries") as summary_mock:
                hrv_sync_flow.sync_hrv_range(args, "token", "user", exercises)

        build_core_mock.assert_not_called()
        run_core_mock.assert_not_called()
        final_mock.assert_called_once()
        sleep_mock.assert_called_once()
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
        exercises = [
            {
                "id": "abc123",
                "start-time": "2026-04-13T07:00:00",
                "duration": "PT5M",
                "detailed-sport-info": "BODY_AND_MIND",
            }
        ]

        class _Result:
            stdout = "core ok"

        sample_session = {
            "id": "abc123",
            "start-time": "2026-04-13T07:00:00",
            "samples": [{"sample-type": "11", "data": "800,810,820"}],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(hrv_sync_flow, "OUTDIR", Path(tmpdir)), patch.object(
                hrv_sync_flow, "get_existing_dates_from_master", return_value=set()
            ), patch.object(hrv_sync_flow, "_run_dropbox_rr_import_for_dates", return_value=({}, 0)), patch.object(
                hrv_sync_flow, "get_exercise_with_samples", return_value=sample_session
            ), patch.object(hrv_sync_flow, "build_hrv_core_cmd", return_value=["python", "build_hrv_core.py", "rr.csv"]
            ), patch.object(hrv_sync_flow, "run_build_hrv_core", return_value=None), patch.object(
                hrv_sync_flow, "run_build_hrv_final_dashboard_only"
            ) as final_mock, patch.object(
                hrv_sync_flow, "run_build_hrv_ssm_shadow_only", return_value=True
            ) as ssm_mock, patch.object(
                hrv_sync_flow, "run_build_hrv_ssm_validation_only", return_value=True
            ) as validation_mock, patch.object(hrv_sync_flow, "_update_sleep_for_dates") as sleep_mock, patch.object(
                hrv_sync_flow, "_send_intervals_wellness_from_master"
            ) as intervals_mock, patch.object(hrv_sync_flow, "show_latest_hrv_summaries") as summary_mock:
                hrv_sync_flow.sync_hrv_range(args, "token", "user", exercises)

        final_mock.assert_not_called()
        ssm_mock.assert_not_called()
        validation_mock.assert_not_called()
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
        exercises = [
            {
                "id": "abc123",
                "start-time": "2026-04-13T07:00:00",
                "duration": "PT5M",
                "detailed-sport-info": "BODY_AND_MIND",
            }
        ]

        class _Result:
            stdout = "core ok"

        sample_session = {
            "id": "abc123",
            "start-time": "2026-04-13T07:00:00",
            "samples": [{"sample-type": "11", "data": "800,810,820"}],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(hrv_sync_flow, "OUTDIR", Path(tmpdir)), patch.object(
                hrv_sync_flow, "get_existing_dates_from_master", return_value=set()
            ), patch.object(hrv_sync_flow, "_run_dropbox_rr_import_for_dates", return_value=({}, 0)), patch.object(
                hrv_sync_flow, "get_exercise_with_samples", return_value=sample_session
            ), patch.object(hrv_sync_flow, "build_hrv_core_cmd", return_value=["python", "build_hrv_core.py", "rr.csv"]
            ), patch.object(hrv_sync_flow, "run_build_hrv_core", return_value=_Result()), patch.object(
                hrv_sync_flow, "run_build_hrv_final_dashboard_only"
            ) as final_mock, patch.object(
                hrv_sync_flow, "run_build_hrv_ssm_shadow_only", return_value=False
            ) as ssm_mock, patch.object(
                hrv_sync_flow, "run_build_hrv_ssm_validation_only", return_value=True
            ) as validation_mock, patch.object(hrv_sync_flow, "_update_sleep_for_dates") as sleep_mock, patch.object(
                hrv_sync_flow, "_send_intervals_wellness_from_master"
            ) as intervals_mock, patch.object(hrv_sync_flow, "show_latest_hrv_summaries") as summary_mock:
                hrv_sync_flow.sync_hrv_range(args, "token", "user", exercises)

        final_mock.assert_called_once()
        ssm_mock.assert_called_once()
        validation_mock.assert_not_called()
        sleep_mock.assert_called_once()
        intervals_mock.assert_called_once()
        summary_mock.assert_called_once()

    def test_validation_failure_does_not_abort_successful_ssm_processing(self):
        args = argparse.Namespace(
            all=False,
            auto=False,
            days=1,
            process=True,
            debug_sports=False,
            verbose=False,
        )
        exercises = [
            {
                "id": "abc123",
                "start-time": "2026-04-13T07:00:00",
                "duration": "PT5M",
                "detailed-sport-info": "BODY_AND_MIND",
            }
        ]

        class _Result:
            stdout = "core ok"

        sample_session = {
            "id": "abc123",
            "start-time": "2026-04-13T07:00:00",
            "samples": [{"sample-type": "11", "data": "800,810,820"}],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(hrv_sync_flow, "OUTDIR", Path(tmpdir)), patch.object(
                hrv_sync_flow, "get_existing_dates_from_master", return_value=set()
            ), patch.object(hrv_sync_flow, "_run_dropbox_rr_import_for_dates", return_value=({}, 0)), patch.object(
                hrv_sync_flow, "get_exercise_with_samples", return_value=sample_session
            ), patch.object(hrv_sync_flow, "build_hrv_core_cmd", return_value=["python", "build_hrv_core.py", "rr.csv"]
            ), patch.object(hrv_sync_flow, "run_build_hrv_core", return_value=_Result()), patch.object(
                hrv_sync_flow, "run_build_hrv_final_dashboard_only"
            ) as final_mock, patch.object(
                hrv_sync_flow, "run_build_hrv_ssm_shadow_only", return_value=True
            ) as ssm_mock, patch.object(
                hrv_sync_flow, "run_build_hrv_ssm_validation_only", return_value=False
            ) as validation_mock, patch.object(hrv_sync_flow, "_update_sleep_for_dates") as sleep_mock, patch.object(
                hrv_sync_flow, "_send_intervals_wellness_from_master"
            ) as intervals_mock, patch.object(hrv_sync_flow, "show_latest_hrv_summaries") as summary_mock:
                hrv_sync_flow.sync_hrv_range(args, "token", "user", exercises)

        final_mock.assert_called_once()
        ssm_mock.assert_called_once()
        validation_mock.assert_called_once()
        sleep_mock.assert_called_once()
        intervals_mock.assert_called_once()
        summary_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
