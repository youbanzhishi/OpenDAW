"""
test_automix.py — Tests for vcmix.engine.automix (Phase 6).

Tests both Phase 4 API (dry vocal analysis) and Phase 6 API
(DataStream closed-loop control).

Covers:
    - Phase 4: analyze_dry_vocal, generate_chain, generate_yaml
    - Phase 6: analyze (DataStream events → MixingState)
    - Phase 6: suggest (MixingState → AdjustmentSuggestions)
    - Phase 6: apply (suggestions → new config)
    - Integration: analyze → suggest → apply pipeline
    - Edge cases: empty events, silent tracks, clipping

Usage:
    pytest tests/test_automix.py -v

Dependencies: pytest, numpy
"""

from __future__ import annotations

import numpy as np
import pytest

from vcmix.engine.automix import (
    AdjustmentSuggestion,
    AutoMixer,
    MasterMixState,
    MixingState,
    TrackMixState,
)
from vcmix.stream.emitter import DataStream, EventLevel, StreamEvent


# ── Phase 4 Tests ───────────────────────────────────────────────────────────

class TestAutoMixerPhase4:
    """Tests for Phase 4 API (dry vocal analysis)."""

    def test_analyze_dry_vocal_returns_required_keys(self) -> None:
        """analyze_dry_vocal should return all required analysis keys."""
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
        audio = 0.5 * np.sin(2 * np.pi * 440 * t)

        mixer = AutoMixer(sample_rate=sr)
        result = mixer.analyze_dry_vocal(audio)

        required_keys = [
            "rms_db", "peak_db", "true_peak_db", "dynamic_range_db",
            "gain_needed_db", "sibilance_ratio", "needs_deesser",
            "spectrum", "tail_energy", "eq_needs", "compression_needs",
            "reverb_suggestion",
        ]
        for key in required_keys:
            assert key in result, f"Missing key: {key}"

    def test_analyze_dry_vocal_rms_near_expected(self) -> None:
        """RMS of a 0.5 amplitude sine should be near -6 dBFS."""
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
        audio = 0.5 * np.sin(2 * np.pi * 440 * t)

        mixer = AutoMixer(sample_rate=sr)
        result = mixer.analyze_dry_vocal(audio)

        # RMS of 0.5*sin = 0.5/sqrt(2) ≈ 0.354 → -9 dBFS
        assert -12.0 < result["rms_db"] < -6.0

    def test_analyze_dry_vocal_silence(self) -> None:
        """Silent audio should return -120 dBFS RMS."""
        sr = 44100
        audio = np.zeros(sr, dtype=np.float32)

        mixer = AutoMixer(sample_rate=sr)
        result = mixer.analyze_dry_vocal(audio)

        assert result["rms_db"] <= -100.0

    def test_generate_chain_contains_limiter(self) -> None:
        """Generated chain should always end with a limiter."""
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
        audio = 0.5 * np.sin(2 * np.pi * 440 * t)

        mixer = AutoMixer(sample_rate=sr)
        analysis = mixer.analyze_dry_vocal(audio)
        chain = mixer.generate_chain(analysis)

        assert chain[-1]["name"] == "vc-limiter"

    def test_generate_yaml_has_required_sections(self) -> None:
        """Generated YAML config should have all required sections."""
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
        audio = 0.5 * np.sin(2 * np.pi * 440 * t)

        mixer = AutoMixer(sample_rate=sr)
        analysis = mixer.analyze_dry_vocal(audio)
        config = mixer.generate_yaml("vocal", "vocal.wav", analysis)

        assert "name" in config
        assert "bpm" in config
        assert "tracks" in config
        assert "master" in config
        assert len(config["tracks"]) == 1
        assert config["tracks"][0]["name"] == "vocal"

    def test_stereo_audio_handling(self) -> None:
        """analyze_dry_vocal should handle 2D stereo audio."""
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
        left = 0.5 * np.sin(2 * np.pi * 440 * t)
        right = 0.3 * np.sin(2 * np.pi * 880 * t)
        stereo = np.stack([left, right])

        mixer = AutoMixer(sample_rate=sr)
        result = mixer.analyze_dry_vocal(stereo)

        assert result["rms_db"] > -120.0


# ── Phase 6 Tests: analyze() ───────────────────────────────────────────────

