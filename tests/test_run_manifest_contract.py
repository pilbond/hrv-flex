import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hrv_app.run_manifest import artifact_signature, build_run_manifest, file_digest, stable_digest


class RunManifestContractTests(unittest.TestCase):
    def test_artifact_signature_hashes_file_contents(self):
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "artifact.txt"
            path.write_text("hola\n", encoding="utf-8")

            signature = artifact_signature(path, role="input", row_count=3, column_count=1)

            self.assertEqual(signature["role"], "input")
            self.assertEqual(signature["name"], "artifact.txt")
            self.assertEqual(signature["row_count"], 3)
            self.assertEqual(signature["column_count"], 1)
            self.assertEqual(signature["size_bytes"], path.stat().st_size)
            self.assertEqual(signature["sha256"], file_digest(path))

    def test_build_run_manifest_hashes_effective_config_stably(self):
        manifest = build_run_manifest(
            stage="core",
            builder="build_hrv_core.py",
            builder_revision="r2026-03-19",
            data_dir=Path("C:/tmp/data"),
            effective_config={"b": 2, "a": 1},
            inputs=[],
            outputs=[],
            generated_at="2026-06-11T00:00:00Z",
        )

        self.assertEqual(manifest["schema_version"], "1.0")
        self.assertEqual(manifest["manifest_kind"], "hrv_run_manifest")
        self.assertEqual(manifest["effective_config_hash"], stable_digest({"a": 1, "b": 2}))
        self.assertEqual(manifest["generated_at"], "2026-06-11T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
