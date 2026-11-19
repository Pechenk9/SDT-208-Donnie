/* Home page: sections fade in as they scroll into view.
 * Without IntersectionObserver (or with reduced motion) everything is simply shown. */
(() => {
    const items = document.querySelectorAll('.reveal');
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    if (!('IntersectionObserver' in window) || reduceMotion) {
        items.forEach(item => item.classList.add('is-visible'));
        return;
    }

    document.documentElement.classList.add('has-reveal');

    const observer = new IntersectionObserver(entries => {
        entries.forEach(entry => {
            if (!entry.isIntersecting) return;
            entry.target.classList.add('is-visible');
            observer.unobserve(entry.target);
        });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.1 });

    items.forEach(item => observer.observe(item));
})();
