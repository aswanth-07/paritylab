# Security policy

ParityLab is a local experimental tool. Version 1.x is the maintained line.

The HTTP server and UDP transport bind to loopback. The protocol has bounded transfer sizes, retry counts, and runtime, but it has no peer authentication, encryption, or production congestion control. Do not expose the demo through a public proxy or use it to transfer confidential files. CRC and file digests detect accidental errors rather than authenticate peers.

## Reporting

Use GitHub's private vulnerability reporting for this repository when available. If it is unavailable, contact [the maintainer through their GitHub profile](https://github.com/aswanth-07) to arrange a private channel before sharing exploit details. Report ordinary correctness bugs through an issue.

Include the affected version, operating system, command or request, expected behavior, and a minimal reproduction. Use synthetic payloads and remove credentials, private file contents, and personal paths.
