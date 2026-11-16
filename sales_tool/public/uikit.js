'use strict';
// 2.0.0-dev50: Verhalten der Baukasten-Menüs (<details class="ui-menu">, siehe docs/UI_BAUKASTEN.md).
// - Es ist immer höchstens ein Menü offen; Klick daneben oder Escape schließt (Escape gibt den Fokus an den Menüknopf zurück).
// - Ein Knopf im Menü (Ansicht wählen, Zurücksetzen, Speichern …) schließt es nach dem Klick; Häkchen und Auswahllisten nicht.
// - Das Menü rückt nach links, wenn es rechts nicht mehr ins Fenster passt – so entsteht kein waagerechtes Scrollen.
(function () {
  const menus = () => document.querySelectorAll('details.ui-menu[open]');
  function closeAll(except) { menus().forEach(m => { if (m !== except) m.open = false; }); }

  // Menü so verschieben, dass es ganz im Fenster liegt (8 px Rand); Lage per CSSOM, die CSP erlaubt keine style-Attribute im HTML
  function place(menu) {
    const body = menu.querySelector('.ui-menu-body');
    if (!body) return;
    body.style.left = '';
    const r = body.getBoundingClientRect(), max = document.documentElement.clientWidth - 8;
    let shift = 0;
    if (r.right > max) shift = max - r.right;
    if (r.left + shift < 8) shift = 8 - r.left;
    if (shift) body.style.left = `${Math.round(shift)}px`;
  }

  document.addEventListener('toggle', e => {
    const m = e.target;
    if (!(m instanceof HTMLDetailsElement) || !m.classList.contains('ui-menu') || !m.open) return;
    closeAll(m);
    place(m);
  }, true);

  document.addEventListener('click', e => {
    const inside = e.target.closest('details.ui-menu');
    if (!inside) return closeAll(null);
    const item = e.target.closest('.ui-menu-body button');
    if (item) setTimeout(() => { inside.open = false; }, 0);  // erst nach den Klick-Handlern der Ansicht schließen
  });

  document.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    const open = [...menus()];
    if (!open.length) return;
    e.preventDefault();
    e.stopPropagation();
    open.forEach(m => { m.open = false; m.querySelector('summary')?.focus(); });
  }, true);
})();
