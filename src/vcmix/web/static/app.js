/**
 * VCMix Web UI — Minimal vanilla JS frontend (Phase 8)
 *
 * No frameworks, just fetch API + vanilla JS + WebSocket.
 */

// ── API Base URL ────────────────────────────────────────────────────────
const API = '/api';

// ── Tab Navigation ──────────────────────────────────────────────────────
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
    });
});

// ── Default YAML ────────────────────────────────────────────────────────
const DEFAULT_YAML = `name: My Project
bpm: 120
sample_rate: 44100

tracks:
  - name: vocal
    file: vocal.wav
    effects:
      - name: vc-deesser
        params:
          threshold: -40
          reduction: -6
      - name: vc-eq
        params:
          low_cut: 80
          high_shelf: 8000
          peak_freq: 2500
          peak_gain: -2
      - name: vc-comp
        params:
          threshold: -24
          ratio: 3
          attack: 5
          release: 50
      - name: vc-reverb
        params:
          room: 30
          decay: 35
          damping: 50
          mix: 10
          predelay: 50
          wetlpf: 5000
      - name: vc-limiter
        params:
          ceiling: -1

master:
  levels:
    vocal: 0.8
  effects: []
  output: output.wav
`;

const yamlEditor = document.getElementById('yaml-editor');
if (!yamlEditor.value) yamlEditor.value = DEFAULT_YAML;

// ── Helper: show result in box ──────────────────────────────────────────
function showResult(elementId, content, cssClass = 'info') {
    const el = document.getElementById(elementId);
    el.textContent = content;
    el.className = 'result-box ' + cssClass;
}

function hideResult(elementId) {
    const el = document.getElementById(elementId);
    el.className = 'result-box hidden';
}

// ── Validate YAML ───────────────────────────────────────────────────────
document.getElementById('btn-validate').addEventListener('click', async () => {
    const yaml = yamlEditor.value;
    if (!yaml.trim()) {
        showResult('validate-result', 'Please enter YAML content', 'invalid');
        return;
    }

    try {
        const resp = await fetch(`${API}/validate?yaml_content=${encodeURIComponent(yaml)}`, {
            method: 'POST',
        });
        const data = await resp.json();

        if (data.valid) {
            showResult('validate-result',
                `✅ Valid!\nProject: ${data.project}\nTracks: ${data.tracks}\nBPM: ${data.bpm}\nSample Rate: ${data.sample_rate}`,
                'valid'
            );
        } else {
            const issues = data.issues ? data.issues.join('\n') : data.error || 'Unknown error';
            showResult('validate-result', `❌ Validation failed:\n${issues}`, 'invalid');
        }
    } catch (err) {
        showResult('validate-result', `Request failed: ${err.message}`, 'invalid');
    }
});

// ── Render from YAML Editor ─────────────────────────────────────────────
document.getElementById('btn-render-editor').addEventListener('click', async () => {
    const yaml = yamlEditor.value;
    if (!yaml.trim()) {
        showResult('render-result', 'Please enter YAML content', 'invalid');
        // Switch to render tab to show
        return;
    }

    try {
        const resp = await fetch(`${API}/render`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                project_yaml: yaml,
                report: false,
                auto_fix: false,
                ab_mode: false,
                arrangement_aware: false,
            }),
        });
        const data = await resp.json();

        if (data.job_id) {
            showResult('render-result', `Job started: ${data.job_id}\n${data.message}`, 'info');
            // Switch to render tab and poll
            switchToTab('render');
            pollRenderStatus(data.job_id);
        } else {
            showResult('render-result', `Error: ${JSON.stringify(data)}`, 'invalid');
        }
    } catch (err) {
        showResult('render-result', `Request failed: ${err.message}`, 'invalid');
    }
});

