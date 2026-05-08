"""
automix.py — /api/automix endpoints for VCMix Web UI.

Auto-mixing engine that analyzes DataStream events and generates
parameter adjustment suggestions. Uses the same AutoMixer as the CLI.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Union

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from vcmix.config.parser import parse_project
from vcmix.engine.automix import AutoMixer
from vcmix.engine.renderer import Renderer

router = APIRouter()


class AutomixRequest(BaseModel):
    """Request body for auto-mixing."""
    project_path: str = Field(..., description="Path to YAML project file")
    dry_run: bool = Field(default=True, description="Show suggestions without writing")
    reference_path: Optional[str] = Field(
        default=None, description="Path to reference audio for matching"
    )


class AutomixSuggestion(BaseModel):
    """A single adjustment suggestion."""
    target: str
    action: str
    params: dict[str, Any]
    reason: str
    priority: int


class AutomixResponse(BaseModel):
    """Response for auto-mixing analysis."""
    project: str
    events_captured: int
    tracks_analyzed: int
    has_clipping: bool
    has_low_snr: bool
    has_sibilance: bool
    suggestions: list[AutomixSuggestion]
    output_path: Optional[str] = None


@router.post("/automix")
async def run_automix(request: AutomixRequest):
    """
    Run auto-mixing analysis on a project.

    Pipeline:
        1. Parse YAML project config
        2. Render with DataStream to capture events
        3. Analyze events → MixingState
        4. Generate adjustment suggestions
        5. Optionally apply suggestions to produce new config
    """
    yaml_path = Path(request.project_path)
    if not yaml_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Project file not found: {request.project_path}",
        )

    try:
        # Step 1: Parse project
        cfg = parse_project(yaml_path)
        cfg.__dict__["_project_dir"] = yaml_path.parent.resolve()

        # Step 2: Render with DataStream to capture events
        engine = Renderer(cfg, stream="dict")
        try:
            engine.run()
        except (ValueError, RuntimeError):
            pass  # May fail but still collect events
        events = engine.get_stream_events()

        # Step 3: Analyze events
        mixer = AutoMixer(sample_rate=cfg.sample_rate, bpm=cfg.bpm)
        state = mixer.analyze(events)

        # Step 4: Generate suggestions
        suggestions = mixer.suggest(state)

        # Build response
        suggestion_list = []
        for s in suggestions:
            suggestion_list.append(AutomixSuggestion(
                target=s.target,
                action=s.action,
                params=s.params,
                reason=s.reason,
                priority=s.priority,
            ))

        # Sort by priority
        suggestion_list.sort(key=lambda s: s.priority)

        # Step 5: Apply if not dry-run
        output_path = None
        if not request.dry_run:

            import yaml

            raw_config = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            new_config = mixer.apply(raw_config, suggestions)

            output_file = yaml_path.with_name(
                yaml_path.stem + "_automix" + yaml_path.suffix
            )
            with open(output_file, "w", encoding="utf-8") as f:
                yaml.dump(new_config, f, default_flow_style=False, allow_unicode=True)
            output_path = str(output_file)

        return AutomixResponse(
            project=str(yaml_path),
            events_captured=len(events),
            tracks_analyzed=len(state.tracks),
            has_clipping=state.has_clipping,
            has_low_snr=state.has_low_snr,
            has_sibilance=state.has_sibilance,
            suggestions=suggestion_list,
            output_path=output_path,
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/automix/dry-run")
async def automix_dry_run(
    project_path: str = Query(..., description="Path to YAML project file"),
):
    """Run auto-mixing in dry-run mode (suggestions only, no files written)."""
    request = AutomixRequest(project_path=project_path, dry_run=True)
    return await run_automix(request)


@router.post("/validate")
async def validate_yaml(yaml_content: str = Query(..., description="YAML content to validate")):
    """
    Validate a YAML configuration without rendering.

    Returns validation issues and project summary.
    """
    import tempfile


    try:
        # Write to temp file for validation
        tmp_dir = Path(tempfile.mkdtemp(prefix="vcmix_validate_"))
        tmp_path = tmp_dir / "validate.yaml"
        tmp_path.write_text(yaml_content, encoding="utf-8")

        cfg = parse_project(tmp_path)

        # Run validation checks (same as CLI)
        issues = _validate_config(cfg)

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "project": cfg.name,
            "tracks": len(cfg.tracks),
            "bpm": cfg.bpm,
            "sample_rate": cfg.sample_rate,
        }

    except Exception as e:
        return {"valid": False, "error": str(e)}


def _validate_config(cfg: Any) -> list[str]:
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

    track_names = {t.name for t in cfg.tracks}
    for name in cfg.master.levels:
        if name not in track_names:
            issues.append(f"Master level references unknown track: '{name}'")

    bus_names = {s.name for s in cfg.sends} if cfg.sends else set()
    for track in cfg.tracks:
        for bus_name in track.sends:
            if bus_name not in bus_names:
                issues.append(
                    f"Track '{track.name}' sends to unknown bus: '{bus_name}'"
                )

    for track in cfg.tracks:
        for effect in track.effects:
            if effect.sidechain is not None and effect.sidechain not in track_names:
                issues.append(
                    f"Track '{track.name}' effect '{effect.name}' sidechains "
                    f"from unknown track: '{effect.sidechain}'"
                )

    return issues
