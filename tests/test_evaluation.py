import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from paritylab.evaluation import run_congestion_evaluation


class EvaluationTests(unittest.TestCase):
    def test_registered_competing_flow_experiments_share_capacity_and_verify_both_files(self):
        with tempfile.TemporaryDirectory() as temporary, contextlib.redirect_stdout(io.StringIO()):
            output = Path(temporary)
            rows = run_congestion_evaluation(output, size=8193, seeds=2, plots=False)
            self.assertEqual(len(rows), 28)
            self.assertTrue(all(r['completed'] for r in rows))
            self.assertTrue(all(len(r['flows']) == 2 and all(f['completed'] and f['bytes_delivered'] == 8193 for f in r['flows']) for r in rows))
            self.assertTrue(all(r['aggregate_goodput_mbps'] <= 2 for r in rows))
            self.assertTrue(all(r['queue_high_water_packets'] <= r['queue_capacity_packets'] for r in rows))
            self.assertEqual(json.loads((output / 'manifest.json').read_text())['flow_transfers'], 56)
            self.assertTrue((output / 'results.md').is_file())
