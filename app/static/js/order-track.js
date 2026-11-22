/*
 * Order tracker on the receipt: step progress.
 *
 * Based on the "Step progress" motion from designbookmark.com. The green line
 * grows to the order's current step on a spring, every finished step fills
 * green and its check draws itself, and the current step pops up in navy.
 * The server renders the real status; this script animates up to it and
 * then checks for changes every few seconds while the page is open, so the
 * guest sees "Baking" or "Ready" as soon as the branch moves the order.
 * Spring values are the original ones (stiffness / damping).
 */
(() => {
    'use strict';

    const root = document.getElementById('order-track');
    if (!root || !window.DonnieMotion) return;

    const { spring, clamp, loop } = window.DonnieMotion;

    const bar = root.querySelector('.order-track__bar');
    const names = [...root.querySelectorAll('.order-track__names span')];
    const dots = [...root.querySelectorAll('.order-track__dot')];
    const N = dots.length;
    const hint = root.querySelector('.order-track__hint');
    const statusText = document.querySelector('.receipt-info .status');
    let current = clamp(Number(root.dataset.current) || 0, 0, N - 1);
    let complete = root.dataset.complete === 'true';

    const L = spring(0, 160, 22); // the line, as a share of the track
    const steps = dots.map((dot, i) => ({
        dot,
        num: dot.querySelector('b'),
        path: dot.querySelector('path'),
        name: names[i],
        f: spring(0, 260, 24),   // green fill when done
        c: spring(0, 140, 20),   // check drawing itself
        p: spring(1, 500, 14),   // pop when it becomes current
        on: spring(0, 300, 26),  // navy highlight of the current step
    }));
    const springs = [L, ...steps.flatMap(s => [s.f, s.c, s.p, s.on])];

    function render() {
        bar.style.width = `${(clamp(L.x, 0, 1) * 100).toFixed(3)}%`;
        steps.forEach(s => {
            const f = clamp(s.f.x, 0, 1);
            const o = clamp(s.on.x, 0, 1);
            s.dot.style.background = f > 0.01
                ? `color-mix(in srgb, var(--success) ${(f * 100).toFixed(1)}%, #fff)`
                : o > 0.01
                    ? `color-mix(in srgb, var(--cta) ${(o * 100).toFixed(1)}%, #fff)`
                    : '';
            // The grey ring fades out as the step fills.
            s.dot.style.boxShadow = `inset 0 0 0 2px rgba(236, 228, 232, ${(1 - Math.max(f, o)).toFixed(3)})`;
            s.dot.style.color = o > 0.5 ? '#fff' : '';
            s.num.style.opacity = (1 - f).toFixed(3);
            s.path.style.strokeDashoffset = (22 * (1 - clamp(s.c.x, 0, 1))).toFixed(2);
            s.dot.style.transform = `scale(${s.p.x.toFixed(4)})`;
        });
    }

    const start = loop({ springs, render });

    // Same as go(i) in the original: set every target, then kick the current step.
    function go(i, allDone) {
        steps.forEach((s, k) => {
            const isCurrent = k === i && !allDone;
            if (isCurrent) s.dot.setAttribute('aria-current', 'step');
            else s.dot.removeAttribute('aria-current');
            const label = s.dot.querySelector('.visually-hidden');
            if (label) {
                const state = k < i || allDone ? 'done' : (isCurrent ? 'in progress' : 'next');
                label.textContent = `${s.name.textContent}: ${state}`;
            }
        });
        L.t = i / (N - 1);
        steps.forEach((s, k) => {
            const done = k < i || (allDone && k === i);
            s.f.t = done ? 1 : 0;
            s.on.t = k === i && !done ? 1 : 0;
            s.name.classList.toggle('is-on', k <= i);
            if (done) setTimeout(() => { s.c.t = 1; start(); }, 120);
            else s.c.t = 0;
        });
        steps[i].p.x = 0.7;
        steps[i].p.v = 6;
        start();
    }

    // Start from an empty line and grow to the real status once the receipt is on screen.
    steps.forEach(s => s.name.classList.remove('is-on'));
    render();

    let played = false;
    const play = () => {
        if (played) return;
        played = true;
        setTimeout(() => go(current, complete), 250);
    };

    /* ---------- live updates ---------- */

    const POLL_SECONDS = 10;
    const statusUrl = root.dataset.statusUrl;

    async function refresh() {
        if (!statusUrl || document.visibilityState !== 'visible') return;
        let data;
        try {
            const response = await fetch(statusUrl, { headers: { Accept: 'application/json' }, cache: 'no-store' });
            if (!response.ok) return;
            data = await response.json();
        } catch (error) {
            return; // Offline for a moment: try again on the next tick.
        }

        // A cancelled order has no tracker: reload to show the cancelled notice.
        if (!data.progress) {
            window.location.reload();
            return;
        }

        if (statusText) statusText.textContent = data.status.charAt(0).toUpperCase() + data.status.slice(1);
        if (hint) hint.textContent = data.progress.hint;

        const nextCurrent = clamp(Number(data.progress.current) || 0, 0, N - 1);
        const nextComplete = Boolean(data.progress.complete);
        if (nextCurrent === current && nextComplete === complete) return;
        current = nextCurrent;
        complete = nextComplete;
        if (played) go(current, complete);
    }

    // Done orders don't change any more, so there is nothing to watch.
    if (statusUrl && !complete) {
        const timer = setInterval(() => {
            if (complete) clearInterval(timer);
            else refresh();
        }, POLL_SECONDS * 1000);
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible' && !complete) refresh();
        });
    }

    if ('IntersectionObserver' in window) {
        const observer = new IntersectionObserver(entries => {
            if (entries.some(entry => entry.isIntersecting)) {
                observer.disconnect();
                play();
            }
        }, { threshold: 0.6 });
        observer.observe(root);
    } else {
        play();
    }
})();
