"""Controlled parameter sensitivity and paired equal-redundancy codec studies."""
import csv
import hashlib
import json
import platform
import statistics
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

from .channel import Channel, ChannelConfig
from .experiments import sample_data
from .fec import Protection, Repair, encode, recover
from .simulation import SCHEMES, SimulationConfig, simulate


def _csv(path, rows):
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _fingerprints():
    return {'src/paritylab/' + p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(__file__).resolve().parent.glob('*.py'))}


def run_sensitivity(output: Path, size=65536, seeds=5, plots=True):
    if size < 1 or seeds < 2:
        raise ValueError('Use a positive file size and at least two seeds')
    output.mkdir(parents=True, exist_ok=True)
    base = SimulationConfig(channel=ChannelConfig(loss=.1))
    conditions = [('baseline', 'baseline', base)]
    for axis, values in [('delay_ms', (0, 25, 100)), ('bandwidth_mbps', (1, 2, 10)),
                         ('window', (8, 16, 64)), ('timeout_ms', (70, 180, 500)),
                         ('packet_size', (512, 1200)), ('fixed_k', (4, 16))]:
        for value in values:
            config = replace(base, channel=replace(base.channel, **{axis: value})) if axis in {'delay_ms', 'bandwidth_mbps'} else replace(base, **{axis: value})
            conditions.append((axis, str(value), config))
    for mean_run in (2, 5, 10):
        conditions.append(('burst_mean_packets', str(mean_run), replace(base,
                          channel=replace(base.channel, model='gilbert-elliott', bad_to_good=1 / mean_run))))
    records = []
    data = sample_data(size)
    for axis, value, condition in conditions:
        schemes = ('fixed',) if axis == 'fixed_k' else SCHEMES
        for scheme in schemes:
            for seed in range(seeds):
                config = replace(condition, scheme=scheme, seed=seed)
                result = simulate(data, config)
                if not result.completed or result.sha256 != hashlib.sha256(data).hexdigest():
                    raise RuntimeError(f'Sensitivity transfer failed: {axis}={value}, {scheme}, seed {seed}')
                records.append({'axis': axis, 'value': value, 'config': asdict(config), **result.to_dict()})
        print(f'Sensitivity {axis}={value} verified', flush=True)
    (output / 'runs.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
    metrics = ('goodput_mbps', 'completion_time_s', 'retransmissions', 'parity_overhead_ratio',
               'p95_delay_ms', 'application_p95_delay_ms')
    groups = {}
    for row in records:
        groups.setdefault((row['axis'], row['value'], row['scheme']), []).append(row)
    summary = []
    for (axis, value, scheme), rows in groups.items():
        aggregate = {'axis': axis, 'value': value, 'scheme': scheme, 'seeds': seeds}
        for metric in metrics:
            values = [row[metric] for row in rows]
            aggregate[metric + '_mean'] = statistics.mean(values)
            aggregate[metric + '_std'] = statistics.stdev(values)
        summary.append(aggregate)
    _csv(output / 'summary.csv', summary)
    manifest = {'recorded_at_utc': datetime.now(timezone.utc).isoformat(), 'python': platform.python_version(),
                'size_bytes': size, 'seeds': list(range(seeds)), 'runs': len(records), 'all_verified': True,
                'payload_sha256': hashlib.sha256(data).hexdigest(), 'source_sha256': _fingerprints(),
                'method': 'One parameter changes from independent 10%, 50ms, 5Mbps, window32, packet1024, fixed block8. Burst cases use the stated Markov mean run. Block-size sweep applies to fixed XOR only.',
                'uncertainty': 'Sample standard deviation across seeds; no confidence interval or universal ranking'}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    lines = ['# Parameter sensitivity', '', f'{len(records)} byte-verified transfers with {seeds} seeds per condition.', '',
             manifest['method'], '', 'Small windows and high delay expose pipeline limits. A timeout shorter than the return path can add unnecessary transmissions. These are implementation measurements at the recorded file size; they do not establish an optimal configuration.', '',
             '| Parameter | Value | Scheme | Goodput Mbps, mean ± sample SD | Retries, mean ± sample SD |',
             '| --- | --- | --- | --- | --- |']
    for row in summary:
        lines.append(f"| {row['axis']} | {row['value']} | {row['scheme']} | {row['goodput_mbps_mean']:.3f} ± {row['goodput_mbps_std']:.3f} | {row['retransmissions_mean']:.1f} ± {row['retransmissions_std']:.1f} |")
    if plots:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(2, 3, figsize=(14, 8), constrained_layout=True)
        for ax, axis in zip(axes.flat, ('delay_ms', 'bandwidth_mbps', 'window', 'timeout_ms', 'packet_size', 'burst_mean_packets'), strict=True):
            for scheme in SCHEMES:
                rows = sorted((r for r in summary if r['axis'] == axis and r['scheme'] == scheme), key=lambda r: float(r['value']))
                ax.errorbar([float(r['value']) for r in rows], [r['goodput_mbps_mean'] for r in rows],
                            yerr=[r['goodput_mbps_std'] for r in rows], marker='o', label=scheme)
            ax.set(xlabel=axis, ylabel='Goodput (Mbps)')
            ax.grid(alpha=.2)
        axes[0, 0].legend()
        fig.suptitle('One-factor sensitivity: mean and sample SD across seeds')
        fig.savefig(output / 'sensitivity.png', dpi=150)
        plt.close(fig)
        lines += ['', '![Sensitivity](sensitivity.png)']
    (output / 'results.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return records


def _wilson(successes, n):
    z, p = 1.959963984540054, successes / n
    scale = 1 + z*z/n
    center = (p + z*z/(2*n))/scale
    half = z*((p*(1-p)/n + z*z/(4*n*n))**.5)/scale
    return max(0, center-half), min(1, center+half)


def run_equal_overhead(output: Path, seeds=5, blocks=1000):
    if seeds < 2 or blocks < 100:
        raise ValueError('Equal-overhead study needs at least two seeds and 100 blocks')
    output.mkdir(parents=True, exist_ok=True)
    packets = [bytes([i, 0, 255, i ^ 170]) for i in range(4)]
    grid = encode(packets, Protection('grid', 4, 2, 2))
    replication = [Repair((i,), packets[i]) for i in range(4)]
    pairwise = [Repair((0, 1), bytes(a ^ b for a, b in zip(packets[0], packets[1], strict=True))),
                Repair((2, 3), bytes(a ^ b for a, b in zip(packets[2], packets[3], strict=True)))]
    single = encode(packets, Protection('xor', 4))[0]
    groups = [(1., {'grid-2x2': grid, 'per-packet-replication': replication}),
              (.5, {'pairwise-xor': pairwise, 'repeated-block-xor': [single, single]})]
    rows = []
    for model in ('bernoulli', 'gilbert-elliott'):
        for loss in (.01, .05, .1, .2):
            for overhead, codes in groups:
                for seed in range(seeds):
                    channel = Channel(ChannelConfig(loss=loss, model=model), seed)
                    for block in range(blocks):
                        # Same erasure mask, ordering and wire count for both codes in a pair.
                        erasures = [channel.transmit(0, 44)[1] for _ in range(4 + len(next(iter(codes.values()))))]
                        for code, repairs in codes.items():
                            known = {i: packet for i, packet in enumerate(packets) if not erasures[i]}
                            recover(known, [repair for i, repair in enumerate(repairs) if not erasures[4 + i]])
                            if any(value != packets[i] for i, value in known.items()):
                                raise AssertionError('Equal-budget decoder produced incorrect bytes')
                            rows.append({'model': model, 'loss': loss, 'parity_ratio': overhead, 'seed': seed,
                                         'block': block, 'code': code, 'erase_mask': ''.join('1' if x else '0' for x in erasures),
                                         'failed': int(len(known) < 4), 'unrecovered_data': 4 - len(known)})
    _csv(output / 'trials.csv', rows)
    aggregates = {}
    for row in rows:
        key = (row['model'], row['loss'], row['parity_ratio'], row['code'])
        a = aggregates.setdefault(key, {'model': key[0], 'loss': key[1], 'parity_ratio': key[2], 'code': key[3], 'blocks': 0, 'failed': 0})
        a['blocks'] += 1
        a['failed'] += row['failed']
    summary = []
    for row in aggregates.values():
        low, high = _wilson(row['failed'], row['blocks'])
        summary.append({**row, 'failure_rate': row['failed']/row['blocks'], 'wilson_low': low, 'wilson_high': high})
    _csv(output / 'summary.csv', summary)
    manifest = {'recorded_at_utc': datetime.now(timezone.utc).isoformat(), 'seeds': list(range(seeds)),
                'blocks_per_seed': blocks, 'decoder_trials': len(rows), 'source_sha256': _fingerprints(),
                'method': 'Paired masks: four data packets, then either two or four equal-width repair packets; no retransmission. Continuous packet-index Markov channel across blocks for burst cases.',
                'uncertainty': '95% Wilson intervals quantify independent sampling; burst trials are correlated so their Wilson columns are descriptive and not valid confidence coverage.',
                'scope': 'Controlled codec residual block failure at exact 50% or 100% parity payload budgets; not transport goodput or controller adaptation.'}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    lines = ['# Equal-overhead codec comparison', '', manifest['method'], '', manifest['scope'], '',
             '| Model | Loss | Parity budget | Code | Failed blocks / trials | Failure rate |',
             '| --- | --- | --- | --- | --- | --- |']
    for row in summary:
        lines.append(f"| {row['model']} | {row['loss']:.0%} | {row['parity_ratio']:.0%} | {row['code']} | {row['failed']} / {row['blocks']} | {row['failure_rate']:.3%} |")
    lines += ['', manifest['uncertainty'], '', 'The ordering is held fixed because burst correlation depends on wire order. The data-plus-parity mask is reused for both members of each pair. Neither pair establishes a universally best code or supports generalization to other block sizes.']
    (output / 'results.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return summary
