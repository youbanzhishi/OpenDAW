"""
xps_export.py — Export VC-Chain YAML configurations to Waves .xps format.

Converts a VC-Chain ChainConfig to a .xps file that can be loaded in
Waves StudioRack. The export is best-effort since the .xps format is
proprietary and not fully reverse-engineered.

.xps file structure:
    [Binary Header] Fixed template (~128 bytes)
    [XML Body] UTF-8 encoded WavesPreset

The exporter:
    1. Maps VC plugin names to Waves plugin names
    2. Maps VC parameter names to Waves parameter names
    3. Generates the XML body
    4. Prepends a minimal binary header
    5. Writes the .xps file

Limitations:
    - Only serial chains can be exported with full fidelity
    - Parallel chains use StudioRack's parallel split rack format
    - Multiband chains use StudioRack's multiband split format
    - VC plugins not in the mapping table are exported with generic names
    - Parameters not in the mapping table are auto-converted (snake_case -> PascalCase)

Usage:
    from vcmix.chain.xps_export import export_xps
    from vcmix.chain.models import ChainConfig

    chain = ChainConfig.from_yaml_file("cla-vocal.yaml")
    export_xps(chain, "cla-vocal.xps")

Dependencies: vcmix.chain.models
"""

from __future__ import annotations

import logging
import re
import struct
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

from vcmix.chain.models import ChainConfig, ChainStep, ParallelBranch

logger = logging.getLogger(__name__)

# ── VC Plugin Name -> Waves Plugin Name Mapping ──────────────────────────

VC_TO_WAVES_PLUGIN: dict[str, str] = {
    "vc-comp": "C1 Comp",
    "vc-eq": "R-EQ",
    "vc-deesser": "DeEsser",
    "vc-limiter": "L2",
    "vc-delay": "H-Delay",
    "vc-reverb": "H-Reverb",
    "vc-saturator": "Vitamin",
    "vc-multiband": "C4",
    "vc-gate": "C1 Gate",
    "vc-chorus": "MetaFlanger",
    "vc-tune": "Waves Tune",
    "vc-distortion": "GTR3",
    "vc-noise": "NS1",
    "vc-dynamiceq": "F6",
    "vc-smooth": "OneKnob Wetter",
    "vc-gain": "C1 Comp",  # Use comp with ratio=1 for gain
    "vc-stereo": "S1",  # Stereo imager
    "vc-pitchshift": "Waves Tune",
    "vc-harmonizer": "Waves Tune",
}

# ── VC Parameter Name -> Waves Parameter Name Mapping ────────────────────

VC_TO_WAVES_PARAM: dict[str, str] = {
    "threshold": "Threshold",
    "ratio": "Ratio",
    "attack": "Attack",
    "release": "Release",
    "makeup": "MakeupGain",
    "knee": "Knee",
    "range": "Range",
    "low_cut": "LowCut",
    "high_cut": "HighCut",
    "low_shelf": "LowShelf",
    "high_shelf": "HighShelf",
    "low_gain": "LowGain",
    "high_gain": "HighGain",
    "peak_freq": "PeakFreq",
    "peak_gain": "PeakGain",
    "peak_q": "PeakQ",
    "frequency": "Frequency",
    "gain": "Gain",
    "q": "Q",
    "reduction": "Reduction",
    "room": "Room",
    "room_size": "Size",
    "decay": "Decay",
    "damping": "Damping",
    "mix": "Mix",
    "wet": "Mix",
    "predelay": "PreDelay",
    "wetlpf": "WetLPF",
    "time": "Time",
    "feedback": "Feedback",
    "drive": "Drive",
    "ceiling": "Ceiling",
    "hold": "Hold",
    "rate": "Rate",
    "depth": "Depth",
    "voices": "Voices",
    "width": "Width",
    "delay": "Delay",
}

# ── Binary Header Template ───────────────────────────────────────────────

# Minimal binary header for .xps compatibility
# This is a best-effort template based on observed .xps file patterns.
# StudioRack may reject files with incorrect headers — the XML body
# is the primary content.

_XPS_HEADER_MAGIC = b"WAVS"  # Not the actual magic, but a placeholder
_XPS_HEADER_VERSION = 1


def _map_plugin_name_vc_to_waves(vc_name: str) -> str:
    """Map a VC plugin name to a Waves plugin name.

    Falls back to a capitalized version of the VC name if no mapping exists.

    Args:
        vc_name: VC plugin name (e.g. "vc-comp").

    Returns:
        Waves plugin name (e.g. "C1 Comp").
    """
    if vc_name in VC_TO_WAVES_PLUGIN:
        return VC_TO_WAVES_PLUGIN[vc_name]

    # No mapping found — generate a generic name
    # Strip "vc-" prefix and capitalize
    generic = vc_name.replace("vc-", "").title()
    logger.warning(
        "No Waves plugin mapping for VC plugin '%s', using '%s'",
        vc_name, generic,
    )
    return generic


def _map_param_name_vc_to_waves(vc_param: str) -> str:
    """Map a VC parameter name to a Waves parameter name.

    Falls back to snake_case -> PascalCase auto-conversion.

    Args:
        vc_param: VC parameter name (e.g. "threshold").

    Returns:
        Waves parameter name (e.g. "Threshold").
    """
    if vc_param in VC_TO_WAVES_PARAM:
        return VC_TO_WAVES_PARAM[vc_param]

    # Auto-convert snake_case to PascalCase
    return _snake_to_pascal(vc_param)


def _snake_to_pascal(name: str) -> str:
    """Convert snake_case to PascalCase.

    Examples:
        threshold -> Threshold
        high_gain -> HighGain
        attack_time -> AttackTime
    """
    return "".join(word.capitalize() for word in name.split("_") if word)


