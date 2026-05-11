/**
 * OpenDAW — Waveform Renderer
 * Canvas-based waveform drawing with zoom/scroll
 */
const WaveformRenderer = (() => {
    // Draw a waveform block on a canvas context
    function draw(ctx, x, y, w, h, peaks, color = 'rgba(74,158,255,0.7)', bgColor = 'rgba(74,158,255,0.15)') {
        if (!peaks || peaks.length === 0) {
            // Draw placeholder
            ctx.fillStyle = bgColor;
            ctx.fillRect(x, y, w, h);
            return;
        }

        const mid = y + h / 2;
        const halfH = h / 2;

        // Background
        ctx.fillStyle = bgColor;
        ctx.fillRect(x, y, w, h);

        // Waveform
        ctx.fillStyle = color;
        const step = Math.max(1, Math.floor(peaks.length / w));

        for (let i = 0; i < w; i++) {
            const idx = Math.floor(i * peaks.length / w);
            const peak = Math.min(Math.abs(peaks[idx] || 0), 1);
            const barH = peak * halfH;
            ctx.fillRect(x + i, mid - barH, 1, barH * 2);
        }
    }

    // Draw a simplified waveform for clip preview
    function drawSimple(ctx, x, y, w, h, color = 'rgba(74,158,255,0.5)') {
        ctx.fillStyle = color;
        const mid = y + h / 2;
        const step = w / 64;
        for (let i = 0; i < 64; i++) {
            const px = x + i * step;
            // Pseudo-random waveform shape
            const amp = 0.3 + 0.5 * Math.sin(i * 0.3) * Math.cos(i * 0.17);
            const barH = amp * h * 0.4;
            ctx.fillRect(px, mid - barH, Math.max(1, step - 1), barH * 2);
        }
    }

    return { draw, drawSimple };
})();
