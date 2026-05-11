/**
 * OpenDAW — Arrangement View (Canvas)
 * Central area: time grid + track lanes + clip blocks + playhead
 */
const Arrangement = (() => {
    let canvas, ctx;
    let scrollX = 0;
    let scrollY = 0;
    let zoom = 1;
    const TRACK_HEIGHT = 64;
    const CLIP_PADDING = 2;
    let dpr = 1;
    let animId = null;

    function init() {
        canvas = document.getElementById('arrangement-canvas');
        if (!canvas) return;
        ctx = canvas.getContext('2d');
        dpr = window.devicePixelRatio || 1;

        resize();
        window.addEventListener('resize', resize);

        // Pointer events for scrolling & zooming (handled by TouchHandler)
        // We just need to sync scroll state
    }

    function resize() {
        if (!canvas) return;
        const parent = canvas.parentElement;
        const rect = parent.getBoundingClientRect();
        canvas.width = rect.width * dpr;
        canvas.height = rect.height * dpr;
        canvas.style.width = rect.width + 'px';
        canvas.style.height = rect.height + 'px';
        render();
    }

    function setScroll(x, y) {
        scrollX = x;
        scrollY = y;
        TimelineRenderer.setScroll(x);
        render();
    }

    function setZoom(z) {
        zoom = Math.max(0.1, Math.min(10, z));
        TimelineRenderer.setZoom(zoom);
        render();
    }

    function getZoom() { return zoom; }
    function getScrollX() { return scrollX; }
    function getScrollY() { return scrollY; }

    function render() {
        if (!ctx || !canvas) return;

        const w = canvas.width / dpr;
        const h = canvas.height / dpr;

        ctx.save();
        ctx.scale(dpr, dpr);

        // Clear
        ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--bg-base').trim() || '#121218';
        ctx.fillRect(0, 0, w, h);

        const tracks = TrackList.getTracks();
        const pps = TimelineRenderer.getPPS();

        // Draw track lanes
        tracks.forEach((track, idx) => {
            const y = idx * TRACK_HEIGHT - scrollY;

            // Skip if off screen
            if (y + TRACK_HEIGHT < 0 || y > h) return;

            // Lane background (alternate)
            ctx.fillStyle = idx % 2 === 0
                ? 'rgba(26,26,36,0.6)'
                : 'rgba(34,34,46,0.6)';
            ctx.fillRect(0, y, w, TRACK_HEIGHT);

            // Selected highlight
            if (track.selected) {
                ctx.fillStyle = 'rgba(74,158,255,0.06)';
                ctx.fillRect(0, y, w, TRACK_HEIGHT);
            }

            // Lane separator
            ctx.strokeStyle = 'rgba(96,96,120,0.1)';
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(0, y + TRACK_HEIGHT - 0.5);
            ctx.lineTo(w, y + TRACK_HEIGHT - 0.5);
            ctx.stroke();

            // Draw clips for this track
            if (track.clips && track.clips.length > 0) {
                track.clips.forEach(clip => {
                    drawClip(ctx, clip, y, pps, track);
                });
            } else if (track.type === 'audio') {
                // Demo: draw a placeholder clip
                drawPlaceholderClip(ctx, track, y, pps);
            } else if (track.type === 'midi') {
                drawPlaceholderMidiClip(ctx, track, y, pps);
            }
        });

        // Draw grid lines (vertical bar lines)
        const bpm = Transport.getBPM();
        const timeSig = Transport.getTimeSig();
        const beatsPerBar = parseInt(timeSig.split('/')[0]) || 4;
        const bps = bpm / 60;
        const secondsPerBar = beatsPerBar / bps;

        const startSec = TimelineRenderer.xToSeconds(0);
        const endSec = TimelineRenderer.xToSeconds(w);
        const startBar = Math.floor(startSec / secondsPerBar);
        const endBar = Math.ceil(endSec / secondsPerBar) + 1;

        for (let bar = Math.max(0, startBar); bar <= endBar; bar++) {
            const x = TimelineRenderer.secondsToX(bar * secondsPerBar);
            if (x < -1 || x > w + 1) continue;

            ctx.strokeStyle = 'rgba(96,96,120,0.08)';
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(x, 0);
            ctx.lineTo(x, h);
            ctx.stroke();
        }

        // Empty state
        if (tracks.length === 0) {
            ctx.fillStyle = 'rgba(96,96,120,0.3)';
            ctx.font = '600 16px -apple-system, system-ui, sans-serif';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText('Add tracks to start composing', w / 2, h / 2);
        }

        ctx.restore();
    }

    function drawClip(ctx, clip, trackY, pps, track) {
        const x = TimelineRenderer.secondsToX(clip.start || 0);
        const w = Math.max(4, (clip.duration || 2) * pps);
        const y = trackY + CLIP_PADDING;
        const h = TRACK_HEIGHT - CLIP_PADDING * 2;

        // Clip body
        ctx.fillStyle = track.color + '33'; // with alpha
        roundRect(ctx, x, y, w, h, 6);
        ctx.fill();

        // Clip border (left side accent)
        ctx.fillStyle = track.color;
        ctx.fillRect(x, y, 3, h);

        // Clip name
        ctx.fillStyle = track.color;
        ctx.font = '600 11px -apple-system, system-ui, sans-serif';
        ctx.textBaseline = 'top';
        ctx.fillText(clip.name || track.name, x + 8, y + 4);

        // Waveform indicator
        if (clip.peaks) {
            WaveformRenderer.draw(ctx, x + 4, y + 20, w - 8, h - 24, clip.peaks, track.color + 'aa', 'transparent');
        }
    }

    function drawPlaceholderClip(ctx, track, trackY, pps) {
        const x = TimelineRenderer.secondsToX(0);
        const w = Math.max(60, 4 * pps);
        const y = trackY + CLIP_PADDING;
        const h = TRACK_HEIGHT - CLIP_PADDING * 2;

        ctx.fillStyle = track.color + '22';
        roundRect(ctx, x, y, w, h, 6);
        ctx.fill();

        ctx.fillStyle = track.color;
        ctx.fillRect(x, y, 3, h);

        ctx.fillStyle = track.color + 'cc';
        ctx.font = '600 11px -apple-system, system-ui, sans-serif';
        ctx.textBaseline = 'top';
        ctx.fillText(track.name, x + 8, y + 4);

        WaveformRenderer.drawSimple(ctx, x + 4, y + 20, w - 8, h - 24, track.color + '66');
    }

    function drawPlaceholderMidiClip(ctx, track, trackY, pps) {
        const x = TimelineRenderer.secondsToX(0);
        const w = Math.max(60, 4 * pps);
        const y = trackY + CLIP_PADDING;
        const h = TRACK_HEIGHT - CLIP_PADDING * 2;

        ctx.fillStyle = track.color + '22';
        roundRect(ctx, x, y, w, h, 6);
        ctx.fill();

        ctx.fillStyle = track.color;
        ctx.fillRect(x, y, 3, h);

        ctx.fillStyle = track.color + 'cc';
        ctx.font = '600 11px -apple-system, system-ui, sans-serif';
        ctx.textBaseline = 'top';
        ctx.fillText(track.name, x + 8, y + 4);

        MidiBlockRenderer.drawIndicator(ctx, x + 4, y + 20, w - 8, h - 24, track.color + '66');
    }

    function roundRect(ctx, x, y, w, h, r) {
        r = Math.min(r, w / 2, h / 2);
        ctx.beginPath();
        ctx.moveTo(x + r, y);
        ctx.lineTo(x + w - r, y);
        ctx.quadraticCurveTo(x + w, y, x + w, y + r);
        ctx.lineTo(x + w, y + h - r);
        ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
        ctx.lineTo(x + r, y + h);
        ctx.quadraticCurveTo(x, y + h, x, y + h - r);
        ctx.lineTo(x, y + r);
        ctx.quadraticCurveTo(x, y, x + r, y);
        ctx.closePath();
    }

    return {
        init, resize, render, setScroll, setZoom,
        getZoom, getScrollX, getScrollY,
        TRACK_HEIGHT
    };
})();
