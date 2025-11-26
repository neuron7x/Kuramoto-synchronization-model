import pathlib

import pytest


@pytest.fixture()
def requirements_path() -> pathlib.Path:
    return (
        pathlib.Path(__file__).resolve().parents[2]
        / "docs"
        / "agent_integration"
        / "agent_trading_requirements.md"
    )


def test_requirements_document_exists(requirements_path: pathlib.Path) -> None:
    assert (
        requirements_path.is_file()
    ), "Trading agent requirements document is missing."


@pytest.mark.parametrize(
    "heading",
    [
        "## 1. System Requirements Analysis",
        "## 2. Historical Data Preparation",
        "## 3. APIs and Simulation Environment",
        "## 4. Action Space Definition",
        "## 5. State Space Representation",
        "## 6. Framework and Environment Research",
        "## 7. Project Tooling Preparation",
        "## 8. Data Collection Strategy",
        "## 9. Evaluation Metrics",
        "## 10. System Performance & Responsiveness Requirements",
        "## 11. Next Steps",
    ],
)
def test_requirements_document_contains_sections(
    requirements_path: pathlib.Path, heading: str
) -> None:
    content = requirements_path.read_text(encoding="utf-8")
    assert (
        heading in content
    ), f"Heading '{heading}' missing from requirements document."
