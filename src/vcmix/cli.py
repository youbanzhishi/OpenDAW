"""
cli.py — VCMix command-line interface entry point.

Provides the `vcmix` CLI with subcommands:
    render    — Render a mix project from YAML config
    validate  — Validate a YAML config without rendering
    graph     — Visualize the signal routing graph
    analyze   — Analyze audio file(s) for RMS/Peak/spectrum

Phase 2 additions:
    --ab      — Render A/B comparison versions
    --diff    — Include difference analysis in A/B mode

Usage:
    vcmix render project.yaml
    vcmix render project.yaml --report
    vcmix render project.yaml --auto-fix --stream log
    vcmix render project.yaml --stream json
    vcmix render project.yaml --ab
    vcmix render project.yaml --ab --diff
    vcmix validate project.yaml
    vcmix graph project.yaml
    vcmix analyze track.wav

Exit Codes (AI Agent processable):
    0  Success
    1  Config error
    2  Plugin CLI error
    3  Audio I/O error
    4  Render error
    5  Cache error
    6  Missing dependency

Dependencies: click>=8.0, rich>=13.0
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click


@click.group()
@click.version_option(package_name="vcmix")
def main() -> None:
    """VCMix — AI-native open-source DAW CLI."""
    pass


@main.command()
@click.argument("project", type=click.Path(exists=True, path_type=Path))
@click.option("--report", is_flag=True, help="Generate per-step analysis report")
@click.option("--auto-fix", is_flag=True, help="Enable auto-fix for gain staging")
@click.option(
    "--stream", type=click.Choice(["log", "json", "none"]),
    default="log", help="Output stream format"
)
@click.option("--ab", is_flag=True, help="Render A/B comparison versions (Phase 2)")
@click.option("--diff", is_flag=True, help="Include difference analysis in A/B mode")
def render(project: Path, report: bool, auto_fix: bool, stream: str, ab: bool, diff: bool) -> None:
    """Render a mix project from YAML config."""
    import vcmix

    try:
        from vcmix.config.parser import parse_project
        from vcmix.engine.renderer import Renderer

        cfg = parse_project(project)
        # Attach project directory for relative path resolution
        cfg.__dict__["_project_dir"] = project.parent.resolve()

        engine = Renderer(
            cfg, report=report, auto_fix=auto_fix, stream=stream,
            ab_mode=ab, ab_diff=diff,
        )
        output_path = engine.run()

        if stream != "json":
            click.secho(f"✔ Render complete → {output_path}", fg="green")
            if ab:
                output_a = output_path.with_name(output_path.stem + "_a" + output_path.suffix)
                output_b = output_path.with_name(output_path.stem + "_b" + output_path.suffix)
                if output_a.exists():
                    click.secho(f"  A version → {output_a}", fg="cyan")
                if output_b.exists():
                    click.secho(f"  B version → {output_b}", fg="cyan")

    except FileNotFoundError as e:
        click.secho(f"✗ File not found: {e}", fg="red")
        sys.exit(vcmix.EXIT_IO_ERROR)
    except ValueError as e:
        click.secho(f"✗ Config error: {e}", fg="red")
        sys.exit(vcmix.EXIT_CONFIG_ERROR)
    except RuntimeError as e:
        click.secho(f"✗ Plugin error: {e}", fg="red")
        sys.exit(vcmix.EXIT_PLUGIN_ERROR)
    except Exception as e:
        click.secho(f"✗ Render failed: {e}", fg="red")
        sys.exit(vcmix.EXIT_RENDER_ERROR)


@main.command()
@click.argument("project", type=click.Path(exists=True, path_type=Path))
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def validate(project: Path, as_json: bool) -> None:
    """Validate a YAML config without rendering."""
    import vcmix

    try:
        from vcmix.config.parser import parse_project

        cfg = parse_project(project)
        issues = _validate_config(cfg)

        if as_json:
            result = {
                "valid": len(issues) == 0,
                "issues": issues,
                "project": cfg.name,
                "tracks": len(cfg.tracks),
                "bpm": cfg.bpm,
            }
            click.echo(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            if issues:
                for issue in issues:
                    click.secho(f"✗ {issue}", fg="yellow")
                click.secho(f"Config has {len(issues)} warning(s)", fg="yellow")
            else:
                click.secho("✔ Config is valid", fg="green")

    except Exception as e:
        if as_json:
            click.echo(json.dumps({"valid": False, "error": str(e)}))
        else:
            click.secho(f"✗ Validation failed: {e}", fg="red")
        sys.exit(vcmix.EXIT_CONFIG_ERROR)


def _validate_config(cfg) -> list[str]:
    """Run validation checks on parsed config. Returns list of issues."""
    issues: list[str] = []

    if not cfg.tracks:
        issues.append("No tracks defined")

    for track in cfg.tracks:
        if not track.file:
            issues.append(f"Track '{track.name}' has no file path")
        for effect in track.effects:
            if not effect.name:
                issues.append(f"Track '{track.name}' has effect with no name")

    # Check master levels reference valid tracks
    track_names = {t.name for t in cfg.tracks}
    for name in cfg.master.levels:
        if name not in track_names:
            issues.append(f"Master level references unknown track: '{name}'")

    # Check send references
    bus_names = {s.name for s in cfg.sends} if cfg.sends else set()
    for track in cfg.tracks:
        for bus_name in track.sends:
            if bus_name not in bus_names:
                issues.append(
                    f"Track '{track.name}' sends to unknown bus: '{bus_name}'"
                )

    # Check sidechain references
    for track in cfg.tracks:
        for effect in track.effects:
            if effect.sidechain is not None and effect.sidechain not in track_names:
                issues.append(
                    f"Track '{track.name}' effect '{effect.name}' sidechains "
                    f"from unknown track: '{effect.sidechain}'"
                )

    return issues


@main.command()
@click.argument("project", type=click.Path(exists=True, path_type=Path))
@click.option(
    "-f", "--format", "fmt",
    type=click.Choice(["text", "mermaid"]),
    default="text", help="Graph output format"
)
def graph(project: Path, fmt: str) -> None:
    """Visualize the signal routing graph."""
    from vcmix.config.parser import parse_project

    cfg = parse_project(project)

    if fmt == "mermaid":
        _graph_mermaid(cfg)
    else:
        _graph_text(cfg)


def _graph_text(cfg) -> None:
    """Print text-based signal graph."""
    click.echo(f"Project: {cfg.name} | BPM: {cfg.bpm} | SR: {cfg.sample_rate}")
    click.echo()

    # Show send buses
    if cfg.sends:
        click.echo("  Send/Return Buses:")
        for bus in cfg.sends:
            chain = " → ".join(e.name for e in bus.effects) if bus.effects else "(direct)"
            click.echo(f"    {bus.name}: {chain} (return={bus.return_level})")
        click.echo()

    for track in cfg.tracks:
        click.echo(f"  Track: {track.name} ({track.file})")
        if track.effects:
            chain = " → ".join(e.name for e in track.effects)
            click.echo(f"    Chain: {chain}")
        else:
            click.echo("    Chain: (direct)")
        if track.sends:
            sends_str = ", ".join(f"{k}={v}" for k, v in track.sends.items())
            click.echo(f"    Sends: {sends_str}")
        if track.effects_a or track.effects_b:
            a_chain = " → ".join(e.name for e in (track.effects_a or [])) or "(same)"
            b_chain = " → ".join(e.name for e in (track.effects_b or [])) or "(same)"
            click.echo(f"    A: {a_chain}")
            click.echo(f"    B: {b_chain}")
        level = cfg.master.levels.get(track.name, 1.0)
        click.echo(f"    → Master (level={level})")
        click.echo()

    if cfg.master.effects:
        chain = " → ".join(e.name for e in cfg.master.effects)
        click.echo(f"  Master Chain: {chain}")
    click.echo(f"  → Output: {cfg.master.output}")


def _graph_mermaid(cfg) -> None:
    """Print Mermaid-format signal graph."""
    click.echo("graph LR")
    for track in cfg.tracks:
        safe_name = track.name.replace(" ", "_")
        click.echo(f"    {safe_name}[{track.name}]")
        prev = safe_name
        for i, effect in enumerate(track.effects):
            node_id = f"{safe_name}_fx{i}"
            click.echo(f"    {node_id}[{effect.name}]")
            click.echo(f"    {prev} --> {node_id}")
            prev = node_id
        click.echo(f"    {prev} --> master[Master]")
    click.echo(f"    master --> output[{cfg.master.output}]")


@main.command()
@click.argument("audio_file", type=click.Path(exists=True, path_type=Path))
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def analyze(audio_file: Path, as_json: bool) -> None:
    """Analyze an audio file for RMS/Peak/spectrum/sibilance."""
    import vcmix
    import numpy as np

    try:
        from vcmix.audio.io import read_audio
        from vcmix.engine.analyzer import Analyzer
        from vcmix.audio.meter import Meter

        audio, sr = read_audio(audio_file)
        analyzer = Analyzer(sample_rate=sr)
        meter = Meter(sample_rate=sr)

        result = {
            "file": str(audio_file),
            "sample_rate": sr,
            "duration_s": round(audio.shape[-1] / sr, 2),
            "channels": audio.shape[0] if audio.ndim == 2 else 1,
            **meter.full_report(audio),
            "sibilance_ratio": round(analyzer.compute_sibilance(audio), 4),
            "spectrum": analyzer.compute_spectrum(audio),
        }

        if as_json:
            click.echo(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            click.echo(f"File:     {audio_file}")
            click.echo(f"Duration: {result['duration_s']}s | SR: {sr}Hz | Ch: {result['channels']}")
            click.echo(f"RMS:      {result['rms_db']:.2f} dBFS")
            click.echo(f"Peak:     {result['peak_db']:.2f} dBFS")
            click.echo(f"TruePeak: {result['true_peak_db']:.2f} dBFS")
            click.echo(f"LUFS:     {result['lufs']:.1f}")
            click.echo(f"DR:       {result['dynamic_range_db']:.2f} dB")
            click.echo(f"Sibilance: {result['sibilance_ratio']:.4f}")

    except FileNotFoundError as e:
        click.secho(f"✗ File not found: {e}", fg="red")
        sys.exit(vcmix.EXIT_IO_ERROR)
    except Exception as e:
        click.secho(f"✗ Analysis failed: {e}", fg="red")
        sys.exit(vcmix.EXIT_RENDER_ERROR)


if __name__ == "__main__":
    main()
