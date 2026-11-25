/*
 * Login / registration UX helpers. Authentication itself stays on the backend:
 * these checks only mirror its rules so customers see problems before submitting.
 */
(function () {
    'use strict';

    const JUST_REGISTERED_KEY = 'donnie_just_registered';
    const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
    const ukrainian = document.documentElement.lang === 'uk';
    const text = ukrainian ? {
        welcome: 'Ваш обліковий запис створено — вітаємо в Donnie!',
        show: 'Показати',
        hide: 'Приховати',
        emailRequired: 'Введіть адресу електронної пошти.',
        emailInvalid: 'Введіть коректну адресу електронної пошти, наприклад you@example.com.',
        passwordRequired: 'Введіть пароль.',
        passwordLength: 'Пароль має містити щонайменше 8 символів.',
        firstNameRequired: 'Введіть ім’я.',
        confirmPassword: 'Підтвердьте пароль.',
        passwordMismatch: 'Паролі не збігаються.',
        creatingAccount: 'Створення облікового запису…',
        loggingIn: 'Вхід…',
    } : {
        welcome: 'Your account was created — welcome to Donnie!',
        show: 'Show',
        hide: 'Hide',
        emailRequired: 'Please enter your email.',
        emailInvalid: 'Enter a valid email address, e.g. you@example.com.',
        passwordRequired: 'Please enter your password.',
        passwordLength: 'Password must be at least 8 characters long.',
        firstNameRequired: 'Please enter your first name.',
        confirmPassword: 'Please confirm your password.',
        passwordMismatch: 'Passwords do not match.',
        creatingAccount: 'Creating account…',
        loggingIn: 'Logging in…',
    };

    function session(action, value) {
        try {
            if (action === 'set') sessionStorage.setItem(JUST_REGISTERED_KEY, value);
            if (action === 'get') return sessionStorage.getItem(JUST_REGISTERED_KEY);
            if (action === 'remove') sessionStorage.removeItem(JUST_REGISTERED_KEY);
        } catch (error) { /* storage blocked */ }
        return null;
    }

    /* ---------- profile: confirmation after successful registration ---------- */

    if ((location.pathname === '/en/profile' || location.pathname === '/ua/profile') && session('get')) {
        session('remove');
        const run = () => window.DonnieCart && window.DonnieCart.toast(text.welcome);
        if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run);
        else run();
    }

    /* ---------- password visibility ---------- */

    document.querySelectorAll('[data-password-toggle]').forEach(button => {
        const input = document.getElementById(button.getAttribute('aria-controls'));
        button.addEventListener('click', () => {
            const show = input.type === 'password';
            input.type = show ? 'text' : 'password';
            button.textContent = show ? text.hide : text.show;
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
            if (!value.trim()) return text.emailRequired;
            if (!EMAIL_PATTERN.test(value.trim())) return text.emailInvalid;
            return '';
        },
        password(value) {
            if (!value) return text.passwordRequired;
            if (isRegister && value.length < 8) return text.passwordLength;
            return '';
        },
        first_name(value) {
            return value.trim() ? '' : text.firstNameRequired;
        },
        last_name() {
            return '';
        },
        confirm_password(value) {
            if (!value) return text.confirmPassword;
            if (value !== field('password').value) return text.passwordMismatch;
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
        submit.textContent = isRegister ? text.creatingAccount : text.loggingIn;
        if (isRegister) session('set', '1');
    });
})();
