/**
 * OpenDAW — MIDI Block Renderer
 * Canvas-based MIDI note rendering within clip blocks
 */
const MidiBlockRenderer = (() => {
    // Draw MIDI notes within a clip area
    function draw(ctx, x, y, w, h, notes = [], color = 'rgba(163,139,250,0.8)') {
        if (!notes || notes.length === 0) {
            // Draw placeholder pattern
            ctx.fillStyle = 'rgba(163,139,250,0.12)';
            ctx.fillRect(x, y, w, h);
            // Grid dots
            ctx.fillStyle = 'rgba(163,139,250,0.3)';
            const step = 12;
            for (let gx = 0; gx < w; gx += step) {
                for (let gy = 0; gy < h; gy += step) {
                    ctx.fillRect(x + gx, y + gy, 2, 2);
                }
            }
            return;
        }

        // Background
        ctx.fillStyle = 'rgba(163,139,250,0.12)';
        ctx.fillRect(x, y, w, h);

        // Notes
        const noteH = Math.max(3, h / 24); // 2 octaves visible
        notes.forEach(note => {
            const nx = x + (note.start || 0) * w;
            const nw = Math.max(2, (note.duration || 0.1) * w);
            const ny = y + h - (note.pitch || 60) * noteH;
            ctx.fillStyle = color;
            ctx.fillRect(nx, ny, nw, Math.max(2, noteH - 1));
        });
    }

    // Draw a simple MIDI clip indicator
    function drawIndicator(ctx, x, y, w, h, color = 'rgba(163,139,250,0.6)') {
        ctx.fillStyle = color;
        const noteH = 3;
        const step = w / 16;
        for (let i = 0; i < 16; i++) {
            const pitchOffset = Math.sin(i * 0.8) * 0.3 + 0.5;
            const ny = y + h * (1 - pitchOffset) - noteH;
            ctx.fillRect(x + i * step, ny, Math.max(2, step - 1), noteH);
        }
    }

    return { draw, drawIndicator };
})();
