/**
 * OpenDAW — Main App Entry
 * Initializes all components, manages global state
 */
const App = (() => {
    // ── Public API for components ──
    function setStatus(msg) {
        const el = document.getElementById('status-msg');
        if (el) el.textContent = msg;
    }

    function toast(msg, type = 'info') {
        const container = document.getElementById('toast-container');
        if (!container) return;
        const el = document.createElement('div');
        el.className = 'toast ' + type;
        el.textContent = msg;
        container.appendChild(el);
        setTimeout(() => el.remove(), 3500);
    }

    // ── Backend health ──
    async function checkBackendHealth() {
        try {
            const result = await TauriBridge.checkHealth();
            const dot = document.querySelector('#backend-status .dot');
            const txt = document.querySelector('#backend-status .status-text');
            if (dot && txt) {
                dot.className = 'dot ' + (result?.healthy ? 'online' : 'offline');
                txt.textContent = result?.message || 'Unknown';
            }
            return result?.healthy;
        } catch {
            return false;
        }
    }

    // ── Keyboard shortcuts ──
    function setupKeyboardShortcuts() {
        document.addEventListener('keydown', e => {
            const tag = document.activeElement?.tagName?.toLowerCase();
            if (tag === 'input' || tag === 'textarea' || tag === 'select') {
                if (e.key === 'Escape') document.activeElement.blur();
                return;
            }

            const ctrl = e.ctrlKey || e.metaKey;

            if (e.key === ' ') { e.preventDefault(); Transport.togglePlay(); return; }
            if (e.key === 'Home') { e.preventDefault(); Transport.rewind(); return; }
            if (e.key === 'r' && !ctrl) { e.preventDefault(); Transport.toggleRecord(); return; }
            if (ctrl && e.key === 'e') { e.preventDefault(); exportProject(); return; }
            if (ctrl && e.key === 'm') { e.preventDefault(); toggleMixer(); return; }
            if (ctrl && e.key === 'n') { e.preventDefault(); TrackList.addTrack('Track ' + (TrackList.getTracks().length + 1)); return; }
            if (ctrl && e.key === 'p') { e.preventDefault(); PianoKeyboard.toggle(); return; }
        });
    }

    function toggleMixer() {
        const panel = document.getElementById('mixer-panel');
        if (panel) {
            panel.classList.toggle('collapsed');
        }
    }

    async function exportProject() {
        toast('Export started', 'info');
        setStatus('Exporting…');
    }

    // ── Meter animation loop ──
    let meterRafId = null;
    function meterLoop() {
        if (Transport.isPlaying()) {
            Mixer.updateMeters();
        }
        meterRafId = requestAnimationFrame(meterLoop);
    }

    // ── Volume slider ──
    function setupVolumeSlider() {
        const slider = document.getElementById('volume-slider');
        const display = document.getElementById('volume-display');
        if (slider && display) {
            slider.addEventListener('input', (e) => {
                const vol = parseFloat(e.target.value);
                display.textContent = vol + ' dB';
                TauriBridge.setMasterVolume(vol).catch(() => {});
            });
        }
    }

    // ── Load WAV button ──
    function setupLoadWav() {
        const btn = document.getElementById('btn-load-wav');
        if (!btn) return;

        btn.addEventListener('click', async () => {
            if (TauriBridge.isTauri) {
                try {
                    const { open } = window.__TAURI_DIALOG__ || {};
                    if (open) {
                        const filePath = await open({
                            multiple: false,
                            filters: [{ name: 'Audio', extensions: ['wav', 'mp3', 'ogg', 'flac'] }]
                        });
                        if (filePath) {
                            await TauriBridge.loadAndPlay(filePath);
                            toast('Audio loaded: ' + filePath.split('/').pop(), 'success');
                        }
                    }
                } catch {
                    const path = prompt('Enter audio file path:');
                    if (path) await TauriBridge.loadAndPlay(path);
                }
            } else {
                const path = prompt('Enter audio file path:');
                if (path) {
                    await TauriBridge.loadAndPlay(path);
                    toast('Audio loaded', 'success');
                }
            }
        });
    }

    // ── Import Project (Reaper/Ableton) ──
    function setupImportProject() {
        const btn = document.getElementById('btn-import-project');
        if (!btn) return;
        btn.addEventListener('click', async () => {
            if (TauriBridge.isTauri) {
                try {
                    const { open } = window.__TAURI_DIALOG__ || {};
                    if (open) {
                        const filePath = await open({
                            multiple: false,
                            filters: [
                                { name: 'DAW Projects', extensions: ['rpp', 'als', 'yaml', 'yml', 'json'] },
                                { name: 'Reaper Project', extensions: ['rpp'] },
                                { name: 'Ableton Project', extensions: ['als'] },
                                { name: 'OpenDAW Project', extensions: ['yaml', 'yml', 'json'] },
                            ]
                        });
                        if (filePath) {
                            const result = await TauriBridge.invoke('import_project', { filePath });
                            if (result?.success) {
                                toast(`Imported ${result.format}: ${result.project_name} (${result.track_count} tracks)`, 'success');
                            } else {
                                toast('Import failed: ' + (result?.message || 'Unknown error'), 'error');
                            }
                        }
                    }
                } catch (e) {
                    toast('Import error: ' + e, 'error');
                }
            }
        });
    }

    // ── Note System (Markdown Notes) ──
    const NoteSystem = (() => {
        let notes = [];
        let currentNote = null;
        let isEditing = false;

        async function loadNotes() {
            try {
                notes = await TauriBridge.invoke('notes_list') || [];
                renderNotesList();
            } catch { notes = []; renderNotesList(); }
        }

        function renderNotesList() {
            const list = document.getElementById('notes-list');
            if (!list) return;
            list.innerHTML = '';

            // Group by level
            const groups = { Global: [], Project: [], Track: [] };
            notes.forEach(n => { if (groups[n.level]) groups[n.level].push(n); });

            const icons = { Global: '🌐', Project: '📁', Track: '🎵' };
            Object.entries(groups).forEach(([level, items]) => {
                if (items.length === 0) return;
                const header = document.createElement('div');
                header.className = 'notes-group-header';
                header.textContent = `${icons[level]} ${level} Notes`;
                list.appendChild(header);

                items.forEach(n => {
                    const item = document.createElement('div');
                    item.className = 'note-item' + (currentNote?.id === n.id ? ' active' : '');
                    item.innerHTML = `<span class="note-title">${escHtml(n.title)}</span><span class="note-preview">${escHtml(n.preview)}</span>`;
                    item.addEventListener('click', () => selectNote(n));
                    list.appendChild(item);
                });
            });
        }

        async function selectNote(note) {
            currentNote = note;
            try {
                const content = await TauriBridge.invoke('notes_get', { id: note.id });
                renderEditor(content);
            } catch { renderEditor(''); }
            renderNotesList();
        }

        function renderEditor(content) {
            const editor = document.getElementById('note-editor');
            const view = document.getElementById('note-view');
            if (!editor || !view) return;

            isEditing = false;
            editor.value = content;
            editor.style.display = 'none';
            view.innerHTML = renderMarkdown(content);
            view.style.display = 'block';

            // Update title display
            const titleEl = document.getElementById('note-editor-title');
            if (titleEl && currentNote) {
                titleEl.textContent = currentNote.title + (currentNote.track_id ? ` [${currentNote.track_id}]` : '');
            }
        }

        function toggleEdit() {
            const editor = document.getElementById('note-editor');
            const view = document.getElementById('note-view');
            if (!editor || !view) return;

            isEditing = !isEditing;
            if (isEditing) {
                view.style.display = 'none';
                editor.style.display = 'block';
                editor.focus();
            } else {
                // Save and re-render
                const newContent = editor.value;
                saveCurrentNote(newContent);
                view.innerHTML = renderMarkdown(newContent);
                view.style.display = 'block';
                editor.style.display = 'none';
            }
        }

        async function saveCurrentNote(content) {
            if (!currentNote) return;
            try {
                await TauriBridge.invoke('notes_save', {
                    id: currentNote.id,
                    level: currentNote.level,
                    title: currentNote.title,
                    content: content,
                    trackId: currentNote.track_id
                });
                toast('Note saved', 'success');
            } catch (e) {
                toast('Save failed: ' + e, 'error');
            }
        }

        async function createNote(level) {
            const title = prompt('Note title:');
            if (!title) return;
            try {
                const result = await TauriBridge.invoke('notes_save', {
                    id: null, level: level, title: title, content: '', trackId: null
                });
                toast('Note created: ' + title, 'success');
                await loadNotes();
                if (result) selectNote(result);
            } catch (e) {
                toast('Create failed: ' + e, 'error');
            }
        }

        async function deleteCurrentNote() {
            if (!currentNote) return;
            if (!confirm('Delete this note?')) return;
            try {
                await TauriBridge.invoke('notes_delete', { id: currentNote.id });
                currentNote = null;
                toast('Note deleted', 'info');
                await loadNotes();
                const view = document.getElementById('note-view');
                const editor = document.getElementById('note-editor');
                if (view) view.innerHTML = '<p class="notes-empty">Select or create a note</p>';
                if (editor) editor.value = '';
            } catch (e) {
                toast('Delete failed: ' + e, 'error');
            }
        }

        async function searchNotes(query) {
            if (!query.trim()) { loadNotes(); return; }
            try {
                notes = await TauriBridge.invoke('notes_search', { query }) || [];
                renderNotesList();
            } catch { /* ignore */ }
        }

        // Simple Markdown renderer (no dependency, Typora-like preview)
        function renderMarkdown(md) {
            if (!md) return '<p class="notes-empty">Select or create a note</p>';
            let html = escHtml(md);
            // Headers
            html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
            html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
            html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
            // Bold & Italic
            html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
            html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
            // Code blocks
            html = html.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
            html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
            // Lists
            html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
            html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');
            // Links
            html = html.replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2">$1</a>');
            // Paragraphs
            html = html.replace(/\n\n/g, '</p><p>');
            html = '<p>' + html + '</p>';
            html = html.replace(/<p><(h[1-3]|pre|ul)/g, '<$1');
            html = html.replace(/<\/\1><\/p>/g, '</$1>');
            return html;
        }

        function escHtml(s) {
            const d = document.createElement('div');
            d.textContent = s;
            return d.innerHTML;
        }

        function init() {
            const panel = document.getElementById('notes-panel');
            if (!panel) return;
            loadNotes();

            // Toolbar buttons
            const btnNewGlobal = document.getElementById('btn-note-new-global');
            const btnNewProject = document.getElementById('btn-note-new-project');
            const btnDelete = document.getElementById('btn-note-delete');
            const btnEdit = document.getElementById('btn-note-edit');
            const searchInput = document.getElementById('notes-search');

            if (btnNewGlobal) btnNewGlobal.addEventListener('click', () => createNote('Global'));
            if (btnNewProject) btnNewProject.addEventListener('click', () => createNote('Project'));
            if (btnDelete) btnDelete.addEventListener('click', deleteCurrentNote);
            if (btnEdit) btnEdit.addEventListener('click', toggleEdit);
            if (searchInput) {
                let debounce;
                searchInput.addEventListener('input', (e) => {
                    clearTimeout(debounce);
                    debounce = setTimeout(() => searchNotes(e.target.value), 300);
                });
            }

            // Editor auto-save on blur
            const editor = document.getElementById('note-editor');
            if (editor) {
                editor.addEventListener('blur', () => {
                    if (isEditing) toggleEdit(); // auto-save on blur
                });
            }
        }

        return { init, loadNotes };
    })();

    // ── Export button ──
    function setupExport() {
        const btn = document.getElementById('btn-export');
        if (btn) btn.addEventListener('click', exportProject);
    }

    // ── New project ──
    function setupNewProject() {
        const btn = document.getElementById('btn-new-project');
        if (btn) {
            btn.addEventListener('click', () => {
                const name = prompt('Project name:', 'New Project');
                if (name) {
                    TauriBridge.createProject(name).then(() => {
                        toast('Project created: ' + name, 'success');
                    }).catch(() => {
                        toast('Failed to create project', 'error');
                    });
                }
            });
        }
    }

    // ── Add demo tracks for visual demo ──
    function addDemoTracks() {
        const tracks = TrackList.getTracks();
        if (tracks.length > 0) return; // Don't add if tracks exist

        const demoTracks = [
            { name: 'Drums', type: 'audio' },
            { name: 'Bass', type: 'audio' },
            { name: 'Keys', type: 'midi' },
            { name: 'Vocals', type: 'audio' },
            { name: 'Synth Lead', type: 'midi' },
            { name: 'Guitar', type: 'audio' },
        ];

        demoTracks.forEach(t => TrackList.addTrack(t.name, t.type));
    }

    // ── Main init ──
    async function init() {
        // Init layout manager first
        LayoutManager.init();
        LayoutManager.onChange((newLayout) => {
            Arrangement.resize();
            TimelineRenderer.resize();
        });

        // Init all components
        TimelineRenderer.init();
        Transport.init();
        TrackList.init();
        Arrangement.init();
        Mixer.init();
        Inspector.init();
        PianoKeyboard.init();
        TouchHandler.init();

        // Setup UI
        setupKeyboardShortcuts();
        setupVolumeSlider();
        setupLoadWav();
        setupExport();
        setupNewProject();
        setupImportProject();

        // Init Note System
        NoteSystem.init();

        // Add demo tracks for visual demo
        addDemoTracks();

        // Start meter loop
        meterLoop();

        // Check backend health
        checkBackendHealth();
        setInterval(checkBackendHealth, 15000);

        setStatus('Ready — Space to play/stop');
    }

    // ── Boot ──
    document.addEventListener('DOMContentLoaded', init);

    return { setStatus, toast, checkBackendHealth };
})();
