/**
 * spectrum.js — FFT spectrum analysis visualization for VCMix (Phase 13).
 *
 * Features:
 *   - Real-time spectrum bar chart (1/3 octave bands)
 *   - Level meters (RMS + Peak + LUFS)
 *   - Spectrogram waterfall display
 *
 * No npm/webpack — pure vanilla JS + Canvas 2D.
 */

class SpectrumView {
    /**
     * @param {string} canvasId - Canvas element for spectrum bars
     * @param {string} meterId - Container element ID for level meters
     * @param {string} spectrogramId - Canvas element for spectrogram
     */
    constructor(canvasId, meterId, spectrogramId) {
        this.canvas = document.getElementById(canvasId);
        this.ctx = this.canvas ? this.canvas.getContext('2d') : null;
        this.meterContainer = document.getElementById(meterId);
        this.spectrogramCanvas = document.getElementById(spectrogramId);
        this.spectrogramCtx = this.spectrogramCanvas ? this.spectrogramCanvas.getContext('2d') : null;

        // Spectrum data
        this.frequencies = [];
        this.magnitudes = [];
        this.sampleRate = 44100;
        this.fftSize = 2048;

        // Level meter state
        this.rmsDb = -60;
        this.peakDb = -60;
        this.lufs = -70;
        this.peakHold = -60;
        this.peakHoldCount = 0;

        // Spectrogram history
        this.spectrogramHistory = [];
        this.maxSpectrogramLines = 200;

        // 1/3 octave band center frequencies
        this.thirdOctaveBands = this._generateThirdOctaveBands(20, 20000);

        // Animation
        this.animFrameId = null;

        this._initMeters();
    }

    /** Generate 1/3 octave band center frequencies */
    _generateThirdOctaveBands(fMin, fMax) {
        const bands = [];
        const refFreq = 1000;
        for (let i = -30; i <= 30; i++) {
            const freq = refFreq * Math.pow(2, i / 3);
            if (freq >= fMin && freq <= fMax) {
                bands.push(freq);
            }
        }
        return bands;
    }

    /** Initialize level meter DOM elements */
    _initMeters() {
        if (!this.meterContainer) return;
        this.meterContainer.innerHTML = `
            <div class="level-meter-group">
                <div class="level-meter-label">RMS</div>
                <div class="level-meter-bar-bg"><div class="level-meter-bar-fill" id="meter-rms-fill"></div></div>
                <div class="level-meter-value" id="meter-rms-val">-∞ dB</div>
            </div>
            <div class="level-meter-group">
                <div class="level-meter-label">Peak</div>
                <div class="level-meter-bar-bg"><div class="level-meter-bar-fill" id="meter-peak-fill"></div></div>
                <div class="level-meter-value" id="meter-peak-val">-∞ dB</div>
            </div>
            <div class="level-meter-group">
                <div class="level-meter-label">LUFS</div>
                <div class="level-meter-bar-bg"><div class="level-meter-bar-fill" id="meter-lufs-fill"></div></div>
                <div class="level-meter-value" id="meter-lufs-val">-∞ LUFS</div>
            </div>
        `;
    }

    /** Load spectrum data from API response */
    loadFromAPI(data) {
        this.frequencies = data.frequencies || [];
        this.magnitudes = data.magnitudes || [];
        this.sampleRate = data.sample_rate || 44100;
        this.fftSize = data.fft_size || 2048;
        this.draw();
    }

    /** Load synthetic spectrum for demo */
    loadSynthetic() {
        this.sampleRate = 44100;
        this.fftSize = 4096;
        const numBins = this.fftSize / 2;
        this.frequencies = [];
        this.magnitudes = [];

        for (let i = 0; i < numBins; i++) {
            const freq = (i / numBins) * (this.sampleRate / 2);
            this.frequencies.push(freq);
            // Simulated spectrum: pink noise + peaks at 200Hz, 1kHz, 4kHz
            let mag = 1.0 / (1 + freq / 500);
            mag += 0.5 * Math.exp(-Math.pow((freq - 200) / 50, 2));
            mag += 0.4 * Math.exp(-Math.pow((freq - 1000) / 100, 2));
            mag += 0.3 * Math.exp(-Math.pow((freq - 4000) / 300, 2));
            mag *= (0.8 + 0.2 * Math.random());
            this.magnitudes.push(mag);
        }

        // Set demo levels
        this.rmsDb = -12;
        this.peakDb = -3;
        this.lufs = -14;

        this.draw();
    }

    /** Set level meter values */
    setLevels(rmsDb, peakDb, lufs) {
        this.rmsDb = rmsDb;
        this.peakDb = peakDb;
        this.lufs = lufs;
    }

