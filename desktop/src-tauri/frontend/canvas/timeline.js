/**
 * OpenDAW — Timeline/Rule Renderer
 * Canvas-based time ruler with bar/beat markers
 */
const TimelineRenderer = (() => {
    let canvas, ctx;
    let scrollX = 0;
    let zoom = 1; // pixels per second base
    const BASE_PPS = 80; // base pixels per second at zoom=1
    let bpm = 120;
    let timeSig = '4/4';

    function init() {
        canvas = document.getElementById('ruler-canvas');
        if (!canvas) return;
        ctx = canvas.getContext('2d');
        resize();
        window.addEventListener('resize', resize);
    }

    function resize() {
        if (!canvas) return;
        const rect = canvas.parentElement.getBoundingClientRect();
        canvas.width = rect.width * window.devicePixelRatio;
        canvas.height = rect.height * window.devicePixelRatio;
        canvas.style.width = rect.width + 'px';
        canvas.style.height = rect.height + 'px';
        ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
        render();
    }

    function setScroll(x) { scrollX = x; render(); }
    function setZoom(z) { zoom = z; render(); }
    function setBPM(b) { bpm = b; render(); }
    function setTimeSig(ts) { timeSig = ts; render(); }

    function getPPS() { return BASE_PPS * zoom; }

    function secondsToX(seconds) {
        return seconds * getPPS() - scrollX;
    }

    function xToSeconds(x) {
        return (x + scrollX) / getPPS();
    }

    function render() {
        if (!ctx || !canvas) return;
        const w = canvas.width / window.devicePixelRatio;
        const h = canvas.height / window.devicePixelRatio;

        // Clear
        ctx.clearRect(0, 0, w, h);

        const pps = getPPS();
        const beatsPerBar = parseInt(timeSig.split('/')[0]) || 4;
        const bps = bpm / 60;
        const secondsPerBar = beatsPerBar / bps;

        // Determine bar spacing and label density
        let barWidth = secondsPerBar * pps;
        let labelEvery = 1;
        if (barWidth < 30) labelEvery = 4;
        if (barWidth < 15) labelEvery = 8;

        // Find first visible bar
        const startSec = xToSeconds(0);
        const endSec = xToSeconds(w);
        const startBar = Math.floor(startSec / secondsPerBar);
        const endBar = Math.ceil(endSec / secondsPerBar) + 1;

        // Draw bar lines and labels
        ctx.textAlign = 'center';
        ctx.textBaseline = 'bottom';

        for (let bar = Math.max(1, startBar); bar <= endBar; bar++) {
            const x = secondsToX((bar - 1) * secondsPerBar);
            if (x < -10 || x > w + 10) continue;

            // Bar line
            ctx.strokeStyle = 'rgba(160,160,184,0.2)';
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(x, 0);
            ctx.lineTo(x, h);
            ctx.stroke();

            // Beat subdivisions
            for (let beat = 1; beat < beatsPerBar; beat++) {
                const bx = secondsToX((bar - 1) * secondsPerBar + beat / bps);
                ctx.strokeStyle = 'rgba(160,160,184,0.08)';
                ctx.beginPath();
                ctx.moveTo(bx, h * 0.6);
                ctx.lineTo(bx, h);
                ctx.stroke();
            }

            // Label
            if (bar % labelEvery === 0) {
                ctx.fillStyle = 'rgba(160,160,184,0.6)';
                ctx.font = '600 10px -apple-system, system-ui, sans-serif';
                ctx.fillText(bar, x + barWidth / 2, h - 4);
            }
        }

        // Bottom edge
        ctx.strokeStyle = 'rgba(160,160,184,0.15)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(0, h - 0.5);
        ctx.lineTo(w, h - 0.5);
        ctx.stroke();
    }

    return { init, resize, setScroll, setZoom, setBPM, setTimeSig, getPPS, secondsToX, xToSeconds, render };
})();
