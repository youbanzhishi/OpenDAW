/**
 * piano_roll.js — MIDI piano roll editor for VCMix (Phase 13).
 *
 * Features:
 *   - Grid drawing (time × pitch)
 *   - Note rectangle rendering with velocity coloring
 *   - Play cursor
 *   - Zoom / scroll (mouse wheel + drag)
 *   - Note name labels on piano keys
 *
 * No npm/webpack — pure vanilla JS + Canvas 2D.
 */

class PianoRollView {
    /**
     * @param {string} canvasId - Canvas element ID
     * @param {object} options - Configuration options
     */
    constructor(canvasId, options = {}) {
        this.canvas = document.getElementById(canvasId);
        if (!this.canvas) return;
        this.ctx = this.canvas.getContext('2d');

        // Configuration
        this.noteColor = options.noteColor || '#4fc3f7';
        this.noteHoverColor = options.noteHoverColor || '#81d4fa';
        this.gridColor = options.gridColor || '#1a2332';
        this.bgColor = options.bgColor || '#0d1117';
        this.keyWidth = 48;
        this.headerHeight = 24;
        this.noteHeight = 14;    // Pixels per semitone
        this.beatWidth = 80;     // Pixels per beat at zoom 1.0

        // Data
        this.notes = [];        // Array of {note, velocity, start_beat, duration_beats, channel}
        this.bpm = 120;
        this.totalBeats = 32;
        this.minNote = 36;      // C2
        this.maxNote = 96;      // C7

        // View state
        this.zoomX = 1.0;
        this.zoomY = 1.0;
        this.scrollX = 0;       // beats
        this.scrollY = this.maxNote; // note number at top

        // Interaction
        this.isDragging = false;
        this.dragStartX = 0;
        this.dragStartY = 0;
        this.dragStartScrollX = 0;
        this.dragStartScrollY = 0;

        // Playback
        this.isPlaying = false;
        this.playBeat = 0;

        this._bindEvents();
        this.resize();
    }

    /** Load MIDI note data from API response */
    loadFromAPI(data) {
        this.notes = data.notes || [];
        this.bpm = data.bpm || 120;
        this.totalBeats = data.total_beats || 32;

        // Auto-range notes
        if (this.notes.length > 0) {
            const minN = Math.min(...this.notes.map(n => n.note || 60));
            const maxN = Math.max(...this.notes.map(n => n.note || 60));
            this.minNote = Math.max(0, minN - 4);
            this.maxNote = Math.min(127, maxN + 4);
        }

        this.scrollX = 0;
        this.scrollY = this.maxNote;
        this.draw();
    }

    /** Load synthetic MIDI data for demo */
    loadSynthetic() {
        this.bpm = 120;
        this.totalBeats = 16;
        this.minNote = 48;
        this.maxNote = 84;
        this.notes = [];

        // C major scale
        const scale = [60, 62, 64, 65, 67, 69, 71, 72];
        for (let i = 0; i < scale.length; i++) {
            this.notes.push({
                note: scale[i],
                velocity: 80 + Math.floor(Math.random() * 40),
                start_beat: i * 2,
                duration_beats: 1.5,
                channel: 0,
            });
        }

        // Add a chord
        this.notes.push(
            { note: 60, velocity: 100, start_beat: 16, duration_beats: 4, channel: 0 },
            { note: 64, velocity: 90, start_beat: 16, duration_beats: 4, channel: 0 },
            { note: 67, velocity: 95, start_beat: 16, duration_beats: 4, channel: 0 },
        );

        // Add bass
        this.notes.push(
            { note: 48, velocity: 110, start_beat: 0, duration_beats: 4, channel: 1 },
            { note: 48, velocity: 110, start_beat: 8, duration_beats: 4, channel: 1 },
            { note: 43, velocity: 100, start_beat: 16, duration_beats: 4, channel: 1 },
        );

        this.scrollX = 0;
        this.scrollY = this.maxNote;
        this.draw();
    }

