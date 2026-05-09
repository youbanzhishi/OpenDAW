/**
 * VCMix Web UI — Minimal vanilla JS frontend (Phase 9)
 *
 * No frameworks, just fetch API + vanilla JS + WebSocket.
 * Phase 9 adds: MIDI, Automation Curves, Chain Presets
 */

// ── API Base URL ────────────────────────────────────────────────────────
const API = '/api';
const API_V1 = '/api/v1';

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

// ═══════════════════════════════════════════════════════════════════════
// ── Phase 9: MIDI Tab ──────────────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════

// ── Scan for MIDI files ─────────────────────────────────────────────────
document.getElementById('btn-midi-scan').addEventListener('click', async () => {
    const dir = document.getElementById('midi-scan-dir').value || '.';
    try {
        const resp = await fetch(`${API}/midi/scan?directory=${encodeURIComponent(dir)}`);
        const data = await resp.json();
        const grid = document.getElementById('midi-files-list');

        if (data.count === 0) {
            grid.innerHTML = '<p style="color:var(--text-secondary)">No MIDI files found.</p>';
            return;
        }

        grid.innerHTML = data.files.map(f => `
            <div class="midi-file-item" onclick="selectMidiFile('${f.path.replace(/'/g, "\\'")}')">
                <div class="midi-name">🎹 ${f.name}</div>
                <div class="midi-size">${(f.size_bytes / 1024).toFixed(1)} KB</div>
            </div>
        `).join('');
    } catch (err) {
        document.getElementById('midi-files-list').innerHTML =
            `<p style="color:var(--error)">Scan failed: ${err.message}</p>`;
    }
});

function selectMidiFile(path) {
    document.getElementById('midi-file-path').value = path;
}

// ── Parse MIDI file ─────────────────────────────────────────────────────
document.getElementById('btn-midi-parse').addEventListener('click', async () => {
    const path = document.getElementById('midi-file-path').value;
    if (!path.trim()) {
        showResult('midi-info', 'Please enter or select a MIDI file path', 'invalid');
        return;
    }

    try {
        const resp = await fetch(`${API}/midi/parse`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: path }),
        });
        const data = await resp.json();

        if (resp.status !== 200) {
            showResult('midi-info', `❌ ${data.detail || 'Parse failed'}`, 'invalid');
            return;
        }

        const info = `🎹 MIDI File Parsed
BPM: ${data.bpm}
Time Signature: ${data.time_signature}
Ticks/Beat: ${data.ticks_per_beat}
Total Beats: ${data.total_beats}
Tracks: ${data.track_count}`;

        showResult('midi-info', info, 'valid');

        // Show note preview for each track
        const preview = document.getElementById('midi-notes-preview');
        const notesList = document.getElementById('midi-notes-list');
        preview.classList.remove('hidden');

        let html = '';
        for (const track of data.tracks) {
            html += `<div style="margin-bottom:0.75rem">
                <strong style="color:var(--accent)">${track.name}</strong>
                <span style="color:var(--text-secondary)"> (Ch ${track.channel}, ${track.note_count} notes, ${track.instrument})</span>
            </div>`;

            // Show first 50 notes
            const notes = track.notes.slice(0, 50);
            for (const n of notes) {
                html += `<div class="note-row">
                    <span class="note-pitch">${n.name}</span>
                    <span class="note-vel">vel:${n.velocity}</span>
                    <span class="note-time">beat:${n.start_beat.toFixed(2)}</span>
                    <span class="note-dur">dur:${n.duration_beats.toFixed(2)}</span>
                </div>`;
            }
            if (track.notes.length > 50) {
                html += `<div style="color:var(--text-secondary);font-size:0.75rem;padding:0.2rem">
                    ... and ${track.notes.length - 50} more notes
                </div>`;
            }
        }
        notesList.innerHTML = html;

    } catch (err) {
        showResult('midi-info', `Parse failed: ${err.message}`, 'invalid');
    }
});

// ── Load Synths list ────────────────────────────────────────────────────
async function loadSynths() {
    try {
        const resp = await fetch(`${API}/midi/synths`);
        const data = await resp.json();
        const select = document.getElementById('midi-synth-select');
        select.innerHTML = data.synths.map(s =>
            `<option value="${s.name}">${s.name} — ${s.description}</option>`
        ).join('');
    } catch (err) {
        console.warn('Failed to load synths:', err);
    }
}

// ═══════════════════════════════════════════════════════════════════════
// ── VC-Chain: Enhanced Chain Editor ───────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════

let selectedChainName = null;
let selectedChainData = null;

