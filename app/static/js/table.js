/* Table home (after scanning a table QR code): shows the branch, the table number and the cart. */
(() => {
    const Cart = window.DonnieCart;
    const Branch = window.DonnieBranch;
    const el = id => document.getElementById(id);

    function renderCart() {
        const { donuts } = Cart.totals();
        el('guest-cart').textContent = donuts > 0
            ? `${Cart.plural(donuts, 'donut', 'donuts')} in your order · pay when you're ready`
            : 'Your order is empty for now';
    }

    Branch.ready.then(branch => {
        const table = Branch.table();
        if (!branch || !table) {
            el('guest-missing').hidden = false;
            return;
        }
        el('guest-branch').textContent = branch.name;
        el('guest-address').textContent = branch.address || branch.city;
        el('guest-table').textContent = `Table ${table}`;
        el('guest-ready').hidden = false;
        renderCart();
        Cart.subscribe(renderCart);
    });
})();
