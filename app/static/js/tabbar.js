/* Mobile tab bar pill (rebuilt from the "Tab pill" motion study).
 * A pill sits under the active tab. Two springs, one per edge: the edge in the direction
 * of travel is stiff (620/40) and the other is soft (170/19), so the pill stretches toward
 * the new tab and then pulls its tail in. Same spring values as the original.
 * Tabs are links to other pages, so the slide plays on the new page: it starts under the
 * tab you came from and springs to the current one. */
(() => {
    const bar = document.querySelector('.footer');
    const pill = bar && bar.querySelector('.tabbar-pill');
    if (!pill) return;
    const tabs = [...bar.querySelectorAll('.nav-item-container')];
    const KEY = 'donnie_tab_prev';
    const INSET = 4; // px of air between the pill and the tab edges

    /* ---------- tiny spring engine (same maths as the original motion.js) ---------- */
    const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
    const S = (x, k = 400, c = 30) => ({ x, v: 0, t: x, k, c });
    const tune = (s, k, c) => { s.k = k; s.c = reduce ? 2 * Math.sqrt(k) : c; };
    const step = (s, dt) => { const a = -s.k * (s.x - s.t) - s.c * s.v; s.v += a * dt; s.x += s.v * dt; };

    const A = S(0), B = S(0); // left and right edge of the pill
    let cur = tabs.findIndex(tab => tab.getAttribute('aria-current') === 'page');
    let running = false;

    // The bar is only shown on phones (display: none on wider screens).
    const visible = () => bar.getClientRects().length > 0;

    function edges(i) {
        const el = tabs[i];
        return [el.offsetLeft + INSET, el.offsetLeft + el.offsetWidth - INSET];
    }

    function snap(i) {
        [A.t, B.t] = edges(i);
        A.x = A.t; B.x = B.t; A.v = 0; B.v = 0;
        render();
    }

    function pick(i, from) {
        const dir = i > from ? 1 : -1;
        [A.t, B.t] = edges(i);
        if (dir > 0) { tune(B, 620, 40); tune(A, 170, 19); } else { tune(A, 620, 40); tune(B, 170, 19); }
        start();
    }

    function render() {
        pill.style.transform = `translateX(${A.x.toFixed(2)}px)`;
        pill.style.width = Math.max(0, B.x - A.x).toFixed(2) + 'px';
    }

    let last = 0;
    function loop(now) {
        const dt = Math.min((now - last) / 1000, 1 / 30); last = now;
        for (let k = 0; k < 4; k++) { step(A, dt / 4); step(B, dt / 4); }
        render();
        const settled = Math.abs(A.x - A.t) < 0.05 && Math.abs(B.x - B.t) < 0.05 && Math.abs(A.v) + Math.abs(B.v) < 0.05;
        if (settled) { A.x = A.t; B.x = B.t; render(); running = false; return; }
        requestAnimationFrame(loop);
    }
    function start() {
        if (running) return;
        running = true;
        last = performance.now();
        requestAnimationFrame(loop);
    }

    function setup() {
        if (!visible() || cur < 0) {
            pill.hidden = cur < 0;
            return;
        }
        pill.hidden = false;
        let prev = -1;
        try { prev = Number(sessionStorage.getItem(KEY)); } catch (error) { /* ignore */ }
        if (Number.isInteger(prev) && prev >= 0 && prev < tabs.length && prev !== cur) {
            snap(prev);
            requestAnimationFrame(() => pick(cur, prev));
        } else {
            snap(cur);
        }
        try { sessionStorage.removeItem(KEY); } catch (error) { /* ignore */ }
    }

    tabs.forEach((tab, i) => tab.addEventListener('click', () => {
        if (i === cur) return;
        // Remember where we came from, so the next page can slide from here.
        try { if (cur >= 0) sessionStorage.setItem(KEY, String(cur)); } catch (error) { /* ignore */ }
        if (cur >= 0) {
            pill.hidden = false;
            pick(i, cur);
        }
        tabs.forEach((t, k) => t.classList.toggle('is-going', k === i));
    }));

    // Keep the pill under its tab when the bar changes size (rotation, resize).
    addEventListener('resize', () => { if (cur >= 0 && visible()) snap(cur); });
    // Coming back with the browser's back button restores the old page as it was.
    addEventListener('pageshow', event => {
        if (!event.persisted) return;
        tabs.forEach(t => t.classList.remove('is-going'));
        if (cur >= 0 && visible()) snap(cur);
    });

    setup();
})();
