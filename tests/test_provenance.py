import hashlib
import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

spec = importlib.util.spec_from_file_location("measurement_audit", Path(__file__).resolve().parents[1] / "scripts/audit_measurements.py")
audit_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_module)


class MeasurementSourceTests(unittest.TestCase):
    def test_current_source_needs_no_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "src/paritylab/model.py"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"measured")
            status = audit_module.source_status({"model.py": hashlib.sha256(b"measured").hexdigest()}, root)
            self.assertTrue(status["source_current"])

    def test_archive_verifies_historical_bytes_and_keeps_current_false(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "output/measured-source"
            directory.mkdir(parents=True)
            archive = directory / "measured.zip"
            with zipfile.ZipFile(archive, "w") as file:
                file.writestr("src/paritylab/model.py", b"measured")
            index = {"archives": [{"file": archive.name, "revision": "recorded", "sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}]}
            (directory / "index.json").write_text(json.dumps(index))
            recorded = {"src/paritylab/model.py": hashlib.sha256(b"measured").hexdigest()}
            status = audit_module.source_status(recorded, root)
            self.assertFalse(status["source_current"])
            self.assertTrue(status["source_verified"])
            with self.assertRaises(ValueError):
                audit_module.source_status(recorded, root, require_current=True)
            with self.assertRaises(ValueError):
                audit_module.source_status({"model.py": hashlib.sha256(b"other").hexdigest()}, root)
            archive.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                audit_module.source_status(recorded, root)

    def test_unarchived_stale_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "no matching verified archive"):
                audit_module.source_status({"model.py": "0" * 64}, Path(temporary))
