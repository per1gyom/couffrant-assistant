/**
 * UI Feature Flags — Phase 2 (30/04/2026 nuit)
 *
 * Gestion des features par tenant dans le panel super_admin.
 *
 * Workflow :
 *  1. Au switchTab('features') -> on charge le catalogue + la matrice tenants/features
 *  2. Affichage : un tableau (tenants en lignes × features en colonnes)
 *  3. Toggle au clic sur une cellule -> step-up 2FA + POST /admin/tenants/{id}/features/{key}
 *  4. Cache invalidé côté serveur, on recharge la matrice
 */

// ─── ÉTAT GLOBAL ──────────────────────────────────────────────────────

let _featuresCatalogue = [];     // [{feature_key, label, category, ...}]
let _tenantsCache = [];          // [{tenant_id, name}]
let _featuresMatrix = {};        // {tenant_id: {feature_key: enabled}}

// Catégories ordonnées (préserve l'ordre logique d'affichage)
const _CAT_ORDER = ['core', 'mail', 'outils', 'ai', 'ux'];
const _CAT_LABELS = {
  core: '🧱 Core',
  mail: '✉️ Mail',
  outils: '🔌 Outils tiers',
  ai: '🧠 IA',
  ux: '🎨 UX',
};

// ─── CHARGEMENT ───────────────────────────────────────────────────────

async function loadFeaturesAdmin() {
  const container = document.getElementById('features-content');
  if (!container) return;

  container.innerHTML = '<div style="padding:20px;color:var(--text3);font-size:13px"><span class="loader"></span> Chargement du catalogue + tenants...</div>';

  try {
    // Charger en parallèle catalogue et tenants
    const [catRes, tenantsRes] = await Promise.all([
      fetch('/admin/features'),
      fetch('/admin/tenants'),
    ]);

    if (!catRes.ok) throw new Error(`HTTP ${catRes.status} sur /admin/features`);
    if (!tenantsRes.ok) throw new Error(`HTTP ${tenantsRes.status} sur /admin/tenants`);

    const catData = await catRes.json();
    _featuresCatalogue = catData.features || [];
    _tenantsCache = await tenantsRes.json();

    // Charger la matrice : pour chaque tenant, fetch /admin/tenants/{id}/features
    _featuresMatrix = {};
    await Promise.all(_tenantsCache.map(async (t) => {
      try {
        const r = await fetch(`/admin/tenants/${encodeURIComponent(t.id)}/features`);
        if (r.ok) {
          const d = await r.json();
          _featuresMatrix[t.id] = d.features || {};
        } else {
          _featuresMatrix[t.id] = {};
        }
      } catch (e) {
        console.error('Load features for', t.id, ':', e);
        _featuresMatrix[t.id] = {};
      }
    }));

    renderFeaturesMatrix();
  } catch (e) {
    container.innerHTML = `<div class="alert err" style="display:block">❌ Erreur de chargement : ${e.message}</div>`;
  }
}

// ─── RENDU MATRICE ────────────────────────────────────────────────────

