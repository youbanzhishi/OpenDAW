"""
community.py — ChainVerse community interface for VC-Chain.

Provides community sharing functionality similar to Waves StudioVerse:
    - Upload chain presets to the community
    - Search chains by tags, instruments, genres
    - Rate chains (1-5 stars)
    - AI-powered chain recommendation based on audio features

Storage:
    - Local: Chain YAML files + metadata JSON in ~/.vcmix/chainverse/
    - Remote (future): GitHub repo or dedicated server

AI Recommendation:
    - Current: Tag-based matching with relevance scoring
    - Future: Audio feature extraction + similarity search

Usage:
    from vcmix.chain.community import ChainVerse

    cv = ChainVerse()
    cv.upload(chain, author="user", tags=["vocal", "pop"])
    results = cv.search("vocal pop bright")
    recommended = cv.recommend(tags=["vocal"], instruments=["vocal"])

Dependencies: vcmix.chain.models, json, pathlib
"""

from __future__ import annotations

import json
import logging
import math
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from vcmix.chain.models import ChainConfig

logger = logging.getLogger(__name__)

# ── Default Storage ──────────────────────────────────────────────────────

_DEFAULT_CHAINVERSE_DIR = Path(
    os.environ.get("VCMIX_CHAINVERSE_DIR", Path.home() / ".vcmix" / "chainverse")
)

# ── Data Models ──────────────────────────────────────────────────────────

@dataclass
class ChainVerseEntry:
    """A chain entry in the ChainVerse community.

    Attributes:
        id: Unique entry ID.
        name: Chain name.
        author: Chain author.
        tags: Search/filter tags.
        instruments: Target instruments.
        genres: Target genres.
        rating: Average user rating (1.0-5.0).
        rating_count: Number of ratings.
        downloads: Download count.
        created: Creation timestamp (epoch).
        updated: Last update timestamp (epoch).
        chain_path: Path to the chain YAML file.
        description: Chain description.
    """

    id: str
    name: str
    author: str = ""
    tags: list[str] = field(default_factory=list)
    instruments: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    rating: float = 0.0
    rating_count: int = 0
    downloads: int = 0
    created: float = 0.0
    updated: float = 0.0
    chain_path: str = ""
    description: str = ""

    @property
    def composite_score(self) -> float:
        """Compute composite score for ranking.

        Formula: rating * log(downloads + 1) / log(max_downloads + 1)
        If no downloads, returns rating alone.
        """
        if self.downloads == 0:
            return self.rating
        return self.rating * math.log(self.downloads + 1)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "id": self.id,
            "name": self.name,
            "author": self.author,
            "tags": self.tags,
            "instruments": self.instruments,
            "genres": self.genres,
            "rating": self.rating,
            "rating_count": self.rating_count,
            "downloads": self.downloads,
            "created": self.created,
            "updated": self.updated,
            "chain_path": self.chain_path,
            "description": self.description,
            "composite_score": self.composite_score,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChainVerseEntry:
        """Deserialize from a plain dict."""
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            author=data.get("author", ""),
            tags=data.get("tags", []),
            instruments=data.get("instruments", []),
            genres=data.get("genres", []),
            rating=float(data.get("rating", 0.0)),
            rating_count=int(data.get("rating_count", 0)),
            downloads=int(data.get("downloads", 0)),
            created=float(data.get("created", 0.0)),
            updated=float(data.get("updated", 0.0)),
            chain_path=data.get("chain_path", ""),
            description=data.get("description", ""),
        )


# ── ChainVerse Manager ───────────────────────────────────────────────────