// ── Render from File ────────────────────────────────────────────────────
document.getElementById('btn-render-file').addEventListener('click', async () => {
    const path = document.getElementById('render-path').value;
    if (!path.trim()) {
        showResult('render-result', 'Please enter a project file path', 'invalid');
        return;
    }

    const report = document.getElementById('render-report').checked;
    const autoFix = document.getElementById('render-autofix').checked;
    const abMode = document.getElementById('render-ab').checked;
    const arrAware = document.getElementById('render-arrangement').checked;

    try {
        const params = new URLSearchParams({ project_path: path });
        if (report) params.set('report', 'true');
        if (autoFix) params.set('auto_fix', 'true');
        if (abMode) params.set('ab_mode', 'true');
        if (arrAware) params.set('arrangement_aware', 'true');

        const resp = await fetch(`${API}/render/file?${params}`, { method: 'POST' });
        const data = await resp.json();

        if (data.job_id) {
            showResult('render-result', `Job started: ${data.job_id}\n${data.message}`, 'info');
            pollRenderStatus(data.job_id);
        } else {
            showResult('render-result', `Error: ${JSON.stringify(data)}`, 'invalid');
        }
    } catch (err) {
        showResult('render-result', `Request failed: ${err.message}`, 'invalid');
    }
});

// ── Poll Render Status ──────────────────────────────────────────────────
let currentJobId = null;

async function pollRenderStatus(jobId) {
    currentJobId = jobId;
    const poll = async () => {
        try {
            const resp = await fetch(`${API}/render/${jobId}`);
            const data = await resp.json();

            let statusText = `Job: ${data.job_id}\nStatus: ${data.status}`;
            if (data.output_path) statusText += `\nOutput: ${data.output_path}`;
            if (data.elapsed_s) statusText += `\nElapsed: ${data.elapsed_s}s`;
            if (data.error) statusText += `\nError: ${data.error}`;

            const cssClass = data.status === 'completed' ? 'valid' :
                             data.status === 'failed' ? 'invalid' : 'info';
            showResult('render-result', statusText, cssClass);

            // Show events
            if (data.events && data.events.length > 0) {
                const eventsBox = document.getElementById('render-events');
                eventsBox.classList.remove('hidden');
                const eventsList = document.getElementById('events-list');
                eventsList.innerHTML = data.events.map(e => {
                    const ts = e.ts ? e.ts.toFixed(1) : '';
                    return `<div class="event-item">
                        <span class="type">[${e.type}]</span>
                        <span class="track">${e.track || ''}</span>
                        <span class="data">${JSON.stringify(e).substring(0, 120)}</span>
                    </div>`;
                }).join('');
            }

            if (data.status === 'pending' || data.status === 'running') {
                setTimeout(poll, 1500);
            }
        } catch (err) {
            showResult('render-result', `Poll failed: ${err.message}`, 'invalid');
        }
    };
    poll();
}

// ── Refresh Status ──────────────────────────────────────────────────────
document.getElementById('btn-render-status').addEventListener('click', () => {
    if (currentJobId) {
        pollRenderStatus(currentJobId);
    } else {
        showResult('render-result', 'No active job. Start a render first.', 'info');
    }
});

// ── Load Plugins ────────────────────────────────────────────────────────
async function loadPlugins() {
    try {
        const resp = await fetch(`${API}/plugins`);
        const data = await resp.json();
        const grid = document.getElementById('plugins-list');
        grid.innerHTML = data.plugins.map(p => `
            <div class="card">
                <h3>${p.name}</h3>
                <p>${p.description || 'VC Plugin'}</p>
            </div>
        `).join('');
    } catch (err) {
        document.getElementById('plugins-list').innerHTML =
            `<p style="color:var(--error)">Failed to load plugins: ${err.message}</p>`;
    }
}

// ── Load Presets ────────────────────────────────────────────────────────
async function loadPresets() {
    try {
        const resp = await fetch(`${API}/presets`);
        const data = await resp.json();
        const grid = document.getElementById('presets-list');
        grid.innerHTML = data.presets.map(p => `
            <div class="card" onclick="showPresetDetail('${p.name}')">
                <h3>${p.name}</h3>
                <p>${p.effect_count} effects</p>
            </div>
        `).join('');
    } catch (err) {
        document.getElementById('presets-list').innerHTML =
            `<p style="color:var(--error)">Failed to load presets: ${err.message}</p>`;
    }
}