def _build_xml(chain: ChainConfig) -> str:
    """Build the XML body for a .xps file.

    Args:
        chain: ChainConfig to export.

    Returns:
        Pretty-printed XML string.
    """
    root = Element("WavesPreset")
    root.set("version", "1.0")

    # PresetInfo
    info = SubElement(root, "PresetInfo")
    name_el = SubElement(info, "Name")
    name_el.text = chain.name
    if chain.author:
        author_el = SubElement(info, "Author")
        author_el.text = chain.author
    if chain.description:
        desc_el = SubElement(info, "Description")
        desc_el.text = chain.description

    # PluginChain
    chain_el = SubElement(root, "PluginChain")

    # Serial steps
    slot = 1
    for step in chain.serial:
        plugin_el = SubElement(chain_el, "Plugin")
        plugin_el.set("slot", str(slot))
        plugin_el.set("name", _map_plugin_name_vc_to_waves(step.plugin))

        for param_name, param_value in step.params.items():
            param_el = SubElement(plugin_el, "Parameter")
            param_el.set("name", _map_param_name_vc_to_waves(param_name))
            param_el.set("value", str(param_value))

        slot += 1

    # Parallel branches
    for branch in chain.parallel:
        split_el = SubElement(chain_el, "ParallelSplit")
        split_el.set("mix", str(branch.mix))

        for step in branch.chain:
            plugin_el = SubElement(split_el, "Plugin")
            plugin_el.set("slot", str(slot))
            plugin_el.set("name", _map_plugin_name_vc_to_waves(step.plugin))

            for param_name, param_value in step.params.items():
                param_el = SubElement(plugin_el, "Parameter")
                param_el.set("name", _map_param_name_vc_to_waves(param_name))
                param_el.set("value", str(param_value))

            slot += 1

    # Multiband
    if chain.multiband and chain.multiband.bands:
        mb_el = SubElement(root, "Multiband")
        if chain.multiband.crossover:
            mb_el.set("crossover", ",".join(str(f) for f in chain.multiband.crossover))

        for i, band in enumerate(chain.multiband.bands):
            band_el = SubElement(mb_el, "Band")
            band_el.set("index", str(i))
            band_el.set("low", str(band.range[0]))
            band_el.set("high", str(band.range[1]))

            for step in band.chain:
                plugin_el = SubElement(band_el, "Plugin")
                plugin_el.set("slot", str(slot))
                plugin_el.set("name", _map_plugin_name_vc_to_waves(step.plugin))

                for param_name, param_value in step.params.items():
                    param_el = SubElement(plugin_el, "Parameter")
                    param_el.set("name", _map_param_name_vc_to_waves(param_name))
                    param_el.set("value", str(param_value))

                slot += 1

    # Macros
    if chain.macro:
        macros_el = SubElement(root, "Macros")
        for i, macro in enumerate(chain.macro):
            macro_el = SubElement(macros_el, "Macro")
            macro_el.set("index", str(i + 1))
            macro_el.set("name", macro.name)

            for mapping in macro.mapping:
                mapping_el = SubElement(macro_el, "Mapping")
                mapping_el.set("plugin", _map_plugin_name_vc_to_waves(mapping.plugin))
                mapping_el.set("param", _map_param_name_vc_to_waves(mapping.param))
                mapping_el.set("min", str(mapping.range[0]))
                mapping_el.set("max", str(mapping.range[1]))
                if mapping.inverse:
                    mapping_el.set("inverse", "true")

    # Tags
    if chain.tags:
        tags_el = SubElement(info, "Tags")
        tags_el.text = ",".join(chain.tags)

    # Pretty-print
    xml_bytes = tostring(root, encoding="unicode", xml_declaration=True)
    dom = minidom.parseString(xml_bytes)
    return dom.toprettyxml(indent="  ", encoding=None)


def _build_header() -> bytes:
    """Build a minimal binary header for .xps compatibility.

    Returns:
        Binary header bytes.
    """
    header = bytearray(128)
    # Magic bytes (placeholder — real format may differ)
    header[0:4] = b"\x00\x00\x00\x00"
    # Version
    struct.pack_into("<I", header, 4, _XPS_HEADER_VERSION)
    # Header size
    struct.pack_into("<I", header, 8, 128)
    # Rest is zeros (padding)
    return bytes(header)


def export_xps(chain: ChainConfig, path: str | Path) -> Path:
    """Export a VC-Chain ChainConfig as a Waves .xps file.

    Generates a .xps file with binary header + XML body.

    Args:
        chain: ChainConfig to export.
        path: Output file path.

    Returns:
        Path to the exported .xps file.

    Note:
        The exported .xps file may not be fully compatible with all
        versions of Waves StudioRack due to the proprietary binary header
        format. The XML body contains all chain information.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Build XML body
    xml_body = _build_xml(chain)

    # Build binary header
    header = _build_header()

    # Write file
    with open(path, "wb") as f:
        f.write(header)
        f.write(xml_body.encode("utf-8"))

    logger.info(
        "Exported .xps file: %s (%d serial steps, %d parallel branches, %d macros)",
        path.name, len(chain.serial), len(chain.parallel), len(chain.macro),
    )

    return path


def export_xps_bytes(chain: ChainConfig) -> bytes:
    """Export a VC-Chain ChainConfig as .xps file bytes.

    Similar to export_xps() but returns bytes instead of writing to a file.

    Args:
        chain: ChainConfig to export.

    Returns:
        Raw .xps file bytes.
    """
    xml_body = _build_xml(chain)
    header = _build_header()
    return header + xml_body.encode("utf-8")