class ChainVerse:
    """ChainVerse community interface.

    Manages chain sharing, search, rating, and recommendation.

    Args:
        storage_dir: Directory for local ChainVerse storage.
            Defaults to ~/.vcmix/chainverse/.
    """

    def __init__(self, storage_dir: str | Path | None = None) -> None:
        if storage_dir is None:
            storage_dir = _DEFAULT_CHAINVERSE_DIR
        self._storage_dir = Path(storage_dir)
        self._chains_dir = self._storage_dir / "chains"
        self._meta_file = self._storage_dir / "metadata.json"
        self._entries: dict[str, ChainVerseEntry] = {}
        self._load_metadata()

    def _load_metadata(self) -> None:
        """Load metadata from storage."""
        if self._meta_file.exists():
            try:
                data = json.loads(self._meta_file.read_text(encoding="utf-8"))
                for entry_data in data.get("entries", []):
                    entry = ChainVerseEntry.from_dict(entry_data)
                    self._entries[entry.id] = entry
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to load ChainVerse metadata: %s", e)

    def _save_metadata(self) -> None:
        """Save metadata to storage."""
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "entries": [e.to_dict() for e in self._entries.values()],
        }
        self._meta_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def upload(
        self,
        chain: ChainConfig,
        author: str = "",
        instruments: list[str] | None = None,
        genres: list[str] | None = None,
    ) -> ChainVerseEntry:
        """Upload a chain to the community.

        Args:
            chain: ChainConfig to upload.
            author: Author name.
            instruments: Target instruments.
            genres: Target genres.

        Returns:
            ChainVerseEntry for the uploaded chain.
        """
        # Generate unique ID
        entry_id = str(uuid4())[:8]

        # Save chain YAML
        self._chains_dir.mkdir(parents=True, exist_ok=True)
        chain_filename = f"{entry_id}-{chain.name}.yaml"
        chain_path = self._chains_dir / chain_filename
        chain.save_yaml(chain_path)

        now = time.time()
        entry = ChainVerseEntry(
            id=entry_id,
            name=chain.name,
            author=author or chain.author,
            tags=list(chain.tags),
            instruments=instruments or [],
            genres=genres or [],
            rating=0.0,
            rating_count=0,
            downloads=0,
            created=now,
            updated=now,
            chain_path=str(chain_path),
            description=chain.description,
        )

        self._entries[entry_id] = entry
        self._save_metadata()

        logger.info(
            "Uploaded chain '%s' to ChainVerse (id=%s)", chain.name, entry_id
        )
        return entry

    def search(
        self,
        query: str = "",
        tags: list[str] | None = None,
        instruments: list[str] | None = None,
        genres: list[str] | None = None,
        limit: int = 20,
    ) -> list[ChainVerseEntry]:
        """Search chains in the community.

        Supports:
            - Full-text search on name and description
            - Tag filtering
            - Instrument filtering
            - Genre filtering
            - Results ranked by composite score

        Args:
            query: Full-text search query.
            tags: Filter by tags (OR match).
            instruments: Filter by instruments (OR match).
            genres: Filter by genres (OR match).
            limit: Maximum results to return.

        Returns:
            List of matching ChainVerseEntry, ranked by score.
        """
        results = []

        for entry in self._entries.values():
            score = 0.0
            match = False

            # Full-text search
            if query:
                query_lower = query.lower()
                words = query_lower.split()
                searchable = f"{entry.name} {entry.description} {' '.join(entry.tags)}"
                searchable_lower = searchable.lower()
                for word in words:
                    if word in searchable_lower:
                        score += 1.0
                        match = True

                if not match and not tags and not instruments and not genres:
                    continue

            # Tag filter
            if tags:
                for tag in tags:
                    if tag.lower() in [t.lower() for t in entry.tags]:
                        score += 2.0
                        match = True

            # Instrument filter
            if instruments:
                for inst in instruments:
                    if inst.lower() in [i.lower() for i in entry.instruments]:
                        score += 2.0
                        match = True

            # Genre filter
            if genres:
                for genre in genres:
                    if genre.lower() in [g.lower() for g in entry.genres]:
                        score += 2.0
                        match = True

            # If no filters specified, include all
            if not query and not tags and not instruments and not genres:
                match = True

            if match:
                # Combine search score with composite score
                combined = score + entry.composite_score * 0.5
                results.append((combined, entry))

        # Sort by combined score descending
        results.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in results[:limit]]

    def recommend(
        self,
        tags: list[str] | None = None,
        instruments: list[str] | None = None,
        genres: list[str] | None = None,
        audio_features: dict[str, float] | None = None,
        limit: int = 5,
    ) -> list[ChainVerseEntry]:
        """AI-powered chain recommendation.

        Currently uses tag-based matching. Future versions will use
        audio feature similarity.

        Args:
            tags: Preferred tags.
            instruments: Target instruments.
            genres: Target genres.
            audio_features: Audio feature dict (for future use).
            limit: Maximum recommendations to return.

        Returns:
            List of recommended ChainVerseEntry.
        """
        # For now, delegate to search with boosted relevance
        results = self.search(
            tags=tags,
            instruments=instruments,
            genres=genres,
            limit=limit * 2,  # Get more candidates
        )

        # Re-rank by composite score (popularity-weighted)
        results.sort(key=lambda e: e.composite_score, reverse=True)

        return results[:limit]

    def rate(self, entry_id: str, rating: float) -> bool:
        """Rate a chain in the community.

        Args:
            entry_id: Entry ID.
            rating: Rating value (1.0-5.0).

        Returns:
            True if rating was recorded, False if entry not found.
        """
        entry = self._entries.get(entry_id)
        if entry is None:
            return False

        # Clamp rating
        rating = max(1.0, min(5.0, rating))

        # Update average rating
        total = entry.rating * entry.rating_count + rating
        entry.rating_count += 1
        entry.rating = total / entry.rating_count
        entry.updated = time.time()

        self._save_metadata()
        return True

    def download(self, entry_id: str) -> ChainConfig | None:
        """Download a chain from the community.

        Increments the download counter and returns the ChainConfig.

        Args:
            entry_id: Entry ID.

        Returns:
            ChainConfig instance, or None if not found.
        """
        entry = self._entries.get(entry_id)
        if entry is None:
            return None

        # Increment downloads
        entry.downloads += 1
        self._save_metadata()

        # Load chain
        chain_path = Path(entry.chain_path)
        if not chain_path.exists():
            logger.warning("Chain file not found: %s", chain_path)
            return None

        return ChainConfig.from_yaml_file(chain_path)

    def delete(self, entry_id: str) -> bool:
        """Delete a chain from the community.

        Args:
            entry_id: Entry ID.

        Returns:
            True if deleted, False if not found.
        """
        entry = self._entries.get(entry_id)
        if entry is None:
            return False

        # Delete chain file
        chain_path = Path(entry.chain_path)
        if chain_path.exists():
            chain_path.unlink()

        # Remove from entries
        del self._entries[entry_id]
        self._save_metadata()

        logger.info("Deleted chain '%s' from ChainVerse (id=%s)", entry.name, entry_id)
        return True

    def list_entries(self, limit: int = 50, offset: int = 0) -> list[ChainVerseEntry]:
        """List all community entries.

        Args:
            limit: Maximum entries to return.
            offset: Offset for pagination.

        Returns:
            List of ChainVerseEntry, sorted by composite score.
        """
        entries = sorted(
            self._entries.values(),
            key=lambda e: e.composite_score,
            reverse=True,
        )
        return entries[offset:offset + limit]

    def get_entry(self, entry_id: str) -> ChainVerseEntry | None:
        """Get a specific community entry.

        Args:
            entry_id: Entry ID.

        Returns:
            ChainVerseEntry or None if not found.
        """
        return self._entries.get(entry_id)

    @property
    def entry_count(self) -> int:
        """Total number of community entries."""
        return len(self._entries)