    /** Draw spectrum bars (1/3 octave) */
    draw() {
        this._drawSpectrum();
        this._updateMeters();
        this._drawSpectrogram();
    }

    /** Draw 1/3 octave spectrum bars */
    _drawSpectrum() {
        if (!this.ctx || !this.canvas) return;
        const ctx = this.ctx;
        const w = this.canvas.width;
        const h = this.canvas.height;
        const padding = { top: 20, bottom: 40, left: 50, right: 10 };
        const drawW = w - padding.left - padding.right;
        const drawH = h - padding.top - padding.bottom;

        // Clear
        ctx.fillStyle = '#0d1117';
        ctx.fillRect(0, 0, w, h);

        // Compute 1/3 octave band magnitudes
        const bandMags = this._computeThirdOctaveBands();

        if (bandMags.length === 0) {
            ctx.fillStyle = '#a0a0b0';
            ctx.font = '14px monospace';
            ctx.textAlign = 'center';
            ctx.fillText('No spectrum data — analyze a track', w / 2, h / 2);
            return;
        }

        // dB scale: -80 to 0
        const dbMin = -80;
        const dbMax = 0;
        const dbRange = dbMax - dbMin;

        // Grid lines
        ctx.strokeStyle = '#1a2332';
        ctx.lineWidth = 1;
        for (let db = dbMin; db <= dbMax; db += 10) {
            const y = padding.top + ((dbMax - db) / dbRange) * drawH;
            ctx.beginPath();
            ctx.moveTo(padding.left, y);
            ctx.lineTo(padding.left + drawW, y);
            ctx.stroke();

            ctx.fillStyle = '#a0a0b0';
            ctx.font = '10px monospace';
            ctx.textAlign = 'right';
            ctx.fillText(`${db}`, padding.left - 4, y + 3);
        }

        // Draw bars
        const barW = Math.max(2, drawW / bandMags.length - 1);
        for (let i = 0; i < bandMags.length; i++) {
            const mag = bandMags[i];
            const dbVal = 20 * Math.log10(Math.max(1e-10, mag));
            const clampedDb = Math.max(dbMin, Math.min(dbMax, dbVal));
            const barH = ((clampedDb - dbMin) / dbRange) * drawH;
            const x = padding.left + (i / bandMags.length) * drawW;

            // Color gradient: green → yellow → red
            const ratio = (clampedDb - dbMin) / dbRange;
            let color;
            if (ratio < 0.6) {
                color = '#66bb6a';
            } else if (ratio < 0.85) {
                color = '#ffa726';
            } else {
                color = '#ef5350';
            }

            ctx.fillStyle = color;
            ctx.fillRect(x, padding.top + drawH - barH, barW, barH);

            // Frequency label (only for some bands)
            if (i % 3 === 0) {
                const freq = this.thirdOctaveBands[i];
                if (freq) {
                    ctx.fillStyle = '#a0a0b0';
                    ctx.font = '9px monospace';
                    ctx.textAlign = 'center';
                    const label = freq >= 1000 ? `${(freq / 1000).toFixed(1)}k` : `${Math.round(freq)}`;
                    ctx.fillText(label, x + barW / 2, h - padding.bottom + 14);
                }
            }
        }

        // Axis label
        ctx.fillStyle = '#a0a0b0';
        ctx.font = '11px monospace';
        ctx.textAlign = 'center';
        ctx.fillText('Frequency (Hz)', w / 2, h - 4);
    }

    /** Compute 1/3 octave band magnitudes from raw spectrum */
    _computeThirdOctaveBands() {
        if (this.frequencies.length === 0 || this.magnitudes.length === 0) {
            return [];
        }

        const bandMags = [];
        for (const centerFreq of this.thirdOctaveBands) {
            const bandMin = centerFreq / Math.pow(2, 1 / 6);
            const bandMax = centerFreq * Math.pow(2, 1 / 6);
            let sum = 0;
            let count = 0;

            for (let i = 0; i < this.frequencies.length; i++) {
                if (this.frequencies[i] >= bandMin && this.frequencies[i] < bandMax) {
                    sum += this.magnitudes[i] * this.magnitudes[i];
                    count++;
                }
            }

            if (count > 0) {
                bandMags.push(Math.sqrt(sum / count));
            } else {
                bandMags.push(0);
            }
        }
        return bandMags;
    }

