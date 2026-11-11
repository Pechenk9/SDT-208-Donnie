const grid = document.querySelector('.donuts-grid');
const cartBadge = document.querySelector('.cart-badge');
const cartBtn = document.getElementById('cart');
const searchInput = document.querySelector('.search-bar input');
const sortBtn = document.getElementById('sort');

const cards = Array.from(document.querySelectorAll('.donut-card'));

function getCart() {
    const cart = JSON.parse(localStorage.getItem('cart')) || [];

    return cart;
}

function saveCart(cart) {
    localStorage.setItem('cart', JSON.stringify(cart));
}

function updateBadge() {
    const cart = getCart();

    const totalQuantity = cart.reduce((sum, item) => {
        return sum + item.quantity;
    }, 0);

    cartBadge.textContent = totalQuantity;

    cartBtn.onclick = () => {
        window.location.href = '/order';
    };
}

updateBadge();

function addToCart(productId) {
    const cart = getCart();

    const existingItem = cart.find(item => {
        return item.product_id === productId;
    });

    if (existingItem) {
        existingItem.quantity += 1;
    } else {
        cart.push({
            product_id: productId,
            quantity: 1
        });
    }

    saveCart(cart);
    updateBadge();
}

grid.addEventListener('click', (event) => {
    const addButton = event.target.closest('.add-to-basket');

    if (!addButton) {
        return;
    }

    const card = addButton.closest('.donut-card');

    if (!card) {
        return;
    }

    const productId = Number(card.dataset.id);

    addToCart(productId);
});