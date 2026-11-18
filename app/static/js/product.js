(function () {
    'use strict';

    const Cart = window.DonnieCart;
    const product = JSON.parse(document.getElementById('product-data').textContent);
    const ingredients = product.ingredients || [];

    const priceEl = document.getElementById('product-price');
    const priceEachEl = document.getElementById('product-price-each');
    const qtyEl = document.getElementById('qty-count');
    const minusBtn = document.getElementById('minus-btn');
    const plusBtn = document.getElementById('plus-btn');
    const addBtn = document.getElementById('add-to-cart-btn');
    const feedback = document.getElementById('add-feedback');
    const resetBtn = document.getElementById('reset-recipe');

    let donuts = 1;

    /* ---------- ingredient selections (per donut) ---------- */

    const round = value => Math.round(value * 100) / 100;

    /** Unit-aware step: 10 g / 10 ml, 1 piece; smaller where the allowed range is small. */
    function stepFor(ingredient) {
        const unit = String(ingredient.unit || '').trim().toLowerCase();
        if (['pcs', 'pc', 'piece', 'pieces', 'шт'].includes(unit)) return 1;
        const max = Number(ingredient.max_quantity);
        if (max >= 30) return 10;
        if (max >= 10) return 5;
        return 1;
    }

    const selections = new Map(); // ingredient id -> quantity per donut
    const startingAmounts = new Map(
        Cart.defaultIngredients(product).map(entry => [entry.ingredient_id, entry.quantity])
    );
    const missingRequired = Cart.missingRequiredIngredients(product);

    function resetSelections() {
        startingAmounts.forEach((quantity, id) => selections.set(id, quantity));
    }
    resetSelections();

    function isEditable(ingredient) {
        return ingredient.is_changeable && ingredient.is_available;
    }

    function clamp(ingredient, value) {
        const max = Number(ingredient.max_quantity);
        if (!Number.isFinite(value)) return Number(ingredient.default_quantity);
        return round(Math.min(Math.max(value, 0), max));
    }

    function setQuantity(ingredient, value) {
        if (!isEditable(ingredient)) return;
        selections.set(ingredient.id, clamp(ingredient, value));
        renderIngredient(ingredient);
        renderPrice();
        renderReset();
    }

    function rowFor(ingredient) {
        return document.querySelector(`.recipe-item[data-ingredient-id="${ingredient.id}"]`);
    }

    function renderIngredient(ingredient) {
        const row = rowFor(ingredient);
        if (!row || !isEditable(ingredient)) return;

        const value = selections.get(ingredient.id);
        const max = Number(ingredient.max_quantity);
        const input = row.querySelector('.stepper__input');
        const less = row.querySelector('[data-step="-1"]');
        const more = row.querySelector('[data-step="1"]');
        const range = row.querySelector('.recipe-range');

        input.value = Cart.formatQuantity(value);
        less.disabled = value <= 0;
        more.disabled = value >= max;
        row.classList.toggle('is-removed', value === 0);
        row.classList.toggle('is-changed', value !== Number(ingredient.default_quantity));

        const unit = ingredient.unit;
        const surcharge = Cart.ingredientSurcharge(ingredient, value);
        range.textContent = value === 0
            ? 'Removed'
            : `Recipe ${Cart.formatQuantity(ingredient.default_quantity)} ${unit} · max ${Cart.formatQuantity(max)} ${unit}`
                + (surcharge > 0 ? ` · +${Cart.formatPrice(surcharge)}` : '');
        row.classList.toggle('is-extra', surcharge > 0);
    }

    function renderReset() {
        const changed = ingredients.some(ingredient =>
            selections.get(ingredient.id) !== startingAmounts.get(ingredient.id)
        );
        resetBtn.hidden = !changed;
    }

    /* ---------- price ---------- */

    function currentSelections() {
        return ingredients.map(ingredient => ({
            ingredient_id: ingredient.id,
            quantity: selections.get(ingredient.id),
        }));
    }

    function renderPrice() {
        const unit = Cart.estimateUnitPrice(product, currentSelections());
        priceEl.textContent = Cart.formatPrice(unit * donuts);
        priceEachEl.textContent = donuts > 1 ? `${Cart.formatPrice(unit)} each × ${donuts}` : 'per donut';
    }

    /* ---------- donut quantity ---------- */

    function setDonuts(value) {
        donuts = Math.min(Math.max(1, value), Cart.MAX_LINE_QUANTITY);
        qtyEl.textContent = String(donuts);
        minusBtn.disabled = donuts <= 1;
        plusBtn.disabled = donuts >= Cart.MAX_LINE_QUANTITY;
        renderPrice();
    }

    minusBtn.addEventListener('click', () => setDonuts(donuts - 1));
    plusBtn.addEventListener('click', () => setDonuts(donuts + 1));

    /* ---------- ingredient events ---------- */

    ingredients.forEach(ingredient => {
        const row = rowFor(ingredient);
        if (!row || !isEditable(ingredient)) return;
        const step = stepFor(ingredient);

        row.querySelectorAll('[data-step]').forEach(button => {
            button.addEventListener('click', () => {
                const direction = Number(button.dataset.step);
                setQuantity(ingredient, selections.get(ingredient.id) + direction * step);
            });
        });

        const input = row.querySelector('.stepper__input');
        input.addEventListener('change', () => setQuantity(ingredient, Number(input.value)));
        input.addEventListener('keydown', event => {
            if (event.key === 'Enter') {
                event.preventDefault();
                setQuantity(ingredient, Number(input.value));
            }
        });

        renderIngredient(ingredient);
    });

    resetBtn.addEventListener('click', () => {
        resetSelections();
        ingredients.forEach(renderIngredient);
        renderPrice();
        renderReset();
    });

    /* ---------- add to cart ---------- */

    addBtn.addEventListener('click', () => {
        if (product.is_available === false || missingRequired.length) return;

        if (!product.branch) {
            window.DonnieBranch.open('Choose a branch first — the menu and prices depend on it.');
            return;
        }

        // Make sure a typed value that was not committed yet is applied.
        document.querySelectorAll('.stepper__input').forEach(input => {
            if (document.activeElement === input) input.dispatchEvent(new Event('change'));
        });

        const result = Cart.addLine({
            productId: product.id,
            quantity: donuts,
            ingredients: currentSelections(),
        });

        const { donuts: total } = Cart.totals();
        Cart.toast(
            result.capped
                ? `Line limit is ${Cart.MAX_LINE_QUANTITY} donuts — the quantity was capped.`
                : `${Cart.plural(donuts, `${product.name} donut`, `${product.name} donuts`)} added · ${total} in cart`,
            { type: result.capped ? 'error' : 'success', action: { href: '/order', label: 'Checkout' } }
        );

        feedback.hidden = false;
        addBtn.textContent = 'Added ✓';
        addBtn.classList.add('is-added');
        setTimeout(() => {
            addBtn.textContent = 'Add another';
            addBtn.classList.remove('is-added');
        }, 1400);

        document.querySelectorAll('[data-cart-count]').forEach(node => {
            node.classList.remove('is-bumped');
            void node.offsetWidth;
            node.classList.add('is-bumped');
        });
    });

    if (missingRequired.length && product.is_available !== false) {
        addBtn.disabled = true;
        addBtn.textContent = 'Unavailable here';
    }

    setDonuts(1);
    renderReset();
})();
