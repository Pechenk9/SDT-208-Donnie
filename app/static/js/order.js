console.log('Js loasded');

const cartList = document.getElementById('cart-list');
const finalPriceElem = document.getElementById('final-price');
const orderForm = document.getElementById('order-form');

const fulfillmentSelect = document.getElementById('fulfillment-type');
const addressGroup = document.getElementById('address-group');
const addressInput = document.getElementById('address');

const productsDataElement = document.getElementById('products-data');

const productsData = JSON.parse(productsDataElement.textContent);

const productsById = new Map(
    productsData.map(product => [Number(product.id), product])
);

console.log('Products received from backend:', productsData);
console.log('Products map:', productsById);

function getCart() {
    return JSON.parse(localStorage.getItem('cart')) || [];
}

function saveCart(cart) {
    localStorage.setItem('cart', JSON.stringify(cart));
}

function formatPrice(price) {
    return `$${Number(price).toFixed(2)}`;
}

function renderUnavailableItem(item, message) {
    const row = document.createElement('div');
    row.className = 'cart-item-row';

    const info = document.createElement('div');
    info.className = 'cart-item-info';

    const status = document.createElement('p');
    status.textContent = message;
    info.appendChild(status);

    const removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.className = 'remove-btn';
    removeBtn.dataset.id = String(item.product_id);
    removeBtn.title = 'Remove item';
    removeBtn.textContent = '×';

    row.append(info, removeBtn);
    cartList.appendChild(row);
}

function renderCart() {
    const cart = getCart();

    cartList.innerHTML = '';

    console.log('Cart from localStorage:', cart);

    if (cart.length === 0) {
        cartList.innerHTML = '<p class="empty-msg">Your basket is empty...</p>';
        finalPriceElem.textContent = '$0.00';
        return;
    }

    let totalPrice = 0;

    cart.forEach(item => {
        const productId = Number(item.product_id);
        const product = productsById.get(productId);
        const itemQuantity = Number(item.quantity);

        if (!product) {
            console.error(`Product with ID ${productId} was not found.`, {
                cartItem: item,
                availableProductIds: [...productsById.keys()]
            });

            renderUnavailableItem(item, `Product #${productId} could not be loaded. Remove it to continue.`);
            return;
        }

        if (!Number.isSafeInteger(itemQuantity) || itemQuantity <= 0) {
            console.error('Cart item has an invalid quantity.', item);
            renderUnavailableItem(item, `${product.name} has an invalid quantity. Remove it to continue.`);

            return;
        }

        const itemTotal = Number(product.base_price) * itemQuantity;
        totalPrice += itemTotal;

        const row = document.createElement('div');
        row.className = 'cart-item-row';

        const image = document.createElement('img');
        image.src = product.image_url || '';
        image.alt = product.name;
        image.className = 'cart-item-img';

        const info = document.createElement('div');
        info.className = 'cart-item-info';

        const name = document.createElement('h3');
        name.textContent = product.name;

        const unitPrice = document.createElement('p');
        unitPrice.textContent = `${formatPrice(product.base_price)} / pc`;

        info.append(name, unitPrice);

        const quantity = document.createElement('div');
        quantity.className = 'cart-item-qty';

        const minusBtn = document.createElement('button');
        minusBtn.type = 'button';
        minusBtn.className = 'quantity-btn';
        minusBtn.textContent = '−';
        minusBtn.dataset.action = 'decrease';
        minusBtn.dataset.id = productId;

        const quantityText = document.createElement('span');
        quantityText.textContent = `${itemQuantity} pcs`;

        const plusBtn = document.createElement('button');
        plusBtn.type = 'button';
        plusBtn.className = 'quantity-btn';
        plusBtn.textContent = '+';
        plusBtn.dataset.action = 'increase';
        plusBtn.dataset.id = productId;

        quantity.append(minusBtn, quantityText, plusBtn);

        const price = document.createElement('div');
        price.className = 'cart-item-price';
        price.textContent = formatPrice(itemTotal);

        const removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'remove-btn';
        removeBtn.dataset.id = productId;
        removeBtn.title = 'Remove item';
        removeBtn.textContent = '×';

        row.append(image, info, quantity, price, removeBtn);
        cartList.appendChild(row);
    });

    finalPriceElem.textContent = formatPrice(totalPrice);
}

function updateQuantity(productId, change) {
    const cart = getCart();

    const item = cart.find(item => {
        return Number(item.product_id) === productId;
    });

    if (!item) {
        return;
    }

    item.quantity = Number(item.quantity) + change;

    const updatedCart = cart.filter(item => item.quantity > 0);

    saveCart(updatedCart);
    renderCart();
}

function removeItem(productId) {
    const cart = getCart();

    const updatedCart = cart.filter(item => {
        return String(item.product_id) !== String(productId);
    });

    saveCart(updatedCart);
    renderCart();
}

cartList.addEventListener('click', event => {
    const button = event.target.closest('button');

    if (!button) {
        return;
    }

    const productId = button.dataset.id;

    if (button.classList.contains('remove-btn')) {
        removeItem(productId);
    }

    if (button.dataset.action === 'increase') {
        updateQuantity(Number(productId), 1);
    }

    if (button.dataset.action === 'decrease') {
        updateQuantity(Number(productId), -1);
    }
});

fulfillmentSelect.addEventListener('change', () => {
    const isDelivery = fulfillmentSelect.value === 'delivery';

    addressGroup.hidden = !isDelivery;
    addressInput.required = isDelivery;

    if (!isDelivery) {
        addressInput.value = '';
    }
});

function showToast(message, type = 'success') {
    let container = document.querySelector('.toast-container');

    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast ${type === 'error' ? 'error' : ''}`;
    toast.textContent = message;

    container.appendChild(toast);

    setTimeout(() => toast.classList.add('show'), 10);

    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 400);
    }, 3000);
}


orderForm.addEventListener('submit', async event => {
    event.preventDefault();

    const cart = getCart();

    if (cart.length === 0) {
        showToast('Your basket is empty!', 'error');
        return;
    }

    const phone = document.getElementById('phone').value.trim();
    const phoneDigits = phone.replace(/\D/g, '');

    if (!/^(0\d{9}|380\d{9})$/.test(phoneDigits)) {
        showToast('Please enter a valid Ukrainian phone number.', 'error');
        return;
    }

    const branchId = Number(document.getElementById('branch').value);

    if (!branchId) {
        showToast('Please select a branch.', 'error');
        return;
    }

    if (
        fulfillmentSelect.value === 'delivery' &&
        !addressInput.value.trim()
    ) {
        showToast('Please enter your delivery address.', 'error');
        return;
    }

    const orderData = {
        customer_name: document.getElementById('customer-name').value.trim(),
        customer_phone: phone,
        customer_email: document.getElementById('email').value.trim() || null,
        branch_id: branchId,
        fulfillment_type: fulfillmentSelect.value,
        delivery_address: fulfillmentSelect.value === 'delivery'
            ? addressInput.value.trim()
            : null,
        items: cart.map(item => ({
            product_id: Number(item.product_id),
            quantity: Number(item.quantity)
        }))
    };

    console.log('Sending order:', orderData);

    try {
        const response = await fetch('/orders', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(orderData)
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.detail || 'Could not create order');
        }

        console.log('Order created:', result);

        localStorage.removeItem('cart');
        renderCart();

        orderForm.reset();
        addressGroup.hidden = true;
        addressInput.required = false;

        showToast(
            `Order #${result.order_id} created successfully!`
        );

    } catch (error) {
        console.error('Order submission failed:', error);
        showToast(error.message, 'error');
    }
});


renderCart();
