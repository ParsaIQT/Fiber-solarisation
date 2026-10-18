# Reduced fibre solarisation in an oxygen-free atmosphere

MSc thesis project: **"Experimental demonstration of reduced fibre solarisation in an oxygen-free atmosphere"**

Thorlabs P3-375PM-FC patch cables (PM-S350-HP, pure-silica core, FC/APC) carry a few mW of 369.5 nm light
(Yb⁺ cooling and detection). They couple very well right after a fresh polish. Their throughput then
falls at a rate that grows with power, at both the input and the output end. This project tests
whether keeping the end faces in an oxygen-free atmosphere halts the degradation, using 3D-printed
enclosures with oxygen absorbers or an inert-gas purge. The experiment is designed to identify the
real cause if oxygen is not it.

## Documents

| Path | What it is |
| --- | --- |
| [`pdf/Fibre-solarisation_MSc-proposal-and-guide.pdf`](pdf/Fibre-solarisation_MSc-proposal-and-guide.pdf) | Full research proposal (Part I), student guide (Part II), appendices (design estimates, draft SOPs, logging spec), ~150 verified references |
| [`pdf/Fibre-solarisation_MSc-proposal-summary.pdf`](pdf/Fibre-solarisation_MSc-proposal-summary.pdf) | 4-page summary |
| `docs/` | LaTeX sources (`proposal.tex`, `summary.tex`, `sections/`, `figures/` in TikZ, `references.bib`, style `fsproposal.sty`) |
| `calc/estimates.py` | Design estimates quoted in Appendix A: end-face intensity, contamination flux, film thickness and heating, gas diffusion in silica, purge, permeation and absorber budgets, optics, statistics |

## Main points of the proposal

- **The damage is at the end faces.** Re-polishing restores the throughput, and O₂ cannot diffuse
  into silica at room temperature (nanometres per year). Any oxygen effect must therefore act at the
  surfaces.
- **The literature points both ways.** For hydrocarbon contamination of UV optics, oxygen, and often
  water, is *protective*. This holds for space lasers, UV cavities in ion-trap labs and GaN diodes.
  Under CW light at our intensity, deposits grow fastest at *trace* O₂. For siloxanes from silicones,
  O₂ ≥ 100 ppm has been found to *accelerate* deposits on a 410 nm fibre end face. Particles and
  restructuring of the silica surface itself (seen at 405 nm) are further candidates.
- **The decisive test** runs identical fibres in parallel in ambient air, clean dry synthetic air,
  clean dry N₂ and a sealed absorber cell. Only the air/N₂ pair differs in O₂ alone. Later arms add an
  O₂ dose–response, humidity, polymer and silicone challenges, and a crossed input/output design.
- **Practical outcome:** a qualified 3D-printed cell (CAD, BOM, SOPs) that holds < 100 ppm O₂ for months,
  tested on a working 369.5 nm link. If the atmosphere turns out not to be the cause, the fall-back is
  a recommendation for end-face engineering (end caps, H₂-loaded or hollow-core fibre).

## Building

Requires TeX Live (with `biber` and `latexmk`) and Python 3 (standard library only).

```sh
make            # builds both PDFs into pdf/
make estimates  # prints the numbers used in Appendix A
make clean
```

The `docs/` folder can also be uploaded to Overleaf as is (compiler: pdfLaTeX, bibliography: Biber).

## Status

Version 1.0 (18 October 2026): draft for discussion between the supervisor and the student. Names are
placeholders. Prices are US list prices or rough estimates; replace them with quotes.
