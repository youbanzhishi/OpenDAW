/**
 * VCMix Desktop — DAW Shell App JS (Phase 14)
 * Vanilla JS, no frameworks. Native HTML/CSS/JS only.
 *
 * Connects to Python backend at http://localhost:8000/api/
 * Uses Tauri invoke() for desktop commands where available.
 */

// ═══════════════════════════════════════════════════════════════════════
// Constants
// ═══════════════════════════════════════════════════════════════════════

const BACKEND_BASE = 'http://localhost:8000';
const API = BACKEND_BASE + '/api';
const API_V1 = BACKEND_BASE + '/api/v1';
const AGENT_API = API_V1 + '/agent';

// ═══════════════════════════════════════════════════════════════════════
// State
// ═══════════════════════════════════════════════════════════════════════

const state = {
  playing: false,
  recording: false,
  currentTime: 0,           // seconds
  bpm: 120,
  timeSig: '4/4',
  projectId: null,
  projectName: 'Untitled',
  tracks: [],               // [{ id, name, type, gain, pan, mute, solo, selected }]
  chatMessages: [],         // [{ role, text, actions, thinking, timestamp }]
  chatOpen: false,
  chatLoading: false,
  timelineWidth: 2000,      // pixels
  pixelsPerSecond: 50,
};

// ═══════════════════════════════════════════════════════════════════════
// DOM References
// ═══════════════════════════════════════════════════════════════════════

const $ = id => document.getElementById(id);

const dom = {
  // Header
  projectSelect:  $('project-select'),
  btnNewProject:   $('btn-new-project'),
  btnPlay:         $('btn-play'),
  btnStop:         $('btn-stop'),
  btnRewind:       $('btn-rewind'),
  btnRecord:       $('btn-record'),
  btnExport:       $('btn-export'),
  btnChatToggle:   $('btn-chat-toggle'),
  timeDisplay:     $('time-display'),
  bpmInput:        $('bpm-input'),
  timeSigSelect:   $('time-sig-select'),
  backendStatus:   $('backend-status'),

  // v0.25.0: Audio controls
  btnLoadWav:      $('btn-load-wav'),
  volumeSlider:    $('volume-slider'),
  volumeDisplay:  $('volume-display'),

  // DAW Layout
  trackList:       $('track-list'),
  mixerStrips:     $('mixer-strips'),
  masterFader:     $('master-fader'),
  masterDb:        $('master-dB'),
  masterMeterFill: $('master-meter-fill'),

  // Arrangement
  timelineRuler:   $('timeline-ruler'),
  rulerLabels:     $('ruler-labels'),
  timelineClips:  $('timeline-clips'),
  playhead:        $('playhead'),

  // Chat
  chatPanel:       $('chat-panel'),
  chatMessages:    $('chat-messages'),
  chatInput:       $('chat-input'),
  btnChatSend:     $('btn-chat-send'),
  personaSelect:   $('persona-select'),
  btnChatClose:    $('btn-chat-close'),

  // Status
  statusMsg:       $('status-msg'),
};

// ═══════════════════════════════════════════════════════════════════════
// Backend Health
// ═══════════════════════════════════════════════════════════════════════

async function checkBackendHealth() {
  try {
    const resp = await fetch(API + '/health');
    if (resp.ok) {
      setBackendStatus(true, 'Backend ready');
      return true;
    }
  } catch (_) {}
  setBackendStatus(false, 'Backend offline');
  return false;
}

function setBackendStatus(online, msg) {
  const dot = dom.backendStatus.querySelector('.dot');
  const txt = dom.backendStatus.querySelector('.status-text');
  dot.className = 'dot ' + (online ? 'online' : 'offline');
  txt.textContent = msg;
}

// ═══════════════════════════════════════════════════════════════════════
// Transport Controls
// ═══════════════════════════════════════════════════════════════════════

