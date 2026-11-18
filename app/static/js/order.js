(function () {
    'use strict';

    const Cart = window.DonnieCart;
    const Branch = window.DonnieBranch;

    const data = JSON.parse(document.getElementById('checkout-data').textContent);
    const fallbackProducts = new Map((data.products || []).map(product => [Number(product.id), product]));

    const el = id => document.getElementById(id);
    const loadingView = el('checkout-loading');
    const emptyView = el('checkout-empty');
    const successView = el('checkout-success');
    const contentView = el('checkout-content');
    const linesList = el('cart-lines');
    const form = el('order-form');
    const submitBtn = el('place-order-btn');
    const blocker = el('checkout-blocker');
    const errorBox = el('checkout-error');
    const addressGroup = el('address-group');
    const addressInput = el('delivery-address');
    const clearDialog = el('clear-cart-dialog');

    const details = new Map(); // product id -> prepared product data from /product/{id}
    const failed = new Set();  // product ids whose details could not be loaded
    let branch = null;
    let submitting = false;
    let completed = false;

    /* ---------- product details ---------- */

    async function loadDetails(cart) {
        const ids = [...new Set(cart.items.map(item => item.product_id))].filter(id => !details.has(id));
        await Promise.all(ids.map(id =>
            Cart.loadProduct(id)
                .then(product => { details.set(id, product); failed.delete(id); })
                .catch(() => { failed.add(id); })
        ));
    }

    /* ---------- line validation ---------- */

    function lineProblem(item) {
        const product = details.get(item.product_id);
        if (!product) {
            return failed.has(item.product_id)
                ? 'This donut is no longer on the menu. Remove it to continue.'
                : null;
        }
        if (product.is_available === false) {
            return `${product.name} is not available at this branch right now. Remove it to continue.`;
        }

        const recipe = product.ingredients || [];
        const chosen = new Map(item.ingredients.map(entry => [entry.ingredient_id, entry.quantity]));
        const valid = recipe.length === chosen.size && recipe.every(ingredient => {
            if (!chosen.has(ingredient.id)) return false;
            const quantity = chosen.get(ingredient.id);
            if (quantity < 0 || quantity > Number(ingredient.max_quantity)) return false;
            if (!ingredient.is_changeable && quantity !== Number(ingredient.default_quantity)) return false;
            return true;
        });
        return valid ? null : 'The recipe of this donut changed since you added it. Remove it and add it again.';
    }

    /* ---------- rendering ---------- */

    function customizationSummary(item, product) {
        if (!product) return 'Customization details unavailable';
        const byId = new Map((product.ingredients || []).map(ingredient => [ingredient.id, ingredient]));
        const changes = [];
        item.ingredients.forEach(entry => {
            const ingredient = byId.get(entry.ingredient_id);
            if (!ingredient || entry.quantity === Number(ingredient.default_quantity)) return;
            changes.push(entry.quantity === 0
                ? `no ${ingredient.name.toLowerCase()}`
                : `${ingredient.name} ${Cart.formatQuantity(entry.quantity)} ${ingredient.unit}`);
        });
        return changes.length ? changes.join(' · ') : 'Original recipe';
    }

    function ingredientTable(item, product) {
        const wrapper = document.createElement('details');
        wrapper.className = 'line-ingredients';
        const summary = document.createElement('summary');
        summary.textContent = 'Ingredients per donut';
        wrapper.appendChild(summary);

        const list = document.createElement('ul');
        const byId = new Map(((product && product.ingredients) || []).map(ingredient => [ingredient.id, ingredient]));
        item.ingredients.forEach(entry => {
            const ingredient = byId.get(entry.ingredient_id);
            const li = document.createElement('li');
            const name = document.createElement('span');
            name.textContent = ingredient ? ingredient.name : `Ingredient #${entry.ingredient_id}`;
            const amount = document.createElement('span');
            amount.className = 'line-ingredients__amount';
            const unit = ingredient ? ` ${ingredient.unit}` : '';
            amount.textContent = entry.quantity === 0 ? 'removed' : `${Cart.formatQuantity(entry.quantity)}${unit}`;
            if (ingredient && entry.quantity !== Number(ingredient.default_quantity)) li.classList.add('is-changed');
            li.append(name, amount);
            list.appendChild(li);
        });
        wrapper.appendChild(list);
        return wrapper;
    }

    function renderLine(item) {
        const product = details.get(item.product_id);
        const fallback = fallbackProducts.get(item.product_id);
        const name = (product && product.name) || (fallback && fallback.name) || `Donut #${item.product_id}`;
        const image = (product && product.image_url) || (fallback && fallback.image_url) || '/static/assets/icons/donnie-donut-icon.png';
        const problem = lineProblem(item);

        const li = document.createElement('li');
        li.className = 'cart-line' + (problem ? ' has-problem' : '');
        li.dataset.lineId = item.line_id;

        const img = document.createElement('img');
        img.className = 'cart-line__img';
        img.src = image;
        img.alt = '';
        img.width = 88;
        img.height = 88;

        const body = document.createElement('div');
        body.className = 'cart-line__body';

        const title = document.createElement('h3');
        title.className = 'cart-line__name';
        const link = document.createElement('a');
        link.href = `/product/${item.product_id}`;
        link.textContent = name;
        title.appendChild(link);

        const custom = document.createElement('p');
        custom.className = 'cart-line__custom';
        custom.textContent = customizationSummary(item, product);

        body.append(title, custom, ingredientTable(item, product));

        if (problem) {
            const warn = document.createElement('p');
            warn.className = 'cart-line__problem';
            warn.textContent = problem;
            body.appendChild(warn);
        }

        const controls = document.createElement('div');
        controls.className = 'cart-line__controls';

        const stepper = document.createElement('div');
        stepper.className = 'stepper';
        stepper.setAttribute('role', 'group');
        stepper.setAttribute('aria-label', `Quantity of ${name}`);
        stepper.innerHTML = `
            <button type="button" class="stepper__btn" data-action="decrease" aria-label="One less ${name}">&minus;</button>
            <output class="stepper__value" aria-live="polite">${item.quantity}</output>
            <button type="button" class="stepper__btn" data-action="increase" aria-label="One more ${name}">+</button>`;
        stepper.querySelector('[data-action="decrease"]').disabled = item.quantity <= 1;
        stepper.querySelector('[data-action="increase"]').disabled = item.quantity >= Cart.MAX_LINE_QUANTITY;

        const price = document.createElement('p');
        price.className = 'cart-line__price';
        if (product) {
            const unit = Cart.estimateUnitPrice(product, item.ingredients);
            price.innerHTML = `<strong>${Cart.formatPrice(unit * item.quantity)}</strong><span>${Cart.formatPrice(unit)} each</span>`;
        } else {
            price.innerHTML = '<strong>—</strong>';
        }

        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'link-btn link-btn--danger';
        remove.dataset.action = 'remove';
        remove.textContent = 'Remove';
        remove.setAttribute('aria-label', `Remove ${name} from cart`);

        controls.append(stepper, price, remove);
        li.append(img, body, controls);
        return li;
    }

    function estimatedTotal(cart) {
        let total = 0;
        let complete = true;
        cart.items.forEach(item => {
            const product = details.get(item.product_id);
            if (!product) { complete = false; return; }
            total += Cart.estimateUnitPrice(product, item.ingredients) * item.quantity;
        });
        return { total, complete };
    }

    function renderSummary(cart) {
        const { donuts, lines } = Cart.totals(cart);
        const { total, complete } = estimatedTotal(cart);
        const missing = Math.max(0, Cart.MIN_ORDER_DONUTS - donuts);

        el('summary-donuts').textContent = String(donuts);
        el('summary-lines').textContent = String(lines);
        el('summary-total').textContent = Cart.formatPrice(total) + (complete ? '' : '+');

        el('min-order').classList.toggle('is-met', missing === 0);
        el('min-order-fill').style.width = `${Math.min(100, (donuts / Cart.MIN_ORDER_DONUTS) * 100)}%`;
        el('min-order-text').textContent = missing > 0
            ? `Minimum order is ${Cart.MIN_ORDER_DONUTS} donuts — add ${Cart.plural(missing, 'more', 'more')}.`
            : `Minimum of ${Cart.MIN_ORDER_DONUTS} donuts reached.`;

        el('checkout-branch-name').textContent = branch ? `${branch.name}, ${branch.city}` : 'No branch selected';
        el('checkout-branch-address').textContent = branch ? branch.address || '' : '';
    }

    function blockingReasons(cart) {
        const reasons = [];
        const { donuts } = Cart.totals(cart);
        if (!branch || cart.branch_id !== branch.id) reasons.push('Choose a branch for your order.');
        if (donuts < Cart.MIN_ORDER_DONUTS) {
            reasons.push(`Add ${Cart.plural(Cart.MIN_ORDER_DONUTS - donuts, 'more donut', 'more donuts')} — the minimum order is ${Cart.MIN_ORDER_DONUTS} donuts in total.`);
        }
        if (cart.items.some(item => lineProblem(item))) reasons.push('Fix or remove the highlighted cart lines.');
        return reasons;
    }

    function renderBlocker(cart) {
        const reasons = blockingReasons(cart);
        blocker.hidden = reasons.length === 0;
        blocker.textContent = reasons.join(' ');
        submitBtn.setAttribute('aria-disabled', String(reasons.length > 0 || submitting));
        if (reasons.length) submitBtn.setAttribute('aria-describedby', 'checkout-blocker');
        else submitBtn.removeAttribute('aria-describedby');
    }

    function render() {
        if (completed) return;
        const cart = Cart.read();
        loadingView.hidden = true;

        if (cart.items.length === 0) {
            contentView.hidden = true;
            emptyView.hidden = false;
            return;
        }

        emptyView.hidden = true;
        contentView.hidden = false;
        linesList.replaceChildren(...cart.items.map(renderLine));
        renderSummary(cart);
        renderBlocker(cart);
    }

    /* ---------- cart management ---------- */

    linesList.addEventListener('click', event => {
        const button = event.target.closest('button[data-action]');
        if (!button || button.disabled) return;
        const line = button.closest('.cart-line');
        const lineId = line.dataset.lineId;
        const item = Cart.read().items.find(entry => entry.line_id === lineId);
        if (!item) return;

        if (button.dataset.action === 'increase') Cart.setLineQuantity(lineId, item.quantity + 1);
        if (button.dataset.action === 'decrease') Cart.setLineQuantity(lineId, item.quantity - 1);
        if (button.dataset.action === 'remove') {
            const next = line.nextElementSibling || line.previousElementSibling;
            Cart.removeLine(lineId);
            Cart.toast('Removed from cart.');
            const focusTarget = next && document.querySelector(`[data-line-id="${next.dataset.lineId}"] [data-action="remove"]`);
            (focusTarget || el('cart-title')).focus?.();
            return;
        }
        // Keep focus on the same control after re-rendering.
        const again = document.querySelector(`[data-line-id="${lineId}"] [data-action="${button.dataset.action}"]`);
        if (again && !again.disabled) again.focus();
    });

    el('clear-cart-btn').addEventListener('click', () => {
        clearDialog.returnValue = '';
        clearDialog.showModal();
    });

    clearDialog.addEventListener('close', () => {
        if (clearDialog.returnValue === 'clear') {
            Cart.clearItems();
            Cart.toast('Your cart is now empty.');
        }
        clearDialog.returnValue = '';
    });

    Cart.subscribe(cart => {
        loadDetails(cart).then(render);
        render();
    });

    /* ---------- form ---------- */

    const fields = {
        name: el('customer-name'),
        phone: el('customer-phone'),
        email: el('customer-email'),
        address: addressInput,
    };

    function fulfillment() {
        const checked = form.querySelector('input[name="fulfillment_type"]:checked');
        return checked ? checked.value : 'pickup';
    }

    function validateField(input) {
        const value = input.value.trim();
        if (input === fields.name) {
            if (!value) return 'Please enter your name.';
        }
        if (input === fields.phone) {
            if (!value) return 'Please enter a phone number so we can reach you.';
            const digits = value.replace(/\D/g, '');
            if (!/^(0\d{9}|380\d{9})$/.test(digits)) return 'Enter a Ukrainian number, e.g. 0671234567 or +380671234567.';
        }
        if (input === fields.email && value) {
            if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value)) return 'Enter a valid email address, e.g. you@example.com.';
        }
        if (input === fields.address && fulfillment() === 'delivery') {
            if (!value) return 'Please enter the delivery address.';
        }
        return '';
    }

    function showFieldError(input, message) {
        const errorId = input.dataset.error;
        const errorEl = el(errorId);
        errorEl.textContent = message;
        input.setAttribute('aria-invalid', message ? 'true' : 'false');
        const describedBy = (input.getAttribute('aria-describedby') || '')
            .split(' ').filter(id => id && id !== errorId);
        if (message) describedBy.push(errorId);
        if (describedBy.length) input.setAttribute('aria-describedby', describedBy.join(' '));
        else input.removeAttribute('aria-describedby');
    }

    Object.values(fields).forEach(input => {
        input.addEventListener('blur', () => {
            if (input.value.trim() || input.dataset.touched) showFieldError(input, validateField(input));
            input.dataset.touched = '1';
        });
        input.addEventListener('input', () => {
            if (input.getAttribute('aria-invalid') === 'true') showFieldError(input, validateField(input));
        });
    });

    function updateFulfillment() {
        const delivery = fulfillment() === 'delivery';
        addressGroup.hidden = !delivery;
        addressInput.required = delivery;
        if (!delivery) showFieldError(addressInput, '');
    }

    form.querySelectorAll('input[name="fulfillment_type"]').forEach(radio => {
        radio.addEventListener('change', () => {
            updateFulfillment();
            if (fulfillment() === 'delivery') addressInput.focus();
        });
    });

    /* ---------- submission ---------- */

    function serverMessage(status, payload) {
        const detail = payload && payload.detail;
        if (typeof detail === 'string') {
            if (detail === 'Duplicate product in order') {
                return 'Your cart has the same donut in more than one customization. Our ordering system can only accept one version of each donut at the moment — please remove the extra versions and try again.';
            }
            if (detail === 'Invalid Ukrainian phone number') return 'Please check your phone number — it must be a Ukrainian number.';
            if (detail === 'Branch not found') return 'The selected branch is no longer available. Please choose another branch.';
            return detail.endsWith('.') ? detail : `${detail}.`;
        }
        if (Array.isArray(detail) && detail.length) {
            return detail.map(entry => {
                const field = Array.isArray(entry.loc) ? entry.loc[entry.loc.length - 1] : '';
                return field ? `${String(field).replace(/_/g, ' ')}: ${entry.msg}` : entry.msg;
            }).join(' ');
        }
        if (status >= 500) return 'Something went wrong on our side and the order was not placed. Please try again in a moment — your cart is saved.';
        return 'The order could not be placed. Please check your details and try again.';
    }

    function showError(message) {
        errorBox.textContent = message;
        errorBox.hidden = false;
        errorBox.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    function setSubmitting(value) {
        submitting = value;
        submitBtn.textContent = value ? 'Placing order…' : 'Place order';
        submitBtn.setAttribute('aria-disabled', String(value || blockingReasons(Cart.read()).length > 0));
        form.setAttribute('aria-busy', String(value));
    }

    form.addEventListener('submit', async event => {
        event.preventDefault();
        if (submitting) return;
        errorBox.hidden = true;

        const cart = Cart.read();
        if (cart.items.length === 0) {
            render();
            return;
        }

        const reasons = blockingReasons(cart);
        if (reasons.length) {
            blocker.hidden = false;
            blocker.textContent = reasons.join(' ');
            blocker.scrollIntoView({ behavior: 'smooth', block: 'center' });
            return;
        }

        let firstInvalid = null;
        Object.values(fields).forEach(input => {
            const message = validateField(input);
            showFieldError(input, message);
            if (message && !firstInvalid) firstInvalid = input;
        });
        if (firstInvalid) {
            firstInvalid.focus();
            return;
        }

        const body = new URLSearchParams();
        body.set('branch_id', String(cart.branch_id));
        body.set('customer_name', fields.name.value.trim());
        body.set('customer_phone', fields.phone.value.trim());
        if (fields.email.value.trim()) body.set('customer_email', fields.email.value.trim());
        body.set('fulfillment_type', fulfillment());
        if (fulfillment() === 'delivery') body.set('delivery_address', fields.address.value.trim());
        // Per-donut ingredient quantities for every recipe ingredient (0 = removed). No prices are sent.
        body.set('items_json', JSON.stringify(cart.items.map(item => ({
            product_id: item.product_id,
            quantity: item.quantity,
            ingredients: item.ingredients.map(entry => ({
                ingredient_id: entry.ingredient_id,
                quantity: entry.quantity,
            })),
        }))));

        setSubmitting(true);
        let response;
        try {
            response = await fetch(form.action, {
                method: 'POST',
                body,
                headers: { Accept: 'application/json, text/html' },
                credentials: 'same-origin',
            });
        } catch (error) {
            setSubmitting(false);
            showError('We could not reach Donnie. Check your internet connection and try again — your cart is saved.');
            return;
        }

        const receipt = response.ok && /\/orders\/(\d+)\/receipt/.exec(new URL(response.url).pathname);
        if (receipt) {
            // Only now, after the backend confirmed the order, the cart is cleared.
            completed = true;
            Cart.clearItems();
            contentView.hidden = true;
            successView.hidden = false;
            el('checkout-success-title').textContent = `Order #${receipt[1]} placed!`;
            el('checkout-success-link').href = response.url;
            successView.focus();
            setTimeout(() => location.assign(response.url), 1500);
            return;
        }

        let payload = null;
        try { payload = await response.json(); } catch (error) { /* not JSON */ }
        setSubmitting(false);
        showError(response.ok
            ? 'We could not confirm your order. Please check your profile or contact the branch before trying again.'
            : serverMessage(response.status, payload));
    });

    /* ---------- start ---------- */

    updateFulfillment();

    Branch.ready.then(async current => {
        branch = current;
        const cart = Cart.read();
        await loadDetails(cart);
        render();
    });
})();