// ── Load VC-Chains (new API) ────────────────────────────────────────
async function loadChainPresets() {
    try {
        const resp = await fetch(`${API_V1}/chains`);
        const data = await resp.json();
        const grid = document.getElementById('chains-list');
        grid.innerHTML = data.chains.map(c => {
            const badges = [];
            if (c.has_parallel) badges.push('⟷ Parallel');
            if (c.has_multiband) badges.push('📊 Multiband');
            if (c.macro_count > 0) badges.push(`🎛️ ${c.macro_count} Macros`);
            const sourceIcon = c.source === 'builtin' ? '📦' : '👤';
            return `
                <div class="card" onclick="showVCChainDetail('${c.name}')">
                    <h3>${sourceIcon} ${c.name}</h3>
                    <p>${c.description || c.step_count + ' steps'}</p>
                    <div style="font-size:0.8rem;color:var(--text-secondary)">
                        Steps: ${c.step_count} | ${badges.join(' | ')}
                    </div>
                    <div class="chain-tags">
                        ${c.tags.map(t => `<span class="tag">${t}</span>`).join('')}
                    </div>
                </div>
            `;
        }).join('');
    } catch (err) {
        // Fallback to old API
        try {
            const resp = await fetch(`${API}/presets/chains`);
            const data = await resp.json();
            const grid = document.getElementById('chains-list');
            grid.innerHTML = data.chains.map(c => `
                <div class="card" onclick="showChainDetailLegacy('${c.name}')">
                    <h3>🔗 ${c.name}</h3>
                    <p>${c.description || c.effect_count + ' effects'}</p>
                    <div class="chain-tags">
                        ${c.tags.map(t => `<span class="tag">${t}</span>`).join('')}
                    </div>
                </div>
            `).join('');
        } catch (err2) {
            document.getElementById('chains-list').innerHTML =
                `<p style="color:var(--error)">Failed to load chains: ${err2.message}</p>`;
        }
    }
}

// ── Show VC-Chain Detail ─────────────────────────────────────────────
async function showVCChainDetail(name) {
    selectedChainName = name;
    document.getElementById('btn-chain-apply').disabled = false;
    document.getElementById('btn-xps-export').disabled = false;
    document.getElementById('btn-chainverse-upload').disabled = false;

    try {
        const resp = await fetch(`${API_V1}/chains/${name}`);
        const data = await resp.json();
        selectedChainData = data;

        // Build detail text
        let info = `🔗 VC-Chain: ${data.name}`;
        if (data.author) info += `\nAuthor: ${data.author}`;
        if (data.description) info += `\n${data.description}`;
        info += `\nVersion: ${data.version || '1.0'}`;

        // Serial chain
        if (data.chain && data.chain.serial) {
            info += `\n\n▶ Serial Chain:`;
            data.chain.serial.forEach((s, i) => {
                const params = s.params ? Object.entries(s.params).map(([k,v]) => `${k}=${v}`).join(', ') : '';
                info += `\n  ${i+1}. ${s.plugin}${params ? ' (' + params + ')' : ''}`;
            });
        }

        // Parallel branches
        if (data.chain && data.chain.parallel && data.chain.parallel.length > 0) {
            info += `\n\n⟷ Parallel Branches:`;
            data.chain.parallel.forEach((b, i) => {
                info += `\n  Branch ${i+1} (mix=${b.mix}):`;
                if (b.chain) {
                    b.chain.forEach((s, j) => {
                        const params = s.params ? Object.entries(s.params).map(([k,v]) => `${k}=${v}`).join(', ') : '';
                        info += `\n    ${j+1}. ${s.plugin}${params ? ' (' + params + ')' : ''}`;
                    });
                }
            });
        }

        // Multiband
        if (data.chain && data.chain.multiband) {
            const mb = data.chain.multiband;
            info += `\n\n📊 Multiband:`;
            if (mb.crossover) info += `\n  Crossover: ${mb.crossover.join(', ')} Hz`;
            if (mb.bands) {
                mb.bands.forEach((b, i) => {
                    info += `\n  Band ${i+1} (${b.range[0]}-${b.range[1]} Hz):`;
                    if (b.chain) {
                        b.chain.forEach((s, j) => {
                            info += `\n    ${j+1}. ${s.plugin}`;
                        });
                    }
                });
            }
        }

        showResult('chain-detail', info, 'info');

        // Render Macro knobs
        renderMacroKnobs(data.macro || []);

        // Render signal flow
        renderSignalFlow(data.signal_flow);

    } catch (err) {
        showResult('chain-detail', `Failed: ${err.message}`, 'invalid');
    }
}

// ── Legacy chain detail (old API fallback) ──────────────────────────
async function showChainDetailLegacy(name) {
    selectedChainName = name;
    document.getElementById('btn-chain-apply').disabled = false;

    try {
        const resp = await fetch(`${API}/presets/chains/${name}`);
        const data = await resp.json();

        const effects = data.effects.map((e, i) => {
            const params = Object.entries(e.params || {})
                .map(([k, v]) => `${k}=${v}`)
                .join(', ');
            return `  ${i + 1}. ${e.name} (${params})`;
        }).join('\n');

        const info = `🔗 Chain: ${data.name}\n${data.description}\nEffects (${data.effect_count}):\n${effects}`;
        showResult('chain-detail', info, 'info');
    } catch (err) {
        showResult('chain-detail', `Failed: ${err.message}`, 'invalid');
    }
}

