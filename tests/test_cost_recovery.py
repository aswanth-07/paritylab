import hashlib
import math
import unittest
from dataclasses import replace

from paritylab.channel import ChannelConfig
from paritylab.controller import AdaptiveController
from paritylab.experiments import sample_data
from paritylab.simulation import SimulationConfig, simulate
from paritylab.socket_transport import SocketConfig, socket_transfer


class CostRecoveryTests(unittest.TestCase):
    def test_short_feedback_has_less_influence_than_a_full_batch(self):
        short = AdaptiveController(policy="cost", packet_serial_s=.002, retry_wait_s=.2)
        full = AdaptiveController(policy="cost", packet_serial_s=.002, retry_wait_s=.2)
        short.observe(1, 1)
        full.observe(16, 16)
        self.assertLess(short.estimate, full.estimate)
        self.assertAlmostEqual(full.estimate, .25)
        for _ in range(15):
            short.observe(1, 1)
        self.assertAlmostEqual(short.estimate, full.estimate)

    def test_cost_decision_changes_with_serialization_and_timeout(self):
        expensive = AdaptiveController(policy="cost", alpha=1, packet_serial_s=1, retry_wait_s=.1)
        cheap = AdaptiveController(policy="cost", alpha=1, packet_serial_s=.0001, retry_wait_s=1)
        for controller in (expensive, cheap):
            controller.observe(10, 100)
        self.assertEqual(expensive.choose().protection.mode, "none")
        choice = cheap.choose(size=3)
        self.assertNotEqual(choice.protection.mode, "none")
        self.assertLess(choice.estimated_cost_per_packet_s, choice.unprotected_cost_per_packet_s)
        self.assertIn("proxy", choice.assumptions)

    def test_cost_requires_valid_network_context(self):
        for serial, timeout in ((None, .1), (.1, None), (0, .1), (.1, math.nan), (math.inf, .1)):
            with self.subTest(serial=serial, timeout=timeout), self.assertRaises(ValueError):
                AdaptiveController(policy="cost", packet_serial_s=serial, retry_wait_s=timeout)

    def test_receiver_status_triggers_retry_before_timer(self):
        data = sample_data(8192)
        config = SimulationConfig(controller_policy="cost", recovery_feedback=True,
                                  timeout_ms=500, channel=ChannelConfig(loss=.2), seed=7)
        result = simulate(data, config, capture_transmissions=True)
        self.assertTrue(result.completed)
        self.assertGreater(result.feedback_retries, 0)
        first = {event["sequence"]: event for event in result.transmissions
                 if event["kind"] == "data" and event["attempt"] == 1}
        early = [event for event in result.transmissions if event["kind"] == "data" and event["attempt"] == 2
                 and event["start_s"] < first[event["sequence"]]["start_s"] + .5]
        self.assertEqual(len(early), result.feedback_retries)
        self.assertEqual(result.application_sha256, hashlib.sha256(data).hexdigest())
        self.assertLess(result.completion_time_s, simulate(data, replace(config, recovery_feedback=False)).completion_time_s)

    def test_cost_preserves_partial_bytes_with_impaired_metadata_and_ack_path(self):
        data = sample_data(17293)
        for model in ("bernoulli", "gilbert-elliott"):
            result = simulate(data, SimulationConfig(controller_policy="cost", recovery_feedback=True,
                              window=8, packet_size=513, metadata_mode="reliable", metadata_loss=.1,
                              channel=ChannelConfig(loss=.2, ack_loss=.1, model=model, jitter_ms=3,
                                                    reorder_probability=.2, reorder_delay_ms=10)))
            self.assertTrue(result.completed)
            self.assertEqual(result.sha256, hashlib.sha256(data).hexdigest())
            self.assertEqual(result.application_bytes_delivered, len(data))

    def test_lost_feedback_falls_back_to_bounded_timeout_failure(self):
        config = SimulationConfig(controller_policy="cost", recovery_feedback=True, max_events=100,
                                  channel=ChannelConfig(loss=.2, ack_loss=1))
        result = simulate(sample_data(8192), config)
        self.assertFalse(result.completed)
        self.assertEqual(result.feedback_retries, 0)
        self.assertGreater(result.retransmissions, 0)

    def test_clean_link_adds_no_parity_or_retries(self):
        data = sample_data(65536)
        config = SimulationConfig(controller_policy="cost", recovery_feedback=True, channel=ChannelConfig(loss=0))
        result = simulate(data, config)
        self.assertEqual((result.retransmissions, result.parity_packets, result.feedback_retries), (0, 0, 0))
        self.assertEqual(result.goodput_mbps, simulate(data, replace(config, controller_policy="legacy", recovery_feedback=False)).goodput_mbps)

    def test_real_cost_transport_verifies_bytes_under_duplicates_and_reordering(self):
        data = sample_data(8199)
        received, result = socket_transfer(data, SocketConfig(controller_policy="cost", recovery_feedback=True,
                                          window=8, duplicate_probability=.1, metadata_loss=.05,
                                          channel=ChannelConfig(loss=.15, ack_loss=.05, delay_ms=2,
                                          jitter_ms=2, reorder_probability=.2, reorder_delay_ms=5)))
        self.assertEqual(received, data)
        self.assertTrue(result["verified"])
        self.assertLessEqual(result["sender"]["feedback_retries"], math.ceil(len(data) / 512))


if __name__ == "__main__":
    unittest.main()
