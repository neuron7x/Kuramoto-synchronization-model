# Citation Policy

## When to cite
- Any scientific or safety-critical claim (neuroscience, thermodynamics, RL, security standards) **must** include at least one primary or authoritative source.
- If no suitable source is available, explicitly label the statement as `[heuristic]`.
- Production guides and runbooks referencing external standards (e.g., NIST, ISO) must cite the standard.

## Preferred sources
- Peer-reviewed papers, official standards (NIST/ISO), books from reputable publishers, and official vendor documentation.
- Avoid blog posts or unverifiable sources. Use arXiv only when no peer-reviewed version exists.

## Markdown citation format
- Inline citations use the Pandoc style: `[@SuttonBarto2018RL]` (swap in the relevant BibTeX key).
- Multiple citations are separated by semicolons: `[@JacobsAzmitia1992Serotonin; @BendaHerz2003Adaptation]`.
- Add a short “Evidence:” line when clarifying the support for a claim (e.g., `Evidence: [@SuttonBarto2018RL]`).

## Adding a new reference
1. Add a BibTeX entry to `docs/REFERENCES.bib` using the key format `AuthorYearShortTitle`.
2. Ensure required fields exist: `title`, `author`, `year`, and at least one of `doi` / `isbn` / `url`.
3. Add a mapping row to `docs/CITATION_MAP.md` with Claim ID, statement, location, code mapping, and citations.
4. Update `docs/BIBLIOGRAPHY.md` with a one-line summary and mapped Claim ID.

## Claim IDs
- Use stable prefixes: `NC` (neuro-control), `TH` (thermodynamics), `CM` (crisis management), `OBS` (observability), `BT` (backtesting), `SEC` (security).
- Claim IDs must be unique and referenced from both `CITATION_MAP.md` and `BIBLIOGRAPHY.md`.

## Lint and CI
- Run `python scripts/lint_bibliography.py` locally before opening a PR.
- The CI job `bibliography-lint` enforces:
  - Valid `REFERENCES.bib`
  - All inline citations resolve to keys present in `REFERENCES.bib`
  - Claim IDs and mappings are complete
  - No duplicate DOI/ISBN entries
