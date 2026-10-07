"""Run correctness checks and save a machine-readable verification receipt."""
import hashlib
import argparse
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from audit_measurements import audit
from audit_controller_comparison import audit as audit_controllers
from audit_references import audit as audit_references

ROOT = Path(__file__).resolve().parents[1]


def main(*, write_receipt=True):
    output = ROOT / "output/verification"
    if write_receipt:
        output.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    run = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=ROOT,
                         env=env, text=True, capture_output=True)
    transcript = run.stdout + run.stderr
    if write_receipt:
        (output / "tests.txt").write_text(transcript, encoding="utf-8")
    try:
        reference_audit = audit_references()
        reference_check = True
    except (ValueError, KeyError, OSError) as error:
        reference_audit = {"status": "failed", "error": str(error)}
        reference_check = False
    experiment_path = ROOT / "output/experiments/runs.json"
    experiment_check = None
    if experiment_path.exists():
        rows = json.loads(experiment_path.read_text(encoding="utf-8"))
        experiment_check = all(row["completed"] and row["bytes_delivered"] > 0 and 0 <= row["fec_recovery_ratio"] <= 1 for row in rows)
        for scenario in {row["scenario"] for row in rows}:
            digests = {row["sha256"] for row in rows if row["scenario"] == scenario}
            experiment_check = experiment_check and len(digests) == 1
    fingerprints = {str(path.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
                    for directory in ("src", "tests") for path in sorted((ROOT / directory).rglob("*.py"))}
    receipt = {"recorded_at_utc": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(),
               "command": ["python", "-m", "unittest", "discover", "-s", "tests", "-v"],
               "exit_code": run.returncode, "references_in_range": reference_check,
               "reference_audit": reference_audit,
               "experiment_integrity": experiment_check, "source_sha256": fingerprints}
    try:
        receipt["measurements"] = audit()
        receipt["measurements_verified"] = True
        receipt["measurements_current"] = all(row["source_current"] for row in receipt["measurements"].values())
        if (ROOT / "output/studies/controller-cost/held-out/manifest.json").exists():
            receipt["controller_comparison"] = audit_controllers()
    except (ValueError, KeyError, OSError) as error:
        receipt["measurements_current"] = False
        receipt["measurements_verified"] = False
        receipt["measurement_error"] = str(error)
    if write_receipt:
        (output / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(transcript, end="")
    print(f"Reference year check: {reference_check}; experiment integrity: {experiment_check}")
    print(f"Measurement provenance verified: {receipt['measurements_verified']}; current source: {receipt['measurements_current']}")
    return 0 if run.returncode == 0 and reference_check and experiment_check is not False and receipt["measurements_verified"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-write", action="store_true", help="Run all checks without rewriting verification receipts")
    sys.exit(main(write_receipt=not parser.parse_args().no_write))
