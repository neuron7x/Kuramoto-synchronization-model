#!/usr/bin/env python3
"""Generate flamegraphs for component benchmarks using py-spy.

This script profiles critical components and generates flamegraphs for
performance analysis and bottleneck identification.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import List, Optional


def generate_flamegraph(
    component: str,
    output_dir: Path,
    duration: int = 10,
) -> Path:
    """Generate flamegraph for a component using py-spy.
    
    Args:
        component: Name of component to profile
        output_dir: Directory to save flamegraph
        duration: Duration to profile in seconds
    
    Returns:
        Path to generated flamegraph SVG
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    svg_path = output_dir / f"{component}_flamegraph.svg"
    
    # Create a simple script that runs the benchmark
    benchmark_script = f"""
import sys
sys.path.insert(0, '.')

from scripts.performance.benchmark_components import (
    benchmark_order_router,
    benchmark_link_activator,
    benchmark_thermo_validator,
)

benchmarks = {{
    'order_router': benchmark_order_router,
    'link_activator': benchmark_link_activator,
    'thermo_validator': benchmark_thermo_validator,
}}

if __name__ == '__main__':
    component = '{component}'
    bench_func = benchmarks.get(component)
    if bench_func:
        # Run for {duration} seconds worth of iterations
        import time
        start = time.time()
        while time.time() - start < {duration}:
            bench_func()
    """
    
    script_path = output_dir / f"_profile_{component}.py"
    with open(script_path, "w") as f:
        f.write(benchmark_script)
    
    try:
        # Run py-spy to generate flamegraph
        cmd = [
            sys.executable,
            "-m",
            "py_spy",
            "record",
            "--format", "flamegraph",
            "--output", str(svg_path),
            "--duration", str(duration),
            "--rate", "100",  # Sample rate: 100 Hz
            "--", 
            sys.executable,
            str(script_path),
        ]
        
        print(f"Profiling {component} for {duration} seconds...", file=sys.stderr)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=duration + 30,
        )
        
        if result.returncode != 0:
            print(f"py-spy failed for {component}:", file=sys.stderr)
            print(result.stderr, file=sys.stderr)
            raise RuntimeError(f"py-spy failed with code {result.returncode}")
        
        print(f"  ✓ Generated {svg_path}", file=sys.stderr)
        return svg_path
    
    finally:
        # Cleanup temporary script
        if script_path.exists():
            script_path.unlink()


def generate_all_flamegraphs(
    output_dir: Path,
    components: Optional[List[str]] = None,
    duration: int = 10,
) -> List[Path]:
    """Generate flamegraphs for all specified components."""
    if components is None:
        components = ["order_router", "link_activator", "thermo_validator"]
    
    flamegraphs = []
    for component in components:
        try:
            svg_path = generate_flamegraph(component, output_dir, duration)
            flamegraphs.append(svg_path)
        except Exception as e:
            print(f"Warning: Failed to generate flamegraph for {component}: {e}", file=sys.stderr)
    
    return flamegraphs


def main() -> int:
    """Generate flamegraphs for component benchmarks."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Generate flamegraphs for component benchmarks"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/performance/flamegraphs"),
        help="Directory to save flamegraphs",
    )
    parser.add_argument(
        "--components",
        nargs="+",
        default=None,
        help="Components to profile (default: all)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=10,
        help="Profile duration in seconds per component",
    )
    
    args = parser.parse_args()
    
    try:
        flamegraphs = generate_all_flamegraphs(
            args.output_dir,
            args.components,
            args.duration,
        )
        
        print("\n" + "=" * 70)
        print("FLAMEGRAPH GENERATION SUMMARY")
        print("=" * 70)
        print(f"\nGenerated {len(flamegraphs)} flamegraph(s):")
        for path in flamegraphs:
            print(f"  • {path}")
        print("\n" + "=" * 70)
        
        return 0
    
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
