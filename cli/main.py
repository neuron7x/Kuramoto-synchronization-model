#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Main CLI entry point for TradePulse.

This module provides the top-level command-line interface for TradePulse,
aggregating various subcommands for different functionality areas.

Usage:
    tradepulse --help
    tradepulse hero-scenario run
    tradepulse hero-scenario plot
"""

import click

from cli.hero_scenario import hero_scenario


@click.group()
@click.version_option()
def cli():
    """TradePulse - Advanced algorithmic trading framework."""
    pass


# Register subcommands
cli.add_command(hero_scenario)


def main():
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
