"""
automation.py — /api/automation endpoints for VCMix Web UI (Phase 9).

Provides automation curve preview and application.
Uses the same AutomationCurve and AutomationEngine as the CLI.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from vcmix.automation.automation_curve import AutomationCurve, AutomationPoint, CurveType
from vcmix.automation.automation_engine import AutomationEngine

router = APIRouter()


# ── Models ───────────────────────────────────────────────────────────────

class AutomationPointModel(BaseModel):
    """A single automation control point."""
    time_beat: float = Field(..., description="Position in beats")
    value: float = Field(..., description="Parameter value")
    curve_type: str = Field(default="linear", description="Interpolation: step, linear, smooth")


class AutomationPreviewRequest(BaseModel):
    """Request body for automation curve preview."""
    points: list[AutomationPointModel] = Field(
        ..., description="Control points defining the automation curve"
    )
    query_beats: list[float] = Field(
        default=[], description="Beat positions to query values at"
    )
    default_value: float = Field(default=0.0, description="Default value when no points")


class AutomationApplyRequest(BaseModel):
    """Request body for applying automation to a track."""
    track_name: str = Field(..., description="Target track name")
    parameter: str = Field(..., description="Parameter key (e.g. 'gain' or 'vc-reverb.mix')")
    points: list[AutomationPointModel] = Field(..., description="Automation control points")


# ── Endpoints ────────────────────────────────────────────────────────────

@router.post("/automation/preview")
async def preview_automation_curve(request: AutomationPreviewRequest):
    """
    Preview an automation curve by returning interpolated values.

    Given a set of control points, computes the curve and optionally
    returns values at specific beat positions. Useful for the frontend
    to visualize automation before applying it.
    """
    if not request.points:
        return {
            "points": [],
            "values_at_beats": [],
            "value_range": [request.default_value, request.default_value],
            "point_count": 0,
        }

    try:
        # Build AutomationCurve from request points
        curve_points = []
        for p in request.points:
            curve_type = CurveType(p.curve_type)
            curve_points.append(AutomationPoint(
                time_beat=p.time_beat,
                value=p.value,
                curve_type=curve_type,
            ))

        curve = AutomationCurve(points=curve_points, default_value=request.default_value)

        # Serialize the curve points
        serialized_points = curve.to_list()

        # Query values at requested beats
        values_at_beats = []
        if request.query_beats:
            for beat in sorted(request.query_beats):
                values_at_beats.append({
                    "beat": beat,
                    "value": curve.value_at(beat),
                })

        return {
            "points": serialized_points,
            "point_count": curve.point_count,
            "value_range": list(curve.value_range),
            "start_beat": curve.start_beat,
            "end_beat": curve.end_beat,
            "values_at_beats": values_at_beats,
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Preview error: {e}")


@router.post("/automation/apply")
async def apply_automation(request: AutomationApplyRequest):
    """
    Apply an automation curve to a track parameter.

    Returns the automation definition that would be added to the
    track's YAML config under the 'automation' key.
    """
    if not request.points:
        raise HTTPException(status_code=400, detail="No automation points provided")

    try:
        # Build the curve
        curve_points = []
        for p in request.points:
            curve_type = CurveType(p.curve_type)
            curve_points.append(AutomationPoint(
                time_beat=p.time_beat,
                value=p.value,
                curve_type=curve_type,
            ))

        curve = AutomationCurve(points=curve_points)

        # Build the automation YAML snippet
        automation_entry = {
            request.parameter: curve.to_list(),
        }

        return {
            "track_name": request.track_name,
            "parameter": request.parameter,
            "automation": automation_entry,
            "point_count": curve.point_count,
            "value_range": list(curve.value_range),
            "applied": True,
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Apply error: {e}")