    /** Update level meter DOM elements */
    _updateMeters() {
        const dbToPercent = (db) => Math.max(0, Math.min(100, ((db + 60) / 60) * 100));

        const rmsFill = document.getElementById('meter-rms-fill');
        const peakFill = document.getElementById('meter-peak-fill');
        const lufsFill = document.getElementById('meter-lufs-fill');
        const rmsVal = document.getElementById('meter-rms-val');
        const peakVal = document.getElementById('meter-peak-val');
        const lufsVal = document.getElementById('meter-lufs-val');

        if (rmsFill) {
            rmsFill.style.width = dbToPercent(this.rmsDb) + '%';
            rmsFill.className = 'level-meter-bar-fill ' + (this.rmsDb > -1 ? 'clip' : this.rmsDb > -6 ? 'warn' : 'ok');
        }
        if (peakFill) {
            peakFill.style.width = dbToPercent(this.peakDb) + '%';
            peakFill.className = 'level-meter-bar-fill ' + (this.peakDb > -1 ? 'clip' : this.peakDb > -6 ? 'warn' : 'ok');
        }
        if (lufsFill) {
            lufsFill.style.width = dbToPercent(this.lufs) + '%';
            lufsFill.className = 'level-meter-bar-fill ' + (this.lufs > -1 ? 'clip' : this.lufs > -8 ? 'warn' : 'ok');
        }
        if (rmsVal) rmsVal.textContent = this.rmsDb > -60 ? `${this.rmsDb.toFixed(1)} dB` : '-∞ dB';
        if (peakVal) peakVal.textContent = this.peakDb > -60 ? `${this.peakDb.toFixed(1)} dB` : '-∞ dB';
        if (lufsVal) lufsVal.textContent = this.lufs > -70 ? `${this.lufs.toFixed(1)} LUFS` : '-∞ LUFS';
    }

    /** Draw spectrogram waterfall */
    _drawSpectrogram() {
        if (!this.spectrogramCtx || !this.spectrogramCanvas) return;
        const ctx = this.spectrogramCtx;
        const w = this.spectrogramCanvas.width;
        const h = this.spectrogramCanvas.height;

        // Add current spectrum to history
        if (this.frequencies.length > 0) {
            const bandMags = this._computeThirdOctaveBands();
            this.spectrogramHistory.push(bandMags.map(m => 20 * Math.log10(Math.max(1e-10, m))));
            if (this.spectrogramHistory.length > this.maxSpectrogramLines) {
                this.spectrogramHistory.shift();
            }
        }

        // Clear
        ctx.fillStyle = '#0d1117';
        ctx.fillRect(0, 0, w, h);

        if (this.spectrogramHistory.length === 0) {
            ctx.fillStyle = '#a0a0b0';
            ctx.font = '12px monospace';
            ctx.textAlign = 'center';
            ctx.fillText('Spectrogram — waiting for data', w / 2, h / 2);
            return;
        }

        const dbMin = -80;
        const dbMax = 0;
        const dbRange = dbMax - dbMin;
        const numBands = this.thirdOctaveBands.length;

        // Draw each time slice as a row of colored pixels
        const lineH = Math.max(1, h / this.maxSpectrogramLines);
        const startLine = Math.max(0, this.spectrogramHistory.length - Math.floor(h / lineH));

        for (let t = startLine; t < this.spectrogramHistory.length; t++) {
            const slice = this.spectrogramHistory[t];
            const y = h - (t - startLine + 1) * lineH;

            for (let b = 0; b < Math.min(slice.length, numBands); b++) {
                const dbVal = Math.max(dbMin, Math.min(dbMax, slice[b]));
                const ratio = (dbVal - dbMin) / dbRange;
                const x = (b / numBands) * w;
                const bw = Math.max(1, w / numBands);

                // Color map: dark blue → cyan → green → yellow → red
                const color = this._heatColor(ratio);
                ctx.fillStyle = color;
                ctx.fillRect(x, y, bw, lineH);
            }
        }

        // Frequency axis labels
        ctx.fillStyle = '#a0a0b0';
        ctx.font = '9px monospace';
        ctx.textAlign = 'center';
        for (let i = 0; i < numBands; i += 6) {
            const freq = this.thirdOctaveBands[i];
            if (freq) {
                const x = (i / numBands) * w;
                const label = freq >= 1000 ? `${(freq / 1000).toFixed(1)}k` : `${Math.round(freq)}`;
                ctx.fillText(label, x, h - 2);
            }
        }
    }

    /** Heat color map (0=dark, 1=bright) */
    _heatColor(ratio) {
        const r = Math.min(255, Math.floor(ratio < 0.5 ? ratio * 2 * 255 : 255));
        const g = Math.min(255, Math.floor(ratio < 0.5 ? ratio * 2 * 100 : (1 - (ratio - 0.5) * 2) * 255));
        const b = Math.min(255, Math.floor(ratio < 0.3 ? ratio * 3 * 200 : (1 - ratio) * 100));
        return `rgb(${r},${g},${b})`;
    }

    /** Clear spectrogram history */
    clearSpectrogram() {
        this.spectrogramHistory = [];
        this._drawSpectrogram();
    }
}

// Export for use in app.js
window.SpectrumView = SpectrumView;