function formatTime(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  const ms = Math.floor((seconds % 1) * 1000);
  return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}.${String(ms).padStart(3,'0')}`;
}

function updateTimeDisplay() {
  dom.timeDisplay.textContent = formatTime(state.currentTime);
  const px = state.currentTime * state.pixelsPerSecond;
  dom.playhead.style.left = (px + 220) + 'px'; // offset by track panel width
}

let transportRaf = null;

// ═══════════════════════════════════════════════════════════════════════════
// v0.25.0: Tauri Audio Commands
// ═══════════════════════════════════════════════════════════════════════════

async function tauriInvoke(cmd, args = {}) {
  if (typeof window.__TAURI_INVOKE__ !== 'undefined') {
    try {
      return await window.__TAURI_INVOKE__(cmd, args);
    } catch (e) {
      console.error(`Tauri invoke ${cmd} failed:`, e);
      return null;
    }
  }
  return null;
}

async function audioPlay() {
  // 初始化音频输出（如果尚未初始化）
  await tauriInvoke('audio_init', { sample_rate: 44100, buffer_size: 256 });
  // 启动播放
  await tauriInvoke('audio_play');
  setStatus('Playing (real audio)');
}

async function audioStop() {
  await tauriInvoke('audio_stop');
  state.currentTime = 0;
  updateTimeDisplay();
  setStatus('Stopped');
}

async function audioLoadAndPlay(filePath) {
  try {
    await tauriInvoke('audio_load_and_play', {
      file_path: filePath,
      track_id: 'main'
    });
    setStatus(`Playing: ${filePath.split('/').pop()}`);
  } catch (e) {
    setStatus('Failed to load audio');
    console.error('Failed to load audio:', e);
  }
}

async function audioSetVolume(volumeDb) {
  await tauriInvoke('audio_set_master_volume', { volume_db: volumeDb });
}

async function audioGetStatus() {
  return await tauriInvoke('audio_get_status');
}

// ── Original Transport Functions (enhanced) ─────────────────────────────

function play() {
  if (state.playing) return;
  state.playing = true;
  dom.btnPlay.classList.add('playing');
  dom.btnPlay.textContent = '⏸';

  // 尝试通过Tauri启动真实音频播放
  audioPlay().catch(() => {
    // 如果失败，使用模拟播放
    console.log('Using simulated playback (no audio device or Tauri not available)');
  });

  const startTime = performance.now() - state.currentTime * 1000;
  function tick() {
    if (!state.playing) return;
    state.currentTime = (performance.now() - startTime) / 1000;
    updateTimeDisplay();
    simulateMeters();
    transportRaf = requestAnimationFrame(tick);
  }
  transportRaf = requestAnimationFrame(tick);
  setStatus('Playing');
}

function stop() {
  if (!state.playing) {
    state.currentTime = 0;
    updateTimeDisplay();
    return;
  }
  state.playing = false;
  cancelAnimationFrame(transportRaf);
  dom.btnPlay.classList.remove('playing');
  dom.btnPlay.textContent = '▶';

  // 通过Tauri停止音频播放
  audioStop().catch(() => {
    console.log('Using simulated stop');
  });

  setStatus('Stopped');
}

function togglePlayStop() {
  if (state.playing) stop(); else play();
}

function rewind() {
  stop();
  state.currentTime = 0;
  updateTimeDisplay();
}

function toggleRecord() {
  state.recording = !state.recording;
  dom.btnRecord.style.background = state.recording ? 'rgba(239,83,80,0.3)' : '';
  dom.btnRecord.style.borderColor = state.recording ? 'var(--danger)' : '';
  setStatus(state.recording ? 'Recording…' : 'Ready');
}

// ── Simulated Meter ───────────────────────────────────────────────────
function simulateMeters() {
  const levels = state.tracks.map((t, i) => {
    if (t.mute) return 0;
    const base = 0.3 + Math.random() * 0.4;
    return t.solo ? base * 1.2 : base * 0.8;
  });

  const max = Math.max(...levels, 0);
  const pct = Math.round(max * 100);
  dom.masterMeterFill.style.height = pct + '%';

  // Update channel strip meters
  document.querySelectorAll('.channel-meter-fill').forEach((el, i) => {
    const level = levels[i] || 0;
    el.style.height = Math.round(level * 100) + '%';
  });
}

// ═══════════════════════════════════════════════════════════════════════
// Project Management
// ═══════════════════════════════════════════════════════════════════════

async function loadProjects() {
  try {
    const resp = await fetch(API_V1 + '/projects');
    if (!resp.ok) return;
    const data = await resp.json();
    const projects = data.projects || [];
    dom.projectSelect.innerHTML = '<option value="">— Select Project —</option>';
    projects.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = p.name || p.id;
      if (p.id === state.projectId) opt.selected = true;
      dom.projectSelect.appendChild(opt);
    });
  } catch (_) {}
}

async function createProject(name) {
  try {
    const resp = await fetch(API_V1 + '/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    if (!resp.ok) throw new Error(await resp.text());
    const data = await resp.json();
    state.projectId = data.id || data.project_id || data.name;
    state.projectName = name;
    setStatus(`Project "${name}" created`);
    toast('Project created', 'success');
    await loadProjects();
    await loadProjectTracks();
  } catch (e) {
    setStatus('Failed to create project');
    toast('Failed to create project: ' + e.message, 'error');
  }
}

async function loadProjectTracks() {
  if (!state.projectId) { renderTrackList(); renderMixerStrips(); return; }
  try {
    const resp = await fetch(API_V1 + '/projects/' + state.projectId);
    if (!resp.ok) return;
    const data = await resp.json();
    const tracks = data.tracks || [];
    state.tracks = tracks.map(t => ({
      id: t.id || t.name || String(Math.random()),
      name: t.name || 'Track',
      type: t.type || 'audio',
      gain: t.gain ?? 0,
      pan: t.pan ?? 0,
      mute: t.mute ?? false,
      solo: t.solo ?? false,
      selected: false,
    }));
    if (data.bpm) {
      state.bpm = data.bpm;
      dom.bpmInput.value = state.bpm;
    }
    renderTrackList();
    renderMixerStrips();
  } catch (_) {}
}

// ═══════════════════════════════════════════════════════════════════════
// Track List (left panel)
// ═══════════════════════════════════════════════════════════════════════

function renderTrackList() {
  if (state.tracks.length === 0) {
    dom.trackList.innerHTML = '<div class="empty-hint">No tracks yet.<br>Add one to get started.</div>';
    return;
  }

  dom.trackList.innerHTML = '';
  state.tracks.forEach((track, idx) => {
    const el = document.createElement('div');
    el.className = 'track-item' + (track.selected ? ' selected' : '');
    el.dataset.idx = idx;

    el.innerHTML = `
      <div class="track-item-header">
        <span class="track-name">${escHtml(track.name)}</span>
        <span class="track-type">${track.type}</span>
      </div>
      <div class="track-controls">
        <button class="btn-mute${track.mute ? ' active' : ''}" data-action="mute" title="Mute">M</button>
        <button class="btn-solo${track.solo ? ' active' : ''}" data-action="solo" title="Solo">S</button>
        <button class="btn-delete" data-action="delete" title="Delete">✕</button>
      </div>
      <div class="track-gain">
        <label>dB</label>
        <input type="range" class="track-gain-slider" min="-60" max="12" value="${track.gain}" step="0.5" data-action="gain">
        <span style="font-size:10px;color:var(--text-muted);width:32px;text-align:right">${track.gain.toFixed(1)}</span>
      </div>`;

    // Event delegation
    el.addEventListener('click', e => {
      const action = e.target.dataset.action;
      if (!action) { selectTrack(idx); return; }
      if (action === 'mute') { track.mute = !track.mute; renderTrackList(); renderMixerStrips(); }
      if (action === 'solo') { track.solo = !track.solo; renderTrackList(); renderMixerStrips(); simulateMeters(); }
      if (action === 'delete') { deleteTrack(idx); }
      if (action === 'gain') {
        // Handled by input event below
      }
    });

    el.addEventListener('input', e => {
      if (e.target.dataset.action === 'gain') {
        const val = parseFloat(e.target.value);
        track.gain = val;
        e.target.nextElementSibling.textContent = val.toFixed(1);
        const strip = document.querySelectorAll('.channel-strip')[idx];
        if (strip) {
          strip.querySelector('.fader-dB').textContent = val.toFixed(1) + ' dB';
          strip.querySelector('.fader-v').value = val;
        }
      }
    });

    dom.trackList.appendChild(el);
  });
}

function selectTrack(idx) {
  state.tracks.forEach((t, i) => t.selected = i === idx);
  renderTrackList();
  renderMixerStrips();
}

async function addTrack() {
  showNewTrackModal();
}

async function deleteTrack(idx) {
  const track = state.tracks[idx];
  state.tracks.splice(idx, 1);
  renderTrackList();
  renderMixerStrips();
  setStatus(`Track "${track.name}" removed`);
}

// ── New Track Modal ───────────────────────────────────────────────────
function showNewTrackModal() {
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal">
      <h3>Add New Track</h3>
      <div class="modal-row">
        <label>Track Name</label>
        <input id="modal-track-name" type="text" placeholder="e.g. Vocal, Bass, Drums" autofocus>
      </div>
      <div class="modal-row">
        <label>Type</label>
        <select id="modal-track-type">
          <option value="audio">Audio</option>
          <option value="midi">MIDI</option>
          <option value="bus">Bus</option>
        </select>
      </div>
      <div class="modal-actions">
        <button class="action-btn" id="modal-cancel">Cancel</button>
        <button class="action-btn primary" id="modal-confirm">Add Track</button>
      </div>
    </div>`;

  document.body.appendChild(overlay);

  const close = () => document.body.removeChild(overlay);
  $('modal-cancel').onclick = close;
  overlay.onclick = e => { if (e.target === overlay) close(); };
  $('modal-track-name').onkeydown = e => { if (e.key === 'Enter') $('modal-confirm').click(); };
  $('modal-confirm').onclick = () => {
    const name = $('modal-track-name').value.trim() || ('Track ' + (state.tracks.length + 1));
    const type = $('modal-track-type').value;
    close();

    const newTrack = {
      id: String(Date.now()),
      name,
      type,
      gain: 0,
      pan: 0,
      mute: false,
      solo: false,
      selected: false,
    };

    state.tracks.push(newTrack);
    renderTrackList();
    renderMixerStrips();
    setStatus(`Track "${name}" added`);

    // Sync to backend
    if (state.projectId) {
      fetch(API_V1 + '/projects/' + state.projectId + '/tracks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newTrack),
      }).catch(() => {});
    }
  };

  $('modal-track-name').focus();
}