// ── Render Macro Knobs ──────────────────────────────────────────────
function renderMacroKnobs(macros) {
    const panel = document.getElementById('macro-panel');
    const container = document.getElementById('macro-knobs');

    if (!macros || macros.length === 0) {
        panel.classList.add('hidden');
        return;
    }

    panel.classList.remove('hidden');
    container.innerHTML = macros.map((m, i) => `
        <div style="text-align:center;min-width:80px">
            <div style="font-size:0.75rem;color:var(--text-secondary);margin-bottom:4px">${m.name}</div>
            <input type="range" min="0" max="100" value="50"
                id="macro-${i}" data-macro-name="${m.name}"
                style="writing-mode:vertical-lr;height:80px;cursor:pointer"
                oninput="onMacroChange(${i}, this.value)">
            <div id="macro-value-${i}" style="font-size:0.7rem;color:var(--text-secondary)">0.50</div>
        </div>
    `).join('');
}

function onMacroChange(index, value) {
    const normalized = value / 100;
    document.getElementById(`macro-value-${index}`).textContent = normalized.toFixed(2);
}

function getMacroValues() {
    if (!selectedChainData || !selectedChainData.macro) return {};
    const values = {};
    selectedChainData.macro.forEach((m, i) => {
        const slider = document.getElementById(`macro-${i}`);
        if (slider) {
            values[m.name] = slider.value / 100;
        }
    });
    return values;
}

// ── Render Signal Flow ──────────────────────────────────────────────
function renderSignalFlow(flow) {
    const panel = document.getElementById('signal-flow-panel');
    const container = document.getElementById('signal-flow');

    if (!flow || !flow.stages || flow.stages.length === 0) {
        panel.classList.add('hidden');
        return;
    }

    panel.classList.remove('hidden');
    let text = '';

    flow.stages.forEach(stage => {
        if (stage.type === 'serial') {
            text += '▶ SERIAL: ';
            text += stage.steps.map(s => `[${s.plugin}]`).join(' → ');
            text += '\n';
        } else if (stage.type === 'parallel') {
            text += '⟷ PARALLEL:\n';
            stage.branches.forEach((b, i) => {
                text += `  Branch ${i+1} (mix=${b.mix}): `;
                text += b.chain.map(s => `[${s.plugin}]`).join(' → ');
                text += '\n';
            });
        } else if (stage.type === 'multiband') {
            text += '📊 MULTIBAND:\n';
            if (stage.crossover) text += `  Crossover: ${stage.crossover.join(', ')} Hz\n`;
            stage.bands.forEach((b, i) => {
                text += `  Band ${i+1}: `;
                text += b.chain.map(s => `[${s.plugin}]`).join(' → ');
                text += '\n';
            });
        }
    });

    container.textContent = text.trim();
}

// ── Apply Chain ──────────────────────────────────────────────────────
document.getElementById('btn-chain-apply').addEventListener('click', async () => {
    if (!selectedChainName) {
        showResult('chain-apply-result', 'Select a chain preset first', 'invalid');
        return;
    }

    const trackName = document.getElementById('chain-apply-track').value.trim();
    const trackFile = document.getElementById('chain-apply-file').value.trim();

    if (!trackName) {
        showResult('chain-apply-result', 'Please enter a track name', 'invalid');
        return;
    }

    try {
        const macroValues = getMacroValues();
        const resp = await fetch(`${API_V1}/chains/${selectedChainName}/apply`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                track_name: trackName,
                track_config: {
                    name: trackName,
                    file: trackFile || `${trackName}.wav`,
                    effects: [],
                },
                macro_values: Object.keys(macroValues).length > 0 ? macroValues : undefined,
            }),
        });
        const data = await resp.json();

        if (data.applied) {
            showResult('chain-apply-result',
                `✅ Chain "${data.chain_name}" applied to track "${data.track_name}"\n${data.effect_count} effects configured${data.macro_values_applied ? '\n🎛️ Macros applied' : ''}`,
                'valid'
            );
        } else {
            showResult('chain-apply-result', `❌ Apply failed: ${JSON.stringify(data)}`, 'invalid');
        }
    } catch (err) {
        showResult('chain-apply-result', `Apply failed: ${err.message}`, 'invalid');
    }
});

// ── .xps Import ─────────────────────────────────────────────────────
document.getElementById('btn-xps-import').addEventListener('click', async () => {
    const fileInput = document.getElementById('xps-import-file');
    if (!fileInput.files || fileInput.files.length === 0) {
        showResult('xps-result', 'Please select a .xps file', 'invalid');
        return;
    }

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);

    try {
        const resp = await fetch(`${API_V1}/chains/import/xps`, {
            method: 'POST',
            body: formData,
        });
        const data = await resp.json();

        if (data.imported) {
            showResult('xps-result',
                `✅ Imported "${data.name}" from .xps\n${data.step_count} steps, ${data.macro_count} macros\nAuthor: ${data.author || 'unknown'}`,
                'valid'
            );
            loadChainPresets(); // Refresh list
        } else {
            showResult('xps-result', `❌ Import failed: ${JSON.stringify(data.detail || data)}`, 'invalid');
        }
    } catch (err) {
        showResult('xps-result', `Import failed: ${err.message}`, 'invalid');
    }
});

