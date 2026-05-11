/**
 * OpenDAW — Transport Controls
 * Play/Pause/Stop/Record/Rewind + time display + BPM
 */
const Transport = (() => {
    let playing = false;
    let recording = false;
    let looping = false;
    let metronome = false;
    let currentTime = 0;
    let bpm = 120;
    let timeSig = '4/4';
    let startTime = 0;
    let rafId = null;

    // DOM refs
    let btnPlay, btnStop, btnRecord, btnRewind, btnLoop, btnMetronome;
    let iconPlay, iconPause;
    let timeDisplay, bpmInput, timeSigSelect;

    function init() {
        btnPlay = document.getElementById('btn-play');
        btnStop = document.getElementById('btn-stop');
        btnRecord = document.getElementById('btn-record');
        btnRewind = document.getElementById('btn-rewind');
        btnLoop = document.getElementById('btn-loop');
        btnMetronome = document.getElementById('btn-metronome');
        iconPlay = document.getElementById('icon-play');
        iconPause = document.getElementById('icon-pause');
        timeDisplay = document.getElementById('time-display');
        bpmInput = document.getElementById('bpm-input');
        timeSigSelect = document.getElementById('time-sig-select');

        btnPlay.addEventListener('click', togglePlay);
        btnStop.addEventListener('click', stop);
        btnRecord.addEventListener('click', toggleRecord);
        btnRewind.addEventListener('click', rewind);
        btnLoop.addEventListener('click', toggleLoop);
        btnMetronome.addEventListener('click', toggleMetronome);

        bpmInput.addEventListener('change', () => {
            bpm = parseInt(bpmInput.value) || 120;
            TimelineRenderer.setBPM(bpm);
        });
        timeSigSelect.addEventListener('change', () => {
            timeSig = timeSigSelect.value;
            TimelineRenderer.setTimeSig(timeSig);
        });

        updateTimeDisplay();
    }

    function formatTime(seconds) {
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = Math.floor(seconds % 60);
        const ms = Math.floor((seconds % 1) * 1000);
        return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}.${String(ms).padStart(3,'0')}`;
    }

    function updateTimeDisplay() {
        const el = timeDisplay?.querySelector('.time-value') || timeDisplay;
        if (el) el.textContent = formatTime(currentTime);

        // Update playhead
        const playhead = document.getElementById('playhead');
        if (playhead) {
            const x = TimelineRenderer.secondsToX(currentTime);
            playhead.style.left = x + 'px';
        }
    }

    function play() {
        if (playing) return;
        playing = true;
        iconPlay.style.display = 'none';
        iconPause.style.display = 'block';
        btnPlay.classList.add('playing');

        TauriBridge.play().catch(() => {});

        startTime = performance.now() - currentTime * 1000;
        function tick() {
            if (!playing) return;
            currentTime = (performance.now() - startTime) / 1000;
            updateTimeDisplay();
            rafId = requestAnimationFrame(tick);
        }
        rafId = requestAnimationFrame(tick);
        App.setStatus('Playing');
    }

    function pause() {
        if (!playing) return;
        playing = false;
        cancelAnimationFrame(rafId);
        iconPlay.style.display = 'block';
        iconPause.style.display = 'none';
        btnPlay.classList.remove('playing');
        TauriBridge.pause().catch(() => {});
        App.setStatus('Paused');
    }

    function stop() {
        if (!playing) {
            currentTime = 0;
            updateTimeDisplay();
            return;
        }
        playing = false;
        recording = false;
        cancelAnimationFrame(rafId);
        iconPlay.style.display = 'block';
        iconPause.style.display = 'none';
        btnPlay.classList.remove('playing');
        btnRecord.classList.remove('recording');
        TauriBridge.stop().catch(() => {});
        currentTime = 0;
        updateTimeDisplay();
        App.setStatus('Stopped');
    }

    function togglePlay() {
        if (playing) pause(); else play();
    }

    function rewind() {
        currentTime = 0;
        updateTimeDisplay();
        if (playing) {
            startTime = performance.now();
        }
    }

    function toggleRecord() {
        recording = !recording;
        btnRecord.classList.toggle('recording', recording);
        if (recording && !playing) play();
        App.setStatus(recording ? 'Recording…' : 'Ready');
    }

    function toggleLoop() {
        looping = !looping;
        btnLoop.classList.toggle('active', looping);
    }

    function toggleMetronome() {
        metronome = !metronome;
        btnMetronome.classList.toggle('active', metronome);
    }

    function isPlaying() { return playing; }
    function isRecording() { return recording; }
    function getTime() { return currentTime; }
    function getBPM() { return bpm; }
    function getTimeSig() { return timeSig; }

    return {
        init, play, pause, stop, togglePlay, rewind,
        toggleRecord, toggleLoop, toggleMetronome,
        updateTimeDisplay,
        isPlaying, isRecording, getTime, getBPM, getTimeSig,
        setBPM(b) { bpm = b; bpmInput.value = b; },
        setTimeSig(ts) { timeSig = ts; timeSigSelect.value = ts; }
    };
})();
