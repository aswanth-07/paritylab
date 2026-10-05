"""Evidence-producing shared-bottleneck and robust localhost transport runs."""
import hashlib
import json
import platform
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .channel import ChannelConfig
from .congestion import CongestionConfig, FlowConfig, simulate_competing_flows
from .experiments import sample_data
from .simulation import SCHEMES
from .socket_transport import SocketConfig, socket_transfer
from .studies import _fingerprints


def run_congestion_evaluation(output: Path, size=262144, seeds=5, plots=True):
    if size < 1 or seeds < 2:
        raise ValueError('Use positive transfer size and at least two seeds')
    output.mkdir(parents=True, exist_ok=True)
    data = sample_data(size)
    records = []
    conditions = [('aimd_equal', [('left', 'sr', 'aimd'), ('right', 'sr', 'aimd')]),
                  ('uncontrolled_equal', [('left', 'sr', 'none'), ('right', 'sr', 'none')]),
                  ('aimd_vs_uncontrolled', [('left', 'sr', 'aimd'), ('right', 'sr', 'none')])]
    conditions += [(f'{scheme}_vs_sr', [('left', scheme, 'aimd'), ('right', 'sr', 'aimd')]) for scheme in SCHEMES]
    for condition, specifications in conditions:
        for queue in (8, 32):
            for seed in range(seeds):
                config = CongestionConfig(channel=ChannelConfig(loss=.01, ack_loss=.01, delay_ms=20, bandwidth_mbps=2),
                                          queue_packets=queue, seed=seed)
                flows = [FlowConfig(name, scheme=scheme, congestion_control=control) for name, scheme, control in specifications]
                row = simulate_competing_flows([data, data], flows, config, capture_transmissions=seed == 0)
                if not row['completed'] or any(r['sha256'] != hashlib.sha256(data).hexdigest() for r in row['flows']):
                    raise RuntimeError(f'Competing flow failed: {condition}, queue {queue}, seed {seed}')
                records.append({'condition': condition, 'flow_configs': [asdict(f) for f in flows], **row})
            print(f'Congestion {condition}, queue {queue} verified', flush=True)
    (output / 'runs.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
    import statistics
    summary = []
    for condition, _ in conditions:
        for queue in (8, 32):
            rows = [r for r in records if r['condition'] == condition and r['queue_capacity_packets'] == queue]
            summary.append({'condition': condition, 'queue_packets': queue, 'seeds': seeds,
                            'aggregate_goodput_mean': statistics.mean(r['aggregate_goodput_mbps'] for r in rows),
                            'aggregate_goodput_std': statistics.stdev(r['aggregate_goodput_mbps'] for r in rows),
                            'jain_mean': statistics.mean(r['common_interval']['jain_fairness'] for r in rows),
                            'jain_std': statistics.stdev(r['common_interval']['jain_fairness'] for r in rows),
                            'queue_drops_mean': statistics.mean(r['queue_drops'] for r in rows)})
    (output / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    manifest = {'recorded_at_utc': datetime.now(timezone.utc).isoformat(), 'python': platform.python_version(),
                'source_sha256': _fingerprints(), 'seeds': list(range(seeds)), 'runs': len(records),
                'flow_transfers': len(records)*2, 'bytes_per_flow': size, 'all_verified': True,
                'scope': 'Shared finite FIFO bottleneck; AIMD model includes parity and retries in congestion window. Local emulator evaluation, not RFC-compliant TCP or Internet validation.',
                'fairness': 'Jain index measured from actual in-order useful bytes on common active interval; finite files and start/tail effects remain. Same configured seed set does not imply identical masks after different packet schedules.'}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    lines = ['# Competing-flow evaluation', '', f"{len(records)} shared-bottleneck runs, {len(records)*2} byte-verified file transfers.", '',
             manifest['scope'], '', manifest['fairness'], '',
             '| Configuration | Queue packets | Aggregate goodput Mbps, mean ± sample SD | Jain fairness, mean ± sample SD | Mean queue drops |',
             '| --- | --- | --- | --- | --- |']
    for r in summary:
        lines.append(f"| {r['condition']} | {r['queue_packets']} | {r['aggregate_goodput_mean']:.3f} ± {r['aggregate_goodput_std']:.3f} | {r['jain_mean']:.3f} ± {r['jain_std']:.3f} | {r['queue_drops_mean']:.1f} |")
    lines += ['', 'The comparison preserves negative results. Equal AIMD settings can still obtain unequal finite-transfer shares. FEC that hides residual data loss still pays for repair packets in the congestion budget. Arbitrary Internet use remains outside the implementation scope.']
    if plots:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        row = next(r for r in records if r['condition'] == 'aimd_vs_uncontrolled' and r['queue_capacity_packets'] == 8 and r['config']['seed'] == 0)
        fig, axes = plt.subplots(2, 1, figsize=(10, 7), constrained_layout=True)
        for flow in row['flows']:
            trace = flow['cwnd_trace']
            axes[0].step([t['time_s'] for t in trace], [t['cwnd'] for t in trace], where='post', label=flow['name'])
            bins = row['measurement_bins']
            axes[1].step([b['start_s'] for b in bins], [b['rates_mbps'][flow['name']] for b in bins], where='post', label=flow['name'])
        axes[0].set(xlabel='Virtual time (s)', ylabel='Congestion window (packets)', title='AIMD left vs uncontrolled right: queue 8, seed 0')
        axes[1].set(xlabel='Virtual time (s)', ylabel='Useful release rate (Mbps)')
        for ax in axes:
            ax.legend()
            ax.grid(alpha=.2)
        fig.savefig(output / 'competing-flows.png', dpi=150)
        plt.close(fig)
        lines += ['', '![Shared bottleneck](competing-flows.png)']
    (output / 'results.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    return records


def run_socket_evaluation(output: Path, size=32768, seeds=3):
    if size < 1 or seeds < 2:
        raise ValueError('Use positive file size and at least two seeds')
    output.mkdir(parents=True, exist_ok=True)
    data = sample_data(size)
    scenarios = [('independent', ChannelConfig(loss=.15, ack_loss=.1, delay_ms=2), {}),
                 ('burst', ChannelConfig(loss=.1, ack_loss=.05, delay_ms=2, model='gilbert-elliott'), {}),
                 ('metadata_reorder', ChannelConfig(loss=.05, ack_loss=.1, delay_ms=2, jitter_ms=3,
                     reorder_probability=.2, reorder_delay_ms=10), {'metadata_loss': .4, 'duplicate_probability': .1, 'corruption_probability': .02})]
    records = []
    for scenario, channel, options in scenarios:
        for scheme in SCHEMES:
            for seed in range(seeds):
                received, row = socket_transfer(data, SocketConfig(scheme=scheme, channel=channel, seed=seed,
                              max_seconds=20, **options), output / f'{scenario}-{scheme}-{seed}.bin')
                if received != data or len({p['pid'] for p in row['processes']}) != 3:
                    raise AssertionError('Socket evaluation lost bytes or process separation')
                records.append({'scenario': scenario, **row})
            print(f'Socket {scenario}, {scheme} verified', flush=True)
    (output / 'runs.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
    manifest = {'recorded_at_utc': datetime.now(timezone.utc).isoformat(), 'python': platform.python_version(),
                'source_sha256': _fingerprints(), 'runs': len(records), 'seeds': list(range(seeds)), 'size_bytes': size,
                'all_verified': True, 'expected_sha256': hashlib.sha256(data).hexdigest(),
                'scope': 'Actual localhost UDP with independent sender/receiver/proxy processes; all manifests, symbols, feedback, ACKs and completion messages impaired.',
                'reproducibility': 'Payloads/settings/seeds/receipts reproduce the protocol experiment; wall-clock scheduling changes arrival order and random draw counts, so timings/masks are not deterministic and not Internet benchmarks.'}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    lines = ['# Full socket transport evidence', '', f'{len(records)} actual three-process transfers verified {size} bytes each.', '',
             manifest['scope'], '', manifest['reproducibility'], '',
             '| Scenario | Scheme | Seed | Retries | Parity packets | Metadata drops | In-order bytes released |',
             '| --- | --- | --- | --- | --- | --- | --- |']
    for r in records:
        lines.append(f"| {r['scenario']} | {r['sender']['scheme']} | {r['config']['seed']} | {r['sender']['retransmissions']} | {r['sender']['parity_packets']} | {r['proxy']['dropped_metadata']} | {r['bytes_delivered']} |")
    (output / 'results.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    return records
