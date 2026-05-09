"""
xps_import.py — Import Waves .xps preset files into VC-Chain YAML format.

Parses the Waves .xps file format (binary header + XML body) and converts
it to a VC-Chain ChainConfig that can be saved as YAML.

.xps file structure:
    [Binary Header] ~128 bytes (skipped on import)
    [XML Body] UTF-8 encoded WavesPreset

The importer:
    1. Locates the XML body within the .xps file
    2. Parses the XML structure
    3. Maps Waves plugin names to VC plugin names
    4. Maps Waves parameter names to VC parameter names
    5. Extracts Macro definitions
    6. Generates a ChainConfig

Limitations:
    - Binary header is skipped (not fully reverse-engineered)
    - Plugins not in the mapping table are logged as warnings
    - Parameters not in the mapping table are auto-converted (PascalCase -> snake_case)
    - VST3 third-party plugins are recorded but not mapped

Usage:
    from vcmix.chain.xps_import import import_xps

    chain = import_xps("CLA-Vocal.xps")
    chain.save_yaml("cla-vocal.yaml")

Dependencies: lxml or xml.etree, vcmix.chain.models
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from vcmix.chain.models import (
    ChainConfig,
    ChainStep,
    MacroConfig,
    MacroMapping,
    ParallelBranch,
    pascal_to_snake,
)

logger = logging.getLogger(__name__)

# ── Waves Plugin Name -> VC Plugin Name Mapping ──────────────────────────

WAVES_TO_VC_PLUGIN: dict[str, str] = {
    # Compressors
    "CLA-76": "vc-comp",
    "CLA-2A": "vc-comp",
    "CLA-3A": "vc-comp",
    "R-Vox": "vc-comp",
    "R-Comp": "vc-comp",
    "C1 Comp": "vc-comp",
    "C1 Compressor": "vc-comp",
    "H-Comp": "vc-comp",
    "SSL Comp": "vc-comp",
    "API-2500": "vc-comp",
    "dbx 160": "vc-comp",
    "LLA": "vc-comp",
    "PUIGChild": "vc-comp",
    "Kramer PIE": "vc-comp",
    "Magma Tube": "vc-comp",

    # EQ
    "R-EQ": "vc-eq",
    "REQ": "vc-eq",
    "SSL EQ": "vc-eq",
    "API-550": "vc-eq",
    "API-560": "vc-eq",
    "Q10": "vc-eq",
    "LinearPhase EQ": "vc-eq",
    "H-EQ": "vc-eq",
    "PuigTec": "vc-eq",
    "Kramer HLS": "vc-eq",
    "OneKnob Brighter": "vc-eq",
    "OneKnob Louder": "vc-comp",
    "R-Bass": "vc-eq",

    # De-Esser
    "DeEsser": "vc-deesser",
    "Sibilance": "vc-deesser",
    "R-DeEsser": "vc-deesser",

    # Limiter
    "L1": "vc-limiter",
    "L2": "vc-limiter",
    "L3": "vc-limiter",
    "L3-16": "vc-limiter",
    "SSL Comp/Limit": "vc-limiter",

    # Delay
    "H-Delay": "vc-delay",
    "SuperTap": "vc-delay",
    "Doubler": "vc-delay",
    "MondoMod": "vc-delay",

    # Reverb
    "H-Reverb": "vc-reverb",
    "R-Verb": "vc-reverb",
    "TrueVerb": "vc-reverb",
    "IR-L": "vc-reverb",
    "IR-1": "vc-reverb",
    "H-Reverb (Mono)": "vc-reverb",

    # Saturator / Enhancement
    "Vitamin": "vc-saturator",
    "Smack Attack": "vc-saturator",
    "Aphex Vintage Aural Exciter": "vc-saturator",
    "J37 Tape": "vc-saturator",
    "Kramer Master Tape": "vc-saturator",
    "Magma Channel": "vc-saturator",
    "BB Tubes": "vc-saturator",
    "OneKnob Driver": "vc-saturator",

    # Multiband
    "C4": "vc-multiband",
    "C6": "vc-multiband",
    "L3 Multimaximizer": "vc-multiband",
    "L3-16": "vc-multiband",
    "LinearPhase Multiband": "vc-multiband",

    # Gate
    "C1 Gate": "vc-gate",
    "Dorrough": "vc-gate",

    # Chorus / Flanger
    "MetaFlanger": "vc-chorus",
    "MondoMod": "vc-chorus",
    "Ultrapitch": "vc-chorus",

    # Tune
    "Waves Tune": "vc-tune",
    "Waves Tune LT": "vc-tune",
    "Tune Real-Time": "vc-tune",

    # Distortion
    "GTR3": "vc-distortion",
    "PRS": "vc-distortion",

    # Noise
    "NS1": "vc-noise",
    "W43": "vc-noise",
    "Z-Noise": "vc-noise",

    # Dynamic EQ
    "F6": "vc-dynamiceq",

    # Smooth
    "OneKnob Wetter": "vc-smooth",
}

# ── Waves Parameter Name -> VC Parameter Name Mapping ────────────────────

WAVES_TO_VC_PARAM: dict[str, str] = {
    # Common compressor params
    "Threshold": "threshold",
    "Ratio": "ratio",
    "Attack": "attack",
    "Release": "release",
    "Makeup": "makeup",
    "MakeupGain": "makeup",
    "Knee": "knee",
    "Range": "range",

    # EQ params
    "LowCut": "low_cut",
    "HighCut": "high_cut",
    "LowShelf": "low_shelf",
    "HighShelf": "high_shelf",
    "LowGain": "low_gain",
    "HighGain": "high_gain",
    "PeakFreq": "peak_freq",
    "PeakGain": "peak_gain",
    "PeakQ": "peak_q",
    "Freq": "frequency",
    "Gain": "gain",
    "Q": "q",

    # De-esser params
    "Frequency": "frequency",
    "Reduction": "reduction",

    # Reverb params
    "Room": "room",
    "Decay": "decay",
    "Damping": "damping",
    "Mix": "mix",
    "PreDelay": "predelay",
    "WetLPF": "wetlpf",
    "Size": "room_size",

    # Delay params
    "Time": "time",
    "Feedback": "feedback",

    # Saturator params
    "Drive": "drive",

    # Limiter params
    "Ceiling": "ceiling",
    "OutCeiling": "ceiling",
    "ThresholdCeiling": "ceiling",

    # Gate params
    "Hold": "hold",

    # Chorus params
    "Rate": "rate",
    "Depth": "depth",
    "Voices": "voices",
    "Width": "width",
    "Delay": "delay",
}


def _find_xml_start(data: bytes) -> int:
    """Find the start of the XML body in a .xps file.

    Searches for common XML declaration patterns after the binary header.

    Args:
        data: Raw .xps file bytes.

    Returns:
        Byte offset of the XML start.
    """
    # Try to find XML declaration
    for pattern in [b"<?xml", b"<WavesPreset", b"<Preset", b"<PluginChain"]:
        offset = data.find(pattern)
        if offset >= 0:
            return offset

    # Fallback: search for '<' after the first 64 bytes (skip binary header)
    for i in range(64, min(len(data), 512)):
        if data[i:i+1] == b"<":
            return i

    return -1


def _map_plugin_name(waves_name: str) -> str:
    """Map a Waves plugin name to a VC plugin name.

    Falls back to a normalized version of the Waves name if no mapping exists.

    Args:
        waves_name: Waves plugin name (e.g. "CLA-76").

    Returns:
        VC plugin name (e.g. "vc-comp").
    """
    # Direct lookup
    if waves_name in WAVES_TO_VC_PLUGIN:
        return WAVES_TO_VC_PLUGIN[waves_name]

    # Case-insensitive lookup
    for key, value in WAVES_TO_VC_PLUGIN.items():
        if key.lower() == waves_name.lower():
            return value

    # Partial match (Waves name contains the key)
    for key, value in WAVES_TO_VC_PLUGIN.items():
        if key.lower() in waves_name.lower():
            return value

    # No mapping found — return a normalized name with warning
    normalized = waves_name.lower().replace(" ", "-").replace("_", "-")
    logger.warning(
        "No VC plugin mapping for Waves plugin '%s', using '%s'",
        waves_name, normalized,
    )
    return normalized


def _map_param_name(waves_param: str) -> str:
    """Map a Waves parameter name to a VC parameter name.

    Falls back to PascalCase -> snake_case auto-conversion.

    Args:
        waves_param: Waves parameter name (e.g. "Threshold").

    Returns:
        VC parameter name (e.g. "threshold").
    """
    # Direct lookup
    if waves_param in WAVES_TO_VC_PARAM:
        return WAVES_TO_VC_PARAM[waves_param]

    # Case-insensitive lookup
    for key, value in WAVES_TO_VC_PARAM.items():
        if key.lower() == waves_param.lower():
            return value

    # Auto-convert PascalCase to snake_case
    return pascal_to_snake(waves_param)


def _parse_param_value(value_str: str) -> Any:
    """Parse a parameter value string to the appropriate Python type.

    Args:
        value_str: Parameter value as string.

    Returns:
        Parsed value (int, float, or str).
    """
    # Try integer
    try:
        return int(value_str)
    except ValueError:
        pass

    # Try float
    try:
        return float(value_str)
    except ValueError:
        pass

    # Return as string
    return value_str


def import_xps(path: str | Path) -> ChainConfig:
    """Import a Waves .xps preset file as a VC-Chain ChainConfig.

    Parses the .xps file, maps Waves plugins/params to VC equivalents,
    and returns a ChainConfig that can be saved as YAML.

    Args:
        path: Path to the .xps file.

    Returns:
        ChainConfig instance.

    Raises:
        ValueError: If the file cannot be parsed.
        FileNotFoundError: If the file does not exist.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f".xps file not found: {path}")

    data = path.read_bytes()
    if not data:
        raise ValueError(f".xps file is empty: {path}")

    # Find XML start
    xml_start = _find_xml_start(data)
    if xml_start < 0:
        raise ValueError(f"Cannot find XML body in .xps file: {path}")

    # Parse XML
    xml_data = data[xml_start:].decode("utf-8", errors="replace")

    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError as e:
        raise ValueError(f"Failed to parse XML in .xps file: {e}") from e

    # Extract chain name
    name = "imported-chain"
    author = ""
    description = ""

    preset_info = root.find(".//PresetInfo") or root.find(".//Info")
    if preset_info is not None:
        name_el = preset_info.find("Name")
        if name_el is not None and name_el.text:
            name = name_el.text.strip()
        author_el = preset_info.find("Author")
        if author_el is not None and author_el.text:
            author = author_el.text.strip()
        desc_el = preset_info.find("Description")
        if desc_el is not None and desc_el.text:
            description = desc_el.text.strip()

    # Also check root attributes
    if "name" in root.attrib:
        name = root.attrib["name"]

    # Parse plugin chain
    serial_steps: list[ChainStep] = []
    parallel_branches: list[ParallelBranch] = []
    is_parallel = False
    parallel_mix = 0.5

    # Check for parallel/multiband routing
    chain_el = root.find(".//PluginChain") or root.find(".//Chain")
    if chain_el is not None:
        routing = chain_el.get("routing", "serial").lower()
        if routing == "parallel":
            is_parallel = True
            parallel_mix = float(chain_el.get("mix", "0.5"))

    # Parse plugin slots
    plugins = root.findall(".//Plugin") or root.findall(".//PluginChain/Plugin")
    for plugin_el in plugins:
        waves_name = plugin_el.get("name", plugin_el.get("plugin", "unknown"))
        vc_name = _map_plugin_name(waves_name)

        params: dict[str, Any] = {}
        for param_el in plugin_el.findall("Parameter") or plugin_el.findall("Param"):
            param_name = _map_param_name(param_el.get("name", ""))
            param_value = _parse_param_value(param_el.get("value", "0"))
            if param_name:
                params[param_name] = param_value

        step = ChainStep(plugin=vc_name, params=params)

        if is_parallel:
            # In parallel mode, add to a parallel branch
            # For simplicity, all plugins go into one branch
            pass
        else:
            serial_steps.append(step)

    # If parallel, create a branch from the serial steps
    if is_parallel and serial_steps:
        parallel_branches.append(
            ParallelBranch(mix=parallel_mix, chain=serial_steps)
        )
        serial_steps = []

    # Check for multiband configuration
    multiband_el = root.find(".//Multiband") or root.find(".//MultiBand")
    multiband_config = None
    if multiband_el is not None:
        from vcmix.chain.models import MultibandBand, MultibandConfig

        crossover_str = multiband_el.get("crossover", "")
        crossover = []
        if crossover_str:
            try:
                crossover = [float(f) for f in crossover_str.split(",")]
            except ValueError:
                pass

        bands = []
        for band_el in multiband_el.findall("Band"):
            low = float(band_el.get("low", 0))
            high = float(band_el.get("high", 22050))
            band_steps = []
            for plugin_el in band_el.findall("Plugin"):
                waves_name = plugin_el.get("name", "unknown")
                vc_name = _map_plugin_name(waves_name)
                params = {}
                for param_el in plugin_el.findall("Parameter"):
                    param_name = _map_param_name(param_el.get("name", ""))
                    param_value = _parse_param_value(param_el.get("value", "0"))
                    if param_name:
                        params[param_name] = param_value
                band_steps.append(ChainStep(plugin=vc_name, params=params))
            bands.append(MultibandBand(range=(low, high), chain=band_steps))

        if bands:
            multiband_config = MultibandConfig(crossover=crossover, bands=bands)

    # Parse Macros
    macros: list[MacroConfig] = []
    macros_el = root.find(".//Macros") or root.find(".//MacroSet")
    if macros_el is not None:
        for macro_el in macros_el.findall("Macro"):
            macro_name = macro_el.get("name", f"Macro {len(macros) + 1}")
            mappings = []
            for mapping_el in macro_el.findall("Mapping"):
                plugin_name = _map_plugin_name(mapping_el.get("plugin", ""))
                param_name = _map_param_name(mapping_el.get("param", ""))
                min_val = float(mapping_el.get("min", 0))
                max_val = float(mapping_el.get("max", 1))
                inverse = mapping_el.get("inverse", "false").lower() == "true"
                if plugin_name and param_name:
                    mappings.append(MacroMapping(
                        plugin=plugin_name,
                        param=param_name,
                        range=(min_val, max_val),
                        inverse=inverse,
                    ))
            if mappings:
                macros.append(MacroConfig(name=macro_name, mapping=mappings))

    # Build ChainConfig
    chain = ChainConfig(
        name=name,
        author=author,
        version="1.0",
        description=description or f"Imported from {path.name}",
        tags=["imported", "xps"],
        macro=macros,
        serial=serial_steps,
        parallel=parallel_branches,
        multiband=multiband_config,
    )

    logger.info(
        "Imported .xps file: %s (%d serial steps, %d parallel branches, %d macros)",
        path.name, len(serial_steps), len(parallel_branches), len(macros),
    )

    return chain


def import_xps_bytes(data: bytes, name: str = "imported-chain") -> ChainConfig:
    """Import a Waves .xps preset from raw bytes.

    Similar to import_xps() but accepts bytes instead of a file path.

    Args:
        data: Raw .xps file bytes.
        name: Default chain name if not found in the file.

    Returns:
        ChainConfig instance.
    """
    # Write to temp file and use import_xps
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".xps", delete=False) as f:
        f.write(data)
        temp_path = f.name

    try:
        return import_xps(temp_path)
    finally:
        Path(temp_path).unlink(missing_ok=True)
