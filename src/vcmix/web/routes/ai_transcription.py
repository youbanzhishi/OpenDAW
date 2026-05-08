"""
ai_transcription.py — AI Agent API endpoints for transcription,
style matching, style transfer, and remix (Phase 17).

Endpoints:
    POST /api/v1/ai/transcribe    — AI扒带
    POST /api/v1/ai/style-match   — Reference style matching
    POST /api/v1/ai/style-transfer — Style transfer
    POST /api/v1/ai/remix         — One-click Remix
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()


# ── Request/Response models ─────────────────────────────────────────────

class TranscribeRequest(BaseModel):
    """Request body for AI transcription."""
    reference_path: str = Field(..., description="Path to reference audio file")
    output_dir: Optional[str] = Field(default=None, description="Output directory")


class TranscribeResponse(BaseModel):
    """Response for AI transcription."""
    project_yaml: str = ""
    stems: dict[str, str] = {}
    bpm: float = 0.0
    key: str = ""
    scale_type: str = ""
    stem_analyses: dict[str, Any] = {}
    arrangement_sections: int = 0
    status: str = "success"
    time_sec: float = 0.0


class StyleMatchRequest(BaseModel):
    """Request body for style matching."""
    reference_path: str = Field(..., description="Path to reference audio file")


class StyleMatchResponse(BaseModel):
    """Response for style matching."""
    genre: str = ""
    bpm: float = 0.0
    key: str = ""
    scale_type: str = ""
    recommended_template: str = ""
    template_score: float = 0.0
    recommended_preset: str = ""
    style_parameters: dict[str, Any] = {}
    status: str = "success"
    time_sec: float = 0.0


class StyleTransferRequest(BaseModel):
    """Request body for style transfer."""
    reference_path: str = Field(..., description="Path to reference audio file")
    project_path: str = Field(..., description="Path to target project YAML")
    output_path: Optional[str] = Field(default=None, description="Output YAML path")


class StyleTransferResponse(BaseModel):
    """Response for style transfer."""
    output_yaml: str = ""
    eq_transfers: dict[str, Any] = {}
    comp_transfers: dict[str, Any] = {}
    reverb_transfers: dict[str, Any] = {}
    gain_adjustments: dict[str, float] = {}
    status: str = "success"
    time_sec: float = 0.0


class RemixRequest(BaseModel):
    """Request body for one-click remix."""
    reference_path: str = Field(..., description="Path to reference audio file")
    new_stems: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of stem names to audio file paths"
    )
    genre: Optional[str] = Field(default=None, description="Override genre")
    bpm: Optional[float] = Field(default=None, description="Override BPM")
    output_dir: Optional[str] = Field(default=None, description="Output directory")


class RemixResponse(BaseModel):
    """Response for one-click remix."""
    output_yaml: str = ""
    replaced_stems: list[str] = []
    kept_stems: list[str] = []
    final_config_keys: list[str] = []
    status: str = "success"
    time_sec: float = 0.0


# ── Endpoints ───────────────────────────────────────────────────────────

@router.post("/ai/transcribe", response_model=TranscribeResponse)
async def transcribe(request: TranscribeRequest):
    """AI transcription —扒带 reference track into editable VCMix project."""
    ref_path = Path(request.reference_path)
    if not ref_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Reference file not found: {request.reference_path}",
        )

    try:
        from vcmix.ai.transcription import AITranscription

        output_dir = request.output_dir or str(ref_path.parent / f"transcription_{ref_path.stem}")
        transcriber = AITranscription()
        result = transcriber.transcribe(str(ref_path), output_dir)

        return TranscribeResponse(
            project_yaml=result.project_yaml,
            stems=result.stems,
            bpm=result.bpm_info.bpm,
            key=result.key_info.root,
            scale_type=result.key_info.scale_type,
            stem_analyses=result.stem_analyses,
            arrangement_sections=len(result.arrangement.get("sections", [])),
            status=result.status,
            time_sec=round(result.transcription_time_sec, 3),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ai/style-match", response_model=StyleMatchResponse)
async def style_match(request: StyleMatchRequest):
    """Reference style matching — recommend template and preset."""
    ref_path = Path(request.reference_path)
    if not ref_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Reference file not found: {request.reference_path}",
        )

    try:
        from vcmix.ai.reference_matcher_v2 import ReferenceMatcherV2

        matcher = ReferenceMatcherV2()
        result = matcher.match_style(reference_path=str(ref_path))

        return StyleMatchResponse(
            genre=result.features.genre,
            bpm=result.features.bpm,
            key=result.features.key,
            scale_type=result.features.scale_type,
            recommended_template=result.recommended_template.template_name,
            template_score=result.recommended_template.match_score,
            recommended_preset=result.recommended_mix_preset.preset_name,
            style_parameters=result.style_parameters,
            status="success",
            time_sec=round(result.match_time_sec, 3),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ai/style-transfer", response_model=StyleTransferResponse)
async def style_transfer(request: StyleTransferRequest):
    """Style transfer — apply reference mixing style to target project."""
    ref_path = Path(request.reference_path)
    project_path = Path(request.project_path)

    if not ref_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Reference file not found: {request.reference_path}",
        )
    if not project_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Project file not found: {request.project_path}",
        )

    try:
        from vcmix.ai.style_transfer import StyleTransfer

        output_path = request.output_path or str(
            project_path.parent / f"{project_path.stem}_styled.yaml"
        )

        st = StyleTransfer()
        result = st.transfer(
            reference_path=str(ref_path),
            project_yaml=str(project_path),
            output_yaml=output_path,
        )

        return StyleTransferResponse(
            output_yaml=result.output_yaml,
            eq_transfers=result.eq_transfers,
            comp_transfers=result.comp_transfers,
            reverb_transfers=result.reverb_transfers,
            gain_adjustments=result.gain_adjustments,
            status=result.status,
            time_sec=round(result.transfer_time_sec, 3),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ai/remix", response_model=RemixResponse)
async def remix(request: RemixRequest):
    """One-click remix — blend reference style with new stems."""
    ref_path = Path(request.reference_path)
    if not ref_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Reference file not found: {request.reference_path}",
        )

    try:
        from vcmix.ai.remix import RemixEngine

        output_dir = request.output_dir or str(ref_path.parent / f"remix_{ref_path.stem}")
        engine = RemixEngine()
        result = engine.remix(
            reference_path=str(ref_path),
            new_stems=request.new_stems,
            genre=request.genre,
            bpm=request.bpm,
            output_dir=output_dir,
        )

        return RemixResponse(
            output_yaml=result.output_yaml,
            replaced_stems=result.replaced_stems,
            kept_stems=result.kept_stems,
            final_config_keys=list(result.final_config.keys()) if result.final_config else [],
            status=result.status,
            time_sec=round(result.remix_time_sec, 3),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