// ── .xps Export ──────────────────────────────────────────────────────
document.getElementById('btn-xps-export').addEventListener('click', async () => {
    if (!selectedChainName) {
        showResult('xps-result', 'Select a chain first', 'invalid');
        return;
    }

    try {
        const resp = await fetch(`${API_V1}/chains/${selectedChainName}/export/xps`, {
            method: 'POST',
        });
        const data = await resp.json();

        if (data.exported) {
            showResult('xps-result',
                `✅ Exported "${data.name}" as .xps\nPath: ${data.xps_path}\n⚠️ Note: ${data.note}`,
                'valid'
            );
        } else {
            showResult('xps-result', `❌ Export failed: ${JSON.stringify(data.detail || data)}`, 'invalid');
        }
    } catch (err) {
        showResult('xps-result', `Export failed: ${err.message}`, 'invalid');
    }
});

// ── ChainVerse Search ───────────────────────────────────────────────
document.getElementById('btn-chainverse-search').addEventListener('click', async () => {
    const query = document.getElementById('chainverse-search').value.trim();
    if (!query) {
        document.getElementById('chainverse-results').innerHTML = '<p style="color:var(--text-secondary)">Enter a search query</p>';
        return;
    }

    try {
        const resp = await fetch(`${API_V1}/chainverse/search?q=${encodeURIComponent(query)}`);
        const data = await resp.json();
        const grid = document.getElementById('chainverse-results');

        if (data.count === 0) {
            grid.innerHTML = '<p style="color:var(--text-secondary)">No chains found. Try different keywords or upload one!</p>';
            return;
        }

        grid.innerHTML = data.results.map(e => `
            <div class="card">
                <h3>🌐 ${e.name}</h3>
                <p>by ${e.author || 'unknown'} | ⭐ ${e.rating.toFixed(1)} (${e.rating_count} ratings) | 📥 ${e.downloads}</p>
                <div class="chain-tags">
                    ${e.tags.map(t => `<span class="tag">${t}</span>`).join('')}
                </div>
            </div>
        `).join('');
    } catch (err) {
        document.getElementById('chainverse-results').innerHTML =
            `<p style="color:var(--error)">Search failed: ${err.message}</p>`;
    }
});

// ── ChainVerse Upload ───────────────────────────────────────────────
document.getElementById('btn-chainverse-upload').addEventListener('click', async () => {
    if (!selectedChainName) {
        showResult('chainverse-result', 'Select a chain first', 'invalid');
        return;
    }

    try {
        const resp = await fetch(`${API_V1}/chainverse/upload`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                chain_name: selectedChainName,
                author: selectedChainData?.author || 'anonymous',
            }),
        });
        const data = await resp.json();

        if (data.uploaded) {
            showResult('chainverse-result',
                `✅ Uploaded "${data.name}" to ChainVerse\nID: ${data.id}\nTags: ${data.tags.join(', ')}`,
                'valid'
            );
        } else {
            showResult('chainverse-result', `❌ Upload failed: ${JSON.stringify(data.detail || data)}`, 'invalid');
        }
    } catch (err) {
        showResult('chainverse-result', `Upload failed: ${err.message}`, 'invalid');
    }
});

// ═══════════════════════════════════════════════════════════════════════
// ── Phase 9: Automation Tab ────────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════

function parseAutoPoints() {
    const text = document.getElementById('auto-points-editor').value.trim();
    if (!text) return [];

    const points = [];
    for (const line of text.split('\n')) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith('#')) continue;
        const parts = trimmed.split(',').map(s => s.trim());
        if (parts.length >= 2) {
            points.push({
                time_beat: parseFloat(parts[0]),
                value: parseFloat(parts[1]),
                curve_type: parts[2] || 'linear',
            });
        }
    }
    return points;
}