class TestAutoMixerAnalyze:
    """Tests for Phase 6 analyze() — DataStream events → MixingState."""

    def _make_track_level_event(
        self, track: str, rms_db: float, peak_db: float, true_peak_db: float = 0.0,
    ) -> StreamEvent:
        """Helper: create a track_level StreamEvent."""
        return StreamEvent(
            event_type="track_level",
            timestamp_ms=100.0,
            track=track,
            data={
                "rms_db": rms_db,
                "peak_db": peak_db,
                "true_peak_db": true_peak_db,
            },
        )

    def _make_master_level_event(
        self, rms_db: float, peak_db: float, true_peak_db: float = 0.0,
    ) -> StreamEvent:
        """Helper: create a master_level StreamEvent."""
        return StreamEvent(
            event_type="master_level",
            timestamp_ms=200.0,
            track="master",
            data={
                "rms_db": rms_db,
                "peak_db": peak_db,
                "true_peak_db": true_peak_db,
            },
        )

    def _make_warning_event(
        self, track: str, warning_type: str, message: str,
    ) -> StreamEvent:
        """Helper: create a warning StreamEvent."""
        return StreamEvent(
            event_type="warning",
            timestamp_ms=150.0,
            level=EventLevel.WARNING,
            track=track,
            data={"warning_type": warning_type, "message": message},
        )

    def _make_effect_delta_event(
        self, track: str, effect: str, delta_db: float = 0.0,
    ) -> StreamEvent:
        """Helper: create an effect_delta StreamEvent."""
        return StreamEvent(
            event_type="effect_delta",
            timestamp_ms=120.0,
            track=track,
            data={
                "effect": effect,
                "before_rms_db": -18.0,
                "after_rms_db": -18.0 + delta_db,
                "before_peak_db": -6.0,
                "after_peak_db": -6.0,
                "delta_db": delta_db,
            },
        )

    def _make_sibilance_event(
        self, track: str, sibilance_db: float, exceeds: bool,
    ) -> StreamEvent:
        """Helper: create a sibilance StreamEvent."""
        return StreamEvent(
            event_type="sibilance",
            timestamp_ms=130.0,
            level=EventLevel.WARNING if exceeds else EventLevel.INFO,
            track=track,
            data={
                "sibilance_db": sibilance_db,
                "threshold_db": -20.0,
                "exceeds": exceeds,
            },
        )

    def test_analyze_empty_events(self) -> None:
        """Empty event list should return empty MixingState."""
        mixer = AutoMixer()
        state = mixer.analyze([])

        assert isinstance(state, MixingState)
        assert len(state.tracks) == 0
        assert state.master.rms_db == -120.0

    def test_analyze_track_levels(self) -> None:
        """Track level events should populate state.tracks."""
        events = [
            self._make_track_level_event("vocal", -12.0, -3.0, -2.5),
            self._make_track_level_event("accomp", -20.0, -10.0, -9.0),
        ]

        mixer = AutoMixer()
        state = mixer.analyze(events)

        assert "vocal" in state.tracks
        assert "accomp" in state.tracks
        assert state.tracks["vocal"].rms_db == -12.0
        assert state.tracks["accomp"].rms_db == -20.0

    def test_analyze_vocal_detection(self) -> None:
        """Track names containing vocal patterns should be detected as vocal."""
        events = [
            self._make_track_level_event("lead_vocal", -12.0, -3.0),
            self._make_track_level_event("bgv", -18.0, -8.0),
            self._make_track_level_event("drums", -16.0, -4.0),
        ]

        mixer = AutoMixer()
        state = mixer.analyze(events)

        assert state.tracks["lead_vocal"].is_vocal is True
        assert state.tracks["bgv"].is_vocal is True
        assert state.tracks["drums"].is_vocal is False

    def test_analyze_master_level(self) -> None:
        """Master level event should populate state.master."""
        events = [
            self._make_master_level_event(-14.0, -3.0, -2.0),
        ]

        mixer = AutoMixer()
        state = mixer.analyze(events)

        assert state.master.rms_db == -14.0
        assert state.master.peak_db == -3.0
        assert state.master.true_peak_db == -2.0

    def test_analyze_dynamic_range_computation(self) -> None:
        """Dynamic range should be peak - RMS."""
        events = [
            self._make_track_level_event("vocal", -18.0, -6.0),
        ]

        mixer = AutoMixer()
        state = mixer.analyze(events)

        assert state.tracks["vocal"].dynamic_range_db == 12.0

    def test_analyze_warning_flags(self) -> None:
        """Warning events should set has_clipping/has_low_snr/has_sibilance."""
        events = [
            self._make_track_level_event("vocal", -12.0, -0.5),
            self._make_warning_event("vocal", "clipping", "Peak exceeds -1 dBFS"),
            self._make_warning_event("vocal", "sibilance", "Sibilance detected"),
        ]

        mixer = AutoMixer()
        state = mixer.analyze(events)

        assert state.has_clipping is True
        assert state.has_sibilance is True

    def test_analyze_low_snr_warning(self) -> None:
        """Low SNR warning should be detected."""
        events = [
            self._make_track_level_event("quiet_pad", -40.0, -30.0),
            self._make_warning_event("quiet_pad", "low_snr", "RMS below -36 dBFS"),
        ]

        mixer = AutoMixer()
        state = mixer.analyze(events)

        assert state.has_low_snr is True

    def test_analyze_effect_deltas(self) -> None:
        """Effect delta events should be accumulated."""
        events = [
            self._make_track_level_event("vocal", -12.0, -3.0),
            self._make_effect_delta_event("vocal", "vc-eq", -2.0),
            self._make_effect_delta_event("vocal", "vc-comp", -4.0),
        ]

        mixer = AutoMixer()
        state = mixer.analyze(events)

        assert "vocal" in state.effect_deltas
        assert len(state.effect_deltas["vocal"]) == 2
        assert state.effect_deltas["vocal"][0]["effect"] == "vc-eq"

    def test_analyze_sibilance_event(self) -> None:
        """Sibilance event with exceeds=True should set flag."""
        events = [
            self._make_track_level_event("vocal", -12.0, -3.0),
            self._make_sibilance_event("vocal", -18.0, True),
        ]

        mixer = AutoMixer()
        state = mixer.analyze(events)

        assert state.has_sibilance is True
        assert state.tracks["vocal"].sibilance_exceeds is True

    def test_analyze_sibilance_event_not_exceeding(self) -> None:
        """Sibilance event with exceeds=False should not set flag."""
        events = [
            self._make_track_level_event("vocal", -12.0, -3.0),
            self._make_sibilance_event("vocal", -25.0, False),
        ]

        mixer = AutoMixer()
        state = mixer.analyze(events)

        assert state.has_sibilance is False
        assert state.tracks["vocal"].sibilance_exceeds is False

    def test_analyze_latest_track_level_wins(self) -> None:
        """Multiple track_level events for same track should keep latest."""
        events = [
            self._make_track_level_event("vocal", -20.0, -10.0),
            self._make_track_level_event("vocal", -15.0, -5.0),
        ]

        mixer = AutoMixer()
        state = mixer.analyze(events)

        assert state.tracks["vocal"].rms_db == -15.0
        assert state.tracks["vocal"].peak_db == -5.0


