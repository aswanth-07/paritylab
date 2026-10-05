# Research manuscript

The manuscript is **Decoder risk and finite-transfer tradeoffs in adaptive packet parity**, by A Aswanth Raj and Dr. Ranjithkumar S, School of Computer Science and Engineering, VIT Vellore.

It is a complete venue-neutral technical manuscript with methods, results, discussion, limitations, ten references dated 2020-2026, five figures, seven main tables, and reproducibility/sensitivity appendices. It reports an empirical artifact and mixed findings. It does not claim a new code, an optimal controller, or Internet validation.

Read [the PDF](../output/pdf/paritylab-paper.pdf) or [the Markdown manuscript](manuscript.md). The editable [LaTeX source](main.tex) embeds its vector figures and bibliography; it works as a standalone document. [The template](manuscript-template.md) is the authored text, with generated-table tokens. Edit that template and rebuild, rather than editing generated tables or the generated LaTeX.

```sh
python -m pip install -e .
python -m pip install -r requirements-reproduction.txt
python scripts/build_paper.py
python scripts/build_paper.py --pdf
python scripts/audit_paper.py --render
```

The first build command reanalyses saved data and writes the manuscript, figures and manifest. The `--pdf` command additionally exports through an existing `pdflatex`; it disables automatic package installation. The native editor is also suitable for the standalone source. In the authoring session, its compiler failed before reading the source because it could not find platform directories, so the PDF was exported and inspected using the existing local MiKTeX installation.

[analysis.json](analysis.json) contains reconstructed counts, exact-error maxima, feasibility diagnostics, and paired seed contrasts. [plot-data.json](plot-data.json) records the plotted values. PNG and SVG versions are in [figures/](figures/). [manifest.json](manifest.json) hashes inputs and generated outputs. The measured source remains revision `1ee75227af7288491722a42813203a136ed37948`; the manuscript introduces no change to the measured implementation.

[claim-evidence.md](claim-evidence.md) maps conclusions to evidence and exclusions. [literature-search.md](literature-search.md) records positioning and search limits; it makes no exhaustive novelty claim. [review.md](review.md) records structured self-review and submission prerequisites. [references.json](references.json) records reading locations and source status; [references.bib](references.bib) supports transfer into a venue template.

Before formal submission, both authors must review the complete manuscript and confirm remaining contribution details, corresponding-author contact, conflicts, applicable ethics declarations, and final approval. A Aswanth Raj confirmed that the work received no funding and that Dr. Ranjithkumar S provided mentorship and supervision. A venue must then be chosen and its current template, length, anonymity, AI-disclosure and supplementary-material rules applied. No absent conflict declaration or coauthor approval has been invented. The paper has not been submitted or posted as a preprint.

[verification.json](verification.json) records the saved-data audit, exact reconstruction of all nine tables, selected prose-number checks, citation/BibTeX consistency, plot bounds, and PDF inspection. Rendering writes every page and contact sheets to the ignored tmp/pdfs/paper/ directory for visual review. A chosen venue may require a shorter main text and separate supplement.
