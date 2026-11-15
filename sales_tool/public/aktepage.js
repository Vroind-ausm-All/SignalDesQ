'use strict';
// 2.0.0-dev40 (Produktreview M07, Variante B): Die Firmenakte ist eine eigene Seite statt eines Fensters über der Liste.
// - Gleiches Element, gleiche Reiter, gleicher Schutz ungespeicherter Eingaben (formguard) – nur Ort und Darstellung ändern sich:
//   Die Akte steht im Inhaltsbereich in voller Breite, die Ansicht dahinter ist ausgeblendet, die Seite scrollt normal.
// - Adresse #/firmen/akte/ID (nav.js); „← Zurück“ schließt die Akte und führt dorthin, wo du herkamst – mit denselben Filtern.
(function () {
  let scrollBefore = 0;

  function init() {
    const modal = document.getElementById('modal'), main = document.querySelector('.main');
    if (!modal || !main || modal.dataset.page) return;
    modal.dataset.page = '1';
    const bar = document.getElementById('areaBar');
    (bar ? bar.after(modal) : main.appendChild(modal));
    modal.setAttribute('role', 'region');
    modal.removeAttribute('aria-modal');
    const close = modal.querySelector('.lf-head-actions .icon-close, .icon-close');
    if (close) { close.textContent = '← Zurück'; close.classList.add('akte-back'); close.setAttribute('aria-label', 'Akte schließen und zurück'); }

    const plainShow = window.showModal;
    window.showModal = async function (...args) {
      const wasOpen = document.body.classList.contains('akte-page');
      if (!wasOpen) scrollBefore = window.scrollY;
      const r = await plainShow.apply(this, args);
      if (!modal.classList.contains('hidden')) {
        document.body.classList.add('akte-page');
        document.body.style.overflow = '';  // Seite scrollt normal (der Dialog sperrte das Scrollen)
        if (!wasOpen) window.scrollTo({top: 0, behavior: 'instant'});
        const crumb = document.getElementById('sectionBreadcrumb');
        if (crumb) crumb.textContent = 'Firmenakte';
      }
      return r;
    };
    const plainClose = window.closeModal;
    window.closeModal = function (...args) {
      const r = plainClose.apply(this, args);
      if (modal.classList.contains('hidden') && document.body.classList.contains('akte-page')) {
        document.body.classList.remove('akte-page');
        setTimeout(() => window.scrollTo({top: scrollBefore, behavior: 'instant'}), 0);
      }
      return r;
    };
  }

  // vor nav.js laufen lassen, damit dessen Adress-Hülle außen liegt
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
  window.aktePageInit = init;
})();
