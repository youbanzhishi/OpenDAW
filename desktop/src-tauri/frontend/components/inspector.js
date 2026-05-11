/**
 * OpenDAW — Inspector Panel
 * Right panel: selected track/clip properties
 */
const Inspector = (() => {
    function init() {
        // Inspector is reactive — populated by show()
    }

    function show(track) {
        const content = document.getElementById('inspector-content');
        if (!content) return;

        content.innerHTML = `
            <div class="inspector-section">
                <div class="inspector-section-title">Track</div>
                <div class="inspector-row">
                    <span class="inspector-label">Name</span>
                    <span class="inspector-value">${escHtml(track.name)}</span>
                </div>
                <div class="inspector-row">
                    <span class="inspector-label">Type</span>
                    <span class="inspector-value">${track.type.toUpperCase()}</span>
                </div>
                <div class="inspector-row">
                    <span class="inspector-label">Color</span>
                    <span class="inspector-value">
                        <span style="display:inline-block;width:20px;height:20px;border-radius:4px;background:${track.color}"></span>
                    </span>
                </div>
            </div>

            <div class="inspector-section">
                <div class="inspector-section-title">Audio</div>
                <div class="inspector-row">
                    <span class="inspector-label">Volume</span>
                    <span class="inspector-value"><input type="number" value="${track.gain}" step="0.5" min="-60" max="12" data-inspector-gain="${track.id}"> dB</span>
                </div>
                <div class="inspector-row">
                    <span class="inspector-label">Pan</span>
                    <span class="inspector-value"><input type="range" min="-100" max="100" value="${track.pan}" data-inspector-pan="${track.id}" style="width:100px"></span>
                </div>
                <div class="inspector-row">
                    <span class="inspector-label">Mute</span>
                    <span class="inspector-value">${track.mute ? '🟡 Yes' : '⚪ No'}</span>
                </div>
                <div class="inspector-row">
                    <span class="inspector-label">Solo</span>
                    <span class="inspector-value">${track.solo ? '🔵 Yes' : '⚪ No'}</span>
                </div>
            </div>

            <div class="inspector-section">
                <div class="inspector-section-title">Routing</div>
                <div class="inspector-row">
                    <span class="inspector-label">Input</span>
                    <span class="inspector-value"><select><option>Stereo In 1/2</option><option>Mono In 1</option></select></span>
                </div>
                <div class="inspector-row">
                    <span class="inspector-label">Output</span>
                    <span class="inspector-value"><select><option>Master</option><option>Bus A</option></select></span>
                </div>
            </div>
        `;

        // Wire inspector inputs
        const gainInput = content.querySelector(`[data-inspector-gain="${track.id}"]`);
        if (gainInput) {
            gainInput.addEventListener('change', (e) => {
                TrackList.setGain(track.id, parseFloat(e.target.value));
                TrackList.render();
                Mixer.render();
            });
        }

        const panInput = content.querySelector(`[data-inspector-pan="${track.id}"]`);
        if (panInput) {
            panInput.addEventListener('input', (e) => {
                const t = TrackList.getTracks().find(tr => tr.id === track.id);
                if (t) t.pan = parseInt(e.target.value);
            });
        }
    }

    function clear() {
        const content = document.getElementById('inspector-content');
        if (!content) return;
        content.innerHTML = `
            <div class="empty-state">
                <svg width="48" height="48" viewBox="0 0 48 48"><rect x="8" y="4" width="32" height="40" rx="3" stroke="currentColor" stroke-width="2" fill="none" opacity="0.3"/><path d="M16 16h16M16 22h12M16 28h8" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" opacity="0.3"/></svg>
                <p>Select a track or clip</p>
            </div>`;
    }

    function escHtml(str) {
        return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }

    return { init, show, clear };
})();
