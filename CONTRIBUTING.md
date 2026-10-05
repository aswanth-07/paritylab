# Contributing

ParityLab accepts fixes, additional controlled experiments, and improvements to the local interface. Open an issue for a change to the protocol, controller objective, or measurement definitions before implementing it.

## Development

Use Python 3.10 or newer. Install with `python -m pip install -e .`; add `.[plots,reports]` when working on figures or PDFs. The browser interface is plain HTML, CSS, and JavaScript served by the Python package.

Run `python -m unittest discover -s tests -v` after changes. Add tests for observable behavior, especially byte integrity, bounded failure, timer/queue accounting, and controller assumptions.

If a change affects measured source, rerun the affected studies and `python scripts/verify.py`. Do not update manifest hashes to make old results appear current. `python scripts/reproduce.py --calibration` regenerates every registered study and the compressed raw artifacts.

For UI changes, check the comparison, replay, keyboard controls, controller seeking, downloads, and UDP transfer on desktop and mobile. Keep recorded results distinguishable from controls for the next run.

With Node.js 22.13 or newer, `npm ci` and `npm run lint` check JavaScript reachability/names and parse CSS with Lightning CSS. These tools are development dependencies; the demo requires no Node.js runtime.

## Pull requests

Describe the problem, resulting behavior, and checks you ran. Keep claims limited to the supplied evidence. Report sample size, uncertainty, and channel assumptions with experimental results. Remove personal or machine-specific data from screenshots and receipts.
