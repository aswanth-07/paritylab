# Review 2 output screenshots

These captures show the implemented demo and its measured output. Use the full desktop capture and plots for Assessment 9; the cropped images make individual results easier to read.

| File | What it shows | Measurement scope |
| --- | --- | --- |
| [slow-link.jpg](slow-link.jpg) | Settings, replay, four-protocol comparison, original-adaptive comparison, completed UDP receipt, and saved study table. | Live simulation: seeds 100–104. Saved study: seeds 100–119. UDP: one wall-time transfer. |
| [comparison.jpg](comparison.jpg) | Goodput, completion, retries, parity, integrity, and original-adaptive comparison. | Five simulation seeds, 64 KiB, 10% independent loss, 50 ms one-way delay, 1 Mbps, window 32, zero ACK loss. |
| [udp-receipt.jpg](udp-receipt.jpg) | Received bytes, retries/parity, three process IDs, and SHA-256. | One 32 KiB UDP transfer, 512-byte packets, seed 100, same channel settings as above. Wall time is separate from simulated time. |
| [mobile.jpg](mobile.jpg) | Complete method selector and channel controls at a 432-pixel test viewport. | Responsive-interface evidence; not another performance measurement. |
| [literature-desktop.jpg](literature-desktop.jpg) | Recent-source links, publication status and implementation boundaries at 1280 pixels. | October 7 literature/copy update; frozen study unchanged. |
| [literature-mobile.jpg](literature-mobile.jpg) | Wrapped references and source links at 390 pixels. | Responsive copy check; no page overflow or new performance measurement. |
| [udp-transfer.json](udp-transfer.json) | Downloaded receipt corresponding to the UDP screenshot. | Actual byte verification and transport configuration. |

The five-seed comparison shows 52.6% higher mean goodput than original adaptive and 32.5% shorter mean completion. The final twenty-seed slow-link result is 64.5% higher goodput and 39.6% shorter completion. Different seed counts give different averages; do not substitute one for the other.

The screenshots were captured after results settled. The replay can be paused partway through even though the complete transfer metrics are already available. The comparison and UDP images are crops of the full desktop capture; their contents were not edited.

The [complete results](../review-2-results.md) include all conditions, sample standard deviations, cases where fixed XOR wins, and the two component comparisons. The [goodput plot](../../output/review-2/goodput.png) and [completion plot](../../output/review-2/completion.png) use the final twenty-seed study.
