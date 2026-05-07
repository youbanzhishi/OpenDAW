"""
automation — Parameter automation curves for VCMix.

Supports time-varying parameter control (volume fades, filter sweeps, etc.)
with step, linear, and smooth interpolation modes.

Usage:
    from vcmix.automation.automation_curve import AutomationCurve, AutomationPoint
    from vcmix.automation.automation_engine import AutomationEngine
"""
from vcmix.automation.automation_curve import AutomationCurve, AutomationPoint
from vcmix.automation.automation_engine import AutomationEngine

__all__ = ["AutomationCurve", "AutomationPoint", "AutomationEngine"]
