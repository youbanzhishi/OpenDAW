/**
 * OpenDAW — Virtual Piano Keyboard
 * Touch-friendly piano for mobile/tablet MIDI input
 */
const PianoKeyboard = (() => {
    const NOTES = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'];
    let baseOctave = 4;
    let visible = false;
    let activeKeys = new Set();

    function init() {
        const btn = document.getElementById('btn-piano-close');
        if (btn) btn.addEventListener('click', hide);

        const octaveSelect = document.getElementById('piano-octave');
        if (octaveSelect) {
            octaveSelect.addEventListener('change', (e) => {
                baseOctave = parseInt(e.target.value);
                renderKeys();
            });
        }

        renderKeys();
    }

    function renderKeys() {
        const container = document.getElementById('piano-keys');
        if (!container) return;

        container.innerHTML = '';
        const octaves = 2; // Show 2 octaves

        for (let oct = 0; oct < octaves; oct++) {
            const currentOct = baseOctave + oct;
            NOTES.forEach((note, i) => {
                const isBlack = note.includes('#');
                const key = document.createElement('div');
                key.className = `piano-key ${isBlack ? 'black' : 'white'}`;
                key.dataset.note = note + currentOct;
                key.dataset.midi = (currentOct + 1) * 12 + i;

                if (!isBlack) {
                    const label = document.createElement('span');
                    label.className = 'key-note';
                    label.textContent = note === 'C' ? `C${currentOct}` : '';
                    key.appendChild(label);
                }

                // Pointer events for multi-touch
                key.addEventListener('pointerdown', onNoteOn);
                key.addEventListener('pointerup', onNoteOff);
                key.addEventListener('pointerleave', onNoteOff);
                key.addEventListener('pointercancel', onNoteOff);

                container.appendChild(key);
            });
        }
    }

    function onNoteOn(e) {
        e.preventDefault();
        const key = e.currentTarget;
        const note = key.dataset.note;
        const midi = parseInt(key.dataset.midi);

        if (activeKeys.has(note)) return;
        activeKeys.add(note);
        key.classList.add('pressed');

        // Trigger MIDI note on via Tauri (if available)
        console.log('Note ON:', note, 'MIDI:', midi);

        // Visual feedback
        key.style.background = 'var(--accent)';
        key.setPointerCapture(e.pointerId);
    }

    function onNoteOff(e) {
        const key = e.currentTarget;
        const note = key.dataset.note;

        activeKeys.delete(note);
        key.classList.remove('pressed');

        // Restore key color
        const isBlack = key.classList.contains('black');
        key.style.background = '';

        console.log('Note OFF:', note);
    }

    function show() {
        visible = true;
        const panel = document.getElementById('piano-keyboard');
        if (panel) panel.classList.remove('hidden');
    }

    function hide() {
        visible = false;
        const panel = document.getElementById('piano-keyboard');
        if (panel) panel.classList.add('hidden');
    }

    function toggle() {
        if (visible) hide(); else show();
    }

    function isVisible() { return visible; }

    return { init, show, hide, toggle, isVisible };
})();
