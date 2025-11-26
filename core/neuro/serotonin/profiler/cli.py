#!/usr/bin/env python3
"""Command-line interface for serotonin controller profiling.

Usage:
    python -m core.neuro.serotonin.profiler.cli --config configs/serotonin.yaml --output profile.json
    python -m core.neuro.serotonin.profiler.cli --config configs/serotonin.yaml --mode pulse --plot
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


def load_module_directly(module_name: str, file_path: Path):
    """Load a Python module directly from file path."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def main(argv: list[str] | None = None) -> int:
    """Run profiling CLI."""
    parser = argparse.ArgumentParser(
        description="Profile SerotoninController behavioral characteristics"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="configs/serotonin.yaml",
        help="Path to serotonin configuration file",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["response", "ramp", "pulse"],
        default="ramp",
        help="Profiling mode: response (discrete levels), ramp (continuous), pulse (stress pulses)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Path to save profile JSON (default: profile_<mode>.json)",
    )
    parser.add_argument(
        "--plot",
        action="store_true",
        help="Generate visualization plots",
    )
    parser.add_argument(
        "--plot-output",
        type=str,
        help="Path to save plot (default: profile_<mode>.png)",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Print formatted report to console",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=500,
        help="Total profiling steps (for ramp mode)",
    )
    parser.add_argument(
        "--stress-levels",
        type=str,
        help="Comma-separated stress levels for response mode (e.g., 0.5,1.0,1.5,2.0)",
    )

    args = parser.parse_args(argv)

    # Load modules directly
    controller_path = Path(__file__).parent.parent / "serotonin_controller.py"
    profiler_path = Path(__file__).parent / "behavioral_profiler.py"

    controller_module = load_module_directly(
        "serotonin_controller_cli", controller_path
    )
    profiler_module = load_module_directly("behavioral_profiler_cli", profiler_path)

    SerotoninController = controller_module.SerotoninController
    SerotoninProfiler = profiler_module.SerotoninProfiler

    # Create controller
    print(f"Loading controller from {args.config}")
    controller = SerotoninController(args.config)

    # Create profiler
    profiler = SerotoninProfiler(controller)

    # Run profiling
    print(f"Running profiling in '{args.mode}' mode...")

    if args.mode == "response":
        stress_levels = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
        if args.stress_levels:
            stress_levels = [float(x.strip()) for x in args.stress_levels.split(",")]
        print(f"  Stress levels: {stress_levels}")
        profile = profiler.profile_stress_response(
            stress_levels=stress_levels,
            steps_per_level=50,
        )
    elif args.mode == "ramp":
        print(f"  Steps: {args.steps}")
        profile = profiler.profile_stress_ramp(
            stress_min=0.0,
            stress_max=3.0,
            total_steps=args.steps,
        )
    elif args.mode == "pulse":
        print("  Generating stress pulses...")
        profile = profiler.profile_stress_pulse(
            baseline_stress=0.5,
            pulse_stress=2.5,
            pulse_duration=50,
            recovery_duration=100,
            num_pulses=3,
        )

    print("Profiling complete!")
    print(f"  Total steps: {profile.statistics.total_steps}")
    print(f"  Veto rate: {profile.statistics.veto_rate:.2%}")
    print(f"  Tonic peak: {profile.tonic_phasic.tonic_peak:.3f}")

    # Save profile
    output_path = args.output or f"profile_{args.mode}.json"
    profile.save(output_path)
    print(f"\nProfile saved to: {output_path}")

    # Generate report
    if args.report:
        print("\n" + profile.generate_report())

    # Generate plots
    if args.plot:
        plot_path = args.plot_output or f"profile_{args.mode}.png"
        print("\nGenerating visualization...")
        profiler.plot_profile(profile, output_path=plot_path)
        print(f"Plot saved to: {plot_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
