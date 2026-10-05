import itertools
import unittest

from paritylab.controller import AdaptiveController
from paritylab.fec import (Protection, encode, failure_probability,
                           markov_failure_probability, markov_failure_upper_bound, recover)


class CodecTests(unittest.TestCase):
    def test_partial_grid_risks_match_byte_decoder_including_lost_repairs(self):
        protection = Protection("grid", 9, 3, 3)
        for size in (0, 1, 3, 5):
            packets = [bytes((i, 0, 255)) for i in range(size)]
            repairs = encode(packets, protection)
            total = size + len(repairs)
            probability, weighted_failure = 0.17, 0.0
            for erased in range(1 << total):
                known = {i: packet for i, packet in enumerate(packets) if not erased & (1 << i)}
                recover(known, [repair for j, repair in enumerate(repairs) if not erased & (1 << (size + j))])
                failed = len(known) != size
                if failed:
                    count = erased.bit_count()
                    weighted_failure += probability ** count * (1 - probability) ** (total - count)
            self.assertAlmostEqual(failure_probability(protection, probability, size=size), weighted_failure)

    def test_markov_risk_matches_each_decoder_pattern_probability(self):
        protection = Protection("grid", 4, 2, 2)
        a, b, initial = 0.13, 0.31, 0.72
        for size in (1, 3, 4):
            packets = [bytes((i, 255)) for i in range(size)]
            repairs = encode(packets, protection)
            total = size + len(repairs)
            weighted_failure = probability_sum = 0.0
            for erased in range(1 << total):
                outcomes = [bool(erased & (1 << i)) for i in range(total)]
                probability = initial if outcomes[0] else 1 - initial
                for previous, current in itertools.pairwise(outcomes):
                    chance = 1 - b if previous else a
                    probability *= chance if current else 1 - chance
                probability_sum += probability
                known = {i: packet for i, packet in enumerate(packets) if not outcomes[i]}
                recover(known, [repair for j, repair in enumerate(repairs) if not outcomes[size + j]])
                weighted_failure += probability * (len(known) != size)
            self.assertAlmostEqual(probability_sum, 1.0)
            self.assertAlmostEqual(markov_failure_probability(protection, a, b, initial_loss=initial, size=size), weighted_failure)

    def test_markov_reduces_to_independent_when_transitions_do_not_depend_on_state(self):
        for protection in (Protection("none", 16), Protection("xor", 16), Protection("grid", 9, 3, 3)):
            for loss in (0.0, 0.03, 0.3, 1.0):
                self.assertAlmostEqual(markov_failure_probability(protection, loss, 1 - loss),
                                       failure_probability(protection, loss), places=11)

    def test_markov_rectangle_bound_covers_interior_and_collapses_at_point(self):
        protection = Protection("grid", 4, 2, 2)
        bound = markov_failure_upper_bound(protection, (0.01, 0.08), (0.1, 0.5), initial_loss_bounds=(0.02, 0.7))
        for a in (0.01, 0.033, 0.08):
            for b in (0.1, 0.23, 0.5):
                for initial in (0.02, 0.33, 0.7):
                    self.assertGreaterEqual(bound, markov_failure_probability(protection, a, b, initial_loss=initial) - 1e-12)
        point = markov_failure_probability(protection, 0.04, 0.2, initial_loss=0.3)
        exact_bound = markov_failure_upper_bound(protection, (0.04, 0.04), (0.2, 0.2), initial_loss_bounds=(0.3, 0.3))
        self.assertAlmostEqual(point, exact_bound)

    def test_risk_models_reject_invalid_parameters_and_absorbing_start_ambiguity(self):
        protection = Protection("xor", 2)
        for loss in (float("nan"), float("inf"), -0.1, 1.1):
            with self.assertRaises(ValueError):
                failure_probability(protection, loss)
        with self.assertRaises(ValueError):
            failure_probability(protection, 0.1, size=3)
        with self.assertRaises(ValueError):
            markov_failure_probability(protection, 0, 0)
        self.assertEqual(markov_failure_probability(protection, 0, 0, initial_loss=0), 0)
        self.assertEqual(markov_failure_probability(protection, 0, 0, initial_loss=1), 1)
        with self.assertRaises(ValueError):
            markov_failure_upper_bound(protection, (0.4, 0.2), (0.2, 0.2))

    def test_each_single_erasure_with_binary_payload(self):
        packets = [bytes([i, 0, 255, i ^ 170]) for i in range(9)]
        for protection in [Protection("xor", 9), Protection("grid", 9, 3, 3)]:
            for missing in range(9):
                known = {i: p for i, p in enumerate(packets) if i != missing}
                recover(known, encode(packets, protection))
                self.assertEqual([known[i] for i in range(9)], packets)

    def test_grid_peels_chain_but_not_rectangle(self):
        packets = [bytes([i]) for i in range(9)]
        parity = encode(packets, Protection("grid", 9, 3, 3))
        known = {i: p for i, p in enumerate(packets) if i not in {0, 1, 4}}
        self.assertEqual(len(recover(known, parity)), 3)
        known = {i: p for i, p in enumerate(packets) if i not in {0, 1, 3, 4}}
        self.assertEqual(recover(known, parity), {})

    def test_partial_grid_and_missing_parity(self):
        packets = [b"abc", b"xyz", b"\0\xff\0"]
        parity = encode(packets, Protection("grid", 9, 3, 3))
        known = {0: packets[0]}
        recover(known, parity[1:])
        self.assertEqual([known[i] for i in range(3)], packets)
        known = {0: packets[0]}
        recover(known, [])
        self.assertEqual(len(known), 1)

    def test_xor_risk_includes_lost_parity(self):
        p = 0.1
        self.assertAlmostEqual(failure_probability(Protection("xor", 2), p), 0.028)

    def test_grid_risk_matches_byte_decoder_for_every_pattern(self):
        protection = Protection("grid", 4, 2, 2)
        packets = [bytes([i + 17]) for i in range(4)]
        repairs = encode(packets, protection)
        p, risk = 0.13, 0.0
        for erased in itertools.product((False, True), repeat=8):
            known = {i: packet for i, packet in enumerate(packets) if not erased[i]}
            recover(known, [r for j, r in enumerate(repairs) if not erased[4+j]])
            if len(known) != 4:
                loss_count = sum(erased)
                risk += p ** loss_count * (1-p) ** (8-loss_count)
        self.assertAlmostEqual(failure_probability(protection, p), risk)

    def test_controller_reports_infeasibility_and_returns_to_clean_mode(self):
        controller = AdaptiveController(alpha=1)
        self.assertEqual(controller.choose().protection.mode, "none")
        controller.observe(20, 100)
        self.assertFalse(controller.choose().target_met)
        controller.observe(0, 100)
        self.assertEqual(controller.choose().protection.mode, "none")

    def test_controller_selects_minimum_feasible_overhead(self):
        controller = AdaptiveController(alpha=1)
        controller.observe(3, 100)
        choice = controller.choose()
        self.assertTrue(choice.target_met)
        feasible = [c for c in controller.candidates if failure_probability(c, 0.03) <= 0.01]
        self.assertEqual(choice.protection.overhead, min(c.overhead for c in feasible))

