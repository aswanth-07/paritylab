import hashlib
import os
import socket
import tempfile
import unittest
from pathlib import Path

from paritylab.channel import ChannelConfig
from paritylab.experiments import sample_data
from paritylab.socket_transport import SocketConfig, _read, _socket, socket_transfer
from paritylab.wire import pack, unpack


class WireTests(unittest.TestCase):
    def test_binary_framing_and_corruption_detection(self):
        message = {"kind": "data", "sequence": 0, "payload": bytes(range(256))}
        wire = pack(message)
        self.assertEqual(unpack(wire), message)
        for damaged in (wire[:-1], wire[:15] + bytes([wire[15] ^ 1]) + wire[16:], b"garbage"):
            with self.assertRaises(ValueError):
                unpack(damaged)


class SocketTransportTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows asynchronous UDP ICMP behavior")
    def test_closed_udp_peer_does_not_crash_receiving_socket(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as peer:
            peer.bind(("127.0.0.1", 0))
            closed_address = peer.getsockname()
        with _socket() as sender:
            sender.settimeout(.05)
            sender.sendto(b"late completion reply", closed_address)
            try:
                result = _read(sender)
            except socket.timeout:
                result = None
            self.assertIsNone(result)

    def test_invalid_limits_are_rejected_before_process_launch(self):
        for settings in ({'window': 1.5}, {'packet_size': True}, {'fixed_k': 8.5}, {'max_seconds': float('inf')}):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                SocketConfig(**settings)
        with self.assertRaises(ValueError):
            socket_transfer(bytes(131073), SocketConfig(packet_size=1))

    def test_optional_uncertainty_policy_exports_assumptions(self):
        received, row = socket_transfer(sample_data(5000), SocketConfig(controller_policy='uncertainty',
            channel=ChannelConfig(loss=.1, delay_ms=1), max_seconds=6))
        self.assertEqual(received, sample_data(5000))
        self.assertTrue(row['sender']['controller_trace'])
        self.assertTrue(all(t['loss_upper'] >= t['loss_lower'] and t['assumptions'] for t in row['sender']['controller_trace']))
    def test_all_windowed_schemes_use_three_processes_and_verify_binary_tail(self):
        data = sample_data(8193)
        for scheme in ("gbn", "sr", "fixed", "adaptive"):
            with self.subTest(scheme=scheme):
                received, row = socket_transfer(data, SocketConfig(scheme=scheme, window=8,
                    channel=ChannelConfig(loss=.15, ack_loss=.15, delay_ms=2), max_seconds=8))
                self.assertEqual(received, data)
                self.assertTrue(row["verified"])
                self.assertEqual(len({p["pid"] for p in row["processes"]}), 3)
                self.assertTrue(all(p["exit_code"] == 0 for p in row["processes"]))
                self.assertEqual(row["receiver"]["sha256"], hashlib.sha256(data).hexdigest())
                self.assertLessEqual(row["sender"]["peak_outstanding"], 8)
                self.assertGreater(row["sender"]["peak_outstanding"], 1)
                times = row["receiver"]["packet_timestamps"]
                self.assertEqual(len(times), 17)
                self.assertTrue(all(t["application_release_s"] >= t["received_s"] >= t["first_sent_s"] for t in times))
                self.assertEqual([t["application_release_s"] for t in times], sorted(t["application_release_s"] for t in times))

    def test_control_loss_duplication_and_corruption_recover(self):
        data = sample_data(12017)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "received.bin"
            received, row = socket_transfer(data, SocketConfig(scheme="fixed", metadata_loss=.5,
                duplicate_probability=.2, corruption_probability=.08, seed=2,
                channel=ChannelConfig(loss=.05, ack_loss=.1, delay_ms=1), max_seconds=8), output)
            self.assertEqual(received, data)
            self.assertEqual(output.read_bytes(), data)
            self.assertTrue(output.with_suffix('.json').is_file())
            self.assertGreater(row["proxy"]["dropped_metadata"], 0)
            self.assertGreater(row["proxy"]["duplicates"], 0)
            self.assertGreater(row["proxy"]["corrupted"], 0)
            self.assertGreater(row["receiver"]["invalid_datagrams"], 0)

    def test_metadata_total_loss_fails_without_output_with_bounded_budget(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "must-not-exist.bin"
            with self.assertRaises(TimeoutError):
                socket_transfer(b"manifest never arrives", SocketConfig(metadata_loss=1,
                    max_attempts=2, max_seconds=2, timeout_ms=30), output)
            self.assertFalse(output.exists())

    def test_one_packet_window_and_zero_loss(self):
        for scheme in ("gbn", "sr", "fixed", "adaptive"):
            received, row = socket_transfer(b"\x00\xfftail", SocketConfig(scheme=scheme, window=1,
                channel=ChannelConfig(loss=0, delay_ms=0), max_seconds=5))
            self.assertEqual(received, b"\x00\xfftail")
            self.assertEqual(row["sender"]["retransmissions"], 0)