    /** Resize canvas */
    resize() {
        if (!this.canvas) return;
        const rect = this.canvas.parentElement.getBoundingClientRect();
        this.canvas.width = rect.width || 900;
        this.canvas.height = rect.height || 400;
        this.draw();
    }

    /** Main draw routine */
    draw() {
        if (!this.ctx || !this.canvas) return;
        const ctx = this.ctx;
        const w = this.canvas.width;
        const h = this.canvas.height;

        // Clear
        ctx.fillStyle = this.bgColor;
        ctx.fillRect(0, 0, w, h);

        const gridW = w - this.keyWidth;
        const gridH = h - this.headerHeight;
        const numNotes = this.maxNote - this.minNote + 1;
        const noteH = this.noteHeight * this.zoomY;
        const beatW = this.beatWidth * this.zoomX;

        // ── Piano keys (left sidebar) ──
        this._drawPianoKeys(ctx, gridH, noteH);

        // ── Clip grid area ──
        ctx.save();
        ctx.beginPath();
        ctx.rect(this.keyWidth, this.headerHeight, gridW, gridH);
        ctx.clip();

        // ── Grid lines ──
        this._drawGrid(ctx, gridW, gridH, noteH, beatW);

        // ── Note rectangles ──
        this._drawNotes(ctx, noteH, beatW);

        // ── Play cursor ──
        if (this.isPlaying || this.playBeat > 0) {
            const playX = this.keyWidth + (this.playBeat - this.scrollX) * beatW;
            if (playX >= this.keyWidth && playX <= w) {
                ctx.strokeStyle = '#ef5350';
                ctx.lineWidth = 2;
                ctx.beginPath();
                ctx.moveTo(playX, this.headerHeight);
                ctx.lineTo(playX, h);
                ctx.stroke();
            }
        }

        ctx.restore();

        // ── Time ruler (top) ──
        this._drawTimeRuler(ctx, gridW, beatW);
    }

    /** Draw piano key labels on left sidebar */
    _drawPianoKeys(ctx, gridH, noteH) {
        const noteNames = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];

        for (let n = this.minNote; n <= this.maxNote; n++) {
            const y = this.headerHeight + (this.scrollY - n - 0.5) * noteH;
            if (y < this.headerHeight - noteH || y > this.canvas.height) continue;

            const noteName = noteNames[n % 12];
            const octave = Math.floor(n / 12) - 1;
            const isBlack = noteName.includes('#');

            // Key background
            ctx.fillStyle = isBlack ? '#1a1a2e' : '#2a2a4e';
            ctx.fillRect(0, y - noteH / 2, this.keyWidth, noteH);

            // Highlight C notes
            if (noteName === 'C') {
                ctx.fillStyle = '#3a3a5e';
                ctx.fillRect(0, y - noteH / 2, this.keyWidth, noteH);
            }

            // Key border
            ctx.strokeStyle = '#2a3a5c';
            ctx.lineWidth = 0.5;
            ctx.strokeRect(0, y - noteH / 2, this.keyWidth, noteH);

            // Label
            ctx.fillStyle = isBlack ? '#a0a0b0' : '#e0e0e0';
            ctx.font = '10px monospace';
            ctx.textAlign = 'right';
            ctx.fillText(`${noteName}${octave}`, this.keyWidth - 4, y + 3);
        }

