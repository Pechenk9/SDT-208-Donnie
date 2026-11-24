(function () {
    'use strict';

    const Cart = window.DonnieCart;
    const Branch = window.DonnieBranch;
    const ukrainian = document.documentElement.lang === 'uk';

    function donutWord(count) {
        const lastTwo = count % 100;
        const last = count % 10;
        if (lastTwo >= 11 && lastTwo <= 14) return 'пончиків';
        if (last === 1) return 'пончик';
        if (last >= 2 && last <= 4) return 'пончики';
        return 'пончиків';
    }

    const text = ukrainian ? {
        unavailableLine: name => `${name} зараз немає в цій філії. Видаліть його, щоб продовжити.`,
        missingLine: 'Цього пончика більше немає в меню. Видаліть його, щоб продовжити.',
        changedRecipe: 'Рецепт цього пончика змінився після додавання до кошика. Видаліть його й додайте знову.',
        missingIngredient: name => `${name} зараз немає в цій філії. Видаліть цей пончик і додайте його ще раз без цього інгредієнта.`,
        customizationUnavailable: 'Не вдалося завантажити дані про налаштування',
        customDonutName: 'Власний пончик',
        noIngredient: name => `без ${name.toLowerCase()}`,
        originalRecipe: 'Оригінальний рецепт',
        ingredientTable: 'Інгредієнти на один пончик',
        ingredientFallback: id => `Інгредієнт №${id}`,
        removed: 'вилучено',
        donutFallback: id => `Пончик №${id}`,
        quantity: name => `Кількість пончиків ${name}`,
        oneLess: name => `На один пончик менше: ${name}`,
        oneMore: name => `На один пончик більше: ${name}`,
        each: 'за штуку',
        remove: 'Видалити',
        removeFromCart: name => `Видалити ${name} з кошика`,
        minOrder: missing => `Мінімальне замовлення — ${Cart.MIN_ORDER_DONUTS} пончиків. Додайте ще ${missing} ${donutWord(missing)}.`,
        minReached: `Мінімальне замовлення — ${Cart.MIN_ORDER_DONUTS} пончиків — виконано.`,
        branchMissing: 'Філію не обрано',
        noBranchBlock: 'Оберіть філію для замовлення.',
        minBlock: missing => `Додайте ще ${missing} ${donutWord(missing)} — мінімальне замовлення становить ${Cart.MIN_ORDER_DONUTS} пончиків.`,
        lineBlock: 'Виправте або видаліть позначені позиції кошика.',
        removedToast: 'Видалено з кошика.',
        clearedToast: 'Кошик очищено.',
        payPickup: 'Оплатити під час самовивозу',
        payCourier: 'Оплатити кур’єру',
        payTable: 'Оплатити за столиком',
        placeOrder: 'Оформити замовлення',
        placeAndPay: 'Оформити замовлення й оплатити',
        nameRequired: 'Введіть ім’я.',
        phoneRequired: 'Введіть номер телефону, щоб ми могли з вами зв’язатися.',
        phoneInvalid: 'Введіть український номер, наприклад 0671234567 або +380671234567.',
        emailInvalid: 'Введіть коректну адресу електронної пошти, наприклад you@example.com.',
        addressRequired: 'Введіть адресу доставки.',
        today: 'Сьогодні',
        scheduleDelivery: 'доставлено',
        schedulePickup: 'готове до самовивозу',
        scheduleLater: (where) => `Замовлення буде ${where} у вибраний проміжок. Передзамовлення можна зробити не раніше ніж за тиждень.`,
        scheduleNow: 'Ми почнемо готувати замовлення одразу після оформлення.',
        phoneServer: 'Перевірте номер телефону — він має бути українським.',
        branchServer: 'Обрана філія більше недоступна. Оберіть іншу філію.',
        orderError: 'Не вдалося оформити замовлення. Перевірте дані й спробуйте ще раз.',
        serverError: 'На нашому боці сталася помилка, і замовлення не оформлено. Спробуйте ще раз за мить — кошик збережено.',
        connectionError: 'Не вдалося зв’язатися з Donnie. Перевірте інтернет-з’єднання й спробуйте ще раз — кошик збережено.',
        confirmationError: 'Не вдалося підтвердити замовлення. Перевірте профіль або зверніться до філії, перш ніж повторити спробу.',
        placing: 'Оформлюємо замовлення…',
        placedForPay: number => `Замовлення №${number} оформлено. Перенаправляємо до оплати…`,
        placed: number => `Замовлення №${number} оформлено!`,
    } : {
        unavailableLine: name => `${name} is not available at this branch right now. Remove it to continue.`,
        missingLine: 'This donut is no longer on the menu. Remove it to continue.',
        changedRecipe: 'The recipe of this donut changed since you added it. Remove it and add it again.',
        missingIngredient: name => `${name} is not available at this branch right now. Remove this donut and add it again without it.`,
        customizationUnavailable: 'Customization details unavailable',
        customDonutName: 'Custom donut',
        noIngredient: name => `no ${name.toLowerCase()}`,
        originalRecipe: 'Original recipe',
        ingredientTable: 'Ingredients per donut',
        ingredientFallback: id => `Ingredient #${id}`,
        removed: 'removed',
        donutFallback: id => `Donut #${id}`,
        quantity: name => `Quantity of ${name}`,
        oneLess: name => `One less ${name}`,
        oneMore: name => `One more ${name}`,
        each: 'each',
        remove: 'Remove',
        removeFromCart: name => `Remove ${name} from cart`,
        minOrder: missing => `Minimum order is ${Cart.MIN_ORDER_DONUTS} donuts — add ${Cart.plural(missing, 'more', 'more')}.`,
        minReached: `Minimum of ${Cart.MIN_ORDER_DONUTS} donuts reached.`,
        branchMissing: 'No branch selected',
        noBranchBlock: 'Choose a branch for your order.',
        minBlock: missing => `Add ${Cart.plural(missing, 'more donut', 'more donuts')} — the minimum order is ${Cart.MIN_ORDER_DONUTS} donuts in total.`,
        lineBlock: 'Fix or remove the highlighted cart lines.',
        removedToast: 'Removed from cart.',
        clearedToast: 'Your cart is now empty.',
        payPickup: 'Pay at pickup',
        payCourier: 'Pay the courier',
        payTable: 'Pay at the table',
        placeOrder: 'Place order',
        placeAndPay: 'Place order and pay',
        nameRequired: 'Please enter your name.',
        phoneRequired: 'Please enter a phone number so we can reach you.',
        phoneInvalid: 'Enter a Ukrainian number, e.g. 0671234567 or +380671234567.',
        emailInvalid: 'Enter a valid email address, e.g. you@example.com.',
        addressRequired: 'Please enter the delivery address.',
        today: 'Today',
        scheduleDelivery: 'delivered',
        schedulePickup: 'ready for pickup',
        scheduleLater: where => `Your box will be ${where} within the chosen window. You can pre-order up to a week ahead.`,
        scheduleNow: 'We start baking right after you order.',
        phoneServer: 'Please check your phone number — it must be a Ukrainian number.',
        branchServer: 'The selected branch is no longer available. Please choose another branch.',
        orderError: 'The order could not be placed. Please check your details and try again.',
        serverError: 'Something went wrong on our side and the order was not placed. Please try again in a moment — your cart is saved.',
        connectionError: 'We could not reach Donnie. Check your internet connection and try again — your cart is saved.',
        confirmationError: 'We could not confirm your order. Please check your profile or contact the branch before trying again.',
        placing: 'Placing order…',
        placedForPay: number => `Order #${number} placed. Taking you to payment…`,
        placed: number => `Order #${number} placed!`,
    };

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
    const extrasConfig = data.extras || { schedule: [] };
    const dateSelect = el('scheduled-date');
    const slotSelect = el('time-slot');

    const details = new Map(); // product id -> prepared product data from /product/{id}
    const failed = new Set();  // product ids whose details could not be loaded
    let customDonutDetails = null;
    let customDonutFailed = false;
    let branch = null;
    let submitting = false;
    let completed = false;

    /* ---------- product details ---------- */

    async function loadDetails(cart) {
        const ids = [...new Set(cart.items
            .filter(item => !item.custom_donut)
            .map(item => item.product_id))].filter(id => !details.has(id));
        const requests = ids.map(id =>
            Cart.loadProduct(id)
                .then(product => { details.set(id, product); failed.delete(id); })
                .catch(() => { failed.add(id); })
        );
        if (cart.items.some(item => item.custom_donut) && !customDonutDetails && !customDonutFailed) {
            requests.push(
                Cart.loadCustomDonut()
                    .then(data => { customDonutDetails = data; customDonutFailed = false; })
                    .catch(() => { customDonutFailed = true; })
            );
        }
        await Promise.all(requests);
    }

    /* ---------- line validation ---------- */

    function lineProblem(item) {
        if (item.custom_donut) {
            if (!customDonutDetails) {
                return customDonutFailed ? text.customizationUnavailable : null;
            }
            const groups = customDonutDetails.groups || [];
            const chosen = new Map(item.ingredients.map(entry => [entry.ingredient_id, entry.quantity]));
            if (!chosen.size || chosen.size !== item.ingredients.length) return text.changedRecipe;
            const ingredientGroups = new Map();
            groups.forEach(group => {
                group.ingredients.forEach(ingredient => {
                    ingredientGroups.set(ingredient.id, { group, ingredient });
                });
            });
            for (const [ingredientId, amount] of chosen) {
                const match = ingredientGroups.get(ingredientId);
                if (!match || amount !== 1) return text.changedRecipe;
                if (!match.ingredient.is_available) return text.missingIngredient(match.ingredient.name);
            }
            for (const group of groups) {
                const count = group.ingredients.filter(ingredient => chosen.has(ingredient.id)).length;
                if ((group.is_mandatory && count === 0) || count > group.max_selections) {
                    return text.changedRecipe;
                }
            }
            return null;
        }

        const product = details.get(item.product_id);
        if (!product) {
            return failed.has(item.product_id)
                ? text.missingLine
                : null;
        }
        if (product.is_available === false) {
            return text.unavailableLine(product.name);
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
        if (!valid) return text.changedRecipe;

        const missing = recipe.find(ingredient => ingredient.is_available === false && chosen.get(ingredient.id) > 0);
        if (missing) {
            return text.missingIngredient(missing.name);
        }
        return null;
    }

    /* ---------- rendering ---------- */

    function customizationSummary(item, product) {
        if (item.custom_donut) {
            if (!customDonutDetails) return text.customizationUnavailable;
            const names = new Map((customDonutDetails.groups || [])
                .flatMap(group => group.ingredients)
                .map(ingredient => [ingredient.id, ingredient.name]));
            return item.ingredients
                .map(entry => names.get(entry.ingredient_id) || text.ingredientFallback(entry.ingredient_id))
                .join(' · ');
        }
        if (!product) return text.customizationUnavailable;
        const byId = new Map((product.ingredients || []).map(ingredient => [ingredient.id, ingredient]));
        const changes = [];
        item.ingredients.forEach(entry => {
            const ingredient = byId.get(entry.ingredient_id);
            if (!ingredient || entry.quantity === Number(ingredient.default_quantity)) return;
            changes.push(entry.quantity === 0
                ? text.noIngredient(ingredient.name)
                : `${ingredient.name} ${Cart.formatQuantity(entry.quantity)} ${ingredient.unit}`);
        });
        return changes.length ? changes.join(' · ') : text.originalRecipe;
    }

    function ingredientTable(item, product) {
        const wrapper = document.createElement('details');
        wrapper.className = 'line-ingredients';
        const summary = document.createElement('summary');
        summary.textContent = text.ingredientTable;
        wrapper.appendChild(summary);

        const list = document.createElement('ul');
        const ingredients = item.custom_donut
            ? (customDonutDetails && customDonutDetails.groups || []).flatMap(group => group.ingredients)
            : ((product && product.ingredients) || []);
        const byId = new Map(ingredients.map(ingredient => [ingredient.id, ingredient]));
        item.ingredients.forEach(entry => {
            const ingredient = byId.get(entry.ingredient_id);
            const li = document.createElement('li');
            const name = document.createElement('span');
            name.textContent = ingredient ? ingredient.name : text.ingredientFallback(entry.ingredient_id);
            const amount = document.createElement('span');
            amount.className = 'line-ingredients__amount';
            const unit = ingredient ? ` ${ingredient.unit || (ukrainian ? 'шт.' : 'pcs')}` : '';
            amount.textContent = entry.quantity === 0 ? text.removed : `${Cart.formatQuantity(entry.quantity)}${unit}`;
            if (ingredient && entry.quantity !== Number(ingredient.default_quantity)) li.classList.add('is-changed');
            li.append(name, amount);
            list.appendChild(li);
        });
        wrapper.appendChild(list);
        return wrapper;
    }

    function renderLine(item) {
        const product = item.custom_donut ? null : details.get(item.product_id);
        const fallback = item.custom_donut ? null : fallbackProducts.get(item.product_id);
        const name = item.custom_donut
            ? text.customDonutName
            : (product && product.name) || (fallback && fallback.name) || text.donutFallback(item.product_id);
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
        link.href = item.custom_donut
            ? `/${ukrainian ? 'ua' : 'en'}/custom-donut`
            : `/${ukrainian ? 'ua' : 'en'}/product/${item.product_id}`;
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
        stepper.setAttribute('aria-label', text.quantity(name));
        stepper.innerHTML = `
            <button type="button" class="stepper__btn" data-action="decrease" aria-label="${text.oneLess(name)}">&minus;</button>
            <output class="stepper__value" aria-live="polite">${item.quantity}</output>
            <button type="button" class="stepper__btn" data-action="increase" aria-label="${text.oneMore(name)}">+</button>`;
        stepper.querySelector('[data-action="decrease"]').disabled = item.quantity <= 1;
        stepper.querySelector('[data-action="increase"]').disabled = item.quantity >= Cart.MAX_LINE_QUANTITY;

        const price = document.createElement('p');
        price.className = 'cart-line__price';
        if (item.custom_donut && customDonutDetails) {
            const unit = Number(customDonutDetails.price);
            price.innerHTML = `<strong>${Cart.formatPrice(unit * item.quantity)}</strong><span>${Cart.formatPrice(unit)} ${text.each}</span>`;
        } else if (product) {
            const unit = Cart.estimateUnitPrice(product, item.ingredients);
            price.innerHTML = `<strong>${Cart.formatPrice(unit * item.quantity)}</strong><span>${Cart.formatPrice(unit)} ${text.each}</span>`;
        } else {
            price.innerHTML = '<strong>—</strong>';
        }

        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'link-btn link-btn--danger';
        remove.dataset.action = 'remove';
        remove.textContent = text.remove;
        remove.setAttribute('aria-label', text.removeFromCart(name));

        controls.append(stepper, price, remove);
        li.append(img, body, controls);
        return li;
    }

    function estimatedTotal(cart) {
        let total = 0;
        let complete = true;
        cart.items.forEach(item => {
            if (item.custom_donut) {
                if (!customDonutDetails) { complete = false; return; }
                total += Number(customDonutDetails.price) * item.quantity;
                return;
            }
            const product = details.get(item.product_id);
            if (!product) { complete = false; return; }
            total += Cart.estimateUnitPrice(product, item.ingredients) * item.quantity;
        });
        return { total, complete };
    }

    function paymentMethod() {
        const checked = form.querySelector('input[name="payment_method"]:checked');
        return checked ? checked.value : 'on_receipt';
    }

    function renderSummary(cart) {
        const { donuts, lines } = Cart.totals(cart);
        const { total, complete } = estimatedTotal(cart);
        const missing = Math.max(0, Cart.MIN_ORDER_DONUTS - donuts);
        const plus = complete ? '' : '+';

        el('summary-donuts').textContent = String(donuts);
        el('summary-lines').textContent = String(lines);
        el('summary-total').textContent = Cart.formatPrice(total) + plus;
        renderPaymentLabels();

        el('min-order').classList.toggle('is-met', missing === 0);
        el('min-order-fill').style.width = `${Math.min(100, (donuts / Cart.MIN_ORDER_DONUTS) * 100)}%`;
        el('min-order-text').textContent = missing > 0
            ? text.minOrder(missing)
            : text.minReached;

        el('checkout-branch-name').textContent = branch ? `${branch.name}, ${branch.city}` : text.branchMissing;
        el('checkout-branch-address').textContent = branch ? branch.address || '' : '';
    }

    function blockingReasons(cart) {
        const reasons = [];
        const { donuts } = Cart.totals(cart);
        if (!branch || cart.branch_id !== branch.id) reasons.push(text.noBranchBlock);
        if (donuts < Cart.MIN_ORDER_DONUTS) {
            reasons.push(text.minBlock(Cart.MIN_ORDER_DONUTS - donuts));
        }
        if (cart.items.some(item => lineProblem(item))) reasons.push(text.lineBlock);
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
            Cart.toast(text.removedToast);
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
            Cart.toast(text.clearedToast);
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

    // Table from a scanned QR code (only for the branch it belongs to).
    let table = null;

    function setupTable() {
        table = Branch.table ? Branch.table() : null;
        const option = el('table-option');
        option.hidden = !table;
        el('table-hint').hidden = !table;
        if (table) {
            el('table-number-label').textContent = String(table);
            option.querySelector('input').checked = true;
        } else if (option.querySelector('input').checked) {
            form.querySelector('input[name="fulfillment_type"][value="pickup"]').checked = true;
        }
        updateFulfillment();
    }

    function renderPaymentLabels() {
        const titles = { pickup: text.payPickup, delivery: text.payCourier, table: text.payTable };
        el('pay-on-receipt-title').textContent = titles[fulfillment()] || titles.pickup;
        submitBtn.dataset.label = paymentMethod() === 'online' ? text.placeAndPay : text.placeOrder;
        if (!submitting) submitBtn.textContent = submitBtn.dataset.label;
    }

    function validateField(input) {
        const value = input.value.trim();
        if (input === fields.name) {
            if (!value) return text.nameRequired;
        }
        if (input === fields.phone) {
            if (!value) return text.phoneRequired;
            const digits = value.replace(/\D/g, '');
            if (!/^(0\d{9}|380\d{9})$/.test(digits)) return text.phoneInvalid;
        }
        if (input === fields.email && value) {
            if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value)) return text.emailInvalid;
        }
        if (input === fields.address && fulfillment() === 'delivery') {
            if (!value) return text.addressRequired;
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
        // Table orders are served right away, so there is nothing to schedule.
        el('schedule-group').hidden = fulfillment() === 'table';
        renderScheduleHint();
    }

    /* ---------- pre-order day and time window ---------- */

    const dayFormat = new Intl.DateTimeFormat(ukrainian ? 'uk-UA' : 'en-GB', { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC' });

    function dayLabel(isoDate) {
        const label = dayFormat.format(new Date(`${isoDate}T00:00:00Z`));
        if (isoDate === extrasConfig.today) return `${text.today} · ${label}`;
        return label;
    }

    function scheduleMode() {
        const checked = form.querySelector('input[name="schedule_mode"]:checked');
        return checked ? checked.value : 'asap';
    }

    function fillDays() {
        dateSelect.replaceChildren(...extrasConfig.schedule.map(day => {
            const option = document.createElement('option');
            option.value = day.date;
            option.textContent = dayLabel(day.date);
            return option;
        }));
        fillSlots();
    }

    function fillSlots() {
        const day = extrasConfig.schedule.find(entry => entry.date === dateSelect.value);
        slotSelect.replaceChildren(...(day ? day.slots : []).map(slot => {
            const option = document.createElement('option');
            option.value = slot;
            option.textContent = slot.replace('-', ' – ');
            return option;
        }));
    }

    function renderScheduleHint() {
        const later = scheduleMode() === 'later';
        el('schedule-pickers').hidden = !later;
        const where = fulfillment() === 'delivery' ? text.scheduleDelivery : text.schedulePickup;
        el('schedule-hint').textContent = later
            ? text.scheduleLater(where)
            : text.scheduleNow;
    }

    form.querySelectorAll('input[name="schedule_mode"]').forEach(radio => {
        radio.addEventListener('change', renderScheduleHint);
    });
    dateSelect.addEventListener('change', fillSlots);

    if (!extrasConfig.schedule.length) {
        form.querySelector('input[name="schedule_mode"][value="later"]').closest('label').hidden = true;
    }
    fillDays();

    form.querySelectorAll('input[name="fulfillment_type"]').forEach(radio => {
        radio.addEventListener('change', () => {
            updateFulfillment();
            renderSummary(Cart.read());
            if (fulfillment() === 'delivery') addressInput.focus();
        });
    });

    form.querySelectorAll('input[name="payment_method"]').forEach(radio => {
        radio.addEventListener('change', () => renderSummary(Cart.read()));
    });

    /* ---------- submission ---------- */

    function serverMessage(status, payload) {
        const detail = payload && payload.detail;
        if (typeof detail === 'string') {
            if (ukrainian) {
                const translations = {
                    'Invalid tip': 'Некоректний розмір чайових.',
                    'Invalid payment method': 'Некоректний спосіб оплати.',
                    "Table orders can't be delivered": 'Замовлення за столиком не можна доставити.',
                    "Table orders can't be scheduled": 'Для замовлення за столиком не можна обрати час.',
                    'Invalid table number': 'Некоректний номер столика.',
                    'Invalid number of candles': 'Некоректна кількість свічок.',
                    'Postcard message is too long': 'Текст листівки задовгий.',
                    'Choose both a day and a time window': 'Оберіть день і часовий проміжок.',
                    'Invalid pre-order date': 'Некоректна дата передзамовлення.',
                    'Invalid time window': 'Некоректний часовий проміжок.',
                    'This time window is no longer available': 'Цей часовий проміжок більше недоступний.',
                    'Customer name is required': 'Вкажіть ім’я.',
                    'Customer phone is required': 'Вкажіть номер телефону.',
                    'Invalid Ukrainian phone number': text.phoneServer,
                    'Invalid email': 'Введіть коректну адресу електронної пошти.',
                    'Delivery address is required': 'Вкажіть адресу доставки.',
                    'Invalid order items': 'Некоректні дані товарів у замовленні.',
                    'Order must contain at least one item': 'Додайте до замовлення хоча б один товар.',
                    'Invalid order item': 'Некоректна позиція замовлення.',
                    'Invalid product ID': 'Некоректний товар.',
                    'Invalid product quantity': 'Некоректна кількість товару.',
                    'Invalid ingredient selections': 'Некоректний вибір інгредієнтів.',
                    'Order must contain at least six donuts': `Додайте щонайменше ${Cart.MIN_ORDER_DONUTS} пончиків загалом, щоб оформити замовлення.`,
                    'Branch not found': text.branchServer,
                    'One or more products do not exist or are inactive': 'Один або кілька товарів більше недоступні.',
                    'Invalid ingredient selection': 'Некоректний вибір інгредієнта.',
                    'Invalid ingredient ID': 'Некоректний інгредієнт.',
                    'Duplicate ingredient in order item': 'Інгредієнт указано в замовленні кілька разів.',
                    'Invalid ingredient quantity': 'Некоректна кількість інгредієнта.',
                    'Ingredient does not belong to this product': 'Цей інгредієнт не належить до обраного пончика.',
                    'Invalid custom donut selections': 'Некоректний вибір інгредієнтів.',
                    'Invalid custom donut ingredient': 'Некоректний інгредієнт.',
                    'Select ingredients for your custom donut': 'Оберіть інгредієнти для власного пончика.',
                    'Custom donut ingredients must have quantity one': 'Кількість кожного інгредієнта власного пончика має дорівнювати одиниці.',
                    'Could not create order': text.serverError,
                };
                if (translations[detail]) return translations[detail];

                let match = detail.match(/^(.+) is unavailable at this branch$/);
                if (match) return `${match[1]} зараз немає в цій філії.`;
                match = detail.match(/^(.+) exceeds its maximum quantity$/);
                if (match) return `Кількість інгредієнта «${match[1]}» перевищує дозволений максимум.`;
                match = detail.match(/^(.+) cannot be customised$/);
                if (match) return `Інгредієнт «${match[1]}» не можна змінювати.`;
                match = detail.match(/^(.+) requires a selection$/);
                if (match) return `Оберіть варіант у групі «${match[1]}».`;
                match = detail.match(/^(.+) allows at most (\d+) selections$/);
                if (match) return `У групі «${match[1]}» можна обрати не більше ${match[2]} варіантів.`;
            }
            if (detail === 'Order must contain at least six donuts') return `Add at least ${Cart.MIN_ORDER_DONUTS} donuts in total to place an order.`;
            if (detail === 'Invalid Ukrainian phone number') return 'Please check your phone number — it must be a Ukrainian number.';
            if (detail === 'Branch not found') return 'The selected branch is no longer available. Please choose another branch.';
            return detail.endsWith('.') ? detail : `${detail}.`;
        }
        if (Array.isArray(detail) && detail.length) {
            return detail.map(entry => {
                const field = Array.isArray(entry.loc) ? entry.loc[entry.loc.length - 1] : '';
                if (!ukrainian) return field ? `${String(field).replace(/_/g, ' ')}: ${entry.msg}` : entry.msg;
                const fieldNames = {
                    customer_name: 'ім’я',
                    customer_phone: 'телефон',
                    customer_email: 'електронна пошта',
                    branch_id: 'філія',
                    fulfillment_type: 'спосіб отримання',
                    items_json: 'товари',
                    payment_method: 'спосіб оплати',
                    delivery_address: 'адреса доставки',
                    scheduled_date: 'дата',
                    time_slot: 'час',
                };
                const messages = {
                    'Field required': 'Обов’язкове поле.',
                    'Input should be a valid string': 'Введіть текстове значення.',
                    'Input should be a valid integer': 'Введіть ціле число.',
                };
                const label = fieldNames[field] || String(field).replace(/_/g, ' ');
                return field ? `${label}: ${messages[entry.msg] || entry.msg}` : (messages[entry.msg] || entry.msg);
            }).join(' ');
        }
        if (status >= 500) return text.serverError;
        return text.orderError;
    }

    function showError(message) {
        errorBox.textContent = message;
        errorBox.hidden = false;
        errorBox.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    function setSubmitting(value) {
        submitting = value;
        submitBtn.textContent = value ? text.placing : (submitBtn.dataset.label || text.placeOrder);
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
        // A table order is a pickup order served at the table from the QR code.
        body.set('fulfillment_type', fulfillment() === 'table' ? 'pickup' : fulfillment());
        if (fulfillment() === 'table' && table) body.set('table_number', String(table));
        if (fulfillment() === 'delivery') body.set('delivery_address', fields.address.value.trim());
        body.set('payment_method', paymentMethod());
        if (fulfillment() !== 'table' && scheduleMode() === 'later' && dateSelect.value && slotSelect.value) {
            body.set('scheduled_date', dateSelect.value);
            body.set('time_slot', slotSelect.value);
        }
        // Prices are never sent; the server validates ingredients and recalculates every line.
        body.set('items_json', JSON.stringify(cart.items.map(item => ({
            ...(item.custom_donut ? { custom_donut: true } : { product_id: item.product_id }),
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
            showError(text.connectionError);
            return;
        }

        // The server redirects to the receipt, or to the payment page for online payment.
        const receipt = response.ok && /\/orders\/(\d+)\/(receipt|pay)$/.exec(new URL(response.url).pathname);
        if (receipt) {
            // Only now, after the backend confirmed the order, the cart is cleared.
            completed = true;
            Cart.clearItems();
            contentView.hidden = true;
            successView.hidden = false;
            el('checkout-success-title').textContent = receipt[2] === 'pay'
                ? text.placedForPay(receipt[1])
                : text.placed(receipt[1]);
            el('checkout-success-link').href = response.url;
            successView.focus();
            setTimeout(() => location.assign(response.url), 1500);
            return;
        }

        let payload = null;
        try { payload = await response.json(); } catch (error) { /* not JSON */ }
        setSubmitting(false);
        showError(response.ok
            ? text.confirmationError
            : serverMessage(response.status, payload));
    });

    /* ---------- start ---------- */

    updateFulfillment();

    Branch.ready.then(async current => {
        branch = current;
        setupTable();
        const cart = Cart.read();
        await loadDetails(cart);
        render();
    });
})();