# ── Phase 6 Tests: suggest() ───────────────────────────────────────────────

class TestAutoMixerSuggest:
    """Tests for Phase 6 suggest() — MixingState → AdjustmentSuggestions."""

    def test_suggest_empty_state(self) -> None:
        """Empty state should produce no suggestions."""
        mixer = AutoMixer()
        state = MixingState()
        suggestions = mixer.suggest(state)

        assert isinstance(suggestions, list)
        assert len(suggestions) == 0

    def test_suggest_rms_off_target_vocal(self) -> None:
        """Vocal track with RMS far from -18 dBFS should get gain suggestion."""
        state = MixingState(
            tracks={
                "vocal": TrackMixState(
                    name="vocal",
                    rms_db=-24.0,
                    peak_db=-12.0,
                    true_peak_db=-11.0,
                    dynamic_range_db=12.0,
                    is_vocal=True,
                ),
            },
        )

        mixer = AutoMixer()
        suggestions = mixer.suggest(state)

        gain_suggestions = [s for s in suggestions if s.action == "gain"]
        assert len(gain_suggestions) >= 1
        # Should suggest ~+6 dB gain (target -18 - current -24 = +6)
        assert gain_suggestions[0].params["gain_db"] > 0

    def test_suggest_rms_off_target_accomp(self) -> None:
        """Accompaniment track with RMS far from -24 dBFS should get gain suggestion."""
        state = MixingState(
            tracks={
                "drums": TrackMixState(
                    name="drums",
                    rms_db=-12.0,
                    peak_db=-3.0,
                    true_peak_db=-2.5,
                    dynamic_range_db=9.0,
                    is_vocal=False,
                ),
            },
        )

        mixer = AutoMixer()
        suggestions = mixer.suggest(state)

        gain_suggestions = [s for s in suggestions if s.action == "gain"]
        assert len(gain_suggestions) >= 1
        # Should suggest negative gain (target -24 - current -12 = -12)
        assert gain_suggestions[0].params["gain_db"] < 0

    def test_suggest_true_peak_exceeds(self) -> None:
        """Track with true peak > -1 dBFS should get limiter suggestion."""
        state = MixingState(
            tracks={
                "vocal": TrackMixState(
                    name="vocal",
                    rms_db=-18.0,
                    peak_db=-0.5,
                    true_peak_db=0.2,
                    dynamic_range_db=17.5,
                    is_vocal=True,
                ),
            },
        )

        mixer = AutoMixer()
        suggestions = mixer.suggest(state)

        limiter_suggestions = [s for s in suggestions if s.action == "limiter"]
        assert len(limiter_suggestions) >= 1
        assert limiter_suggestions[0].priority == 1

    def test_suggest_vocal_over_compressed(self) -> None:
        """Vocal with DR < 6 dB should get reduce-compression suggestion."""
        state = MixingState(
            tracks={
                "vocal": TrackMixState(
                    name="vocal",
                    rms_db=-18.0,
                    peak_db=-15.0,
                    true_peak_db=-14.5,
                    dynamic_range_db=3.0,
                    is_vocal=True,
                ),
            },
        )

        mixer = AutoMixer()
        suggestions = mixer.suggest(state)

        comp_suggestions = [s for s in suggestions if s.action == "compressor"]
        assert len(comp_suggestions) >= 1
        assert comp_suggestions[0].params.get("action") == "reduce"

    def test_suggest_vocal_too_dynamic(self) -> None:
        """Vocal with DR > 12 dB should get add-compression suggestion."""
        state = MixingState(
            tracks={
                "vocal": TrackMixState(
                    name="vocal",
                    rms_db=-18.0,
                    peak_db=-3.0,
                    true_peak_db=-2.5,
                    dynamic_range_db=15.0,
                    is_vocal=True,
                ),
            },
        )

        mixer = AutoMixer()
        suggestions = mixer.suggest(state)

        comp_suggestions = [s for s in suggestions if s.action == "compressor"]
        assert len(comp_suggestions) >= 1

    def test_suggest_master_over_compressed(self) -> None:
        """Master with DR < 3 dB should get reduce-compression suggestion."""
        state = MixingState(
            master=MasterMixState(
                rms_db=-14.0,
                peak_db=-13.0,
                true_peak_db=-12.5,
                dynamic_range_db=1.0,
            ),
        )

        mixer = AutoMixer()
        suggestions = mixer.suggest(state)

        master_comp = [
            s for s in suggestions
            if s.target == "master" and s.action == "compressor"
        ]
        assert len(master_comp) >= 1

    def test_suggest_master_true_peak(self) -> None:
        """Master true peak > -1 dBFS should get limiter suggestion."""
        state = MixingState(
            master=MasterMixState(
                rms_db=-14.0,
                peak_db=-2.0,
                true_peak_db=0.1,
                dynamic_range_db=12.0,
            ),
        )

        mixer = AutoMixer()
        suggestions = mixer.suggest(state)

        limiter = [s for s in suggestions if s.target == "master" and s.action == "limiter"]
        assert len(limiter) >= 1
        assert limiter[0].priority == 1

    def test_suggest_sibilance_deesser(self) -> None:
        """Track with sibilance_exceeds should get DeEsser suggestion."""
        state = MixingState(
            tracks={
                "vocal": TrackMixState(
                    name="vocal",
                    rms_db=-18.0,
                    peak_db=-6.0,
                    true_peak_db=-5.5,
                    dynamic_range_db=12.0,
                    sibilance_exceeds=True,
                    is_vocal=True,
                ),
            },
        )

        mixer = AutoMixer()
        suggestions = mixer.suggest(state)

        deesser = [s for s in suggestions if s.action == "deesser"]
        assert len(deesser) >= 1

    def test_suggest_sorted_by_priority(self) -> None:
        """Suggestions should be sorted by priority (1 first)."""
        state = MixingState(
            tracks={
                "vocal": TrackMixState(
                    name="vocal",
                    rms_db=-30.0,
                    peak_db=0.5,
                    true_peak_db=1.0,
                    dynamic_range_db=30.5,
                    sibilance_exceeds=True,
                    is_vocal=True,
                ),
            },
            master=MasterMixState(
                rms_db=-14.0,
                peak_db=0.2,
                true_peak_db=0.5,
                dynamic_range_db=14.2,
            ),
        )

        mixer = AutoMixer()
        suggestions = mixer.suggest(state)

        if len(suggestions) > 1:
            priorities = [s.priority for s in suggestions]
            assert priorities == sorted(priorities)

    def test_suggest_no_change_needed(self) -> None:
        """Well-mixed state should produce minimal suggestions."""
        state = MixingState(
            tracks={
                "vocal": TrackMixState(
                    name="vocal",
                    rms_db=-18.0,
                    peak_db=-8.0,
                    true_peak_db=-7.5,
                    dynamic_range_db=10.0,
                    is_vocal=True,
                ),
            },
            master=MasterMixState(
                rms_db=-14.0,
                peak_db=-5.0,
                true_peak_db=-4.5,
                dynamic_range_db=9.0,
            ),
        )

        mixer = AutoMixer()
        suggestions = mixer.suggest(state)

        # A well-mixed state should produce few or no critical suggestions
        critical = [s for s in suggestions if s.priority == 1]
        assert len(critical) == 0


