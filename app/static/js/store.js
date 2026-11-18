(function () {
    'use strict';

    const Cart = window.DonnieCart;
    const PAGE_SIZE = 9;

    const data = JSON.parse(document.getElementById('store-data').textContent);
    // The original list from the backend is never modified.
    const PRODUCTS = Object.freeze((data.products || []).map(product => Object.freeze({ ...product })));
    const productsById = new Map(PRODUCTS.map(product => [product.id, product]));
    const hasBranch = Boolean(data.selected_branch);

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
        if (sort === 'price-asc') sorted.sort((a, b) => a.price - b.price);
        if (sort === 'price-desc') sorted.sort((a, b) => b.price - a.price);
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
            pill.textContent = 'Available';
        } else if (product.is_available === false) {
            pill.classList.add('pill--no');
            pill.textContent = 'Unavailable here';
        } else {
            pill.classList.add('pill--unknown');
            pill.textContent = 'Select a branch';
        }
        return pill;
    }

    function renderCard(product) {
        const unavailable = product.is_available === false;

        const item = document.createElement('li');
        item.className = 'donut-card' + (unavailable ? ' is-unavailable' : '');

        const link = document.createElement('a');
        link.className = 'donut-product-link';
        link.href = `/product/${product.id}`;

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

        const info = document.createElement('div');
        info.className = 'donut-info';
        const name = document.createElement('h2');
        name.className = 'donut-name';
        name.textContent = product.name;
        const price = document.createElement('span');
        price.className = 'donut-price';
        price.textContent = Cart.formatPrice(product.price);
        info.append(name, price);

        link.append(imageBox, info);

        const footer = document.createElement('div');
        footer.className = 'donut-card__footer';
        footer.appendChild(availabilityPill(product));

        const details = document.createElement('a');
        details.className = 'donut-card__details';
        details.href = `/product/${product.id}`;
        details.textContent = 'Customize';
        details.setAttribute('aria-label', `Customize ${product.name}`);
        footer.appendChild(details);

        item.append(link, footer);

        if (!unavailable) {
            const add = document.createElement('button');
            add.type = 'button';
            add.className = 'add-to-basket';
            add.dataset.productId = String(product.id);
            add.setAttribute('aria-label', `Add ${product.name} to cart`);
            add.innerHTML =
                '<img src="/static/assets/img/basket-controller-back.png" class="btn-back" alt="">' +
                '<img src="/static/assets/img/to-basket-controller.png" class="btn-icon" alt="">';
            item.appendChild(add);
        }

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
        button.setAttribute('aria-label', `Page ${page} of ${totalPages}`);
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
        const range = resultCount > PAGE_SIZE ? `Showing ${start + 1}–${start + shown} of ` : '';
        const page = totalPages > 1 ? ` · Page ${state.page} of ${totalPages}` : '';
        status.textContent = `${range}${Cart.plural(resultCount, 'donut', 'donuts')}${page}`;
    }

    function renderEmpty(resultCount) {
        emptyState.hidden = resultCount > 0;
        if (resultCount > 0) return;

        if (PRODUCTS.length === 0) {
            emptyTitle.textContent = 'Nothing on the menu here yet';
            emptyText.textContent = hasBranch
                ? 'This branch has no donuts available right now. Try another branch.'
                : 'Our menu could not be loaded. Please refresh the page.';
            clearSearchBtn.hidden = true;
        } else {
            emptyTitle.textContent = 'No donuts found';
            emptyText.textContent = `Nothing matches “${state.query.trim()}”. Check the spelling or try another name.`;
            clearSearchBtn.hidden = false;
        }
    }

    /* ---------- cart summary ---------- */

    function estimatedTotal(cart) {
        let total = 0;
        let known = true;
        cart.items.forEach(item => {
            const product = productsById.get(item.product_id);
            if (!product) {
                known = false;
                return;
            }
            total += Cart.estimateUnitPrice(product, item.ingredients) * item.quantity;
        });
        return { total, known };
    }

    function renderSummary(cart) {
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
            ? `Minimum order is ${Cart.MIN_ORDER_DONUTS} donuts in total.`
            : missing > 0
                ? `Add ${Cart.plural(missing, 'more donut', 'more donuts')} to reach the ${Cart.MIN_ORDER_DONUTS}-donut minimum.`
                : 'Minimum order reached — ready for checkout!';

        const checkout = document.querySelector('[data-summary="checkout"]');
        checkout.textContent = donuts === 0 ? 'Cart is empty' : 'Go to checkout';
        checkout.classList.toggle('btn--ghost', donuts === 0);

        const mobileBar = document.getElementById('mobile-cart-bar');
        mobileBar.hidden = donuts === 0;
        document.querySelector('[data-summary="mobile-cta"]').textContent =
            missing > 0 ? `${missing} more to order` : 'Checkout →';
    }

    /* ---------- add to cart ---------- */

    async function quickAdd(button) {
        const productId = Number(button.dataset.productId);
        const product = productsById.get(productId);
        if (!product || product.is_available === false) return;

        if (!hasBranch) {
            window.DonnieBranch.open('Choose a branch first — the menu and prices depend on it.');
            return;
        }

        button.disabled = true;
        button.classList.add('is-loading');
        try {
            // Every line stores the full recipe; a quick add uses the default recipe.
            const details = await Cart.loadProduct(productId);
            if (details.is_available === false) {
                Cart.toast(`${product.name} is not available at this branch.`, { type: 'error' });
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
                    ? `You can order up to ${Cart.MAX_LINE_QUANTITY} of one donut per line.`
                    : `${product.name} added · ${Cart.plural(donuts, 'donut', 'donuts')} in cart`,
                { type: result.capped ? 'error' : 'success', action: { href: '/order', label: 'View cart' } }
            );
            bumpBadge();
            button.classList.add('is-added');
            setTimeout(() => button.classList.remove('is-added'), 900);
        } catch (error) {
            Cart.toast('Could not add this donut. Please try again.', { type: 'error' });
        } finally {
            button.disabled = false;
            button.classList.remove('is-loading');
        }
    }

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
            if (!branch) window.DonnieBranch.open('Welcome to Donnie! Pick your nearest branch to see its menu and prices.');
        });
    }
})();
