/**
 * _modal_system.js — Comportements universels du système modale Raya v1
 *
 * Source unique de vérité pour les modales du système "clean" (pages user :
 * /settings et /chat).
 *
 * COMPORTEMENTS UNIVERSELS GERÉS :
 *   - Échap ferme la modale active la plus récemment ouverte
 *   - Clic sur le fond (l'overlay) ferme la modale
 *   - Bouton .modal-close ferme la modale parente
 *   - Scroll lock du <body> tant qu'une modale est ouverte
 *   - Animation : fadeIn de l'overlay + popIn de la modale (gérées en CSS)
 *
 * API PUBLIQUE :
 *   window.Modal.open(id)        → ouvre la modale par son id
 *   window.Modal.close(id)       → ferme une modale spécifique
 *   window.Modal.closeAll()      → ferme toutes les modales ouvertes
 *   window.Modal.isOpen(id)      → true si la modale est ouverte
 *   window.Modal.onOpen(id, fn)  → enregistre un callback à l'ouverture
 *   window.Modal.onClose(id, fn) → enregistre un callback à la fermeture
 *
 * USAGE MINIMAL :
 *   <div class="modal-overlay" id="myModal">...</div>
 *   <button onclick="Modal.open('myModal')">Ouvrir</button>
 *   → tout le reste (Escape, clic fond, scroll lock) est géré automatiquement
 */
(function() {
  'use strict';

  const _callbacks = { open: {}, close: {} };

  function _lockScroll() {
    if (document.querySelectorAll('.modal-overlay.open').length === 1) {
      document.body.style.overflow = 'hidden';
    }
  }

  function _unlockScroll() {
    if (document.querySelectorAll('.modal-overlay.open').length === 0) {
      document.body.style.overflow = '';
    }
  }

  function open(id) {
    const el = document.getElementById(id);
    if (!el || !el.classList.contains('modal-overlay')) {
      console.warn('[Modal] Cible introuvable ou invalide :', id);
      return false;
    }
    el.classList.add('open');
    _lockScroll();
    if (_callbacks.open[id]) {
      try { _callbacks.open[id](el); } catch(e) { console.error('[Modal] onOpen callback :', e); }
    }
    return true;
  }

  function close(id) {
    const el = document.getElementById(id);
    if (!el) return false;
    el.classList.remove('open');
    _unlockScroll();
    if (_callbacks.close[id]) {
      try { _callbacks.close[id](el); } catch(e) { console.error('[Modal] onClose callback :', e); }
    }
    return true;
  }

  function closeAll() {
    document.querySelectorAll('.modal-overlay.open').forEach(el => {
      el.classList.remove('open');
      if (_callbacks.close[el.id]) {
        try { _callbacks.close[el.id](el); } catch(e) {}
      }
    });
    _unlockScroll();
  }

  function isOpen(id) {
    const el = document.getElementById(id);
    return !!(el && el.classList.contains('open'));
  }

  function onOpen(id, fn)  { _callbacks.open[id] = fn; }
  function onClose(id, fn) { _callbacks.close[id] = fn; }

  // ─── Comportements universels ──────────────────────────────────────────

  // Échap → ferme la modale ouverte la plus récente
  document.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    const opens = document.querySelectorAll('.modal-overlay.open');
    if (opens.length === 0) return;
    // Ferme la dernière (la plus haute dans le DOM = la plus récente visuellement)
    const last = opens[opens.length - 1];
    close(last.id);
  });

  // Clic sur le fond → ferme la modale
  document.addEventListener('click', e => {
    if (e.target.classList && e.target.classList.contains('modal-overlay') && e.target.classList.contains('open')) {
      close(e.target.id);
    }
  });

  // Bouton .modal-close → ferme la modale parente
  document.addEventListener('click', e => {
    const closeBtn = e.target.closest('.modal-close');
    if (!closeBtn) return;
    const overlay = closeBtn.closest('.modal-overlay');
    if (overlay && overlay.id) {
      e.preventDefault();
      close(overlay.id);
    }
  });

  // ─── Exposition globale ────────────────────────────────────────────────
  window.Modal = { open, close, closeAll, isOpen, onOpen, onClose };
})();
