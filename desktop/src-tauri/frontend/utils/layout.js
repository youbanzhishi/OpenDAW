/**
 * OpenDAW — Responsive Layout Manager
 * Handles responsive breakpoints and layout state
 */
const LayoutManager = (() => {
    const breakpoints = {
        mobile: 768,
        tablet: 1200,
        desktop: Infinity
    };

    let currentLayout = 'desktop';
    let listeners = [];

    function detect() {
        const w = window.innerWidth;
        if (w < breakpoints.mobile) return 'mobile';
        if (w < breakpoints.tablet) return 'tablet';
        return 'desktop';
    }

    function update() {
        const newLayout = detect();
        if (newLayout !== currentLayout) {
            const old = currentLayout;
            currentLayout = newLayout;
            document.body.dataset.layout = newLayout;
            listeners.forEach(fn => fn(newLayout, old));
        }
    }

    function init() {
        document.body.dataset.layout = detect();
        currentLayout = detect();
        window.addEventListener('resize', update);
    }

    function onChange(fn) { listeners.push(fn); }
    function get() { return currentLayout; }
    function isMobile() { return currentLayout === 'mobile'; }
    function isTablet() { return currentLayout === 'tablet'; }
    function isDesktop() { return currentLayout === 'desktop'; }

    return { init, onChange, get, isMobile, isTablet, isDesktop };
})();
