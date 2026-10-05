import contextlib
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from paritylab.studies import run_equal_overhead, run_sensitivity


class StudiesTests(unittest.TestCase):
    def test_sensitivity_changes_one_axis_and_preserves_payloads(self):
        with tempfile.TemporaryDirectory() as temporary, contextlib.redirect_stdout(io.StringIO()):
            output = Path(temporary)
            rows = run_sensitivity(output, size=4097, seeds=2, plots=False)
            self.assertTrue(all(r['completed'] and r['application_sha256'] == r['sha256'] for r in rows))
            self.assertEqual(len({r['sha256'] for r in rows}), 1)
            self.assertEqual({r['axis'] for r in rows}, {'baseline', 'delay_ms', 'bandwidth_mbps', 'window',
                'timeout_ms', 'packet_size', 'fixed_k', 'burst_mean_packets'})
            for r in rows:
                if r['axis'] == 'window':
                    self.assertEqual(r['config']['window'], int(r['value']))
                    self.assertEqual(r['config']['channel']['loss'], .1)
                    self.assertEqual(r['config']['channel']['delay_ms'], 50)
                    self.assertEqual(r['config']['packet_size'], 1024)
            manifest = json.loads((output / 'manifest.json').read_text())
            self.assertEqual(manifest['runs'], len(rows))
            self.assertTrue(manifest['source_sha256'])

    def test_equal_budget_pairs_use_identical_masks_and_trial_counts(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            summary = run_equal_overhead(output, seeds=2, blocks=100)
            self.assertTrue(all(r['blocks'] == 200 and 0 <= r['failure_rate'] <= 1 for r in summary))
            with (output / 'trials.csv').open(newline='') as stream:
                rows = list(csv.DictReader(stream))
            groups = {}
            for r in rows:
                key = tuple(r[k] for k in ('model','loss','parity_ratio','seed','block'))
                groups.setdefault(key, []).append(r)
            self.assertTrue(all(len(g) == 2 and g[0]['erase_mask'] == g[1]['erase_mask'] for g in groups.values()))
            self.assertTrue(all(len(g[0]['erase_mask']) == (8 if g[0]['parity_ratio'] == '1.0' else 6) for g in groups.values()))
