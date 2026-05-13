/**
 * OpenDAW — Tauri Bridge
 * Unified interface for Tauri commands + HTTP API fallback
 */
const TauriBridge = (() => {
    const BACKEND_BASE = window.location.origin  // 同源部署：API和Web UI在同一端口;
    const API = BACKEND_BASE + '/api';
    const API_V1 = BACKEND_BASE + '/api/v1';
    const AGENT_API = API_V1 + '/agent';

    const isTauri = typeof window.__TAURI_INTERNALS__ !== 'undefined';

    async function invoke(cmd, args = {}) {
        if (isTauri) {
            try {
                return await window.__TAURI_INTERNALS__.invoke(cmd, args);
            } catch (e) {
                console.warn(`Tauri invoke ${cmd} failed:`, e);
                return null;
            }
        }
        return null;
    }

    async function fetchJSON(url, options = {}) {
        try {
            const resp = await fetch(url, {
                headers: { 'Content-Type': 'application/json' },
                ...options
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            return await resp.json();
        } catch (e) {
            console.warn(`Fetch ${url} failed:`, e);
            return null;
        }
    }

    // ── Transport ──
    async function play() {
        await invoke('audio_init', { sample_rate: 44100, buffer_size: 256 });
        return await invoke('audio_play');
    }

    async function stop() {
        return await invoke('audio_stop');
    }

    async function pause() {
        return await invoke('audio_pause');
    }

    async function setMasterVolume(db) {
        return await invoke('audio_set_master_volume', { volume_db: db });
    }

    async function loadAndPlay(filePath, trackId) {
        return await invoke('audio_load_and_play', {
            file_path: filePath,
            track_id: trackId || 'main'
        });
    }

    async function getAudioStatus() {
        return await invoke('audio_get_status');
    }

    // ── Engine ──
    async function engineStart(sampleRate, bufferSize) {
        return await invoke('engine_start', { sample_rate: sampleRate, buffer_size: bufferSize });
    }

    async function engineStop() {
        return await invoke('engine_stop');
    }

    async function engineGetState() {
        return await invoke('engine_get_state');
    }

    async function engineGetPosition() {
        return await invoke('engine_get_position');
    }

    async function engineSetPosition(pos) {
        return await invoke('engine_set_position', { pos });
    }

    async function engineSetTrackVolume(trackId, volumeDb) {
        return await invoke('engine_set_track_volume', { track_id: trackId, volume_db: volumeDb });
    }

    async function engineToggleTrackMute(trackId) {
        return await invoke('engine_toggle_track_mute', { track_id: trackId });
    }

    async function engineRegisterTrack(trackId) {
        return await invoke('engine_register_track', { track_id: trackId });
    }

    async function engineLoadWav(trackId, filePath) {
        return await invoke('engine_load_wav', { track_id: trackId, file_path: filePath });
    }

    // ── Projects (HTTP API) ──
    async function listProjects() {
        return await fetchJSON(API_V1 + '/projects');
    }

    async function getProject(id) {
        return await fetchJSON(API_V1 + '/projects/' + id);
    }

    async function createProject(name) {
        return await fetchJSON(API_V1 + '/projects', {
            method: 'POST',
            body: JSON.stringify({ name })
        });
    }

    async function addTrack(projectId, name, type) {
        return await fetchJSON(API_V1 + '/projects/' + projectId + '/tracks', {
            method: 'POST',
            body: JSON.stringify({ name, type })
        });
    }

    async function deleteTrack(projectId, trackName) {
        return await fetchJSON(API_V1 + '/projects/' + projectId + '/tracks/' + encodeURIComponent(trackName), {
            method: 'DELETE'
        });
    }

    // ── Render ──
    async function renderProject(yamlPath) {
        if (isTauri) {
            return await invoke('render_project', { yamlPath });
        }
        return await fetchJSON(API + '/render', {
            method: 'POST',
            body: JSON.stringify({ project_path: yamlPath })
        });
    }

    // ── Health ──
    async function checkHealth() {
        const result = await invoke('check_backend_health', { port: 8000 });
        if (result) return result;
        try {
            const resp = await fetch(API + '/health');
            return { healthy: resp.ok, message: resp.ok ? 'Backend ready' : 'Error' };
        } catch {
            return { healthy: false, message: 'Backend offline' };
        }
    }

    // ── Agent Chat ──
    async function agentChat(message, projectId) {
        if (isTauri) {
            return await invoke('agent_chat', { message, project_id: projectId });
        }
        return await fetchJSON(AGENT_API + '/chat', {
            method: 'POST',
            body: JSON.stringify({ message, project_id: projectId })
        });
    }

    // ── Waveform ──
    async function getWaveform(projectId, track) {
        return await invoke('get_waveform', { project_id: projectId, track });
    }

    return {
        isTauri,
        invoke,
        play, stop, pause,
        setMasterVolume, loadAndPlay, getAudioStatus,
        engineStart, engineStop, engineGetState,
        engineGetPosition, engineSetPosition,
        engineSetTrackVolume, engineToggleTrackMute,
        engineRegisterTrack, engineLoadWav,
        listProjects, getProject, createProject,
        addTrack, deleteTrack, renderProject,
        checkHealth, agentChat, getWaveform,
        API, API_V1, AGENT_API, BACKEND_BASE
    };
})();