# ── Phase 6 Tests: apply() ─────────────────────────────────────────────────

class TestAutoMixerApply:
    """Tests for Phase 6 apply() — suggestions → new config."""

    def _base_config(self) -> dict:
        """Create a minimal test config."""
        return {
            "name": "test_project",
            "bpm": 120,
            "sample_rate": 44100,
            "tracks": [
                {
                    "name": "vocal",
                    "file": "vocal.wav",
                    "effects": [
                        {"name": "vc-gain", "params": {"gain": 2.0}},
                        {"name": "vc-comp", "params": {"threshold": -20, "ratio": 3}},
                        {"name": "vc-limiter", "params": {"ceiling": -1}},
                    ],
                },
                {
                    "name": "drums",
                    "file": "drums.wav",
                    "effects": [],
                },
            ],
            "master": {
                "levels": {"vocal": 0.8, "drums": 0.6},
                "effects": [],
                "output": "output.wav",
            },
        }

    def test_apply_does_not_modify_original(self) -> None:
        """apply() must not modify the original config."""
        original = self._base_config()
        original_copy = __import__("copy").deepcopy(original)

        suggestions = [
            AdjustmentSuggestion(
                target="track:vocal",
                action="gain",
                params={"gain_db": 3.0},
                reason="test",
                priority=2,
            ),
        ]

        mixer = AutoMixer()
        new_config = mixer.apply(original, suggestions)

        # Original should be unchanged
        assert original == original_copy
        # New config should differ
        assert new_config != original or suggestions == []

    def test_apply_gain_to_track_with_existing_gain(self) -> None:
        """Applying gain to a track with existing vc-gain should adjust it."""
        original = self._base_config()

        suggestions = [
            AdjustmentSuggestion(
                target="track:vocal",
                action="gain",
                params={"gain_db": 3.0},
                reason="test",
                priority=2,
            ),
        ]

        mixer = AutoMixer()
        new_config = mixer.apply(original, suggestions)

        # Find the vc-gain effect in the new config
        vocal = new_config["tracks"][0]
        gain_effect = next(e for e in vocal["effects"] if e["name"] == "vc-gain")
        # Original gain was 2.0, adding 3.0 → 5.0
        assert gain_effect["params"]["gain"] == 5.0

    def test_apply_gain_to_track_without_existing_gain(self) -> None:
        """Applying gain to a track without vc-gain should insert one."""
        original = self._base_config()

        suggestions = [
            AdjustmentSuggestion(
                target="track:drums",
                action="gain",
                params={"gain_db": -4.0},
                reason="test",
                priority=2,
            ),
        ]

        mixer = AutoMixer()
        new_config = mixer.apply(original, suggestions)

        drums = new_config["tracks"][1]
        gain_effect = next(e for e in drums["effects"] if e["name"] == "vc-gain")
        assert gain_effect["params"]["gain"] == -4.0

    def test_apply_limiter_to_track(self) -> None:
        """Applying limiter to track without one should add it."""
        original = self._base_config()

        suggestions = [
            AdjustmentSuggestion(
                target="track:drums",
                action="limiter",
                params={"ceiling": -1},
                reason="test",
                priority=1,
            ),
        ]

        mixer = AutoMixer()
        new_config = mixer.apply(original, suggestions)

        drums = new_config["tracks"][1]
        has_limiter = any(e["name"] == "vc-limiter" for e in drums["effects"])
        assert has_limiter

    def test_apply_deesser_to_track(self) -> None:
        """Applying DeEsser to track should insert it."""
        original = self._base_config()

        suggestions = [
            AdjustmentSuggestion(
                target="track:vocal",
                action="deesser",
                params={"threshold": -35, "reduction": -6},
                reason="sibilance",
                priority=2,
            ),
        ]

        mixer = AutoMixer()
        new_config = mixer.apply(original, suggestions)

        vocal = new_config["tracks"][0]
        has_deesser = any(e["name"] == "vc-deesser" for e in vocal["effects"])
        assert has_deesser

    def test_apply_compressor_to_track(self) -> None:
        """Applying compressor to track without one should add it."""
        original = self._base_config()

        suggestions = [
            AdjustmentSuggestion(
                target="track:drums",
                action="compressor",
                params={
                    "threshold_db": -20,
                    "ratio": 3,
                    "attack_ms": 5,
                    "release_ms": 50,
                },
                reason="test",
                priority=2,
            ),
        ]

        mixer = AutoMixer()
        new_config = mixer.apply(original, suggestions)

        drums = new_config["tracks"][1]
        has_comp = any(e["name"] == "vc-comp" for e in drums["effects"])
        assert has_comp

    def test_apply_reduce_compression(self) -> None:
        """Reducing compression should lower ratio on existing compressor."""
        original = self._base_config()

        suggestions = [
            AdjustmentSuggestion(
                target="track:vocal",
                action="compressor",
                params={"action": "reduce", "ratio_adjust": -1},
                reason="over-compressed",
                priority=2,
            ),
        ]

        mixer = AutoMixer()
        new_config = mixer.apply(original, suggestions)

        vocal = new_config["tracks"][0]
        comp = next(e for e in vocal["effects"] if e["name"] == "vc-comp")
        assert comp["params"]["ratio"] == 2  # Was 3, reduced by 1

    def test_apply_master_limiter(self) -> None:
        """Applying limiter to master should add/update it."""
        original = self._base_config()

        suggestions = [
            AdjustmentSuggestion(
                target="master",
                action="limiter",
                params={"ceiling": -1},
                reason="master clipping",
                priority=1,
            ),
        ]

        mixer = AutoMixer()
        new_config = mixer.apply(original, suggestions)

        has_limiter = any(e["name"] == "vc-limiter" for e in new_config["master"]["effects"])
        assert has_limiter

    def test_apply_no_suggestions(self) -> None:
        """Applying no suggestions should return identical config."""
        original = self._base_config()

        mixer = AutoMixer()
        new_config = mixer.apply(original, [])

        assert new_config == original

    def test_apply_unknown_track_ignored(self) -> None:
        """Suggestions for non-existent tracks should be silently ignored."""
        original = self._base_config()

        suggestions = [
            AdjustmentSuggestion(
                target="track:nonexistent",
                action="gain",
                params={"gain_db": 5.0},
                reason="test",
                priority=2,
            ),
        ]

        mixer = AutoMixer()
        new_config = mixer.apply(original, suggestions)

        # Config should be unchanged (except deep copy)
        assert new_config == original


