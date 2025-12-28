from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Sequence

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "docs" / "responsible_ai_program.md"
OUTPUT_DIR = ROOT / "stakeholders"
SAFE_PATH_RE = re.compile(r"[A-Za-z0-9_./-]+")


@dataclass
class SourceRef:
    pattern: str
    description: str


@dataclass
class StakeholderEntry:
    name: str
    role: str
    interests: str
    influence: int
    expectations: str
    channels: str
    frequency: str
    power: str
    interest_level: int
    sources: Sequence[SourceRef] = field(default_factory=list)


@dataclass
class CommunicationEntry:
    audience: str
    format: str
    frequency: str
    initiator: str
    goal: str
    sources: Sequence[SourceRef] = field(default_factory=list)


RACI_ROLES = [
    "Responsible AI Council",
    "Risk Management Team",
    "Product Governance",
    "MLOps & Platform Team",
    "Security Team",
    "Legal Counsel",
    "Data Governance & Privacy",
    "Customer Support Service",
    "Regulators",
]


RACI_MATRIX = {
    "Development": {
        "Responsible AI Council": "A",
        "Risk Management Team": "C",
        "Product Governance": "C",
        "MLOps & Platform Team": "R",
        "Security Team": "I",
        "Legal Counsel": "I",
        "Data Governance & Privacy": "C",
        "Customer Support Service": "I",
        "Regulators": "I",
    },
    "Testing": {
        "Responsible AI Council": "A",
        "Risk Management Team": "C",
        "Product Governance": "I",
        "MLOps & Platform Team": "C",
        "Security Team": "C",
        "Legal Counsel": "I",
        "Data Governance & Privacy": "R",
        "Customer Support Service": "I",
        "Regulators": "I",
    },
    "Deployment": {
        "Responsible AI Council": "A",
        "Risk Management Team": "C",
        "Product Governance": "R",
        "MLOps & Platform Team": "C",
        "Security Team": "C",
        "Legal Counsel": "I",
        "Data Governance & Privacy": "I",
        "Customer Support Service": "C",
        "Regulators": "I",
    },
    "Security": {
        "Responsible AI Council": "A",
        "Risk Management Team": "C",
        "Product Governance": "I",
        "MLOps & Platform Team": "C",
        "Security Team": "R",
        "Legal Counsel": "C",
        "Data Governance & Privacy": "C",
        "Customer Support Service": "I",
        "Regulators": "I",
    },
    "Legal": {
        "Responsible AI Council": "A",
        "Risk Management Team": "I",
        "Product Governance": "I",
        "MLOps & Platform Team": "I",
        "Security Team": "C",
        "Legal Counsel": "R",
        "Data Governance & Privacy": "C",
        "Customer Support Service": "I",
        "Regulators": "C",
    },
}

