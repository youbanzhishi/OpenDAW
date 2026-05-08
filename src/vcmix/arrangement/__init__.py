"""
arrangement — Arrangement template engine for VCMix (Phase 12).

Provides pre-defined arrangement structure templates that can be applied
to generate complete VCMix YAML project configurations, including track
lists, effect chains, section markers, and automation.
"""

from vcmix.arrangement.templates import (
    TEMPLATE_REGISTRY,
    ArrangementTemplate,
    Section,
    TrackSpec,
    get_template,
    list_templates,
    list_templates_by_genre,
)

__all__ = [
    "ArrangementTemplate",
    "Section",
    "TrackSpec",
    "TEMPLATE_REGISTRY",
    "get_template",
    "list_templates",
    "list_templates_by_genre",
]
