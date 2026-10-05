# Full socket transport evidence

36 actual three-process transfers verified 32768 bytes each.

Actual localhost UDP with independent sender/receiver/proxy processes; all manifests, symbols, feedback, ACKs and completion messages impaired.

Payloads/settings/seeds/receipts reproduce the protocol experiment; wall-clock scheduling changes arrival order and random draw counts, so timings/masks are not deterministic and not Internet benchmarks.

| Scenario | Scheme | Seed | Retries | Parity packets | Metadata drops | In-order bytes released |
| --- | --- | --- | --- | --- | --- | --- |
| independent | gbn | 0 | 113 | 0 | 0 | 32768 |
| independent | gbn | 1 | 255 | 0 | 1 | 32768 |
| independent | gbn | 2 | 100 | 0 | 0 | 32768 |
| independent | sr | 0 | 17 | 0 | 0 | 32768 |
| independent | sr | 1 | 20 | 0 | 0 | 32768 |
| independent | sr | 2 | 14 | 0 | 0 | 32768 |
| independent | fixed | 0 | 13 | 8 | 0 | 32768 |
| independent | fixed | 1 | 19 | 8 | 0 | 32768 |
| independent | fixed | 2 | 12 | 8 | 0 | 32768 |
| independent | adaptive | 0 | 16 | 20 | 4 | 32768 |
| independent | adaptive | 1 | 16 | 29 | 4 | 32768 |
| independent | adaptive | 2 | 15 | 6 | 0 | 32768 |
| burst | gbn | 0 | 31 | 0 | 0 | 32768 |
| burst | gbn | 1 | 46 | 0 | 0 | 32768 |
| burst | gbn | 2 | 0 | 0 | 0 | 32768 |
| burst | sr | 0 | 11 | 0 | 0 | 32768 |
| burst | sr | 1 | 15 | 0 | 0 | 32768 |
| burst | sr | 2 | 5 | 0 | 0 | 32768 |
| burst | fixed | 0 | 10 | 8 | 0 | 32768 |
| burst | fixed | 1 | 14 | 8 | 0 | 32768 |
| burst | fixed | 2 | 5 | 8 | 0 | 32768 |
| burst | adaptive | 0 | 8 | 0 | 3 | 32768 |
| burst | adaptive | 1 | 15 | 31 | 4 | 32768 |
| burst | adaptive | 2 | 6 | 0 | 0 | 32768 |
| metadata_reorder | gbn | 0 | 769 | 0 | 3 | 32768 |
| metadata_reorder | gbn | 1 | 852 | 0 | 0 | 32768 |
| metadata_reorder | gbn | 2 | 401 | 0 | 2 | 32768 |
| metadata_reorder | sr | 0 | 15 | 0 | 3 | 32768 |
| metadata_reorder | sr | 1 | 16 | 0 | 0 | 32768 |
| metadata_reorder | sr | 2 | 15 | 0 | 2 | 32768 |
| metadata_reorder | fixed | 0 | 13 | 8 | 3 | 32768 |
| metadata_reorder | fixed | 1 | 11 | 8 | 0 | 32768 |
| metadata_reorder | fixed | 2 | 11 | 8 | 2 | 32768 |
| metadata_reorder | adaptive | 0 | 14 | 17 | 7 | 32768 |
| metadata_reorder | adaptive | 1 | 12 | 10 | 13 | 32768 |
| metadata_reorder | adaptive | 2 | 13 | 16 | 5 | 32768 |
