/**
 * OpenDAW — Track List Component
 * Left panel track list with controls (mute/solo/gain/delete)
 */
const TrackList = (() => {
    const TRACK_COLORS = [
        '#4a9eff', '#34d399', '#fb923c', '#f472b6',
        '#a78bfa', '#22d3ee', '#f87171', '#fbbf24'
    ];
    let tracks = [];
    let selectedTrackId = null;
    let trackIdCounter = 0;

    function init() {
        document.getElementById('btn-add-track').addEventListener('click', () => showAddTrackModal());
    }

    function addTrack(name, type = 'audio') {
        const id = 'track_' + (++trackIdCounter);
        const color = TRACK_COLORS[tracks.length % TRACK_COLORS.length];
        const track = {
            id, name, type, color,
            gain: 0, pan: 0,
            mute: false, solo: false,
            selected: false,
            clips: []
        };
        tracks.push(track);
        render();
        Mixer.render();
        Arrangement.render();
        Inspector.show(track);
        return track;
    }

    function removeTrack(id) {
        tracks = tracks.filter(t => t.id !== id);
        if (selectedTrackId === id) {
            selectedTrackId = null;
            Inspector.clear();
        }
        render();
        Mixer.render();
        Arrangement.render();
    }

    function selectTrack(id) {
        tracks.forEach(t => t.selected = (t.id === id));
        selectedTrackId = id;
        render();
        const track = tracks.find(t => t.id === id);
        if (track) Inspector.show(track);
    }

    function toggleMute(id) {
        const track = tracks.find(t => t.id === id);
        if (track) {
            track.mute = !track.mute;
            render();
            Mixer.render();
            TauriBridge.engineToggleTrackMute(id).catch(() => {});
        }
    }

    function toggleSolo(id) {
        const track = tracks.find(t => t.id === id);
        if (track) {
            track.solo = !track.solo;
            render();
        }
    }

    function setGain(id, db) {
        const track = tracks.find(t => t.id === id);
        if (track) {
            track.gain = db;
            TauriBridge.engineSetTrackVolume(id, db).catch(() => {});
        }
    }

    function render() {
        const list = document.getElementById('track-list');
        if (!list) return;

        if (tracks.length === 0) {
            list.innerHTML = `
                <div class="empty-state">
                    <svg width="48" height="48" viewBox="0 0 48 48"><path d="M24 8v24M16 20l8 8 8-8M12 36h24" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round" opacity="0.3"/></svg>
                    <p>No tracks yet</p>
                    <p class="hint">Tap + or drag audio here</p>
                </div>`;
            return;
        }

        list.innerHTML = tracks.map(t => `
            <div class="track-item ${t.selected ? 'selected' : ''}" data-id="${t.id}">
                <div class="track-item-header">
                    <div class="track-color" style="background:${t.color}"></div>
                    <span class="track-name">${escHtml(t.name)}</span>
                    <span class="track-type-badge">${t.type.toUpperCase()}</span>
                </div>
                <div class="track-controls">
                    <button class="btn-mute ${t.mute ? 'active' : ''}" data-action="mute" data-id="${t.id}" title="Mute">M</button>
                    <button class="btn-solo ${t.solo ? 'active' : ''}" data-action="solo" data-id="${t.id}" title="Solo">S</button>
                    <div style="flex:1"></div>
                    <button class="btn-delete" data-action="delete" data-id="${t.id}" title="Delete">
                        <svg width="12" height="12" viewBox="0 0 12 12"><path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
                    </button>
                </div>
                <div class="track-gain">
                    <label>V</label>
                    <input type="range" min="-60" max="12" value="${t.gain}" step="0.5"
                           data-action="gain" data-id="${t.id}">
                </div>
            </div>
        `).join('');

        // Event delegation
        list.onclick = (e) => {
            const btn = e.target.closest('[data-action]');
            if (btn) {
                const action = btn.dataset.action;
                const id = btn.dataset.id;
                if (action === 'mute') toggleMute(id);
                else if (action === 'solo') toggleSolo(id);
                else if (action === 'delete') removeTrack(id);
                return;
            }
            const item = e.target.closest('.track-item');
            if (item) selectTrack(item.dataset.id);
        };

        list.oninput = (e) => {
            const input = e.target.closest('[data-action="gain"]');
            if (input) setGain(input.dataset.id, parseFloat(input.value));
        };
    }

    function getTracks() { return tracks; }
    function getSelected() { return tracks.find(t => t.id === selectedTrackId); }

    function showAddTrackModal() {
        const name = prompt('Track name:', 'Track ' + (tracks.length + 1));
        if (!name) return;
        const type = prompt('Track type (audio/midi/bus):', 'audio') || 'audio';
        addTrack(name, type);
    }

    function escHtml(str) {
        return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }

    return { init, addTrack, removeTrack, selectTrack, toggleMute, toggleSolo, setGain, render, getTracks, getSelected };
})();
