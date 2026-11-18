(function () {
    'use strict';

    const list = document.getElementById('about-branch-list');

    window.DonnieBranch.ready.then(current => {
        const branches = window.DonnieBranch.list();

        if (!branches.length) {
            const item = document.createElement('li');
            item.className = 'state-message';
            item.textContent = 'Branch information could not be loaded right now.';
            list.replaceChildren(item);
            return;
        }

        list.replaceChildren(...branches.map(branch => {
            const item = document.createElement('li');
            item.className = 'about-branch' + (current && current.id === branch.id ? ' is-current' : '');

            const city = document.createElement('h3');
            city.textContent = branch.city;
            const name = document.createElement('p');
            name.className = 'about-branch__name';
            name.textContent = branch.name;
            const address = document.createElement('p');
            address.textContent = branch.address || '';

            item.append(city, name, address);

            if (current && current.id === branch.id) {
                const badge = document.createElement('span');
                badge.className = 'pill pill--ok';
                badge.textContent = 'Your branch';
                item.appendChild(badge);
            }
            return item;
        }));
    });
})();
