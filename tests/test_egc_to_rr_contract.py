import unittest
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import egc_to_rr
import pandas as pd


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class EgcToRrContractTests(unittest.TestCase):
    def test_dropbox_file_matches_target_date_from_cloud_path(self):
        file_entry = egc_to_rr.FileEntry(
            source="dropbox",
            name="ACC.jsonl",
            parent="2026/06/19",
            sort_key=0.0,
            cloud_id="/hrv/raw_jsonl/PolarRecording_20260619_071500/ACC.jsonl",
        )

        self.assertTrue(egc_to_rr._matches_target_dates(file_entry, {"2026-06-19"}))
        self.assertFalse(egc_to_rr._matches_target_dates(file_entry, {"2026-06-18"}))

    def test_list_dropbox_input_files_filters_to_requested_dates(self):
        payload = {
            "entries": [
                {
                    ".tag": "file",
                    "name": "ECG.jsonl",
                    "path_lower": "/hrv/raw_jsonl/PolarRecording_20260618_071500/ECG.jsonl",
                    "path_display": "/HRV/raw_jsonl/PolarRecording_20260618_071500/ECG.jsonl",
                    "server_modified": "2026-06-18T07:20:00Z",
                },
                {
                    ".tag": "file",
                    "name": "ACC.jsonl",
                    "path_lower": "/hrv/raw_jsonl/PolarRecording_20260619_071500/ACC.jsonl",
                    "path_display": "/HRV/raw_jsonl/PolarRecording_20260619_071500/ACC.jsonl",
                    "server_modified": "2026-06-19T07:20:00Z",
                },
            ],
            "has_more": False,
        }

        with patch.object(egc_to_rr.requests, "post", return_value=_FakeResponse(200, payload)) as post_mock:
            files = egc_to_rr.list_dropbox_input_files(
                "token",
                "/HRV/raw_jsonl",
                recursive=True,
                target_dates={"2026-06-19"},
            )

        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].name, "ACC.jsonl")
        self.assertIn("20260619", files[0].cloud_id)
        post_mock.assert_called_once()

    def test_process_pair_writes_canonical_rr_without_versioning(self):
        rr_events = pd.DataFrame({"duration_ms": [1000.0, 980.0], "offline": [0, 1], "reason": ["OK", "DELTA_RR_GT_20P"]})
        acc_windows = pd.DataFrame({"start_s": [0.0], "end_s": [1.0]})
        resp_rate = pd.DataFrame({"t0_s": [0.0], "t1_s": [30.0], "resp_rate_bpm": [12.0]})

        with TemporaryDirectory() as tmpdir:
            outdir = Path(tmpdir)
            canonical = outdir / "ENDURANCE_2026-06-19_from_jsonl_RR.CSV"
            versioned = outdir / "ENDURANCE_2026-06-19_from_jsonl_v2_RR.CSV"
            canonical.write_text("duration,offline\n111,0\n", encoding="utf-8")
            versioned.write_text("duration,offline\n222,0\n", encoding="utf-8")
            (outdir / "ECG.jsonl").write_text("ecg", encoding="utf-8")
            (outdir / "ACC.jsonl").write_text("acc", encoding="utf-8")

            with (
                patch.object(egc_to_rr, "extract_ecg", return_value=([0.0, 1.0], [0.1, 0.2], [], "rec")),
                patch.object(egc_to_rr, "extract_acc", return_value=([0.0, 1.0], [0.0, 0.0], [0.0, 0.0], [0.0, 0.0], [], "rec")),
                patch.object(egc_to_rr, "normalize_ts_seconds", side_effect=lambda arr: (arr, "s")),
                patch.object(egc_to_rr, "sort_unique", side_effect=lambda *arrs: arrs),
                patch.object(egc_to_rr, "infer_session_date", return_value=("2026-06-19", None)),
                patch.object(egc_to_rr, "detect_rpeaks", return_value=([1], 130.0)),
                patch.object(egc_to_rr, "rr_events", return_value=rr_events),
                patch.object(egc_to_rr, "acc_high_motion_windows", return_value=(acc_windows, 0.1)),
                patch.object(egc_to_rr, "resp_rate_from_acc", return_value=resp_rate),
                patch.object(egc_to_rr, "fs_est", return_value=52.0),
            ):
                pair_args = dict(
                    ecg_path=outdir / "ECG.jsonl",
                    acc_path=outdir / "ACC.jsonl",
                    outdir=outdir,
                    aux_dir=outdir,
                    prefix="ENDURANCE",
                    write_aux=False,
                )
                result = egc_to_rr.process_pair(**pair_args)
                published_rr = canonical.read_bytes()
                canonical.write_text("previous RR\n", encoding="utf-8")
                with patch.object(egc_to_rr, "_write_json_atomic", side_effect=OSError("diagnostic write failed")):
                    with self.assertRaises(OSError):
                        egc_to_rr.process_pair(**pair_args)
                self.assertEqual(canonical.read_text(encoding="utf-8"), "previous RR\n")
                canonical.write_bytes(published_rr)

            self.assertEqual(result["rr_path"].name, canonical.name)
            self.assertTrue(canonical.exists())
            self.assertTrue(versioned.exists())
            self.assertEqual(canonical.read_text(encoding="utf-8"), "duration,offline\n1000.0,0\n980.0,1\n")
            diagnostic = json.loads(result["diagnostic_path"].read_text(encoding="utf-8"))
            reasons = pd.read_csv(result["reasons_path"])
            self.assertEqual(diagnostic["reason_counts"], {"OK": 1, "DELTA_RR_GT_20P": 1})
            self.assertEqual(diagnostic["rr_sha256"], hashlib.sha256(canonical.read_bytes()).hexdigest())
            self.assertEqual(diagnostic["reasons_sha256"], hashlib.sha256(result["reasons_path"].read_bytes()).hexdigest())
            self.assertEqual(reasons.to_dict("list"), {"rr_index": [0, 1], "reason": ["OK", "DELTA_RR_GT_20P"]})
            self.assertEqual(diagnostic["offline_count"], 1)


if __name__ == "__main__":
    unittest.main()
