"""
cli.py — VCMix command-line interface entry point.

Provides the `vcmix` CLI with subcommands:
    render    — Render a mix project from YAML config
    validate  — Validate a YAML config without rendering
    graph     — Visualize the signal routing graph
    analyze   — Analyze audio file(s) for RMS/Peak/spectrum

Usage:
    vcmix render project.yaml
    vcmix render project.yaml --report
    vcmix render project.yaml --auto-fix --stream log
    vcmix validate project.yaml
    vcmix graph project.yaml
    vcmix analyze track.wav

Dependencies: click>=8.0, rich>=13.0
"""

from pathlib import Path

import click


@click.group()
@click.version_option(package_name="vcmix")
def main() -> None:
    """VCMix — AI-native open-source DAW CLI."""
    pass


@main.command()
@click.argument("project", type=click.Path(exists=True, path_type=Path))
@click.option("--report", is_flag=True, help="Generate real-time analysis report")
@click.option("--auto-fix", is_flag=True, help="Enable auto-fix for gain/staging issues")
@click.option("--stream", type=click.Choice(["log", "json", "none"]), default="log",
              help="Output stream format")
def render(project: Path, report: bool, auto_fix: bool, stream: str) -> None:
    """Render a mix project from YAML config."""
    from vcmix.config.parser import parse_project
    from vcmix.engine.renderer import Renderer

    cfg = parse_project(project)
    engine = Renderer(cfg, report=report, auto_fix=auto_fix, stream=stream)
    engine.run()
    click.secho("✔ Render complete", fg="green")


@main.command()
@click.argument("project", type=click.Path(exists=True, path_type=Path))
def validate(project: Path) -> None:
    """Validate a YAML config without rendering."""
    from vcmix.config.parser import parse_project
    from vcmix.config.validator import validate_config

    cfg = parse_project(project)
    issues = validate_config(cfg)
    if issues:
        for issue in issues:
            click.secho(f"✗ {issue}", fg="red")
        raise SystemExit(1)
    click.secho("✔ Config is valid", fg="green")


@main.command()
@click.argument("project", type=click.Path(exists=True, path_type=Path))
def graph(project: Path) -> None:
    """Visualize the signal routing graph."""
    from vcmix.config.parser import parse_project

    cfg = parse_project(project)
    click.echo(f"Signal graph for: {project}")
    click.echo("(graph visualization coming in Phase 2)")


if __name__ == "__main__":
    main()
