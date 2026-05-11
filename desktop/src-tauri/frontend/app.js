/**
 * OpenDAW — Main App Entry
 * Initializes all components, manages global state
 */
const App = (() => {
    // ── Public API for components ──
    function setStatus(msg) {
        const el = document.getElementById('status-msg');
        if (el) el.textContent = msg;
    }

    function toast(msg, type = 'info') {
        const container = document.getElementById('toast-container');
        if (!container) return;
        const el = document.createElement('div');
        el.className = 'toast ' + type;
        el.textContent = msg;
        container.appendChild(el);
        setTimeout(() => el.remove(), 3500);
    }

    // ── Backend health ──
    async function checkBackendHealth() {
        try {
            const result = await TauriBridge.checkHealth();
            const dot = document.querySelector('#backend-status .dot');
            const txt = document.querySelector('#backend-status .status-text');
            if (dot && txt) {
                dot.className = 'dot ' + (result?.healthy ? 'online' : 'offline');
                txt.textContent = result?.message || 'Unknown';
            }
            return result?.healthy;
        } catch {
            return false;
        }
    }

    // ── Keyboard shortcuts ──
    function setupKeyboardShortcuts() {
        document.addEventListener('keydown', e => {
            const tag = document.activeElement?.tagName?.toLowerCase();
            if (tag === 'input' || tag === 'textarea' || tag === 'select') {
                if (e.key === 'Escape') document.activeElement.blur();
                return;
            }

            const ctrl = e.ctrlKey || e.metaKey;

            if (e.key === ' ') { e.preventDefault(); Transport.togglePlay(); return; }
            if (e.key === 'Home') { e.preventDefault(); Transport.rewind(); return; }
            if (e.key === 'r' && !ctrl) { e.preventDefault(); Transport.toggleRecord(); return; }
            if (ctrl && e.key === 'e') { e.preventDefault(); exportProject(); return; }
            if (ctrl && e.key === 'm') { e.preventDefault(); toggleMixer(); return; }
            if (ctrl && e.key === 'n') { e.preventDefault(); TrackList.addTrack('Track ' + (TrackList.getTracks().length + 1)); return; }
            if (ctrl && e.key === 'p') { e.preventDefault(); PianoKeyboard.toggle(); return; }
        });
    }

    function toggleMixer() {
        const panel = document.getElementById('mixer-panel');
        if (panel) {
            panel.classList.toggle('collapsed');
        }
    }

    async function exportProject() {
        toast('Export started', 'info');
        setStatus('Exporting…');
    }

    // ── Meter animation loop ──
    let meterRafId = null;
    function meterLoop() {
        if (Transport.isPlaying()) {
            Mixer.updateMeters();
        }
        meterRafId = requestAnimationFrame(meterLoop);
    }

    // ── Volume slider ──
    function setupVolumeSlider() {
        const slider = document.getElementById('volume-slider');
        const display = document.getElementById('volume-display');
        if (slider && display) {
            slider.addEventListener('input', (e) => {
                const vol = parseFloat(e.target.value);
                display.textContent = vol + ' dB';
                TauriBridge.setMasterVolume(vol).catch(() => {});
            });
        }
    }

    // ── Load WAV button ──
    function setupLoadWav() {
        const btn = document.getElementById('btn-load-wav');
        if (!btn) return;

        btn.addEventListener('click', async () => {
            if (TauriBridge.isTauri) {
                try {
                    const { open } = window.__TAURI_DIALOG__ || {};
                    if (open) {
                        const filePath = await open({
                            multiple: false,
                            filters: [{ name: 'Audio', extensions: ['wav', 'mp3', 'ogg', 'flac'] }]
                        });
                        if (filePath) {
                            await TauriBridge.loadAndPlay(filePath);
                            toast('Audio loaded: ' + filePath.split('/').pop(), 'success');
                        }
                    }
                } catch {
                    const path = prompt('Enter audio file path:');
                    if (path) await TauriBridge.loadAndPlay(path);
                }
            } else {
                const path = prompt('Enter audio file path:');
                if (path) {
                    await TauriBridge.loadAndPlay(path);
                    toast('Audio loaded', 'success');
                }
            }
        });
    }

    // ── Export button ──
    function setupExport() {
        const btn = document.getElementById('btn-export');
        if (btn) btn.addEventListener('click', exportProject);
    }

    // ── New project ──
    function setupNewProject() {
        const btn = document.getElementById('btn-new-project');
        if (btn) {
            btn.addEventListener('click', () => {
                const name = prompt('Project name:', 'New Project');
                if (name) {
                    TauriBridge.createProject(name).then(() => {
                        toast('Project created: ' + name, 'success');
                    }).catch(() => {
                        toast('Failed to create project', 'error');
                    });
                }
            });
        }
    }

    // ── Add demo tracks for visual demo ──
    function addDemoTracks() {
        const tracks = TrackList.getTracks();
        if (tracks.length > 0) return; // Don't add if tracks exist

        const demoTracks = [
            { name: 'Drums', type: 'audio' },
            { name: 'Bass', type: 'audio' },
            { name: 'Keys', type: 'midi' },
            { name: 'Vocals', type: 'audio' },
            { name: 'Synth Lead', type: 'midi' },
            { name: 'Guitar', type: 'audio' },
        ];

        demoTracks.forEach(t => TrackList.addTrack(t.name, t.type));
    }

    // ── Main init ──
    async function init() {
        // Init layout manager first
        LayoutManager.init();
        LayoutManager.onChange((newLayout) => {
            Arrangement.resize();
            TimelineRenderer.resize();
        });

        // Init all components
        TimelineRenderer.init();
        Transport.init();
        TrackList.init();
        Arrangement.init();
        Mixer.init();
        Inspector.init();
        PianoKeyboard.init();
        TouchHandler.init();

        // Setup UI
        setupKeyboardShortcuts();
        setupVolumeSlider();
        setupLoadWav();
        setupExport();
        setupNewProject();

        // Add demo tracks for visual demo
        addDemoTracks();

        // Start meter loop
        meterLoop();

        // Check backend health
        checkBackendHealth();
        setInterval(checkBackendHealth, 15000);

        setStatus('Ready — Space to play/stop');
    }

    // ── Boot ──
    document.addEventListener('DOMContentLoaded', init);

    return { setStatus, toast, checkBackendHealth };
})();
