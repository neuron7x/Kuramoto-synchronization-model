# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Requirement extraction utility for GeoSync.

This script parses a markdown specification (default: ``docs/requirements/product_specification.md``) and
derives a structured backlog. It focuses on Ukrainian key phrases that signal
requirements (``повинно``, ``має``, ``необхідно`` …) and produces:

* ``backlog/requirements.csv`` – canonical backlog for spreadsheet tools.
* ``backlog/requirements.json`` – machine friendly export.
* ``backlog/jira_import.csv`` – ready to import into Jira.
* ``backlog/report.md`` – concise analytical report.

The implementation is intentionally lightweight (pure Python 3.11 standard
library) yet designed for maintainability and future extensibility.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, List, Sequence

LOGGER = logging.getLogger(__name__)


KEYWORDS = (
    "повинно",
    "повинен",
    "повинна",
    "має",
    "мають",
    "необхідно",
    "необхідна",
    "необхідні",
    "призводить",
    "ризик",
)

SECURITY_KEYWORDS = (
    "безпек",
    "шифру",
    "крипт",
    "автентиф",
    "аутентиф",
    "авторизац",
    "вразлив",
    "ата",
    "ризик",
    "інцидент",
    "компрометац",
)

LEGAL_KEYWORDS = (
    "закон",
    "регуля",
    "політик",
    "compliance",
    "відповідн",
    "правов",
    "gdpr",
    "ліценз",
)

NON_FUNCTIONAL_KEYWORDS = (
    "продуктив",
    "швидк",
    "latency",
    "надійн",
    "стабіль",
    "масштаб",
    "доступн",
    "usability",
    "інтерфейс",
    "операцій",
    "підтримк",
    "observability",
    "логув",
    "монітор",
)

UNCERTAIN_TOKENS = (
    "може",
    "ймовірно",
    "потенційно",
    "орієнтовно",
    "планується",
    "tbd",
    "?",
)

CONFLICT_TOKENS = (
    "але",
    "однак",
    "проте",
)

ACCEPTANCE_TOKENS = ("коли", "тоді", "якщо")


@dataclass(slots=True)
class Requirement:
    """Structured representation of a requirement extracted from markdown."""

    identifier: str
    description: str
    category: str
    source_section: str
    source_line: int
    page: int
    priority: str
    acceptance_criteria: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)

    def to_csv_row(self) -> dict[str, str]:
        return {
            "id": self.identifier,
            "category": self.category,
            "description": self.description,
            "source": f"{self.source_section}:{self.source_line}",
            "page": str(self.page),
            "priority": self.priority,
            "dependencies": ", ".join(self.dependencies),
            "acceptance_criteria": " | ".join(self.acceptance_criteria),
            "flags": ", ".join(self.flags),
        }

    def jira_summary(self) -> str:
        return f"{self.identifier}: {self.description[:120]}"

    def jira_description(self) -> str:
        lines = [
            self.description,
            "",
            f"Джерело: {self.source_section}:{self.source_line} (стор. {self.page})",
        ]
        if self.acceptance_criteria:
            lines.append("Критерії приймання:")
            for criterion in self.acceptance_criteria:
                lines.append(f"- {criterion}")
        if self.flags:
            lines.append("Позначки:")
            for flag in self.flags:
                lines.append(f"- {flag}")
        # Jira CSV import does not tolerate literal newlines inside fields. Convert them
        # to escaped sequences so that each requirement stays on a single row.
        return "\\n".join(lines)


@dataclass
class ExtractionResult:
    requirements: List[Requirement]
    duplicates: dict[str, list[str]]
    gaps: List[str]
    source_path: Path