// ── Preview Automation ──────────────────────────────────────────────────
document.getElementById('btn-auto-preview').addEventListener('click', async () => {
    const points = parseAutoPoints();
    if (points.length === 0) {
        showResult('auto-preview-result', 'Enter at least one control point', 'invalid');
        return;
    }

    // Generate query beats for visualization
    const minBeat = Math.min(...points.map(p => p.time_beat));
    const maxBeat = Math.max(...points.map(p => p.time_beat));
    const queryBeats = [];
    const step = Math.max(0.25, (maxBeat - minBeat) / 100);
    for (let b = minBeat; b <= maxBeat; b += step) {
        queryBeats.push(Math.round(b * 100) / 100);
    }

    try {
        const resp = await fetch(`${API}/automation/preview`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                points: points,
                query_beats: queryBeats,
                default_value: 0.0,
            }),
        });
        const data = await resp.json();

        if (resp.status !== 200) {
            showResult('auto-preview-result', `❌ ${data.detail || 'Preview failed'}`, 'invalid');
            return;
        }

        const info = `🎚️ Automation Curve Preview
Points: ${data.point_count}
Range: [${data.value_range[0].toFixed(2)}, ${data.value_range[1].toFixed(2)}]
Start Beat: ${data.start_beat} | End Beat: ${data.end_beat}`;

        showResult('auto-preview-result', info, 'info');

        // Draw curve on canvas
        if (data.values_at_beats && data.values_at_beats.length > 0) {
            drawAutomationCurve(data.values_at_beats, data.value_range);
        }

    } catch (err) {
        showResult('auto-preview-result', `Preview failed: ${err.message}`, 'invalid');
    }
});

// ── Draw Automation Curve ───────────────────────────────────────────────
function drawAutomationCurve(values, valueRange) {
    const vizDiv = document.getElementById('auto-curve-viz');
    vizDiv.classList.remove('hidden');
    const canvas = document.getElementById('auto-curve-canvas');
    const ctx = canvas.getContext('2d');

    const width = canvas.width;
    const height = canvas.height;
    const padding = 30;

    // Clear
    ctx.fillStyle = '#0d1117';
    ctx.fillRect(0, 0, width, height);

    if (values.length < 2) return;

    const minBeat = values[0].beat;
    const maxBeat = values[values.length - 1].beat;
    const minVal = valueRange[0];
    const maxVal = valueRange[1];
    const valSpan = maxVal - minVal || 1;
    const beatSpan = maxBeat - minBeat || 1;

    // Grid lines
    ctx.strokeStyle = '#1a2332';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
        const y = padding + (height - 2 * padding) * (i / 4);
        ctx.beginPath();
        ctx.moveTo(padding, y);
        ctx.lineTo(width - padding, y);
        ctx.stroke();

        // Label
        const val = maxVal - (valSpan * i / 4);
        ctx.fillStyle = '#a0a0b0';
        ctx.font = '10px monospace';
        ctx.fillText(val.toFixed(1), 2, y + 3);
    }

    // Draw curve
    ctx.strokeStyle = '#4fc3f7';
    ctx.lineWidth = 2;
    ctx.beginPath();

    for (let i = 0; i < values.length; i++) {
        const x = padding + ((values[i].beat - minBeat) / beatSpan) * (width - 2 * padding);
        const y = padding + (1 - (values[i].value - minVal) / valSpan) * (height - 2 * padding);

        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    }
    ctx.stroke();

    // Draw control points
    const points = parseAutoPoints();
    ctx.fillStyle = '#ffa726';
    for (const p of points) {
        const x = padding + ((p.time_beat - minBeat) / beatSpan) * (width - 2 * padding);
        const y = padding + (1 - (p.value - minVal) / valSpan) * (height - 2 * padding);
        ctx.beginPath();
        ctx.arc(x, y, 4, 0, Math.PI * 2);
        ctx.fill();
    }
}

// ── Apply Automation ────────────────────────────────────────────────────
document.getElementById('btn-auto-apply').addEventListener('click', async () => {
    const points = parseAutoPoints();
    if (points.length === 0) {
        showResult('auto-preview-result', 'Enter at least one control point', 'invalid');
        return;
    }

    const trackName = document.getElementById('auto-track-name').value.trim();
    const parameter = document.getElementById('auto-param-select').value;

    if (!trackName) {
        showResult('auto-preview-result', 'Enter a target track name', 'invalid');
        return;
    }

    try {
        const resp = await fetch(`${API}/automation/apply`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                track_name: trackName,
                parameter: parameter,
                points: points,
            }),
        });
        const data = await resp.json();

        if (data.applied) {
            showResult('auto-preview-result',
                `✅ Automation applied!\nTrack: ${data.track_name}\nParameter: ${data.parameter}\nPoints: ${data.point_count}\nRange: [${data.value_range[0].toFixed(2)}, ${data.value_range[1].toFixed(2)}]`,
                'valid'
            );
        } else {
            showResult('auto-preview-result', `❌ Apply failed: ${JSON.stringify(data)}`, 'invalid');
        }
    } catch (err) {
        showResult('auto-preview-result', `Apply failed: ${err.message}`, 'invalid');
    }
});

// ═══════════════════════════════════════════════════════════════════════
// ── Real-time Sync via WebSocket ──────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════

let currentProjectId = null;

const SYNC_EVENT_TYPES = new Set([
    'project_created',
    'project_updated',
    'project_deleted',
    'track_added',
    'track_updated',
    'track_removed',
    'effect_added',
    'effect_updated',
    'effect_removed',
    'ai_mix_applied',
    'ai_master_applied',
]);

