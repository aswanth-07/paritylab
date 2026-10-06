"""Local UI service for measured simulator runs and bounded loopback checks."""
import hashlib
import json
import math
import mimetypes
import os
import socket
import threading
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .channel import ChannelConfig
from .experiments import sample_data
from .simulation import SCHEMES, SimulationConfig, simulate
from .udp_demo import udp_transfer
from .socket_transport import SocketConfig, socket_transfer

ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = ROOT / "web"
PDF_ROOT = ROOT / "output/pdf"
if not WEB_ROOT.is_dir():
    WEB_ROOT = Path(__file__).resolve().parent / "assets/web"
    PDF_ROOT = Path(__file__).resolve().parent / "assets/pdf"
RUN_LOCK = threading.BoundedSemaphore(2)
MAX_BODY = 8192


def number(body, key, default, low, high, *, integer=False):
    value = body.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{key.replace('_', ' ')} must be a finite number")
    if not low <= value <= high or (integer and int(value) != value):
        raise ValueError(f"{key.replace('_', ' ')} must be between {low} and {high}" + (" and a whole number" if integer else ""))
    return int(value) if integer else float(value)


def run_comparison(body):
    loss = number(body, "loss_percent", 10, 0, 30) / 100
    delay = number(body, "delay_ms", 50, 0, 500)
    bandwidth = number(body, "bandwidth_mbps", 5, 0.25, 100)
    window = number(body, "window", 32, 1, 128, integer=True)
    size = number(body, "file_kib", 64, 8, 256, integer=True) * 1024
    seed = number(body, "seed", 7, 0, 999999, integer=True)
    ack_loss = number(body, "ack_loss_percent", 0, 0, 20) / 100
    scenario = body.get("scenario", "random")
    if scenario not in {"random", "burst", "changing"}:
        raise ValueError("Choose random, burst, or changing loss")
    phases = ((0.25, loss), (0.75, 0.02), (1.2, loss)) if scenario == "changing" else ()
    channel = ChannelConfig(loss=0 if scenario == "changing" else loss, delay_ms=delay,
                            bandwidth_mbps=bandwidth, ack_loss=ack_loss,
                            model="gilbert-elliott" if scenario == "burst" else "bernoulli", phases=phases)
    payload = sample_data(size)
    expected_digest = hashlib.sha256(payload).hexdigest()
    rows = []
    for scheme in SCHEMES:
        config = SimulationConfig(scheme=scheme, channel=channel, seed=seed, window=window, max_events=80000)
        row = simulate(payload, config, capture_transmissions=True).to_dict()
        row["integrity_verified"] = row["completed"] and row["sha256"] == expected_digest
        # Replay only transmissions starting before sender completion.
        row["transmissions"] = [event for event in row["transmissions"] if event["start_s"] <= row["sender_completion_time_s"]]
        rows.append(row)
    return {"config": {"loss_percent": loss * 100, "delay_ms": delay, "bandwidth_mbps": bandwidth,
                       "window": window, "file_kib": size // 1024, "seed": seed,
                       "ack_loss_percent": ack_loss * 100, "scenario": scenario, "channel": asdict(channel)},
            "results": rows, "expected_sha256": expected_digest,
            "all_verified": all(row["integrity_verified"] for row in rows),
            "replay_note": "Actual recorded transmissions in virtual time; path positions are illustrative."}


def run_socket_check(body):
    """A bounded real transport using the same visible network controls."""
    loss = number(body, "loss_percent", 10, 0, 30) / 100
    delay = number(body, "delay_ms", 50, 0, 500)
    bandwidth = number(body, "bandwidth_mbps", 5, .25, 100)
    window = number(body, "window", 32, 1, 128, integer=True)
    seed = number(body, "seed", 7, 0, 999999, integer=True)
    ack_loss = number(body, "ack_loss_percent", 0, 0, 20) / 100
    scheme = body.get("scheme", "adaptive")
    scenario = body.get("scenario", "random")
    if scheme not in SCHEMES or scenario not in {"random", "burst", "changing"}:
        raise ValueError("Choose a supported scheme and loss model")
    phases = ((.25, loss), (.75, .02), (1.2, loss)) if scenario == "changing" else ()
    channel = ChannelConfig(loss=0 if phases else loss, delay_ms=delay, bandwidth_mbps=bandwidth,
                            ack_loss=ack_loss, phases=phases,
                            model="gilbert-elliott" if scenario == "burst" else "bernoulli")
    _, result = socket_transfer(sample_data(32768), SocketConfig(scheme=scheme, seed=seed,
                                channel=channel, window=window, max_seconds=25))
    result["transport"] = "Three separate localhost UDP processes with sliding windows"
    return result


