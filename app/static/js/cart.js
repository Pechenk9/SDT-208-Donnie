/*
 * Donnie shared cart.
 *
 * The cart lives in localStorage under CART_STORAGE_KEY and has the shape
 *   { branch_id: number | null, items: [{ line_id, product_id, quantity, ingredients: [{ ingredient_id, quantity }] }] }
 * Ingredient quantities are stored per donut. Prices are never stored here:
 * every price shown in the UI is an estimate, the backend calculates the real one.
 */
(function () {
    'use strict';

    const CART_STORAGE_KEY = 'donnie_cart_v1';
    const MIN_ORDER_DONUTS = 6;
    const MAX_LINE_QUANTITY = 99; // POST /orders accepts 1..99 per item

    const listeners = new Set();

    /* ---------- storage ---------- */

    function emptyCart(branchId = null) {
        return { branch_id: branchId, items: [] };
    }

    function isPositiveInt(value) {
        return Number.isSafeInteger(value) && value > 0;
    }

    function sanitizeIngredients(list) {
        if (!Array.isArray(list)) return [];
        return list
            .filter(entry => entry && isPositiveInt(Number(entry.ingredient_id)))
            .map(entry => ({
                ingredient_id: Number(entry.ingredient_id),
                quantity: Math.max(0, Number(entry.quantity) || 0),
            }));
    }

    function sanitize(raw) {
        if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return emptyCart();

        const branchId = Number(raw.branch_id);
        const items = Array.isArray(raw.items) ? raw.items : [];
        const seenLineIds = new Set();

        return {
            branch_id: isPositiveInt(branchId) ? branchId : null,
            items: items
                .filter(item => item && isPositiveInt(Number(item.product_id)) && isPositiveInt(Number(item.quantity)))
                .map(item => {
                    let lineId = typeof item.line_id === 'string' && item.line_id ? item.line_id : newLineId();
                    if (seenLineIds.has(lineId)) lineId = newLineId();
                    seenLineIds.add(lineId);
                    return {
                        line_id: lineId,
                        product_id: Number(item.product_id),
                        quantity: Math.min(Number(item.quantity), MAX_LINE_QUANTITY),
                        ingredients: sanitizeIngredients(item.ingredients),
                    };
                }),
        };
    }

    function read() {
        try {
            const stored = localStorage.getItem(CART_STORAGE_KEY);
            return stored ? sanitize(JSON.parse(stored)) : emptyCart();
        } catch (error) {
            return emptyCart();
        }
    }

    function write(cart) {
        const clean = sanitize(cart);
        try {
            localStorage.setItem(CART_STORAGE_KEY, JSON.stringify(clean));
        } catch (error) {
            // Storage can be full or blocked (private mode); the UI still reflects the in-memory state.
        }
        notify(clean);
        return clean;
    }

    function newLineId() {
        if (window.crypto && typeof window.crypto.randomUUID === 'function') {
            return `cart-${window.crypto.randomUUID()}`;
        }
        return `cart-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
    }

    /* ---------- change notifications ---------- */

    function notify(cart) {
        listeners.forEach(listener => listener(cart));
    }

    function subscribe(listener) {
        listeners.add(listener);
        return () => listeners.delete(listener);
    }

    // Changes made in another tab or on another page (bfcache restore, tab switch).
    window.addEventListener('storage', event => {
        if (event.key === CART_STORAGE_KEY || event.key === null) notify(read());
    });
    window.addEventListener('pageshow', event => {
        if (event.persisted) notify(read());
    });
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') notify(read());
    });

    /* ---------- mutations ---------- */

    function sameConfiguration(a, b) {
        if (a.length !== b.length) return false;
        const byId = new Map(a.map(entry => [entry.ingredient_id, entry.quantity]));
        return b.every(entry => byId.has(entry.ingredient_id) && byId.get(entry.ingredient_id) === entry.quantity);
    }

    /**
     * Adds donuts to the cart. A line with exactly the same product and ingredient
     * configuration is reused; any different configuration becomes its own line.
     */
    function addLine({ productId, quantity, ingredients }) {
        const cart = read();
        const cleanIngredients = sanitizeIngredients(ingredients);
        const amount = Math.max(1, Math.floor(Number(quantity) || 1));

        const existing = cart.items.find(item =>
            item.product_id === Number(productId) && sameConfiguration(item.ingredients, cleanIngredients)
        );

        let lineId;
        let capped = false;
        if (existing) {
            const next = existing.quantity + amount;
            capped = next > MAX_LINE_QUANTITY;
            existing.quantity = Math.min(next, MAX_LINE_QUANTITY);
            lineId = existing.line_id;
        } else {
            lineId = newLineId();
            capped = amount > MAX_LINE_QUANTITY;
            cart.items.push({
                line_id: lineId,
                product_id: Number(productId),
                quantity: Math.min(amount, MAX_LINE_QUANTITY),
                ingredients: cleanIngredients,
            });
        }

        write(cart);
        return { lineId, merged: Boolean(existing), capped };
    }

    function setLineQuantity(lineId, quantity) {
        const cart = read();
        const line = cart.items.find(item => item.line_id === lineId);
        if (!line) return cart;
        const next = Math.floor(Number(quantity) || 0);
        if (next <= 0) {
            cart.items = cart.items.filter(item => item.line_id !== lineId);
        } else {
            line.quantity = Math.min(next, MAX_LINE_QUANTITY);
        }
        return write(cart);
    }

    function removeLine(lineId) {
        const cart = read();
        cart.items = cart.items.filter(item => item.line_id !== lineId);
        return write(cart);
    }

    function clearItems() {
        const cart = read();
        return write(emptyCart(cart.branch_id));
    }

    /** Saves the branch. When clearItems is true the current lines are dropped. */
    function setBranch(branchId, { clearItems: clear = false } = {}) {
        const cart = read();
        cart.branch_id = isPositiveInt(Number(branchId)) ? Number(branchId) : null;
        if (clear) cart.items = [];
        return write(cart);
    }

    /* ---------- derived values ---------- */

    function totals(cart = read()) {
        return {
            donuts: cart.items.reduce((sum, item) => sum + item.quantity, 0),
            lines: cart.items.length,
        };
    }

    /**
     * Estimated price of one donut, mirroring POST /orders:
     * branch price (or base price) plus, for every changeable ingredient whose
     * amount is above the recipe default, its extra_price once, no matter how
     * much above. Removing or reducing an ingredient never lowers the price.
     * The backend repeats this calculation and decides the final price.
     */
    function estimateUnitPrice(product, ingredientSelections) {
        const price = Number(product && product.price);
        let cents = Number.isFinite(price) ? Math.round(price * 100) : 0;

        const recipe = (product && product.ingredients) || [];
        if (recipe.length && Array.isArray(ingredientSelections)) {
            const chosen = new Map(ingredientSelections.map(entry => [entry.ingredient_id, Number(entry.quantity)]));
            recipe.forEach(ingredient => {
                const quantity = chosen.get(ingredient.id);
                const extra = Number(ingredient.extra_price);
                if (
                    ingredient.is_changeable
                    && Number.isFinite(quantity)
                    && quantity > Number(ingredient.default_quantity)
                    && Number.isFinite(extra)
                ) {
                    cents += Math.round(extra * 100);
                }
            });
        }
        return cents / 100;
    }

    /** extra_price of an ingredient if it is charged at this amount, else 0. */
    function ingredientSurcharge(ingredient, quantity) {
        const extra = Number(ingredient.extra_price);
        return ingredient.is_changeable && quantity > Number(ingredient.default_quantity) && Number.isFinite(extra)
            ? extra
            : 0;
    }

    /* ---------- product details for display ---------- */

    const productCache = new Map();

    /**
     * Reads the prepared product data (branch price, availability, recipe) that the
     * existing /product/{id} route embeds as JSON. Used for quick-add on the Store
     * and for showing names and ingredients on Checkout.
     */
    function loadProduct(productId) {
        const id = Number(productId);
        if (!productCache.has(id)) {
            const request = fetch(`/product/${id}`, { headers: { Accept: 'text/html' }, credentials: 'same-origin' })
                .then(response => {
                    if (!response.ok) throw new Error(`Product ${id} could not be loaded (${response.status}).`);
                    return response.text();
                })
                .then(html => {
                    const doc = new DOMParser().parseFromString(html, 'text/html');
                    const node = doc.getElementById('product-data');
                    if (!node) throw new Error(`Product ${id} has no data.`);
                    return JSON.parse(node.textContent);
                })
                .catch(error => {
                    productCache.delete(id);
                    throw error;
                });
            productCache.set(id, request);
        }
        return productCache.get(id);
    }

    /**
     * Starting amounts for a new line. A changeable ingredient that the branch
     * does not have starts at 0, because the backend rejects any amount of an
     * unavailable ingredient.
     */
    function defaultIngredients(product) {
        return (product.ingredients || []).map(ingredient => ({
            ingredient_id: ingredient.id,
            quantity: ingredient.is_changeable && ingredient.is_available === false
                ? 0
                : Number(ingredient.default_quantity),
        }));
    }

    /** Ingredients the recipe cannot do without but the branch does not have. */
    function missingRequiredIngredients(product) {
        return (product.ingredients || []).filter(ingredient =>
            ingredient.is_available === false
            && !ingredient.is_changeable
            && Number(ingredient.default_quantity) > 0
        );
    }

    /* ---------- small shared UI helpers ---------- */

    function formatPrice(value) {
        return `$${(Number(value) || 0).toFixed(2)}`;
    }

    function formatQuantity(value) {
        const number = Number(value) || 0;
        return Number.isInteger(number) ? String(number) : String(Number(number.toFixed(2)));
    }

    function plural(count, one, many) {
        return `${count} ${count === 1 ? one : many}`;
    }

    function toast(message, { type = 'success', action } = {}) {
        let region = document.getElementById('toast-region');
        if (!region) {
            region = document.createElement('div');
            region.id = 'toast-region';
            region.className = 'toast-region';
            region.setAttribute('role', 'status');
            region.setAttribute('aria-live', 'polite');
            document.body.appendChild(region);
        }

        const item = document.createElement('div');
        item.className = `toast toast--${type}`;
        const text = document.createElement('span');
        text.textContent = message;
        item.appendChild(text);

        if (action) {
            const link = document.createElement('a');
            link.href = action.href;
            link.textContent = action.label;
            link.className = 'toast__action';
            item.appendChild(link);
        }

        region.appendChild(item);
        requestAnimationFrame(() => item.classList.add('is-visible'));
        setTimeout(() => {
            item.classList.remove('is-visible');
            setTimeout(() => item.remove(), 300);
        }, 4000);
    }

    /* ---------- shared header badge ---------- */

    function renderHeaderBadge(cart) {
        const { donuts } = totals(cart);
        document.querySelectorAll('[data-cart-count]').forEach(node => {
            node.textContent = String(donuts);
            node.hidden = donuts === 0;
        });
        document.querySelectorAll('[data-cart-link]').forEach(link => {
            link.setAttribute('aria-label', `Cart, ${plural(donuts, 'donut', 'donuts')}`);
        });
    }

    subscribe(renderHeaderBadge);
    document.addEventListener('DOMContentLoaded', () => renderHeaderBadge(read()));

    window.DonnieCart = {
        CART_STORAGE_KEY,
        MIN_ORDER_DONUTS,
        MAX_LINE_QUANTITY,
        read,
        write,
        subscribe,
        addLine,
        setLineQuantity,
        removeLine,
        clearItems,
        setBranch,
        totals,
        estimateUnitPrice,
        ingredientSurcharge,
        missingRequiredIngredients,
        loadProduct,
        defaultIngredients,
        formatPrice,
        formatQuantity,
        plural,
        toast,
    };
})();
