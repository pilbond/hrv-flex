import io
import json
import unittest
from contextlib import redirect_stdout

from hrv_app.pipeline_status import PIPELINE_RESULT_PREFIX, PipelineResult, result_from_marker


class PipelineStatusContractTests(unittest.TestCase):
    def test_marker_is_machine_parseable_and_preserves_degradation(self):
        result = PipelineResult()
        result.degrade("sleep", "pending", "sleep_not_ready", "Polar aún no publicó sleep")

        output = io.StringIO()
        with redirect_stdout(output):
            result.emit_marker()

        payload = result_from_marker("logs\n" + output.getvalue() + "post-atexit\n")
        self.assertEqual(payload["status"], "degraded")
        self.assertTrue(payload["success"])
        self.assertEqual(payload["degraded_stages"][0]["stage"], "sleep")

    def test_duplicate_or_invalid_markers_fail_closed(self):
        valid = PIPELINE_RESULT_PREFIX + json.dumps({"status": "ok"})
        self.assertIsNone(result_from_marker(valid + "\n" + valid))
        self.assertIsNone(result_from_marker(PIPELINE_RESULT_PREFIX + "not-json"))

    def test_marker_requires_complete_and_coherent_pipeline_contract(self):
        result = PipelineResult()
        result.ok("core")
        payload = result.to_dict()
        marker = PIPELINE_RESULT_PREFIX + json.dumps(payload)
        self.assertEqual(result_from_marker(marker), payload)

        contradictory = dict(payload, success=False)
        self.assertIsNone(result_from_marker(PIPELINE_RESULT_PREFIX + json.dumps(contradictory)))

        incomplete = dict(payload)
        incomplete.pop("stages")
        self.assertIsNone(result_from_marker(PIPELINE_RESULT_PREFIX + json.dumps(incomplete)))

    def test_required_failure_invalidates_canonical_result(self):
        result = PipelineResult()
        result.fail("core", "builder_failed", "CORE falló")
        payload = result.to_dict()
        self.assertEqual(payload["status"], "failed")
        self.assertFalse(payload["success"])
        self.assertFalse(payload["canonical_valid"])

    def test_optional_failed_stage_degrades_without_invalidating_canonicals(self):
        result = PipelineResult()
        result.degrade(
            "backup",
            "best_effort_error",
            "backup_failed",
            "Backup no disponible",
        )
        self.assertEqual(result.status, "degraded")
        self.assertTrue(result.success)
        self.assertTrue(result.canonical_valid)
        self.assertEqual(result.degraded_stages[0]["stage"], "backup")

    def test_merge_preserves_local_coverage_and_terminal_stage(self):
        result = PipelineResult()
        child = PipelineResult().set_source(status="not_requested", outcome="local_coverage")
        child.ok("dropbox_rr", "local_coverage")

        result.merge(child)

        self.assertEqual(result.source["outcome"], "local_coverage")
        self.assertEqual(result.stage, "dropbox_rr")


if __name__ == "__main__":
    unittest.main()
