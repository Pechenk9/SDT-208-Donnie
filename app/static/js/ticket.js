/* Pickup ticket on the receipt (rebuilt from the "Parallax ticket" motion study).
 * The card tilts toward the cursor; each layer moves by its own depth, so the background,
 * the donut and the order number separate in space. A glare follows the cursor.
 * Tap flips it on a spring that overshoots a little, showing the QR code staff scan at pickup.
 * Untouched, it floats gently so the depth is visible even without a cursor.
 * Springs use the same stiffness/damping values as the original (see ticket.css tokens). */
(() => {
    const stage = document.getElementById('ticket-stage');
    if (!stage) return;
    const ticket = document.getElementById('ticket');
    const glare = document.getElementById('ticket-glare');
    const layers = [...ticket.querySelectorAll('.t-layer')].map(el => ({ el, depth: parseFloat(el.dataset.depth) }));

    /* ---------- tiny spring engine (same maths as the original shared motion.js) ---------- */
    const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
    // With reduced motion every spring is critically damped: it still moves, but never bounces.
    const S = (x, k = 400, c = 30) => ({ x, v: 0, t: x, k, c: reduce ? 2 * Math.sqrt(k) : c });
    const step = (s, dt) => { const a = -s.k * (s.x - s.t) - s.c * s.v; s.v += a * dt; s.x += s.v * dt; };
    const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
    const token = (name, fallback) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
    const num = (name, fallback) => parseFloat(token(name, String(fallback)));
    const spring = (name, fallback) => token(name, fallback).split(/\s+/).map(Number);

    const T = { tilt: num('--ticket-tilt', 14), depth: num('--ticket-depth', 12), flip: spring('--ticket-flip', '170 15') };

    const RX = S(0, 220, 18), RY = S(0, 220, 18), F = S(0, ...T.flip), G = S(0, 300, 26), LIFT = S(1, 300, 18);
    let hover = false, nx = 0, ny = 0, flipped = false, clock = 0, gx = 50, gy = 30;

    /* ---------- real QR code for this order (qrcode-generator from jsDelivr) ---------- */
    const qrBox = document.getElementById('ticket-qr');
    function drawQr() {
        const url = qrBox.dataset.url;
        if (typeof window.qrcode !== 'function') {
            qrBox.innerHTML = `<span class="t-qr__fallback">Show order #${qrBox.dataset.order} at the counter</span>`;
            return;
        }
        const qr = window.qrcode(0, 'M');
        qr.addData(url);
        qr.make();
        qrBox.innerHTML = qr.createSvgTag({ cellSize: 4, margin: 0, scalable: true });
    }
    if (document.readyState === 'complete') drawQr(); else addEventListener('load', drawQr);

    /* ---------- input ---------- */
    stage.addEventListener('pointermove', e => {
        if (e.pointerType === 'touch') return; // on phones: tap to flip, the card floats on its own
        const r = stage.getBoundingClientRect();
        nx = clamp((e.clientX - r.left) / r.width * 2 - 1, -1, 1);
        ny = clamp((e.clientY - r.top) / r.height * 2 - 1, -1, 1);
        gx = (nx + 1) * 50; gy = (ny + 1) * 50;
        hover = true;
    });
    stage.addEventListener('pointerleave', () => { hover = false; });
    stage.addEventListener('pointerdown', () => { LIFT.t = 0.97; });
    addEventListener('pointerup', () => { LIFT.t = 1; });

    const label = ticket.getAttribute('aria-label');
    function flip() {
        flipped = !flipped;
        F.t = flipped ? 180 : 0;
        LIFT.v += 1.5;
        ticket.setAttribute('aria-pressed', String(flipped));
        ticket.setAttribute('aria-label', flipped ? `${label}. QR code shown, press to flip back` : label);
    }
    ticket.addEventListener('click', flip);
    ticket.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); flip(); }
    });

    /* ---------- loop: 4 sub-steps per frame, dt capped like the original ---------- */
    function frame(dt) {
        clock += dt;
        if (hover) { RX.t = -ny * T.tilt; RY.t = nx * T.tilt; G.t = 1; }
        else if (reduce) { RX.t = 0; RY.t = 0; G.t = 0.25; }
        else { RX.t = Math.sin(clock * 0.9) * 4; RY.t = Math.cos(clock * 0.7) * 7; G.t = 0.25; }
        [RX, RY, F, G, LIFT].forEach(s => step(s, dt));
    }

    function render() {
        ticket.style.transform = `rotateX(${RX.x}deg) rotateY(${RY.x + F.x}deg) scale(${LIFT.x})`;
        // parallax: layers slide by depth against the tilt
        const ox = RY.x / T.tilt, oy = -RX.x / T.tilt;
        layers.forEach(l => { l.el.style.transform = `translate(${ox * T.depth * l.depth}px,${oy * T.depth * l.depth}px)`; });
        glare.style.setProperty('--g', clamp(G.x, 0, 1));
        glare.style.setProperty('--gx', (hover ? gx : 50 + ox * 30) + '%');
        glare.style.setProperty('--gy', (hover ? gy : 30 + oy * 30) + '%');
    }

    let last = performance.now();
    function loop(now) {
        const dt = Math.min((now - last) / 1000, 1 / 30); last = now;
        for (let k = 0; k < 4; k++) frame(dt / 4);
        render();
        requestAnimationFrame(loop);
    }
    requestAnimationFrame(loop);
})();
