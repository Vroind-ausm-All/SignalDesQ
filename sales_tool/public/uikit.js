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

// 2.0.0-dev52: Eingaben beim Neuzeichnen erhalten (Fehlerbehebung Erlebnisstudien, Fachreview, Stichprobe).
// Ansichten, die jede Eingabe sofort speichern und danach neu zeichnen, ersetzen dabei alle Felder. Tippt man währenddessen in einem
// anderen Feld, war der Text weg. uiKeep(root, selector, draw) merkt sich vor dem Neuzeichnen alle geänderten, noch nicht
// gespeicherten Felder (Wert ≠ gezeichneter Wert), zeichnet neu und schreibt sie zurück – samt Fokus und Schreibmarke. Ein so
// zurückgeschriebenes Feld speichert beim Verlassen (synthetisches „change“), auch wenn danach nichts mehr getippt wurde.
// uiSerial() reiht Speichervorgänge hintereinander, damit Antworten nicht in falscher Reihenfolge neu zeichnen.
(function () {
  const keyOf = el => JSON.stringify([el.id || '', Object.entries(el.dataset).filter(([k]) => k !== 'uiDirty').sort(), el.type === 'radio' ? el.value : '']);
  const toggle = el => el.type === 'checkbox' || el.type === 'radio';
  const dirty = el => (toggle(el) ? el.checked !== el.defaultChecked
    : el.tagName === 'SELECT' ? [...el.options].some(o => o.selected !== o.defaultSelected) : el.value !== el.defaultValue);

  window.uiKeep = function (root, selector, draw) {
    const keep = new Map();
    let focusKey = null, sel = null;
    if (root) {
      root.querySelectorAll(selector).forEach(el => { if (!el.disabled && dirty(el)) keep.set(keyOf(el), toggle(el) ? el.checked : el.value); });
      const a = document.activeElement;
      if (a && root.contains(a) && a.matches(selector)) {
        focusKey = keyOf(a);
        try { sel = [a.selectionStart, a.selectionEnd]; } catch { sel = null; }
      }
    }
    const result = draw();
    if (!root) return result;
    root.querySelectorAll(selector).forEach(el => {
      const k = keyOf(el);
      if (keep.has(k) && !el.disabled) {
        if (toggle(el)) el.checked = keep.get(k); else el.value = keep.get(k);
        if (dirty(el)) el.dataset.uiDirty = '1';
      }
      if (k === focusKey) {
        el.focus({preventScroll: true});
        if (sel && sel[0] != null) { try { el.setSelectionRange(sel[0], sel[1]); } catch { /* Zahl, Auswahl */ } }
      }
    });
    return result;
  };

  window.uiSerial = function () {
    let chain = Promise.resolve();
    return fn => (chain = chain.then(fn, fn));
  };

  // Zurückgeschriebene Felder: echtes „change“ (weitergetippt) räumt die Markierung ab, sonst speichert das Verlassen
  document.addEventListener('change', e => { if (e.isTrusted && e.target?.dataset?.uiDirty) delete e.target.dataset.uiDirty; }, true);
  document.addEventListener('focusout', e => {
    const el = e.target;
    if (!el?.dataset?.uiDirty || !el.isConnected) return;
    delete el.dataset.uiDirty;
    if (dirty(el)) el.dispatchEvent(new Event('change', {bubbles: true}));
  }, true);
})();
