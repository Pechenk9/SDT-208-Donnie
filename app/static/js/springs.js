/*
 * Tiny spring engine shared by Donnie's animated components (Pay button,
 * order tracker). Same maths as designbookmark.com's motion.js: springs are
 * "stiffness damping" with mass 1, frames are capped at 1/30 s and split
 * into 4 substeps, and when the visitor prefers reduced motion every spring
 * is critically damped (it settles without overshooting).
 */
window.DonnieMotion = (() => {
    'use strict';

    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    const spring = (x, k, c) => ({ x, v: 0, t: x, k, c: reduce ? 2 * Math.sqrt(k) : c });

    const step = (s, dt) => {
        const a = -s.k * (s.x - s.t) - s.c * s.v;
        s.v += a * dt;
        s.x += s.v * dt;
    };

    const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

    const isSettled = s => Math.abs(s.x - s.t) < 0.001 && Math.abs(s.v) < 0.001;

    /**
     * Runs one animation loop for a group of springs.
     *   springs     springs to step every frame
     *   render()    writes the spring values to the DOM
     *   onFrame(dt) optional, for things that are not springs (a spinner angle)
     *   keepAlive() optional, keeps the loop going even when springs are settled
     *   onStop()    optional, called once the loop stops
     * Returns start(): call it whenever a spring target changes.
     */
    function loop({ springs, render, onFrame, keepAlive = () => false, onStop }) {
        let running = false;
        let last = 0;

        function frame(now) {
            const dt = Math.min((now - last) / 1000, 1 / 30);
            last = now;
            if (onFrame) onFrame(dt);
            for (let i = 0; i < 4; i += 1) springs.forEach(s => step(s, dt / 4));
            render();
            if (!keepAlive() && springs.every(isSettled)) {
                running = false;
                if (onStop) onStop();
                return;
            }
            requestAnimationFrame(frame);
        }

        const start = () => {
            if (running) return;
            running = true;
            last = performance.now();
            requestAnimationFrame(frame);
        };
        start.isRunning = () => running;
        return start;
    }

    return { reduce, spring, step, clamp, loop };
})();