async function loadProject(projectId) {
    if (!projectId) return;
    try {
        const resp = await fetch(`${API}/v1/projects/${projectId}`);
        if (!resp.ok) return;
        const data = await resp.json();
        currentProjectId = projectId;
        // Populate YAML editor if project has tracks
        if (data.tracks && data.tracks.length > 0) {
            const yamlLines = [`name: ${data.name || 'Project'}`, `bpm: ${data.bpm || 120}`, `sample_rate: ${data.sample_rate || 44100}`, '', 'tracks:'];
            for (const t of data.tracks) {
                yamlLines.push(`  - name: ${t.name}`);
                if (t.file) yamlLines.push(`    file: ${t.file}`);
                if (t.type) yamlLines.push(`    type: ${t.type}`);
                yamlLines.push(`    volume: ${t.volume !== undefined ? t.volume : 1.0}`);
                yamlLines.push(`    mute: ${!!t.mute}`);
                yamlLines.push(`    solo: ${!!t.solo}`);
                if (t.effects && t.effects.length > 0) {
                    yamlLines.push('    effects:');
                    for (const fx of t.effects) {
                        yamlLines.push(`      - name: ${fx.name}`);
                        if (fx.params && Object.keys(fx.params).length > 0) {
                            yamlLines.push('        params:');
                            for (const [k, v] of Object.entries(fx.params)) {
                                yamlLines.push(`          ${k}: ${v}`);
                            }
                        }
                    }
                }
            }
            if (data.master) {
                yamlLines.push('', 'master:');
                if (data.master.levels) {
                    yamlLines.push('  levels:');
                    for (const [k, v] of Object.entries(data.master.levels)) {
                        yamlLines.push(`    ${k}: ${v}`);
                    }
                }
                if (data.master.output) yamlLines.push(`  output: ${data.master.output}`);
            }
            yamlEditor.value = yamlLines.join('\n');
        }
    } catch (err) {
        addLogEntry('error', `loadProject failed: ${err.message}`);
    }
}

// ═══════════════════════════════════════════════════════════════════════
// ── WebSocket DataStream ───────────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════

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

    addLogEntry(type, JSON.stringify(data).substring(0, 200), ts);

    // Existing render event handling
    if (type === 'track_level' || type === 'master_level') {
        updateMeter(data.track || 'unknown', data.rms_db, data.peak_db);
    }

    if (type === 'warning') {
        addLogEntry('⚠️ WARNING', `${data.track}: ${data.message}`, ts);
    }

    // Real-time sync events: refresh UI when data changes
    if (SYNC_EVENT_TYPES.has(type)) {
        if (type === 'project_deleted') {
            if (currentProjectId === data.project_id) {
                currentProjectId = null;
                addLogEntry('sync', `Project ${data.project_id} deleted — editor cleared`);
            }
        } else if (type === 'project_created') {
            loadProject(data.project_id);
        } else {
            // For all other events, refresh if it affects current project
            if (data.project_id && (currentProjectId === data.project_id)) {
                loadProject(data.project_id);
            }
        }
        addLogEntry('sync', `${type}${data.detail ? ': ' + JSON.stringify(data.detail) : ''}`);
    }
}

