# Build targets for the Ricci microstructure arXiv submission.
#
# Two paths to the final PDF:
#
#   make pdf            — pdflatex + bibtex, assumes TeX Live is installed
#   make pdf-pandoc     — pandoc + xelatex, assumes pandoc >= 2.0
#
# Plus a submission bundle:
#
#   make arxiv-bundle   — zips the minimal files arXiv requires
#   make clean          — removes LaTeX aux and build artefacts
#
# All targets assume you run `make -C paper/ricci_microstructure <target>`
# from the repository root; relative figure paths are resolved from this
# Makefile's directory.

PAPER          := paper
BIB            := references
FIGURES_DIR    := ../../results/figures
FIGURES        := $(wildcard $(FIGURES_DIR)/fig*.png)
ARXIV_BUNDLE   := ricci_microstructure_arxiv.zip
BUILD_DIR      := build

.PHONY: pdf pdf-pandoc arxiv-bundle clean check

pdf: $(PAPER).pdf

$(PAPER).pdf: $(PAPER).tex $(BIB).bib $(FIGURES)
	@command -v pdflatex >/dev/null 2>&1 || { echo "pdflatex not found — install TeX Live or use 'make pdf-pandoc'"; exit 1; }
	@command -v bibtex   >/dev/null 2>&1 || { echo "bibtex not found — install TeX Live"; exit 1; }
	pdflatex -interaction=nonstopmode $(PAPER).tex
	bibtex $(PAPER)
	pdflatex -interaction=nonstopmode $(PAPER).tex
	pdflatex -interaction=nonstopmode $(PAPER).tex

pdf-pandoc: $(PAPER).md $(BIB).bib
	@command -v pandoc >/dev/null 2>&1 || { echo "pandoc not found — install via apt / brew / conda"; exit 1; }
	pandoc $(PAPER).md \
	  --from markdown \
	  --to latex \
	  --standalone \
	  --bibliography=$(BIB).bib \
	  --natbib \
	  --output=$(PAPER)-from-md.tex
	@echo "Wrote $(PAPER)-from-md.tex. Convert to PDF via a LaTeX toolchain:"
	@echo "    pdflatex $(PAPER)-from-md.tex && bibtex $(PAPER)-from-md && pdflatex $(PAPER)-from-md.tex && pdflatex $(PAPER)-from-md.tex"

arxiv-bundle: $(PAPER).pdf
	@rm -rf $(BUILD_DIR)/arxiv
	@mkdir -p $(BUILD_DIR)/arxiv
	cp $(PAPER).tex $(BIB).bib $(PAPER).bbl $(BUILD_DIR)/arxiv/
	@cp $(FIGURES) $(BUILD_DIR)/arxiv/
	@sed -i.bak 's|\.\./\.\./results/figures/||g' $(BUILD_DIR)/arxiv/$(PAPER).tex
	@rm -f $(BUILD_DIR)/arxiv/$(PAPER).tex.bak
	@cd $(BUILD_DIR)/arxiv && zip -q -r ../../$(ARXIV_BUNDLE) .
	@echo "arXiv bundle written to $(ARXIV_BUNDLE)"
	@echo "Contents:"
	@unzip -l $(ARXIV_BUNDLE) | sed 's/^/  /'

check:
	@echo "Title length (char):"
	@head -1 $(PAPER).tex | wc -c
	@echo "Abstract length (char, approx):"
	@awk '/begin\{abstract\}/,/end\{abstract\}/' $(PAPER).tex | wc -c
	@echo "Figure files present:"
	@for f in $(FIGURES); do test -s "$$f" && echo "  OK $$f" || echo "  MISSING $$f"; done
	@echo "BibTeX entries:"
	@grep -c '^@' $(BIB).bib

clean:
	@rm -f $(PAPER).aux $(PAPER).bbl $(PAPER).blg $(PAPER).log $(PAPER).out $(PAPER).toc
	@rm -f $(PAPER)-from-md.tex $(PAPER)-from-md.aux $(PAPER)-from-md.log
	@rm -rf $(BUILD_DIR)
	@rm -f $(ARXIV_BUNDLE)
	@rm -f $(PAPER).pdf
