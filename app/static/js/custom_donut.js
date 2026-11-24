(function () {
    'use strict';

    const Cart = window.DonnieCart;
    const Branch = window.DonnieBranch;
    const ukrainian = document.documentElement.lang === 'uk';
    const apiPath = ukrainian ? '/ua/api/custom-donut' : '/en/api/custom-donut';
    const orderPath = ukrainian ? '/ua/order' : '/en/order';
    const MAX_QUANTITY = Cart.MAX_LINE_QUANTITY;
    let unitPrice = 150;

    const text = ukrainian ? {
        loading: 'Завантажуємо інгредієнти…',
        noBranch: 'Оберіть філію, щоб переглянути доступні інгредієнти.',
        loadError: 'Не вдалося завантажити інгредієнти. Спробуйте оновити сторінку.',
        unavailableGroup: 'У цій групі зараз немає доступних інгредієнтів.',
        mandatory: 'Оберіть принаймні один варіант.',
        max: count => `Можна обрати не більше ${count}.`,
        optional: count => `Необов’язково · максимум ${count}`,
        required: count => `Обов’язково · максимум ${count}`,
        unavailable: 'Немає в цій філії',
        available: 'Є в наявності',
        one: 'за пончик',
        each: 'за кожен',
        select: 'Оберіть інгредієнти перед додаванням.',
        serverError: detail => detail || 'Не вдалося перевірити вибір. Спробуйте ще раз.',
        added: count => `Додано до кошика: ${count} ${count === 1 ? 'пончик' : 'пончики'}.`,
        capped: `В одному рядку можна додати не більше ${MAX_QUANTITY} пончиків.`,
        checkout: 'Перейти до кошика',
    } : {
        loading: 'Loading ingredients…',
        noBranch: 'Choose a branch to see available ingredients.',
        loadError: 'Ingredients could not be loaded. Please refresh the page.',
        unavailableGroup: 'No ingredients in this group are available right now.',
        mandatory: 'Choose at least one option.',
        max: count => `Choose no more than ${count}.`,
        optional: count => `Optional · up to ${count}`,
        required: count => `Required · up to ${count}`,
        unavailable: 'Unavailable at this branch',
        available: 'Available',
        one: 'per donut',
        each: 'each',
        select: 'Choose ingredients before adding this donut.',
        serverError: detail => detail || 'Your selection could not be checked. Please try again.',
        added: count => `${Cart.plural(count, 'custom donut', 'custom donuts')} added to your cart.`,
        capped: `A cart line can contain up to ${MAX_QUANTITY} donuts.`,
        checkout: 'Go to cart',
    };

    const groupsNode = document.getElementById('custom-donut-groups');
    const messageNode = document.getElementById('custom-donut-message');
    const branchStatus = document.querySelector('[data-branch-status]');
    const quantityNode = document.getElementById('custom-donut-quantity');
    const totalNode = document.getElementById('custom-donut-total');
    const unitNode = document.getElementById('custom-donut-unit');
    const minusButton = document.getElementById('custom-donut-minus');
    const plusButton = document.getElementById('custom-donut-plus');
    const addButton = document.getElementById('custom-donut-add');
    const feedbackNode = document.getElementById('custom-donut-feedback');

    let catalog = [];
    let quantity = 1;
    let loaded = false;
    let loading = false;

    function setMessage(message, isError) {
        messageNode.textContent = message;
        messageNode.classList.toggle('is-error', Boolean(isError));
        messageNode.hidden = !message;
    }

    function branchLabel(branch) {
        return `${ukrainian ? 'Філія: ' : 'Branch: '}${branch.name}, ${branch.city}`;
    }

    function selectedIds() {
        return [...groupsNode.querySelectorAll('input[type="checkbox"]:checked')]
            .map(input => Number(input.value));
    }

    function groupSelection(group) {
        return groupsNode.querySelectorAll(
            `.custom-donut-group[data-group-id="${group.id}"] input[type="checkbox"]:checked`
        ).length;
    }

    function groupError(group) {
        const selected = groupSelection(group);
        if (group.is_mandatory && selected === 0) return text.mandatory;
        if (selected > group.max_selections) return text.max(group.max_selections);
        return '';
    }

    function renderValidation() {
        let valid = loaded && selectedIds().length > 0;
        catalog.forEach(group => {
            const node = groupsNode.querySelector(`[data-group-id="${group.id}"]`);
            if (!node) return;
            const error = groupError(group);
            const hasAvailable = group.ingredients.some(ingredient => ingredient.is_available);
            node.setAttribute('aria-invalid', String(Boolean(error)));
            node.querySelector('.custom-donut-group__error').textContent =
                error || (!hasAvailable ? text.unavailableGroup : '');
            if (error || (group.is_mandatory && !hasAvailable)) valid = false;
        });
        addButton.disabled = !valid;
    }

    function renderCatalog() {
        groupsNode.replaceChildren();
        catalog.forEach(group => {
            const section = document.createElement('section');
            section.className = 'custom-donut-group';
            section.dataset.groupId = String(group.id);

            const head = document.createElement('div');
            head.className = 'custom-donut-group__head';
            const title = document.createElement('h2');
            title.textContent = group.name;
            const rule = document.createElement('span');
            rule.className = 'custom-donut-group__rule';
            rule.textContent = group.is_mandatory
                ? text.required(group.max_selections)
                : text.optional(group.max_selections);
            head.append(title, rule);
            section.appendChild(head);

            const list = document.createElement('ul');
            list.className = 'custom-donut-options';
            group.ingredients.forEach(ingredient => {
                const item = document.createElement('li');
                item.className = 'custom-donut-option';

                const input = document.createElement('input');
                input.type = 'checkbox';
                input.id = `custom-ingredient-${ingredient.id}`;
                input.value = String(ingredient.id);
                input.disabled = !ingredient.is_available;
                input.setAttribute('aria-describedby', `custom-ingredient-status-${ingredient.id}`);

                const label = document.createElement('label');
                label.htmlFor = input.id;
                const name = document.createElement('span');
                name.className = 'custom-donut-option__name';
                name.textContent = ingredient.name;
                label.appendChild(name);
                if (ingredient.description) {
                    const description = document.createElement('span');
                    description.className = 'custom-donut-option__description';
                    description.textContent = ingredient.description;
                    label.appendChild(description);
                }

                const availability = document.createElement('span');
                availability.id = `custom-ingredient-status-${ingredient.id}`;
                availability.className = 'custom-donut-option__availability';
                availability.textContent = ingredient.is_available ? text.available : text.unavailable;
                availability.classList.toggle('is-unavailable', !ingredient.is_available);
                label.appendChild(availability);

                item.append(input, label);
                list.appendChild(item);
            });
            section.appendChild(list);
            const error = document.createElement('p');
            error.className = 'custom-donut-group__error';
            error.setAttribute('aria-live', 'polite');
            section.appendChild(error);
            groupsNode.appendChild(section);
        });
        renderValidation();
    }

    function setQuantity(next) {
        quantity = Math.min(Math.max(1, Math.floor(next)), MAX_QUANTITY);
        quantityNode.textContent = String(quantity);
        minusButton.disabled = quantity <= 1;
        plusButton.disabled = quantity >= MAX_QUANTITY;
        totalNode.textContent = Cart.formatPrice(unitPrice * quantity);
        unitNode.textContent = quantity > 1
            ? `${Cart.formatPrice(unitPrice)} ${text.each} × ${quantity}`
            : text.one;
    }

    async function loadCatalog() {
        if (loading || loaded) return;
        const branch = Branch.current();
        if (!branch) {
            branchStatus.textContent = text.noBranch;
            setMessage(text.noBranch, false);
            groupsNode.replaceChildren();
            addButton.disabled = true;
            return;
        }

        loading = true;
        branchStatus.textContent = branchLabel(branch);
        setMessage(text.loading, false);
        try {
            const response = await fetch(`${apiPath}/ingredients`, {
                headers: { Accept: 'application/json' },
                credentials: 'same-origin',
            });
            const payload = await response.json();
            if (!response.ok) throw new Error(payload.detail || text.loadError);
            unitPrice = Number(payload.price);
            if (!Number.isFinite(unitPrice) || unitPrice < 0) throw new Error(text.loadError);
            setQuantity(quantity);
            catalog = Array.isArray(payload.groups) ? payload.groups : [];
            loaded = true;
            setMessage('', false);
            renderCatalog();
        } catch (error) {
            setMessage(error.message || text.loadError, true);
            addButton.disabled = true;
        } finally {
            loading = false;
        }
    }

    async function addToCart() {
        if (!Branch.current()) {
            Branch.open(text.noBranch);
            return;
        }
        renderValidation();
        if (addButton.disabled) {
            setMessage(text.select, true);
            return;
        }

        addButton.disabled = true;
        const previousLabel = addButton.textContent;
        addButton.textContent = ukrainian ? 'Перевіряємо…' : 'Checking…';
        try {
            const response = await fetch(`${apiPath}/validate`, {
                method: 'POST',
                headers: {
                    Accept: 'application/json',
                    'Content-Type': 'application/json',
                },
                credentials: 'same-origin',
                body: JSON.stringify({ ingredient_ids: selectedIds() }),
            });
            const payload = await response.json();
            if (!response.ok) throw new Error(text.serverError(payload.detail));

            const result = Cart.addCustomDonut({
                quantity,
                ingredients: payload.ingredients,
            });
            const message = result.capped ? text.capped : text.added(quantity);
            feedbackNode.replaceChildren(document.createTextNode(`${message} `));
            const link = document.createElement('a');
            link.href = orderPath;
            link.textContent = text.checkout;
            feedbackNode.appendChild(link);
            feedbackNode.hidden = false;
            Cart.toast(result.capped ? text.capped : text.added(quantity), {
                type: result.capped ? 'error' : 'success',
                action: { href: orderPath, label: text.checkout },
            });
        } catch (error) {
            setMessage(error.message || text.serverError(''), true);
        } finally {
            addButton.textContent = previousLabel;
            renderValidation();
        }
    }

    groupsNode.addEventListener('change', event => {
        const input = event.target;
        if (!(input instanceof HTMLInputElement) || input.type !== 'checkbox') return;
        const group = catalog.find(entry =>
            groupsNode.querySelector(`[data-group-id="${entry.id}"]`)?.contains(input)
        );
        if (!group) return;
        if (input.checked && groupSelection(group) > group.max_selections) {
            input.checked = false;
            setMessage(text.max(group.max_selections), true);
        } else {
            setMessage('', false);
        }
        renderValidation();
    });

    minusButton.addEventListener('click', () => setQuantity(quantity - 1));
    plusButton.addEventListener('click', () => setQuantity(quantity + 1));
    addButton.addEventListener('click', addToCart);

    setQuantity(1);
    Branch.ready.then(loadCatalog).catch(() => setMessage(text.loadError, true));
})();
