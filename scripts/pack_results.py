"""Compress large raw artifacts deterministically for the source repository."""
import gzip
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_PATHS = (
    "output/congestion/runs.json",
    "output/studies/equal-overhead/trials.csv",
)


def main():
    for name in RAW_PATHS:
        source = ROOT / name
        destination = source.with_suffix(source.suffix + ".gz")
        if source.exists():
            with destination.open("wb") as stream:
                with gzip.GzipFile(filename="", mode="wb", fileobj=stream, mtime=0) as archive:
                    archive.write(source.read_bytes())
            print(f"{name}: {source.stat().st_size} bytes -> {destination.stat().st_size} bytes")
        elif not destination.exists():
            raise FileNotFoundError(f"No raw or compressed artifact: {name}")


if __name__ == "__main__":
    main()