// ═══════════════════════════════════════════════════════════════════════
// Mixer Strips (right panel)
// ═══════════════════════════════════════════════════════════════════════

function renderMixerStrips() {
  if (state.tracks.length === 0) {
    dom.mixerStrips.innerHTML = '<div class="empty-hint">No channels.</div>';
    return;
  }

  dom.mixerStrips.innerHTML = '';
  state.tracks.forEach((track, idx) => {
    const strip = document.createElement('div');
    strip.className = 'channel-strip' + (track.selected ? ' selected' : '');
    strip.innerHTML = `
      <div class="strip-label">${escHtml(track.name)}</div>
      <div class="strip-pan">
        <input type="range" class="pan-slider" min="-100" max="100" value="${track.pan * 100}" step="1" data-idx="${idx}">
        <div class="strip-pan-label">${panLabel(track.pan)}</div>
      </div>
      <div class="fader-wrap">
        <input type="range" class="fader-v" min="-60" max="12" value="${track.gain}" step="0.5" data-idx="${idx}">
        <div class="fader-dB">${track.gain.toFixed(1)} dB</div>
      </div>
      <div class="meter">
        <div class="meter-fill channel-meter-fill" id="meter-${idx}" style="height:0%"></div>
      </div>`;

    strip.addEventListener('click', () => selectTrack(idx));
    dom.mixerStrips.appendChild(strip);
  });

  // Wire up mixer fader and pan sliders
  document.querySelectorAll('.fader-v').forEach(slider => {
    slider.addEventListener('input', e => {
      const idx = parseInt(e.target.dataset.idx);
      const val = parseFloat(e.target.value);
      state.tracks[idx].gain = val;
      e.target.nextElementSibling.textContent = val.toFixed(1) + ' dB';
      // Sync track list gain display
      const trackEl = dom.trackList.children[idx];
      if (trackEl) {
        const gainSlider = trackEl.querySelector('.track-gain-slider');
        const gainVal = trackEl.querySelector('.track-gain span');
        if (gainSlider) gainSlider.value = val;
        if (gainVal) gainVal.textContent = val.toFixed(1);
      }
    });
  });

  document.querySelectorAll('.pan-slider').forEach(slider => {
    slider.addEventListener('input', e => {
      const idx = parseInt(e.target.dataset.idx);
      const val = parseFloat(e.target.value) / 100;
      state.tracks[idx].pan = val;
      e.target.nextElementSibling.textContent = panLabel(val);
    });
  });
}

