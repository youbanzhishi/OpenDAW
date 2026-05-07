/**
 * waveform.js — Canvas waveform visualization module for VCMix (Phase 13).
 *
 * Features:
 *   - Read WAV data (via API) → decode → downsample → draw peaks
 *   - Zoom / scroll with mouse wheel and drag
 *   - Selection highlighting
 *   - Time ruler
 *   - Minimap overview
 *
 * No npm/webpack — pure vanilla JS + Canvas 2D.
 */

class WaveformView {
    /**
     * @param {string} canvasId - Canvas element ID
     * @param {object} options - Configuration options
     */
    constructor(canvasId, options = {}) {
        this.canvas = document.getElementById(canvasId);
        if (!this.canvas) return;
        this.ctx = this.canvas.getContext('2d');

        // Configuration
        this.waveColor = options.waveColor || '#4fc3f7';
        this.bgColor = options.bgColor || '#0d1117';
        this.gridColor = options.gridColor || '#1a2332';
        this.rulerColor = options.rulerColor || '#a0a0b0';
        this.selectionColor = options.selectionColor || 'rgba(255, 167, 38, 0.3)';
        this.peakColor = options.peakColor || '#ef5350';

        // Data
        this.peaks = [];        // Normalized peak values [0..1]
        this.sampleRate = 44100;
        this.duration = 0;
        this.channels = 1;

        // View state
        this.zoomLevel = 1.0;   // 1.0 = fit all, 2.0 = 2x zoom
        this.scrollOffset = 0;  // 0..1 (fraction of total width)
        this.selection = null;  // { start: 0..1, end: 0..1 }
        this.isPlaying = false;
        this.playPosition = 0;  // 0..1

        // Interaction state
        this.isDragging = false;
        this.dragStartX = 0;
        this.dragStartOffset = 0;

        this._bindEvents();
        this.resize();
    }

    /** Load waveform peak data from API response */
    loadFromAPI(data) {
        this.peaks = data.peaks || [];
        this.sampleRate = data.sample_rate || 44100;
        this.duration = data.duration_s || 0;
        this.channels = data.channels || 1;
        this.zoomLevel = 1.0;
        this.scrollOffset = 0;
        this.selection = null;
        this.draw();
    }

    /** Generate synthetic waveform for demo/testing */
    loadSynthetic(duration = 10, sampleRate = 44100, numPeaks = 2000) {
        this.sampleRate = sampleRate;
        this.duration = duration;
        this.channels = 1;
        this.peaks = [];
        for (let i = 0; i < numPeaks; i++) {
            const t = i / numPeaks;
            // Composite waveform: sine + noise envelope
            const env = Math.exp(-3 * Math.abs(t - 0.5));
            const wave = Math.sin(t * 40 * Math.PI) * 0.5 +
                         Math.sin(t * 80 * Math.PI) * 0.3 +
                         Math.random() * 0.2;
            this.peaks.push(Math.min(1.0, Math.max(0, Math.abs(wave) * env)));
        }
        this.zoomLevel = 1.0;
        this.scrollOffset = 0;
        this.draw();
    }

    /** Resize canvas to fill container */
    resize() {
        if (!this.canvas) return;
        const rect = this.canvas.parentElement.getBoundingClientRect();
        this.canvas.width = rect.width || 800;
        this.canvas.height = rect.height || 200;
        this.draw();
    }

