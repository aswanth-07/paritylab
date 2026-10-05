"""Package the source, build an offline wheel, and prove a clean installation."""
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import venv
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    destination = ROOT / "output/release"
    destination.mkdir(parents=True, exist_ok=True)
    bundle = destination / "paritylab-source.zip"
    if (ROOT / ".git").exists():
        listing = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                                 cwd=ROOT, check=True, capture_output=True, text=True)
        files = [ROOT / name for name in set(listing.stdout.split("\0")) if name and (ROOT / name).is_file()]
    else:
        # An extracted source archive already contains only public release files.
        files = [path for path in ROOT.rglob("*") if path.is_file()
                 and not any(part in {"__pycache__", ".venv", "build", "release", "tmp"}
                             or part.endswith(".egg-info") for part in path.relative_to(ROOT).parts)]
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=7) as archive:
        for path in sorted(files):
            archive.write(path, "paritylab/" + path.relative_to(ROOT).as_posix())
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env["PYTHONNOUSERSITE"] = "1"
    with tempfile.TemporaryDirectory(prefix="paritylab-release-") as temporary:
        work = Path(temporary)
        with zipfile.ZipFile(bundle) as archive:
            archive.extractall(work)
        source = work / "paritylab"
        # Build from the extracted bundle to prove it contains the required assets.
        subprocess.run([sys.executable, "-m", "pip", "wheel", str(source), "--no-deps", "--wheel-dir", str(destination)],
                       cwd=work, env=env, check=True)
        wheel = destination / "packet_parity_lab-1.0.0-py3-none-any.whl"
        if not wheel.is_file():
            raise RuntimeError("Expected release wheel was not produced")
        environment = work / "isolated"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run([str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheel)],
                       cwd=work, env=env, check=True)
        tests = subprocess.run([str(python), "-m", "unittest", "discover", "-s", str(source / "tests"), "-v"],
                               cwd=work, env=env, capture_output=True, text=True)
        (destination / "installed-tests.txt").write_text(tests.stdout + tests.stderr, encoding="utf-8")
        if tests.returncode:
            raise RuntimeError("Isolated installed tests failed: see output/release/installed-tests.txt")
        subprocess.run([str(python), str(source / "scripts/audit_measurements.py")],
                       cwd=work, env=env, check=True)
        smoke = subprocess.run([str(python), "-m", "paritylab", "socket-run", "--scheme", "all", "--bytes", "4097",
                                "--delay-ms", "1", "--loss", ".05", "--output", str(work / "socket")],
                               cwd=work, env=env, capture_output=True, text=True, check=True)
        sockets = json.loads((work / "socket/comparison.json").read_text())
        if not all(r["verified"] for r in sockets):
            raise RuntimeError("Installed socket smoke test failed")
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        log = (work / "server.log").open("w")
        process = subprocess.Popen([str(python), "-m", "paritylab", "demo", "--port", str(port)], cwd=work, env=env,
                                   stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            deadline = time.monotonic() + 10
            while True:
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as response:
                        if not json.load(response).get("ok"):
                            raise RuntimeError("Installed server health check failed")
                    break
                except OSError as error:
                    if time.monotonic() > deadline or process.poll() is not None:
                        raise RuntimeError("Installed server failed to start") from error
                    time.sleep(.05)
            assets = {}
            for path in ("/", "/app.js", "/styles.css", "/assets/fonts/Atkinson-Regular.ttf", "/assets/fonts/Atkinson-Bold.ttf", "/proposal.pdf", "/report.pdf"):
                with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=2) as response:
                    wire = response.read()
                    if not wire or response.status != 200:
                        raise RuntimeError(f"Missing installed asset: {path}")
                    if path.endswith(".pdf") and not wire.startswith(b"%PDF"):
                        raise RuntimeError("Invalid installed PDF")
                    assets[path] = {"bytes": len(wire), "sha256": hashlib.sha256(wire).hexdigest()}
        finally:
            process.terminate()
            process.wait(timeout=5)
            log.close()
        receipt = {"passed": True, "source_bundle_extraction": True, "isolated_wheel_installation": True,
                   "installed_test_exit_code": tests.returncode, "installed_socket_schemes": [r["config"]["scheme"] for r in sockets],
                   "socket_transcript": smoke.stdout, "offline_assets": assets,
                   "scope": "Fresh standard-library runtime; all tests, binary socket transfers, and packaged UI/PDF retrieval from outside the checkout"}
        (destination / "verification.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    checksums = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (bundle, wheel)}
    (destination / "checksums.json").write_text(json.dumps(checksums, indent=2), encoding="utf-8")
    print("Source bundle and offline wheel verified:", destination)


if __name__ == "__main__":
    main()