function renderFeaturesMatrix() {
  const container = document.getElementById('features-content');
  if (!container) return;

  // Grouper le catalogue par catégorie
  const byCategory = {};
  _featuresCatalogue.forEach((f) => {
    const cat = f.category || 'core';
    if (!byCategory[cat]) byCategory[cat] = [];
    byCategory[cat].push(f);
  });

  // Ordre des catégories
  const cats = _CAT_ORDER.filter((c) => byCategory[c]);

  let html = `
    <div style="margin-bottom:12px;padding:12px 14px;background:rgba(99,102,241,.08);border:1px solid rgba(99,102,241,.3);border-radius:8px;font-size:13px;color:var(--text2);line-height:1.6">
      <strong style="color:var(--accent)">🎛️ Système feature flags par tenant</strong><br>
      Active/désactive les fonctionnalités logicielles tenant par tenant.
      Le toggle nécessite une re-validation 2FA (5 min). Les changements sont immédiats côté serveur (cache invalidé).<br>
      <em style="color:var(--text3);font-size:12px">Pour les CONNEXIONS d'outils tiers (Outlook/Gmail/Drive), gérez les attributions par user via l'onglet Sociétés.</em>
    </div>

    <div class="actions-row">
      <button class="btn btn-ghost" onclick="loadFeaturesAdmin()">&#8635; Actualiser</button>
      <span style="font-family:var(--mono);font-size:12px;color:var(--text3)">
        ${_featuresCatalogue.length} features × ${_tenantsCache.length} tenants =
        ${_featuresCatalogue.length * _tenantsCache.length} cellules
      </span>
    </div>

    <div id="features-alert" class="alert"></div>
  `;

  // Pour chaque catégorie, on affiche un tableau
  cats.forEach((cat) => {
    const features = byCategory[cat];
    html += `
      <div class="section-title" style="margin-top:18px">${_CAT_LABELS[cat] || cat}</div>
      <div class="table-wrap">
        <table style="font-size:12px">
          <thead>
            <tr>
              <th style="text-align:left;min-width:240px">Feature</th>
              <th style="text-align:left;max-width:320px">Description</th>
    `;
    _tenantsCache.forEach((t) => {
      html += `<th style="text-align:center;min-width:90px;font-family:var(--mono)">${t.name || t.id}</th>`;
    });
    html += `</tr></thead><tbody>`;

    features.forEach((f) => {
      html += `
        <tr>
          <td><strong style="color:var(--text1)">${f.label}</strong>
              <div style="font-family:var(--mono);font-size:10px;color:var(--text3)">${f.feature_key}</div></td>
          <td style="color:var(--text3);font-size:11px;line-height:1.4">${f.description || '—'}</td>
      `;
      _tenantsCache.forEach((t) => {
        const enabled = _featuresMatrix[t.id]?.[f.feature_key] ?? f.default_enabled;
        const checked = enabled ? 'checked' : '';
        const label = enabled ? 'ON' : 'OFF';
        const color = enabled ? 'var(--green)' : 'var(--text3)';
        html += `
          <td style="text-align:center">
            <label class="ff-switch" style="display:inline-flex;align-items:center;gap:6px;cursor:pointer">
              <input type="checkbox" ${checked}
                     onchange="toggleFeature('${t.id}', '${f.feature_key}', this.checked, this)"
                     style="cursor:pointer">
              <span style="font-family:var(--mono);font-size:10px;color:${color};font-weight:600">${label}</span>
            </label>
          </td>
        `;
      });
      html += `</tr>`;
    });

    html += `</tbody></table></div>`;
  });

  container.innerHTML = html;
}

// ─── TOGGLE D'UNE FEATURE ─────────────────────────────────────────────

async function toggleFeature(tenantId, featureKey, newEnabled, checkboxEl) {
  // Sauvegarder l'état précédent pour rollback en cas d'erreur
  const prevState = !newEnabled;

  // Désactiver le checkbox pendant la requête
  checkboxEl.disabled = true;

  try {
    // Step-up 2FA obligatoire
    const stepupOk = await ensureStepUp();
    if (!stepupOk) {
      checkboxEl.checked = prevState;
      checkboxEl.disabled = false;
      setAlert('features-alert', '❌ Action annulée : 2FA non validée.', 'err');
      return;
    }

    // Appel API
    const r = await fetch(
      `/admin/tenants/${encodeURIComponent(tenantId)}/features/${encodeURIComponent(featureKey)}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: newEnabled }),
      }
    );
    const d = await r.json();

    if (!r.ok) {
      throw new Error(d.detail?.message || d.detail || d.message || `HTTP ${r.status}`);
    }

    // Maj cache local
    if (!_featuresMatrix[tenantId]) _featuresMatrix[tenantId] = {};
    _featuresMatrix[tenantId][featureKey] = newEnabled;

    // Maj label visuel à côté du checkbox
    const labelSpan = checkboxEl.parentElement.querySelector('span');
    if (labelSpan) {
      labelSpan.textContent = newEnabled ? 'ON' : 'OFF';
      labelSpan.style.color = newEnabled ? 'var(--green)' : 'var(--text3)';
    }

    setAlert(
      'features-alert',
      `✅ ${featureKey} ${newEnabled ? 'activé' : 'désactivé'} pour ${tenantId}`,
      'ok'
    );
    setTimeout(() => {
      const el = document.getElementById('features-alert');
      if (el) el.className = 'alert';
    }, 3000);

  } catch (e) {
    // Rollback du checkbox
    checkboxEl.checked = prevState;
    setAlert('features-alert', `❌ Erreur : ${e.message}`, 'err');
  } finally {
    checkboxEl.disabled = false;
  }
}

// ─── HOOK SWITCHTAB ───────────────────────────────────────────────────
// On hook le switchTab existant pour appeler loadFeaturesAdmin quand on
// active l'onglet features. Idempotent : si on switch plusieurs fois,
// on recharge à chaque fois (les données peuvent avoir changé).

(function () {
  if (typeof window.switchTab === 'function') {
    const _origSwitch = window.switchTab;
    window.switchTab = function (tabId) {
      _origSwitch(tabId);
      if (tabId === 'features') {
        loadFeaturesAdmin();
      }
    };
  }
})();

// Helper setAlert si pas déjà défini globalement
if (typeof window.setAlert !== 'function') {
  window.setAlert = function (elId, msg, type) {
    const el = document.getElementById(elId);
    if (!el) return;
    el.textContent = msg;
    el.className = 'alert ' + (type === 'err' ? 'err' : 'ok');
    el.style.display = 'block';
  };
}
