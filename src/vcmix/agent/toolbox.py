"""
toolbox.py — VCMix Agent Tool definitions and executor (Phase 22a).

Defines 20 tools that map directly to VCMix REST API endpoints.
ToolExecutor translates tool calls into HTTP requests against the local API.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger("vcmix.agent.toolbox")

# ── 20 Agent Tool Definitions ────────────────────────────────────────────
# Each tool defines name, description, and parameter schema following
# OpenAI function-calling format. Parameters are aligned with the
# actual VCMix API endpoints.

AGENT_TOOLS: list[dict[str, Any]] = [
    {
        "name": "analyze_project",
        "description": "Analyze a project's audio characteristics: loudness, spectral balance, dynamics, and problem diagnosis for all tracks.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID to analyze"},
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "list_plugins",
        "description": "List all available VCMix plugins (vc-eq, vc-comp, vc-reverb, etc.) and their parameters.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "add_effect",
        "description": "Add an effect plugin to a track. Example: add vc-eq to the vocal track.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID"},
                "track_name": {"type": "string", "description": "Track name (e.g. 'vocal')"},
                "effect_name": {"type": "string", "description": "Plugin name (e.g. 'vc-eq', 'vc-comp', 'vc-reverb')"},
                "params": {"type": "object", "description": "Initial plugin parameters", "default": {}},
            },
            "required": ["project_id", "track_name", "effect_name"],
        },
    },
    {
        "name": "update_effect",
        "description": "Update effect parameters on a track. Example: change vc-eq high_shelf to +3dB on vocal.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID"},
                "track_name": {"type": "string", "description": "Track name"},
                "effect_index": {"type": "integer", "description": "0-based effect index on the track"},
                "params": {"type": "object", "description": "Updated plugin parameters"},
            },
            "required": ["project_id", "track_name", "effect_index", "params"],
        },
    },
    {
        "name": "remove_effect",
        "description": "Remove an effect from a track by index.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID"},
                "track_name": {"type": "string", "description": "Track name"},
                "effect_index": {"type": "integer", "description": "0-based effect index to remove"},
            },
            "required": ["project_id", "track_name", "effect_index"],
        },
    },
    {
        "name": "get_project",
        "description": "Get full project details: tracks, effects, master settings, BPM, sample rate.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID"},
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "render_project",
        "description": "Trigger a render for a project. Returns job ID for status tracking.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID"},
                "report": {"type": "boolean", "description": "Generate analysis report", "default": False},
                "auto_fix": {"type": "boolean", "description": "Enable auto-fix", "default": False},
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "ai_auto_mix",
        "description": "Run AI auto-mixing on a project. Analyzes and adjusts levels, EQ, compression, and spatial balance.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID"},
                "mode": {"type": "string", "enum": ["step", "one_click"], "description": "Step-by-step or one-click mode", "default": "step"},
                "apply": {"type": "boolean", "description": "Auto-apply suggestions", "default": False},
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "ai_master",
        "description": "Run AI mastering on a project. Optimizes loudness, stereo width, and final polish.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID"},
                "mode": {"type": "string", "enum": ["step", "one_click"], "description": "Step-by-step or one-click mode", "default": "step"},
                "apply": {"type": "boolean", "description": "Auto-apply suggestions", "default": False},
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "get_waveform",
        "description": "Get waveform peak data for a track. Useful for visualizing audio levels.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID"},
                "track_name": {"type": "string", "description": "Track name"},
            },
            "required": ["project_id", "track_name"],
        },
    },
    {
        "name": "get_spectrum",
        "description": "Get FFT spectrum data for a track. Essential for diagnosing frequency problems.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID"},
                "track_name": {"type": "string", "description": "Track name"},
            },
            "required": ["project_id", "track_name"],
        },
    },
    {
        "name": "add_track",
        "description": "Add a new track to the project. Specify name, file, type, and optional effects.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID"},
                "name": {"type": "string", "description": "Track name (e.g. 'vocal', 'guitar')"},
                "file": {"type": "string", "description": "Audio file path", "default": ""},
                "type": {"type": "string", "enum": ["audio", "midi", "vst3", "sampler"], "description": "Track type", "default": "audio"},
                "volume": {"type": "number", "description": "Initial volume (0.0-2.0)", "default": 1.0},
            },
            "required": ["project_id", "name"],
        },
    },
    {
        "name": "update_track",
        "description": "Update track properties: volume, mute, solo.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID"},
                "track_name": {"type": "string", "description": "Track name"},
                "volume": {"type": "number", "description": "Volume level (0.0-2.0)"},
                "mute": {"type": "boolean", "description": "Mute the track"},
                "solo": {"type": "boolean", "description": "Solo the track"},
            },
            "required": ["project_id", "track_name"],
        },
    },
    {
        "name": "remove_track",
        "description": "Remove a track from the project.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID"},
                "track_name": {"type": "string", "description": "Track name to remove"},
            },
            "required": ["project_id", "track_name"],
        },
    },
    {
        "name": "validate_project",
        "description": "Validate a project's configuration. Checks YAML syntax, file existence, plugin parameters.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID to validate"},
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "get_presets",
        "description": "List available effect chain presets and mix presets.",
        "parameters": {
            "type": "object",
            "properties": {
                "preset_type": {"type": "string", "enum": ["chains", "mix", "arrangement"], "description": "Type of presets to list", "default": "chains"},
            },
        },
    },
    {
        "name": "apply_preset",
        "description": "Apply a preset to a track or project. Chain presets go to tracks, mix presets to the whole project.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID"},
                "preset_name": {"type": "string", "description": "Preset key name"},
                "track_name": {"type": "string", "description": "Target track name (for chain presets)", "default": ""},
            },
            "required": ["project_id", "preset_name"],
        },
    },
    {
        "name": "ai_compose",
        "description": "AI composition engine — generate a complete arrangement with chords, melody, drums, and bass.",
        "parameters": {
            "type": "object",
            "properties": {
                "genre": {"type": "string", "description": "Genre: pop/rock/edm/hiphop/rnb/ballad", "default": "pop"},
                "duration": {"type": "number", "description": "Target duration in seconds", "default": 180.0},
                "bpm": {"type": "number", "description": "Tempo in BPM", "default": 120.0},
                "key": {"type": "string", "description": "Musical key (e.g. C, Am, D Major)", "default": "C"},
                "mood": {"type": "string", "description": "Mood: happy/sad/energetic/calm/dark/bright", "default": "happy"},
            },
        },
    },
    {
        "name": "create_snapshot",
        "description": "Create a snapshot of the project's current state for version control and rollback.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID"},
                "label": {"type": "string", "description": "Optional snapshot label", "default": ""},
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "export_stems",
        "description": "Export individual track stems for external mixing or collaboration.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID"},
                "format": {"type": "string", "enum": ["wav", "flac", "mp3"], "description": "Export format", "default": "wav"},
            },
            "required": ["project_id"],
        },
    },
]


# ── Tool name → API route mapping ────────────────────────────────────────

_TOOL_ROUTE_MAP: dict[str, dict[str, str]] = {
    "analyze_project":   {"method": "GET",  "path": "/projects/{project_id}/analysis"},
    "list_plugins":      {"method": "GET",  "path": "/plugins"},
    "add_effect":        {"method": "POST", "path": "/projects/{project_id}/tracks/{track_name}/effects"},
    "update_effect":     {"method": "PUT",  "path": "/projects/{project_id}/tracks/{track_name}/effects/{effect_index}"},
    "remove_effect":     {"method": "DELETE", "path": "/projects/{project_id}/tracks/{track_name}/effects/{effect_index}"},
    "get_project":       {"method": "GET",  "path": "/projects/{project_id}"},
    "render_project":    {"method": "POST", "path": "/projects/{project_id}/render"},
    "ai_auto_mix":       {"method": "POST", "path": "/ai/mix"},
    "ai_master":         {"method": "POST", "path": "/ai/master"},
    "get_waveform":      {"method": "GET",  "path": "/waveform/{project_id}/{track_name}"},
    "get_spectrum":      {"method": "GET",  "path": "/spectrum/{project_id}/{track_name}"},
    "add_track":         {"method": "POST", "path": "/projects/{project_id}/tracks"},
    "update_track":      {"method": "PUT",  "path": "/projects/{project_id}/tracks/{track_name}"},
    "remove_track":      {"method": "DELETE", "path": "/projects/{project_id}/tracks/{track_name}"},
    "validate_project":  {"method": "POST", "path": "/validate"},
    "get_presets":       {"method": "GET",  "path": "/presets/chains"},
    "apply_preset":      {"method": "POST", "path": "/presets/chains/{preset_name}/apply"},
    "ai_compose":        {"method": "POST", "path": "/ai/compose"},
    "create_snapshot":   {"method": "POST", "path": "/projects/{project_id}/snapshots"},
    "export_stems":      {"method": "POST", "path": "/projects/{project_id}/export-stems"},
}


class ToolExecutor:
    """Execute Agent tool calls by mapping them to local VCMix API requests.

    Uses httpx to call the local API server. All routes are under /api/v1/.
    """

    def __init__(self, api_base: str = "http://localhost:8000/api/v1") -> None:
        self._api_base = api_base.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._api_base,
            timeout=30.0,
        )

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool call against the VCMix API.

        Args:
            tool_name: One of the 20 tool names in AGENT_TOOLS.
            arguments: Tool arguments (already validated by the LLM).

        Returns:
            API response as a dict.
        """
        route_info = _TOOL_ROUTE_MAP.get(tool_name)
        if route_info is None:
            return {"error": f"Unknown tool: {tool_name}"}

        method = route_info["method"]
        path_template = route_info["path"]

        # Build path by substituting {param} placeholders from arguments
        path = path_template
        for key in list(arguments.keys()):
            placeholder = "{" + key + "}"
            if placeholder in path:
                path = path.replace(placeholder, str(arguments.pop(key)))

        url = path  # relative to base_url

        try:
            if method == "GET":
                resp = await self._client.get(url, params=arguments)
            elif method == "POST":
                resp = await self._client.post(url, json=arguments)
            elif method == "PUT":
                resp = await self._client.put(url, json=arguments)
            elif method == "DELETE":
                resp = await self._client.delete(url, params=arguments)
            else:
                return {"error": f"Unsupported HTTP method: {method}"}

            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.warning("Tool %s API error %d: %s", tool_name, e.response.status_code, e.response.text[:200])
            return {
                "error": f"API error {e.response.status_code}",
                "detail": e.response.text[:500],
            }
        except httpx.RequestError as e:
            logger.warning("Tool %s request failed: %s", tool_name, e)
            return {"error": f"Request failed: {e}"}
        except Exception as e:
            logger.warning("Tool %s unexpected error: %s", tool_name, e)
            return {"error": f"Unexpected error: {e}"}

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    @staticmethod
    def get_tool_names() -> list[str]:
        """Return list of all available tool names."""
        return [t["name"] for t in AGENT_TOOLS]
