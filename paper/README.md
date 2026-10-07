# Research manuscript

The manuscript is **Decoder risk and finite-transfer tradeoffs in adaptive packet parity**, by A Aswanth Raj and Dr. Ranjithkumar S, School of Computer Science and Engineering, VIT Vellore.

It is a complete venue-neutral technical manuscript with methods, results, discussion, limitations, references dated 2020-2026, five figures, seven main tables, and reproducibility/sensitivity appendices. It reports an empirical artifact and mixed findings. It does not claim a new code, an optimal controller, or Internet validation.

Read [the current Markdown manuscript](manuscript.md). The [retained October 5 PDF](../output/pdf/paritylab-paper.pdf) predates the October 7 reference update. [pdf-export.json](pdf-export.json) binds that export to its source hash; the audit reports when it differs from current source. The editable [LaTeX source](main.tex) embeds its vector figures and bibliography; it works as a standalone document. [The template](manuscript-template.md) is the authored text, with generated-table tokens. Edit that template and rebuild, rather than editing generated tables or the generated LaTeX.

The October 7 source update adds four 2025–2026 references without changing historical results. Twelve references were read in full and two at abstract level, with reading locations and publication status recorded individually. The separate cost-plus-feedback lab evaluation is context, not a replacement for the paper's risk-target experiments.

```sh
python -m pip install -e .
python -m pip install -r requirements-reproduction.txt
python scripts/build_paper.py
python scripts/build_paper.py --text-only
python scripts/build_paper.py --pdf
python scripts/audit_paper.py --render
```

The first build command reanalyses saved data and writes the manuscript, figures and manifest. Use `--text-only` to update text/references while analysis and plot data remain unchanged. The `--pdf` command explicitly exports through an existing `pdflatex`; it disables automatic package installation and records export provenance. The native editor supports the standalone source, but the October 7 preview attempt failed before parsing because its Windows sandbox setup refresh failed. The earlier October 5 export used local MiKTeX after a separate platform-directory error. The October 7 update keeps the editor open and has no new paper PDF export.

[analysis.json](analysis.json) contains reconstructed counts, exact-error maxima, feasibility diagnostics, and paired seed contrasts. [plot-data.json](plot-data.json) records the plotted values. PNG and SVG versions are in [figures/](figures/). [manifest.json](manifest.json) hashes inputs and generated outputs. The measured source remains revision `1ee75227af7288491722a42813203a136ed37948`; the manuscript introduces no change to the measured implementation.

[claim-evidence.md](claim-evidence.md) maps conclusions to evidence and exclusions. [literature-search.md](literature-search.md) records positioning and search limits; it makes no exhaustive novelty claim. [review.md](review.md) records structured self-review and submission prerequisites. [references.json](references.json) records reading locations and source status; [references.bib](references.bib) supports transfer into a venue template.

Before formal submission, both authors must review the complete manuscript and confirm remaining contribution details, corresponding-author contact, conflicts, applicable ethics declarations, and final approval. A Aswanth Raj confirmed that the work received no funding and that Dr. Ranjithkumar S provided mentorship and supervision. A venue must then be chosen and its current template, length, anonymity, AI-disclosure and supplementary-material rules applied. No absent conflict declaration or coauthor approval has been invented. The paper has not been submitted or posted as a preprint.

[verification.json](verification.json) records the saved-data audit, exact reconstruction of all nine tables, selected prose-number checks, citation/BibTeX consistency, plot bounds, and PDF inspection. Rendering writes every page and contact sheets to the ignored tmp/pdfs/paper/ directory for visual review. A chosen venue may require a shorter main text and separate supplement.