class RequirementExtractor:
    """Parse markdown documents and build requirement objects."""

    def __init__(self, markdown_path: Path, output_dir: Path) -> None:
        self.markdown_path = markdown_path
        self.output_dir = output_dir

    def run(self) -> ExtractionResult:
        if not self.markdown_path.exists():
            LOGGER.warning("Markdown specification not found: %s", self.markdown_path)
            return ExtractionResult(
                [],
                {},
                [f"Відсутній файл {self.markdown_path.name}"],
                self.markdown_path,
            )

        text = self.markdown_path.read_text(encoding="utf-8")
        lines = text.splitlines()
        section_by_line = self._build_section_index(lines)
        paragraphs = list(self._iter_paragraphs(lines))
        requirements: list[Requirement] = []

        counters = {"REQ": 0, "SEC": 0, "NFR": 0}
        normalized_index: dict[str, list[str]] = defaultdict(list)
        gaps: list[str] = []

        for paragraph, start_line in paragraphs:
            if not self._contains_keyword(paragraph):
                continue

            section = section_by_line.get(start_line, "Без розділу")
            sentences = self._split_sentences(paragraph)
            matches = [s for s in sentences if self._contains_keyword(s)]
            if not matches:
                matches = [paragraph.strip()]

            for sentence in matches:
                category = self._classify(sentence)
                identifier = self._allocate_id(category, counters)
                priority = self._infer_priority(sentence)
                acceptance = self._extract_acceptance(sentence)
                flags = self._detect_flags(sentence)
                page = self._line_to_page(start_line)

                requirement = Requirement(
                    identifier=identifier,
                    description=self._clean_text(sentence),
                    category=category,
                    source_section=section,
                    source_line=start_line,
                    page=page,
                    priority=priority,
                    acceptance_criteria=acceptance,
                    flags=flags,
                )

                normalized = self._normalize_text(requirement.description)
                normalized_index[normalized].append(requirement.identifier)

                requirements.append(requirement)

        if not requirements:
            gaps.append("У документі не знайдено жодної фрази з ключовими словами")

        duplicates = {text: ids for text, ids in normalized_index.items() if len(ids) > 1}
        for ids in duplicates.values():
            for req in requirements:
                if req.identifier in ids and "дублікат" not in req.flags:
                    req.flags.append("дублікат")

        return ExtractionResult(requirements, duplicates, gaps, self.markdown_path)

    @staticmethod
    def _build_section_index(lines: Sequence[str]) -> dict[int, str]:
        section_by_line: dict[int, str] = {}
        current_section = "Головний документ"
        for idx, line in enumerate(lines, start=1):
            if line.strip().startswith("#"):
                heading = line.lstrip("# ").strip() or "Без назви"
                current_section = heading
            section_by_line[idx] = current_section
        return section_by_line

    @staticmethod
    def _iter_paragraphs(lines: Sequence[str]) -> Iterator[tuple[str, int]]:
        buffer: list[str] = []
        start_line = 1
        for idx, line in enumerate(lines, start=1):
            if line.strip():
                if not buffer:
                    start_line = idx
                buffer.append(line.rstrip())
            elif buffer:
                yield (" ".join(buffer).strip(), start_line)
                buffer.clear()
        if buffer:
            yield (" ".join(buffer).strip(), start_line)

    @staticmethod
    def _contains_keyword(text: str) -> bool:
        lowered = text.lower()
        return any(keyword in lowered for keyword in KEYWORDS)

    @staticmethod
    def _split_sentences(paragraph: str) -> list[str]:
        raw_sentences = re.split(r"(?<=[.!?])\s+", paragraph.strip())
        return [sentence.strip() for sentence in raw_sentences if sentence.strip()]

    @staticmethod
    def _clean_text(text: str) -> str:
        return re.sub(r"\s+", " ", text.strip())

    @staticmethod
    def _normalize_text(text: str) -> str:
        return re.sub(r"[^a-zа-я0-9]+", "", text.lower())

    @staticmethod
    def _line_to_page(line_number: int, lines_per_page: int = 40) -> int:
        return max(1, (line_number - 1) // lines_per_page + 1)

    def _classify(self, text: str) -> str:
        lowered = text.lower()
        if any(token in lowered for token in SECURITY_KEYWORDS):
            return "security"
        if any(token in lowered for token in LEGAL_KEYWORDS):
            return "legal"
        if any(token in lowered for token in NON_FUNCTIONAL_KEYWORDS):
            return "non-functional"
        return "functional"

    @staticmethod
    def _allocate_id(category: str, counters: dict[str, int]) -> str:
        if category == "security":
            prefix = "SEC"
        elif category == "functional":
            prefix = "REQ"
        else:
            prefix = "NFR"
        counters[prefix] += 1
        return f"{prefix}-{counters[prefix]:03d}"

    @staticmethod
    def _infer_priority(text: str) -> str:
        lowered = text.lower()
        if any(token in lowered for token in ("необхід", "обов'", "критич", "повин")):
            return "Must"
        if "має" in lowered or "мають" in lowered:
            return "Should"
        if "призводить" in lowered or "ризик" in lowered:
            return "Must"
        return "Could"

    @staticmethod
    def _extract_acceptance(text: str) -> list[str]:
        lowered = text.lower()
        if any(token in lowered for token in ACCEPTANCE_TOKENS):
            return [RequirementExtractor._clean_text(text)]
        return []

    @staticmethod
    def _detect_flags(text: str) -> list[str]:
        lowered = text.lower()
        flags: list[str] = []
        if any(token in lowered for token in UNCERTAIN_TOKENS):
            flags.append("невизначеність")
        if any(token in lowered for token in CONFLICT_TOKENS):
            flags.append("суперечність")
        return flags


def write_csv(path: Path, rows: Iterable[dict[str, str]], headers: Sequence[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def build_jira_rows(requirements: Sequence[Requirement]) -> list[dict[str, str]]:
    priority_map = {"Must": "Highest", "Should": "High", "Could": "Medium"}
    jira_rows = []
    for req in requirements:
        issue_type = "Security" if req.category == "security" else "Story"
        labels = ["requirement", req.category.replace("-", "_")]
        jira_rows.append(
            {
                "Summary": req.jira_summary(),
                "Description": req.jira_description(),
                "Issue Type": issue_type,
                "Priority": priority_map.get(req.priority, "Medium"),
                "Labels": ",".join(labels),
                "Custom field (Requirement ID)": req.identifier,
            }
        )
    return jira_rows


def render_report(path: Path, result: ExtractionResult) -> None:
    requirements = result.requirements
    total = len(requirements)
    by_category = Counter(req.category for req in requirements)
    by_priority = Counter(req.priority for req in requirements)
    flagged = [req for req in requirements if req.flags]

    page_map: dict[int, list[str]] = defaultdict(list)
    for req in requirements:
        page_map[req.page].append(req.identifier)

    lines = ["# Аналітичний звіт", ""]
    lines.append(f"**Файл-джерело:** {result.source_path}")
    lines.append(f"**Кількість вимог:** {total}")
    lines.append("")

    if by_category:
        lines.append("## Розподіл за категоріями")
        for category, count in sorted(by_category.items()):
            lines.append(f"- {category}: {count}")
        lines.append("")

    if by_priority:
        lines.append("## Розподіл за пріоритетами (MoSCoW)")
        for priority, count in sorted(by_priority.items()):
            lines.append(f"- {priority}: {count}")
        lines.append("")

    if flagged:
        lines.append("## Позначені невизначені або суперечливі вимоги")
        for req in flagged:
            joined_flags = ", ".join(req.flags)
            lines.append(f"- {req.identifier} ({joined_flags}): {req.description}")
        lines.append("")

    if result.duplicates:
        lines.append("## Виявлені дублікати")
        for normalized, ids in result.duplicates.items():
            lines.append(f"- {', '.join(ids)}")
        lines.append("")

    if result.gaps:
        lines.append("## Прогалини")
        for gap in result.gaps:
            lines.append(f"- {gap}")
        lines.append("")

    lines.append("## Мапа на сторінки")
    if page_map:
        for page, reqs in sorted(page_map.items()):
            lines.append(f"- Сторінка {page}: {', '.join(reqs)}")
    else:
        lines.append("- Дані відсутні")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def ensure_output_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Виділення вимог із product specification")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("docs/requirements/product_specification.md"),
        help="Шлях до markdown-файлу зі специфікацією (default: docs/requirements/product_specification.md)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("backlog"),
        help="Каталог для збереження результатів (default: backlog)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Увімкнути детальний логінг",
    )
    return parser.parse_args(argv)


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    configure_logging(args.verbose)

    extractor = RequirementExtractor(args.input, args.output_dir)
    result = extractor.run()

    ensure_output_dir(args.output_dir)

    requirements = result.requirements
    csv_path = args.output_dir / "requirements.csv"
    json_path = args.output_dir / "requirements.json"
    jira_path = args.output_dir / "jira_import.csv"
    report_path = args.output_dir / "report.md"

    csv_headers = [
        "id",
        "category",
        "description",
        "source",
        "page",
        "priority",
        "dependencies",
        "acceptance_criteria",
        "flags",
    ]
    write_csv(csv_path, (req.to_csv_row() for req in requirements), csv_headers)
    write_json(
        json_path,
        [
            {
                "id": req.identifier,
                "description": req.description,
                "category": req.category,
                "source": {
                    "section": req.source_section,
                    "line": req.source_line,
                    "page": req.page,
                },
                "priority": req.priority,
                "dependencies": req.dependencies,
                "acceptance_criteria": req.acceptance_criteria,
                "flags": req.flags,
            }
            for req in requirements
        ],
    )

    jira_headers = [
        "Summary",
        "Description",
        "Issue Type",
        "Priority",
        "Labels",
        "Custom field (Requirement ID)",
    ]
    write_csv(jira_path, build_jira_rows(requirements), jira_headers)

    render_report(report_path, result)

    LOGGER.info("Збережено %d вимог", len(requirements))


if __name__ == "__main__":
    main()
