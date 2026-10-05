"""Run correctness checks and save a machine-readable verification receipt."""
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from audit_measurements import audit

ROOT = Path(__file__).resolve().parents[1]


def main():
    output = ROOT / "output/verification"
    output.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    run = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=ROOT,
                         env=env, text=True, capture_output=True)
    transcript = run.stdout + run.stderr
    (output / "tests.txt").write_text(transcript, encoding="utf-8")
    reference_audit = json.loads((ROOT / "docs/reference-audit.json").read_text(encoding="utf-8"))
    reference_check = all(2020 <= item["year"] <= 2026 for item in reference_audit["sources"]) and len(reference_audit["sources"]) == 7
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
               "experiment_integrity": experiment_check, "source_sha256": fingerprints}
    try:
        receipt["measurements"] = audit()
        receipt["measurements_current"] = True
    except (ValueError, KeyError, OSError) as error:
        receipt["measurements_current"] = False
        receipt["measurement_error"] = str(error)
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(transcript, end="")
    print(f"Reference year check: {reference_check}; experiment integrity: {experiment_check}")
    print(f"Measurement provenance: {receipt['measurements_current']}")
    return 0 if run.returncode == 0 and reference_check and experiment_check is not False and receipt["measurements_current"] else 1


if __name__ == "__main__":
    sys.exit(main())
