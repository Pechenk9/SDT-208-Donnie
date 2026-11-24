/*
 * Shared branch selection.
 *
 * The backend reads the selected branch from the `selected_branch` cookie (branch code).
 * The cart stores the same branch as `branch_id`. This module keeps the two in sync:
 * whenever one changes, the other is updated, so there is a single selected branch.
 */
(function () {
    'use strict';

    const COOKIE_NAME = 'selected_branch';
    const LIST_CACHE_KEY = 'donnie_branches_v1';
    const RELOAD_GUARD_KEY = 'donnie_branch_sync_reload';
    const ukrainian = document.documentElement.lang === 'uk';

    function countPhrase(count, type) {
        if (!ukrainian) {
            return type === 'donut'
                ? window.DonnieCart.plural(count, 'donut', 'donuts')
                : window.DonnieCart.plural(count, 'line', 'lines');
        }

        const lastTwo = count % 100;
        const last = count % 10;
        const form = lastTwo >= 11 && lastTwo <= 14
            ? 2
            : last === 1
                ? 0
                : last >= 2 && last <= 4
                    ? 1
                    : 2;
        const words = type === 'donut'
            ? ['пончик', 'пончики', 'пончиків']
            : ['позиція', 'позиції', 'позицій'];
        return `${count} ${words[form]}`;
    }

    const dialog = document.getElementById('branch-dialog');
    let branches = [];
    let pendingBranch = null;

    /* ---------- cookie ---------- */

    function readCookie() {
        const match = document.cookie.split('; ').find(part => part.startsWith(`${COOKIE_NAME}=`));
        return match ? decodeURIComponent(match.slice(COOKIE_NAME.length + 1)) : null;
    }

    function writeCookie(code) {
        const secure = location.protocol === 'https:' ? '; secure' : '';
        document.cookie = `${COOKIE_NAME}=${encodeURIComponent(code)}; path=/; max-age=31536000; samesite=lax${secure}`;
    }

    /* ---------- branch list ---------- */

    async function loadBranches() {
        try {
            const cached = sessionStorage.getItem(LIST_CACHE_KEY);
            if (cached) return JSON.parse(cached);
        } catch (error) { /* ignore */ }

        const languagePrefix = document.documentElement.lang.toLowerCase().startsWith('uk')
            ? '/ua'
            : '/en';
        const response = await fetch(`${languagePrefix}/api/branches`, { headers: { Accept: 'application/json' } });
        if (!response.ok) throw new Error('Branches could not be loaded.');
        const list = await response.json();
        try { sessionStorage.setItem(LIST_CACHE_KEY, JSON.stringify(list)); } catch (error) { /* ignore */ }
        return list;
    }

    const byId = id => branches.find(branch => branch.id === Number(id)) || null;
    const byCode = code => branches.find(branch => branch.code === code) || null;

    function current() {
        return byCode(readCookie());
    }

    /* ---------- keep cookie and cart in sync ---------- */

    function needsServerRender() {
        return document.body.hasAttribute('data-branch-dependent');
    }

    function reloadOnce() {
        try {
            if (sessionStorage.getItem(RELOAD_GUARD_KEY)) return false;
            sessionStorage.setItem(RELOAD_GUARD_KEY, '1');
        } catch (error) {
            return false;
        }
        location.reload();
        return true;
    }

    function sync() {
        const Cart = window.DonnieCart;
        const cart = Cart.read();
        const cookieBranch = current();
        let cartBranch = cart.branch_id ? byId(cart.branch_id) : null;

        // The cart points at a branch that no longer exists: its lines cannot be ordered.
        if (cart.branch_id && !cartBranch) {
            Cart.setBranch(cookieBranch ? cookieBranch.id : null, { clearItems: true });
            cartBranch = null;
        }

        const { donuts } = Cart.totals();

        if (cookieBranch && (!cartBranch || cartBranch.id === cookieBranch.id || donuts === 0)) {
            if (cart.branch_id !== cookieBranch.id) Cart.setBranch(cookieBranch.id);
            return true;
        }

        if (cartBranch) {
            // The cart (with items) belongs to another branch than the cookie, or the cookie
            // is missing: restore the cookie so the backend renders the cart's branch.
            writeCookie(cartBranch.code);
            if (needsServerRender() && reloadOnce()) return false;
        }
        return true;
    }

    /* ---------- labels across the page ---------- */

    function renderLabels() {
        const branch = current();
        document.querySelectorAll('[data-branch-label]').forEach(node => {
            node.textContent = branch ? branch.city : ukrainian ? 'Оберіть філію' : 'Choose branch';
        });
        document.querySelectorAll('[data-open-branch]').forEach(button => {
            button.setAttribute(
                'aria-label',
                branch
                    ? ukrainian
                        ? `Філія: ${branch.name}, ${branch.city}. Змінити філію`
                        : `Branch: ${branch.name}, ${branch.city}. Change branch`
                    : ukrainian ? 'Оберіть філію' : 'Choose a branch'
            );
        });
    }

    /* ---------- dialog ---------- */

    function showView(name) {
        dialog.querySelectorAll('[data-view]').forEach(view => {
            view.hidden = view.dataset.view !== name;
        });
        dialog.setAttribute('aria-labelledby', name === 'confirm' ? 'branch-confirm-title' : 'branch-dialog-title');
    }

    function renderList(message) {
        const list = dialog.querySelector('[data-branch-list]');
        const note = dialog.querySelector('[data-branch-note]');
        const selected = current();

        note.textContent = message || (ukrainian
            ? 'Асортимент, ціни та наявність залежать від обраної філії.'
            : 'Assortment, prices and availability depend on the branch you choose.');
        list.replaceChildren();

        if (!branches.length) {
            const empty = document.createElement('p');
            empty.className = 'state-message state-message--error';
            empty.textContent = ukrainian
                ? 'Не вдалося завантажити філії. Оновіть сторінку та спробуйте ще раз.'
                : 'Branches could not be loaded. Please refresh the page and try again.';
            list.appendChild(empty);
            return;
        }

        branches.forEach(branch => {
            const isCurrent = selected && selected.id === branch.id;
            const item = document.createElement('li');
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'branch-option';
            button.dataset.branchId = String(branch.id);
            if (isCurrent) button.setAttribute('aria-current', 'true');

            const city = document.createElement('span');
            city.className = 'branch-option__city';
            city.textContent = branch.city;

            const name = document.createElement('span');
            name.className = 'branch-option__name';
            name.textContent = branch.name;

            const address = document.createElement('span');
            address.className = 'branch-option__address';
            address.textContent = branch.address || '';

            button.append(city, name, address);

            if (isCurrent) {
                const badge = document.createElement('span');
                badge.className = 'branch-option__badge';
                badge.textContent = ukrainian ? 'Обрана' : 'Selected';
                button.appendChild(badge);
            }

            item.appendChild(button);
            list.appendChild(item);
        });
    }

    function open(message) {
        if (!dialog) return;
        pendingBranch = null;
        renderList(message);
        showView('list');
        if (!dialog.open) dialog.showModal();
        const target = dialog.querySelector('.branch-option[aria-current="true"]') || dialog.querySelector('.branch-option');
        if (target) target.focus();
    }

    function apply(branch, clearItems) {
        writeCookie(branch.code);
        window.DonnieCart.setBranch(branch.id, { clearItems });
        dialog.close();
        // The backend renders assortment and prices for the selected branch.
        location.reload();
    }

    function choose(branchId) {
        const branch = byId(branchId);
        if (!branch) return;

        const selected = current();
        if (selected && selected.id === branch.id) {
            dialog.close();
            return;
        }

        const cart = window.DonnieCart.read();
        const { donuts, lines } = window.DonnieCart.totals(cart);
        if (donuts > 0 && cart.branch_id !== branch.id) {
            pendingBranch = branch;
            const from = byId(cart.branch_id);
            dialog.querySelector('[data-confirm-text]').textContent =
                ukrainian
                    ? `У кошику ${countPhrase(donuts, 'donut')} (${countPhrase(lines, 'line')})` +
                        `${from ? ` з філії ${from.name}` : ''}. Перехід до філії ${branch.name} очистить кошик, адже асортимент і ціни відрізняються між філіями.`
                    : `Your cart has ${countPhrase(donuts, 'donut')} ` +
                        `(${countPhrase(lines, 'line')})` +
                        `${from ? ` from ${from.name}` : ''}. ` +
                        `Switching to ${branch.name} will empty your cart, because assortment and prices differ between branches.`;
            showView('confirm');
            dialog.querySelector('[data-confirm-cancel]').focus();
            return;
        }

        apply(branch, false);
    }

    if (dialog) {
        dialog.addEventListener('click', event => {
            const option = event.target.closest('.branch-option');
            if (option) choose(option.dataset.branchId);

            if (event.target.closest('[data-close]')) dialog.close();
            if (event.target.closest('[data-confirm-cancel]')) {
                pendingBranch = null;
                // A QR welcome for the branch the user just declined must not show later.
                try { sessionStorage.removeItem('donnie_qr_welcome'); } catch (error) { /* ignore */ }
                renderList();
                showView('list');
                const selected = dialog.querySelector('.branch-option[aria-current="true"]');
                if (selected) selected.focus();
            }
            if (event.target.closest('[data-confirm-accept]') && pendingBranch) {
                apply(pendingBranch, true);
            }
        });

        // Light dismiss where `closedby` is not supported yet (Safari).
        if (!('closedBy' in HTMLDialogElement.prototype)) {
            const outside = (event) => {
                const rect = dialog.getBoundingClientRect();
                return event.clientX < rect.left || event.clientX > rect.right ||
                    event.clientY < rect.top || event.clientY > rect.bottom;
            };
            let pressedOutside = false;
            dialog.addEventListener('pointerdown', event => { pressedOutside = outside(event); });
            dialog.addEventListener('pointerup', event => {
                if (pressedOutside && outside(event)) dialog.close();
            });
        }
    }

    document.addEventListener('click', event => {
        if (event.target.closest('[data-open-branch]')) open();

        // "Order from this Donnie" buttons (home page): pick a branch directly.
        // The dialog opens first so the "your cart will be emptied" confirmation can show in it.
        const pick = event.target.closest('[data-choose-branch]');
        if (pick) {
            ready.then(() => {
                open();
                choose(pick.dataset.chooseBranch);
            });
        }
    });

    /* ---------- QR codes: /qr/BRANCH?table=N lands on /en/store?branch=BRANCH&table=N ---------- */

    const TABLE_KEY = 'donnie_table';
    const WELCOME_KEY = 'donnie_qr_welcome';
    const TABLE_TTL_MS = 4 * 60 * 60 * 1000; // a table visit lasts at most a few hours

    function rememberTable(branch, table) {
        try {
            if (table) {
                localStorage.setItem(TABLE_KEY, JSON.stringify({ branch_id: branch.id, table, at: Date.now() }));
            } else {
                localStorage.removeItem(TABLE_KEY);
            }
            sessionStorage.setItem(
                WELCOME_KEY,
                ukrainian
                    ? table ? `Вітаємо у ${branch.name} · стіл ${table}` : `Вітаємо у ${branch.name}`
                    : table ? `Welcome to ${branch.name} · Table ${table}` : `Welcome to ${branch.name}`
            );
        } catch (error) { /* storage blocked: the QR still selects the branch */ }
    }

    // Table number for the currently selected branch, or null.
    function currentTable() {
        try {
            const saved = JSON.parse(localStorage.getItem(TABLE_KEY) || 'null');
            const selected = current();
            if (!saved || !selected || saved.branch_id !== selected.id) return null;
            if (Date.now() - saved.at > TABLE_TTL_MS) {
                localStorage.removeItem(TABLE_KEY);
                return null;
            }
            return Number(saved.table) || null;
        } catch (error) {
            return null;
        }
    }

    function handleQrLanding() {
        const params = new URLSearchParams(location.search);
        const code = params.get('branch');
        if (!code) return;

        const table = Number(params.get('table'));
        params.delete('branch');
        params.delete('table');
        // Clean the URL first, so the reload after choosing the branch doesn't repeat this.
        const query = params.toString();
        history.replaceState(null, '', location.pathname + (query ? `?${query}` : '') + location.hash);

        const target = byCode(code);
        if (!target) return;
        rememberTable(target, Number.isInteger(table) && table > 0 ? table : null);

        const selected = current();
        if (!selected || selected.id !== target.id) {
            // Same flow as picking a branch by hand, including the "your cart will be emptied" warning.
            open();
            choose(target.id);
        }
    }

    function showQrWelcome() {
        try {
            const text = sessionStorage.getItem(WELCOME_KEY);
            if (!text) return;
            sessionStorage.removeItem(WELCOME_KEY);
            if (window.DonnieCart && window.DonnieCart.toast) window.DonnieCart.toast(text, { type: 'success' });
        } catch (error) { /* ignore */ }
    }

    /* ---------- start ---------- */

    const ready = loadBranches()
        .then(list => {
            branches = Array.isArray(list) ? list : [];
            const settled = sync();
            try { if (settled) sessionStorage.removeItem(RELOAD_GUARD_KEY); } catch (error) { /* ignore */ }
            renderLabels();
            if (settled) {
                handleQrLanding();
                if (!dialog || !dialog.open) showQrWelcome();
            }
            return current();
        })
        .catch(() => {
            renderLabels();
            return null;
        });

    window.DonnieBranch = {
        ready,
        open,
        current,
        list: () => branches.slice(),
        byId,
        table: currentTable,
    };
})();
