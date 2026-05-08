"""
cli.py — VCMix command-line interface entry point.

Provides the `vcmix` CLI with subcommands:
    render    — Render a mix project from YAML config
    validate  — Validate a YAML config without rendering
    graph     — Visualize the signal routing graph
    analyze   — Analyze audio file(s) for RMS/Peak/spectrum
    automix   — Auto-analyze and intelligently mix a project (Phase 4 + Phase 6)
    presets   — List all built-in presets (Phase 4)
    separate  — Source separation via Demucs (Phase 4)

Phase 2 additions:
    --ab      — Render A/B comparison versions
    --diff    — Include difference analysis in A/B mode

Phase 4 additions:
    automix   — Intelligent auto-mixing from dry vocal analysis
    presets   — List/inspect built-in effect chain presets
    separate  — Demucs-based source separation
    analyze-mix       — Reverse-engineer mixing parameters
    analyze-arrangement — Analyze arrangement structure
    generate-config   — One-click analysis + VCMix config generation

Phase 6 additions:
    automix project.yaml        — DataStream closed-loop auto-mixing
    automix project.yaml --dry-run — Show suggestions without writing
    automix project.yaml --reference ref.wav — Reference track matching

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
    vcmix automix project.yaml --dry-run
    vcmix automix project.yaml --reference ref.wav
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
from typing import Any

import click
import numpy as np


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
@click.option("--parallel", type=int, default=1, help="Parallel track rendering workers (Phase 10)")
@click.option("--cache-size", type=int, default=500, help="Audio cache size in MB (Phase 10)")
@click.option("--incremental", is_flag=True, help="Only re-render changed tracks (Phase 10)")
@click.option("--arrangement-aware", is_flag=True, help="Apply arrangement-aware mixing (Phase 7)")
def render(
    project: Path, report: bool, auto_fix: bool, stream: str,
    ab: bool, diff: bool, parallel: int, cache_size: int, incremental: bool,
    arrangement_aware: bool,
) -> None:
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
            parallel=parallel, cache_size_mb=cache_size,
            incremental=incremental,
        )
        if arrangement_aware:
            engine.arrangement_aware = True
            click.secho("  Arrangement-aware mixing enabled", fg="cyan")
        if parallel > 1:
            click.secho(f"  Parallel rendering: {parallel} workers", fg="cyan")
        if incremental:
            click.secho("  Incremental rendering enabled", fg="cyan")
        if cache_size != 500:
            click.secho(f"  Audio cache: {cache_size} MB", fg="cyan")
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
        track_type = getattr(track, 'type', 'audio')
        if track_type == 'sampler':
            # Sampler tracks don't need a file field, they use zones
            if not getattr(track, 'zones', []):
                issues.append(f"Sampler track '{track.name}' has no zones defined")
            if not getattr(track, 'midi_file', None):
                issues.append(f"Sampler track '{track.name}' has no MIDI file")
        elif track_type == 'midi':
            # MIDI tracks need midi_file, not file
            if not track.midi_file:
                issues.append(f"MIDI track '{track.name}' has no midi_file")
        elif not track.file:
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

    try:
        from vcmix.audio.io import read_audio
        from vcmix.audio.meter import Meter
        from vcmix.engine.analyzer import Analyzer

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


# ── Phase 4+6: automix command ────────────────────────────────────────────

@main.command()
@click.argument("input_path", type=click.Path(exists=True, path_type=Path))
@click.option("--bpm", type=float, default=120.0, help="Project BPM (default: 120)")
@click.option("--output", "-o", type=click.Path(path_type=Path), default=None,
              help="Output YAML file path")
@click.option("--json", "as_json", is_flag=True, help="Output analysis as JSON instead of YAML")
@click.option("--dry-run", is_flag=False, flag_value="phase6", default=None,
              help="Show suggestions without generating files (Phase 6)")
@click.option("--reference", type=click.Path(exists=True, path_type=Path), default=None,
              help="Reference audio track for matching (Phase 6)")
def automix(
    input_path: Path,
    bpm: float,
    output: Path | None,
    as_json: bool,
    dry_run: str | None,
    reference: Path | None,
) -> None:
    """
    Auto-analyze and intelligently mix audio.

    Phase 4 mode: vcmix automix vocal.wav
        Analyzes a dry vocal file and generates a VCMix YAML config.

    Phase 6 mode: vcmix automix project.yaml
        Runs DataStream closed-loop auto-mixing on an existing project.
        Use --dry-run to see suggestions without writing files.
        Use --reference ref.wav to match a reference track's sound.
    """

    import vcmix

    try:
        # Detect mode: YAML file → Phase 6, audio file → Phase 4
        is_yaml = input_path.suffix.lower() in (".yaml", ".yml")

        if is_yaml:
            _automix_phase6(input_path, bpm, output, as_json, dry_run, reference)
        else:
            _automix_phase4(input_path, bpm, output, as_json)

    except FileNotFoundError as e:
        click.secho(f"✗ File not found: {e}", fg="red")
        sys.exit(vcmix.EXIT_IO_ERROR)
    except Exception as e:
        click.secho(f"✗ AutoMix failed: {e}", fg="red")
        sys.exit(vcmix.EXIT_RENDER_ERROR)


def _automix_phase4(
    vocal_file: Path,
    bpm: float,
    output: Path | None,
    as_json: bool,
) -> None:
    """Phase 4: Analyze dry vocal and generate YAML config."""

    from vcmix.audio.io import read_audio
    from vcmix.engine.automix import AutoMixer

    audio, sr = read_audio(vocal_file)
    mixer = AutoMixer(sample_rate=sr, bpm=bpm)
    analysis = mixer.analyze_dry_vocal(audio, sr)

    if as_json:
        import json
        result = {
            "file": str(vocal_file),
            "sample_rate": sr,
            "bpm": bpm,
            "analysis": analysis,
            "effects_chain": mixer.generate_chain(analysis),
        }
        click.echo(json.dumps(result, ensure_ascii=False, indent=2))
    else:
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

        click.secho("✔ AutoMix analysis complete", fg="green")
        click.echo(f"  RMS:       {analysis['rms_db']:.1f} dBFS")
        click.echo(f"  Peak:      {analysis['peak_db']:.1f} dBFS")
        click.echo(f"  DR:        {analysis['dynamic_range_db']:.1f} dB")
        click.echo(f"  Sibilance: {analysis['sibilance_ratio']:.4f}"
                    f" {'⚠ needs de-ess' if analysis['needs_deesser'] else '✓ OK'}")
        click.echo(f"  Gain:      {analysis['gain_needed_db']:+.1f} dB")
        click.echo(f"  Config:    {output}")


def _automix_phase6(
    project_file: Path,
    bpm: float,
    output: Path | None,
    as_json: bool,
    dry_run: str | None,
    reference: Path | None,
) -> None:
    """
    Phase 6: DataStream closed-loop auto-mixing on an existing project.

    Steps:
        1. Parse the YAML project config
        2. Render with DataStream enabled to capture events
        3. Analyze events → MixingState
        4. Optionally match against a reference track
        5. Generate suggestions
        6. Apply suggestions to produce new config (or show dry-run)
    """

    from vcmix.audio.io import read_audio
    from vcmix.config.parser import parse_project
    from vcmix.engine.automix import AutoMixer
    from vcmix.engine.reference_matcher import ReferenceMatcher
    from vcmix.engine.renderer import Renderer

    # Step 1: Parse project
    cfg = parse_project(project_file)
    cfg.__dict__["_project_dir"] = project_file.parent.resolve()

    # Step 2: Render with DataStream to capture events
    click.secho(f"▸ Rendering {cfg.name} with DataStream...", fg="cyan")
    engine = Renderer(cfg, stream="none")
    try:
        engine.run()
    except (ValueError, RuntimeError):
        # May fail with no tracks or other issues — still collect events
        pass
    events = engine.get_stream_events()

    click.secho(f"  Captured {len(events)} DataStream events", fg="cyan")

    # Step 3: Analyze events
    mixer = AutoMixer(sample_rate=cfg.sample_rate, bpm=cfg.bpm)
    state = mixer.analyze(events)

    click.secho(f"  Tracks analyzed: {len(state.tracks)}", fg="cyan")
    if state.has_clipping:
        click.secho("  ⚠ Clipping detected", fg="yellow")
    if state.has_low_snr:
        click.secho("  ⚠ Low SNR detected", fg="yellow")
    if state.has_sibilance:
        click.secho("  ⚠ Sibilance detected", fg="yellow")

    # Step 4: Optional reference matching
    ref_adjustments = []
    if reference is not None:
        click.secho(f"▸ Analyzing reference: {reference.name}", fg="cyan")
        ref_audio, ref_sr = read_audio(reference)
        ref_matcher = ReferenceMatcher(sample_rate=ref_sr)
        ref_features = ref_matcher.analyze_reference(ref_audio, ref_sr)

        # Build current mix features from master state
        from vcmix.engine.reference_matcher import SpectralFeatures
        current_features = SpectralFeatures(
            rms_db=state.master.rms_db,
            peak_db=state.master.peak_db,
            dynamic_range_db=state.master.dynamic_range_db,
        )

        diff = ref_matcher.compute_match(current_features, ref_features)
        click.secho(f"  Reference match: {diff.summary}", fg="cyan")

        ref_adjustments = ref_matcher.generate_adjustments(diff, target="master")

    # Step 5: Generate suggestions
    suggestions = mixer.suggest(state)

    # Add reference-based suggestions
    all_suggestions_raw = suggestions + [
        _ref_adj_to_suggestion(adj) for adj in ref_adjustments
    ]

    # Sort by priority
    all_suggestions_raw.sort(key=lambda s: s.priority)

    # Display suggestions
    if all_suggestions_raw:
        click.secho(f"\n▸ AutoMix Suggestions ({len(all_suggestions_raw)}):", fg="green")
        for i, s in enumerate(all_suggestions_raw, 1):
            priority_marker = "❗" if s.priority == 1 else "⚠" if s.priority == 2 else "💡"
            click.echo(f"  {i}. {priority_marker} [{s.target}] {s.action}: {s.reason}")
    else:
        click.secho("\n✔ Mix looks good — no suggestions needed", fg="green")

    # Dry-run: stop here
    if dry_run is not None:
        click.secho("\n--dry-run: no files written", fg="yellow")
        if as_json:
            import json
            click.echo(json.dumps({
                "project": str(project_file),
                "events_captured": len(events),
                "tracks_analyzed": len(state.tracks),
                "has_clipping": state.has_clipping,
                "has_low_snr": state.has_low_snr,
                "has_sibilance": state.has_sibilance,
                "suggestions": [
                    {
                        "target": s.target,
                        "action": s.action,
                        "params": s.params,
                        "reason": s.reason,
                        "priority": s.priority,
                    }
                    for s in all_suggestions_raw
                ],
            }, ensure_ascii=False, indent=2))
        return

    # Step 6: Apply suggestions and write new config
    # Convert ProjectConfig to dict for modification
    import yaml as _yaml

    from vcmix.config.parser import parse_project

    # Read the raw YAML to preserve structure
    raw_config = _yaml.safe_load(project_file.read_text(encoding="utf-8"))

    new_config = mixer.apply(raw_config, all_suggestions_raw)

    # Also apply reference-based level adjustments
    for adj in ref_adjustments:
        if adj.category == "level":
            gain_db = adj.params.get("gain_db", 0.0)
            master = new_config.get("master", {})
            levels = master.get("levels", {})
            for name in levels:
                levels[name] = round(levels[name] * (10.0 ** (gain_db / 20.0)), 4)
            master["levels"] = levels

    # Determine output path
    if output is None:
        output = project_file.with_name(
            project_file.stem + "_automix" + project_file.suffix
        )

    with open(output, "w", encoding="utf-8") as f:
        _yaml.dump(new_config, f, default_flow_style=False, allow_unicode=True)

    click.secho(f"\n✔ AutoMix config written → {output}", fg="green")

    if as_json:
        import json
        click.echo(json.dumps({
            "project": str(project_file),
            "output": str(output),
            "events_captured": len(events),
            "suggestions_applied": len(all_suggestions_raw),
        }, ensure_ascii=False, indent=2))


def _ref_adj_to_suggestion(adj) -> Any:
    """Convert a ReferenceAdjustment to an AdjustmentSuggestion."""
    from vcmix.engine.automix import AdjustmentSuggestion

    # Map category to action
    action_map = {
        "eq": "eq",
        "comp": "compressor",
        "level": "gain",
    }
    return AdjustmentSuggestion(
        target=adj.target,
        action=action_map.get(adj.category, adj.category),
        params=adj.params,
        reason=adj.reason,
        priority=2,
    )


# ── Phase 4: presets command ──────────────────────────────────────────────

@main.command("presets")
@click.option("--name", type=str, default=None, help="Show details for a specific preset")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def presets_cmd(name: str | None, as_json: bool) -> None:
    """List all built-in effect chain presets."""
    from vcmix.presets.manager import get_preset, list_presets

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


# ── Phase 7: arrangement command ──────────────────────────────────────────
@main.command()
@click.argument("project", type=click.Path(exists=True, path_type=Path))
@click.option("--strategy", is_flag=True, help="Show mixing strategy per section")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def arrangement(project: Path, strategy: bool, as_json: bool) -> None:
    """Analyze song arrangement structure and mixing strategy.

    \b
    vcmix arrangement project.yaml           — Show section analysis
    vcmix arrangement project.yaml --strategy — Show per-section mixing strategy
    """
    import json as json_mod

    from vcmix.config.parser import parse_project
    from vcmix.engine.arrangement_strategy import ArrangementStrategy
    from vcmix.separation.arrangement import ArrangementExtractor

    cfg = parse_project(project)

    # Extract arrangement from audio if available
    extractor = ArrangementExtractor()
    sections = []
    project_dir = getattr(cfg, "_project_dir", project.parent.resolve())
    for track in cfg.tracks:
        track_path = project_dir / track.file if track.file else None
        if track_path and track_path.exists():
            try:
                from vcmix.audio.io import read_audio
                audio, sr = read_audio(track_path)
                # Extract expects {stem_name: audio_array} dict
                stems = {track.name: audio.flatten()}
                sections = extractor.extract(stems, sr, cfg.bpm)
                break
            except Exception:
                continue

    if not sections:
        click.secho("⚠ No audio found for arrangement analysis", fg="yellow")
        click.echo("  Provide audio files in project YAML for analysis.")
        return

    if not strategy:
        # Show section analysis
        if as_json:
            data = [{"type": s.name, "start_beat": s.start_beat,
                      "end_beat": s.end_beat, "energy_level": s.energy_level,
                      "start_sec": s.start_sec, "end_sec": s.end_sec}
                     for s in sections]
            click.echo(json_mod.dumps(data, indent=2))
        else:
            click.secho("╔══════════════════════════════════════╗", fg="cyan")
            click.secho("║     Arrangement Analysis            ║", fg="cyan")
            click.secho("╚══════════════════════════════════════╝", fg="cyan")
            for s in sections:
                bar = "█" * {"low": 5, "medium": 10, "high": 18}.get(s.energy_level, 10)
                click.echo(
                    f"  {s.name:>8s}  beats "
                    f"{s.start_beat:5d}-{s.end_beat:<5d}  [{bar}] {s.energy_level}"
                )
        return

    # Show mixing strategy
    strat = ArrangementStrategy.from_sections(sections)

    if as_json:
        result = []
        for s in sections:
            params = strat.get_params_at_beat(s.start_beat)
            result.append({
                "section": s.name,
                "start_beat": s.start_beat,
                "end_beat": s.end_beat,
                "strategy": {
                    "reverb_mix": params.reverb_mix,
                    "delay_mix": params.delay_mix,
                    "compression_ratio": params.compression_ratio,
                    "gain_db": params.gain_db,
                    "crossfade_beats": params.crossfade_beats,
                }
            })
        click.echo(json_mod.dumps(result, indent=2))
    else:
        click.secho("╔══════════════════════════════════════╗", fg="cyan")
        click.secho("║   Arrangement Mixing Strategy       ║", fg="cyan")
        click.secho("╚══════════════════════════════════════╝", fg="cyan")
        click.echo(
            f"  {'Section':>8s}  {'Beats':>12s}  "
            f"{'Reverb':>6s}  {'Delay':>5s}  {'Comp':>4s}  {'Gain':>5s}"
        )
        click.echo("  " + "─" * 52)
        for s in sections:
            params = strat.get_params_at_beat(s.start_beat)
            click.echo(f"  {s.name:>8s}  {s.start_beat:5d}-{s.end_beat:<5d}  "
                       f"{params.reverb_mix:5.1f}%  {params.delay_mix:4.1f}%  "
                       f"{params.compression_ratio:3.1f}:1  {params.gain_db:+4.1f}dB")

        # YAML overrides
        overrides = strat.to_yaml_overrides()
        if overrides:
            click.echo()
            click.secho("YAML Overrides:", fg="yellow")
            import yaml
            click.echo(yaml.dump(overrides, default_flow_style=False))



# ── Phase 9.5: sampler command ────────────────────────────────────────

@main.group("sampler")
def sampler_group() -> None:
    """Sampler track operations (Phase 9.5).

    \b
    vcmix sampler info --project proj.yaml --track piano    — Show sampler info
    vcmix sampler render --project proj.yaml --track piano   — Render sampler track
    """
    pass


@sampler_group.command("info")
@click.option("--project", required=True, type=click.Path(exists=True, path_type=Path),
              help="Project YAML file")
@click.option("--track", required=True, help="Sampler track name")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def sampler_info(project: Path, track: str, as_json: bool) -> None:
    """Display sampler track information."""
    from vcmix.config.parser import parse_project
    from vcmix.sampler.sampler_track import SamplerTrack

    cfg = parse_project(project)
    project_dir = project.parent.resolve()

    # Find the sampler track
    track_cfg = None
    for t in cfg.tracks:
        if t.name == track:
            track_cfg = t
            break

    if track_cfg is None:
        click.secho(f"✗ Track '{track}' not found in project", fg="red")
        sys.exit(1)

    if getattr(track_cfg, 'type', 'audio') != 'sampler':
        track_type = getattr(track_cfg, 'type', 'audio')
        click.secho(f"✗ Track '{track}' is not a sampler track (type={track_type})", fg="red")
        sys.exit(1)

    sampler_track = SamplerTrack.from_config(track_cfg, project_dir)

    if as_json:
        click.echo(json.dumps(sampler_track.info, ensure_ascii=False, indent=2))
    else:
        info = sampler_track.info
        click.secho("╔══════════════════════════════════════╗", fg="cyan")
        click.secho(f"║   Sampler Track: {track:<20s}║", fg="cyan")
        click.secho("╚══════════════════════════════════════╝", fg="cyan")
        click.echo(f"  Sample Rate: {info['sample_rate']}")
        click.echo(f"  BPM:         {info['bpm']}")
        click.echo(f"  MIDI File:   {info['midi_file'] or 'N/A'}")
        click.echo(f"  Zones:       {info['zone_count']}")
        for z in info['zones']:
            loaded = "✔" if z['sample_loaded'] else "✗"
            loop_s = z.get('loop_start', 'N/A')
            loop_e = z.get('loop_end', 'N/A')
            loop_info = f"{z['loop_mode']} loop {loop_s}-{loop_e}"
            loop_str = f" [{loop_info}]" if z['has_loop'] else ""
            click.echo(f"    {loaded} {z['file']}")
            click.echo(f"      key={z['key_range']} vel={z['velocity_range']} "
                       f"root={z['root_key']} tune={z['tune_cents']}¢ "
                       f"gain={z['gain_db']}dB{loop_str}")
            click.echo(f"      trigger={z['trigger_mode']} samples={z['sample_length']}")


@sampler_group.command("render")
@click.option("--project", required=True, type=click.Path(exists=True, path_type=Path),
              help="Project YAML file")
@click.option("--track", required=True, help="Sampler track name")
@click.option("--output", type=click.Path(path_type=Path), help="Output WAV file path")
def sampler_render(project: Path, track: str, output: Path | None) -> None:
    """Render a sampler track to audio."""
    from vcmix.audio.io import write_audio
    from vcmix.config.parser import parse_project
    from vcmix.sampler.sampler_track import SamplerTrack

    cfg = parse_project(project)
    project_dir = project.parent.resolve()

    track_cfg = None
    for t in cfg.tracks:
        if t.name == track:
            track_cfg = t
            break

    if track_cfg is None:
        click.secho(f"✗ Track '{track}' not found", fg="red")
        sys.exit(1)

    if getattr(track_cfg, 'type', 'audio') != 'sampler':
        click.secho(f"✗ Track '{track}' is not a sampler track", fg="red")
        sys.exit(1)

    sampler_track = SamplerTrack.from_config(track_cfg, project_dir, sample_rate=cfg.sample_rate)
    sampler_track.bpm = cfg.bpm

    if sampler_track.zone_count == 0:
        click.secho("✗ No sample zones loaded", fg="red")
        sys.exit(1)

    audio = sampler_track.render_full()

    if output is None:
        output = project_dir / f"{track}_sampler_output.wav"

    write_audio(audio, output, cfg.sample_rate)
    click.secho(f"✔ Sampler track '{track}' rendered → {output}", fg="green")
    click.echo(f"  Duration: {len(audio) / cfg.sample_rate:.2f}s ({len(audio)} samples)")


# ── Phase 9: chain-presets command ────────────────────────────────────────

@main.group("chain-presets")
def chain_presets_group() -> None:
    """Manage plugin chain presets (Phase 9).

    \b
    vcmix chain-presets list                  — List all chain presets
    vcmix chain-presets apply vocal-chain     — Apply a chain to a track
    vcmix chain-presets save my-chain         — Save chain from a track
    vcmix chain-presets show vocal-chain      — Show chain preset details
    """
    pass


@chain_presets_group.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def chain_presets_list(as_json: bool) -> None:
    """List all available chain presets."""
    from vcmix.presets.chain_presets import ChainPresetManager

    manager = ChainPresetManager()
    preset_names = manager.list_presets()

    if as_json:
        result = []
        for name in preset_names:
            preset = manager.get(name)
            if preset:
                result.append({
                    "name": preset.name,
                    "description": preset.description,
                    "effects": preset.effect_count,
                    "routing": preset.routing,
                    "tags": preset.tags,
                })
        click.echo(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        click.secho(f"Chain Presets ({len(preset_names)}):", fg="cyan")
        for name in preset_names:
            preset = manager.get(name)
            if preset:
                effects_str = " → ".join(preset.effect_names)
                click.echo(f"  • {name} ({preset.effect_count} effects)")
                click.echo(f"    {effects_str}")
                if preset.tags:
                    click.echo(f"    tags: {', '.join(preset.tags)}")


@chain_presets_group.command("apply")
@click.argument("preset_name")
@click.option("--track", required=True, help="Track name to apply chain to")
@click.option("--project", type=click.Path(exists=True, path_type=Path),
              help="Project YAML file (for in-place modification)")
@click.option("--json", "as_json", is_flag=True, help="Output result as JSON")
def chain_presets_apply(
    preset_name: str, track: str, project: Path | None, as_json: bool
) -> None:
    """Apply a chain preset to a track.

    If --project is given, updates the YAML file in-place.
    Otherwise, prints the resulting track config.
    """
    from vcmix.presets.chain_presets import ChainPresetManager

    manager = ChainPresetManager()
    chain = manager.get(preset_name)
    if chain is None:
        click.secho(f"✗ Chain preset not found: {preset_name}", fg="red")
        sys.exit(1)

    if project:
        import yaml as yaml_mod
        raw = yaml_mod.safe_load(project.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            click.secho("✗ Invalid project YAML", fg="red")
            sys.exit(1)

        tracks = raw.get("tracks", [])
        found = False
        for t in tracks:
            if t.get("name") == track:
                updated = manager.apply_to_track(chain, t)
                t.clear()
                t.update(updated)
                found = True
                break

        if not found:
            click.secho(f"✗ Track '{track}' not found in project", fg="red")
            sys.exit(1)

        with open(project, "w", encoding="utf-8") as f:
            yaml_mod.dump(raw, f, default_flow_style=False, allow_unicode=True)
        click.secho(f"✔ Applied '{preset_name}' to track '{track}'", fg="green")
    else:
        track_config = {"name": track, "file": "unknown.wav"}
        result = manager.apply_to_track(chain, track_config)
        if as_json:
            click.echo(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            click.secho(f"Chain: {chain.name}", fg="cyan")
            click.secho(f"Track: {track}", fg="cyan")
            for i, effect in enumerate(chain.effects, 1):
                params_str = ", ".join(f"{k}={v}" for k, v in effect.params.items())
                status = "" if effect.enabled else " [DISABLED]"
                click.echo(f"  {i}. {effect.name} ({params_str}){status}")


@chain_presets_group.command("save")
@click.argument("name")
@click.option("--from-project", type=click.Path(exists=True, path_type=Path),
              help="Project YAML file to extract chain from")
@click.option("--from-track", help="Track name in the project")
@click.option("--description", default="", help="Description for the chain preset")
def chain_presets_save(
    name: str, from_project: Path | None, from_track: str | None, description: str
) -> None:
    """Save a chain preset from an existing track configuration."""
    from vcmix.presets.chain_presets import ChainPresetManager

    if not from_project or not from_track:
        click.secho("✗ Both --from-project and --from-track are required", fg="red")
        sys.exit(1)

    import yaml as yaml_mod
    raw = yaml_mod.safe_load(from_project.read_text(encoding="utf-8"))

    tracks = raw.get("tracks", [])
    track_config = None
    for t in tracks:
        if t.get("name") == from_track:
            track_config = t
            break

    if track_config is None:
        click.secho(f"✗ Track '{from_track}' not found", fg="red")
        sys.exit(1)

    manager = ChainPresetManager()
    path = manager.save_from_track(name, description, track_config)
    click.secho(f"✔ Chain preset '{name}' saved → {path}", fg="green")


@chain_presets_group.command("show")
@click.argument("preset_name")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def chain_presets_show(preset_name: str, as_json: bool) -> None:
    """Show details of a chain preset."""
    from vcmix.presets.chain_presets import ChainPresetManager

    manager = ChainPresetManager()
    chain = manager.get(preset_name)
    if chain is None:
        click.secho(f"✗ Chain preset not found: {preset_name}", fg="red")
        sys.exit(1)

    if as_json:
        click.echo(json.dumps(chain.to_dict(), ensure_ascii=False, indent=2))
    else:
        click.secho(f"Chain: {chain.name}", fg="cyan")
        click.echo(f"  Description: {chain.description}")
        click.echo(f"  Routing: {chain.routing}")
        click.echo(f"  Effects ({chain.effect_count}):")
        for i, effect in enumerate(chain.effects, 1):
            params_str = ", ".join(f"{k}={v}" for k, v in effect.params.items())
            status = "" if effect.enabled else " [DISABLED]"
            click.echo(f"    {i}. {effect.name} ({params_str}){status}")
        if chain.input_gain_db != 0:
            click.echo(f"  Input gain: {chain.input_gain_db:+.1f} dB")
        if chain.output_gain_db != 0:
            click.echo(f"  Output gain: {chain.output_gain_db:+.1f} dB")
        if chain.tags:
            click.echo(f"  Tags: {', '.join(chain.tags)}")


# ── Demucs v2: analyze-mix command ───────────────────────────────────────

@main.command("analyze-mix")
@click.argument("audio_file", type=click.Path(exists=True, path_type=Path))
@click.option("--output-dir", "-o", type=click.Path(path_type=Path), default=None,
              help="Output directory for stems and analysis")
@click.option("--device", type=str, default="cpu", help="Device: cpu or cuda")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def analyze_mix(
    audio_file: Path,
    output_dir: Path | None,
    device: str,
    as_json: bool,
) -> None:
    """Reverse-engineer mixing parameters from an audio file.

    Separates the audio into stems using Demucs, then analyzes each
    stem's EQ curve, compression, reverb, delay, and panning.
    """
    import vcmix
    from vcmix.audio.io import read_audio
    from vcmix.separation.demucs_engine import DemucsEngine
    from vcmix.separation.reverse_analyzer import ReverseMixAnalyzer

    try:
        # Step 1: Separate
        engine = DemucsEngine(device=device)
        if output_dir is None:
            output_dir = audio_file.parent / "analysis_output"
        output_dir.mkdir(parents=True, exist_ok=True)

        click.secho(f"Separating {audio_file.name}...", fg="cyan")
        stem_paths = engine.separate(audio_file, output_dir=output_dir)
        click.secho(f"  Found {len(stem_paths)} stems", fg="green")

        # Step 2: Analyze each stem
        analyzer = ReverseMixAnalyzer()
        results = {}
        for stem_name, stem_path in sorted(stem_paths.items()):
            click.secho(f"  Analyzing {stem_name}...", fg="cyan")
            try:
                audio, sr = read_audio(stem_path)
                analysis = analyzer.analyze_stem(audio, stem_name)
                results[stem_name] = analysis.to_dict()
            except Exception as e:
                click.secho(f"    ✗ Failed: {e}", fg="yellow")
                results[stem_name] = {"error": str(e)}

        if as_json:
            click.echo(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            for name, data in results.items():
                if "error" in data:
                    click.secho(f"  {name}: ERROR - {data['error']}", fg="red")
                    continue
                click.secho(f"\n  {name.upper()}", fg="cyan", bold=True)
                click.echo(f"    RMS: {data.get('rms_db', 'N/A')} dB")
                click.echo(f"    Peak: {data.get('peak_db', 'N/A')} dB")
                if data.get("eq_curve", {}).get("bands"):
                    bands_str = ", ".join(
                        f"{b['freq']}Hz/{b['gain_db']:+.1f}dB"
                        for b in data["eq_curve"]["bands"]
                    )
                    click.echo(f"    EQ: {bands_str}")
                comp = data.get("compression", {})
                if comp.get("ratio", 1.0) > 1.0:
                    click.echo(f"    Comp: {comp['threshold_db']}dB thresh, "
                               f"{comp['ratio']}:1 ratio")
                rev = data.get("reverb", {})
                if rev.get("rt60_ms", 0) > 100:
                    click.echo(f"    Reverb: RT60={rev['rt60_ms']:.0f}ms, "
                               f"wet={rev['wet_ratio']:.2f}")
                delay = data.get("delay", {})
                if delay.get("delay_ms", 0) > 10:
                    click.echo(f"    Delay: {delay['delay_ms']:.0f}ms, "
                               f"fb={delay['feedback']:.2f}")
                pan = data.get("pan", {})
                if pan.get("stereo_width", 0) > 0:
                    click.echo(f"    Pan: {pan['position']:.2f}, "
                               f"width={pan['stereo_width']:.2f}")

    except ImportError as e:
        click.secho(f"✗ Missing dependency: {e}", fg="red")
        sys.exit(vcmix.EXIT_MISSING_DEP)
    except FileNotFoundError as e:
        click.secho(f"✗ File not found: {e}", fg="red")
        sys.exit(vcmix.EXIT_IO_ERROR)
    except Exception as e:
        click.secho(f"✗ Analysis failed: {e}", fg="red")
        sys.exit(vcmix.EXIT_RENDER_ERROR)


# ── Demucs v2: analyze-arrangement command ──────────────────────────────

@main.command("analyze-arrangement")
@click.argument("audio_file", type=click.Path(exists=True, path_type=Path))
@click.option("--bpm", type=float, default=None, help="Override BPM (auto-detect if omitted)")
@click.option("--device", type=str, default="cpu", help="Device for Demucs")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def analyze_arrangement_cmd(
    audio_file: Path,
    bpm: float | None,
    device: str,
    as_json: bool,
) -> None:
    """Analyze the arrangement structure of an audio file.

    Separates audio into stems, then detects sections (Intro/Verse/Chorus/
    Bridge/Outro) and instrument entry/exit patterns.
    """
    import vcmix
    from vcmix.audio.io import read_audio
    from vcmix.bpm.detector import detect_bpm
    from vcmix.separation.arrangement_analyzer import ArrangementAnalyzer
    from vcmix.separation.demucs_engine import DemucsEngine

    try:
        # Detect BPM
        if bpm is None:
            click.secho("Detecting BPM...", fg="cyan")
            try:
                bpm = detect_bpm(str(audio_file))
            except Exception:
                bpm = 120.0
        click.echo(f"  BPM: {bpm}")

        # Separate
        engine = DemucsEngine(device=device)
        import tempfile
        output_dir = Path(tempfile.mkdtemp(prefix="vcmix_arr_"))
        click.secho("Separating stems...", fg="cyan")
        stem_paths = engine.separate(audio_file, output_dir=output_dir)

        # Load stems
        stems = {}
        sr = 44100
        for stem_name, stem_path in stem_paths.items():
            audio, sr = read_audio(stem_path)
            # Convert to mono for arrangement analysis
            if audio.ndim == 2:
                mono = np.mean(audio, axis=0)
            else:
                mono = audio
            stems[stem_name] = mono

        # Analyze arrangement
        analyzer = ArrangementAnalyzer()
        timeline = analyzer.analyze(stems, sr, bpm)

        if as_json:
            click.echo(json.dumps(timeline.to_dict(), ensure_ascii=False, indent=2))
        else:
            click.secho("\nArrangement:", fg="cyan", bold=True)
            click.echo(f"  Duration: {timeline.duration_sec:.1f}s")
            click.echo(f"  Sections: {len(timeline.sections)}")
            click.echo()
            for s in timeline.sections:
                active = ", ".join(s.active_stems()) or "none"
                click.echo(f"  {s.name:>8s}  {s.start_sec:6.1f}s - {s.end_sec:6.1f}s  "
                           f"[{s.energy_level}]  active: {active}")

    except ImportError as e:
        click.secho(f"✗ Missing dependency: {e}", fg="red")
        sys.exit(vcmix.EXIT_MISSING_DEP)
    except FileNotFoundError as e:
        click.secho(f"✗ File not found: {e}", fg="red")
        sys.exit(vcmix.EXIT_IO_ERROR)
    except Exception as e:
        click.secho(f"✗ Analysis failed: {e}", fg="red")
        sys.exit(vcmix.EXIT_RENDER_ERROR)


# ── Demucs v2: generate-config command ─────────────────────────────────

@main.command("generate-config")
@click.argument("audio_file", type=click.Path(exists=True, path_type=Path))
@click.option("--output", "-o", type=click.Path(path_type=Path), default=None,
              help="Output YAML file path")
@click.option("--bpm", type=float, default=None, help="Override BPM")
@click.option("--device", type=str, default="cpu", help="Device for Demucs")
@click.option("--stem-dir", type=str, default="./stems/", help="Stem file directory")
def generate_config_cmd(
    audio_file: Path,
    output: Path | None,
    bpm: float | None,
    device: str,
    stem_dir: str,
) -> None:
    """One-click analysis + VCMix config generation.

    Separates audio, analyzes mixing, detects arrangement, and generates
    a complete VCMix YAML config that can be used with ``vcmix render``.
    """
    import vcmix
    from vcmix.audio.io import read_audio
    from vcmix.bpm.detector import detect_bpm
    from vcmix.separation.arrangement_analyzer import ArrangementAnalyzer
    from vcmix.separation.config_generator import VCMixConfigGenerator
    from vcmix.separation.demucs_engine import DemucsEngine
    from vcmix.separation.reverse_analyzer import ReverseMixAnalyzer

    try:
        # Detect BPM
        if bpm is None:
            click.secho("Detecting BPM...", fg="cyan")
            try:
                bpm = detect_bpm(str(audio_file))
            except Exception:
                bpm = 120.0
        click.echo(f"  BPM: {bpm}")

        # Separate
        output_dir = audio_file.parent / "stems"
        output_dir.mkdir(parents=True, exist_ok=True)
        engine = DemucsEngine(device=device)
        click.secho("Separating stems...", fg="cyan")
        stem_paths = engine.separate(audio_file, output_dir=output_dir)

        # Analyze each stem
        click.secho("Analyzing mixing parameters...", fg="cyan")
        mix_analyzer = ReverseMixAnalyzer()
        stem_analyses = {}
        stems_audio = {}
        sr = 44100
        for stem_name, stem_path in sorted(stem_paths.items()):
            audio, sr = read_audio(stem_path)
            stems_audio[stem_name] = audio
            stem_analyses[stem_name] = mix_analyzer.analyze_stem(audio, stem_name)
            click.echo(f"  ✓ {stem_name}: RMS={stem_analyses[stem_name].rms_db:.1f}dB")

        # Analyze arrangement
        click.secho("Analyzing arrangement...", fg="cyan")
        arr_analyzer = ArrangementAnalyzer()
        # Convert to mono for arrangement
        mono_stems = {}
        for name, audio in stems_audio.items():
            if audio.ndim == 2:
                mono_stems[name] = np.mean(audio, axis=0)
            else:
                mono_stems[name] = audio
        timeline = arr_analyzer.analyze(mono_stems, sr, bpm)
        click.echo(f"  {len(timeline.sections)} sections detected")

        # Generate config
        click.secho("Generating VCMix config...", fg="cyan")
        generator = VCMixConfigGenerator(stem_dir=stem_dir)
        if output is None:
            output = audio_file.with_suffix(".vcmix.yaml")
        result_path = generator.generate_to_file(
            stem_analyses, timeline, bpm, output,
        )
        click.secho(f"✔ Config saved → {result_path}", fg="green")

    except ImportError as e:
        click.secho(f"✗ Missing dependency: {e}", fg="red")
        sys.exit(vcmix.EXIT_MISSING_DEP)
    except FileNotFoundError as e:
        click.secho(f"✗ File not found: {e}", fg="red")
        sys.exit(vcmix.EXIT_IO_ERROR)
    except Exception as e:
        click.secho(f"✗ Config generation failed: {e}", fg="red")
        sys.exit(vcmix.EXIT_RENDER_ERROR)


# ── Phase 12: Arrangement Template & Mix Preset Commands ──────────────────────

@main.command("templates")
@click.option("--genre", type=str, default=None, help="Filter by genre")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_arrangement_templates(genre: str | None, as_json: bool) -> None:
    """List available arrangement templates (Phase 12)."""
    from vcmix.arrangement.templates import TEMPLATE_REGISTRY, list_templates, list_templates_by_genre

    keys = list_templates_by_genre(genre) if genre else list_templates()

    if as_json:
        result = []
        for key in keys:
            tmpl = TEMPLATE_REGISTRY[key]
            result.append({
                "key": key,
                "name": tmpl.name,
                "genre": tmpl.genre,
                "bpm_range": list(tmpl.bpm_range),
                "sections": len(tmpl.structure),
                "total_bars": tmpl.total_bars,
                "default_key": tmpl.default_key,
                "description": tmpl.description,
            })
        click.echo(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        click.secho(f"\n  Arrangement Templates ({len(keys)}):\n", fg="cyan", bold=True)
        for key in keys:
            tmpl = TEMPLATE_REGISTRY[key]
            sections_str = " → ".join(tmpl.section_names)
            click.echo(f"  {key}")
            click.echo(f"    {tmpl.name} [{tmpl.genre}] — BPM {tmpl.bpm_range[0]}-{tmpl.bpm_range[1]}")
            click.echo(f"    {sections_str}")
            click.echo(f"    {tmpl.total_bars} bars, key: {tmpl.default_key}")
            click.echo()


@main.command("apply-template")
@click.argument("template_name")
@click.option("--bpm", type=float, default=120.0, help="BPM")
@click.option("--key", "musical_key", type=str, default="C", help="Musical key")
@click.option("--output", "-o", type=click.Path(path_type=Path), default=None, help="Output YAML path")
def apply_template(template_name: str, bpm: float, musical_key: str, output: Path | None) -> None:
    """Apply an arrangement template to generate a VCMix YAML project (Phase 12)."""
    import vcmix
    from vcmix.arrangement.templates import get_template
    from vcmix.arrangement.template_applier import TemplateApplier

    template = get_template(template_name)
    if template is None:
        click.secho(f"✗ Template not found: {template_name}", fg="red")
        click.echo("  Use 'vcmix templates' to list available templates.")
        sys.exit(vcmix.EXIT_CONFIG_ERROR)

    try:
        applier = TemplateApplier()
        yaml_str = applier.apply(template, bpm=bpm, key=musical_key)

        if output is None:
            output = Path(f"{template_name}_{musical_key}_{int(bpm)}bpm.yaml")

        output.write_text(yaml_str, encoding="utf-8")

        click.secho(f"✔ Applied template: {template.name}", fg="green")
        click.echo(f"  BPM: {bpm}, Key: {musical_key}")
        click.echo(f"  Sections: {len(template.structure)}, Total bars: {template.total_bars}")
        click.echo(f"  Output → {output}")

    except Exception as e:
        click.secho(f"✗ Template application failed: {e}", fg="red")
        sys.exit(vcmix.EXIT_RENDER_ERROR)


@main.command("mix-presets")
@click.option("--genre", type=str, default=None, help="Filter by genre")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_mix_presets_cmd(genre: str | None, as_json: bool) -> None:
    """List available mix presets (Phase 12)."""
    from vcmix.presets.mix_presets import MIX_PRESET_REGISTRY, list_mix_presets, list_mix_presets_by_genre

    keys = list_mix_presets_by_genre(genre) if genre else list_mix_presets()

    if as_json:
        result = []
        for key in keys:
            preset = MIX_PRESET_REGISTRY[key]
            result.append({
                "key": key,
                "name": preset.name,
                "genre": preset.genre,
                "description": preset.description,
                "track_types": preset.track_types,
                "master_target_lufs": preset.master.target_lufs,
            })
        click.echo(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        click.secho(f"\n  Mix Presets ({len(keys)}):\n", fg="cyan", bold=True)
        for key in keys:
            preset = MIX_PRESET_REGISTRY[key]
            track_types_str = ", ".join(preset.track_types)
            click.echo(f"  {key}")
            click.echo(f"    {preset.name} [{preset.genre}]")
            click.echo(f"    {preset.description}")
            click.echo(f"    Tracks: {track_types_str}")
            click.echo(f"    Master target: {preset.master.target_lufs} LUFS")
            click.echo()


# ── Phase 15: AI Composition & Smart Mixing Commands ────────────────────

@main.command("compose")
@click.option("--genre", type=str, required=True, help="Genre: pop/rock/edm/hiphop/rnb/ballad/lofi")
@click.option("--bpm", type=float, default=120.0, help="Tempo in BPM")
@click.option("--key", "musical_key", type=str, default="C", help="Musical key (e.g. C, Am, D Major)")
@click.option("--mood", type=str, default="happy", help="Mood: happy/sad/energetic/calm/dark/bright")
@click.option("--duration", type=float, default=180.0, help="Target duration in seconds")
@click.option("--reference", type=click.Path(exists=True, path_type=Path), default=None, help="Reference track path")
@click.option("--output", "-o", type=click.Path(path_type=Path), default=None, help="Output YAML path")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def compose_cmd(
    genre: str, bpm: float, musical_key: str, mood: str,
    duration: float, reference: Path | None, output: Path | None, as_json: bool,
) -> None:
    """AI composition engine — generate a complete arrangement (Phase 15).

    Creates a VCMix project configuration with chord progression, melody,
    drum patterns, bass lines, and instrument assignments based on the
    specified genre, key, BPM, and mood.
    """
    import vcmix
    from vcmix.ai.composer import AIComposer

    try:
        composer = AIComposer()
        result = composer.compose(
            genre=genre,
            duration=duration,
            bpm=bpm,
            key=musical_key,
            mood=mood,
            reference=str(reference) if reference else None,
        )

        if as_json:
            output_dict = result.to_dict()
            click.echo(json.dumps(output_dict, ensure_ascii=False, indent=2, default=str))
        else:
            click.secho(f"✔ Composition generated: {genre.title()} in {musical_key}", fg="green")
            click.echo(f"  BPM: {bpm}, Duration: {duration}s, Mood: {mood}")
            click.echo(f"  Scale: {result.scale}")
            click.echo(f"  Sections: {result.sections}, Total bars: {result.total_bars}")
            if result.chord_progression:
                cp_str = " - ".join(c.name for c in result.chord_progression.chords)
                click.echo(f"  Chord progression: {cp_str}")
            click.echo(f"  Instruments: {', '.join(result.instruments.keys())}")
            click.echo(f"  Composition time: {result.composition_time_sec:.3f}s")

        # Save output if requested
        if output is not None:
            import yaml
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                yaml.dump(result.project_config, allow_unicode=True, default_flow_style=False),
                encoding="utf-8",
            )
            if not as_json:
                click.secho(f"  Saved → {output}", fg="cyan")

    except Exception as e:
        click.secho(f"✗ Composition failed: {e}", fg="red")
        sys.exit(vcmix.EXIT_RENDER_ERROR)


@main.command("auto-mix")
@click.argument("project", type=click.Path(exists=True, path_type=Path))
@click.option("--max-iterations", type=int, default=3, help="Maximum mixing iterations")
@click.option("--target-lufs", type=float, default=-14.0, help="Target LUFS")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def auto_mix_cmd(
    project: Path, max_iterations: int, target_lufs: float, as_json: bool,
) -> None:
    """Smart mixing closed-loop — auto-iterate to optimize mix (Phase 15).

    Runs an iterative render→analyze→diagnose→adjust→verify pipeline
    to optimize the mix toward target loudness, spectral balance, and
    dynamic range.
    """
    import vcmix
    from vcmix.ai.smart_mixer import SmartMixer

    try:
        mixer = SmartMixer(target_lufs=target_lufs)
        result = mixer.auto_mix(
            project_config=str(project),
            max_iterations=max_iterations,
        )

        if as_json:
            click.echo(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, default=str))
        else:
            click.secho(f"✔ Smart mixing complete ({result.total_iterations} iterations)", fg="green")
            click.echo(f"  Converged: {'Yes' if result.converged else 'No'}")
            click.echo(f"  Initial LUFS: {result.initial_analysis.lufs:.1f}")
            click.echo(f"  Final LUFS: {result.final_analysis.lufs:.1f}")
            click.echo(f"  Total time: {result.total_time_sec:.3f}s")

            for itr in result.iterations:
                click.echo(f"\n  Iteration {itr.iteration}:")
                click.echo(f"    Diagnoses: {len(itr.diagnoses)}")
                for diag in itr.diagnoses:
                    click.echo(f"      [{diag.severity}] {diag.target}: {diag.problem}")
                click.echo(f"    Improved: {'Yes' if itr.improved else 'No'}")

    except FileNotFoundError as e:
        click.secho(f"✗ File not found: {e}", fg="red")
        sys.exit(vcmix.EXIT_IO_ERROR)
    except Exception as e:
        click.secho(f"✗ Auto-mix failed: {e}", fg="red")
        sys.exit(vcmix.EXIT_RENDER_ERROR)


@main.command("compose-and-mix")
@click.option("--genre", type=str, required=True, help="Genre: pop/rock/edm/hiphop/rnb/ballad")
@click.option("--bpm", type=float, default=120.0, help="Tempo in BPM")
@click.option("--key", "musical_key", type=str, default="C", help="Musical key")
@click.option("--mood", type=str, default="happy", help="Mood: happy/sad/energetic/calm/dark/bright")
@click.option("--duration", type=float, default=180.0, help="Target duration in seconds")
@click.option("--max-iterations", type=int, default=3, help="Maximum mixing iterations")
@click.option("--output", "-o", type=click.Path(path_type=Path), default=None, help="Output YAML path")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def compose_and_mix_cmd(
    genre: str, bpm: float, musical_key: str, mood: str,
    duration: float, max_iterations: int, output: Path | None, as_json: bool,
) -> None:
    """One-click compose + mix — AI composition with smart mixing (Phase 15).

    Generates a complete arrangement and automatically optimizes the mix
    in a single pipeline.
    """
    import vcmix
    from vcmix.ai.arrangement_mixer import ArrangementMixer

    try:
        am = ArrangementMixer()
        result = am.compose_and_mix(
            genre=genre,
            duration=duration,
            bpm=bpm,
            key=musical_key,
            mood=mood,
            max_mix_iterations=max_iterations,
        )

        if as_json:
            click.echo(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, default=str))
        else:
            status_color = {"success": "green", "partial": "yellow", "failed": "red"}
            click.secho(f"✔ Compose & Mix: {result.status.upper()}", fg=status_color.get(result.status, "white"))
            if result.composition:
                click.echo(f"  Genre: {genre}, Key: {musical_key}, BPM: {bpm}")
                click.echo(f"  Sections: {result.composition.sections}")
            if result.mix_result:
                click.echo(f"  Mixing iterations: {result.mix_result.total_iterations}")
                click.echo(f"  Converged: {'Yes' if result.mix_result.converged else 'No'}")
            click.echo(f"  Total time: {result.total_time_sec:.3f}s")

        # Save output if requested
        if output is not None and result.final_config:
            import yaml
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                yaml.dump(result.final_config, allow_unicode=True, default_flow_style=False),
                encoding="utf-8",
            )
            if not as_json:
                click.secho(f"  Saved → {output}", fg="cyan")

    except Exception as e:
        click.secho(f"✗ Compose & Mix failed: {e}", fg="red")
        sys.exit(vcmix.EXIT_RENDER_ERROR)


# ── Phase 16: Serve command ──────────────────────────────────────────────


@main.command()
@click.option("--host", default="127.0.0.1", help="Bind host address")
@click.option("--port", default=8000, type=int, help="Bind port number")
@click.option("--reload", is_flag=True, help="Enable auto-reload (development)")
@click.option(
    "--profile", type=click.Choice(["core", "full"]), default="full",
    help="Startup profile: core (lightweight, ~40% less memory) or full (all features)",
)
def serve(host: str, port: int, reload: bool, profile: str) -> None:
    """Start VCMix web UI server.

    Launches the FastAPI-based web interface, providing both REST API
    and WebSocket endpoints for AI Agent and human interaction.

    Profiles:
        core — Lightweight mode: render/plugins/presets/midi/automation/
               arrangement/automix + agent_api basic endpoints.
               No AI transcription, collaboration, or visualization routes.
               Recommended for 1G memory servers.

        full — All features including AI transcription, collaboration,
               waveform/spectrum/piano-roll visualization. (default)

    Examples:

        vcmix serve
        vcmix serve --profile core
        vcmix serve --host 0.0.0.0 --port 8080
        vcmix serve --reload
    """
    try:
        import uvicorn
        from vcmix.web.app import create_app
    except ImportError:
        click.secho(
            "✗ Web UI dependencies not installed. Install with: pip install vcmix[web]",
            fg="red",
        )
        sys.exit(6)

    # Set VCMIX_PROFILE env var so module-level app instance picks it up
    import os
    os.environ["VCMIX_PROFILE"] = profile

    app = create_app(profile=profile)  # type: ignore[arg-type]

    if profile == "core":
        click.secho(f"♫ VCMix web UI (core profile) → http://{host}:{port}", fg="cyan", bold=True)
        click.secho("  ⚡ Core mode: AI/collab/visualization endpoints disabled", fg="yellow")
    else:
        click.secho(f"♫ VCMix web UI → http://{host}:{port}", fg="cyan", bold=True)

    if reload:
        uvicorn.run(
            "vcmix.web.app:create_app",
            host=host,
            port=port,
            reload=True,
            factory=True,
        )
    else:
        uvicorn.run(app, host=host, port=port)


# ── Phase 17: AI Transcription, Style Match, Style Transfer, Remix ──────


@main.command("transcribe")
@click.argument("reference", type=click.Path(exists=True, path_type=Path))
@click.option("--output-dir", "-o", type=click.Path(path_type=Path), default=None,
              help="Output directory for transcribed project")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def transcribe_cmd(
    reference: Path, output_dir: Path | None, as_json: bool,
) -> None:
    """AI transcription —扒带 reference track into editable VCMix project (Phase 17).

    Analyzes a reference audio track and generates a complete VCMix project
    with separated stems, reverse mixing analysis, BPM/key detection,
    and arrangement structure.

    Pipeline: separate → reverse analyze → detect BPM/key → generate project
    """
    import vcmix
    from vcmix.ai.transcription import AITranscription

    if output_dir is None:
        output_dir = Path(f"./transcription_{reference.stem}")

    try:
        transcriber = AITranscription()
        result = transcriber.transcribe(str(reference), str(output_dir))

        if as_json:
            click.echo(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, default=str))
        else:
            status_color = "green" if result.status == "success" else "red"
            click.secho(f"✔ Transcription: {result.status.upper()}", fg=status_color)
            click.echo(f"  BPM: {result.bpm_info.bpm}")
            click.echo(f"  Key: {result.key_info.root} {result.key_info.scale_type}")
            click.echo(f"  Stems: {', '.join(result.stems.keys())}")
            click.echo(f"  Sections: {len(result.arrangement.get('sections', []))}")
            click.echo(f"  Project: {result.project_yaml}")
            click.echo(f"  Time: {result.transcription_time_sec:.3f}s")

    except Exception as e:
        click.secho(f"✗ Transcription failed: {e}", fg="red")
        sys.exit(vcmix.EXIT_RENDER_ERROR)


@main.command("match-style")
@click.argument("reference", type=click.Path(exists=True, path_type=Path))
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def match_style_cmd(
    reference: Path, as_json: bool,
) -> None:
    """Match reference track style — recommend template and preset (Phase 17).

    Analyzes a reference track's style features and recommends a matching
    arrangement template and mixing preset.
    """
    import vcmix
    from vcmix.ai.reference_matcher_v2 import ReferenceMatcherV2

    try:
        matcher = ReferenceMatcherV2()
        result = matcher.match_style(reference_path=str(reference))

        if as_json:
            click.echo(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, default=str))
        else:
            click.secho("✔ Style Match Results", fg="green")
            click.echo(f"  Genre: {result.features.genre}")
            click.echo(f"  BPM: {result.features.bpm}")
            click.echo(f"  Key: {result.features.key} {result.features.scale_type}")
            click.echo(f"  Dynamic Range: {result.features.dynamic_range:.1f} dB")
            click.echo(f"  Template: {result.recommended_template.template_name}")
            click.echo(f"  Template Score: {result.recommended_template.match_score:.2f}")
            click.echo(f"  Preset: {result.recommended_mix_preset.preset_name}")
            click.echo(f"  Time: {result.match_time_sec:.3f}s")

    except Exception as e:
        click.secho(f"✗ Style match failed: {e}", fg="red")
        sys.exit(vcmix.EXIT_RENDER_ERROR)


@main.command("style-transfer")
@click.argument("reference", type=click.Path(exists=True, path_type=Path))
@click.option("--project", "-p", type=click.Path(exists=True, path_type=Path), required=True,
              help="Target project YAML to apply style to")
@click.option("--output", "-o", type=click.Path(path_type=Path), default=None,
              help="Output YAML path")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def style_transfer_cmd(
    reference: Path, project: Path, output: Path | None, as_json: bool,
) -> None:
    """Style transfer — apply reference mixing style to project (Phase 17).

    Analyzes the reference track's mixing style (EQ, compression, reverb,
    gain balance) and applies it to the target project.
    """
    import vcmix
    from vcmix.ai.style_transfer import StyleTransfer

    if output is None:
        output = project.parent / f"{project.stem}_styled.yaml"

    try:
        st = StyleTransfer()
        result = st.transfer(
            reference_path=str(reference),
            project_yaml=str(project),
            output_yaml=str(output),
        )

        if as_json:
            click.echo(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, default=str))
        else:
            status_color = "green" if result.status == "success" else "red"
            click.secho(f"✔ Style Transfer: {result.status.upper()}", fg=status_color)
            click.echo(f"  EQ transfers: {len(result.eq_transfers)} tracks")
            click.echo(f"  Comp transfers: {len(result.comp_transfers)} tracks")
            click.echo(f"  Reverb transfers: {len(result.reverb_transfers)} tracks")
            click.echo(f"  Gain adjustments: {len(result.gain_adjustments)} tracks")
            click.echo(f"  Output: {result.output_yaml}")
            click.echo(f"  Time: {result.transfer_time_sec:.3f}s")

    except Exception as e:
        click.secho(f"✗ Style transfer failed: {e}", fg="red")
        sys.exit(vcmix.EXIT_RENDER_ERROR)


@main.command("remix")
@click.argument("reference", type=click.Path(exists=True, path_type=Path))
@click.option("--stems", "-s", type=click.Path(exists=True, path_type=Path), required=True,
              help="Directory containing new stem audio files")
@click.option("--genre", "-g", type=str, default=None,
              help="Override genre for remix")
@click.option("--bpm", type=float, default=None,
              help="Override BPM for remix")
@click.option("--output-dir", "-o", type=click.Path(path_type=Path), default=None,
              help="Output directory")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def remix_cmd(
    reference: Path, stems: Path, genre: str | None, bpm: float | None,
    output_dir: Path | None, as_json: bool,
) -> None:
    """One-click Remix — blend reference style with new stems (Phase 17).

    Analyzes the reference track, replaces specified stems with new素材,
    and auto-mixes everything in the reference's style.
    """
    import vcmix
    from vcmix.ai.remix import RemixEngine

    # Collect new stems from directory
    new_stems: dict[str, str] = {}
    if stems.is_dir():
        for wav_file in stems.glob("*.wav"):
            new_stems[wav_file.stem] = str(wav_file)
        for wav_file in stems.glob("*.mp3"):
            new_stems[wav_file.stem] = str(wav_file)
    else:
        click.secho("✗ --stems must be a directory", fg="red")
        sys.exit(1)

    if not new_stems:
        click.secho("✗ No audio files found in stems directory", fg="red")
        sys.exit(1)

    if output_dir is None:
        output_dir = Path(f"./remix_{reference.stem}")

    try:
        engine = RemixEngine()
        result = engine.remix(
            reference_path=str(reference),
            new_stems=new_stems,
            genre=genre,
            bpm=bpm,
            output_dir=str(output_dir),
        )

        if as_json:
            click.echo(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, default=str))
        else:
            status_color = "green" if result.status == "success" else "red"
            click.secho(f"✔ Remix: {result.status.upper()}", fg=status_color)
            click.echo(f"  Replaced stems: {', '.join(result.replaced_stems) or 'none'}")
            click.echo(f"  Kept stems: {', '.join(result.kept_stems) or 'none'}")
            click.echo(f"  Output: {result.output_yaml}")
            click.echo(f"  Time: {result.remix_time_sec:.3f}s")

    except Exception as e:
        click.secho(f"✗ Remix failed: {e}", fg="red")
        sys.exit(vcmix.EXIT_RENDER_ERROR)


# ── Phase 18: Export & Version Management ──────────────────────────────────


@main.command("export")
@click.argument("project", type=click.Path(exists=True, path_type=Path))
@click.option("--format", "-f", "fmt", type=click.Choice(["wav", "mp3", "flac", "ogg"]),
              default="wav", help="Output format")
@click.option("--output", "-o", type=click.Path(path_type=Path), default=None,
              help="Output file path")
@click.option("--bitrate", type=str, default=None, help="MP3 bitrate (e.g. 320k)")
@click.option("--sample-rate", type=int, default=None, help="Target sample rate")
def export_cmd(
    project: Path, fmt: str, output: Path | None, bitrate: str | None,
    sample_rate: int | None,
) -> None:
    """Export project audio to WAV/MP3/FLAC/OGG (Phase 18).

    Renders the project and exports to the specified format.

    Examples:

        vcmix export project.yaml --format mp3 --bitrate 320k
        vcmix export project.yaml --format flac --output mix.flac
    """
    import vcmix
    from vcmix.export.exporter import AudioExporter

    try:
        # Render first
        from vcmix.config.parser import parse_project
        from vcmix.engine.renderer import Renderer

        cfg = parse_project(project)
        cfg.__dict__["_project_dir"] = project.parent.resolve()
        engine = Renderer(cfg, stream="none")
        wav_output = engine.run()

        if wav_output is None:
            click.secho("✗ Render produced no output", fg="red")
            sys.exit(vcmix.EXIT_RENDER_ERROR)

        # Export to target format
        quality = {}
        if bitrate:
            quality["bitrate"] = bitrate
        if sample_rate:
            quality["sample_rate"] = sample_rate

        if output is None:
            output = Path(wav_output).with_suffix(f".{fmt}")

        exporter = AudioExporter()
        result = exporter.export(
            input_wav=str(wav_output),
            output_path=str(output),
            format=fmt,
            quality=quality or None,
        )
        click.secho(f"✔ Exported → {result} ({fmt})", fg="green")

    except FileNotFoundError as e:
        click.secho(f"✗ File not found: {e}", fg="red")
        sys.exit(vcmix.EXIT_IO_ERROR)
    except ValueError as e:
        click.secho(f"✗ Invalid format: {e}", fg="red")
        sys.exit(vcmix.EXIT_CONFIG_ERROR)
    except Exception as e:
        click.secho(f"✗ Export failed: {e}", fg="red")
        sys.exit(vcmix.EXIT_RENDER_ERROR)


@main.command("export-stems")
@click.argument("project", type=click.Path(exists=True, path_type=Path))
@click.option("--format", "-f", "fmt", type=click.Choice(["wav", "mp3", "flac", "ogg"]),
              default="wav", help="Output format")
@click.option("--output-dir", "-o", type=click.Path(path_type=Path), default=None,
              help="Output directory for stems")
@click.option("--by-bus", is_flag=True, help="Export by bus instead of per-track")
def export_stems_cmd(
    project: Path, fmt: str, output_dir: Path | None, by_bus: bool,
) -> None:
    """Export project stems — per-track or per-bus (Phase 18).

    Each track (or bus) is rendered and exported as a separate file.

    Examples:

        vcmix export-stems project.yaml --format wav
        vcmix export-stems project.yaml --by-bus --format flac
    """
    import vcmix
    from vcmix.export.exporter import AudioExporter

    try:
        if output_dir is None:
            output_dir = project.parent / "stems"

        exporter = AudioExporter()
        if by_bus:
            results = exporter.export_stems_by_bus(
                project_yaml=str(project),
                output_dir=str(output_dir),
                format=fmt,
            )
        else:
            results = exporter.export_stems(
                project_yaml=str(project),
                output_dir=str(output_dir),
                format=fmt,
            )

        click.secho(f"✔ Exported {len(results)} stems → {output_dir}/", fg="green")
        for name, path in results.items():
            click.echo(f"  {name}: {path}")

    except FileNotFoundError as e:
        click.secho(f"✗ File not found: {e}", fg="red")
        sys.exit(vcmix.EXIT_IO_ERROR)
    except Exception as e:
        click.secho(f"✗ Stem export failed: {e}", fg="red")
        sys.exit(vcmix.EXIT_RENDER_ERROR)


@main.command("snapshot")
@click.argument("project", type=click.Path(exists=True, path_type=Path))
@click.option("--message", "-m", type=str, default="", help="Snapshot description")
def snapshot_cmd(project: Path, message: str) -> None:
    """Create a project snapshot (Phase 18).

    Saves a versioned copy of the project YAML for later restoration.

    Examples:

        vcmix snapshot project.yaml --message "v1 baseline"
    """
    import vcmix
    from vcmix.project.version_manager import ProjectVersionManager

    try:
        vm = ProjectVersionManager()
        snapshot_id = vm.create_snapshot(str(project), message=message)
        click.secho(f"✔ Snapshot created: {snapshot_id}", fg="green")
        if message:
            click.echo(f"  Message: {message}")

    except FileNotFoundError as e:
        click.secho(f"✗ File not found: {e}", fg="red")
        sys.exit(vcmix.EXIT_IO_ERROR)
    except Exception as e:
        click.secho(f"✗ Snapshot failed: {e}", fg="red")
        sys.exit(vcmix.EXIT_RENDER_ERROR)


@main.command("snapshots")
@click.argument("project", type=click.Path(exists=True, path_type=Path))
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def snapshots_cmd(project: Path, as_json: bool) -> None:
    """List project snapshots (Phase 18).

    Shows all saved snapshots with timestamps and messages.

    Examples:

        vcmix snapshots project.yaml
        vcmix snapshots project.yaml --json
    """
    import vcmix
    import hashlib
    from vcmix.project.version_manager import ProjectVersionManager

    try:
        vm = ProjectVersionManager()
        project_name = project.stem
        project_id = hashlib.sha256(project_name.encode("utf-8")).hexdigest()[:12]
        snapshots = vm.list_snapshots(project_id)

        if as_json:
            click.echo(json.dumps(snapshots, ensure_ascii=False, indent=2, default=str))
        else:
            if not snapshots:
                click.echo("No snapshots found.")
            else:
                click.secho(f"Snapshots for {project_name} ({len(snapshots)}):", fg="cyan")
                for snap in snapshots:
                    msg = snap.get("message", "")
                    ts = snap.get("created_at", "")
                    sid = snap.get("snapshot_id", "")
                    click.echo(f"  {sid}  {ts}  {msg}")

    except Exception as e:
        click.secho(f"✗ Failed to list snapshots: {e}", fg="red")
        sys.exit(vcmix.EXIT_RENDER_ERROR)


@main.command("restore")
@click.argument("project", type=click.Path(exists=True, path_type=Path))
@click.option("--snapshot", "-s", type=str, required=True, help="Snapshot ID to restore")
def restore_cmd(project: Path, snapshot: str) -> None:
    """Restore project from a snapshot (Phase 18).

    Creates a backup of the current project and replaces it with
    the snapshot version.

    Examples:

        vcmix restore project.yaml --snapshot snap_12345_abc12345
    """
    import vcmix
    import hashlib
    from vcmix.project.version_manager import ProjectVersionManager

    try:
        vm = ProjectVersionManager()
        project_name = project.stem
        project_id = hashlib.sha256(project_name.encode("utf-8")).hexdigest()[:12]
        restored = vm.restore_snapshot(
            project_id=project_id,
            snapshot_id=snapshot,
            projects_dir=project.parent,
        )
        click.secho(f"✔ Restored snapshot: {snapshot}", fg="green")
        click.echo(f"  Project: {restored}")

    except FileNotFoundError as e:
        click.secho(f"✗ Not found: {e}", fg="red")
        sys.exit(vcmix.EXIT_IO_ERROR)
    except Exception as e:
        click.secho(f"✗ Restore failed: {e}", fg="red")
        sys.exit(vcmix.EXIT_RENDER_ERROR)

