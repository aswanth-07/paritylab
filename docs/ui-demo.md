# Presenting ParityLab

Start the service from the project folder and open http://127.0.0.1:8770:

```powershell
.\.venv\Scripts\python.exe -m paritylab demo
```

For another source checkout, install with `python -m pip install -e .` first. The interface uses local fonts and the Python standard-library server; it needs no frontend build. Keep the terminal open. Ctrl+C stops the service. If the port is occupied, add `--port 8771` and open that address.

## A lab presentation sequence

1. Start with the default 64 KiB file, independent 10% loss, 50 ms delay, 5 Mbps bandwidth, window 32, and seed 7. Run comparison, select a scheme, and play its recorded transmissions. Slow playback to 0.25Ã— and drag the scrubber to pause on losses or returning acknowledgments.
2. Compare useful throughput, receiver completion, retries, and parity. All four completed rows should show Verified. Adaptive protection minimizes modeled redundancy subject to a risk target; it does not always produce the highest throughput.
3. Use Clean to show zero retries and adaptive transmission without parity. Fixed XOR still pays for repair packets.
4. Use Bursts to run 15% stationary burst loss with seed 19. The configured percentage describes the channel model, not the exact percentage erased in a short file. Compare the observed retries and inspect the adaptive decisions.
5. Use Changing to run a 256 KiB file with loss starting at 0%, rising to 15% at 0.25 seconds, falling to 2% at 0.75 seconds, and rising again at 1.2 seconds. Short transfers may finish before a later phase. Select a controller decision to seek to that block in the adaptive replay.
6. Run socket transfer. Choose Transfer protocol and transfer a separate 32 KiB file through actual sender, proxy, and receiver processes using the displayed channel, ACK loss, and window settings. Show the digest, verified byte count, three process IDs, and Download transfer JSON.
7. Download CSV for the comparison table, or full JSON for the settings, measurements, transmission events, and controller trace. Open Report for the experiment report and its 2020â€“2026 references.

## Controls and measurement limits

Advanced settings contains the sender window, random seed, and ACK loss. Changes take effect on Run comparison; the recorded settings remain printed below the table. The presets set and run their own complete configurations. Arrow keys, Home, and End change the selected protocol tab. The scrubber and native controls also work from the keyboard. Playback starts only when requested and pauses when the browser tab is hidden.

Each comparison runs one trial per scheme using identical configured channel settings and seed. Different transmission counts consume random draws differently, so the schemes do not share a fixed loss mask. Use `python -m paritylab experiment --seeds 5` for the saved 260-run sweep and averages.

The simulator uses 1 KiB packets. Completion measures the last received file byte; replay ends when the sender has the acknowledgments. Replay paths are illustrative. Its timestamps and loss outcomes are recorded simulator events. The visualization includes data, parity, and packet acknowledgments; separate block-loss feedback is not drawn. Recovery counts are aggregate measurements.

Controller predictions assume independent, equal data and parity loss. A 1% modeled block-failure target does not guarantee 1% failures under bursts or uncertain estimates. The default legacy UI policy shows applied block choices and full-candidate risks, even when the actual admitted block is shorter. Optional CLI policies evaluate actual partial-block risks and report interval/model assumptions.

The full socket check applies the visible channel settings to a separate fixed 32 KiB trial with 512-byte packets. All message classes traverse its proxy. It has a 25-second transfer budget and reports bounded failure with a recovery suggestion. Extreme delay/loss may need a lower-loss or higher-bandwidth trial. Recorded result details persist until another check is run; the downloaded JSON retains exact settings and input digest. Wall time includes process scheduling and is not directly comparable with the emulator. Use `socket-run --scheme all` for a saved four-scheme socket comparison.

The interface and PDFs also ship in the installable wheel. The Experiment report link opens the measured report. The legacy `udp-demo` CLI remains a smaller example; the UI uses the full transport.

## Fonts

Atkinson Hyperlegible regular and bold are self-hosted under `web/assets/fonts`, with their SIL Open Font License. The files come from the [Google Fonts repository](https://github.com/google/fonts/tree/main/ofl/atkinsonhyperlegible). The interface uses authored vector icons and runtime packet geometry.
