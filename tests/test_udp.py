import unittest

from paritylab.experiments import sample_data
from paritylab.udp_demo import udp_transfer


class UDPTests(unittest.TestCase):
    def test_loopback_binary_transfer_with_loss_and_partial_tail(self):
        for scheme in ("sr", "fixed", "adaptive"):
            data = sample_data(6017)
            received, stats = udp_transfer(data, loss=0.2, seed=3, scheme=scheme)
            self.assertEqual(received, data)
            self.assertTrue(stats["verified"])
            self.assertGreater(stats["dropped_datagrams"], 0)

    def test_total_loss_exits_with_bounded_retries(self):
        with self.assertRaises(TimeoutError):
            udp_transfer(b"no delivery", loss=1, max_rounds=2)
