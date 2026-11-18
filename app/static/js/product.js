
const minusBtn = document.getElementById('minus-btn');
const plusBtn = document.getElementById('plus-btn');
const qtyDisplay = document.getElementById('qty-count');
const addToCartBtn = document.getElementById('add-to-cart-btn');
const productData = JSON.parse(
    document.getElementById('product-data').textContent
);

const productId = productData.id;

let count = 1;

plusBtn.addEventListener('click', () => {
    count++;
    qtyDisplay.textContent = count;
});

minusBtn.addEventListener('click', () => {
    if (count > 1) {
        count--;
        qtyDisplay.textContent = count;
    }
});

function getCart() {
    return JSON.parse(localStorage.getItem('cart')) || [];
}

function saveCart(cart) {
    localStorage.setItem('cart', JSON.stringify(cart));
}

function addToCart() {
    const cart = getCart();

    const existingItem = cart.find(item => {
        return item.product_id === productId;
    });

    if (existingItem) {
        existingItem.quantity += count;
    } else {
        cart.push({
            product_id: productId,
            quantity: count
        });
    }

    saveCart(cart);

    window.location.href = '/store';
}

addToCartBtn.addEventListener('click', addToCart);
