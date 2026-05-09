"""
chain_api.py — VC-Chain API endpoints for VCMix.

REST API under /api/v1/ for chain management, .xps import/export,
and ChainVerse community operations.

Endpoints:
    GET    /api/v1/chains                    — List all chains
    POST   /api/v1/chains                    — Create chain
    GET    /api/v1/chains/{name}             — Get chain details
    PUT    /api/v1/chains/{name}             — Update chain
    DELETE /api/v1/chains/{name}             — Delete chain
    POST   /api/v1/chains/{name}/apply       — Apply chain to track
    POST   /api/v1/chains/import/xps         — Import .xps file
    POST   /api/v1/chains/{name}/export/xps  — Export as .xps
    GET    /api/v1/chainverse/search         — Community search
    POST   /api/v1/chainverse/upload         — Upload to community
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from vcmix.chain.community import ChainVerse
from vcmix.chain.models import (
    ChainConfig,
    ChainStep,
    MacroConfig,
    MacroMapping,
    ParallelBranch,
)
from vcmix.chain.presets import get_builtin_preset, list_builtin_presets
from vcmix.chain.xps_export import export_xps
from vcmix.chain.xps_import import import_xps

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Shared instances ─────────────────────────────────────────────────────

# User chains storage directory
_CHAINS_DIR = Path(tempfile.gettempdir()) / "vcmix_chains"
_CHAINS_DIR.mkdir(parents=True, exist_ok=True)

# In-memory chain store (name -> ChainConfig)
_user_chains: dict[str, ChainConfig] = {}

# ChainVerse community
_chainverse = ChainVerse()

# ── Request/Response Models ──────────────────────────────────────────────


class ChainStepModel(BaseModel):
    """Request model for a chain step."""
    plugin: str = Field(..., description="Plugin name (e.g. vc-comp)")
    params: dict[str, Any] = Field(default_factory=dict, description="Plugin parameters")
    enabled: bool = Field(True, description="Whether step is active")


class MacroMappingModel(BaseModel):
    """Request model for a macro mapping."""
    plugin: str = Field(..., description="Target plugin name")
    param: str = Field(..., description="Target parameter name")
    range: list[float] = Field([0.0, 1.0], description="Mapping range [min, max]")
    inverse: bool = Field(False, description="Inverse mapping")


class MacroModel(BaseModel):
    """Request model for a macro controller."""
    name: str = Field(..., description="Macro display name")
    mapping: list[MacroMappingModel] = Field(default_factory=list)


class ParallelBranchModel(BaseModel):
    """Request model for a parallel branch."""
    mix: float = Field(0.5, description="Wet signal mix level")
    chain: list[ChainStepModel] = Field(default_factory=list)


class CreateChainRequest(BaseModel):
    """Request body for creating a chain."""
    name: str = Field(..., description="Chain name")
    author: str = Field("", description="Chain author")
    version: str = Field("1.0", description="Format version")
    description: str = Field("", description="Chain description")
    tags: list[str] = Field(default_factory=list, description="Search tags")
    macro: list[MacroModel] = Field(default_factory=list, description="Macro controllers")
    serial: list[ChainStepModel] = Field(default_factory=list, description="Serial chain steps")
    parallel: list[ParallelBranchModel] = Field(default_factory=list, description="Parallel branches")


class UpdateChainRequest(BaseModel):
    """Request body for updating a chain."""
    author: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    macro: list[MacroModel] | None = None
    serial: list[ChainStepModel] | None = None
    parallel: list[ParallelBranchModel] | None = None


class ApplyChainRequest(BaseModel):
    """Request body for applying a chain to a track."""
    track_name: str = Field(..., description="Target track name")
    track_config: dict[str, Any] = Field(..., description="Track config dict")
    macro_values: dict[str, float] | None = Field(
        None, description="Optional macro values to apply"
    )


class ChainverseUploadRequest(BaseModel):
    """Request body for uploading to ChainVerse."""
    chain_name: str = Field(..., description="Chain name to upload")
    author: str = Field("", description="Author name")
    instruments: list[str] = Field(default_factory=list, description="Target instruments")
    genres: list[str] = Field(default_factory=list, description="Target genres")


# ── Helper Functions ─────────────────────────────────────────────────────


def _get_all_chains() -> dict[str, ChainConfig]:
    """Get all chains (built-in + user)."""
    all_chains = {}
    # Built-in presets
    for name in list_builtin_presets():
        chain = get_builtin_preset(name)
        if chain:
            all_chains[name] = chain
    # User chains
    all_chains.update(_user_chains)
    return all_chains


def _get_chain(name: str) -> ChainConfig | None:
    """Get a chain by name (user chains take precedence)."""
    if name in _user_chains:
        return _user_chains[name]
    return get_builtin_preset(name)


def _step_model_to_step(model: ChainStepModel) -> ChainStep:
    """Convert API model to ChainStep."""
    return ChainStep(
        plugin=model.plugin,
        params=model.params,
        enabled=model.enabled,
    )


def _macro_model_to_config(model: MacroModel) -> MacroConfig:
    """Convert API model to MacroConfig."""
    return MacroConfig(
        name=model.name,
        mapping=[
            MacroMapping(
                plugin=m.plugin,
                param=m.param,
                range=(m.range[0], m.range[1]) if len(m.range) == 2 else (0.0, 1.0),
                inverse=m.inverse,
            )
            for m in model.mapping
        ],
    )


def _branch_model_to_branch(model: ParallelBranchModel) -> ParallelBranch:
    """Convert API model to ParallelBranch."""
    return ParallelBranch(
        mix=model.mix,
        chain=[_step_model_to_step(s) for s in model.chain],
    )


# ── Chain CRUD Endpoints ────────────────────────────────────────────────


@router.get("/chains")
async def list_chains():
    """List all available chains (built-in + user)."""
    all_chains = _get_all_chains()
    chain_list = []
    for name, chain in all_chains.items():
        chain_list.append({
            "name": chain.name,
            "author": chain.author,
            "description": chain.description,
            "tags": chain.tags,
            "step_count": chain.step_count,
            "macro_count": chain.macro_count,
            "has_parallel": len(chain.parallel) > 0,
            "has_multiband": chain.multiband is not None,
            "source": "builtin" if name in list_builtin_presets() and name not in _user_chains else "user",
        })
    return {"chains": chain_list, "count": len(chain_list)}


@router.post("/chains")
async def create_chain(request: CreateChainRequest):
    """Create a new chain."""
    if request.name in list_builtin_presets() and request.name not in _user_chains:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot overwrite built-in chain: {request.name}",
        )

    chain = ChainConfig(
        name=request.name,
        author=request.author,
        version=request.version,
        description=request.description,
        tags=request.tags,
        macro=[_macro_model_to_config(m) for m in request.macro],
        serial=[_step_model_to_step(s) for s in request.serial],
        parallel=[_branch_model_to_branch(b) for b in request.parallel],
    )

    # Validate
    issues = chain.validate()
    if issues:
        raise HTTPException(status_code=400, detail=f"Validation errors: {issues}")

    # Save
    _user_chains[request.name] = chain
    chain_path = _CHAINS_DIR / f"{request.name}.yaml"
    chain.save_yaml(chain_path)

    return {
        "name": chain.name,
        "created": True,
        "path": str(chain_path),
        "step_count": chain.step_count,
        "macro_count": chain.macro_count,
    }


@router.get("/chains/{name}")
async def get_chain_detail(name: str):
    """Get detailed information about a chain."""
    chain = _get_chain(name)
    if chain is None:
        raise HTTPException(status_code=404, detail=f"Chain not found: {name}")

    result = chain.to_dict()

    # Add signal flow info
    from vcmix.chain.engine import ChainEngine
    engine = ChainEngine(chain)
    result["signal_flow"] = engine.get_signal_flow()

    # Add validation info
    result["validation"] = chain.validate()

    # Add macro descriptions
    if chain.macro:
        from vcmix.chain.macro import MacroController
        controller = MacroController(chain.macro)
        result["macro_descriptions"] = controller.describe()

    return result


@router.put("/chains/{name}")
async def update_chain(name: str, request: UpdateChainRequest):
    """Update an existing chain."""
    chain = _get_chain(name)
    if chain is None:
        raise HTTPException(status_code=404, detail=f"Chain not found: {name}")

    # Cannot modify built-in chains
    if name in list_builtin_presets() and name not in _user_chains:
        raise HTTPException(
            status_code=403,
            detail=f"Cannot modify built-in chain: {name}",
        )

    # Apply updates
    if request.author is not None:
        chain.author = request.author
    if request.description is not None:
        chain.description = request.description
    if request.tags is not None:
        chain.tags = request.tags
    if request.macro is not None:
        chain.macro = [_macro_model_to_config(m) for m in request.macro]
    if request.serial is not None:
        chain.serial = [_step_model_to_step(s) for s in request.serial]
    if request.parallel is not None:
        chain.parallel = [_branch_model_to_branch(b) for b in request.parallel]

    # Validate
    issues = chain.validate()
    if issues:
        raise HTTPException(status_code=400, detail=f"Validation errors: {issues}")

    # Save
    _user_chains[name] = chain
    chain_path = _CHAINS_DIR / f"{name}.yaml"
    chain.save_yaml(chain_path)

    return {
        "name": chain.name,
        "updated": True,
        "step_count": chain.step_count,
        "macro_count": chain.macro_count,
    }


@router.delete("/chains/{name}")
async def delete_chain(name: str):
    """Delete a user-defined chain."""
    if name in list_builtin_presets() and name not in _user_chains:
        raise HTTPException(
            status_code=403,
            detail=f"Cannot delete built-in chain: {name}",
        )

    if name not in _user_chains:
        raise HTTPException(status_code=404, detail=f"Chain not found: {name}")

    del _user_chains[name]

    # Delete file
    chain_path = _CHAINS_DIR / f"{name}.yaml"
    if chain_path.exists():
        chain_path.unlink()

    return {"name": name, "deleted": True}


@router.post("/chains/{name}/apply")
async def apply_chain(name: str, request: ApplyChainRequest):
    """Apply a chain to a track configuration."""
    chain = _get_chain(name)
    if chain is None:
        raise HTTPException(status_code=404, detail=f"Chain not found: {name}")

    try:
        # Build effects list from chain serial steps
        effects = [step.to_dict() for step in chain.serial if step.enabled]

        # Apply macro values if provided
        if request.macro_values:
            from vcmix.chain.macro import MacroController
            controller = MacroController(chain.macro)
            updates = controller.apply_all(request.macro_values)
            # Merge macro updates into effects
            for effect in effects:
                plugin = effect.get("plugin", "")
                if plugin in updates:
                    for param_name, param_value in updates[plugin].items():
                        effect.setdefault("params", {})[param_name] = param_value

        # Update track config
        updated_config = dict(request.track_config)
        updated_config["effects"] = effects
        updated_config["chain_name"] = name

        return {
            "chain_name": name,
            "track_name": request.track_name,
            "updated_config": updated_config,
            "applied": True,
            "effect_count": len(effects),
            "macro_values_applied": bool(request.macro_values),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Apply error: {e}")


# ── .xps Import/Export Endpoints ────────────────────────────────────────


@router.post("/chains/import/xps")
async def import_xps_file(file: UploadFile = File(...)):
    """Import a Waves .xps preset file as a VC-Chain."""
    if not file.filename or not file.filename.endswith(".xps"):
        raise HTTPException(
            status_code=400,
            detail="File must have .xps extension",
        )

    try:
        # Save uploaded file to temp location
        with tempfile.NamedTemporaryFile(suffix=".xps", delete=False) as f:
            content = await file.read()
            f.write(content)
            temp_path = f.name

        # Import
        chain = import_xps(temp_path)

        # Clean up temp file
        Path(temp_path).unlink(missing_ok=True)

        # Save as user chain
        _user_chains[chain.name] = chain
        chain_path = _CHAINS_DIR / f"{chain.name}.yaml"
        chain.save_yaml(chain_path)

        return {
            "name": chain.name,
            "author": chain.author,
            "description": chain.description,
            "tags": chain.tags,
            "imported": True,
            "step_count": chain.step_count,
            "macro_count": chain.macro_count,
            "has_parallel": len(chain.parallel) > 0,
            "has_multiband": chain.multiband is not None,
            "yaml_path": str(chain_path),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Import error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import failed: {e}")


@router.post("/chains/{name}/export/xps")
async def export_xps_file(name: str):
    """Export a chain as a Waves .xps preset file."""
    chain = _get_chain(name)
    if chain is None:
        raise HTTPException(status_code=404, detail=f"Chain not found: {name}")

    try:
        # Export to temp file
        xps_path = _CHAINS_DIR / f"{name}.xps"
        export_xps(chain, xps_path)

        return {
            "name": chain.name,
            "exported": True,
            "xps_path": str(xps_path),
            "step_count": chain.step_count,
            "note": "Exported .xps uses a template binary header; "
                    "compatibility with all StudioRack versions is not guaranteed.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export error: {e}")


# ── ChainVerse Community Endpoints ──────────────────────────────────────


@router.get("/chainverse/search")
async def search_chainverse(
    q: str = "",
    tags: str = "",
    instruments: str = "",
    genres: str = "",
    limit: int = 20,
):
    """Search chains in the ChainVerse community."""
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    inst_list = [i.strip() for i in instruments.split(",") if i.strip()] if instruments else []
    genre_list = [g.strip() for g in genres.split(",") if g.strip()] if genres else []

    results = _chainverse.search(
        query=q,
        tags=tag_list or None,
        instruments=inst_list or None,
        genres=genre_list or None,
        limit=limit,
    )

    return {
        "results": [e.to_dict() for e in results],
        "count": len(results),
        "query": q,
        "tags": tag_list,
        "instruments": inst_list,
        "genres": genre_list,
    }


@router.post("/chainverse/upload")
async def upload_to_chainverse(request: ChainverseUploadRequest):
    """Upload a chain to the ChainVerse community."""
    chain = _get_chain(request.chain_name)
    if chain is None:
        raise HTTPException(
            status_code=404,
            detail=f"Chain not found: {request.chain_name}",
        )

    entry = _chainverse.upload(
        chain=chain,
        author=request.author,
        instruments=request.instruments,
        genres=request.genres,
    )

    return {
        "id": entry.id,
        "name": entry.name,
        "author": entry.author,
        "uploaded": True,
        "tags": entry.tags,
        "instruments": entry.instruments,
        "genres": entry.genres,
    }


@router.post("/chainverse/{entry_id}/rate")
async def rate_chainverse_entry(entry_id: str, rating: float = 5.0):
    """Rate a chain in the ChainVerse community."""
    success = _chainverse.rate(entry_id, rating)
    if not success:
        raise HTTPException(status_code=404, detail=f"Entry not found: {entry_id}")

    entry = _chainverse.get_entry(entry_id)
    return {
        "id": entry_id,
        "rated": True,
        "new_rating": entry.rating if entry else 0.0,
        "rating_count": entry.rating_count if entry else 0,
    }


@router.get("/chainverse/{entry_id}")
async def get_chainverse_entry(entry_id: str):
    """Get a ChainVerse community entry."""
    entry = _chainverse.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Entry not found: {entry_id}")

    return entry.to_dict()


@router.get("/chainverse")
async def list_chainverse_entries(limit: int = 50, offset: int = 0):
    """List all ChainVerse community entries."""
    entries = _chainverse.list_entries(limit=limit, offset=offset)
    return {
        "entries": [e.to_dict() for e in entries],
        "count": len(entries),
        "total": _chainverse.entry_count,
    }
