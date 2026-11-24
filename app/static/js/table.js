/* Table home (after scanning a table QR code): shows the branch, the table number and the cart. */
(() => {
    const Cart = window.DonnieCart;
    const Branch = window.DonnieBranch;
    const el = id => document.getElementById(id);

    function renderCart() {
        const { donuts } = Cart.totals();
        const ukrainian = document.documentElement.lang.toLowerCase().startsWith('uk');
        el('guest-cart').textContent = donuts > 0
            ? (ukrainian
                ? `${donuts} ${donuts === 1 ? 'пончик' : donuts < 5 ? 'пончики' : 'пончиків'} у замовленні · оплатіть, коли будете готові`
                : `${Cart.plural(donuts, 'donut', 'donuts')} in your order · pay when you're ready`)
            : (ukrainian ? 'У кошику поки немає замовлення' : 'Your order is empty for now');
    }

    Branch.ready.then(branch => {
        const table = Branch.table();
        if (!branch || !table) {
            el('guest-missing').hidden = false;
            return;
        }
        el('guest-branch').textContent = branch.name;
        el('guest-address').textContent = branch.address || branch.city;
        el('guest-table').textContent = document.documentElement.lang.toLowerCase().startsWith('uk')
            ? `Стіл ${table}`
            : `Table ${table}`;
        el('guest-ready').hidden = false;
        renderCart();
        Cart.subscribe(renderCart);
    });
})();
