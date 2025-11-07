import argparse
import json

from ..validate.cv_runner import run_cv


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=str, default="nak_controller/conf/nak.yaml")
    ap.add_argument("--steps", type=int, default=1600)
    ap.add_argument("--seeds", type=int, default=8)
    args = ap.parse_args()
    res = run_cv(args.config, steps=args.steps, seeds=args.seeds)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
