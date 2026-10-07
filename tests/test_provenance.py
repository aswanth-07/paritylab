import hashlib
import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("measurement_audit", Path(__file__).resolve().parents[1] / "scripts/audit_measurements.py")
audit_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_module)
report_spec = importlib.util.spec_from_file_location("report_builder", Path(__file__).resolve().parents[1] / "scripts/build_report.py")
report_module = importlib.util.module_from_spec(report_spec)
report_spec.loader.exec_module(report_module)


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


class ReportEvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        source = self.root / "src/paritylab/model.py"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"current implementation")
        self.receipt = {"exit_code": 0, "references_in_range": True, "experiment_integrity": True,
                        "measurements_verified": True, "measurements_current": False,
                        "source_sha256": {"src/paritylab/model.py": hashlib.sha256(source.read_bytes()).hexdigest()},
                        "measurements": {name: {"passed": True, "source_verified": True,
                            "source_current": False, "archived_revision": "measured-revision"}
                            for name in ("experiments", "studies/sensitivity", "studies/equal-overhead",
                                         "congestion", "socket-evaluation", "calibration")}}
        patcher = patch.object(report_module, "ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_verified_historical_measurements_accept_current_tests(self):
        report_module.check_receipt(self.receipt)

    def test_test_receipt_must_cover_current_source(self):
        (self.root / "src/paritylab/model.py").write_bytes(b"changed after tests")
        with self.assertRaisesRegex(RuntimeError, "does not match current source"):
            report_module.check_receipt(self.receipt)

    def test_failed_or_incomplete_evidence_is_rejected(self):
        for update in ({"exit_code": 1}, {"references_in_range": False}, {"measurements_verified": False},
                       {"measurements": {}}, {"measurements": {"experiments": {"passed": True}}}):
            with self.subTest(update=update), self.assertRaises(RuntimeError):
                report_module.check_receipt({**self.receipt, **update})
        self.receipt["measurements"]["experiments"].pop("archived_revision")
        with self.assertRaisesRegex(RuntimeError, "provenance"):
            report_module.check_receipt(self.receipt)

    def test_report_labels_archived_measurements_without_claiming_new_runs(self):
        files = {"output/verification/receipt.json": json.dumps(self.receipt),
                 "output/verification/tests.txt": "Ran 78 tests\nOK\n",
                 "output/experiments/summary.csv": "scenario,scheme\n",
                 "output/calibration/manifest.json": json.dumps({"decoder_trials": 3060000,
                     "policy_test_trials": 225000, "maximum_exact_absolute_error": .001,
                     "maximum_wrong_iid_stationary_burst_error": .1, "maximum_wrong_iid_burst_error": .2}),
                 "docs/proposal.md": "## References (2020-2026)\nSaved references\n"}
        for name, contents in files.items():
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(contents, encoding="utf-8")
        text = report_module.report_text()
        self.assertIn("The current suite passes 78 tests", text)
        self.assertIn("These historical measurements are not new measurements of this release.", text)
        self.assertIn("--require-current", text)
