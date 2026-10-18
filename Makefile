# Build the proposal and the summary PDFs (needs TeX Live with biber and latexmk).
#   make            build both PDFs and copy them to pdf/
#   make estimates  print the design estimates of Appendix A
#   make clean      remove LaTeX build files

DOCS := docs
PROPOSAL_PDF := pdf/Fibre-solarisation_MSc-proposal-and-guide.pdf
SUMMARY_PDF := pdf/Fibre-solarisation_MSc-proposal-summary.pdf

.PHONY: all estimates clean

all: $(PROPOSAL_PDF) $(SUMMARY_PDF)

$(PROPOSAL_PDF): $(DOCS)/proposal.tex $(wildcard $(DOCS)/sections/*.tex) $(wildcard $(DOCS)/figures/*.tex) $(DOCS)/references.bib $(DOCS)/fsproposal.sty
	cd $(DOCS) && latexmk -pdf -interaction=nonstopmode -halt-on-error proposal.tex
	mkdir -p pdf && cp $(DOCS)/proposal.pdf $@

$(SUMMARY_PDF): $(DOCS)/summary.tex $(DOCS)/sections/s-body.tex $(wildcard $(DOCS)/figures/*.tex) $(DOCS)/references.bib $(DOCS)/fsproposal.sty
	cd $(DOCS) && latexmk -pdf -interaction=nonstopmode -halt-on-error summary.tex
	mkdir -p pdf && cp $(DOCS)/summary.pdf $@

estimates:
	python3 calc/estimates.py

clean:
	cd $(DOCS) && latexmk -C proposal.tex summary.tex