function panLabel(pan) {
  if (pan === 0) return 'C';
  if (pan < 0) return 'L' + Math.round(Math.abs(pan) * 100);
  return 'R' + Math.round(pan * 100);
}

// Master fader
dom.masterFader.addEventListener('input', e => {
  const val = parseFloat(e.target.value);
  dom.masterDb.textContent = val.toFixed(1) + ' dB';
});

// ═══════════════════════════════════════════════════════════════════════
// Timeline / Arrangement
// ═══════════════════════════════════════════════════════════════════════

function renderTimelineRuler() {
  const bps = state.bpm / 60;
  const beatsPerBar = parseInt(state.timeSig.split('/')[0]) || 4;
  const bars = 32;
  const totalBeats = bars * beatsPerBar;
  const totalSeconds = totalBeats / bps;

  dom.rulerLabels.innerHTML = '';
  for (let bar = 1; bar <= bars; bar++) {
    const beatOffset = (bar - 1) * beatsPerBar;
    const seconds = beatOffset / bps;
    const px = seconds * state.pixelsPerSecond + 220;
    const el = document.createElement('div');
    el.className = 'ruler-bar';
    el.textContent = bar;
    el.style.cssText = `position:absolute;left:${px}px;font-size:10px;color:var(--text-muted);padding:4px 0;min-width:24px;text-align:center;`;
    dom.rulerLabels.appendChild(el);
  }

  // Set grid overlay width
  const gridW = totalSeconds * state.pixelsPerSecond;
  $('grid-overlay').style.width = gridW + 'px';
  dom.timelineClips.style.width = (gridW + 220) + 'px';
}