    /** Main draw routine */
    draw() {
        if (!this.ctx || !this.canvas) return;
        const ctx = this.ctx;
        const w = this.canvas.width;
        const h = this.canvas.height;
        const padding = { top: 24, bottom: 24, left: 50, right: 10 };
        const drawW = w - padding.left - padding.right;
        const drawH = h - padding.top - padding.bottom;

        // Clear
        ctx.fillStyle = this.bgColor;
        ctx.fillRect(0, 0, w, h);

        if (this.peaks.length === 0) {
            ctx.fillStyle = this.rulerColor;
            ctx.font = '14px monospace';
            ctx.textAlign = 'center';
            ctx.fillText('No waveform data — load a track', w / 2, h / 2);
            return;
        }

        // Compute visible range
        const visibleFraction = 1.0 / this.zoomLevel;
        const viewStart = this.scrollOffset;
        const viewEnd = Math.min(1.0, viewStart + visibleFraction);
        const startIdx = Math.floor(viewStart * this.peaks.length);
        const endIdx = Math.ceil(viewEnd * this.peaks.length);
        const visiblePeaks = this.peaks.slice(startIdx, endIdx);

        // ── Time ruler ──
        this._drawTimeRuler(ctx, w, padding, viewStart, viewEnd);

        // ── Grid lines ──
        ctx.strokeStyle = this.gridColor;
        ctx.lineWidth = 1;
        const centerY = padding.top + drawH / 2;
        // Center line
        ctx.beginPath();
        ctx.moveTo(padding.left, centerY);
        ctx.lineTo(padding.left + drawW, centerY);
        ctx.stroke();
        // -6dB / +6dB lines
        for (const frac of [0.25, 0.75]) {
            const y = padding.top + drawH * frac;
            ctx.beginPath();
            ctx.setLineDash([4, 4]);
            ctx.moveTo(padding.left, y);
            ctx.lineTo(padding.left + drawW, y);
            ctx.stroke();
        }
        ctx.setLineDash([]);

        // ── Draw waveform ──
        ctx.fillStyle = this.waveColor;
        ctx.strokeStyle = this.waveColor;
        ctx.lineWidth = 1;
        ctx.beginPath();

        const barWidth = Math.max(1, drawW / visiblePeaks.length);

        for (let i = 0; i < visiblePeaks.length; i++) {
            const x = padding.left + (i / visiblePeaks.length) * drawW;
            const peakVal = visiblePeaks[i] || 0;
            const halfH = peakVal * (drawH / 2);

            // Top half
            ctx.fillRect(x, centerY - halfH, Math.max(1, barWidth - 0.5), halfH);
            // Bottom half (mirror)
            ctx.fillRect(x, centerY, Math.max(1, barWidth - 0.5), halfH);
        }

        // ── Selection highlight ──
        if (this.selection) {
            const selStartX = padding.left + ((this.selection.start - viewStart) / visibleFraction) * drawW;
            const selEndX = padding.left + ((this.selection.end - viewStart) / visibleFraction) * drawW;
            ctx.fillStyle = this.selectionColor;
            ctx.fillRect(selStartX, padding.top, selEndX - selStartX, drawH);

            // Selection borders
            ctx.strokeStyle = '#ffa726';
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(selStartX, padding.top);
            ctx.lineTo(selStartX, padding.top + drawH);
            ctx.moveTo(selEndX, padding.top);
            ctx.lineTo(selEndX, padding.top + drawH);
            ctx.stroke();
        }

        // ── Play cursor ──
        if (this.playPosition >= viewStart && this.playPosition <= viewEnd) {
            const playX = padding.left + ((this.playPosition - viewStart) / visibleFraction) * drawW;
            ctx.strokeStyle = this.peakColor;
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.moveTo(playX, padding.top);
            ctx.lineTo(playX, padding.top + drawH);
            ctx.stroke();
        }

        // ── dB scale labels ──
        ctx.fillStyle = this.rulerColor;
        ctx.font = '10px monospace';
        ctx.textAlign = 'right';
        ctx.fillText('0 dB', padding.left - 4, padding.top + 4);
        ctx.fillText('-6', padding.left - 4, padding.top + drawH * 0.25 + 4);
        ctx.fillText('-∞', padding.left - 4, centerY + 4);
        ctx.fillText('-6', padding.left - 4, padding.top + drawH * 0.75 + 4);
    }

    /** Draw time ruler at the top */
    _drawTimeRuler(ctx, canvasW, padding, viewStart, viewEnd) {
        const drawW = canvasW - padding.left - padding.right;
        const totalDuration = this.duration;
        const viewDuration = (viewEnd - viewStart) * totalDuration;

        // Determine tick interval
        let tickInterval = 1.0; // seconds
        const pixelsPerTick = drawW / (viewDuration / tickInterval);
        if (pixelsPerTick < 30) tickInterval = 5.0;
        if (pixelsPerTick < 15) tickInterval = 10.0;
        if (pixelsPerTick > 120) tickInterval = 0.5;
        if (pixelsPerTick > 240) tickInterval = 0.1;

        const viewStartSec = viewStart * totalDuration;
        const viewEndSec = viewEnd * totalDuration;
        const firstTick = Math.ceil(viewStartSec / tickInterval) * tickInterval;

        ctx.strokeStyle = this.gridColor;
        ctx.fillStyle = this.rulerColor;
        ctx.font = '10px monospace';
        ctx.textAlign = 'center';
        ctx.lineWidth = 1;

        for (let t = firstTick; t <= viewEndSec; t += tickInterval) {
            const fraction = (t / totalDuration - viewStart) / (viewEnd - viewStart);
            const x = padding.left + fraction * drawW;

            // Tick line
            ctx.beginPath();
            ctx.moveTo(x, 0);
            ctx.lineTo(x, padding.top);
            ctx.stroke();

            // Label
            const label = this._formatTime(t);
            ctx.fillText(label, x, 14);
        }
    }

