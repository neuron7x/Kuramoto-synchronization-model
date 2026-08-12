# Ricci Microstructure — arXiv / SSRN Submission Kit

Working draft + build pipeline for the Ricci cross-sectional edge paper,
derived from the 10-axis empirical audit in
`research/microstructure/FINDINGS.md`.

## Files

| Path | Role |
|------|------|
| `paper.tex` | Camera-ready LaTeX source. arXiv-compatible, single `\documentclass{article}`, `natbib` for citations. 67-char title, 1634-char abstract, 5 figure floats, 11-row verdict table. |
| `paper.md` | Markdown draft (first revision). Retained as the narrative source of truth; kept in sync with `paper.tex` content. |
| `references.bib` | 13 BibTeX entries covering every citation: Ollivier, Sandhu–Georgiou–Tannenbaum, Cont–Kukanov–Stoikov, Peng DFA, Schreiber TE, López de Prado DSR+AFML, Politis–Romano, Dickey–Fuller, Newey–West, Kuramoto, Ng–Perron, Samal et al. on network Ricci. |
| `Makefile` | Build targets for `pdf`, `pdf-pandoc`, `arxiv-bundle`, `check`, `clean`. |
| `../../research/microstructure/FINDINGS.md` | Evidence appendix. Referenced from `paper.tex` Section 4 and Section "Reproducibility". |
| `../../results/figures/fig{0..4}*.png` | Five PNG figures. arXiv accepts PNG, so no conversion needed. |

## Build

From the repository root:

```bash
# Pre-flight: title/abstract length, figures present, bib entries
make -C paper/ricci_microstructure check

# Build the PDF (requires pdflatex + bibtex)
make -C paper/ricci_microstructure pdf

# Alternative: pandoc → LaTeX (requires pandoc >= 2.0)
make -C paper/ricci_microstructure pdf-pandoc

# Package for arXiv upload
make -C paper/ricci_microstructure arxiv-bundle
```

The `arxiv-bundle` target rewrites the `../../results/figures/` prefix in
the LaTeX source so figures can live flat inside the zip — arXiv's build
environment expects the figure files in the same directory as `paper.tex`.

## arXiv submission steps (manual)

The automation stops at the zip. The actual upload is the author's
signature — credentials and endorsement belong to a human, not a script.

1. **Verify locally.** `make pdf` and eyeball `paper.pdf`. Check:
   - Title renders without overflow.
   - Abstract fits in the arXiv abstract box.
   - Every figure displays at a readable resolution.
   - All citations resolve (no `[?]`).
2. **Build the bundle.** `make arxiv-bundle` → `ricci_microstructure_arxiv.zip`.
3. **Endorsement.** First submissions to a new arXiv category (e.g.
   `q-fin.TR`) require endorsement from an already-registered author. If
   this is your first submission in that category, use the arXiv
   endorsement system to request one before starting the upload.
4. **Upload.** Go to <https://arxiv.org/submit>, pick "New submission",
   upload `ricci_microstructure_arxiv.zip`, set:
   - Primary classification: `q-fin.TR` (Trading and Market
     Microstructure).
   - Cross-lists: `q-fin.ST` (Statistical Finance).
   - License: CC-BY-4.0 (matches the manuscript license statement).
5. **arXiv will build the PDF server-side.** If the build fails, fix and
   re-upload; arXiv keeps all revisions.
6. **Note the arXiv ID** and record it in `paper/ricci_microstructure/
   SUBMISSION_LOG.md` (create on first submission, commit on main).

## SSRN submission (parallel track)

SSRN indexes for the finance professional audience. Submit the same PDF
to:

- **Mathematical Finance eJournal** — quantitative theory audience.
- **Quantitative Finance: Ex-Post Experiment eJournal** — empirical /
  back-test audience.

Upload `paper.pdf` at <https://www.ssrn.com> → "Submit a Paper". SSRN
does not compile LaTeX — you upload the PDF your local build produced.

## Venue roadmap (post-arXiv)

1. **Journal of Computational Finance** — practitioner rigour. Reuse the
   arXiv TeX verbatim; the journal accepts LaTeX submissions. ~8--12
   week review cycle.
2. **Quantitative Finance (Taylor & Francis)** — pure quant audience.
   Lead with Ricci theory, empirics secondary. ~10--14 week review.
3. **NeurIPS / ICML workshop on ML for Finance** — 4-page position-
   paper derivative of Sections 1, 3, and 4; defer to the annual
   deadline.

## Pre-flight checklist

- [x] Abstract $\leq$ 1920 characters (arXiv limit). Currently 1634.
- [x] Title $\leq$ 240 characters. Currently 67.
- [x] All 5 figures present at `results/figures/fig{0..4}*.png`.
- [x] `references.bib` compiles under BibTeX (13 entries, no TODO).
- [x] `make check` passes.
- [ ] `make pdf` produces a clean PDF with no `[?]` citations and no
      overfull/underfull warnings beyond cosmetic tolerance.
- [ ] `make arxiv-bundle` produces `ricci_microstructure_arxiv.zip`.
- [ ] Replication section cites commit SHA on `main` where evidence is
      frozen. (Record the SHA in the paper during the final revision
      pass before upload.)
- [ ] ORCID iD attached during arXiv submission.
- [ ] Endorsement secured for `q-fin.TR` (first-time submitters only).

## Why this paper is ready to ship

The evidence body in `research/microstructure/FINDINGS.md` is 471 lines
of orthogonal empirical validation on one Session~1 Binance USDT-M
substrate. Every numeric claim in the manuscript (IC = 0.122, p = 0.002,
block-bootstrap CI [0.029, 0.210], deflated Sharpe 15.1, 5/5 CV folds,
$\beta$ = 1.80, H = 1.01, 45/45 TE, 33/36 CTE, 82 % rolling WF) is
backed by a frozen gate fixture under `results/gate_fixtures/` whose
SHA-256 is pinned in `MANIFEST.sha256`. The `l2-demo-gate.yml` workflow
runs the end-to-end pipeline on every PR that touches the L2 research
surface, so the numbers cannot drift without CI failure.

The honest limitations in Section~7 are not afterthoughts: single
session, simulation P\&L, single asset class, latency assumption, no
execution-topology model, point estimate of $f^{\star}$. Stating them
in the manuscript is a design property, not a concession.

## Open items (do not block arXiv submission)

- Multi-session substrate activation (FINDINGS §10 · U1). Adds one
  robustness paragraph if completed before submission.
- Live-paper execution engine on Binance testnet (FINDINGS §10 · U2).
  Would upgrade Section 5 from simulation to semi-live.
