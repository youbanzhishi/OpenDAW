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
@click.option("--arrangement-aware", is_flag=True, help="Apply arrangement-aware mixing (Phase 7)")
def render(project: Path, report: bool, auto_fix: bool, stream: str, ab: bool, diff: bool, arrangement_aware: bool) -> None:
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
        if arrangement_aware:
            engine.arrangement_aware = True
            click.secho("  Arrangement-aware mixing enabled", fg="cyan")
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
    import numpy as np

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
    import numpy as np

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
    import numpy as np
    import yaml

    from vcmix.config.parser import parse_project
    from vcmix.engine.renderer import Renderer
    from vcmix.engine.automix import AutoMixer
    from vcmix.engine.reference_matcher import ReferenceMatcher
    from vcmix.audio.io import read_audio

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
    from vcmix.config.parser import parse_project
    import yaml as _yaml

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


if __name__ == "__main__":
    main()


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
    from vcmix.separation.arrangement import ArrangementExtractor
    from vcmix.engine.arrangement_strategy import ArrangementStrategy, SectionMixParams

    cfg = parse_project(project)

    # Extract arrangement from audio if available
    extractor = ArrangementExtractor(bpm=cfg.bpm)
    sections = []
    for track in cfg.tracks:
        if track.file and track.file.exists():
            try:
                sections = extractor.extract(track.file)
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
            data = [{"type": s.section_type, "start_beat": s.start_beat,
                      "end_beat": s.end_beat, "confidence": s.confidence}
                     for s in sections]
            click.echo(json_mod.dumps(data, indent=2))
        else:
            click.secho("╔══════════════════════════════════════╗", fg="cyan")
            click.secho("║     Arrangement Analysis            ║", fg="cyan")
            click.secho("╚══════════════════════════════════════╝", fg="cyan")
            for s in sections:
                bar = "█" * int(s.confidence * 20)
                click.echo(f"  {s.section_type:>8s}  beats {s.start_beat:5.1f}-{s.end_beat:5.1f}  [{bar}] {s.confidence:.0%}")
        return

    # Show mixing strategy
    strat = ArrangementStrategy.from_sections(sections, bpm=cfg.bpm)

    if as_json:
        result = []
        for s in sections:
            params = strat.get_params_at_beat(s.start_beat)
            result.append({
                "section": s.section_type,
                "start_beat": s.start_beat,
                "end_beat": s.end_beat,
                "strategy": {
                    "reverb_mix": params.reverb_mix,
                    "delay_mix": params.delay_mix,
                    "compression_ratio": params.compression_ratio,
                    "gain_offset_db": params.gain_offset_db,
                    "crossfade_beats": params.crossfade_beats,
                }
            })
        click.echo(json_mod.dumps(result, indent=2))
    else:
        click.secho("╔══════════════════════════════════════╗", fg="cyan")
        click.secho("║   Arrangement Mixing Strategy       ║", fg="cyan")
        click.secho("╚══════════════════════════════════════╝", fg="cyan")
        click.echo(f"  {'Section':>8s}  {'Beats':>12s}  {'Reverb':>6s}  {'Delay':>5s}  {'Comp':>4s}  {'Gain':>5s}")
        click.echo("  " + "─" * 52)
        for s in sections:
            params = strat.get_params_at_beat(s.start_beat)
            click.echo(f"  {s.section_type:>8s}  {s.start_beat:5.1f}-{s.end_beat:<5.1f}  "
                       f"{params.reverb_mix:5.1f}%  {params.delay_mix:4.1f}%  "
                       f"{params.compression_ratio:3.1f}:1  {params.gain_offset_db:+4.1f}dB")

        # YAML overrides
        overrides = strat.to_yaml_overrides()
        if overrides:
            click.echo()
            click.secho("YAML Overrides:", fg="yellow")
            import yaml
            click.echo(yaml.dump(overrides, default_flow_style=False))
