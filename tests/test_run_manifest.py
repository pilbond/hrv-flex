import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hrv_app.run_manifest import (
    GenerationCoherenceError,
    file_digest,
    verify_generation_coherence,
)


class GenerationCoherenceTests(unittest.TestCase):
    def _write_generation(self, data_dir: Path) -> None:
        core = data_dir / "ENDURANCE_HRV_master_CORE.csv"
        beta_audit = data_dir / "ENDURANCE_HRV_master_BETA_AUDIT.csv"
        final = data_dir / "ENDURANCE_HRV_master_FINAL.csv"
        dashboard = data_dir / "ENDURANCE_HRV_master_DASHBOARD.csv"
        core_manifest = data_dir / "ENDURANCE_HRV_master_CORE_manifest.json"
        final_manifest = data_dir / "ENDURANCE_HRV_master_FINAL_manifest.json"

        core.write_text("Fecha,Calidad\n2026-11-10,OK\n", encoding="utf-8")
        beta_audit.write_text("Fecha,cRMSSD\n2026-11-10,42\n", encoding="utf-8")
        final.write_text("Fecha,gate_badge\n2026-11-10,VERDE\n", encoding="utf-8")
        dashboard.write_text("Fecha,gate_badge\n2026-11-10,VERDE\n", encoding="utf-8")
        core_payload = {
            "effective_config_hash": "core-config",
            "outputs": [
                {"role": "core", "sha256": file_digest(core)},
                {"role": "beta_audit", "sha256": file_digest(beta_audit)},
            ],
        }
        core_manifest.write_text(json.dumps(core_payload), encoding="utf-8")
        final_payload = {
            "source_manifest_sha256": file_digest(core_manifest),
            "source_manifest_effective_config_hash": "core-config",
            "outputs": [
                {"role": "final", "sha256": file_digest(final)},
                {"role": "dashboard", "sha256": file_digest(dashboard)},
            ],
        }
        final_manifest.write_text(json.dumps(final_payload), encoding="utf-8")

    def test_accepts_a_coherent_generation(self):
        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            self._write_generation(data_dir)
            self.assertIsNone(verify_generation_coherence(data_dir))

    def test_rejects_an_unreadable_manifest_and_partial_set(self):
        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            self._write_generation(data_dir)
            manifest = data_dir / "ENDURANCE_HRV_master_FINAL_manifest.json"
            manifest.write_text("{invalid", encoding="utf-8")
            with self.assertRaises(GenerationCoherenceError):
                verify_generation_coherence(data_dir)
            self._write_generation(data_dir)
            (data_dir / "ENDURANCE_HRV_master_DASHBOARD.csv").unlink()
            with self.assertRaises(GenerationCoherenceError):
                verify_generation_coherence(data_dir)

    def test_rejects_a_missing_manifest(self):
        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            self._write_generation(data_dir)
            (data_dir / "ENDURANCE_HRV_master_FINAL_manifest.json").unlink()
            with self.assertRaises(GenerationCoherenceError):
                verify_generation_coherence(data_dir)

    def test_rejects_an_altered_core(self):
        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            self._write_generation(data_dir)
            (data_dir / "ENDURANCE_HRV_master_CORE.csv").write_text("changed", encoding="utf-8")
            with self.assertRaises(GenerationCoherenceError):
                verify_generation_coherence(data_dir)

    def test_rejects_missing_or_altered_beta_audit(self):
        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            self._write_generation(data_dir)
            beta_audit = data_dir / "ENDURANCE_HRV_master_BETA_AUDIT.csv"
            beta_audit.write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(GenerationCoherenceError, "BETA_AUDIT"):
                verify_generation_coherence(data_dir)
            beta_audit.unlink()
            with self.assertRaises(GenerationCoherenceError):
                verify_generation_coherence(data_dir)

    def test_rejects_an_altered_final_or_dashboard(self):
        for filename in ("ENDURANCE_HRV_master_FINAL.csv", "ENDURANCE_HRV_master_DASHBOARD.csv"):
            with self.subTest(filename=filename), TemporaryDirectory() as tmpdir:
                data_dir = Path(tmpdir)
                self._write_generation(data_dir)
                (data_dir / filename).write_text("changed", encoding="utf-8")
                with self.assertRaises(GenerationCoherenceError):
                    verify_generation_coherence(data_dir)

    def test_rejects_a_misaligned_core_lineage(self):
        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            self._write_generation(data_dir)
            manifest_path = data_dir / "ENDURANCE_HRV_master_FINAL_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["source_manifest_sha256"] = "not-the-core-manifest"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(GenerationCoherenceError):
                verify_generation_coherence(data_dir)


if __name__ == "__main__":
    unittest.main()