# ── Phase 6 Integration Tests ──────────────────────────────────────────────

class TestAutoMixerIntegration:
    """Integration tests: analyze → suggest → apply pipeline."""

    def test_full_pipeline_clipping_vocal(self) -> None:
        """Full pipeline should detect clipping and apply limiter."""
        # Simulate a loud vocal with clipping
        events = [
            StreamEvent(
                event_type="track_level",
                timestamp_ms=100.0,
                track="vocal",
                data={"rms_db": -8.0, "peak_db": -0.5, "true_peak_db": 0.2},
            ),
            StreamEvent(
                event_type="master_level",
                timestamp_ms=200.0,
                track="master",
                data={"rms_db": -10.0, "peak_db": -1.0, "true_peak_db": -0.5},
            ),
            StreamEvent(
                event_type="warning",
                timestamp_ms=150.0,
                level=EventLevel.WARNING,
                track="vocal",
                data={"warning_type": "clipping", "message": "Peak exceeds -1 dBFS"},
            ),
        ]

        config = {
            "name": "test",
            "bpm": 120,
            "tracks": [
                {"name": "vocal", "file": "vocal.wav", "effects": []},
            ],
            "master": {"levels": {"vocal": 1.0}, "effects": [], "output": "out.wav"},
        }

        mixer = AutoMixer()

        # Step 1: Analyze
        state = mixer.analyze(events)
        assert state.has_clipping is True
        assert state.tracks["vocal"].rms_db == -8.0

        # Step 2: Suggest
        suggestions = mixer.suggest(state)
        assert len(suggestions) > 0

        # Should have gain adjustment (vocal is -8, target -18)
        gain_suggestions = [s for s in suggestions if s.action == "gain"]
        assert len(gain_suggestions) >= 1

        # Should have limiter for true peak
        limiter_suggestions = [s for s in suggestions if s.action == "limiter"]
        assert len(limiter_suggestions) >= 1

        # Step 3: Apply
        new_config = mixer.apply(config, suggestions)
        vocal = new_config["tracks"][0]
        assert len(vocal["effects"]) > 0

    def test_full_pipeline_sibilance(self) -> None:
        """Full pipeline should detect sibilance and add DeEsser."""
        events = [
            StreamEvent(
                event_type="track_level",
                timestamp_ms=100.0,
                track="vocal",
                data={"rms_db": -18.0, "peak_db": -6.0, "true_peak_db": -5.5},
            ),
            StreamEvent(
                event_type="sibilance",
                timestamp_ms=110.0,
                level=EventLevel.WARNING,
                track="vocal",
                data={"sibilance_db": -18.0, "threshold_db": -20.0, "exceeds": True},
            ),
            StreamEvent(
                event_type="warning",
                timestamp_ms=120.0,
                level=EventLevel.WARNING,
                track="vocal",
                data={"warning_type": "sibilance", "message": "Sibilance detected"},
            ),
        ]

        config = {
            "name": "test",
            "bpm": 120,
            "tracks": [
                {"name": "vocal", "file": "vocal.wav", "effects": [
                    {"name": "vc-gain", "params": {"gain": 0}},
                ]},
            ],
            "master": {"levels": {"vocal": 1.0}, "effects": [], "output": "out.wav"},
        }

        mixer = AutoMixer()
        state = mixer.analyze(events)
        assert state.has_sibilance is True
        assert state.tracks["vocal"].sibilance_exceeds is True

        suggestions = mixer.suggest(state)
        deesser = [s for s in suggestions if s.action == "deesser"]
        assert len(deesser) >= 1

        new_config = mixer.apply(config, suggestions)
        vocal = new_config["tracks"][0]
        has_deesser = any(e["name"] == "vc-deesser" for e in vocal["effects"])
        assert has_deesser

    def test_datastream_dict_format_pipeline(self) -> None:
        """Pipeline should work with DataStream in dict format."""
        ds = DataStream(format="dict")
        ds.start()
        ds.emit_track_level("vocal", rms_db=-24.0, peak_db=-10.0, true_peak_db=-9.5)
        ds.emit_track_level("bass", rms_db=-15.0, peak_db=-4.0, true_peak_db=-3.5)
        ds.emit_master_level(rms_db=-12.0, peak_db=-3.0, true_peak_db=-2.5)
        ds.emit_warning("vocal", "low_snr", "RMS below -36 dBFS")

        events = ds.get_events()

        mixer = AutoMixer()
        state = mixer.analyze(events)

        assert "vocal" in state.tracks
        assert "bass" in state.tracks
        assert state.has_low_snr is True

        suggestions = mixer.suggest(state)
        assert len(suggestions) > 0