function renderClips() {
  // Remove old clips
  dom.timelineClips.querySelectorAll('.clip-block').forEach(el => el.remove());

  state.tracks.forEach((track, trackIdx) => {
    const clip = document.createElement('div');
    clip.className = 'clip-block';
    clip.textContent = track.name;
    // Position: top offset by track index, just for visual
    clip.style.top = (trackIdx * 40 + 4) + 'px';
    clip.style.left = '224px'; // after track panel
    clip.style.width = '300px';
    clip.title = track.name;
    dom.timelineClips.appendChild(clip);
  });
}

// ═══════════════════════════════════════════════════════════════════════
// Chat Panel
// ═══════════════════════════════════════════════════════════════════════

function toggleChat() {
  state.chatOpen = !state.chatOpen;
  dom.chatPanel.classList.toggle('hidden', !state.chatOpen);
  dom.btnChatToggle.style.background = state.chatOpen ? 'var(--accent-dim)' : '';
  dom.btnChatToggle.style.borderColor = state.chatOpen ? 'var(--accent)' : '';
  if (state.chatOpen) dom.chatInput.focus();
}

function closeChat() {
  state.chatOpen = false;
  dom.chatPanel.classList.add('hidden');
  dom.btnChatToggle.style.background = '';
  dom.btnChatToggle.style.borderColor = '';
}

async function sendChatMessage() {
  const text = dom.chatInput.value.trim();
  if (!text || state.chatLoading) return;

  // Add user message
  state.chatMessages.push({ role: 'user', text, timestamp: new Date() });
  dom.chatInput.value = '';
  renderChatMessages();

  state.chatLoading = true;
  appendThinking();

  try {
    const resp = await fetch(AGENT_API + '/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: text,
        project_id: state.projectId || null,
      }),
    });

    if (!resp.ok) throw new Error(await resp.text());
    const data = await resp.json();

    state.chatLoading = false;
    removeThinking();

    state.chatMessages.push({
      role: 'agent',
      text: data.message || 'No response.',
      actions: data.actions || [],
      thinking: data.thinking || '',
      timestamp: new Date(),
    });
    renderChatMessages();

    // Execute agent actions (display only, no auto-execute in desktop shell)
    if (data.actions && data.actions.length > 0) {
      setStatus(`Agent suggested ${data.actions.length} action(s)`);
    }

  } catch (e) {
    state.chatLoading = false;
    removeThinking();
    state.chatMessages.push({
      role: 'agent',
      text: '⚠️ Agent unavailable: ' + e.message + '\n\nMake sure the AI backend is configured and try again.',
      actions: [],
      thinking: '',
      timestamp: new Date(),
    });
    renderChatMessages();
  }
}