COMMUNICATION_PLAN = [
    CommunicationEntry(
        audience="Responsible AI Council",
        format="Кік-оф воркшоп (засідання ради)",
        frequency="Тижні 1–2 згідно дорожньої карти",
        initiator="Responsible AI Council",
        goal="Затвердити мандат і призначити власників потоків",
        sources=[
            SourceRef("Затвердити мандат", "mandate"),
            SourceRef("| 1–2   |", "roadmap weeks 1-2"),
        ],
    ),
    CommunicationEntry(
        audience="Risk & Compliance Teams",
        format="Ризик-рев'ю (воркшоп + дашборд демо)",
        frequency="Тижні 3–4",
        initiator="Product Governance",
        goal="Представити карту ризиків та контрольні точки",
        sources=[
            SourceRef("мапу ризиків", "risk map"),
            SourceRef("| 3–4   |", "roadmap weeks 3-4"),
        ],
    ),
    CommunicationEntry(
        audience="Data Governance & Customer Support",
        format="Демо результатів тестів упередженості й explainability",
        frequency="Тижні 5–6",
        initiator="Data Governance & Privacy",
        goal="Узгодити політики даних і шаблони пояснень перед запуском каналів апеляцій",
        sources=[
            SourceRef("Затвердити політики збору", "data policies"),
            SourceRef("Розробити шаблони пояснень", "explainability templates"),
            SourceRef("| 5–6   |", "roadmap weeks 5-6"),
        ],
    ),
    CommunicationEntry(
        audience="Security & Legal (Red Team Collective)",
        format="Комбінований стендап + red team бріфінг",
        frequency="Тижні 7–8",
        initiator="Security Team",
        goal="Скоординувати запуск апеляцій, red team сценарії та юридичні рев'ю",
        sources=[
            SourceRef("Механізми апеляцій", "appeals"),
            SourceRef("red team", "red team"),
            SourceRef("Юридичні та нормативні рев’ю", "legal reviews section"),
            SourceRef("| 7–8   |", "roadmap weeks 7-8"),
        ],
    ),
    CommunicationEntry(
        audience="Executive Leadership & Regulators",
        format="Щоквартальний прозорий звіт (лист + дашборд демо)",
        frequency="Тижні 9–10 та щоквартально",
        initiator="Responsible AI Council",
        goal="Надати аудит відповідності й KPI програми перед зовнішніми звітами",
        sources=[
            SourceRef("Відповідність стандартам та аудит", "compliance"),
            SourceRef("Прозорі звіти та комунікація", "transparency"),
            SourceRef("| 9–10  |", "roadmap weeks 9-10"),
        ],
    ),
    CommunicationEntry(
        audience="All Stakeholders",
        format="Ретроспектива програми (стратегічна сесія)",
        frequency="Тижні 11–12",
        initiator="Responsible AI Council",
        goal="Зафіксувати уроки, оновити політики й roadmap розвитку",
        sources=[
            SourceRef("ретроспективи ради Responsible AI", "continuous improvement"),
            SourceRef("| 11–12 |", "roadmap weeks 11-12"),
        ],
    ),
]


def load_source_lines(path: Path) -> List[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _validate_repo_path(
    value: str,
    *,
    must_exist: bool,
    expect_file: bool,
    allowed_suffixes: tuple[str, ...] | None = None,
) -> Path:
    if not SAFE_PATH_RE.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "Paths may only contain letters, numbers, and ./_- characters."
        )
    path = Path(value).expanduser().resolve()
    try:
        path.relative_to(ROOT)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Path must be inside repository root ({ROOT})."
        ) from exc
    if must_exist and not path.exists():
        raise argparse.ArgumentTypeError(f"Path does not exist: {path}")
    if expect_file and path.exists() and not path.is_file():
        raise argparse.ArgumentTypeError(f"Expected file path, got: {path}")
    if not expect_file and path.exists() and not path.is_dir():
        raise argparse.ArgumentTypeError(f"Expected directory path, got: {path}")
    if allowed_suffixes and path.suffix.lower() not in allowed_suffixes:
        raise argparse.ArgumentTypeError(
            f"Expected file suffix in {allowed_suffixes}, got {path.suffix or '<none>'}."
        )
    return path


def _validate_source_path(value: str) -> Path:
    return _validate_repo_path(
        value,
        must_exist=True,
        expect_file=True,
        allowed_suffixes=(".md",),
    )


def _validate_output_dir(value: str) -> Path:
    return _validate_repo_path(value, must_exist=False, expect_file=False)


def _validate_manifest_path(value: str) -> Path:
    return _validate_repo_path(
        value,
        must_exist=False,
        expect_file=True,
        allowed_suffixes=(".json",),
    )


def build_section_index(lines: Sequence[str]) -> List[str]:
    section_labels: List[str] = [""] * len(lines)
    current = ""
    for idx, raw in enumerate(lines):
        stripped = raw.lstrip()
        if stripped.startswith("###"):
            current = stripped.strip("# ")
        elif stripped.startswith("##"):
            current = stripped.strip("# ")
        section_labels[idx] = current
    return section_labels


def find_line_numbers(lines: Sequence[str], pattern: str) -> Iterable[int]:
    for idx, line in enumerate(lines, start=1):
        if pattern in line:
            yield idx


def format_sources(
    lines: Sequence[str],
    sections: Sequence[str],
    refs: Sequence[SourceRef],
) -> str:
    parts: List[str] = []
    for ref in refs:
        matches = list(find_line_numbers(lines, ref.pattern))
        if not matches:
            raise ValueError(f"Pattern '{ref.pattern}' not found for {ref.description}")
        for line_no in matches:
            section = sections[line_no - 1] or ""
            parts.append(f"{section}:{line_no}")
    unique_parts = []
    seen = set()
    for part in parts:
        if part not in seen:
            unique_parts.append(part)
            seen.add(part)
    return ";".join(unique_parts)


