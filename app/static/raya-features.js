/**
 * RayaFeatures — helper front pour les feature flags.
 *
 * Phase 3 (30/04/2026) : à charger sur les pages user (chat, settings).
 * Cache l'état des features 60s côté client + expose API simple :
 *
 *   await RayaFeatures.load();
 *   if (RayaFeatures.enabled('memory_topics')) { ... }
 *   RayaFeatures.applyVisibility();  // masque les éléments [data-feature='X']
 *
 * Pattern HTML pour masquer un élément si une feature est OFF :
 *   <div data-feature="memory_topics">Mes sujets</div>
 *   → invisible si memory_topics est OFF pour le tenant
 */

window.RayaFeatures = (function () {
  let _features = null;          // {feature_key: enabled, ...}
  let _loadedAt = 0;
  const TTL_MS = 60 * 1000;       // 60s — doit matcher le cache backend

  /**
   * Charge les features depuis /me/features.
   * Renvoie une Promise qui resolve quand le chargement est terminé.
   * Si déjà chargé < 60s, retourne le cache.
   */
  async function load(force) {
    if (!force && _features && (Date.now() - _loadedAt < TTL_MS)) {
      return _features;
    }
    try {
      const r = await fetch('/me/features', { credentials: 'include' });
      if (!r.ok) {
        console.warn('[RayaFeatures] /me/features HTTP', r.status);
        // Fail-safe : tout activé pour ne pas casser l'UI
        _features = {};
        _loadedAt = Date.now();
        return _features;
      }
      const d = await r.json();
      _features = d.features || {};
      _loadedAt = Date.now();
      return _features;
    } catch (e) {
      console.warn('[RayaFeatures] load error:', e);
      _features = {};
      _loadedAt = Date.now();
      return _features;
    }
  }

  /**
   * Renvoie true/false pour une feature_key.
   * Si pas chargé : retourne TRUE par défaut (fail-safe — n'empêche pas
   * l'UI de fonctionner si le fetch a foiré).
   */
  function enabled(featureKey) {
    if (_features === null) {
      // Pas encore chargé → on assume true pour ne pas casser l'UI
      return true;
    }
    // Si la feature n'est pas dans la liste : on laisse l'UI affichée
    // (cas : feature inconnue côté backend, pas de panique côté front)
    if (!(featureKey in _features)) return true;
    return !!_features[featureKey];
  }

  /**
   * Applique la visibilité sur les éléments [data-feature].
   * Cache (display:none) les éléments dont la feature est OFF.
   * À appeler après load() ou quand le DOM change.
   */
  function applyVisibility() {
    if (_features === null) {
      // Pas chargé : on laisse tout visible
      return;
    }
    document.querySelectorAll('[data-feature]').forEach((el) => {
      const fk = el.getAttribute('data-feature');
      if (!fk) return;
      const isOn = enabled(fk);
      if (!isOn) {
        el.style.display = 'none';
        el.setAttribute('data-feature-hidden', 'true');
      } else if (el.getAttribute('data-feature-hidden') === 'true') {
        // Si on avait masqué et que maintenant c'est ON, on restaure
        el.style.display = '';
        el.removeAttribute('data-feature-hidden');
      }
    });
  }

  /**
   * Force un reload + applyVisibility. Pratique après un changement
   * via le panel super_admin (le user n'a pas besoin de F5).
   */
  async function refresh() {
    await load(true);
    applyVisibility();
    return _features;
  }

  /**
   * Auto-load au DOMContentLoaded.
   */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', async () => {
      await load();
      applyVisibility();
    });
  } else {
    // DOM déjà prêt → load immédiat
    load().then(applyVisibility);
  }

  return {
    load,
    enabled,
    applyVisibility,
    refresh,
    // Pour debug : expose le cache
    _debug: () => ({ features: _features, loadedAt: _loadedAt }),
  };
})();