function renderChatMessages() {
  // Remove welcome + all msgs
  dom.chatMessages.querySelectorAll('.chat-welcome, .msg').forEach(el => el.remove());

  state.chatMessages.forEach(msg => {
    const div = document.createElement('div');
    div.className = 'msg ' + msg.role;

    let html = `<div class="msg-bubble">${escHtml(msg.text)}</div>`;

    if (msg.actions && msg.actions.length > 0) {
      html += '<div class="msg-actions">';
      msg.actions.forEach(a => {
        html += `<span class="msg-action-tag">${escHtml(a.tool || a.explanation || 'action')}</span>`;
      });
      html += '</div>';
    }

    if (msg.thinking) {
      html += `<div class="msg-thinking">💭 ${escHtml(msg.thinking)}</div>`;
    }

    html += `<div class="msg-time">${formatChatTime(msg.timestamp)}</div>`;
    div.innerHTML = html;
    dom.chatMessages.appendChild(div);
  });

  dom.chatMessages.scrollTop = dom.chatMessages.scrollHeight;
}

let thinkingEl = null;
function appendThinking() {
  thinkingEl = document.createElement('div');
  thinkingEl.className = 'msg agent';
  thinkingEl.innerHTML = '<div class="msg-bubble" id="thinking-bubble">🤖 Thinking…</div>';
  dom.chatMessages.appendChild(thinkingEl);
  dom.chatMessages.scrollTop = dom.chatMessages.scrollHeight;
}

function removeThinking() {
  if (thinkingEl) { thinkingEl.remove(); thinkingEl = null; }
}

function formatChatTime(d) {
  const h = String(d.getHours()).padStart(2,'0');
  const m = String(d.getMinutes()).padStart(2,'0');
  return h + ':' + m;
}

// ═══════════════════════════════════════════════════════════════════════
// Export
// ═══════════════════════════════════════════════════════════════════════

async function exportProject() {
  if (!state.projectId) {
    toast('No project loaded to export', 'error');
    return;
  }
  setStatus('Starting export…');
  try {
    // Try Tauri command first, fall back to direct fetch
    let result;
    try {
      result = await window.__TAURI__.core.invoke('render_project', { yamlPath: state.projectId });
    } catch (_) {
      const resp = await fetch(API + '/render', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_path: state.projectId }),
      });
      result = await resp.json();
    }
    const jobId = result.job_id || result.message || 'unknown';
    toast('Export started: ' + jobId, 'info');
    setStatus('Exporting: ' + jobId);
  } catch (e) {
    toast('Export failed: ' + e.message, 'error');
    setStatus('Export failed');
  }
}

// ═══════════════════════════════════════════════════════════════════════
// Keyboard Shortcuts
// ═══════════════════════════════════════════════════════════════════════

function setupKeyboardShortcuts() {
  document.addEventListener('keydown', e => {
    // Ignore when typing in inputs
    const tag = document.activeElement.tagName.toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') {
      if (e.key === 'Escape') document.activeElement.blur();
      return;
    }

    const ctrl = e.ctrlKey || e.metaKey;

    if (e.key === ' ') { e.preventDefault(); togglePlayStop(); return; }
    if (e.key === 'Home') { e.preventDefault(); rewind(); return; }

    if (ctrl && e.key === 'e') { e.preventDefault(); exportProject(); return; }
    if (ctrl && e.key === 'k') { e.preventDefault(); toggleChat(); return; }
    if (ctrl && e.key === 'm') { e.preventDefault(); dom.mixerPanel && dom.mixerPanel.focus(); return; }
    if (ctrl && e.key === 'n') { e.preventDefault(); showNewTrackModal(); return; }
    if (e.key === 'Escape' && state.chatOpen) { closeChat(); return; }
  });
}

// ═══════════════════════════════════════════════════════════════════════
// Toast Notifications
// ═══════════════════════════════════════════════════════════════════════