async function showPresetDetail(name) {
    try {
        const resp = await fetch(`${API}/presets/${name}`);
        const data = await resp.json();
        const effects = data.effects.map((e, i) => {
            const params = Object.entries(e.params || {})
                .map(([k, v]) => `${k}=${v}`)
                .join(', ');
            return `  ${i + 1}. ${e.name} (${params})`;
        }).join('\n');
        showResult('preset-detail', `Preset: ${name}\n${effects}`, 'info');
    } catch (err) {
        showResult('preset-detail', `Failed: ${err.message}`, 'invalid');
    }
}

// ── WebSocket DataStream ────────────────────────────────────────────────
let ws = null;
const wsStatus = document.getElementById('ws-status');
const streamLog = document.getElementById('stream-log');
const meterGrid = document.getElementById('level-meters');

function connectWebSocket() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${location.host}${API}/stream`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        wsStatus.textContent = 'Connected';
        wsStatus.className = 'status-badge connected';
        addLogEntry('system', 'WebSocket connected');
    };

    ws.onclose = () => {
        wsStatus.textContent = 'Disconnected';
        wsStatus.className = 'status-badge disconnected';
        addLogEntry('system', 'WebSocket disconnected');
    };

    ws.onerror = (err) => {
        addLogEntry('error', 'WebSocket error');
    };

    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            handleStreamEvent(data);
        } catch (e) {
            addLogEntry('error', `Parse error: ${e.message}`);
        }
    };
}

function handleStreamEvent(data) {
    const type = data.type || 'unknown';
    const ts = data.ts ? new Date(data.ts).toISOString().substr(11, 12) : '';

    // Add to log
    addLogEntry(type, JSON.stringify(data).substring(0, 200), ts);

    // Update level meters for track_level and master_level events
    if (type === 'track_level' || type === 'master_level') {
        updateMeter(data.track || 'unknown', data.rms_db, data.peak_db);
    }

    // Highlight warnings
    if (type === 'warning') {
        addLogEntry('⚠️ WARNING', `${data.track}: ${data.message}`, ts);
    }
}

function updateMeter(name, rmsDb, peakDb) {
    // Create or update meter card
    let card = document.getElementById('meter-' + name);
    if (!card) {
        card = document.createElement('div');
        card.id = 'meter-' + name;
        card.className = 'meter-card';
        card.innerHTML = `
            <div class="name">${name}</div>
            <div class="meter-bar"><div class="meter-fill" style="width:0%"></div></div>
            <div class="values">RMS: -- dB | Peak: -- dB</div>
        `;
        meterGrid.appendChild(card);
    }

    // Convert dB to percentage (0 dB = 100%, -60 dB = 0%)
    const pct = Math.max(0, Math.min(100, ((rmsDb || -60) + 60) / 60 * 100));
    const fill = card.querySelector('.meter-fill');
    fill.style.width = pct + '%';

    // Color based on level
    fill.className = 'meter-fill';
    if (peakDb > -1) fill.classList.add('clip');
    else if (peakDb > -6) fill.classList.add('warn');

    card.querySelector('.values').textContent =
        `RMS: ${(rmsDb || -60).toFixed(1)} dB | Peak: ${(peakDb || -60).toFixed(1)} dB`;
}

function addLogEntry(type, message, ts = '') {
    const entry = document.createElement('div');
    entry.className = 'log-entry';
    entry.innerHTML = `<span class="ts">${ts}</span> <span class="type">[${type}]</span> ${message}`;
    streamLog.appendChild(entry);
    streamLog.scrollTop = streamLog.scrollHeight;
}

// ── WebSocket Controls ──────────────────────────────────────────────────
document.getElementById('btn-ws-connect').addEventListener('click', () => {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.close();
    } else {
        connectWebSocket();
    }
});

document.getElementById('btn-ws-clear').addEventListener('click', () => {
    streamLog.innerHTML = '';
    meterGrid.innerHTML = '';
});

// ── Switch Tab Helper ───────────────────────────────────────────────────
function switchToTab(tabName) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');
    document.getElementById('tab-' + tabName).classList.add('active');
}

// ── Initialize on load ─────────────────────────────────────────────────
loadPlugins();
loadPresets();
