/**
 * OpenDAW — Mixer Component
 * Bottom panel with channel strips, faders, meters, pan
 */
const Mixer = (() => {
    let expanded = true;

    function init() {
        const toggleBtn = document.getElementById('btn-mixer-toggle');
        const expandBtn = document.getElementById('btn-mixer-expand');
        const masterFader = document.getElementById('master-fader');
        const panel = document.getElementById('mixer-panel');

        if (toggleBtn) {
            toggleBtn.addEventListener('click', () => {
                expanded = !expanded;
                panel.classList.toggle('collapsed', !expanded);
                if (LayoutManager.isMobile()) {
                    panel.classList.toggle('expanded', expanded);
                }
            });
        }

        if (expandBtn) {
            expandBtn.addEventListener('click', () => {
                expanded = true;
                panel.classList.remove('collapsed');
                if (LayoutManager.isMobile()) panel.classList.add('expanded');
            });
        }

        if (masterFader) {
            masterFader.addEventListener('input', (e) => {
                const db = parseFloat(e.target.value);
                document.getElementById('master-dB').textContent = db.toFixed(1);
                TauriBridge.setMasterVolume(db).catch(() => {});
            });
        }
    }

    function render() {
        const container = document.getElementById('mixer-strips');
        if (!container) return;

        const tracks = TrackList.getTracks();
        container.innerHTML = tracks.map(t => `
            <div class="channel-strip ${t.selected ? 'selected' : ''}" data-id="${t.id}">
                <div class="strip-label">${escHtml(t.name)}</div>
                <div class="strip-meter">
                    <div class="meter-bar" data-meter="${t.id}"></div>
                </div>
                <div class="strip-pan">
                    <input type="range" min="-100" max="100" value="${t.pan}" step="1"
                           data-pan="${t.id}">
                </div>
                <div class="strip-pan-label">${t.pan === 0 ? 'C' : (t.pan < 0 ? 'L' + Math.abs(t.pan) : 'R' + t.pan)}</div>
                <div class="fader-wrap">
                    <input type="range" class="fader-v" min="-60" max="12" value="${t.gain}" step="0.5"
                           data-fader="${t.id}">
                </div>
                <div class="fader-dB" data-db="${t.id}">${t.gain.toFixed(1)}</div>
            </div>
        `).join('');

        // Pan input events
        container.querySelectorAll('[data-pan]').forEach(input => {
            input.addEventListener('input', (e) => {
                const id = e.target.dataset.pan;
                const track = TrackList.getTracks().find(t => t.id === id);
                if (track) {
                    track.pan = parseInt(e.target.value);
                    const label = container.querySelector(`[data-db="${id}"]`);
                    // Update pan label
                    const panLabel = e.target.parentElement.nextElementSibling;
                    if (panLabel) {
                        panLabel.textContent = track.pan === 0 ? 'C' : (track.pan < 0 ? 'L' + Math.abs(track.pan) : 'R' + track.pan);
                    }
                }
            });
        });

        // Fader input events
        container.querySelectorAll('[data-fader]').forEach(input => {
            input.addEventListener('input', (e) => {
                const id = e.target.dataset.fader;
                const db = parseFloat(e.target.value);
                TrackList.setGain(id, db);
                const label = container.querySelector(`[data-db="${id}"]`);
                if (label) label.textContent = db.toFixed(1);
            });
        });
    }

    function updateMeters() {
        const tracks = TrackList.getTracks();
        tracks.forEach(t => {
            const meter = document.querySelector(`[data-meter="${t.id}"]`);
            if (!meter) return;
            if (t.mute || !Transport.isPlaying()) {
                meter.style.height = '0%';
                return;
            }
            // Simulated meter level
            const base = t.solo ? 0.6 : 0.4;
            const level = base + Math.random() * 0.3;
            meter.style.height = Math.round(level * 100) + '%';
            meter.style.background = level > 0.9 ? 'var(--danger)' : level > 0.75 ? 'var(--warning)' : 'var(--success)';
        });

        // Master meter
        const masterL = document.getElementById('master-meter-L');
        const masterR = document.getElementById('master-meter-R');
        if (masterL && masterR && Transport.isPlaying()) {
            const level = 0.3 + Math.random() * 0.4;
            masterL.style.height = Math.round(level * 100) + '%';
            masterR.style.height = Math.round((level + (Math.random() - 0.5) * 0.1) * 100) + '%';
            const color = level > 0.9 ? 'var(--danger)' : level > 0.75 ? 'var(--warning)' : 'var(--success)';
            masterL.style.background = color;
            masterR.style.background = color;
        }
    }

    function escHtml(str) {
        return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }

    return { init, render, updateMeters };
})();
