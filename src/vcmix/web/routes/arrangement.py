"""
arrangement.py — /api/arrangement endpoints for VCMix Web UI.

Provides arrangement analysis and mixing strategy generation.
Uses the same ArrangementExtractor and ArrangementStrategy as the CLI.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from vcmix.config.parser import parse_project
from vcmix.separation.arrangement import ArrangementExtractor, Section
from vcmix.engine.arrangement_strategy import ArrangementStrategy

router = APIRouter()


class ArrangementResponse(BaseModel):
    """Response for arrangement analysis."""
    sections: list[dict[str, Any]]
    section_count: int
    total_beats: int


class StrategyResponse(BaseModel):
    """Response for arrangement strategy."""
    strategy: dict[str, Any]
    yaml_overrides: str


@router.get("/arrangement")
async def analyze_arrangement(
    project_path: str = Query(..., description="Path to YAML project file"),
):
    """
    Analyze arrangement structure of a project.

    Returns section information (intro/verse/chorus/bridge/outro) with
    beat positions and energy levels.
    """
    yaml_path = Path(project_path)
    if not yaml_path.exists():
        raise HTTPException(status_code=404, detail=f"Project file not found: {project_path}")

    try:
        cfg = parse_project(yaml_path)

        # Try to use stems from the project if available
        stems = getattr(cfg, "_stems", None)
        if stems and len(stems) > 0:
            extractor = ArrangementExtractor()
            sections = extractor.extract(stems, cfg.sample_rate, cfg.bpm)
        else:
            sections = _create_default_sections(cfg)

        section_list = []
        for sec in sections:
            section_list.append({
                "name": sec.name,
                "start_beat": sec.start_beat,
                "end_beat": sec.end_beat,
                "start_sec": round(sec.start_sec, 2),
                "end_sec": round(sec.end_sec, 2),
                "energy_level": sec.energy_level,
                "active_stems": sec.active_stems,
            })

        total_beats = max((s.end_beat for s in sections), default=0)

        return ArrangementResponse(
            sections=section_list,
            section_count=len(section_list),
            total_beats=total_beats,
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/arrangement/strategy")
async def get_arrangement_strategy(
    project_path: str = Query(..., description="Path to YAML project file"),
):
    """
    Get arrangement-aware mixing strategy for a project.

    Returns per-section effect parameter overrides and YAML export.
    """
    yaml_path = Path(project_path)
    if not yaml_path.exists():
        raise HTTPException(status_code=404, detail=f"Project file not found: {project_path}")

    try:
        cfg = parse_project(yaml_path)

        stems = getattr(cfg, "_stems", None)
        if stems and len(stems) > 0:
            extractor = ArrangementExtractor()
            sections = extractor.extract(stems, cfg.sample_rate, cfg.bpm)
        else:
            sections = _create_default_sections(cfg)

        if not sections:
            return StrategyResponse(
                strategy={"sections": []},
                yaml_overrides="",
            )

        strategy = ArrangementStrategy.from_sections(sections)

        # Build strategy dict
        strategy_data = {}
        for i, sec_params in enumerate(strategy.sections):
            start_beat = strategy._find_start_beat(i)
            strategy_data[f"section_{i}_{sec_params.section_name}"] = {
                "start_beat": start_beat,
                "section_name": sec_params.section_name,
                "reverb_mix": round(sec_params.reverb_mix, 4),
                "delay_mix": round(sec_params.delay_mix, 4),
                "compression_ratio": sec_params.compression_ratio,
                "gain_db": sec_params.gain_db,
                "crossfade_beats": sec_params.crossfade_beats,
            }

        yaml_overrides = strategy.to_yaml_overrides()

        return StrategyResponse(
            strategy=strategy_data,
            yaml_overrides=yaml_overrides,
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Helpers ──────────────────────────────────────────────────────────────

def _create_default_sections(cfg: Any) -> list[Section]:
    """Create default sections from project config when no stems available."""
    import soundfile

    project_dir = getattr(cfg, "_project_dir", Path("."))
    total_duration = 0.0

    for track in cfg.tracks:
        track_path = project_dir / track.file
        try:
            info = soundfile.info(str(track_path))
            total_duration = max(total_duration, info.duration)
        except Exception:
            pass

    if total_duration <= 0:
        total_duration = 180.0

    beat_sec = 60.0 / cfg.bpm if cfg.bpm > 0 else 0.5
    total_beats = int(total_duration / beat_sec)

    sections_def = [
        ("intro", 0, min(8, total_beats // 6)),
        ("verse", min(8, total_beats // 6), min(24, total_beats // 2)),
        ("chorus", min(24, total_beats // 2), min(40, total_beats * 2 // 3)),
        ("bridge", min(40, total_beats * 2 // 3), min(48, total_beats * 5 // 6)),
        ("outro", min(48, total_beats * 5 // 6), total_beats),
    ]

    result = []
    for name, start, end in sections_def:
        if end > start:
            result.append(Section(
                name=name,
                start_beat=start,
                end_beat=end,
                start_sec=start * beat_sec,
                end_sec=end * beat_sec,
                active_stems=[],
                energy_level="medium",
            ))

    return result
