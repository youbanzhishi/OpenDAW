"""
demucs_wrapper.py - Demucs source separation for VCMix.
"""
from __future__ import annotations
import subprocess
import tempfile
from pathlib import Path
from typing import Any
import numpy as np


def separate_stems(
    input_path: str | Path,
    output_dir: str | Path | None = None,
    model: str = "htdemucs",
    device: str = "cpu",
    two_stems: str | None = None,
) -> dict[str, Path]:
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Input not found: {input_path}")
    if output_dir is None:
        output_dir = Path(tempfile.mkdtemp(prefix="vcmix_sep_"))
    else:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
    try:
        import demucs.api  # noqa
        return _separate_with_api(input_path, output_dir, model, device, two_stems)
    except ImportError:
        return _separate_with_cli(input_path, output_dir, model, device, two_stems)


def _separate_with_api(input_path, output_dir, model, device, two_stems):
    import demucs.api
    import soundfile as sf
    separator = demucs.api.Separator(model=model, device=device)
    if two_stems:
        separator.two_stems = two_stems
    _, separated = separator.separate_audio_file(str(input_path))
    results = {}
    for stem_name, stem_audio in separated.items():
        out_path = output_dir / f"{stem_name}.wav"
        audio_np = stem_audio.cpu().numpy()
        if audio_np.ndim == 1:
            audio_np = audio_np.reshape(1, -1)
        sf.write(str(out_path), audio_np.T, 44100)
        results[stem_name] = out_path
    return results


def _separate_with_cli(input_path, output_dir, model, device, two_stems):
    cmd = ["python", "-m", "demucs", "-n", model, "-d", device, "-o", str(output_dir)]
    if two_stems:
        cmd.extend(["--two-stems", two_stems])
    cmd.append(str(input_path))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            raise RuntimeError(f"Demucs CLI failed: {result.stderr[:500]}")
    except FileNotFoundError:
        raise ImportError("Demucs not installed. Install with: pip install demucs")
    results = {}
    track_dir = output_dir / model / input_path.stem
    if track_dir.exists():
        for wav_file in track_dir.glob("*.wav"):
            results[wav_file.stem] = wav_file
    return results
