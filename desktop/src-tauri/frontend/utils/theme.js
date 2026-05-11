/**
 * OpenDAW — Theme Manager
 * CSS custom property based theme system
 */
const ThemeManager = (() => {
    const themes = {
        dark: {
            '--bg-base':       '#121218',
            '--bg-surface':    '#1a1a24',
            '--bg-elevated':   '#22222e',
            '--bg-hover':      '#2a2a3a',
            '--bg-active':     '#32324a',
            '--text-primary':  '#e8e8f0',
            '--text-secondary':'#a0a0b8',
            '--text-muted':    '#606078',
            '--accent':        '#4a9eff',
            '--accent-hover':  '#6ab4ff',
            '--accent-dim':    'rgba(74,158,255,0.12)',
        },
        midnight: {
            '--bg-base':       '#0a0a14',
            '--bg-surface':    '#10101c',
            '--bg-elevated':   '#181828',
            '--bg-hover':      '#202038',
            '--bg-active':     '#2a2a4a',
            '--text-primary':  '#d0d0e8',
            '--text-secondary':'#8888a8',
            '--text-muted':    '#505070',
            '--accent':        '#6366f1',
            '--accent-hover':  '#818cf8',
            '--accent-dim':    'rgba(99,102,241,0.12)',
        }
    };

    let current = 'dark';

    function apply(name) {
        const theme = themes[name];
        if (!theme) return;
        current = name;
        const root = document.documentElement;
        Object.entries(theme).forEach(([key, val]) => {
            root.style.setProperty(key, val);
        });
    }

    function toggle() {
        apply(current === 'dark' ? 'midnight' : 'dark');
    }

    function get() { return current; }

    return { apply, toggle, get, themes };
})();
