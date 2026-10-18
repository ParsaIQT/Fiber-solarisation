# Reduced fibre solarisation in an oxygen-free atmosphere

MSc thesis project: **"Experimental demonstration of reduced fibre solarisation in an oxygen-free atmosphere"**

Single-mode, polarisation-maintaining UV fibres carrying a few mW of 369.5 nm light (Yb⁺ cooling and
detection) couple very well right after a fresh polish. Their throughput then falls at a rate that
grows with power, and both the input and output end faces are affected. This project tests whether
keeping the end faces in an oxygen-free atmosphere halts the degradation, using 3D-printed enclosures
with oxygen absorbers or an inert-gas purge. The experiment is designed to identify the real cause if
oxygen is not it.

## Contents

| Path | What it is |
| --- | --- |
| [`pdf/Fibre-solarisation_MSc-proposal-and-guide.pdf`](pdf/Fibre-solarisation_MSc-proposal-and-guide.pdf) | Full research proposal (Part I) and student guide (Part II), with appendices |
| [`pdf/Fibre-solarisation_MSc-proposal-summary.pdf`](pdf/Fibre-solarisation_MSc-proposal-summary.pdf) | Short summary of the proposal |
| `docs/` | LaTeX sources (`proposal.tex`, `summary.tex`, `sections/`, `figures/`, `references.bib`, style `fsproposal.sty`) |
| `calc/estimates.py` | Back-of-envelope design estimates quoted in Appendix A (intensities, contamination flux, heating, gas diffusion, purge and absorber budgets, optics, statistics) |

## Building

Requires TeX Live (with `biber` and `latexmk`) and Python 3 (standard library only).

```sh
make            # builds both PDFs into pdf/
make estimates  # prints the numbers used in Appendix A
make clean
```

The `docs/` folder can also be uploaded to Overleaf as is (compiler: pdfLaTeX, bibliography: Biber).

## Status

Version 1.0 (October 2026): draft for discussion between the supervisor and the student. Names,
dates and local facilities are left as placeholders. Prices in the budget are rough estimates;
replace them with quotes.
