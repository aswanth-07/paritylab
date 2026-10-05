import json
import threading
import unittest
from contextlib import closing
from http.client import HTTPConnection

from paritylab.server import DemoHandler, DemoServer, run_comparison


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = DemoServer(("127.0.0.1", 0), DemoHandler)
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join()

    def request(self, method, path, body=None, headers=None):
        with closing(HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)) as connection:
            connection.request(method, path, json.dumps(body) if body is not None else None,
                               headers or {"Content-Type": "application/json"})
            response = connection.getresponse()
            return response.status, json.loads(response.read())

    def test_measured_comparison_and_replay_integrity(self):
        result = run_comparison({"file_kib": 8, "loss_percent": 10})
        self.assertTrue(result["all_verified"])
        self.assertEqual([r["scheme"] for r in result["results"]], ["gbn", "sr", "fixed", "adaptive"])
        for row in result["results"]:
            data = [event for event in row["transmissions"] if event["kind"] == "data"]
            self.assertEqual(len(data), row["data_transmissions"])
            self.assertTrue(all(e["arrival_s"] >= e["start_s"] for e in row["transmissions"]))

    def test_invalid_and_nonfinite_settings_are_rejected(self):
        for body in ({"file_kib": 500}, {"window": 0}, {"seed": True}, {"scenario": "invalid"}, {"delay_ms": float("nan")}):
            with self.subTest(body=body):
                status, result = self.request("POST", "/api/simulate", body)
                self.assertEqual(status, 400)
                self.assertIn("error", result)

    def test_unknown_paths_and_traversal_are_not_served(self):
        for path in ("/.private/state.db", "/assets/../../README.md", "/src/paritylab/server.py"):
            self.assertEqual(self.request("GET", path)[0], 404)

    def test_cross_origin_execution_is_rejected(self):
        for origin in ("https://example.com", "http://localhost:invalid"):
            with self.subTest(origin=origin):
                status, _ = self.request("POST", "/api/udp", {}, {"Content-Type": "application/json", "Origin": origin})
                self.assertEqual(status, 403)

    def test_health_and_changing_scenario(self):
        self.assertTrue(self.request("GET", "/api/health")[1]["ok"])
        status, response = self.request("POST", "/api/simulate", {"file_kib": 8, "scenario": "changing"})
        self.assertEqual(status, 200)
        self.assertTrue(response["all_verified"])
        self.assertEqual(len(response["config"]["channel"]["phases"]), 3)

    def test_udp_endpoint_checks_real_bytes(self):
        status, response = self.request("POST", "/api/udp", {"loss_percent": 15})
        self.assertEqual(status, 200)
        self.assertTrue(response["verified"])
        self.assertEqual(response["bytes_delivered"], 32768)

    def test_full_socket_endpoint_checks_three_processes(self):
        status, response = self.request("POST", "/api/socket", {"loss_percent": 5, "delay_ms": 1,
                                      "ack_loss_percent": 5, "scheme": "sr", "window": 8})
        self.assertEqual(status, 200)
        self.assertTrue(response["verified"])
        self.assertEqual(response["bytes_delivered"], 32768)
        self.assertEqual(len({p["pid"] for p in response["processes"]}), 3)
        self.assertEqual(response["receiver"]["application_release_count"], 64)

    def test_socket_settings_are_validated(self):
        for body in ({"scheme": "invalid"}, {"scenario": "invalid"}, {"window": 0}, {"seed": True}):
            self.assertEqual(self.request("POST", "/api/socket", body)[0], 400)

    def test_occupied_port_cannot_be_shared(self):
        with self.assertRaises(OSError):
            DemoServer(("127.0.0.1", self.server.server_port), DemoHandler)

    def test_controller_trace_describes_transmitted_blocks(self):
        response = run_comparison({"file_kib": 64, "loss_percent": 10})
        adaptive = response["results"][-1]
        trace = adaptive["controller_trace"]
        starts = [decision["start_packet"] for decision in trace]
        self.assertEqual(starts, sorted(set(starts)))
        self.assertEqual(sum(decision["data_packets"] for decision in trace), 64)
        first_data = {event["sequence"] for event in adaptive["transmissions"] if event["kind"] == "data" and event["attempt"] == 1}
        for decision in trace:
            block = range(decision["start_packet"], decision["start_packet"] + decision["data_packets"])
            self.assertTrue(set(block).issubset(first_data))
