/* Manager panel: printable QR codes for the branch menu and for each table.
 * Uses the qrcode-generator library (loaded from jsDelivr) to draw SVG codes. */
(() => {
    const panel = document.querySelector('.qr-panel');
    if (!panel) return;

    const base = panel.dataset.qrBase;
    const code = panel.dataset.branchCode;
    const branchName = panel.dataset.branchName;
    const form = document.getElementById('qr-form');
    const tablesInput = document.getElementById('qr-tables');
    const sheet = document.getElementById('qr-sheet');
    const errorBox = document.getElementById('qr-error');
    const ukrainian = document.documentElement.lang.toLowerCase().startsWith('uk');
    const languagePrefix = ukrainian ? '/ua' : '/en';

    function qrSvg(url) {
        const qr = window.qrcode(0, 'M'); // 0 = pick the smallest size that fits
        qr.addData(url);
        qr.make();
        return qr.createSvgTag({ cellSize: 4, margin: 2, scalable: true });
    }

    // A table tent card: dark card, "Menu & payment here", QR on white, table label, ways to pay.
    function card(label, url) {
        const figure = document.createElement('figure');
        figure.className = 'qr-card';

        const heading = document.createElement('p');
        heading.className = 'qr-card__heading';
        heading.textContent = ukrainian ? 'Меню та оплата тут' : 'Menu & payment here';

        const box = document.createElement('div');
        box.className = 'qr-card__box';
        box.innerHTML = qrSvg(url);
        const meta = document.createElement('p');
        meta.className = 'qr-card__meta';
        const codeSpan = document.createElement('span');
        codeSpan.textContent = code;
        const labelSpan = document.createElement('span');
        labelSpan.textContent = label;
        meta.append(codeSpan, labelSpan);
        box.appendChild(meta);

        const pay = document.createElement('p');
        pay.className = 'qr-card__pay';
        pay.textContent = ukrainian ? 'Картка · Apple Pay · Google Pay' : 'Card · Apple Pay · Google Pay';

        const brand = document.createElement('a');
        brand.className = 'qr-card__brand';
        brand.href = url;
        brand.textContent = 'donnie';
        brand.title = url;

        figure.append(heading, box, pay, brand);
        return figure;
    }

    function render() {
        if (typeof window.qrcode !== 'function') {
            errorBox.hidden = false;
            return;
        }
        const tables = Math.max(0, Math.min(99, Math.floor(Number(tablesInput.value) || 0)));
        const cards = [card(ukrainian ? 'Меню' : 'Menu', `${base}${languagePrefix}/qr/${encodeURIComponent(code)}`)];
        for (let table = 1; table <= tables; table += 1) {
            cards.push(card(`${ukrainian ? 'Стіл' : 'Table'} №${table}`, `${base}${languagePrefix}/qr/${encodeURIComponent(code)}?table=${table}`));
        }
        sheet.replaceChildren(...cards);
    }

    form.addEventListener('submit', event => {
        event.preventDefault();
        render();
    });

    document.getElementById('qr-print').addEventListener('click', () => {
        document.body.classList.add('is-printing-qr');
        window.print();
    });
    window.addEventListener('afterprint', () => document.body.classList.remove('is-printing-qr'));

    render();
})();
