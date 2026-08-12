from __future__ import annotations

import pytest

from scripts.verify_claim_hashes import claim_lines


def test_duplicate_claim_id_raises() -> None:
    claim_id = "C-AAA"
    text = f"| {claim_id} | x | y | z |\n" f"| {claim_id} | x2 | y2 | z2 |"
    with pytest.raises(ValueError):
        claim_lines(text)
