import gzip
import hashlib
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("controller_audit", ROOT / "scripts/audit_controller_comparison.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ControllerProvenanceTests(unittest.TestCase):
    def test_saved_final_comparison_recomputes_from_raw_records(self):
        result = module.audit(ROOT)
        self.assertEqual(result["records_checked"], 1440)
        self.assertTrue(result["all_verified"])
        self.assertGreater(result["geometric_goodput_ratio_to_legacy_nonclean"], 1.05)

    def test_altered_metrics_are_rejected_even_when_artifact_hash_is_refreshed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "output/studies/controller-cost/held-out"
            shutil.copytree(ROOT / "output/studies/controller-cost/held-out", directory)
            path = directory / "runs.json.gz"
            rows = json.loads(gzip.decompress(path.read_bytes()))
            rows[0]["goodput_mbps"] *= 2
            path.write_bytes(gzip.compress(json.dumps(rows).encode(), mtime=0))
            manifest_path = directory / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["artifacts_sha256"][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "goodput mismatch"):
                module.audit(root)

    def test_missing_final_trials_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "output/studies/controller-cost/held-out"
            shutil.copytree(ROOT / "output/studies/controller-cost/held-out", directory)
            path = directory / "runs.json.gz"
            rows = json.loads(gzip.decompress(path.read_bytes()))
            path.write_bytes(gzip.compress(json.dumps(rows[:-1]).encode(), mtime=0))
            manifest_path = directory / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["artifacts_sha256"][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "trial count"):
                module.audit(root)


if __name__ == "__main__":
    unittest.main()
