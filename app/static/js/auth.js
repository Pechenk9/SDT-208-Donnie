/*
 * Login / registration UX helpers. Authentication itself stays on the backend:
 * these checks only mirror its rules so customers see problems before submitting.
 */
(function () {
    'use strict';

    const JUST_REGISTERED_KEY = 'donnie_just_registered';
    const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

    function session(action, value) {
        try {
            if (action === 'set') sessionStorage.setItem(JUST_REGISTERED_KEY, value);
            if (action === 'get') return sessionStorage.getItem(JUST_REGISTERED_KEY);
            if (action === 'remove') sessionStorage.removeItem(JUST_REGISTERED_KEY);
        } catch (error) { /* storage blocked */ }
        return null;
    }

    /* ---------- profile: confirmation after successful registration ---------- */

    if (location.pathname === '/profile' && session('get')) {
        session('remove');
        const run = () => window.DonnieCart && window.DonnieCart.toast('Your account was created — welcome to Donnie!');
        if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run);
        else run();
    }

    /* ---------- password visibility ---------- */

    document.querySelectorAll('[data-password-toggle]').forEach(button => {
        const input = document.getElementById(button.getAttribute('aria-controls'));
        button.addEventListener('click', () => {
            const show = input.type === 'password';
            input.type = show ? 'text' : 'password';
            button.textContent = show ? 'Hide' : 'Show';
            button.setAttribute('aria-pressed', String(show));
        });
    });

    /* ---------- validation ---------- */

    const form = document.querySelector('[data-auth-form]');
    if (!form) return;

    const isRegister = form.hasAttribute('data-register-form');
    if (isRegister) session('remove');

    const field = name => form.querySelector(`[name="${name}"]`);

    const rules = {
        email(value) {
            if (!value.trim()) return 'Please enter your email.';
            if (!EMAIL_PATTERN.test(value.trim())) return 'Enter a valid email address, e.g. you@example.com.';
            return '';
        },
        password(value) {
            if (!value) return 'Please enter your password.';
            if (isRegister && value.length < 8) return 'Password must be at least 8 characters long.';
            return '';
        },
        first_name(value) {
            return value.trim() ? '' : 'Please enter your first name.';
        },
        last_name() {
            return '';
        },
        confirm_password(value) {
            if (!value) return 'Please confirm your password.';
            if (value !== field('password').value) return 'Passwords do not match.';
            return '';
        },
    };

    function show(input, message) {
        const errorId = input.dataset.error;
        const errorEl = errorId && document.getElementById(errorId);
        if (!errorEl) return;
        errorEl.textContent = message;
        input.setAttribute('aria-invalid', message ? 'true' : 'false');
        const ids = (input.getAttribute('aria-describedby') || '').split(' ').filter(id => id && id !== errorId);
        if (message) ids.push(errorId);
        if (ids.length) input.setAttribute('aria-describedby', ids.join(' '));
        else input.removeAttribute('aria-describedby');
    }

    const inputs = [...form.querySelectorAll('input[name]')].filter(input => rules[input.name]);

    inputs.forEach(input => {
        input.addEventListener('blur', () => {
            if (input.value || input.dataset.touched) show(input, rules[input.name](input.value));
            input.dataset.touched = '1';
        });
        input.addEventListener('input', () => {
            if (input.getAttribute('aria-invalid') === 'true') show(input, rules[input.name](input.value));
        });
    });

    form.addEventListener('submit', event => {
        let firstInvalid = null;
        inputs.forEach(input => {
            const message = rules[input.name](input.value);
            show(input, message);
            if (message && !firstInvalid) firstInvalid = input;
        });

        if (firstInvalid) {
            event.preventDefault();
            firstInvalid.focus();
            return;
        }

        const submit = form.querySelector('[type="submit"]');
        submit.setAttribute('aria-disabled', 'true');
        submit.textContent = isRegister ? 'Creating account…' : 'Logging in…';
        if (isRegister) session('set', '1');
    });
})();
