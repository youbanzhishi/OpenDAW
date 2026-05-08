"""
demucs_engine.py — Demucs source separation engine with progress callbacks.

Supports:
    - htdemucs model (4 sources: vocals/drums/bass/other)
    - Custom model paths
    - Progress callback for WebSocket push
    - Fallback to CLI when demucs Python API is unavailable

Usage:
    from vcmix.separation.demucs_engine import DemucsEngine

    engine = DemucsEngine(model="htdemucs", device="cpu")
    results = engine.separate("song.wav", output_dir="./stems/")
    # results = {"vocals": Path("./stems/vocals.wav"), ...}
"""
from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional

import soundfile as sf

logger = logging.getLogger(__name__)

# Default Demucs 4-source stem names
DEFAULT_STEMS = ("vocals", "drums", "bass", "other")


class DemucsEngine:
    """Demucs source separation engine.

    Parameters
    ----------
    model : str
        Model name (default htdemucs).
    device : str
        Compute device ("cpu" or "cuda").
    model_path : str or Path or None
        Custom path to a pre-downloaded model directory.
        If *None*, demucs will auto-download to its default cache.
    """

    def __init__(
        self,
        model: str = "htdemucs",
        device: str = "cpu",
        model_path: Optional[str | Path] = None,
    ):
        self.model = model
        self.device = device
        self.model_path = Path(model_path) if model_path else None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def separate(
        self,
        input_path: str | Path,
        output_dir: Optional[str | Path] = None,
        two_stems: Optional[str] = None,
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> dict[str, Path]:
        """Separate an audio file into stems.

        Parameters
        ----------
        input_path : str or Path
            Path to the input audio file.
        output_dir : str or Path or None
            Output directory for separated WAV files.
            If *None*, a temporary directory is created.
        two_stems : str or None
            If set (e.g. "vocals"), only separate into 2 stems
            (target + rest).
        progress_callback : callable or None
            Called with a float 0.0-1.0 to report progress.

        Returns
        -------
        dict[str, Path]
            Mapping of stem name -> output WAV file path.
        """
        input_path = Path(input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Input not found: {input_path}")

        if output_dir is None:
            output_dir = Path(tempfile.mkdtemp(prefix="vcmix_sep_"))
        else:
            output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Try Python API first, fall back to CLI
        try:
            return self._separate_with_api(
                input_path, output_dir, two_stems, progress_callback,
            )
        except ImportError:
            logger.info("demucs Python API not available, falling back to CLI")
            return self._separate_with_cli(
                input_path, output_dir, two_stems, progress_callback,
            )

    # ------------------------------------------------------------------
    # Python API path
    # ------------------------------------------------------------------

    def _separate_with_api(
        self,
        input_path: Path,
        output_dir: Path,
        two_stems: Optional[str],
        progress_callback: Optional[Callable[[float], None]],
    ) -> dict[str, Path]:
        """Separate using demucs Python API (demucs.api)."""
        import demucs.api

        kwargs: dict = {"model": self.model, "device": self.device}
        if self.model_path:
            kwargs["repo"] = str(self.model_path)

        separator = demucs.api.Separator(**kwargs)
        if two_stems:
            separator.two_stems = two_stems

        if progress_callback:
            progress_callback(0.1)

        _, separated = separator.separate_audio_file(str(input_path))

        if progress_callback:
            progress_callback(0.8)

        results: dict[str, Path] = {}
        for stem_name, stem_audio in separated.items():
            out_path = output_dir / f"{stem_name}.wav"
            audio_np = stem_audio.cpu().numpy()
            # Ensure 2D: (channels, samples)
            if audio_np.ndim == 1:
                audio_np = audio_np.reshape(1, -1)
            sf.write(str(out_path), audio_np.T, 44100)
            results[stem_name] = out_path

        if progress_callback:
            progress_callback(1.0)

        return results

    # ------------------------------------------------------------------
    # CLI fallback path
    # ------------------------------------------------------------------

    def _separate_with_cli(
        self,
        input_path: Path,
        output_dir: Path,
        two_stems: Optional[str],
        progress_callback: Optional[Callable[[float], None]],
    ) -> dict[str, Path]:
        """Separate using the python -m demucs CLI command."""
        cmd = [
            "python", "-m", "demucs",
            "-n", self.model,
            "-d", self.device,
            "-o", str(output_dir),
        ]
        if two_stems:
            cmd.extend(["--two-stems", two_stems])
        if self.model_path:
            cmd.extend(["--repo", str(self.model_path)])
        cmd.append(str(input_path))

        if progress_callback:
            progress_callback(0.1)

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600,
            )
            if result.returncode != 0:
                raise RuntimeError(f"Demucs CLI failed: {result.stderr[:500]}")
        except FileNotFoundError as exc:
            raise ImportError(
                "Demucs not installed. Install with: pip install demucs"
            ) from exc

        if progress_callback:
            progress_callback(0.9)

        # Locate output files
        results: dict[str, Path] = {}
        track_dir = output_dir / self.model / input_path.stem
        if track_dir.exists():
            for wav_file in track_dir.glob("*.wav"):
                results[wav_file.stem] = wav_file
        else:
            # Try output_dir itself
            for wav_file in output_dir.glob("*.wav"):
                results[wav_file.stem] = wav_file

        if progress_callback:
            progress_callback(1.0)

        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def list_available_models() -> list[str]:
        """Return known Demucs model names."""
        return [
            "htdemucs",
            "htdemucs_ft",
            "hdemucs_mmi",
            "mdx",
            "mdx_extra",
            "mdx_q",
            "mdx_extra_q",
        ]

    @staticmethod
    def is_available() -> bool:
        """Check whether demucs is importable or on PATH."""
        try:
            import demucs.api  # noqa: F401
            return True
        except ImportError:
            pass
        # Check CLI
        try:
            result = subprocess.run(
                ["python", "-m", "demucs", "--help"],
                capture_output=True, text=True, timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