function toast(msg, type = 'info') {
  const container = $('toast-container');
  const el = document.createElement('div');
  el.className = 'toast ' + type;
  el.textContent = msg;
  container.appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

// ═══════════════════════════════════════════════════════════════════════
// Status Bar
// ═══════════════════════════════════════════════════════════════════════

function setStatus(msg) {
  dom.statusMsg.textContent = msg;
}

// ═══════════════════════════════════════════════════════════════════════
// Utility
// ═══════════════════════════════════════════════════════════════════════

function escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g,'&amp;')
    .replace(/</g,'&lt;')
    .replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;');
}

// ═══════════════════════════════════════════════════════════════════════
// Init
// ═══════════════════════════════════════════════════════════════════════

async function init() {
  setupKeyboardShortcuts();
  setupEventListeners();
  updateTimeDisplay();
  renderTimelineRuler();
  renderClips();
  renderTrackList();
  renderMixerStrips();

  // Check backend periodically
  checkBackendHealth();
  setInterval(checkBackendHealth, 15000);

  // Load projects
  loadProjects();

  setStatus('Ready — Space to play/stop');
}

function setupEventListeners() {
  // Transport
  dom.btnPlay.addEventListener('click', togglePlayStop);
  dom.btnStop.addEventListener('click', stop);
  dom.btnRewind.addEventListener('click', rewind);
  dom.btnRecord.addEventListener('click', toggleRecord);
  dom.btnExport.addEventListener('click', exportProject);

  // BPM / Time Sig
  dom.bpmInput.addEventListener('change', e => {
    state.bpm = parseInt(e.target.value) || 120;
    renderTimelineRuler();
  });
  dom.timeSigSelect.addEventListener('change', e => {
    state.timeSig = e.target.value;
    renderTimelineRuler();
  });

  // Projects
  dom.projectSelect.addEventListener('change', async e => {
    if (!e.target.value) return;
    state.projectId = e.target.value;
    state.projectName = e.target.options[e.target.selectedIndex].textContent;
    setStatus('Loading project: ' + state.projectName);
    await loadProjectTracks();
    setStatus('Project: ' + state.projectName);
  });
  dom.btnNewProject.addEventListener('click', () => {
    const name = prompt('Project name:', 'New Project');
    if (name) createProject(name);
  });

  // Tracks
  $('btn-add-track').addEventListener('click', addTrack);

  // Chat
  dom.btnChatToggle.addEventListener('click', toggleChat);
  dom.btnChatClose.addEventListener('click', closeChat);
  dom.btnChatSend.addEventListener('click', sendChatMessage);
  dom.chatInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendChatMessage();
    }
  });

  // Suggestion chips
  dom.chatMessages.addEventListener('click', e => {
    if (e.target.classList.contains('chip')) {
      dom.chatInput.value = e.target.dataset.msg || '';
      dom.chatInput.focus();
    }
  });

  // Persona change
  dom.personaSelect.addEventListener('change', async e => {
    try {
      await fetch(AGENT_API + '/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ persona: e.target.value }),
      });
      toast('Persona set: ' + e.target.value, 'success');
    } catch (_) {}
  });

  // Master fader
  dom.masterFader.addEventListener('input', e => {
    dom.masterDb.textContent = parseFloat(e.target.value).toFixed(1) + ' dB';
  });

  // v0.25.0: Volume slider
  dom.volumeSlider.addEventListener('input', e => {
    const vol = parseFloat(e.target.value);
    dom.volumeDisplay.textContent = vol + ' dB';
    audioSetVolume(vol);
  });

  // v0.25.0: Load WAV button
  dom.btnLoadWav.addEventListener('click', async () => {
    // 如果在Tauri环境中，使用文件对话框
    if (typeof window.__TAURI_DIALOG__ !== 'undefined') {
      try {
        const { open } = window.__TAURI_DIALOG__;
        const filePath = await open({
          multiple: false,
          filters: [{ name: 'Audio', extensions: ['wav', 'mp3', 'ogg', 'flac'] }]
        });
        if (filePath) {
          await audioLoadAndPlay(filePath);
        }
      } catch (e) {
        console.error('File dialog error:', e);
        // Fallback: 提示用户输入路径
        const path = prompt('Enter WAV file path:');
        if (path) {
          await audioLoadAndPlay(path);
        }
      }
    } else {
      // 非Tauri环境：提示用户输入路径
      const path = prompt('Enter WAV file path:');
      if (path) {
        await audioLoadAndPlay(path);
      }
    }
  });
}

// ── Run ───────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', init);