        // Sidebar border
        ctx.strokeStyle = '#4a5a7c';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(this.keyWidth, 0);
        ctx.lineTo(this.keyWidth, this.canvas.height);
        ctx.stroke();
    }

    /** Draw horizontal (pitch) and vertical (beat) grid lines */
    _drawGrid(ctx, gridW, gridH, noteH, beatW) {
        ctx.strokeStyle = this.gridColor;
        ctx.lineWidth = 0.5;

        // Horizontal lines (per note)
        for (let n = this.minNote; n <= this.maxNote; n++) {
            const y = this.headerHeight + (this.scrollY - n - 0.5) * noteH;
            if (y < this.headerHeight || y > this.canvas.height) continue;

            const noteNames = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
            const noteName = noteNames[n % 12];

            if (noteName === 'C') {
                ctx.strokeStyle = '#2a3a5c';
                ctx.lineWidth = 1;
            } else if (noteName.includes('#')) {
                ctx.strokeStyle = '#0f1520';
                ctx.lineWidth = 0.5;
                // Fill black key rows darker
                ctx.fillStyle = 'rgba(0,0,0,0.15)';
                ctx.fillRect(this.keyWidth, y - noteH / 2, gridW, noteH);
            } else {
                ctx.strokeStyle = this.gridColor;
                ctx.lineWidth = 0.5;
            }

            ctx.beginPath();
            ctx.moveTo(this.keyWidth, y);
            ctx.lineTo(this.keyWidth + gridW, y);
            ctx.stroke();
        }

        // Vertical lines (per beat)
        const startBeat = Math.floor(this.scrollX);
        const endBeat = Math.ceil(this.scrollX + gridW / beatW);

        for (let b = startBeat; b <= endBeat; b++) {
            const x = this.keyWidth + (b - this.scrollX) * beatW;
            if (x < this.keyWidth || x > this.canvas.width) continue;

            // Bar lines (every 4 beats) thicker
            if (b % 4 === 0) {
                ctx.strokeStyle = '#2a3a5c';
                ctx.lineWidth = 1.5;
            } else {
                ctx.strokeStyle = this.gridColor;
                ctx.lineWidth = 0.5;
            }

            ctx.beginPath();
            ctx.moveTo(x, this.headerHeight);
            ctx.lineTo(x, this.canvas.height);
            ctx.stroke();
        }
    }

    /** Draw MIDI note rectangles */
    _drawNotes(ctx, noteH, beatW) {
        for (const note of this.notes) {
            const n = note.note || 60;
            if (n < this.minNote || n > this.maxNote) continue;

            const x = this.keyWidth + (note.start_beat - this.scrollX) * beatW;
            const y = this.headerHeight + (this.scrollY - n - 0.5) * noteH;
            const noteW = Math.max(2, note.duration_beats * beatW - 1);

            // Skip if off-screen
            if (x + noteW < this.keyWidth || x > this.canvas.width) continue;
            if (y + noteH < this.headerHeight || y > this.canvas.height) continue;

            // Velocity-based coloring
            const vel = (note.velocity || 100) / 127;
            const r = Math.floor(79 + vel * 50);
            const g = Math.floor(195 - vel * 30);
            const b = Math.floor(247 - vel * 50);

            // Note body
            ctx.fillStyle = `rgb(${r},${g},${b})`;
            ctx.beginPath();
            const radius = Math.min(3, noteH / 4);
            this._roundRect(ctx, x, y - noteH / 2 + 1, noteW, noteH - 2, radius);
            ctx.fill();

            // Note border
            ctx.strokeStyle = `rgba(${r + 30},${g + 30},${b + 30},0.5)`;
            ctx.lineWidth = 0.5;
            ctx.stroke();

            // Note label (if wide enough)
            if (noteW > 20) {
                const noteNames = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
                const name = `${noteNames[n % 12]}${Math.floor(n / 12) - 1}`;
                ctx.fillStyle = 'rgba(0,0,0,0.7)';
                ctx.font = '9px monospace';
                ctx.textAlign = 'left';
                ctx.fillText(name, x + 3, y + 3);
            }
        }
    }

    /** Draw time ruler at the top */
    _drawTimeRuler(ctx, gridW, beatW) {
        // Header background
        ctx.fillStyle = '#16213e';
        ctx.fillRect(0, 0, this.canvas.width, this.headerHeight);

        const startBeat = Math.floor(this.scrollX);
        const endBeat = Math.ceil(this.scrollX + gridW / beatW);

        ctx.fillStyle = '#a0a0b0';
        ctx.font = '10px monospace';
        ctx.textAlign = 'center';

        for (let b = startBeat; b <= endBeat; b++) {
            const x = this.keyWidth + (b - this.scrollX) * beatW;
            if (x < this.keyWidth || x > this.canvas.width) continue;

            // Show beat numbers, bar numbers on beat 0
            if (b % 4 === 0) {
                ctx.fillStyle = '#e0e0e0';
                ctx.font = '11px monospace';
                const bar = Math.floor(b / 4) + 1;
                ctx.fillText(`${bar}`, x, 15);
            } else if (beatW > 20) {
                ctx.fillStyle = '#a0a0b0';
                ctx.font = '9px monospace';
                ctx.fillText(`${b % 4 + 1}`, x, 15);
            }

            // Tick
            ctx.strokeStyle = '#4a5a7c';
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(x, this.headerHeight - 4);
            ctx.lineTo(x, this.headerHeight);
            ctx.stroke();
        }

        // Bottom border
        ctx.strokeStyle = '#4a5a7c';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(0, this.headerHeight);
        ctx.lineTo(this.canvas.width, this.headerHeight);
        ctx.stroke();
    }

    /** Draw rounded rectangle */
    _roundRect(ctx, x, y, w, h, r) {
        r = Math.min(r, w / 2, h / 2);
        ctx.moveTo(x + r, y);
        ctx.lineTo(x + w - r, y);
        ctx.quadraticCurveTo(x + w, y, x + w, y + r);
        ctx.lineTo(x + w, y + h - r);
        ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
        ctx.lineTo(x + r, y + h);
        ctx.quadraticCurveTo(x, y + h, x, y + h - r);
        ctx.lineTo(x, y + r);
        ctx.quadraticCurveTo(x, y, x + r, y);
    }

    /** Bind mouse events for zoom/scroll */
    _bindEvents() {
        if (!this.canvas) return;

        // Mouse wheel zoom
        this.canvas.addEventListener('wheel', (e) => {
            e.preventDefault();
            if (e.ctrlKey || e.metaKey) {
                // Vertical zoom
                const zoomDelta = e.deltaY > 0 ? 0.95 : 1.05;
                this.zoomY = Math.max(0.5, Math.min(4.0, this.zoomY * zoomDelta));
            } else {
                // Horizontal zoom
                const zoomDelta = e.deltaY > 0 ? 0.9 : 1.1;
                this.zoomX = Math.max(0.2, Math.min(10.0, this.zoomX * zoomDelta));
            }
            this.draw();
        });

        // Drag to scroll
        this.canvas.addEventListener('mousedown', (e) => {
            this.isDragging = true;
            this.dragStartX = e.clientX;
            this.dragStartY = e.clientY;
            this.dragStartScrollX = this.scrollX;
            this.dragStartScrollY = this.scrollY;
            e.preventDefault();
        });

        window.addEventListener('mousemove', (e) => {
            if (!this.isDragging) return;
            const dx = e.clientX - this.dragStartX;
            const dy = e.clientY - this.dragStartY;
            const beatW = this.beatWidth * this.zoomX;
            const noteH = this.noteHeight * this.zoomY;

            this.scrollX = Math.max(0, this.dragStartScrollX - dx / beatW);
            this.scrollY = Math.min(127, this.dragStartScrollY + dy / noteH);
            this.scrollY = Math.max(this.minNote, this.scrollY);
            this.draw();
        });

        window.addEventListener('mouseup', () => {
            this.isDragging = false;
        });
    }

    /** Set play position in beats */
    setPlayBeat(beat) {
        this.playBeat = beat;
        this.isPlaying = true;
        this.draw();
    }

    /** Stop playback */
    stop() {
        this.isPlaying = false;
        this.draw();
    }

    /** Reset view */
    resetView() {
        this.zoomX = 1.0;
        this.zoomY = 1.0;
        this.scrollX = 0;
        this.scrollY = this.maxNote;
        this.playBeat = 0;
        this.isPlaying = false;
        this.draw();
    }
}

// Export for use in app.js
window.PianoRollView = PianoRollView;