function updateMeter(name, rmsDb, peakDb) {
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

    const pct = Math.max(0, Math.min(100, ((rmsDb || -60) + 60) / 60 * 100));
    const fill = card.querySelector('.meter-fill');
    fill.style.width = pct + '%';

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
loadSynths();
loadChainPresets();

// ═══════════════════════════════════════════════════════════════════════
// ── Phase 13: Waveform, Spectrum, Piano Roll Tabs ─────────────────────
// ═══════════════════════════════════════════════════════════════════════

// ── Waveform Tab ──────────────────────────────────────────────────────
let waveformView = null;

function initWaveformTab() {
    waveformView = new WaveformView('waveform-canvas');

    document.getElementById('btn-wf-load').addEventListener('click', async () => {
        const projectId = document.getElementById('wf-project-id').value.trim();
        const track = document.getElementById('wf-track-name').value.trim();
        if (!projectId || !track) {
            showResult('waveform-info', 'Enter Project ID and Track name', 'invalid');
            return;
        }
        try {
            const resp = await fetch(`${API}/v1/waveform/${projectId}/${track}`);
            const data = await resp.json();
            if (resp.status !== 200) {
                showResult('waveform-info', `❌ ${data.detail || 'Load failed'}`, 'invalid');
                return;
            }
            waveformView.loadFromAPI(data);
            showResult('waveform-info',
                `✅ Loaded: ${data.sample_count} samples | ${data.duration_s.toFixed(2)}s | ${data.sample_rate}Hz | ${data.channels}ch`,
                'valid');
        } catch (err) {
            showResult('waveform-info', `Load failed: ${err.message}`, 'invalid');
        }
    });

    document.getElementById('btn-wf-demo').addEventListener('click', () => {
        waveformView.loadSynthetic(15, 44100, 2000);
        showResult('waveform-info', '🎵 Demo waveform loaded (15s, 44100Hz)', 'info');
    });

    document.getElementById('btn-wf-reset').addEventListener('click', () => {
        waveformView.resetView();
    });
}

// ── Spectrum Tab ──────────────────────────────────────────────────────
let spectrumView = null;

function initSpectrumTab() {
    spectrumView = new SpectrumView('spectrum-canvas', 'spectrum-meters', 'spectrogram-canvas');

    // Set canvas sizes
    const specCanvas = document.getElementById('spectrum-canvas');
    if (specCanvas) {
        specCanvas.width = 700;
        specCanvas.height = 250;
    }
    const sgCanvas = document.getElementById('spectrogram-canvas');
    if (sgCanvas) {
        sgCanvas.width = 900;
        sgCanvas.height = 150;
    }

    document.getElementById('btn-sp-load').addEventListener('click', async () => {
        const projectId = document.getElementById('sp-project-id').value.trim();
        const track = document.getElementById('sp-track-name').value.trim();
        if (!projectId || !track) {
            return;
        }
        try {
            const resp = await fetch(`${API}/v1/spectrum/${projectId}/${track}`);
            const data = await resp.json();
            if (resp.status !== 200) return;
            spectrumView.loadFromAPI(data);
        } catch (err) {
            // silently ignore
        }
    });

    document.getElementById('btn-sp-demo').addEventListener('click', () => {
        spectrumView.loadSynthetic();
    });

    document.getElementById('btn-sp-clear').addEventListener('click', () => {
        spectrumView.clearSpectrogram();
    });
}

// ── Piano Roll Tab ────────────────────────────────────────────────────
let pianoRollView = null;

function initPianoRollTab() {
    pianoRollView = new PianoRollView('piano-roll-canvas');

    const prCanvas = document.getElementById('piano-roll-canvas');
    if (prCanvas) {
        prCanvas.width = 900;
        prCanvas.height = 400;
    }

    document.getElementById('btn-pr-load').addEventListener('click', async () => {
        const projectId = document.getElementById('pr-project-id').value.trim();
        const track = document.getElementById('pr-track-name').value.trim();
        if (!projectId || !track) {
            showResult('piano-roll-info', 'Enter Project ID and Track name', 'invalid');
            return;
        }
        try {
            const resp = await fetch(`${API}/v1/midi/${projectId}/${track}`);
            const data = await resp.json();
            if (resp.status !== 200) {
                showResult('piano-roll-info', `❌ ${data.detail || 'Load failed'}`, 'invalid');
                return;
            }
            pianoRollView.loadFromAPI(data);
            showResult('piano-roll-info',
                `✅ ${data.note_count} notes | BPM: ${data.bpm} | Beats: ${data.total_beats.toFixed(1)}`,
                'valid');
        } catch (err) {
            showResult('piano-roll-info', `Load failed: ${err.message}`, 'invalid');
        }
    });

    document.getElementById('btn-pr-demo').addEventListener('click', () => {
        pianoRollView.loadSynthetic();
        showResult('piano-roll-info', '🎵 Demo MIDI data loaded (C major scale + chord + bass)', 'info');
    });

    document.getElementById('btn-pr-reset').addEventListener('click', () => {
        pianoRollView.resetView();
    });
}

// ── Initialize Phase 13 tabs ──────────────────────────────────────────
initWaveformTab();
initSpectrumTab();
initPianoRollTab();

// ═══════════════════════════════════════════════════════════════════════
// ── Phase 22a: Agent Chat Panel ───────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════

// ── Agent Chat State ──────────────────────────────────────────────────
let agentChatHistory = [];
let agentActions = [];
let agentConfig = {
    provider: 'openai',
    model: 'gpt-4o',
    persona: 'mix-engineer',
    execution_mode: 'confirm',
};

// ── Agent Chat Functions ──────────────────────────────────────────────

async function agentChat(message) {
    if (!message || !message.trim()) return;
    const msg = message.trim();

    // Add user message to chat
    addChatMessage('user', msg);

    // Clear input
    const input = document.getElementById('agent-chat-input');
    if (input) input.value = '';

    try {
        const resp = await fetch(`${API}/v1/agent/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: msg,
                project_id: currentProjectId || undefined,
            }),
        });
        const data = await resp.json();

        if (data.message) {
            addChatMessage('assistant', data.message);
        }

        // Show actions taken
        if (data.actions && data.actions.length > 0) {
            for (const action of data.actions) {
                addChatAction(action);
            }
        }

        // Show thinking chain (collapsible)
        if (data.thinking) {
            addThinkingChain(data.thinking);
        }

    } catch (err) {
        addChatMessage('system', `❌ Agent error: ${err.message}`);
    }
}

async function configureAgent(config) {
    try {
        const resp = await fetch(`${API}/v1/agent/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config),
        });
        const data = await resp.json();
        if (data.status === 'configured') {
            agentConfig = { ...agentConfig, ...config };
            addChatMessage('system', `⚙️ Agent configured: ${data.agent.model} | persona: ${data.agent.persona} | mode: ${data.agent.execution_mode}`);
        }
    } catch (err) {
        addChatMessage('system', `❌ Config error: ${err.message}`);
    }
}

