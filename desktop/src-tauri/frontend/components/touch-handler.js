/**
 * OpenDAW — Touch Handler
 * Unified gesture manager using Pointer Events API
 * Supports: single-finger drag, pinch-zoom, two-finger scroll, long-press
 */
const TouchHandler = (() => {
    let arrangementEl = null;
    let isTouchDevice = false;

    // Gesture state
    let pointers = new Map();
    let initialPinchDist = 0;
    let initialZoom = 1;
    let isDragging = false;
    let dragStartX = 0;
    let dragStartY = 0;
    let scrollStartX = 0;
    let scrollStartY = 0;
    let longPressTimer = null;
    let longPressFired = false;

    const LONG_PRESS_MS = 500;
    const MIN_PINCH_DIST = 10;

    function init() {
        arrangementEl = document.getElementById('arrangement-body');
        if (!arrangementEl) return;

        // Detect touch device
        isTouchDevice = 'ontouchstart' in window || navigator.maxTouchPoints > 0;
        if (isTouchDevice) {
            document.body.classList.add('touch-mode');
        }

        // Use pointer events (unified mouse+touch+pen)
        arrangementEl.addEventListener('pointerdown', onPointerDown, { passive: false });
        arrangementEl.addEventListener('pointermove', onPointerMove, { passive: false });
        arrangementEl.addEventListener('pointerup', onPointerUp, { passive: false });
        arrangementEl.addEventListener('pointercancel', onPointerUp, { passive: false });

        // Wheel zoom (desktop)
        arrangementEl.addEventListener('wheel', onWheel, { passive: false });

        // Prevent default touch behaviors
        arrangementEl.addEventListener('touchstart', e => e.preventDefault(), { passive: false });
        arrangementEl.addEventListener('touchmove', e => e.preventDefault(), { passive: false });
    }

    function onPointerDown(e) {
        e.preventDefault();
        pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });

        if (pointers.size === 1) {
            // Single pointer: potential drag or long-press
            isDragging = true;
            dragStartX = e.clientX;
            dragStartY = e.clientY;
            scrollStartX = Arrangement.getScrollX();
            scrollStartY = Arrangement.getScrollY();
            longPressFired = false;

            longPressTimer = setTimeout(() => {
                if (pointers.size === 1 && !hasMoved(e)) {
                    longPressFired = true;
                    onLongPress(e);
                }
            }, LONG_PRESS_MS);

        } else if (pointers.size === 2) {
            // Two pointers: pinch-zoom or two-finger scroll
            clearTimeout(longPressTimer);
            isDragging = false;

            const pts = [...pointers.values()];
            initialPinchDist = getDistance(pts[0], pts[1]);
            initialZoom = Arrangement.getZoom();
        }

        arrangementEl.setPointerCapture(e.pointerId);
    }

    function onPointerMove(e) {
        if (!pointers.has(e.pointerId)) return;

        pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });

        if (pointers.size === 1 && isDragging && !longPressFired) {
            // Single finger drag = scroll
            const dx = e.clientX - dragStartX;
            const dy = e.clientY - dragStartY;

            if (Math.abs(dx) > 3 || Math.abs(dy) > 3) {
                clearTimeout(longPressTimer);
                const newScrollX = Math.max(0, scrollStartX - dx);
                const newScrollY = Math.max(0, scrollStartY - dy);
                Arrangement.setScroll(newScrollX, newScrollY);
            }

        } else if (pointers.size === 2) {
            const pts = [...pointers.values()];
            const dist = getDistance(pts[0], pts[1]);

            if (initialPinchDist > MIN_PINCH_DIST) {
                // Pinch zoom
                const scale = dist / initialPinchDist;
                const newZoom = Math.max(0.1, Math.min(10, initialZoom * scale));
                Arrangement.setZoom(newZoom);
            }

            // Two-finger pan
            const centerX = (pts[0].x + pts[1].x) / 2;
            const centerY = (pts[0].y + pts[1].y) / 2;
        }
    }

    function onPointerUp(e) {
        pointers.delete(e.pointerId);
        clearTimeout(longPressTimer);
        isDragging = false;

        if (pointers.size === 0) {
            // All fingers up
        } else if (pointers.size === 1) {
            // Went from 2 to 1 — restart single-pointer tracking
            const remaining = [...pointers.values()][0];
            dragStartX = remaining.x;
            dragStartY = remaining.y;
            scrollStartX = Arrangement.getScrollX();
            scrollStartY = Arrangement.getScrollY();
            isDragging = true;
        }
    }

    function onWheel(e) {
        e.preventDefault();
        if (e.ctrlKey || e.metaKey) {
            // Ctrl+Wheel = horizontal zoom
            const delta = e.deltaY > 0 ? 0.9 : 1.1;
            const newZoom = Math.max(0.1, Math.min(10, Arrangement.getZoom() * delta));
            Arrangement.setZoom(newZoom);
        } else if (e.shiftKey) {
            // Shift+Wheel = vertical scroll
            const newScrollY = Math.max(0, Arrangement.getScrollY() + e.deltaY);
            Arrangement.setScroll(Arrangement.getScrollX(), newScrollY);
        } else {
            // Wheel = horizontal scroll
            const newScrollX = Math.max(0, Arrangement.getScrollX() + e.deltaX + e.deltaY);
            Arrangement.setScroll(newScrollX, Arrangement.getScrollY());
        }
    }

    function onLongPress(e) {
        // Show context menu or selection action
        console.log('Long press at:', e.clientX, e.clientY);
        // Could show a radial menu or context actions
        App.toast('Long press detected — context menu coming soon', 'info');
    }

    function hasMoved(e) {
        const start = { x: dragStartX, y: dragStartY };
        return getDistance(start, { x: e.clientX, y: e.clientY }) > 8;
    }

    function getDistance(p1, p2) {
        const dx = p2.x - p1.x;
        const dy = p2.y - p1.y;
        return Math.sqrt(dx * dx + dy * dy);
    }

    function isTouch() { return isTouchDevice; }

    return { init, isTouch };
})();
