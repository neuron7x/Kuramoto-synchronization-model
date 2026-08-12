from __future__ import annotations

import argparse
import json


def finalize(text: str) -> dict[str, str]:
    cleaned = " ".join(text.split())
    return {
        "intent": cleaned[:240],
        "constraint": "bounded practical output",
        "blocker": "missing external evidence" if not cleaned else "none declared",
        "next_action": "convert intent into an inspectable artifact",
        "metric": "has_next_action and has_artifact_target",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Finalize noisy text into operational intent.")
    parser.add_argument("text", nargs="*", help="Input text")
    args = parser.parse_args()
    print(json.dumps(finalize(" ".join(args.text)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
