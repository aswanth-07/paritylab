# Full windowed localhost transport

`python -m paritylab socket-run --scheme all` launches three separate processes per transfer: a sender, receiver, and impairment proxy. All four schemes transfer the same file. The orchestrator verifies the received bytes, records each process ID and exit code, and stops every child on success or failure. Output files and JSON receipts appear under `output/socket`.

## Wire and reliability

Each UDP datagram contains a version marker, CRC-32, JSON control fields, and an unmodified binary symbol. CRC failures are discarded and recovered through retransmission. CRC detects accidental corruption; it does not authenticate a peer. The service binds only to loopback addresses.

A retried manifest declares file length, symbol width, packet count, scheme, and expected SHA-256. Every data and repair datagram repeats its block descriptor, so losing a standalone metadata packet cannot leave a surviving symbol uninterpretable. A conflicting descriptor is rejected. Parity indices must match an equation in the declared codec. The final exchange is retried until the sender receives the receiver's file length and digest.

Go-Back-N discards out-of-order data and acknowledges the received prefix. A base timeout resends the outstanding window. Selective Repeat acknowledges received and reconstructed sequences individually and retries only unacknowledged data. Fixed XOR and adaptive parity share that Selective Repeat state machine. The window bounds outstanding original data; parity shares the serialized link and bandwidth. A full parity block waits for enough window space, while unprotected data uses every available slot.

The adaptive sender asks for raw first-attempt arrivals after the original block transmission. Reports and their reverse feedback can be lost. Report requests are retried, and duplicate feedback is applied once per block. The receiver waits a grace interval covering configured jitter and reordering before reporting. Feedback preserves the loss observation even when parity reconstruction succeeds.

## Impairments and measurement

The proxy serializes actual framed datagram bytes in separate forward and reverse queues, then adds propagation delay, jitter, and extra reordering delay. It injects independent or packet-index Markov burst erasures. Manifest, report-request, and final-message losses can use a separate metadata probability. ACKs and receiver feedback use the reverse-loss probability. Duplication and bit corruption are optional. Control traffic receives no exemption.

`--metadata-loss 0.4 --ack-loss 0.1 --jitter-ms 3 --reorder-probability 0.2 --reorder-delay-ms 10 --duplicate-probability 0.1 --corruption-probability 0.02` exercises these behaviors. `socket-evaluate` runs all schemes across registered independent, burst, and combined impairment cases with multiple seeds.

Receipts contain original send, received-byte availability, and in-order application-release timestamps for every sequence. The application releases a byte only after all preceding data is available. These processes share the operating system's monotonic clock. Timing includes process scheduling and framing costs. Counted wire bytes are UDP payload datagram bytes including the protocol framing; IP/UDP headers are outside that counter.

The file limit is 64 MiB and at most 131,072 symbols. Runtime and per-sequence retries are bounded. A permanently lost manifest, forward path, or reverse path returns failure rather than a success receipt. An incomplete transfer does not create the requested output file.

## Model boundaries

The socket transport verifies full-window reliability and byte codecs over actual local processes. Its operating-system scheduling and packet ordering prevent bitwise timing or erasure-mask reproducibility from a seed alone. Recorded settings, input digest, traces, and receipts make each measured run inspectable. Compare deterministic emulator results for controlled timing conclusions.

Optional `--controller-policy uncertainty` uses an approximate independent-loss confidence bound; `burst` uses fitted binary Markov transitions when enough ordered feedback exists. Fitted intervals can exclude the true parameters, changing loss can violate stationarity, and independent fallback is unsafe as a burst-risk guarantee. The calibration report measures those limits.

The separate `udp-demo` command remains a smaller block-at-a-time demonstration with loss-exempt control messages. The UI now runs the full three-process socket transport and exports its receipt. The shared-bottleneck congestion experiment is a separate deterministic teaching model with a finite queue and congestion window. This localhost socket transport does not implement a congestion-controlled Internet transport, cryptographic authentication, path-MTU discovery, or RFC-compliant TCP/QUIC. Keep it local.
