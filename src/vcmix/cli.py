"""
cli.py — VCMix command-line interface entry point.

Provides the `vcmix` CLI with subcommands:
    render    — Render a mix project from YAML config
    validate  — Validate a YAML config without rendering
    graph     — Visualize the signal routing graph
    analyze   — Analyze audio file(s) for RMS/Peak/spectrum
    automix   — Auto-analyze dry vocal and generate YAML config (Phase 4)
    presets   — List all built-in presets (Phase 4)
    separate  — Source separation via Demucs (Phase 4)

Phase 2 additions:
    --ab      — Render A/B comparison versions
    --diff    — Include difference analysis in A/B mode

Phase 7 additions:
    --arrangement-aware — Enable arrangement-aware rendering
    arrangement         — Display arrangement analysis results
    arrangement --strategy — Display mixing strategy

Phase 4 additions:
    automix   — Intelligent auto-mixing from dry vocal analysis
    presets   — List/inspect built-in effect chain presets
    separate  — Demucs-based source separation

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
    vcmix automix vocal.wav
    vcmix automix vocal.wav --bpm 120 --output mix.yaml
    vcmix presets
    vcmix presets --name pop_vocal
    vcmix separate song.wav
    vcmix separate song.wav --model htdemucs --two-stems vocals

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
@click.option("--arrangement-aware", is_flag=True,
              help="Enable arrangement-aware rendering (Phase 7)")
def render(project: Path, report: bool, auto_fix: bool, stream: str,
           ab: bool, diff: bool, arrangement_aware: bool) -> None:
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
            ab_mode=ab, ab_diff=diff, arrangement_aware=arrangement_aware,
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


# ── Phase 4: automix command ──────────────────────────────────────────────

@main.command()
@click.argument("vocal_file", type=click.Path(exists=True, path_type=Path))
@click.option("--bpm", type=float, default=120.0, help="Project BPM (default: 120)")
@click.option("--output", "-o", type=click.Path(path_type=Path), default=None,
              help="Output YAML file path (default: <vocal>_automix.yaml)")
@click.option("--json", "as_json", is_flag=True, help="Output analysis as JSON instead of YAML")
def automix(vocal_file: Path, bpm: float, output: Path | None, as_json: bool) -> None:
    """Auto-analyze dry vocal and generate VCMix YAML config."""
    import vcmix
    import numpy as np

    try:
        from vcmix.audio.io import read_audio
        from vcmix.engine.automix import AutoMixer

        audio, sr = read_audio(vocal_file)
        mixer = AutoMixer(sample_rate=sr, bpm=bpm)
        analysis = mixer.analyze_dry_vocal(audio, sr)

        if as_json:
            # Output analysis as JSON
            result = {
                "file": str(vocal_file),
                "sample_rate": sr,
                "bpm": bpm,
                "analysis": analysis,
                "effects_chain": mixer.generate_chain(analysis),
            }
            click.echo(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            # Generate and output YAML config
            yaml_config = mixer.generate_yaml(
                track_name=vocal_file.stem,
                audio_path=str(vocal_file),
                analysis=analysis,
            )

            if output is None:
                output = vocal_file.with_name(vocal_file.stem + "_automix.yaml")

            import yaml
            with open(output, "w", encoding="utf-8") as f:
                yaml.dump(yaml_config, f, default_flow_style=False, allow_unicode=True)

            click.secho(f"✔ AutoMix analysis complete", fg="green")
            click.echo(f"  RMS:       {analysis['rms_db']:.1f} dBFS")
            click.echo(f"  Peak:      {analysis['peak_db']:.1f} dBFS")
            click.echo(f"  DR:        {analysis['dynamic_range_db']:.1f} dB")
            click.echo(f"  Sibilance: {analysis['sibilance_ratio']:.4f}"
                        f" {'⚠ needs de-ess' if analysis['needs_deesser'] else '✓ OK'}")
            click.echo(f"  Gain:      {analysis['gain_needed_db']:+.1f} dB")
            click.echo(f"  Config:    {output}")

    except FileNotFoundError as e:
        click.secho(f"✗ File not found: {e}", fg="red")
        sys.exit(vcmix.EXIT_IO_ERROR)
    except Exception as e:
        click.secho(f"✗ AutoMix failed: {e}", fg="red")
        sys.exit(vcmix.EXIT_RENDER_ERROR)


# ── Phase 4: presets command ──────────────────────────────────────────────

@main.command("presets")
@click.option("--name", type=str, default=None, help="Show details for a specific preset")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def presets_cmd(name: str | None, as_json: bool) -> None:
    """List all built-in effect chain presets."""
    from vcmix.presets.manager import list_presets, get_preset

    if name:
        chain = get_preset(name)
        if chain is None:
            click.secho(f"✗ Preset not found: {name}", fg="red")
            sys.exit(1)
        if as_json:
            click.echo(json.dumps({"name": name, "effects": chain}, ensure_ascii=False, indent=2))
        else:
            click.secho(f"Preset: {name}", fg="cyan")
            for i, effect in enumerate(chain, 1):
                params_str = ", ".join(f"{k}={v}" for k, v in effect.get("params", {}).items())
                click.echo(f"  {i}. {effect['name']} ({params_str})")
    else:
        preset_names = list_presets()
        if as_json:
            click.echo(json.dumps({"presets": preset_names}, ensure_ascii=False, indent=2))
        else:
            click.secho(f"Built-in Presets ({len(preset_names)}):", fg="cyan")
            for pname in preset_names:
                chain = get_preset(pname)
                n_effects = len(chain) if chain else 0
                click.echo(f"  • {pname} ({n_effects} effects)")


# ── Phase 4: separate command ─────────────────────────────────────────────

@main.command()
@click.argument("audio_file", type=click.Path(exists=True, path_type=Path))
@click.option("--model", type=str, default="htdemucs", help="Demucs model name")
@click.option("--output-dir", "-o", type=click.Path(path_type=Path), default=None,
              help="Output directory for separated stems")
@click.option("--two-stems", type=str, default=None,
              help="Separate into 2 stems (e.g. 'vocals')")
@click.option("--device", type=str, default="cpu", help="Device: cpu or cuda")
def separate(
    audio_file: Path,
    model: str,
    output_dir: Path | None,
    two_stems: str | None,
    device: str,
) -> None:
    """Separate audio into stems using Demucs."""
    import vcmix

    try:
        from vcmix.separation import separate_stems

        click.secho(f"Separating {audio_file.name} with {model}...", fg="cyan")
        results = separate_stems(
            input_path=audio_file,
            output_dir=output_dir,
            model=model,
            device=device,
            two_stems=two_stems,
        )

        click.secho("✔ Separation complete:", fg="green")
        for stem_name, stem_path in sorted(results.items()):
            click.echo(f"  • {stem_name}: {stem_path}")

    except ImportError as e:
        click.secho(f"✗ Demucs not installed: {e}", fg="red")
        click.echo("  Install with: pip install demucs")
        sys.exit(vcmix.EXIT_MISSING_DEP)
    except FileNotFoundError as e:
        click.secho(f"✗ File not found: {e}", fg="red")
        sys.exit(vcmix.EXIT_IO_ERROR)
    except Exception as e:
        click.secho(f"✗ Separation failed: {e}", fg="red")
        sys.exit(vcmix.EXIT_RENDER_ERROR)


@main.command()
@click.argument("project", type=click.Path(exists=True, path_type=Path))
@click.option("--strategy", is_flag=True,
              help="Display the arrangement mixing strategy")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def arrangement(project: Path, strategy: bool, as_json: bool) -> None:
    """Display arrangement analysis and mixing strategy.

    Analyzes the song structure (intro/verse/chorus/bridge/outro) from
    the project's audio tracks and displays the detected sections.
    With --strategy, also shows the per-section mixing parameters.

    Phase 7 feature.
    """
    try:
        from vcmix.config.parser import parse_project
        from vcmix.engine.arrangement_strategy import ArrangementStrategy
        from vcmix.separation.arrangement import ArrangementExtractor

        cfg = parse_project(project)
        project_dir = project.parent.resolve()
        sr = cfg.sample_rate
        bpm = cfg.bpm

        # Try to extract arrangement from audio
        stems = getattr(cfg, "_stems", None)
        if stems and len(stems) > 0:
            extractor = ArrangementExtractor()
            sections = extractor.extract(stems, sr, bpm)
        else:
            # Build from audio files
            import numpy as np
            from vcmix.audio.io import read_audio

            stems = {}
            for track in cfg.tracks:
                track_path = project_dir / track.file
                try:
                    audio, track_sr = read_audio(track_path)
                    # Convert to mono if stereo
                    if audio.ndim == 2:
                        audio = np.mean(audio, axis=0)
                    stems[track.name] = audio.flatten().astype(np.float64)
                except Exception:
                    continue

            if stems:
                extractor = ArrangementExtractor()
                sections = extractor.extract(stems, sr, bpm)
            else:
                sections = []

        if not sections:
            click.secho("No arrangement sections detected", fg="yellow")
            return

        if as_json:
            result = {
                "project": cfg.name,
                "bpm": bpm,
                "sections": [
                    {
                        "name": s.name,
                        "start_beat": s.start_beat,
                        "end_beat": s.end_beat,
                        "start_sec": round(s.start_sec, 2),
                        "end_sec": round(s.end_sec, 2),
                        "energy_level": s.energy_level,
                        "active_stems": s.active_stems,
                    }
                    for s in sections
                ],
            }
            if strategy:
                strat = ArrangementStrategy.from_sections(sections)
                result["strategy"] = {}
                for idx, sec_params in enumerate(strat.sections):
                    start_beat = strat._find_start_beat(idx)
                    result["strategy"][f"section_{idx}_{sec_params.section_name}"] = {
                        "start_beat": start_beat,
                        "reverb_mix": sec_params.reverb_mix,
                        "delay_mix": sec_params.delay_mix,
                        "compression_ratio": sec_params.compression_ratio,
                        "gain_db": sec_params.gain_db,
                        "crossfade_beats": sec_params.crossfade_beats,
                    }
            click.echo(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            click.secho(f"Arrangement Analysis: {cfg.name}", fg="cyan", bold=True)
            click.echo(f"BPM: {bpm} | Sections: {len(sections)}")
            click.echo()
            for s in sections:
                bar = "█" * ((s.end_beat - s.start_beat) // 2)
                click.echo(
                    f"  {s.name:<8} beats {s.start_beat:>3}-{s.end_beat:<3} "
                    f"({s.start_sec:.1f}s-{s.end_sec:.1f}s) "
                    f"energy={s.energy_level:<6} "
                    f"stems={s.active_stems} {bar}"
                )

            if strategy:
                click.echo()
                click.secho("Mixing Strategy:", fg="cyan", bold=True)
                strat = ArrangementStrategy.from_sections(sections)
                for idx, sec_params in enumerate(strat.sections):
                    start_beat = strat._find_start_beat(idx)
                    click.echo(
                        f"  [{sec_params.section_name}] @beat {start_beat}: "
                        f"reverb={sec_params.reverb_mix:.0%} "
                        f"delay={sec_params.delay_mix:.0%} "
                        f"comp={sec_params.compression_ratio:.1f}:1 "
                        f"gain={sec_params.gain_db:+.1f}dB "
                        f"fade={sec_params.crossfade_beats}beats"
                    )

    except Exception as e:
        click.secho(f"✗ Arrangement analysis failed: {e}", fg="red")
        import vcmix
        sys.exit(vcmix.EXIT_RENDER_ERROR)


if __name__ == "__main__":
    main()
