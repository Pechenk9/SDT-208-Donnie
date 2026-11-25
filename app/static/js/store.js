(function () {
    'use strict';

    const Cart = window.DonnieCart;
    const PAGE_SIZE = 9;

    const data = JSON.parse(document.getElementById('store-data').textContent);
    // The original list from the backend is never modified.
    const PRODUCTS = Object.freeze((data.products || []).map(product => Object.freeze({ ...product })));
    const productsById = new Map(PRODUCTS.map(product => [product.id, product]));
    const hasBranch = Boolean(data.selected_branch);
    const ukrainian = document.documentElement.lang === 'uk';
    const productPath = id => `/${ukrainian ? 'ua' : 'en'}/product/${id}`;
    const orderPath = ukrainian ? '/ua/order' : '/en/order';

    function donutWord(count) {
        const lastTwo = count % 100;
        const last = count % 10;
        if (lastTwo >= 11 && lastTwo <= 14) return 'пончиків';
        if (last === 1) return 'пончик';
        if (last >= 2 && last <= 4) return 'пончики';
        return 'пончиків';
    }

    const text = ukrainian ? {
        available: 'Є в наявності',
        unavailable: 'Тут немає в наявності',
        selectBranch: 'Оберіть філію',
        limited: 'Обмежена серія',
        bestseller: 'Хіт продажу',
        customize: 'Налаштувати',
        add: 'Додати',
        addToCart: name => `Додати ${name} до кошика`,
        page: (number, total) => `Сторінка ${number} із ${total}`,
        nothingOnMenu: 'Поки що в меню нічого немає',
        branchEmpty: 'У цій філії зараз немає пончиків. Спробуйте обрати іншу філію.',
        loadError: 'Не вдалося завантажити меню. Оновіть сторінку.',
        noResults: 'Пончиків не знайдено',
        noMatch: query => `За запитом «${query}» нічого не знайдено. Перевірте написання або спробуйте іншу назву.`,
        showing: 'Показано',
        pageSeparator: 'із',
        minimumEmpty: count => `Мінімальне замовлення — ${count} ${donutWord(count)} загалом.`,
        minimumAdd: count => `Додайте ще ${count} ${donutWord(count)}, щоб досягти мінімуму в ${Cart.MIN_ORDER_DONUTS} пончиків.`,
        minimumReached: 'Мінімальне замовлення виконано — можна оформлювати!',
        cartEmpty: 'Кошик порожній',
        checkout: 'Перейти до оформлення',
        mobileMore: count => `Ще ${count} до замовлення`,
        mobileCheckout: 'Оформити замовлення →',
        chooseBranchFirst: 'Спочатку оберіть філію — меню та ціни залежать від неї.',
        unavailableAtBranch: name => `${name} немає в цій філії.`,
        capped: `В одному рядку можна замовити не більше ${Cart.MAX_LINE_QUANTITY} пончиків.`,
        addedToCart: (name, count) => `${name} додано · у кошику ${count} ${donutWord(count)}`,
        viewCart: 'Переглянути кошик',
        addError: 'Не вдалося додати цей пончик. Спробуйте ще раз.',
        boxUnavailable: 'Зараз у цій філії немає пончиків для асорті.',
        pickAdded: names => `Вибір Donnie додано: ${names.join(', ')}.`,
        checkoutShort: 'Оформити',
        boxError: 'Не вдалося зібрати коробку. Спробуйте ще раз.',
        welcome: 'Вітаємо в Donnie! Оберіть найближчу філію, щоб переглянути меню та ціни.',
    } : {
        available: 'Available',
        unavailable: 'Unavailable here',
        selectBranch: 'Select a branch',
        limited: 'Limited edition',
        bestseller: 'Bestseller',
        customize: 'Customize',
        add: 'Add',
        addToCart: name => `Add ${name} to cart`,
        page: (number, total) => `Page ${number} of ${total}`,
        nothingOnMenu: 'Nothing on the menu here yet',
        branchEmpty: 'This branch has no donuts available right now. Try another branch.',
        loadError: 'Our menu could not be loaded. Please refresh the page.',
        noResults: 'No donuts found',
        noMatch: query => `Nothing matches “${query}”. Check the spelling or try another name.`,
        showing: 'Showing',
        pageSeparator: 'of',
        minimumEmpty: count => `Minimum order is ${count} donuts in total.`,
        minimumAdd: count => `Add ${Cart.plural(count, 'more donut', 'more donuts')} to reach the ${Cart.MIN_ORDER_DONUTS}-donut minimum.`,
        minimumReached: 'Minimum order reached — ready for checkout!',
        cartEmpty: 'Cart is empty',
        checkout: 'Go to checkout',
        mobileMore: count => `${count} more to order`,
        mobileCheckout: 'Checkout →',
        chooseBranchFirst: 'Choose a branch first — the menu and prices depend on it.',
        unavailableAtBranch: name => `${name} is not available at this branch.`,
        capped: `You can order up to ${Cart.MAX_LINE_QUANTITY} of one donut per line.`,
        addedToCart: (name, count) => `${name} added · ${Cart.plural(count, 'donut', 'donuts')} in cart`,
        viewCart: 'View cart',
        addError: 'Could not add this donut. Please try again.',
        boxUnavailable: 'Nothing is available for a mixed box at this branch right now.',
        pickAdded: names => `Donnie's pick added: ${names.join(', ')}.`,
        checkoutShort: 'Checkout',
        boxError: 'Could not put the box together. Please try again.',
        welcome: 'Welcome to Donnie! Pick your nearest branch to see its menu and prices.',
    };

    const grid = document.getElementById('catalogue-grid');
    const searchInput = document.getElementById('catalogue-search');
    const sortSelect = document.getElementById('catalogue-sort');
    const status = document.getElementById('catalogue-status');
    const emptyState = document.getElementById('catalogue-empty');
    const emptyTitle = document.getElementById('catalogue-empty-title');
    const emptyText = document.getElementById('catalogue-empty-text');
    const clearSearchBtn = document.getElementById('catalogue-clear-search');
    const pagination = document.getElementById('catalogue-pagination');
    const pagesList = document.getElementById('catalogue-pages');
    const prevBtn = pagination.querySelector('[data-page="prev"]');
    const nextBtn = pagination.querySelector('[data-page="next"]');

    const state = {
        query: '',
        sort: 'default',
        page: 1,
    };

    /* ---------- catalogue pipeline: search → sort → paginate → render ---------- */

    function applySearch(list, query) {
        const needle = query.trim().toLocaleLowerCase();
        if (!needle) return list.slice();
        return list.filter(product => product.name.toLocaleLowerCase().includes(needle));
    }

    function applySort(list, sort) {
        const sorted = list.slice();
        // Default order: limited-edition donuts come first, the rest keep the server order.
        if (sort === 'default') sorted.sort((a, b) => Number(Boolean(b.is_limited)) - Number(Boolean(a.is_limited)));
        if (sort === 'price-asc') sorted.sort((a, b) => a.price - b.price);
        if (sort === 'price-desc') sorted.sort((a, b) => b.price - a.price);
        if (sort === 'popular') sorted.sort((a, b) => Number(Boolean(b.is_bestseller)) - Number(Boolean(a.is_bestseller)));
        return sorted; // Array.prototype.sort is stable, so equal prices keep the default order.
    }

    function update() {
        const filtered = applySearch(PRODUCTS, state.query);
        const sorted = applySort(filtered, state.sort);
        const totalPages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
        state.page = Math.min(Math.max(1, state.page), totalPages);

        const start = (state.page - 1) * PAGE_SIZE;
        const pageItems = sorted.slice(start, start + PAGE_SIZE);

        renderGrid(pageItems);
        renderPagination(sorted.length, totalPages);
        renderStatus(sorted.length, start, pageItems.length, totalPages);
        renderEmpty(sorted.length);
    }

    /* ---------- rendering ---------- */

    function availabilityPill(product) {
        const pill = document.createElement('span');
        pill.className = 'pill';
        if (product.is_available === true) {
            pill.classList.add('pill--ok');
            pill.textContent = text.available;
        } else if (product.is_available === false) {
            pill.classList.add('pill--no');
            pill.textContent = text.unavailable;
        } else {
            pill.classList.add('pill--unknown');
            pill.textContent = text.selectBranch;
        }
        return pill;
    }

    // Each donut gets its own pastel tile behind the photo (cycled by id, so it never changes).
    const TILE_COUNT = 6;

    function renderCard(product) {
        const unavailable = product.is_available === false;

        const item = document.createElement('li');
        item.className = 'donut-card' + (unavailable ? ' is-unavailable' : '') + (product.is_limited ? ' is-limited' : '');
        item.style.setProperty('--tile', `var(--tile-${(product.id % TILE_COUNT) + 1})`);

        const link = document.createElement('a');
        link.className = 'donut-product-link';
        link.href = productPath(product.id);

        const imageBox = document.createElement('div');
        imageBox.className = 'donut-img-container';
        const image = document.createElement('img');
        image.src = product.image_url || '/static/assets/icons/donnie-donut-icon.png';
        image.alt = '';
        image.loading = 'lazy';
        image.decoding = 'async';
        image.width = 220;
        image.height = 220;
        imageBox.appendChild(image);

        if (product.is_limited || product.is_bestseller) {
            const badges = document.createElement('div');
            badges.className = 'badge-row';
            if (product.is_limited) {
                const badge = document.createElement('span');
                badge.className = 'limited-badge';
                badge.textContent = text.limited;
                badges.appendChild(badge);
            }
            if (product.is_bestseller) {
                const badge = document.createElement('span');
                badge.className = 'bestseller-badge';
                badge.textContent = text.bestseller;
                badges.appendChild(badge);
            }
            imageBox.appendChild(badges);
        }

        const name = document.createElement('h2');
        name.className = 'donut-name';
        name.textContent = product.name;

        link.append(imageBox, name);
        item.appendChild(link);

        if (product.description) {
            const description = document.createElement('p');
            description.className = 'donut-desc';
            description.textContent = product.description;
            item.appendChild(description);
        }

        if (product.is_available !== true) {
            item.appendChild(availabilityPill(product));
        }

        const footer = document.createElement('div');
        footer.className = 'donut-card__footer';

        const price = document.createElement('span');
        price.className = 'donut-price';
        price.textContent = Cart.formatPrice(product.price);
        footer.appendChild(price);

        const actions = document.createElement('div');
        actions.className = 'donut-card__actions';

        const details = document.createElement('a');
        details.className = 'btn btn--ghost btn--small';
        details.href = productPath(product.id);
        details.textContent = text.customize;
        details.setAttribute('aria-label', `${text.customize} ${product.name}`);
        actions.appendChild(details);

        if (!unavailable) {
            const add = document.createElement('button');
            add.type = 'button';
            add.className = 'btn btn--small add-to-basket';
            add.dataset.productId = String(product.id);
            add.setAttribute('aria-label', text.addToCart(product.name));
            add.innerHTML =
                '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>' +
                `<span>${text.add}</span>`;
            actions.appendChild(add);
        }

        footer.appendChild(actions);
        item.appendChild(footer);

        return item;
    }

    function renderGrid(items) {
        grid.replaceChildren(...items.map(renderCard));
        grid.hidden = items.length === 0;
    }

    function pageButton(page, totalPages) {
        const li = document.createElement('li');
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'pagination__page';
        button.dataset.page = String(page);
        button.textContent = String(page);
        button.setAttribute('aria-label', text.page(page, totalPages));
        if (page === state.page) button.setAttribute('aria-current', 'page');
        li.appendChild(button);
        return li;
    }

    function renderPagination(resultCount, totalPages) {
        pagination.hidden = resultCount <= PAGE_SIZE;
        prevBtn.disabled = state.page <= 1;
        nextBtn.disabled = state.page >= totalPages;

        const pages = [];
        for (let page = 1; page <= totalPages; page += 1) pages.push(pageButton(page, totalPages));
        pagesList.replaceChildren(...pages);
    }

    function renderStatus(resultCount, start, shown, totalPages) {
        if (resultCount === 0) {
            status.textContent = '';
            return;
        }
        if (ukrainian) {
            const range = resultCount > PAGE_SIZE ? `${text.showing} ${start + 1}–${start + shown} ${text.pageSeparator} ` : '';
            const page = totalPages > 1 ? ` · ${text.page(state.page, totalPages)}` : '';
            status.textContent = `${range}${resultCount} ${donutWord(resultCount)}${page}`;
        } else {
            const range = resultCount > PAGE_SIZE ? `Showing ${start + 1}–${start + shown} of ` : '';
            const page = totalPages > 1 ? ` · Page ${state.page} of ${totalPages}` : '';
            status.textContent = `${range}${Cart.plural(resultCount, 'donut', 'donuts')}${page}`;
        }
    }

    function renderEmpty(resultCount) {
        emptyState.hidden = resultCount > 0;
        if (resultCount > 0) return;

        if (PRODUCTS.length === 0) {
            emptyTitle.textContent = text.nothingOnMenu;
            emptyText.textContent = hasBranch
                ? text.branchEmpty
                : text.loadError;
            clearSearchBtn.hidden = true;
        } else {
            emptyTitle.textContent = text.noResults;
            emptyText.textContent = text.noMatch(state.query.trim());
            clearSearchBtn.hidden = false;
        }
    }

    /* ---------- cart summary ---------- */

    // Recipes (with extra_price) of products in the cart, so customised lines are priced right.
    const cartDetails = new Map();

    function loadCartDetails(cart) {
        const wanted = new Set(cart.items.map(item => item.product_id));
        wanted.forEach(id => {
            if (cartDetails.has(id)) return;
            cartDetails.set(id, null);
            Cart.loadProduct(id)
                .then(details => {
                    cartDetails.set(id, details);
                    renderSummary(Cart.read());
                })
                .catch(() => cartDetails.delete(id));
        });
    }

    function estimatedTotal(cart) {
        let total = 0;
        let known = true;
        cart.items.forEach(item => {
            const product = cartDetails.get(item.product_id) || productsById.get(item.product_id);
            if (!product) {
                known = false;
                return;
            }
            total += Cart.estimateUnitPrice(product, item.ingredients) * item.quantity;
        });
        return { total, known };
    }

    function renderSummary(cart) {
        loadCartDetails(cart);
        const { donuts, lines } = Cart.totals(cart);
        const { total, known } = estimatedTotal(cart);
        const missing = Math.max(0, Cart.MIN_ORDER_DONUTS - donuts);

        document.querySelectorAll('[data-summary="donuts"]').forEach(node => { node.textContent = String(donuts); });
        document.querySelectorAll('[data-summary="lines"]').forEach(node => { node.textContent = String(lines); });
        document.querySelectorAll('[data-summary="total"]').forEach(node => {
            node.textContent = Cart.formatPrice(total) + (known ? '' : '+');
        });

        const minOrder = document.querySelector('[data-summary="min-order"]');
        const minText = document.querySelector('[data-summary="min-text"]');
        const minFill = document.querySelector('[data-summary="min-fill"]');
        minOrder.classList.toggle('is-met', missing === 0);
        minFill.style.width = `${Math.min(100, (donuts / Cart.MIN_ORDER_DONUTS) * 100)}%`;
        minText.textContent = donuts === 0
            ? text.minimumEmpty(Cart.MIN_ORDER_DONUTS)
            : missing > 0
                ? text.minimumAdd(missing)
                : text.minimumReached;

        const checkout = document.querySelector('[data-summary="checkout"]');
        checkout.textContent = donuts === 0 ? text.cartEmpty : text.checkout;
        checkout.classList.toggle('btn--ghost', donuts === 0);

        const mobileBar = document.getElementById('mobile-cart-bar');
        mobileBar.hidden = donuts === 0;
        document.querySelector('[data-summary="mobile-cta"]').textContent =
            missing > 0 ? text.mobileMore(missing) : text.mobileCheckout;
    }

    /* ---------- add to cart ---------- */

    async function quickAdd(button) {
        const productId = Number(button.dataset.productId);
        const product = productsById.get(productId);
        if (!product || product.is_available === false) return;

        if (!hasBranch) {
            window.DonnieBranch.open(text.chooseBranchFirst);
            return;
        }

        button.disabled = true;
        button.classList.add('is-loading');
        try {
            // Every line stores the full recipe; a quick add uses the default recipe.
            const details = await Cart.loadProduct(productId);
            if (details.is_available === false) {
                Cart.toast(text.unavailableAtBranch(product.name), { type: 'error' });
                return;
            }
            const result = Cart.addLine({
                productId,
                quantity: 1,
                ingredients: Cart.defaultIngredients(details),
            });
            const { donuts } = Cart.totals();
            Cart.toast(
                result.capped
                    ? text.capped
                    : text.addedToCart(product.name, donuts),
                { type: result.capped ? 'error' : 'success', action: { href: orderPath, label: text.viewCart } }
            );
            bumpBadge();
            button.classList.add('is-added');
            setTimeout(() => button.classList.remove('is-added'), 900);
        } catch (error) {
            Cart.toast(text.addError, { type: 'error' });
        } finally {
            button.disabled = false;
            button.classList.remove('is-loading');
        }
    }

    /* ---------- Donnie's pick: a mixed box of six ---------- */

    const tastingBtn = document.getElementById('tasting-box-btn');

    function shuffled(list) {
        const copy = list.slice();
        for (let i = copy.length - 1; i > 0; i -= 1) {
            const j = Math.floor(Math.random() * (i + 1));
            [copy[i], copy[j]] = [copy[j], copy[i]];
        }
        return copy;
    }

    async function addTastingBox() {
        if (!hasBranch) {
            window.DonnieBranch.open(ukrainian
                ? 'Спочатку оберіть філію — вибір Donnie залежить від того, що сьогодні там готують.'
                : 'Choose a branch first — Donnie\'s pick depends on what it bakes today.');
            return;
        }

        tastingBtn.disabled = true;
        tastingBtn.classList.add('is-loading');
        try {
            // Bestsellers and limited editions go in first, then a random mix of the rest.
            const available = PRODUCTS.filter(product => product.is_available === true);
            const featured = available.filter(product => product.is_bestseller || product.is_limited);
            const others = available.filter(product => !product.is_bestseller && !product.is_limited);
            const ordered = [...shuffled(featured), ...shuffled(others)];

            const settled = await Promise.allSettled(ordered.map(product => Cart.loadProduct(product.id)));
            const orderable = settled
                .map((result, index) => ({ result, product: ordered[index] }))
                .filter(({ result }) =>
                    result.status === 'fulfilled'
                    && result.value.is_available !== false
                    && Cart.missingRequiredIngredients(result.value).length === 0
                )
                .map(({ result, product }) => ({ product, details: result.value }));

            if (orderable.length === 0) {
                Cart.toast(text.boxUnavailable, { type: 'error' });
                return;
            }

            // Six different donuts when possible; with a smaller menu the picks repeat.
            const box = [];
            for (let i = 0; box.length < Cart.MIN_ORDER_DONUTS; i += 1) box.push(orderable[i % orderable.length]);
            box.forEach(({ product, details }) => {
                Cart.addLine({ productId: product.id, quantity: 1, ingredients: Cart.defaultIngredients(details) });
            });

            const names = [...new Set(box.map(({ product }) => product.name))];
            Cart.toast(text.pickAdded(names), { action: { href: orderPath, label: text.checkoutShort } });
            bumpBadge();
        } catch (error) {
            Cart.toast(text.boxError, { type: 'error' });
        } finally {
            tastingBtn.disabled = false;
            tastingBtn.classList.remove('is-loading');
        }
    }

    tastingBtn.addEventListener('click', addTastingBox);

    function bumpBadge() {
        document.querySelectorAll('[data-cart-count]').forEach(node => {
            node.classList.remove('is-bumped');
            void node.offsetWidth;
            node.classList.add('is-bumped');
        });
    }

    /* ---------- events ---------- */

    searchInput.addEventListener('input', () => {
        state.query = searchInput.value;
        state.page = 1;
        update();
    });

    sortSelect.addEventListener('change', () => {
        state.sort = sortSelect.value;
        state.page = 1;
        update();
    });

    clearSearchBtn.addEventListener('click', () => {
        searchInput.value = '';
        state.query = '';
        state.page = 1;
        update();
        searchInput.focus();
    });

    function goToPage(page) {
        state.page = page;
        update();
        document.getElementById('store-title').scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    pagination.addEventListener('click', event => {
        const button = event.target.closest('button[data-page]');
        if (!button || button.disabled) return;
        const target = button.dataset.page;
        if (target === 'prev') goToPage(state.page - 1);
        else if (target === 'next') goToPage(state.page + 1);
        else goToPage(Number(target));
    });

    grid.addEventListener('click', event => {
        const button = event.target.closest('.add-to-basket');
        if (button) quickAdd(button);
    });

    Cart.subscribe(renderSummary);

    // Restore the search text when the browser keeps form values (back navigation).
    state.query = searchInput.value;
    state.sort = sortSelect.value;
    update();
    renderSummary(Cart.read());

    if (!hasBranch) {
        // Branch sync may restore a branch from the cart and reload; only ask when there is none.
        window.DonnieBranch.ready.then(branch => {
            if (!branch) window.DonnieBranch.open(text.welcome);
        });
    }
})();
