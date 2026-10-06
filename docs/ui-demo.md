# Presenting ParityLab

Start the service from the project folder:

```powershell
.\.venv\Scripts\python.exe -m paritylab demo
```

Open [http://127.0.0.1:8770](http://127.0.0.1:8770). For a new checkout, install with `python -m pip install -e .` first. Keep the terminal open; Ctrl+C stops the server. If the port is occupied, add `--port 8771` and open that address. The interface, fonts, and reports work offline and need no frontend build.

## A lab presentation sequence

1. Start with **Random loss**: 64 KiB, independent 10% loss, 50 ms one-way delay, 5 Mbps, window 32, and seed 7. The preset runs immediately. Select **5 seeds** and **Run comparison** to measure seeds 7–11. The progress indicator counts completed seeds; the table summarizes 20 transfers.
2. Select **Go-Back-N**, then **Next loss** and **Next retry**. Play at 0.25× or 0.1× to show the outstanding window being resent. Data/retries, parity, and returning acknowledgments use separate lanes. Go-Back-N sends no parity.
3. Select **Fixed XOR** or **Adaptive parity**, restart, and choose **Next repair**. The receiver map marks a packet recovered by parity. Select that packet to inspect its recorded attempts and recovery time. Event buttons in the inspector seek to those times.
4. Switch to **Delivery**. The chart shows the bytes released in order by each protocol for the selected replay seed. Select a point to seek the selected protocol's replay. A receiver can accept later packets while the application waits for an earlier gap; use the packet inspector to show the difference.
5. Compare goodput, completion, retries, and parity. In five-seed mode, values are mean ± sample standard deviation. Select another **Replay seed** to inspect a different run without changing the table's seed group. **File integrity** counts how many completed files match their expected SHA-256.
6. Use **Clean link** to show zero retries and adaptive transmission without parity. Fixed XOR still sends its repair packets. Use **Burst loss** for 15% stationary burst loss and seed 19. Then use **Changing loss** for a 256 KiB file with loss starting at 0%, rising to 15% at 0.25 seconds, falling to 2% at 0.75 seconds, and rising again at 1.2 seconds. Presets retain the selected seed count.
7. Inspect **Adaptive decisions**. Select a block decision to seek its timestamp in the adaptive replay. Show both feasible and infeasible model targets if the recording contains them. The loss estimate and predicted risk describe the controller's model, not a guarantee about the channel.
8. Run **Real UDP transfer**. Choose a protocol and send a separate 32 KiB file through sender, proxy, and receiver processes on this computer. Show the verified byte count, three process IDs, in-order releases, and received digest. Download the transfer JSON to keep the receipt.
9. Use **Present** to hide the introduction and lower panels during packet demonstrations; **Exit presentation** restores them. Save the comparison as CSV or JSON. **Report** opens the experiment report; the footer also links to the proposal and source code.

## Replay and controls

Playback starts only when requested and pauses when the browser tab is hidden. Restart returns to time zero. Scrubbing backward reconstructs the earlier state; later retries, repairs, and application releases disappear. Next-event buttons advance strictly and become disabled when no reachable event remains. A scheme change pauses playback and starts near the beginning of that recording.

The receiver map uses text and color for waiting, in-flight, lost, received, and repaired packets. An outline identifies the selected packet. Go-Back-N can discard a successful out-of-order arrival; that arrival alone does not mark the packet received. Packet inspector buttons describe recorded events, including events later than the current replay position. The in-order byte count increases only when the receiver releases contiguous data to the application.

**More settings** contains the sender window, starting seed, and acknowledgment loss. Changing controls marks the displayed results as a previous recording until **Run comparison** completes. Recent runs hold the latest five completed groups in memory; reloading the page clears them. Restoring a group also restores its settings. A failed comparison leaves the previous completed group available.

**Copy settings link** uses the completed group's settings, seed count, and selected protocol. Opening the link on the same server reruns that configuration; it does not store a result file, transfer receipt, selected replay seed, or playback position. If clipboard access fails, the interface exposes the link for manual copying. The local server must be running for the URL to work.

Protocol tabs support Left/Right, Home, and End. The packet map has one Tab stop; Left/Right select adjacent packets, Up/Down move by a row, and Home/End select the first or last packet. Outside native controls, Space plays or pauses, R restarts, and L seeks the next loss. The scrubber, fields, selectors, and scrollable tables use native keyboard behavior. On narrow screens, results scroll within their own table rather than shrinking the measurements.

## Reading the measurements

Single-seed mode runs one trial per scheme. Five-seed mode runs the starting seed and the next four seeds, then computes a mean and sample standard deviation. This describes a small sample, not a confidence interval or significance test. All schemes use the same configured channel conditions and seeds, but their send schedules consume random draws differently; they do not share a fixed loss mask. The interactive runs are separate from the saved paper studies.

The simulator uses 1 KiB packets. Goodput counts useful file bytes and excludes redundant transmissions. Completion is when the receiver has the file. The replay continues until the sender has its acknowledgments. Delivery curves use the chosen replay seed, with steps at recorded application-release times. Comparison bars are scaled within each metric row; a longer retry bar is not an improvement.

The replay reads recorded simulator transmissions and receiver events. It does not implement a second protocol model. Positions between start and arrival are illustrative; timestamps, loss outcomes, receiver acceptance, and release events come from the simulator. Separate block-loss feedback is not drawn. The aggregate FEC recovery metric counts first-attempt losses repaired, while the replay's repaired count follows recorded receiver acceptance through parity.

The default controller assumes independent, equal data and parity loss. A feasible 1% modeled block-failure target does not guarantee 1% failures under bursts or uncertain estimates. The legacy interface policy reports full-candidate risks even when the admitted block is shorter. Optional command-line policies evaluate actual partial-block risks and report interval/model assumptions.

## Socket checks and exports

The socket check uses the visible channel, window, starting seed, acknowledgment loss, and selected transfer protocol for a fixed 32 KiB file with 512-byte packets. Every message class traverses its proxy. It has a 25-second transfer budget and reports bounded failures with a recovery suggestion. Extreme delay or loss may need lower loss or a smaller delay. A completed receipt remains visible if a subsequent check fails; changed-settings text identifies when it belongs to an earlier configuration. Wall time includes process scheduling and has a different boundary from simulated time. Use `socket-run --scheme all` for a saved four-protocol socket comparison.

Comparison CSV contains one row per protocol per seed: four rows in single-seed mode or 20 in five-seed mode. JSON contains the recorded settings, measurements, transmissions, receiver events, and controller decisions for each trial. Changing controls after a run does not alter those downloads. Transfer JSON contains the separate socket receipt and its exact configuration.

The wheel includes the interface, fonts, and PDFs. `scripts/build_release.py` verifies their retrieval after installing the wheel in a fresh environment. Saved paper studies retain hash-verified historical source in `output/measured-source/`. Their audit reports whether that source also matches the current checkout. Use `python scripts/audit_measurements.py --require-current` when current-source measurements are required.

## Fonts

Atkinson Hyperlegible regular and bold are self-hosted under `web/assets/fonts`, with their SIL Open Font License. The files come from the [Google Fonts repository](https://github.com/google/fonts/tree/main/ofl/atkinsonhyperlegible). Icons are authored vector paths; packet marks and delivery charts are runtime geometry.
