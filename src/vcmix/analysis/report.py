"""
report.py — Analysis report generation for VCMix.

Generates formatted reports from analysis results:
    - JSON: Full structured data (default)
    - Text: Human-readable console output
    - Markdown: Formatted documentation

Usage:
    from vcmix.analysis.report import ReportGenerator
    gen = ReportGenerator()
    json_str = gen.generate(result, format="json")
    text_str = gen.generate(result, format="text")
    md_str = gen.generate(result, format="markdown")

Dependencies: json (stdlib)
"""

from __future__ import annotations

import json
from typing import Any


class ReportGenerator:
    """Analysis report generator supporting JSON, text, and markdown formats."""

    def generate(self, result: dict[str, Any], format: str = "json") -> str:
        """
        Generate analysis report.

        Args:
            result: Analysis result dict (from AudioAnalyzer.analyze()).
            format: Output format — "json", "text", or "markdown".

        Returns:
            Formatted report string.
        """
        if format == "json":
            return self._format_json(result)
        elif format == "text":
            return self._format_text(result)
        elif format == "markdown":
            return self._format_markdown(result)
        else:
            raise ValueError(f"Unknown format: {format!r}. Use json/text/markdown.")

    def _format_json(self, result: dict[str, Any]) -> str:
        """Format as JSON."""
        return json.dumps(result, ensure_ascii=False, indent=2)

    def _format_text(self, result: dict[str, Any]) -> str:
        """Format as human-readable text."""
        lines = []
        lines.append("=" * 60)
        lines.append("VCMix Audio Analysis Report")
        lines.append("=" * 60)
        lines.append(f"File:       {result.get('file', 'N/A')}")
        lines.append(f"Duration:   {result.get('duration', 'N/A')}s")
        lines.append(f"Sample Rate:{result.get('sample_rate', 'N/A')}Hz")
        lines.append(f"Channels:   {result.get('channels', 'N/A')}")
        lines.append("")

        # Loudness
        if "loudness" in result:
            loudness = result["loudness"]
            lines.append("─ Loudness ──────────────────────────────")
            lines.append(f"  Integrated LUFS:  {loudness.get('integrated_lufs', 'N/A')}")
            lines.append(f"  RMS (dBFS):       {loudness.get('rms_dbfs', 'N/A')}")
            lines.append(f"  True Peak (dBFS): {loudness.get('true_peak_dbfs', 'N/A')}")
            lines.append(f"  Dynamic Range:    {loudness.get('dynamic_range_db', 'N/A')} dB")
            lines.append(f"  Loudness Range:   {loudness.get('loudness_range_lu', 'N/A')} LU")
            lines.append("")

        # Spectrum
        if "spectrum" in result:
            s = result["spectrum"]
            lines.append("─ Spectrum ──────────────────────────────")
            lines.append(f"  Peak Band:  {s.get('peak_band', 'N/A')} Hz")
            lines.append(f"  Dip Band:   {s.get('dip_band', 'N/A')} Hz")
            bal = s.get("balance", {})
            if bal:
                lines.append(f"  Balance:    Low={bal.get('low', 'N/A')} Mid={bal.get('mid', 'N/A')} "
                           f"High={bal.get('high', 'N/A')} Air={bal.get('air', 'N/A')}")
            lines.append("")

        # BPM
        if "bpm" in result:
            b = result["bpm"]
            lines.append("─ BPM ───────────────────────────────────")
            lines.append(f"  BPM:        {b.get('value', 'N/A')}")
            lines.append(f"  Confidence: {b.get('confidence', 'N/A')}")
            lines.append("")

        # Key
        if "key" in result:
            k = result["key"]
            lines.append("─ Key ───────────────────────────────────")
            lines.append(f"  Tonic:      {k.get('tonic', 'N/A')}")
            lines.append(f"  Mode:       {k.get('mode', 'N/A')}")
            lines.append(f"  Confidence: {k.get('confidence', 'N/A')}")
            lines.append("")

        # Sibilance
        if "sibilance" in result:
            s = result["sibilance"]
            lines.append("─ Sibilance ─────────────────────────────")
            lines.append(f"  Index:      {s.get('index', 'N/A')}")
            lines.append(f"  Peak Freq:  {s.get('peak_freq', 'N/A')} Hz")
            lines.append(f"  Energy Ratio:{s.get('energy_ratio', 'N/A')}")
            lines.append("")

        # Dynamics
        if "dynamics" in result:
            d = result["dynamics"]
            lines.append("─ Dynamics ──────────────────────────────")
            lines.append(f"  Crest Factor: {d.get('crest_factor_db', 'N/A')} dB")
            dist = d.get("level_distribution", {})
            if dist:
                lines.append("  Level Distribution:")
                for k, v in dist.items():
                    bar = "█" * int(v * 40)
                    lines.append(f"    {k:>15s}: {v:.2f} {bar}")
            comp = d.get("compression_suggestion", {})
            if comp:
                lines.append(f"  Compression: threshold={comp.get('threshold_db', 'N/A')}dB, "
                           f"ratio={comp.get('ratio', 'N/A')}:1")
                lines.append(f"    → {comp.get('reason', 'N/A')}")
            lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)

    def _format_markdown(self, result: dict[str, Any]) -> str:
        """Format as Markdown."""
        lines = []
        lines.append("# VCMix Audio Analysis Report")
        lines.append("")
        lines.append(f"- **File**: `{result.get('file', 'N/A')}`")
        lines.append(f"- **Duration**: {result.get('duration', 'N/A')}s")
        lines.append(f"- **Sample Rate**: {result.get('sample_rate', 'N/A')}Hz")
        lines.append(f"- **Channels**: {result.get('channels', 'N/A')}")
        lines.append("")

        # Loudness
        if "loudness" in result:
            loudness = result["loudness"]
            lines.append("## 🎵 Loudness")
            lines.append("")
            lines.append("| Metric | Value |")
            lines.append("|--------|-------|")
            lines.append(f"| Integrated LUFS | {loudness.get('integrated_lufs', 'N/A')} |")
            lines.append(f"| RMS (dBFS) | {loudness.get('rms_dbfs', 'N/A')} |")
            lines.append(f"| True Peak (dBFS) | {loudness.get('true_peak_dbfs', 'N/A')} |")
            lines.append(f"| Dynamic Range | {loudness.get('dynamic_range_db', 'N/A')} dB |")
            lines.append(f"| Loudness Range | {loudness.get('loudness_range_lu', 'N/A')} LU |")
            lines.append("")

        # Spectrum
        if "spectrum" in result:
            s = result["spectrum"]
            lines.append("## 📊 Spectrum")
            lines.append("")
            lines.append(f"- **Peak Band**: {s.get('peak_band', 'N/A')} Hz")
            lines.append(f"- **Dip Band**: {s.get('dip_band', 'N/A')} Hz")
            bal = s.get("balance", {})
            if bal:
                lines.append(f"- **Balance**: Low={bal.get('low', 'N/A')} Mid={bal.get('mid', 'N/A')} "
                           f"High={bal.get('high', 'N/A')} Air={bal.get('air', 'N/A')}")
            lines.append("")

        # BPM
        if "bpm" in result:
            b = result["bpm"]
            lines.append("## 🥁 BPM")
            lines.append("")
            lines.append(f"- **BPM**: {b.get('value', 'N/A')}")
            lines.append(f"- **Confidence**: {b.get('confidence', 'N/A')}")
            lines.append("")

        # Key
        if "key" in result:
            k = result["key"]
            lines.append("## 🎹 Key")
            lines.append("")
            lines.append(f"- **Tonic**: {k.get('tonic', 'N/A')}")
            lines.append(f"- **Mode**: {k.get('mode', 'N/A')}")
            lines.append(f"- **Confidence**: {k.get('confidence', 'N/A')}")
            lines.append("")

        # Sibilance
        if "sibilance" in result:
            s = result["sibilance"]
            lines.append("## 🔊 Sibilance")
            lines.append("")
            lines.append(f"- **Index**: {s.get('index', 'N/A')}")
            lines.append(f"- **Peak Freq**: {s.get('peak_freq', 'N/A')} Hz")
            lines.append(f"- **Energy Ratio**: {s.get('energy_ratio', 'N/A')}")
            lines.append("")

        # Dynamics
        if "dynamics" in result:
            d = result["dynamics"]
            lines.append("## 📈 Dynamics")
            lines.append("")
            lines.append(f"- **Crest Factor**: {d.get('crest_factor_db', 'N/A')} dB")
            dist = d.get("level_distribution", {})
            if dist:
                lines.append("")
                lines.append("### Level Distribution")
                lines.append("")
                lines.append("| Range | Ratio |")
                lines.append("|-------|-------|")
                for k, v in dist.items():
                    lines.append(f"| {k} | {v:.2f} |")
            comp = d.get("compression_suggestion", {})
            if comp:
                lines.append("")
                lines.append("### Compression Suggestion")
                lines.append("")
                lines.append(f"- **Threshold**: {comp.get('threshold_db', 'N/A')} dB")
                lines.append(f"- **Ratio**: {comp.get('ratio', 'N/A')}:1")
                lines.append(f"- **Reason**: {comp.get('reason', 'N/A')}")
            lines.append("")

        return "\n".join(lines)
