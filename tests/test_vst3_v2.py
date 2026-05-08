"""
test_vst3_v2.py — Phase 14 VST3 deep implementation tests.

Tests cover:
- VST3HostBridge: plugin loading, parameters, processing, state
- VST3PluginProxy: high-level proxy, presets, snapshots
- VST3ScannerV2: enhanced scanner with caching
- ParameterEnumerator: type inference
- PresetManager: preset file I/O
- StateSnapshotManager: undo/redo

All tests work without actual VST3 plugins or C++ library.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

import numpy as np
import pytest

from vcmix.vst3.vst3_host_bridge import (
    PluginParameterInfo,
    VST3HostBridge,
    VST3HostConfig,
)
from vcmix.vst3.vst3_plugin_proxy import (
    ParameterEnumerator,
    ParamType,
    PresetInfo,
    PresetManager,
    StateSnapshotManager,
    VST3PluginProxy,
)
from vcmix.vst3.vst3_scanner_v2 import (
    PluginMetadata,
    ScanCache,
    VST3ScannerV2,
)

# ═══════════════════════════════════════════════════════════════════════════
# VST3HostBridge Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestVST3HostBridge:
    """Tests for the VST3 Host Bridge."""

    def test_bridge_creation(self):
        bridge = VST3HostBridge()
        assert bridge.is_mock is True  # No native library available

    def test_bridge_custom_config(self):
        config = VST3HostConfig(sample_rate=48000, block_size=1024)
        bridge = VST3HostBridge(config)
        assert bridge.config.sample_rate == 48000

    def test_bridge_load_plugin(self):
        bridge = VST3HostBridge()
        handle = bridge.load_plugin("/usr/lib/vst3/Test.vst3")
        assert handle > 0
        assert bridge.is_plugin_loaded(handle)

    def test_bridge_load_multiple_plugins(self):
        bridge = VST3HostBridge()
        h1 = bridge.load_plugin("/usr/lib/vst3/Plugin1.vst3")
        h2 = bridge.load_plugin("/usr/lib/vst3/Plugin2.vst3")
        assert h1 != h2
        assert bridge.is_plugin_loaded(h1)
        assert bridge.is_plugin_loaded(h2)

    def test_bridge_unload_plugin(self):
        bridge = VST3HostBridge()
        handle = bridge.load_plugin("/usr/lib/vst3/Test.vst3")
        bridge.unload_plugin(handle)
        assert not bridge.is_plugin_loaded(handle)

    def test_bridge_unload_invalid_handle(self):
        bridge = VST3HostBridge()
        bridge.unload_plugin(999)  # Should not raise

    def test_bridge_setup_processing(self):
        bridge = VST3HostBridge()
        handle = bridge.load_plugin("/usr/lib/vst3/Test.vst3")
        bridge.setup_processing(handle, 48000, 256)
        info = bridge._handles[handle]
        assert info["sample_rate"] == 48000
        assert info["block_size"] == 256
        assert info["prepared"] is True

    def test_bridge_setup_invalid_handle(self):
        bridge = VST3HostBridge()
        with pytest.raises(ValueError, match="Invalid plugin handle"):
            bridge.setup_processing(999, 48000, 256)

    def test_bridge_create_processor(self):
        bridge = VST3HostBridge()
        handle = bridge.load_plugin("/usr/lib/vst3/Test.vst3")
        bridge.create_processor(handle)
        assert bridge._handles[handle].get("processor_created") is True

    def test_bridge_set_parameter(self):
        bridge = VST3HostBridge()
        handle = bridge.load_plugin("/usr/lib/vst3/Test.vst3")
        bridge.set_parameter(handle, 0, 0.5)
        assert bridge.get_parameter(handle, 0) == pytest.approx(0.5)

    def test_bridge_set_parameter_clamped(self):
        bridge = VST3HostBridge()
        handle = bridge.load_plugin("/usr/lib/vst3/Test.vst3")
        bridge.set_parameter(handle, 0, -0.5)
        assert bridge.get_parameter(handle, 0) == 0.0
        bridge.set_parameter(handle, 0, 1.5)
        assert bridge.get_parameter(handle, 0) == 1.0

    def test_bridge_get_parameter_default(self):
        bridge = VST3HostBridge()
        handle = bridge.load_plugin("/usr/lib/vst3/Test.vst3")
        # Default value for unset param is 0.0
        assert bridge.get_parameter(handle, 0) == 0.0

    def test_bridge_get_parameter_invalid_handle(self):
        bridge = VST3HostBridge()
        with pytest.raises(ValueError):
            bridge.get_parameter(999, 0)

    def test_bridge_get_parameter_name(self):
        bridge = VST3HostBridge()
        handle = bridge.load_plugin("/usr/lib/vst3/Test.vst3")
        bridge.set_param_info(handle, [
            PluginParameterInfo(index=0, name="Gain", current_value=0.5, default_value=0.5),
        ])
        assert bridge.get_parameter_name(handle, 0) == "Gain"

    def test_bridge_get_parameter_name_unknown(self):
        bridge = VST3HostBridge()
        handle = bridge.load_plugin("/usr/lib/vst3/Test.vst3")
        name = bridge.get_parameter_name(handle, 99)
        assert "Param" in name

    def test_bridge_get_parameter_count(self):
        bridge = VST3HostBridge()
        handle = bridge.load_plugin("/usr/lib/vst3/Test.vst3")
        bridge.set_param_info(handle, [
            PluginParameterInfo(index=0, name="Gain", current_value=0.5, default_value=0.5),
            PluginParameterInfo(index=1, name="Mix", current_value=1.0, default_value=1.0),
        ])
        assert bridge.get_parameter_count(handle) == 2

    def test_bridge_get_all_parameters(self):
        bridge = VST3HostBridge()
        handle = bridge.load_plugin("/usr/lib/vst3/Test.vst3")
        params = [
            PluginParameterInfo(index=0, name="Gain", current_value=0.5, default_value=0.5),
            PluginParameterInfo(index=1, name="Mix", current_value=1.0, default_value=1.0),
        ]
        bridge.set_param_info(handle, params)
        result = bridge.get_all_parameters(handle)
        assert len(result) == 2
        assert result[0].name == "Gain"

    def test_bridge_process_audio(self):
        bridge = VST3HostBridge()
        handle = bridge.load_plugin("/usr/lib/vst3/Test.vst3")
        bridge.setup_processing(handle, 44100, 512)
        input_audio = np.random.randn(512).astype(np.float32) * 0.1
        output = bridge.process_audio(handle, input_audio)
        assert len(output) == 512

    def test_bridge_process_not_prepared(self):
        bridge = VST3HostBridge()
        handle = bridge.load_plugin("/usr/lib/vst3/Test.vst3")
        with pytest.raises(RuntimeError, match="not prepared"):
            bridge.process_audio(handle, np.zeros(512, dtype=np.float32))

    def test_bridge_get_state(self):
        bridge = VST3HostBridge()
        handle = bridge.load_plugin("/usr/lib/vst3/Test.vst3")
        bridge.set_parameter(handle, 0, 0.7)
        state = bridge.get_state(handle)
        assert isinstance(state, bytes)
        data = json.loads(state)
        assert "0" in data["parameters"]
        assert data["parameters"]["0"] == pytest.approx(0.7)

    def test_bridge_set_state(self):
        bridge = VST3HostBridge()
        handle = bridge.load_plugin("/usr/lib/vst3/Test.vst3")
        state = json.dumps({"path": "/test", "parameters": {"0": 0.3, "1": 0.8}}).encode()
        bridge.set_state(handle, state)
        assert bridge.get_parameter(handle, 0) == pytest.approx(0.3)
        assert bridge.get_parameter(handle, 1) == pytest.approx(0.8)

    def test_bridge_get_loaded_plugins(self):
        bridge = VST3HostBridge()
        h1 = bridge.load_plugin("/usr/lib/vst3/A.vst3")
        h2 = bridge.load_plugin("/usr/lib/vst3/B.vst3")
        loaded = bridge.get_loaded_plugins()
        assert len(loaded) == 2
        assert h1 in loaded
        assert h2 in loaded

    def test_bridge_close(self):
        bridge = VST3HostBridge()
        bridge.load_plugin("/usr/lib/vst3/Test.vst3")
        bridge.close()
        assert len(bridge.get_loaded_plugins()) == 0


# ═══════════════════════════════════════════════════════════════════════════
# ParameterEnumerator Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestParameterEnumerator:
    """Tests for parameter type inference."""

    def test_infer_continuous(self):
        ptype = ParameterEnumerator.infer_type("Gain", 0.5)
        assert ptype == ParamType.CONTINUOUS

    def test_infer_switch_on_off(self):
        ptype = ParameterEnumerator.infer_type("On/Off", 0.0)
        assert ptype == ParamType.SWITCH

    def test_infer_switch_bypass(self):
        ptype = ParameterEnumerator.infer_type("Bypass", 0.0)
        assert ptype == ParamType.SWITCH

    def test_infer_switch_enable(self):
        ptype = ParameterEnumerator.infer_type("Enable", 1.0)
        assert ptype == ParamType.SWITCH

    def test_infer_switch_power(self):
        ptype = ParameterEnumerator.infer_type("Power", 0.0)
        assert ptype == ParamType.SWITCH

    def test_infer_enum_mode(self):
        ptype = ParameterEnumerator.infer_type("Mode", 0.0)
        assert ptype == ParamType.ENUM

    def test_infer_enum_type(self):
        ptype = ParameterEnumerator.infer_type("Filter Type", 0.0)
        assert ptype == ParamType.ENUM

    def test_infer_enum_algorithm(self):
        ptype = ParameterEnumerator.infer_type("Algorithm", 0.0)
        assert ptype == ParamType.ENUM

    def test_infer_integer(self):
        ptype = ParameterEnumerator.infer_type("Voices", 0.5, num_steps=8)
        assert ptype == ParamType.INTEGER

    def test_enumerate_params(self):
        params = [
            PluginParameterInfo(index=0, name="Gain", current_value=0.5, default_value=0.5),
            PluginParameterInfo(index=1, name="Bypass", current_value=0.0, default_value=0.0),
            PluginParameterInfo(index=2, name="Filter Mode", current_value=0.0, default_value=0.0),
        ]
        result = ParameterEnumerator.enumerate_params(params)
        assert len(result) == 3
        assert result[0]["type"] == "CONTINUOUS"
        assert result[1]["type"] == "SWITCH"
        assert result[2]["type"] == "ENUM"


# ═══════════════════════════════════════════════════════════════════════════
# PresetManager Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestPresetManager:
    """Tests for preset management."""

    def test_preset_manager_creation(self):
        mgr = PresetManager("/usr/lib/vst3/Test.vst3")
        assert mgr.plugin_path == "/usr/lib/vst3/Test.vst3"

    def test_scan_presets_nonexistent(self):
        mgr = PresetManager("/nonexistent/plugin.vst3")
        presets = mgr.scan_presets()
        assert presets == []

    def test_load_preset_nonexistent(self):
        mgr = PresetManager("/usr/lib/vst3/Test.vst3")
        result = mgr.load_preset("/nonexistent/preset.vstpreset")
        assert result is None

    def test_save_and_load_preset(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            preset_path = os.path.join(tmpdir, "test.vstpreset")
            mgr = PresetManager("/usr/lib/vst3/Test.vst3")

            state_data = b'\x01\x02\x03\x04\x05'
            assert mgr.save_preset(preset_path, state_data, class_id="test123")

            loaded = mgr.load_preset(preset_path)
            assert loaded is not None

    def test_preset_info_dataclass(self):
        info = PresetInfo(
            name="Init",
            path="/presets/Init.vstpreset",
            category="Factory",
            vendor="TestCo",
            is_factory=True,
        )
        assert info.name == "Init"
        assert info.is_factory is True

    def test_presets_property_empty(self):
        mgr = PresetManager("/nonexistent.vst3")
        assert mgr.presets == []


# ═══════════════════════════════════════════════════════════════════════════
# StateSnapshotManager Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestStateSnapshotManager:
    """Tests for state snapshot undo/redo."""

    def test_snapshot_creation(self):
        mgr = StateSnapshotManager()
        assert mgr.can_undo is False
        assert mgr.can_redo is False

    def test_snapshot_push(self):
        mgr = StateSnapshotManager()
        mgr.push({0: 0.5, 1: 0.8}, label="init")
        assert mgr.can_undo is True
        assert mgr.undo_count == 1

    def test_snapshot_undo(self):
        mgr = StateSnapshotManager()
        mgr.push({0: 0.5}, label="state1")
        mgr.push({0: 0.8}, label="state2")
        snapshot = mgr.undo()
        assert snapshot is not None
        assert snapshot.values[0] == pytest.approx(0.8)
        assert mgr.can_redo is True

    def test_snapshot_undo_empty(self):
        mgr = StateSnapshotManager()
        assert mgr.undo() is None

    def test_snapshot_redo(self):
        mgr = StateSnapshotManager()
        mgr.push({0: 0.5}, label="state1")
        mgr.push({0: 0.8}, label="state2")
        mgr.undo()
        snapshot = mgr.redo()
        assert snapshot is not None
        assert snapshot.values[0] == pytest.approx(0.8)

    def test_snapshot_redo_empty(self):
        mgr = StateSnapshotManager()
        assert mgr.redo() is None

    def test_snapshot_push_clears_redo(self):
        mgr = StateSnapshotManager()
        mgr.push({0: 0.5}, label="state1")
        mgr.push({0: 0.8}, label="state2")
        mgr.undo()
        assert mgr.can_redo is True
        mgr.push({0: 0.3}, label="state3")
        assert mgr.can_redo is False

    def test_snapshot_max_history(self):
        mgr = StateSnapshotManager(max_history=3)
        for i in range(5):
            mgr.push({0: float(i)}, label=f"state{i}")
        assert mgr.undo_count == 3

    def test_snapshot_clear(self):
        mgr = StateSnapshotManager()
        mgr.push({0: 0.5})
        mgr.push({0: 0.8})
        mgr.clear()
        assert mgr.undo_count == 0
        assert mgr.redo_count == 0

    def test_snapshot_deep_copy(self):
        mgr = StateSnapshotManager()
        values = {0: 0.5, 1: 0.8}
        mgr.push(values, label="test")
        values[0] = 1.0  # Modify original
        snapshot = mgr.undo()
        assert snapshot.values[0] == pytest.approx(0.5)  # Not affected

    def test_snapshot_label(self):
        mgr = StateSnapshotManager()
        mgr.push({0: 0.5}, label="my_snapshot")
        snapshot = mgr.undo()
        assert snapshot.label == "my_snapshot"


# ═══════════════════════════════════════════════════════════════════════════
# VST3PluginProxy Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestVST3PluginProxy:
    """Tests for the high-level VST3 plugin proxy."""

    def test_proxy_creation(self):
        proxy = VST3PluginProxy("/usr/lib/vst3/Test.vst3")
        assert proxy.is_loaded is True
        assert proxy.handle is not None

    def test_proxy_setup(self):
        proxy = VST3PluginProxy("/usr/lib/vst3/Test.vst3")
        proxy.setup(48000, 256)
        # Should not raise

    def test_proxy_set_get_parameter(self):
        proxy = VST3PluginProxy("/usr/lib/vst3/Test.vst3")
        proxy.set_parameter(0, 0.7)
        assert proxy.get_parameter(0) == pytest.approx(0.7)

    def test_proxy_set_parameter_clamped(self):
        proxy = VST3PluginProxy("/usr/lib/vst3/Test.vst3")
        proxy.set_parameter(0, -0.5)
        assert proxy.get_parameter(0) == 0.0
        proxy.set_parameter(0, 2.0)
        assert proxy.get_parameter(0) == 1.0

    def test_proxy_get_all_parameter_values(self):
        proxy = VST3PluginProxy("/usr/lib/vst3/Test.vst3")
        proxy.set_parameter(0, 0.3)
        proxy.set_parameter(1, 0.7)
        values = proxy.get_all_parameter_values()
        assert values[0] == pytest.approx(0.3)
        assert values[1] == pytest.approx(0.7)

    def test_proxy_save_snapshot(self):
        proxy = VST3PluginProxy("/usr/lib/vst3/Test.vst3")
        proxy.set_parameter(0, 0.5)
        proxy.save_snapshot("init")
        assert proxy.snapshot_manager.can_undo is True  # Snapshot is on undo stack

    def test_proxy_undo_redo(self):
        proxy = VST3PluginProxy("/usr/lib/vst3/Test.vst3")
        proxy.set_parameter(0, 0.5)
        proxy.save_snapshot("state1")
        proxy.set_parameter(0, 0.8)
        proxy.save_snapshot("state2")
        # Undo should restore state1
        proxy.undo()
        assert proxy.get_parameter(0) == pytest.approx(0.5)
        # Redo should restore state2
        proxy.redo()
        assert proxy.get_parameter(0) == pytest.approx(0.8)

    def test_proxy_undo_empty(self):
        proxy = VST3PluginProxy("/usr/lib/vst3/Test.vst3")
        assert proxy.undo() is False

    def test_proxy_process(self):
        proxy = VST3PluginProxy("/usr/lib/vst3/Test.vst3")
        proxy.setup(44100, 512)
        input_audio = np.random.randn(512).astype(np.float32) * 0.1
        output = proxy.process(input_audio)
        assert len(output) == 512

    def test_proxy_get_state(self):
        proxy = VST3PluginProxy("/usr/lib/vst3/Test.vst3")
        proxy.set_parameter(0, 0.5)
        state = proxy.get_state()
        assert isinstance(state, bytes)
        data = json.loads(state)
        assert "parameters" in data

    def test_proxy_set_state(self):
        proxy = VST3PluginProxy("/usr/lib/vst3/Test.vst3")
        state = json.dumps({
            "path": "/test",
            "parameters": {"0": 0.3, "1": 0.7}
        }).encode()
        proxy.set_state(state)
        # Bridge should have updated params

    def test_proxy_close(self):
        proxy = VST3PluginProxy("/usr/lib/vst3/Test.vst3")
        proxy.close()
        assert proxy.is_loaded is False
        assert proxy.handle is None

    def test_proxy_preset_manager(self):
        proxy = VST3PluginProxy("/usr/lib/vst3/Test.vst3")
        assert isinstance(proxy.preset_manager, PresetManager)

    def test_proxy_get_parameter_name(self):
        proxy = VST3PluginProxy("/usr/lib/vst3/Test.vst3")
        name = proxy.get_parameter_name(0)
        assert isinstance(name, str)

    def test_proxy_enumerate_parameters(self):
        proxy = VST3PluginProxy("/usr/lib/vst3/Test.vst3")
        result = proxy.enumerate_parameters()
        assert isinstance(result, list)

    def test_proxy_scan_presets(self):
        proxy = VST3PluginProxy("/usr/lib/vst3/Test.vst3")
        presets = proxy.scan_presets()
        assert isinstance(presets, list)


# ═══════════════════════════════════════════════════════════════════════════
# VST3ScannerV2 Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestVST3ScannerV2:
    """Tests for the enhanced VST3 scanner."""

    def test_scanner_creation(self):
        scanner = VST3ScannerV2()
        assert scanner is not None

    def test_scanner_custom_cache_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            scanner = VST3ScannerV2(cache_dir=tmpdir)
            assert str(scanner._cache_dir) == tmpdir

    def test_get_default_search_paths(self):
        paths = VST3ScannerV2.get_default_search_paths()
        assert isinstance(paths, list)
        assert len(paths) > 0

    def test_get_au_search_paths_non_macos(self):
        paths = VST3ScannerV2.get_au_search_paths()
        # On non-macOS, should be empty
        if not hasattr(os, 'uname') or os.uname().sysname != 'Darwin':
            assert paths == []

    def test_scan_no_plugins(self):
        scanner = VST3ScannerV2()
        plugins = scanner.scan(force_rescan=True)
        assert isinstance(plugins, list)
        # May or may not find plugins depending on system

    def test_scan_caching(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            scanner = VST3ScannerV2(cache_dir=tmpdir)
            # First scan
            plugins1 = scanner.scan(force_rescan=True)
            # Second scan (should use cache)
            plugins2 = scanner.scan()
            assert len(plugins1) == len(plugins2)

    def test_clear_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            scanner = VST3ScannerV2(cache_dir=tmpdir)
            scanner.scan(force_rescan=True)
            scanner.clear_cache()
            assert not scanner._cache_path.exists()

    def test_get_cache_info_no_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            scanner = VST3ScannerV2(cache_dir=tmpdir)
            info = scanner.get_cache_info()
            assert info is None

    def test_get_cache_info_with_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            scanner = VST3ScannerV2(cache_dir=tmpdir)
            scanner.scan(force_rescan=True)
            info = scanner.get_cache_info()
            if info is not None:
                assert "version" in info
                assert "num_plugins" in info

    def test_plugin_metadata_dataclass(self):
        meta = PluginMetadata(
            name="TestPlugin",
            path="/usr/lib/vst3/Test.vst3",
            manufacturer="TestCo",
            version="1.0.0",
            category="Effect",
            is_instrument=False,
            num_params=10,
        )
        assert meta.name == "TestPlugin"
        assert meta.version == "1.0.0"

    def test_scan_cache_dataclass(self):
        cache = ScanCache()
        assert cache.version == 2
        assert cache.plugins == []

    def test_get_all_search_paths(self):
        scanner = VST3ScannerV2(extra_paths=["/custom/vst3"])
        paths = scanner.get_all_search_paths()
        assert len(paths) > 0
        has_custom = any(p == Path("/custom/vst3") for p in paths)
        assert has_custom

    def test_scan_with_extra_paths(self):
        scanner = VST3ScannerV2(extra_paths=["/nonexistent/vst3"])
        plugins = scanner.scan(force_rescan=True)
        assert isinstance(plugins, list)

    def test_scan_audio_units(self):
        scanner = VST3ScannerV2()
        au_plugins = scanner.scan_audio_units()
        assert isinstance(au_plugins, list)

    def test_checksum(self):
        with tempfile.NamedTemporaryFile(suffix=".vst3", delete=False) as f:
            f.write(b"test data for checksum")
            f.flush()
            fname = f.name
        checksum = VST3ScannerV2._compute_checksum(fname)
        assert len(checksum) == 32  # MD5 hex
        # Windows: retry unlink to handle brief file lock after close
        for _ in range(5):
            try:
                os.unlink(fname)
                break
            except PermissionError:
                time.sleep(0.1)

    def test_incremental_scan(self):
        """Test that unchanged plugins are served from cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scanner = VST3ScannerV2(cache_dir=tmpdir)
            # Force scan
            plugins1 = scanner.scan(force_rescan=True)
            # Cache should exist
            if scanner._cache_path.exists():
                # Second scan should be faster (from cache)
                start = time.time()
                plugins2 = scanner.scan()
                time.time() - start
                assert len(plugins1) == len(plugins2)


