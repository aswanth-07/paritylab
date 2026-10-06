"""Check saved measurement provenance, output bytes and registered trial counts."""
import csv
import gzip
import hashlib
import json
import io
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def artifact_bytes(path):
    """Read raw data or its lossless repository copy."""
    if path.exists():
        return path.read_bytes()
    return gzip.decompress(path.with_suffix(path.suffix + ".gz").read_bytes())


def digest(path):
    return hashlib.sha256(artifact_bytes(path)).hexdigest()


def source_status(recorded, root=ROOT, *, require_current=False):
    """Verify measured bytes without mistaking historical runs for current runs."""
    paths = {file if file.startswith("src/") else "src/paritylab/" + file: expected
             for file, expected in recorded.items()}
    current = all((root / file).is_file() and hashlib.sha256((root / file).read_bytes()).hexdigest() == expected
                  for file, expected in paths.items())
    if current:
        return {"source_current": True, "source_verified": True}
    if require_current:
        raise ValueError("Recorded measurements do not match current source; reproduce them")
    directory = root / "output/measured-source"
    index = directory / "index.json"
    if index.is_file():
        for item in json.loads(index.read_text(encoding="utf-8"))["archives"]:
            if Path(item["file"]).name != item["file"]:
                raise ValueError("Measured source archive must be a local filename")
            archive_path = directory / item["file"]
            if hashlib.sha256(archive_path.read_bytes()).hexdigest() != item["sha256"]:
                raise ValueError("Measured source archive hash mismatch")
            with zipfile.ZipFile(archive_path) as archive:
                if all(file in archive.namelist() and hashlib.sha256(archive.read(file)).hexdigest() == expected
                       for file, expected in paths.items()):
                    return {"source_current": False, "source_verified": True, "archived_revision": item["revision"]}
    raise ValueError("Recorded source differs from the checkout and has no matching verified archive")


def audit(*, require_current=False):
    results = {}
    for name in ("experiments", "studies/sensitivity", "studies/equal-overhead", "congestion", "socket-evaluation", "calibration"):
        directory = ROOT / "output" / name
        manifest = json.loads((directory / "manifest.json").read_text())
        sources = source_status(manifest["source_sha256"], require_current=require_current)
        for file, expected in manifest.get("artifacts_sha256", {}).items():
            if digest(directory / file) != expected:
                raise ValueError(f"Changed measurement artifact: {name}/{file}")
        if name == "calibration":
            counts = {}
            with gzip.open(directory / "raw-trials.csv.gz", "rt", newline="") as stream:
                reader = csv.DictReader(stream)
                for row in reader:
                    key = (row["case"], row["seed"])
                    item = counts.setdefault(key, [0, 0])
                    item[0] += 1
                    if int(row["trial"]) != item[0] - 1 or row["decoder_failed"] not in {"0", "1"}:
                        raise ValueError("Calibration trial sequence or outcome is invalid")
                    item[1] += int(row["decoder_failed"])
            with (directory / "seed-counts.csv").open(newline="") as stream:
                summaries = list(csv.DictReader(stream))
            for row in summaries:
                if counts[(row["case"], row["seed"])] != [int(row["trials"]), int(row["failures"])]:
                    raise ValueError("Calibration raw counts differ from summaries")
            count = sum(v[0] for v in counts.values())
            if count != manifest["decoder_trials"] or manifest["byte_decoder_wrong_recoveries"] != 0:
                raise ValueError("Calibration trial or byte-integrity audit failed")
        elif name == "studies/equal-overhead":
            with io.StringIO(artifact_bytes(directory / "trials.csv").decode("utf-8"), newline="") as stream:
                count = sum(1 for _ in csv.DictReader(stream))
            if count != manifest["decoder_trials"]:
                raise ValueError("Equal-overhead trial count differs from manifest")
        else:
            rows = json.loads(artifact_bytes(directory / "runs.json"))
            count = len(rows)
            if count != manifest["runs"]:
                raise ValueError(f"Run count mismatch: {name}")
            for row in rows:
                if name == "congestion":
                    if not row["completed"] or row["queue_high_water_packets"] > row["queue_capacity_packets"]:
                        raise ValueError("Congestion completion or queue bound failed")
                    for flow in row["flows"]:
                        if not flow["completed"] or flow["sha256"] != flow["expected_sha256"]:
                            raise ValueError("Competing-flow byte audit failed")
                elif name == "socket-evaluation":
                    expected = manifest["expected_sha256"]
                    if not row["verified"] or row["receiver"]["sha256"] != expected or len({p["pid"] for p in row["processes"]}) != 3:
                        raise ValueError("Socket integrity or process separation failed")
                    file = directory / f"{row['scenario']}-{row['config']['scheme']}-{row['config']['seed']}.bin"
                    if digest(file) != expected:
                        raise ValueError("Saved socket file hash mismatch")
                else:
                    from paritylab.experiments import sample_data
                    expected = hashlib.sha256(sample_data(row["bytes_delivered"])).hexdigest()
                    if not row["completed"] or row["sha256"] != expected or row["application_sha256"] != expected:
                        raise ValueError(f"Transfer byte audit failed: {name}")
        results[name] = {"records_checked": count, **sources, "passed": True}
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-current", action="store_true", help="Reject verified historical sources; require new measurements")
    print(json.dumps(audit(require_current=parser.parse_args().require_current), indent=2))
