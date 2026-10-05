import argparse
import json
from pathlib import Path

from .channel import ChannelConfig
from .experiments import run_experiments, sample_data
from .simulation import SCHEMES, SimulationConfig, simulate
from .udp_demo import udp_transfer


def build_parser():
    parser = argparse.ArgumentParser(description="Packet recovery experiments with retransmission and parity")
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="Open the local interactive network lab service")
    demo.add_argument("--port", type=int, default=8770)
    run = commands.add_parser("simulate", help="Transfer deterministic bytes in virtual time")
    run.add_argument("--scheme", choices=(*SCHEMES, "all"), default="all")
    run.add_argument("--bytes", type=int, default=65536)
    run.add_argument("--input", type=Path)
    run.add_argument("--loss", type=float, default=0.1)
    run.add_argument("--ack-loss", type=float, default=0)
    run.add_argument("--delay-ms", type=float, default=50)
    run.add_argument("--bandwidth-mbps", type=float, default=5)
    run.add_argument("--model", choices=("bernoulli", "gilbert-elliott"), default="bernoulli")
    run.add_argument("--window", type=int, default=32)
    run.add_argument("--packet-size", type=int, default=1024)
    run.add_argument("--fixed-k", type=int, default=8)
    run.add_argument("--timeout-ms", type=float)
    run.add_argument("--seed", type=int, default=7)
    run.add_argument("--output", type=Path)
    sweep = commands.add_parser("experiment", help="Run the 0-20% sweep, burst test, and changing-loss test")
    sweep.add_argument("--bytes", type=int, default=131072)
    sweep.add_argument("--seeds", type=int, default=3)
    sweep.add_argument("--output", type=Path, default=Path("output/experiments"))
    sweep.add_argument("--no-plots", action="store_true")
    udp = commands.add_parser("udp-demo", help="Verify actual loopback datagrams with selective block repair")
    udp.add_argument("--input", type=Path)
    udp.add_argument("--bytes", type=int, default=32768)
    udp.add_argument("--loss", type=float, default=0.15)
    udp.add_argument("--seed", type=int, default=7)
    udp.add_argument("--scheme", choices=("sr", "fixed", "adaptive"), default="adaptive")
    udp.add_argument("--output", type=Path, default=Path("output/udp/received.bin"))
    transport = commands.add_parser("socket-run", help="Run all four windowed transports in separate localhost processes")
    transport.add_argument("--input", type=Path)
    transport.add_argument("--bytes", type=int, default=32768)
    transport.add_argument("--scheme", choices=(*SCHEMES, "all"), default="all")
    transport.add_argument("--loss", type=float, default=.1)
    transport.add_argument("--ack-loss", type=float, default=.05)
    transport.add_argument("--metadata-loss", type=float)
    transport.add_argument("--delay-ms", type=float, default=5)
    transport.add_argument("--bandwidth-mbps", type=float, default=5)
    transport.add_argument("--model", choices=("bernoulli", "gilbert-elliott"), default="bernoulli")
    transport.add_argument("--packet-size", type=int, default=512)
    transport.add_argument("--window", type=int, default=32)
    transport.add_argument("--fixed-k", type=int, default=8)
    transport.add_argument("--timeout-ms", type=float)
    transport.add_argument("--max-seconds", type=float, default=20)
    transport.add_argument("--max-attempts", type=int, default=150)
    transport.add_argument("--seed", type=int, default=7)
    transport.add_argument("--duplicate-probability", type=float, default=0)
    transport.add_argument("--corruption-probability", type=float, default=0)
    transport.add_argument("--output", type=Path, default=Path("output/socket"))
    studies = commands.add_parser("studies", help="Run one-factor sensitivity and exact equal-parity-budget codec comparisons")
    studies.add_argument("--bytes", type=int, default=65536)
    studies.add_argument("--seeds", type=int, default=5)
    studies.add_argument("--blocks", type=int, default=1000)
    studies.add_argument("--output", type=Path, default=Path("output/studies"))
    studies.add_argument("--no-plots", action="store_true")
    calibration = commands.add_parser("calibrate", help="Validate independent/Markov decoder predictions and optional controller policies")
    calibration.add_argument("--seeds", type=int, default=5)
    calibration.add_argument("--trials-per-seed", type=int, default=4000)
    calibration.add_argument("--output", type=Path, default=Path("output/calibration"))
    calibration.add_argument("--no-plots", action="store_true")
    calibration.set_defaults(bytes=1)
    congestion = commands.add_parser("congestion", help="Evaluate competing flows through a shared finite-buffer bottleneck")
    congestion.add_argument("--bytes", type=int, default=262144)
    congestion.add_argument("--seeds", type=int, default=5)
    congestion.add_argument("--output", type=Path, default=Path("output/congestion"))
    congestion.add_argument("--no-plots", action="store_true")
    sockets = commands.add_parser("socket-evaluate", help="Verify all socket schemes under forward/ACK/control loss, jitter, reordering and corruption")
    sockets.add_argument("--bytes", type=int, default=32768)
    sockets.add_argument("--seeds", type=int, default=3)
    sockets.add_argument("--output", type=Path, default=Path("output/socket-evaluation"))
    run.add_argument("--jitter-ms", type=float, default=0)
    run.add_argument("--reorder-probability", type=float, default=0)
    run.add_argument("--reorder-delay-ms", type=float, default=0)
    run.add_argument("--metadata-mode", choices=("idealized", "reliable"), default="idealized")
    run.add_argument("--metadata-loss", type=float)
    run.add_argument("--controller-policy", choices=("legacy", "uncertainty", "burst"), default="legacy")
    transport.add_argument("--jitter-ms", type=float, default=0)
    transport.add_argument("--reorder-probability", type=float, default=0)
    transport.add_argument("--reorder-delay-ms", type=float, default=0)
    transport.add_argument("--controller-policy", choices=("legacy", "uncertainty", "burst"), default="legacy")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "demo":
            from .server import serve
            serve(args.port)
            return
        if args.bytes < 1:
            raise ValueError("--bytes must be positive")
        if args.command == "experiment":
            run_experiments(args.output, args.bytes, args.seeds, not args.no_plots)
            print(f"Results saved in {args.output.resolve()}")
        elif args.command == "studies":
            from .studies import run_equal_overhead, run_sensitivity
            run_sensitivity(args.output / "sensitivity", args.bytes, args.seeds, not args.no_plots)
            run_equal_overhead(args.output / "equal-overhead", args.seeds, args.blocks)
            print(f"Controlled studies saved in {args.output.resolve()}")
        elif args.command == "calibrate":
            from .calibration import run_calibration
            result = run_calibration(args.output, seeds=args.seeds, trials_per_seed=args.trials_per_seed, plots=not args.no_plots)
            print(json.dumps(result["manifest"], indent=2))
        elif args.command == "congestion":
            from .evaluation import run_congestion_evaluation
            run_congestion_evaluation(args.output, args.bytes, args.seeds, not args.no_plots)
        elif args.command == "socket-evaluate":
            from .evaluation import run_socket_evaluation
            run_socket_evaluation(args.output, args.bytes, args.seeds)
        elif args.command == "socket-run":
            from .socket_transport import SocketConfig, socket_transfer
            data = args.input.read_bytes() if args.input else sample_data(args.bytes)
            channel = ChannelConfig(loss=args.loss, ack_loss=args.ack_loss, delay_ms=args.delay_ms,
                                    bandwidth_mbps=args.bandwidth_mbps, model=args.model, jitter_ms=args.jitter_ms,
                                    reorder_probability=args.reorder_probability, reorder_delay_ms=args.reorder_delay_ms)
            rows = []
            for scheme in (SCHEMES if args.scheme == "all" else (args.scheme,)):
                config = SocketConfig(scheme=scheme, seed=args.seed, channel=channel, window=args.window,
                        packet_size=args.packet_size, fixed_k=args.fixed_k, timeout_ms=args.timeout_ms,
                        metadata_loss=args.metadata_loss, max_seconds=args.max_seconds, max_attempts=args.max_attempts,
                        duplicate_probability=args.duplicate_probability, corruption_probability=args.corruption_probability)
                from dataclasses import replace
                config = replace(config, controller_policy=args.controller_policy)
                _, row = socket_transfer(data, config, args.output / f"{scheme}-received.bin")
                rows.append(row)
                print(f"{scheme}: verified {row['bytes_delivered']} bytes, {row['sender']['retransmissions']} retries, "
                      f"{row['sender']['elapsed_s']:.3f}s, distinct process IDs {[p['pid'] for p in row['processes']]}", flush=True)
            (args.output / "comparison.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
        elif args.command == "udp-demo":
            data = args.input.read_bytes() if args.input else sample_data(args.bytes)
            received, stats = udp_transfer(data, args.loss, args.seed, scheme=args.scheme)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(received)
            args.output.with_suffix(".json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
            print(json.dumps(stats, indent=2))
        else:
            data = args.input.read_bytes() if args.input else sample_data(args.bytes)
            channel = ChannelConfig(args.loss, args.delay_ms, args.bandwidth_mbps, args.ack_loss, args.model,
                                    jitter_ms=args.jitter_ms, reorder_probability=args.reorder_probability,
                                    reorder_delay_ms=args.reorder_delay_ms)
            rows = [simulate(data, SimulationConfig(scheme=scheme, seed=args.seed, channel=channel,
                    window=args.window, packet_size=args.packet_size, fixed_k=args.fixed_k, timeout_ms=args.timeout_ms,
                    metadata_mode=args.metadata_mode, metadata_loss=args.metadata_loss, controller_policy=args.controller_policy)).to_dict()
                    for scheme in (SCHEMES if args.scheme == "all" else (args.scheme,))]
            print(f"{'Scheme':10} {'Complete':9} {'Goodput Mbps':>12} {'Time s':>10} {'Resends':>9} {'Parity':>9}")
            for row in rows:
                print(f"{row['scheme']:10} {str(row['completed']):9} {row['goodput_mbps']:12.3f} {row['completion_time_s']:10.3f} {row['retransmissions']:9} {row['parity_packets']:9}")
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(rows, indent=2), encoding="utf-8")
            if not all(row["completed"] for row in rows):
                parser.exit(1, "One or more transfers exceeded the event budget.\n")
    except (ValueError, OSError, TimeoutError, RuntimeError) as error:
        parser.exit(2, f"Error: {error}\n")


if __name__ == "__main__":
    main()

