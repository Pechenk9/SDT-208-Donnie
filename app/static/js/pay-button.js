/*
 * Pay button: loading > success.
 *
 * Based on the "Loading to success" motion from designbookmark.com: the
 * button closes into a round spinner while the payment is sent, then opens
 * into a green bar, the check draws itself and "Paid" rises in. After that
 * the guest is taken to the receipt.
 *
 * Used on two pages:
 * - Donnie's payment page: the server answers with a signed LiqPay checkout
 *   ({"checkout": {url, data, signature}}); the spinner keeps turning while
 *   the browser posts it to LiqPay.
 * - the demo LiqPay checkout: the payment ends on the receipt, so the
 *   button plays the success state first.
 *
 * The springs keep the original stiffness / damping values; the engine is
 * the shared one in springs.js. Without JavaScript the form still submits
 * normally.
 */
(() => {
    'use strict';

    const button = document.getElementById('pay-button');
    const form = button && button.closest('form');
    if (!form || !button || !window.DonnieMotion) return;
    const ukrainian = document.documentElement.lang === 'uk';
    const text = ukrainian ? {
        processing: 'Обробляємо платіж…',
        complete: 'Платіж завершено. Дякуємо!',
        opening: 'Відкриваємо LiqPay…',
        failed: 'Не вдалося провести платіж. Кошти не списано — спробуйте ще раз.',
        offline: 'Не вдалося зв’язатися з Donnie. Перевірте з’єднання й спробуйте ще раз.',
        pay: amount => `Сплатити ₴${amount.toFixed(2)}`,
    } : {
        processing: 'Processing your payment…',
        complete: 'Payment complete. Thank you!',
        opening: 'Opening LiqPay…',
        failed: 'The payment could not be completed. Nothing was charged, please try again.',
        offline: 'We could not reach Donnie. Check your connection and try again.',
        pay: amount => `Pay ₴${amount.toFixed(2)}`,
    };

    const label = button.querySelector('.pay-btn__label');
    const spin = button.querySelector('.pay-btn__spin');
    const done = button.querySelector('.pay-btn__done');
    const tick = button.querySelector('.pay-btn__tick');
    const status = document.getElementById('pay-status');
    const otherButtons = [...form.querySelectorAll('button[type="submit"]')].filter(b => b !== button);
    const errorBox = document.getElementById('pay-error');

    const { spring, clamp, loop } = window.DonnieMotion;

    // Same values as the original component.
    const W = spring(1, 300, 22); // width, as a share of the full button
    const T = spring(1, 400, 30); // "Pay ₴…" label
    const P = spring(0, 300, 28); // spinner
    const D = spring(0, 220, 20); // "Paid" row
    const G = spring(0, 200, 30); // green fill
    const K = spring(0, 120, 20); // check drawing itself
    const springs = [W, T, P, D, G, K];

    const TICK_LENGTH = 22;
    tick.style.strokeDasharray = String(TICK_LENGTH);
    tick.style.strokeDashoffset = String(TICK_LENGTH);

    // Width in the "done" state, as in the original (140 of 168).
    const DONE_WIDTH = 140 / 168;
    const MIN_SPINNER_SECONDS = 1.6;
    const SUCCESS_HOLD_SECONDS = 1.4;

    let fullWidth = 0;
    let height = 0;
    let rotation = 0;
    let state = 'idle';

    const start = loop({
        springs,
        render: () => render(),
        onFrame: dt => { rotation = (rotation + dt * 360 * 1.4) % 360; },
        // The spinner keeps turning while the payment is in flight.
        keepAlive: () => state !== 'idle',
        onStop: () => reset(),
    });

    function render() {
        // Below the full width the button rounds off into a circle (radius = half the height).
        const width = Math.max(height, W.x * fullWidth);
        const closed = clamp((fullWidth - width) / Math.max(1, fullWidth - height), 0, 1);
        button.style.width = `${width.toFixed(2)}px`;
        button.style.borderRadius = `${(18 + (height / 2 - 18) * closed).toFixed(2)}px`;

        const g = clamp(G.x, 0, 1);
        button.style.background = g > 0.01
            ? `color-mix(in srgb, var(--success) ${(g * 100).toFixed(1)}%, #000)`
            : '';

        label.style.opacity = clamp(T.x, 0, 1).toFixed(3);
        label.style.transform = `translateY(${((1 - T.x) * 14).toFixed(2)}px)`;

        spin.style.opacity = clamp(P.x, 0, 1).toFixed(3);
        spin.style.transform = `rotate(${rotation}deg) scale(${(0.6 + 0.4 * clamp(P.x, 0, 1.2)).toFixed(3)})`;

        done.style.opacity = clamp(D.x, 0, 1).toFixed(3);
        done.style.transform = `translateY(${((1 - D.x) * 12).toFixed(2)}px)`;

        tick.style.strokeDashoffset = (TICK_LENGTH * (1 - clamp(K.x, 0, 1))).toFixed(2);
    }

    function reset() {
        ['width', 'borderRadius', 'background'].forEach(prop => { button.style[prop] = ''; });
        button.classList.remove('is-busy');
    }

    const wait = seconds => new Promise(resolve => setTimeout(resolve, seconds * 1000));

    /* ---------- states ---------- */

    function toLoading() {
        state = 'load';
        fullWidth = button.getBoundingClientRect().width;
        height = button.getBoundingClientRect().height;
        button.classList.add('is-busy');
        button.setAttribute('aria-disabled', 'true');
        otherButtons.forEach(b => { b.disabled = true; });
        if (errorBox) errorBox.hidden = true;
        status.textContent = text.processing;
        T.t = 0;
        W.t = height / fullWidth;
        P.t = 1;
        start();
    }

    function toSuccess() {
        state = 'done';
        P.t = 0;
        W.t = DONE_WIDTH;
        G.t = 1;
        D.t = 1;
        setTimeout(() => { K.t = 1; }, 150);
        status.textContent = text.complete;
        start();
    }

    function toIdle(message) {
        state = 'idle';
        D.t = 0;
        G.t = 0;
        K.t = 0;
        P.t = 0;
        W.t = 1;
        setTimeout(() => { T.t = 1; }, 120);
        button.removeAttribute('aria-disabled');
        otherButtons.forEach(b => { b.disabled = false; });
        status.textContent = message || '';
        if (message && errorBox) {
            errorBox.textContent = message;
            errorBox.hidden = false;
        }
        start();
    }

    /* ---------- submit ---------- */

    form.addEventListener('submit', async event => {
        // Only the Pay button gets the animation; other buttons submit as usual.
        if (event.submitter !== button) return;
        event.preventDefault();
        if (state !== 'idle' || start.isRunning()) return;

        const body = new URLSearchParams(new FormData(form));
        if (button.name) body.set(button.name, button.value);

        toLoading();
        let response = null;
        try {
            [response] = await Promise.all([
                fetch(form.action, {
                    method: 'POST',
                    body,
                    credentials: 'same-origin',
                    headers: { Accept: 'application/json, text/html;q=0.9' },
                }),
                wait(MIN_SPINNER_SECONDS),
            ]);
        } catch (error) {
            response = null;
        }

        // Donnie's payment page: post the signed checkout to LiqPay, spinner still turning.
        if (response && response.ok && (response.headers.get('content-type') || '').includes('application/json')) {
            const data = await response.json().catch(() => null);
            if (data && data.checkout) {
                status.textContent = text.opening;
                postCheckout(data.checkout);
                return;
            }
        }

        const target = response && response.ok ? new URL(response.url) : null;
        // A declined card comes back to the payment page with a message.
        if (target && target.pathname.endsWith('/pay') && target.searchParams.has('declined')) {
            window.location.assign(target.href);
            return;
        }
        if (target && target.pathname.endsWith('/receipt')) {
            toSuccess();
            await wait(SUCCESS_HOLD_SECONDS);
            window.location.assign(target.href);
            return;
        }

        toIdle(response
            ? text.failed
            : text.offline);
    });

    function postCheckout({ url, data, signature }) {
        const checkout = document.createElement('form');
        checkout.method = 'POST';
        checkout.action = url;
        checkout.acceptCharset = 'utf-8';
        checkout.hidden = true;
        // No Referer for LiqPay: see the referrer meta tag in payment.html.
        checkout.setAttribute('rel', 'noreferrer');
        [['data', data], ['signature', signature]].forEach(([name, value]) => {
            const input = document.createElement('input');
            input.type = 'hidden';
            input.name = name;
            input.value = value;
            checkout.appendChild(input);
        });
        document.body.appendChild(checkout);
        checkout.submit();
    }

    // Keep the label in sync with the tip (the inline script on the page updates the amount).
    form.addEventListener('change', event => {
        if (event.target.name !== 'tip_percent' || !form.dataset.total) return;
        const due = Number(form.dataset.total) + Number(event.target.dataset.amount);
        label.textContent = text.pay(due);
    });
})();
