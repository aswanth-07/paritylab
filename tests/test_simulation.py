import hashlib
import unittest

from paritylab.channel import Channel, ChannelConfig
from paritylab.experiments import sample_data
from paritylab.simulation import SCHEMES, SimulationConfig, simulate


class SimulatorTests(unittest.TestCase):
    def test_all_schemes_preserve_bytes_across_loss_models(self):
        data = sample_data(17293)
        for model in ("bernoulli", "gilbert-elliott"):
            for scheme in SCHEMES:
                for seed in range(3):
                    with self.subTest(model=model, scheme=scheme, seed=seed):
                        result = simulate(data, SimulationConfig(scheme=scheme, seed=seed,
                                          channel=ChannelConfig(loss=0.2, ack_loss=0.1, model=model)))
                        self.assertTrue(result.completed)
                        self.assertEqual(result.sha256, hashlib.sha256(data).hexdigest())
                        self.assertEqual(result.bytes_delivered, len(data))

    def test_clean_channel_has_no_retransmissions_and_adaptive_has_no_parity(self):
        for scheme in SCHEMES:
            result = simulate(sample_data(65000), SimulationConfig(scheme=scheme, channel=ChannelConfig(loss=0)))
            self.assertEqual(result.retransmissions, 0)
            if scheme != "fixed":
                self.assertEqual(result.parity_packets, 0)

    def test_selective_repeat_does_not_resend_unlost_packets(self):
        channel = ChannelConfig(loss=0.15)
        data = sample_data(64000)
        sr = simulate(data, SimulationConfig(scheme="sr", seed=4, channel=channel))
        gbn = simulate(data, SimulationConfig(scheme="gbn", seed=4, channel=channel))
        self.assertGreater(gbn.retransmissions, sr.retransmissions)
        self.assertGreaterEqual(sr.retransmissions, sr.original_data_losses)

    def test_one_packet_window_and_partial_tail(self):
        for scheme in SCHEMES:
            result = simulate(b"\x00\xffabc" * 25, SimulationConfig(scheme=scheme, window=1, packet_size=17, channel=ChannelConfig(loss=0.2)))
            self.assertTrue(result.completed)
            self.assertEqual(result.bytes_delivered, 125)

    def test_no_parity_mode_keeps_window_utilization(self):
        data = sample_data(131072)
        channel = ChannelConfig(loss=0)
        sr = simulate(data, SimulationConfig(scheme="sr", channel=channel))
        adaptive = simulate(data, SimulationConfig(channel=channel))
        self.assertLess(adaptive.completion_time_s, sr.completion_time_s * 1.01)

    def test_ack_loss_retransmits_and_event_budget_bounds_total_loss(self):
        result = simulate(sample_data(10000), SimulationConfig(scheme="sr", channel=ChannelConfig(loss=0, ack_loss=0.4)))
        self.assertTrue(result.completed)
        self.assertGreater(result.retransmissions, 0)
        result = simulate(b"abc", SimulationConfig(max_events=100, channel=ChannelConfig(loss=1)))
        self.assertFalse(result.completed)

    def test_bandwidth_and_delay_are_observable(self):
        data = sample_data(102400)
        fast = simulate(data, SimulationConfig(scheme="sr", channel=ChannelConfig(loss=0, delay_ms=0, bandwidth_mbps=5)))
        slow = simulate(data, SimulationConfig(scheme="sr", channel=ChannelConfig(loss=0, delay_ms=0, bandwidth_mbps=1)))
        delayed = simulate(data, SimulationConfig(scheme="sr", channel=ChannelConfig(loss=0, delay_ms=100, bandwidth_mbps=5)))
        self.assertGreaterEqual(slow.completion_time_s, len(data) * 8 / 1_000_000)
        self.assertGreater(slow.completion_time_s, fast.completion_time_s)
        self.assertGreater(delayed.completion_time_s, fast.completion_time_s)

    def test_changing_loss_uses_feedback_and_is_reproducible(self):
        config = SimulationConfig(channel=ChannelConfig(loss=0, phases=((0.15, 0.2), (0.6, 0.01))))
        data = sample_data(131072)
        first, second = simulate(data, config), simulate(data, config)
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertGreater(len({entry["mode"] for entry in first.controller_trace}), 1)
        self.assertTrue(any(not entry["target_met"] for entry in first.controller_trace))

    def test_burst_stationary_loss_and_runs(self):
        channel = Channel(ChannelConfig(loss=0.2, model="gilbert-elliott"), seed=9)
        drops = [channel.transmit(0, 10)[1] for _ in range(10000)]
        self.assertAlmostEqual(sum(drops) / len(drops), 0.2, delta=0.025)
        self.assertGreater(sum(a and b for a, b in zip(drops, drops[1:], strict=False)) / sum(drops), 0.65)

    def test_reordering_releases_only_contiguous_application_data(self):
        data = sample_data(12000)
        channel = ChannelConfig(loss=0, delay_ms=2, bandwidth_mbps=5,
                                reorder_probability=0.4, reorder_delay_ms=25, jitter_ms=3)
        sr = simulate(data, SimulationConfig(scheme="sr", packet_size=256, seed=4, channel=channel), capture_transmissions=True)
        gbn = simulate(data, SimulationConfig(scheme="gbn", packet_size=256, seed=4, channel=channel))
        self.assertTrue(sr.completed)
        self.assertTrue(gbn.completed)
        self.assertEqual(sr.application_sha256, hashlib.sha256(data).hexdigest())
        self.assertEqual(sr.application_bytes_delivered, len(data))
        self.assertGreater(sr.head_of_line_mean_ms, 0)
        self.assertGreater(sr.application_mean_delay_ms, sr.mean_delay_ms)
        self.assertGreater(gbn.retransmissions, sr.retransmissions)
        self.assertTrue(all(packet["arrival_s"] >= packet["start_s"] for packet in sr.transmissions))
        self.assertEqual(sr.to_dict(), simulate(data, SimulationConfig(scheme="sr", packet_size=256, seed=4, channel=channel), capture_transmissions=True).to_dict())

    def test_reliable_metadata_survives_erasure_reordering_and_ack_loss(self):
        data = sample_data(18001)
        for scheme in SCHEMES:
            with self.subTest(scheme=scheme):
                config = SimulationConfig(scheme=scheme, metadata_mode="reliable", metadata_loss=0.6,
                                          seed=9, channel=ChannelConfig(loss=0.1, ack_loss=0.1, delay_ms=3,
                                                                       reorder_probability=0.4, reorder_delay_ms=15))
                result = simulate(data, config)
                self.assertTrue(result.completed)
                self.assertEqual(result.application_sha256, hashlib.sha256(data).hexdigest())
                self.assertEqual(result.application_bytes_delivered, len(data))
                self.assertGreater(result.metadata_retransmissions, 0)
                self.assertGreater(result.metadata_acks, 0)

    def test_missing_metadata_prevents_application_delivery(self):
        result = simulate(sample_data(8192), SimulationConfig(scheme="fixed", metadata_mode="reliable", metadata_loss=1,
                                                             max_events=200, channel=ChannelConfig(loss=0)))
        self.assertFalse(result.completed)
        self.assertEqual(result.application_bytes_delivered, 0)
        self.assertEqual(result.bytes_delivered, 0)
        self.assertGreater(result.metadata_retransmissions, 0)

    def test_default_metadata_is_out_of_band_and_application_metrics_are_explicit(self):
        result = simulate(sample_data(8192), SimulationConfig(scheme="sr", channel=ChannelConfig(loss=0)))
        self.assertEqual(result.metadata_transmissions, 0)
        self.assertEqual(result.head_of_line_mean_ms, 0)
        self.assertEqual(result.application_packet_delays_ms, result.packet_delays_ms)
        self.assertEqual(result.application_sha256, result.sha256)

    def test_impairment_configuration_rejects_nonfinite_values(self):
        for field in ("jitter_ms", "reorder_delay_ms", "reorder_probability"):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    ChannelConfig(**{field: float("nan")})
        with self.assertRaises(ValueError):
            SimulationConfig(metadata_loss=1.1)

    def test_opt_in_burst_policy_reports_model_and_raw_ordered_feedback(self):
        result = simulate(sample_data(262144), SimulationConfig(controller_policy="burst", seed=1,
                          channel=ChannelConfig(loss=0.25, model="gilbert-elliott", bad_to_good=0.3)))
        self.assertTrue(result.completed)
        choices = result.controller_trace
        self.assertTrue(any(entry["risk_model"] == "binary Markov parameter envelope" for entry in choices))
        self.assertTrue(all(entry["uncertainty_applied"] for entry in choices))
        self.assertTrue(all(entry["assumption"] == entry["assumptions"] for entry in choices))
        self.assertTrue(any(entry["transition_samples"] > 0 for entry in choices))

