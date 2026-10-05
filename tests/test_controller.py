import math
import csv
import gzip
import json
import random
import tempfile
import unittest
from pathlib import Path

from paritylab.calibration import CalibrationCase, _decode_trial, _sequence, calibration_cases, run_calibration
from paritylab.controller import AdaptiveController, wilson_interval
from paritylab.fec import Protection, encode, failure_probability, markov_failure_probability


class ControllerTests(unittest.TestCase):
    def test_legacy_matches_original_algorithm_after_every_feedback(self):
        controller = AdaptiveController()
        expected_loss = 0.0
        for lost, total in ((0, 32), (1, 32), (7, 16), (2, 9), (0, 16), (16, 16)):
            controller.observe(lost, total)
            expected_loss = 0.75 * expected_loss + 0.25 * lost / total
            risks = [(p, failure_probability(p, expected_loss)) for p in controller.candidates]
            feasible = [pair for pair in risks if pair[1] <= 0.01]
            original = (min(feasible, key=lambda pair: (pair[0].overhead, -pair[0].k)) if feasible
                        else min(risks, key=lambda pair: (pair[1], pair[0].overhead)))
            choice = controller.choose()
            self.assertEqual(choice.protection, original[0])
            self.assertEqual(choice.predicted_failure, original[1])
            self.assertEqual(choice.estimated_loss, expected_loss)
            self.assertEqual(choice.target_met, bool(feasible))
            self.assertFalse(choice.uncertainty_applied)

    def test_interval_stays_uncertain_until_samples_arrive(self):
        self.assertEqual(wilson_interval(0, 0), (0.0, 1.0))
        few = wilson_interval(0, 10)
        many = wilson_interval(0, 1000)
        self.assertGreater(few[1], many[1])
        self.assertGreater(many[1], 0)
        self.assertGreater(wilson_interval(20, 100, 0.99)[1], wilson_interval(20, 100, 0.9)[1])

    def test_uncertainty_policy_is_more_cautious_with_short_clean_history(self):
        point = AdaptiveController(policy="legacy", alpha=1)
        careful = AdaptiveController(policy="uncertainty", alpha=1)
        point.observe(0, 16)
        careful.observe(0, 16)
        self.assertEqual(point.choose().protection.mode, "none")
        choice = careful.choose()
        self.assertNotEqual(choice.protection.mode, "none")
        self.assertGreater(choice.predicted_failure, choice.estimated_failure)
        self.assertGreater(choice.loss_upper, choice.estimated_loss)
        self.assertTrue(choice.uncertainty_applied)
        careful.observe(0, 10000)
        self.assertEqual(careful.choose().protection.mode, "none")

    def test_count_feedback_does_not_manufacture_burst_transitions(self):
        controller = AdaptiveController(policy="burst")
        controller.observe(16, 100)
        self.assertEqual(controller.burst_statistics()["transition_samples"], 0)
        self.assertIn("fallback", controller.choose().assumptions)

    def test_gaps_reset_adjacency_and_retained_history_is_bounded(self):
        controller = AdaptiveController(policy="burst", history_size=8)
        controller.observe_sequence([False, False, True])
        controller.observe_sequence([True, False], contiguous=False)
        stats = controller.burst_statistics()
        self.assertEqual(stats["transition_samples"], 3)
        self.assertEqual(stats["counts"]["11"], 0)
        controller.observe(1, 1)
        controller.observe_sequence([False, False])
        self.assertEqual(controller.burst_statistics()["counts"]["10"], 1)
        controller.observe_sequence([True, False] * 30, contiguous=False)
        self.assertEqual(controller.burst_statistics()["transition_samples"], 7)

    def test_burst_policy_uses_real_transition_estimates(self):
        controller = AdaptiveController(policy="burst", alpha=1, history_size=4096)
        sequence = ([False] * 45 + [True] * 5) * 70
        controller.observe_sequence(sequence)
        stats = controller.burst_statistics()
        self.assertAlmostEqual(stats["good_to_bad"], 1 / 45, delta=0.001)
        self.assertAlmostEqual(stats["bad_to_good"], 1 / 5, delta=0.003)
        choice = controller.choose()
        self.assertEqual(choice.risk_model, "binary Markov parameter envelope")
        self.assertIsNotNone(choice.good_to_bad)
        self.assertNotEqual(choice.protection.mode, "none")
        self.assertGreaterEqual(choice.predicted_failure, choice.estimated_failure - 1e-12)
        self.assertIn("no guarantee", choice.assumptions)
        self.assertFalse(choice.target_met)
        independent = AdaptiveController(policy="uncertainty", alpha=1, history_size=4096)
        independent.observe_sequence(sequence)
        self.assertNotEqual(choice.protection, independent.choose().protection)
        self.assertTrue(independent.choose().target_met)

    def test_partial_block_choice_prediction_uses_actual_size(self):
        controller = AdaptiveController(policy="uncertainty")
        controller.observe(3, 100)
        choice = controller.choose(size=1)
        self.assertAlmostEqual(choice.predicted_failure,
                               failure_probability(choice.protection, choice.loss_upper, size=1))
        self.assertTrue(choice.target_met)

    def test_raw_feedback_validation(self):
        for kwargs in ({"policy": "unknown"}, {"alpha": math.nan}, {"target": math.nan},
                       {"confidence": math.inf}, {"history_size": 1}, {"window": 0}):
            with self.assertRaises(ValueError):
                AdaptiveController(**kwargs)
        controller = AdaptiveController()
        for counts in ((-1, 10), (11, 10), (1, 0), (1.5, 10), (True, 10)):
            with self.assertRaises(ValueError):
                controller.observe(*counts)
        for sequence in ([], [0, 1], [False, "lost"]):
            with self.assertRaises(ValueError):
                controller.observe_sequence(sequence)
        with self.assertRaises(ValueError):
            controller.choose(size=0)

    def test_reproducible_decoder_calibration_independent_and_conditional_burst(self):
        protection = Protection("grid", 4, 2, 2)
        packets = [bytes((i, 0, 255, 17 ^ i)) for i in range(4)]
        repairs = encode(packets, protection)
        for model, previous in (("independent", None), ("binary_markov", False), ("binary_markov", True)):
            case = CalibrationCase("test", protection, 4, model, 0.1, 1 / 45, 0.2, previous)
            rng = random.Random(137)
            n = 20000
            failures = sum(_decode_trial(packets, repairs, _sequence(rng, 8, model, 0.1, 1 / 45, 0.2, previous))
                           for _ in range(n))
            tolerance = math.sqrt(math.log(2 / 0.001) / (2 * n))
            self.assertLess(abs(failures / n - case.prediction), tolerance)
        after_good = markov_failure_probability(protection, 1 / 45, 0.2, initial_loss=1 / 45)
        after_bad = markov_failure_probability(protection, 1 / 45, 0.2, initial_loss=0.8)
        self.assertGreater(after_bad, after_good)

    def test_calibration_artifacts_preserve_raw_masks_and_decoder_outcomes(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            result = run_calibration(output, seeds=1, trials_per_seed=2, plots=False)
            cases = calibration_cases()
            with gzip.open(output / "raw-trials.csv.gz", "rt", encoding="utf-8", newline="") as stream:
                raw = list(csv.DictReader(stream))
            self.assertEqual(len(raw), len(cases) * 2)
            counts = {}
            for row in raw:
                case = cases[int(row["case"])]
                packets = [bytes((i, 0, 255, i ^ 170)) for i in range(case.size)]
                repairs = encode(packets, case.protection)
                erased = int(row["erased_mask"])
                losses = [bool(erased & (1 << i)) for i in range(len(packets) + len(repairs))]
                self.assertEqual(int(row["decoder_failed"]), int(_decode_trial(packets, repairs, losses)))
                counts[int(row["case"])] = counts.get(int(row["case"]), 0) + int(row["decoder_failed"])
            for row in result["summary"]:
                self.assertEqual(row["failures"], counts[row["case"]])
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["decoder_trials"], len(raw))
            self.assertEqual(manifest["byte_decoder_wrong_recoveries"], 0)
            self.assertIn("raw-trials.csv.gz", manifest["artifacts_sha256"])


if __name__ == "__main__":
    unittest.main()
