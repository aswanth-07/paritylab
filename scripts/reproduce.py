"""Reproduce registered transport studies; optionally regenerate full calibration."""
import argparse
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calibration", action="store_true", help="Regenerate all 3.06 million byte-decoder trials")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    for command in (("experiment", "--seeds", "5"), ("studies", "--seeds", "5", "--blocks", "1000"),
                    ("congestion", "--seeds", "5"), ("socket-evaluate", "--seeds", "3")):
        subprocess.run([sys.executable, "-m", "paritylab", *command], cwd=root, check=True)
    if args.calibration:
        subprocess.run([sys.executable, "-m", "paritylab", "calibrate", "--seeds", "5", "--trials-per-seed", "4000"], cwd=root, check=True)
    subprocess.run([sys.executable, str(root / "scripts/pack_results.py")], cwd=root, check=True)


if __name__ == "__main__":
    main()