function addChatMessage(role, content) {
    agentChatHistory.push({ role, content, timestamp: Date.now() });
    renderChatPanel();
}

function addChatAction(action) {
    agentActions.push(action);
    const msg = `[工具调用] ${action.tool}(${JSON.stringify(action.arguments).substring(0, 60)}...)`;
    addChatMessage('action', msg);
}

function addThinkingChain(thinking) {
    // Add as a collapsible thinking entry
    agentChatHistory.push({
        role: 'thinking',
        content: thinking,
        timestamp: Date.now(),
    });
    renderChatPanel();
}

// ── External Agent (MCP) Message Handler ──────────────────────────────

function addExternalAgentAction(agentName, action) {
    const msg = `[外部Agent: ${agentName}] 执行了 ${action.tool} 操作`;
    addChatMessage('external', msg);
}

// ── Chat Panel Renderer ───────────────────────────────────────────────

function renderChatPanel() {
    const container = document.getElementById('chat-messages');
    if (!container) return;

    container.innerHTML = '';
    for (const entry of agentChatHistory) {
        const div = document.createElement('div');
        div.className = `chat-msg chat-msg-${entry.role}`;

        const time = new Date(entry.timestamp).toLocaleTimeString('zh-CN', { hour12: false });
        let roleLabel = '';
        let icon = '';
        switch (entry.role) {
            case 'user':
                roleLabel = '你';
                icon = '👤';
                break;
            case 'assistant':
                roleLabel = 'Agent';
                icon = '🤖';
                break;
            case 'action':
                roleLabel = '操作';
                icon = '🔧';
                break;
            case 'thinking':
                roleLabel = '思维链';
                icon = '💭';
                break;
            case 'external':
                roleLabel = '外部Agent';
                icon = '🔗';
                break;
            case 'system':
                roleLabel = '系统';
                icon = '⚙️';
                break;
            default:
                roleLabel = entry.role;
                icon = '📋';
        }

        if (entry.role === 'thinking') {
            div.innerHTML = `
                <details class="thinking-details">
                    <summary>${icon} ${roleLabel} <span class="chat-time">${time}</span></summary>
                    <pre class="thinking-content">${escapeHtml(entry.content)}</pre>
                </details>`;
        } else {
            div.innerHTML = `
                <span class="chat-icon">${icon}</span>
                <span class="chat-role">${roleLabel}</span>
                <span class="chat-time">${time}</span>
                <div class="chat-text">${escapeHtml(entry.content)}</div>`;
        }
        container.appendChild(div);
    }

    // Auto-scroll to bottom
    container.scrollTop = container.scrollHeight;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ── Initialize Agent Chat Panel ───────────────────────────────────────

function initAgentChat() {
    // Send button
    const sendBtn = document.getElementById('agent-chat-send');
    const input = document.getElementById('agent-chat-input');

    if (sendBtn) {
        sendBtn.addEventListener('click', () => {
            agentChat(input ? input.value : '');
        });
    }

    if (input) {
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                agentChat(input.value);
            }
        });
    }

    // Config button
    const configBtn = document.getElementById('agent-config-btn');
    if (configBtn) {
        configBtn.addEventListener('click', () => {
            const persona = document.getElementById('agent-persona-select');
            const mode = document.getElementById('agent-mode-select');
            const model = document.getElementById('agent-model-input');
            const apiKey = document.getElementById('agent-apikey-input');

            const config = {};
            if (persona && persona.value) config.persona = persona.value;
            if (mode && mode.value) config.execution_mode = mode.value;
            if (model && model.value) config.model = model.value;
            if (apiKey && apiKey.value) config.api_key = apiKey.value;

            configureAgent(config);
        });
    }

    // Load personas
    loadAgentPersonas();

    // Load status
    loadAgentStatus();
}

async function loadAgentPersonas() {
    try {
        const resp = await fetch(`${API}/v1/agent/personas`);
        const data = await resp.json();
        const select = document.getElementById('agent-persona-select');
        if (select && data.personas) {
            select.innerHTML = '';
            for (const p of data.personas) {
                const opt = document.createElement('option');
                opt.value = p.id;
                opt.textContent = `${p.name} — ${p.description}`;
                select.appendChild(opt);
            }
        }
    } catch (err) {
        // Silently ignore — personas may not be available
    }
}

async function loadAgentStatus() {
    try {
        const resp = await fetch(`${API}/v1/agent/status`);
        const data = await resp.json();
        const statusEl = document.getElementById('agent-status');
        if (statusEl && data.agent) {
            statusEl.textContent = `${data.agent.model} | ${data.agent.persona} | ${data.agent.execution_mode}`;
        }
    } catch (err) {
        // Silently ignore
    }
}

initAgentChat();
