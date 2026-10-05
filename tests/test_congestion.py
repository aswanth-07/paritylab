import hashlib
import itertools
import math
import unittest

from paritylab.channel import ChannelConfig
from paritylab.congestion import CongestionConfig, FlowConfig, SharedBottleneck, jain_fairness, simulate_competing_flows
from paritylab.experiments import sample_data
from paritylab.simulation import SCHEMES


class SharedFlowTests(unittest.TestCase):
    def test_flows_recover_bytes_through_one_bounded_serialized_link(self):
        data = sample_data(65539)
        config = CongestionConfig(queue_packets=12, channel=ChannelConfig(loss=0.04, ack_loss=0.03, delay_ms=10,
                                                                         bandwidth_mbps=2, reorder_probability=0.1,
                                                                         reorder_delay_ms=15))
        result = simulate_competing_flows([data] * 4, [FlowConfig(scheme, scheme=scheme) for scheme in SCHEMES],
                                         config, capture_transmissions=True)
        self.assertTrue(result["completed"])
        for flow in result["flows"]:
            self.assertEqual(flow["sha256"], hashlib.sha256(data).hexdigest())
            self.assertEqual(flow["bytes_delivered"], len(data))
        self.assertGreater(result["queue_drops"], 0)
        self.assertLessEqual(result["queue_high_water_packets"], config.queue_packets)
        accepted = sorted((packet for packet in result["transmissions"] if packet["loss_reason"] != "queue_overflow"),
                          key=lambda packet: packet["start_s"])
        for previous, current in itertools.pairwise(accepted):
            self.assertGreaterEqual(current["start_s"] + 1e-10, previous["end_s"])
        self.assertEqual(result["serialized_forward_wire_bytes"], sum(packet["wire_bytes"] for packet in accepted))
        self.assertEqual(result["offered_forward_wire_bytes"], sum(packet["wire_bytes"] for packet in result["transmissions"]))
        self.assertLessEqual(result["aggregate_goodput_mbps"], config.channel.bandwidth_mbps)

    def test_parity_counts_against_the_same_congestion_budget_as_data(self):
        config = CongestionConfig(queue_packets=32, channel=ChannelConfig(loss=0, delay_ms=5))
        flow = FlowConfig("fixed", scheme="fixed", window=16, initial_cwnd=1)
        result = simulate_competing_flows([sample_data(32768)], [flow], config, capture_transmissions=True)
        self.assertTrue(result["completed"])
        self.assertEqual(result["flows"][0]["parity_packets"], 4)
        self.assertTrue(any(packet["kind"] == "parity" for packet in result["transmissions"]))
        for packet in result["transmissions"]:
            self.assertLessEqual(packet["inflight"], max(1, math.floor(packet["cwnd"])))
        self.assertEqual(result["flows"][0]["forward_wire_bytes"], (32 + 4) * (1024 + 40))

    def test_aimd_reduces_window_on_congestion_and_clean_adaptive_uses_no_parity(self):
        config = CongestionConfig(queue_packets=8)
        result = simulate_competing_flows([sample_data(262144)] * 2,
                                         [FlowConfig("adaptive", scheme="adaptive", initial_cwnd=32),
                                          FlowConfig("sr", initial_cwnd=32)], config)
        self.assertTrue(result["completed"])
        self.assertGreater(result["queue_drops"], 0)
        for flow in result["flows"]:
            self.assertGreater(flow["congestion_reductions"], 0)
            reductions = [row for row in flow["cwnd_trace"] if row["event"] == "timeout"]
            self.assertTrue(reductions)
            self.assertLess(reductions[0]["cwnd"], flow["config"]["initial_cwnd"])
        clean = simulate_competing_flows([sample_data(65536)], [FlowConfig("adaptive", scheme="adaptive")],
                                        CongestionConfig(queue_packets=128))
        self.assertTrue(clean["completed"])
        self.assertEqual(clean["flows"][0]["parity_packets"], 0)
        self.assertEqual(clean["flows"][0]["retransmissions"], 0)

    def test_fairness_is_recomputed_from_released_bytes_in_common_active_interval(self):
        data = sample_data(262144)
        flows = [FlowConfig("first"), FlowConfig("later", start_s=0.1)]
        result = simulate_competing_flows([data, data], flows)
        self.assertTrue(result["completed"])
        interval = result["common_interval"]
        self.assertTrue(interval["valid"])
        self.assertEqual(interval["start_s"], 0.1)
        rates = []
        for flow in result["flows"]:
            delivered = sum(event["bytes"] for event in flow["application_delivery"]
                            if interval["start_s"] < event["time_s"] <= interval["end_s"])
            rate = delivered * 8 / (interval["end_s"] - interval["start_s"]) / 1_000_000
            self.assertAlmostEqual(rate, interval["rates_mbps"][flow["name"]])
            rates.append(rate)
        self.assertAlmostEqual(interval["jain_fairness"], jain_fairness(rates))
        self.assertGreater(interval["jain_fairness"], 0.8)
        self.assertTrue(result["measurement_bins"])
        self.assertAlmostEqual(sum(row["end_s"] - row["start_s"] for row in result["measurement_bins"]),
                               interval["end_s"] - interval["start_s"])

    def test_shared_bottleneck_tail_drop_does_not_serialize_rejected_packets(self):
        link = SharedBottleneck(CongestionConfig(queue_packets=1, channel=ChannelConfig(loss=0, delay_ms=0, bandwidth_mbps=1)))
        first = link.transmit(0, 1000)
        rejected = link.transmit(0, 1000)
        second = link.transmit(first[2], 1000)
        self.assertFalse(first[1])
        self.assertEqual(rejected[3], "queue_overflow")
        self.assertAlmostEqual(second[2], 0.016)
        self.assertEqual(link.accepted_bytes, 2000)
        self.assertEqual(link.offered_bytes, 3000)

    def test_seed_reproduces_shared_schedules_and_budget_bounds_total_loss(self):
        data = sample_data(32768)
        flows = [FlowConfig("fixed", scheme="fixed"), FlowConfig("sr")]
        config = CongestionConfig(channel=ChannelConfig(loss=0.1, ack_loss=0.1))
        self.assertEqual(simulate_competing_flows([data] * 2, flows, config),
                         simulate_competing_flows([data] * 2, flows, config))
        failed = simulate_competing_flows([data], [FlowConfig("sr")],
                                          CongestionConfig(max_events=100, channel=ChannelConfig(loss=1)))
        self.assertFalse(failed["completed"])
        self.assertTrue(failed["event_budget_exhausted"])
        self.assertFalse(failed["common_interval"]["valid"])
        self.assertIsNone(failed["common_interval"]["jain_fairness"])

    def test_interleaved_flows_do_not_invent_markov_adjacency(self):
        result = simulate_competing_flows([sample_data(131072)] * 2,
                                         [FlowConfig("adaptive", scheme="adaptive", controller_policy="burst"),
                                          FlowConfig("sr")])
        self.assertTrue(result["completed"])
        trace = result["flows"][0]["controller_trace"]
        self.assertTrue(trace)
        self.assertTrue(all(entry["transition_samples"] == 0 for entry in trace))
        self.assertTrue(all("independent fallback" in entry["assumptions"] for entry in trace))

    def test_invalid_fairness_and_configuration_are_rejected(self):
        self.assertEqual(jain_fairness([1, 1]), 1)
        self.assertEqual(jain_fairness([1, 0]), 0.5)
        self.assertIsNone(jain_fairness([0, 0]))
        with self.assertRaises(ValueError):
            jain_fairness([-1, 1])
        with self.assertRaises(ValueError):
            CongestionConfig(queue_packets=0)
        with self.assertRaises(ValueError):
            FlowConfig("flow", start_s=float("nan"))


if __name__ == "__main__":
    unittest.main()