    /** Format seconds to mm:ss.s */
    _formatTime(seconds) {
        const min = Math.floor(seconds / 60);
        const sec = seconds % 60;
        if (min > 0) return `${min}:${sec.toFixed(1).padStart(4, '0')}`;
        return `${sec.toFixed(1)}s`;
    }

    /** Bind mouse events for zoom/scroll/selection */
    _bindEvents() {
        if (!this.canvas) return;

        // Mouse wheel zoom
        this.canvas.addEventListener('wheel', (e) => {
            e.preventDefault();
            const zoomDelta = e.deltaY > 0 ? 0.9 : 1.1;
            const oldZoom = this.zoomLevel;
            this.zoomLevel = Math.max(1.0, Math.min(100.0, this.zoomLevel * zoomDelta));

            // Zoom toward mouse position
            const rect = this.canvas.getBoundingClientRect();
            const mouseX = (e.clientX - rect.left) / rect.width;
            const visibleFraction = 1.0 / this.zoomLevel;
            const oldVisibleFraction = 1.0 / oldZoom;
            const mouseWorld = this.scrollOffset + mouseX * oldVisibleFraction;
            this.scrollOffset = Math.max(0, Math.min(1 - visibleFraction,
                mouseWorld - mouseX * visibleFraction));

            this.draw();
        });

        // Middle button / right button drag to scroll
        this.canvas.addEventListener('mousedown', (e) => {
            if (e.button === 1 || (e.button === 0 && e.shiftKey)) {
                this.isDragging = true;
                this.dragStartX = e.clientX;
                this.dragStartOffset = this.scrollOffset;
                e.preventDefault();
            }
        });

        window.addEventListener('mousemove', (e) => {
            if (!this.isDragging) return;
            const dx = e.clientX - this.dragStartX;
            const visibleFraction = 1.0 / this.zoomLevel;
            const scrollDelta = (dx / this.canvas.width) * visibleFraction;
            this.scrollOffset = Math.max(0, Math.min(1 - visibleFraction,
                this.dragStartOffset - scrollDelta));
            this.draw();
        });

        window.addEventListener('mouseup', () => {
            this.isDragging = false;
        });

        // Double-click to set selection start, then end
        let selectionClick = 0;
        this.canvas.addEventListener('dblclick', (e) => {
            const rect = this.canvas.getBoundingClientRect();
            const padding = { left: 50, right: 10 };
            const drawW = this.canvas.width - padding.left - padding.right;
            const mouseX = (e.clientX - rect.left - padding.left) / drawW;
            const visibleFraction = 1.0 / this.zoomLevel;
            const worldX = this.scrollOffset + mouseX * visibleFraction;

            if (selectionClick === 0) {
                this.selection = { start: worldX, end: worldX };
                selectionClick = 1;
            } else {
                if (this.selection) {
                    this.selection.end = worldX;
                    if (this.selection.start > this.selection.end) {
                        [this.selection.start, this.selection.end] = [this.selection.end, this.selection.start];
                    }
                }
                selectionClick = 0;
            }
            this.draw();
        });
    }

    /** Set play position (0..1) */
    setPlayPosition(pos) {
        this.playPosition = Math.max(0, Math.min(1, pos));
        this.isPlaying = true;
        this.draw();
    }

    /** Stop playback */
    stop() {
        this.isPlaying = false;
        this.draw();
    }

    /** Reset zoom and scroll */
    resetView() {
        this.zoomLevel = 1.0;
        this.scrollOffset = 0;
        this.selection = null;
        this.draw();
    }
}

// Export for use in app.js
window.WaveformView = WaveformView;