class DemoHandler(BaseHTTPRequestHandler):
    server_version = "ParityLab/1.0"

    def log_message(self, message, *args):
        """Keep the local experiment server quiet during packet replay."""

    def respond(self, status, content, content_type="application/json; charset=utf-8"):
        wire = json.dumps(content, allow_nan=False).encode() if isinstance(content, (dict, list)) else content
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(wire)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.end_headers()
        self.wfile.write(wire)

    def do_GET(self):
        path = unquote(urlsplit(self.path).path)
        if path == "/api/health":
            self.respond(200, {"ok": True, "engine": "Python event-driven emulator", "schemes": list(SCHEMES)})
            return
        allowed = {"/": (WEB_ROOT / "index.html"), "/index.html": WEB_ROOT / "index.html",
                   "/app.js": WEB_ROOT / "app.js", "/replay.mjs": WEB_ROOT / "replay.mjs",
                   "/styles.css": WEB_ROOT / "styles.css",
                   "/proposal.pdf": PDF_ROOT / "proposal-2020-2026.pdf",
                   "/report.pdf": PDF_ROOT / "project-report.pdf"}
        target = allowed.get(path)
        if target is None and path.startswith("/assets/"):
            candidate = (WEB_ROOT / path.lstrip("/")).resolve()
            if candidate.is_relative_to((WEB_ROOT / "assets").resolve()):
                target = candidate
        if target is None or not target.is_file():
            self.respond(404, {"error": "That page or file is not available."})
            return
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if target.suffix in {".html", ".js", ".css"}:
            content_type += "; charset=utf-8"
        self.respond(200, target.read_bytes(), content_type)

    def do_POST(self):
        path = urlsplit(self.path).path
        if path not in {"/api/simulate", "/api/udp", "/api/socket"}:
            self.respond(404, {"error": "That operation is not available."})
            return
        origin = self.headers.get("Origin")
        if origin:
            try:
                parsed = urlsplit(origin)
                local_origin = parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"} and parsed.port == self.server.server_port
            except ValueError:
                local_origin = False
            if not local_origin:
                self.respond(403, {"error": "Open the demo on its localhost address and try again."})
                return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY:
                raise ValueError("Request size must be between 1 and 8192 bytes")
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                self.respond(415, {"error": "Send the settings as JSON."})
                return
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError("Settings must be a JSON object")
        except (ValueError, UnicodeDecodeError) as error:
            self.respond(400, {"error": str(error)})
            return
        if not RUN_LOCK.acquire(blocking=False):
            self.respond(429, {"error": "Two runs are already in progress. Wait a moment and try again."})
            return
        try:
            if path == "/api/simulate":
                result = run_comparison(body)
            elif path == "/api/socket":
                result = run_socket_check(body)
            else:
                loss = number(body, "loss_percent", 15, 0, 30) / 100
                seed = number(body, "seed", 7, 0, 999999, integer=True)
                _, result = udp_transfer(sample_data(32768), loss=loss, seed=seed, max_rounds=40)
                result["transport"] = "Actual UDP sockets on 127.0.0.1"
            self.respond(200, result)
        except ValueError as error:
            self.respond(400, {"error": str(error)})
        except (TimeoutError, OSError, RuntimeError):
            self.respond(503, {"error": "The localhost check reached its retry or time limit. Lower loss or delay, or increase bandwidth, then try again."})
        except Exception:
            self.respond(500, {"error": "The run could not complete. Restart the local server and try again."})
        finally:
            RUN_LOCK.release()


class DemoServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self):
        if os.name == "nt":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def serve(port=8770):
    if not 1 <= port <= 65535:
        raise ValueError("Port must be between 1 and 65535")
    with DemoServer(("127.0.0.1", port), DemoHandler) as server:
        print(f"Packet parity lab: http://127.0.0.1:{port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            return