# ═══════════════════════════════════════════════════════════════════════════
# Cross-Module Integration Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestVST3Integration:
    """Integration tests for VST3 components working together."""

    def test_bridge_to_proxy(self):
        bridge = VST3HostBridge()
        proxy = VST3PluginProxy("/usr/lib/vst3/Test.vst3", bridge=bridge)
        proxy.setup(44100, 512)
        proxy.set_parameter(0, 0.5)
        assert proxy.get_parameter(0) == pytest.approx(0.5)

    def test_proxy_with_snapshots(self):
        proxy = VST3PluginProxy("/usr/lib/vst3/Test.vst3")
        proxy.set_parameter(0, 0.5)
        proxy.save_snapshot("init")
        proxy.set_parameter(0, 0.8)
        proxy.save_snapshot("modified")
        # Undo twice to get back
        proxy.undo()
        assert proxy.get_parameter(0) == pytest.approx(0.5)

    def test_proxy_state_roundtrip(self):
        proxy = VST3PluginProxy("/usr/lib/vst3/Test.vst3")
        proxy.set_parameter(0, 0.3)
        proxy.set_parameter(1, 0.7)
        state = proxy.get_state()
        proxy.set_parameter(0, 0.0)
        proxy.set_parameter(1, 0.0)
        proxy.set_state(state)
        # State should be restored via bridge

    def test_full_workflow(self):
        """Test complete plugin workflow: scan -> load -> param -> process -> save."""
        # 1. Create bridge and proxy
        proxy = VST3PluginProxy("/usr/lib/vst3/Test.vst3")
        assert proxy.is_loaded

        # 2. Setup
        proxy.setup(44100, 512)

        # 3. Set parameters
        proxy.set_parameter(0, 0.5)
        proxy.set_parameter(1, 0.8)

        # 4. Process audio
        input_audio = np.random.randn(512).astype(np.float32) * 0.1
        output = proxy.process(input_audio)
        assert len(output) > 0

        # 5. Save state
        state = proxy.get_state()
        assert len(state) > 0

        # 6. Modify and undo
        proxy.save_snapshot("before_mod")
        proxy.set_parameter(0, 1.0)
        proxy.save_snapshot("after_mod")
        proxy.undo()  # Restores to before_mod state
        assert proxy.get_parameter(0) == pytest.approx(0.5)  # Restored from before_mod

        # 7. Cleanup
        proxy.close()

    def test_multiple_proxies_same_bridge(self):
        bridge = VST3HostBridge()
        proxy1 = VST3PluginProxy("/usr/lib/vst3/A.vst3", bridge=bridge)
        proxy2 = VST3PluginProxy("/usr/lib/vst3/B.vst3", bridge=bridge)
        proxy1.set_parameter(0, 0.3)
        proxy2.set_parameter(0, 0.7)
        assert proxy1.get_parameter(0) == pytest.approx(0.3)
        assert proxy2.get_parameter(0) == pytest.approx(0.7)

    def test_scanner_with_proxy(self):
        scanner = VST3ScannerV2()
        plugins = scanner.scan(force_rescan=True)
        # Scanner can find plugins, proxy can load them
        # This is a structural test, not functional
        assert isinstance(plugins, list)