def write_matrix(
    entries: Sequence[StakeholderEntry],
    source_lines: Sequence[str],
    section_index: Sequence[str],
    path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "stakeholder",
        "role",
        "interests",
        "influence",
        "expectations",
        "channels",
        "frequency",
        "source",
        "power",
        "interest",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for entry in entries:
            source_str = format_sources(source_lines, section_index, entry.sources)
            writer.writerow(
                {
                    "stakeholder": entry.name,
                    "role": entry.role,
                    "interests": entry.interests,
                    "influence": entry.influence,
                    "expectations": entry.expectations,
                    "channels": entry.channels,
                    "frequency": entry.frequency,
                    "source": source_str,
                    "power": entry.power,
                    "interest": entry.interest_level,
                }
            )


def write_raci(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["work"] + RACI_ROLES)
        for work, assignments in RACI_MATRIX.items():
            row = [work]
            for role in RACI_ROLES:
                row.append(assignments.get(role, ""))
            writer.writerow(row)


def write_communication_plan(
    entries: Sequence[CommunicationEntry],
    source_lines: Sequence[str],
    section_index: Sequence[str],
    path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "audience",
        "format",
        "frequency",
        "initiator",
        "goal",
        "source",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for entry in entries:
            source_str = format_sources(source_lines, section_index, entry.sources)
            writer.writerow(
                {
                    "audience": entry.audience,
                    "format": entry.format,
                    "frequency": entry.frequency,
                    "initiator": entry.initiator,
                    "goal": entry.goal,
                    "source": source_str,
                }
            )


def compute_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def describe_repo_state(root: Path) -> dict[str, str]:
    try:
        rev = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip()
    except Exception:
        rev = "unknown"
    return {"git_rev": rev}


def dump_manifest(
    manifest_path: Path, files: Sequence[Path], extras: dict[str, str]
) -> None:
    records = []
    for file_path in files:
        records.append(
            {
                "path": str(file_path.relative_to(ROOT)),
                "sha256": compute_sha256(file_path),
            }
        )
    payload = {"artifacts": records, **extras}
    manifest_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def build_entries() -> List[StakeholderEntry]:
    return [
        StakeholderEntry(
            name="Responsible AI Council",
            role=(
                "Крос-функціональний орган нагляду, що представляє ризик-менеджмент, продукт, платформу, безпеку, юристів та "
                "незалежну етику"
            ),
            interests="Єдине керування програмою, відповідність регуляторним вимогам і аудитам",
            influence=5,
            expectations="Затверджувати мандат, процедури ескалації та призначати власників робочих потоків",
            channels="Засідання ради, протоколи, ескалаційні процедури",
            frequency="Частота засідань, визначена мандатом",
            power="High",
            interest_level=5,
            sources=[
                SourceRef("Створити Раду з відповідального ШІ", "council formation"),
                SourceRef("Затвердити мандат", "mandate"),
                SourceRef("Назначити власників робочих потоків", "workstream owners"),
                SourceRef(
                    "ретроспективи ради Responsible AI", "continuous improvement"
                ),
            ],
        ),
        StakeholderEntry(
            name="Risk & Compliance Teams",
            role="Функції ризику та комплаєнсу, що координують інвентаризацію ризиків і отримують прозорі звіти",
            interests="Карта ризиків, контроль небезпек і своєчасні оновлення комплаєнсу",
            influence=4,
            expectations="Будувати карту ризиків, брати участь у порталі звітності та інтеграції результатів",
            channels="Risk-дашборди, централізований портал, інцидентні ескалації",
            frequency="Щоквартальні звіти та регулярні оновлення карти ризиків",
            power="Medium",
            interest_level=5,
            sources=[
                SourceRef("ризик-", "council representation"),
                SourceRef("мапу ризиків", "risk map"),
                SourceRef("compliance, risk, executive", "transparency portal"),
            ],
        ),
        StakeholderEntry(
            name="Product Governance",
            role="Продуктові лідери та борд, які узгоджують roadmap і впроваджують gate review",
            interests="Відповідність продукту політикам та інтеграція уроків у розвиток",
            influence=4,
            expectations="Синхронізувати roadmap із картами ризиків і правовими рев’ю, додати gate review",
            channels="Product governance сесії, roadmap оновлення",
            frequency="Відповідно до дорожньої карти (цикли 1–12 тижнів)",
            power="High",
            interest_level=4,
            sources=[
                SourceRef("продукту, платформи", "council composition"),
                SourceRef("Product governance", "integration with processes"),
                SourceRef("план розвитку продукту", "continuous improvement"),
            ],
        ),
        StakeholderEntry(
            name="MLOps & Platform Team",
            role="Команди MLOps та платформи, що впроваджують перевірки в CI/CD та підтримують пайплайни",
            interests="Інтеграція перевірок упередженості, приватності та explainability у пайплайни",
            influence=4,
            expectations="Додати стадії перевірок до CI/CD, підтримувати реєстр активів та артефактів",
            channels="CI/CD пайплайни, інвентаризаційні реєстри",
            frequency="Безперервно з контрольними точками згідно дорожньої карти",
            power="High",
            interest_level=5,
            sources=[
                SourceRef("платформи", "council composition"),
                SourceRef("Провести інвентаризацію моделей", "catalogue"),
                SourceRef("MLOps пайплайни", "integration"),
            ],
        ),
        StakeholderEntry(
            name="Security Team",
            role="Функція безпеки, що очолює red team і контролює безпекові вимоги",
            interests="Запобігання атакам, контроль небезпек та відповідність регуляціям",
            influence=4,
            expectations="Брати участь у red team, впроваджувати технічні обмеження і моніторинг",
            channels="Red team вправи, інцидентні playbooks, дашборди",
            frequency="Щонайменше щоквартальні red team вправи та постійний моніторинг",
            power="High",
            interest_level=5,
            sources=[
                SourceRef("безпеки", "council composition"),
                SourceRef("red team", "red team"),
                SourceRef("контроль за ланцюжками викликів", "domain limits"),
            ],
        ),
        StakeholderEntry(
            name="Legal Counsel",
            role="Юридичний напрям, що забезпечує правові рев’ю та комунікацію з регуляторами",
            interests="Юридична відповідність продуктів і даних",
            influence=4,
            expectations="Проводити правові перегляди, вести реєстр рішень та узгоджувати комунікації",
            channels="Юридичні рев’ю, реєстри рішень, регуляторні канали",
            frequency="Регулярні правові перегляди та DPIA перед запуском високоризикових функцій",
            power="High",
            interest_level=4,
            sources=[
                SourceRef("юристів", "council composition"),
                SourceRef("правові перегляди", "legal reviews"),
                SourceRef(
                    "Узгодити процес комунікації з регуляторами", "regulator comms"
                ),
            ],
        ),
        StakeholderEntry(
            name="Independent Ethics Expert",
            role="Незалежний етичний радник у складі ради",
            interests="Етичність політик, прозорість та справедливість",
            influence=3,
            expectations="Оцінювати політики та брати участь у ретроспективах",
            channels="Засідання ради, етичні рев’ю",
            frequency="За графіком ради",
            power="Medium",
            interest_level=4,
            sources=[SourceRef("незалежного етичного експерта", "council composition")],
        ),
        StakeholderEntry(
            name="Data Governance & Privacy",
            role="Команда, що визначає та впроваджує політики даних, приватності й мінімізації",
            interests="Захист даних, контроль доступу та оцінка постачальників",
            influence=4,
            expectations="Затвердити політики, класифікувати дані та оцінити сторонніх постачальників",
            channels="Каталог даних, політики доступу, оцінки постачальників",
            frequency="Постійний контроль із пріоритетними хвилями на тижнях 5–6",
            power="High",
            interest_level=5,
            sources=[
                SourceRef("Затвердити політики збору", "data policies"),
                SourceRef("Визначити категорії даних", "data classification"),
                SourceRef("Оцінити постачальників", "vendors"),
            ],
        ),
        StakeholderEntry(
            name="Customer Support Service",
            role="Служба підтримки, що обробляє апеляції та канали звернення",
            interests="Прозорі процеси апеляцій і якісні пояснення для клієнтів",
            influence=3,
            expectations="Утримувати канали звернення, виконувати SLA та підтримувати пояснення",
            channels="Портал, API та служба підтримки для апеляцій",
            frequency="Відповідно до SLA апеляцій та постійних каналів",
            power="Medium",
            interest_level=5,
            sources=[
                SourceRef("служба підтримки", "user appeals"),
                SourceRef("Визначити SLA", "appeals SLA"),
                SourceRef("Розробити шаблони пояснень", "explainability templates"),
            ],
        ),
        StakeholderEntry(
            name="Clients (Internal & External)",
            role="Внутрішні та зовнішні клієнти, кінцева аудиторія продукту і звітів",
            interests="Справедливі, прозорі та захищені рішення",
            influence=3,
            expectations="Отримувати пояснення, звіти та можливість апеляції",
            channels="Портал, API, публічні картки моделей, прозорі звіти",
            frequency="Щоквартальні звіти та за потреби через апеляції",
            power="Low",
            interest_level=5,
            sources=[
                SourceRef("внутрішній/зовнішній клієнт", "usage contexts"),
                SourceRef(
                    "клієнт, служба підтримки, регулятор", "explainability audiences"
                ),
                SourceRef("Публікувати щоквартальні звіти", "transparency reports"),
            ],
        ),
        StakeholderEntry(
            name="Regulators",
            role="Регуляторні органи, для яких готуються комунікації та звіти",
            interests="Дотримання норм і наявність аудиторських артефактів",
            influence=5,
            expectations="Отримувати узгоджені комунікації, шаблони відповідей і повні звіти",
            channels="Регуляторні комунікації, аудиторські звіти",
            frequency="Регулярні правові рев’ю та за вимогою регулятора",
            power="High",
            interest_level=4,
            sources=[
                SourceRef("регулятор", "explainability audiences"),
                SourceRef("комунікації з регуляторами", "regulator comms"),
                SourceRef("аудиторські артефакти", "audit storage"),
            ],
        ),
        StakeholderEntry(
            name="Executive Leadership",
            role="Виконавче керівництво, що отримує звіти про стан програми",
            interests="Зменшення операційних ризиків та прозорість",
            influence=5,
            expectations="Огляд щоквартальних звітів і затвердження roadmap розвитку",
            channels="Централізований портал, прозорі дашборди, roadmap рев’ю",
            frequency="Щоквартальні звіти та підсумкові огляди",
            power="High",
            interest_level=4,
            sources=[
                SourceRef("executive", "transparency portal"),
                SourceRef("Затверджений roadmap розвитку програми", "roadmap approval"),
                SourceRef("Підвищення довіри клієнтів", "benefits"),
            ],
        ),
        StakeholderEntry(
            name="SRE & Incident Management",
            role="Команди SRE, що інтегрують метрики відповідального ШІ в дашборди та пост-мортеми",
            interests="Стабільність сервісів та швидке виявлення інцидентів",
            influence=4,
            expectations="Включити метрики в центральні дашборди та процеси post-mortem",
            channels="SRE дашборди, інцидент-менеджмент",
            frequency="Постійний моніторинг та післяінцидентні ретроспективи",
            power="Medium",
            interest_level=5,
            sources=[
                SourceRef("SRE та інцидент-менеджмент", "integration with processes"),
                SourceRef("Швидше виявлення і усунення", "benefits"),
            ],
        ),
        StakeholderEntry(
            name="Data Science & Analytics",
            role="Data science команда, що бере участь у red team та аналізі упереджень",
            interests="Якість моделей, справедливість та контроль показників",
            influence=4,
            expectations="Участь у red team, розробці метрик упередженості та аналізі уроків",
            channels="Red team вправи, метрики упередженості, ретроспективи",
            frequency="Щонайменше щоквартальні red team вправи та регулярні метрики",
            power="Medium",
            interest_level=5,
            sources=[
                SourceRef("data science", "red team"),
                SourceRef("Побудувати метрики упереджень", "bias metrics"),
            ],
        ),
        StakeholderEntry(
            name="Training & Enablement",
            role="Команди навчання, що розробляють тренінги для інженерів, дата-сайентістів і операторів",
            interests="Підготовка персоналу до політик та інструментів програми",
            influence=3,
            expectations="Розробити тренінги й забезпечити охоплення ролей",
            channels="Програми навчання, семінари",
            frequency="За планом навчання під час інтеграції процесів",
            power="Medium",
            interest_level=4,
            sources=[SourceRef("Навчання персоналу", "integration with processes")],
        ),
        StakeholderEntry(
            name="Third-Party Data Providers",
            role="Постачальники та сторонні набори даних, що мають відповідати політикам",
            interests="Збереження партнерства та відповідність вимогам",
            influence=3,
            expectations="Проходити оцінку відповідності політикам та підтримувати якість даних",
            channels="Оцінки постачальників, договірні рев’ю",
            frequency="Під час оцінок постачальників та онбордингу",
            power="Medium",
            interest_level=3,
            sources=[SourceRef("сторонні набори даних", "vendors")],
        ),
        StakeholderEntry(
            name="Red Team Collective",
            role="Міждисциплінарна red team (безпека, data science, продукт, юридичний відділ)",
            interests="Виявлення вразливостей і підтвердження стійкості",
            influence=4,
            expectations="Розробляти сценарії атак, проводити щоквартальні випробування та інтегрувати результати",
            channels="Red team сценарії, звіти про знахідки",
            frequency="Щоквартальні симульовані атаки",
            power="Medium",
            interest_level=5,
            sources=[
                SourceRef("red team", "red team"),
                SourceRef(
                    "симульовані атаки щонайменше щоквартально", "red team cadence"
                ),
            ],
        ),
        StakeholderEntry(
            name="TBD: Data Protection Officer",
            role="Потенційний DPO для координації DPIA та взаємодії з регуляторами",
            interests="Централізоване управління DPIA та запитами регуляторів",
            influence=4,
            expectations="Уточнити, хто відповідає за DPIA та підписання регуляторних відповідей",
            channels="Регуляторні канали, DPIA процес",
            frequency="Перед запуском високоризикових функцій",
            power="High",
            interest_level=4,
            sources=[
                SourceRef("оцінки впливу на захист даних", "DPIA"),
                SourceRef("комунікації з регуляторами", "regulator comms"),
            ],
        ),
        StakeholderEntry(
            name="TBD: Model Owners in Business Units",
            role="Гіпотетичні власники моделей у бізнес-підрозділах, яких треба ідентифікувати",
            interests="Використання моделей у бізнес-процесах та відповідність обмеженням",
            influence=3,
            expectations="Уточнити власників моделей для підписання політик та відповідальності",
            channels="Каталог моделей, gate review",
            frequency="Згідно roadmap запусків (щотижневі хвилі)",
            power="Medium",
            interest_level=5,
            sources=[
                SourceRef(
                    "Задокументувати зв’язок між продуктами й моделями", "catalogue"
                ),
                SourceRef(
                    "gate review перед запуском критичних функцій", "product governance"
                ),
            ],
        ),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate stakeholder matrix and RACI from RLHF/RLAIF strategy doc"
    )
    parser.add_argument(
        "--source",
        type=_validate_source_path,
        default=DEFAULT_SOURCE,
        help="Path to the RLHF/RLAIF strategy markdown file",
    )
    parser.add_argument(
        "--output-dir",
        type=_validate_output_dir,
        default=OUTPUT_DIR,
        help="Directory to store generated CSV artifacts",
    )
    parser.add_argument(
        "--manifest",
        type=_validate_manifest_path,
        default=OUTPUT_DIR / "manifest.json",
        help="Path to write manifest with checksums",
    )
    args = parser.parse_args()

    source_path = _validate_source_path(str(args.source))
    output_dir = _validate_output_dir(str(args.output_dir))
    manifest_path = _validate_manifest_path(str(args.manifest))

    lines = load_source_lines(source_path)
    section_index = build_section_index(lines)

    entries = build_entries()
    matrix_path = output_dir / "matrix.csv"
    raci_path = output_dir / "raci.csv"
    comm_plan_path = output_dir / "communication_plan.csv"

    write_matrix(entries, lines, section_index, matrix_path)
    write_raci(raci_path)
    write_communication_plan(COMMUNICATION_PLAN, lines, section_index, comm_plan_path)

    extras = describe_repo_state(ROOT)
    extras["source_sha256"] = compute_sha256(source_path)
    dump_manifest(
        manifest_path, [matrix_path, raci_path, comm_plan_path, source_path], extras
    )

    print(f"Generated {matrix_path.relative_to(ROOT)}")
    print(f"Generated {raci_path.relative_to(ROOT)}")
    print(f"Generated {comm_plan_path.relative_to(ROOT)}")
    print(f"Manifest written to {manifest_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
