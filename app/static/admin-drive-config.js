/* ============================================================
   admin-drive-config.js
   ============================================================
   Logique partagee de la modale "Configurer dossiers" Drive.
   Inclus dans admin_connexions.html (super-admin) ET dans
   tenant_panel.html (tenant-admin).

   Permissions cote backend :
     - require_tenant_admin : super_admin ET tenant_admin OK
     - filter par _can_access_tenant : tenant_admin = son tenant uniquement

   Endpoints utilises :
     GET    /admin/drive_config/drives/{tenant_id}
     POST   /admin/drive_config/roots/{tenant_id}     (add/update)
     DELETE /admin/drive_config/roots/{root_id}
     GET    /admin/drive_config/rules/{connection_id}
     POST   /admin/drive_config/rules/{connection_id} (add/update)
     DELETE /admin/drive_config/rules/{rule_id}
     GET    /admin/drive_config/preview/{connection_id}?path=
   ============================================================ */

(function() {
  'use strict';

  // Etat global de la modale en cours
  let _ctx = {
    tenant_id: null,
    connection_id: null,
    connection_label: '',
    site_name: '',
  };

  // ===== Public API =====
  // Appelee depuis admin_connexions.html ou tenant_panel.html
  // Ouvre la modale pour une connexion drive donnee.
  window.openDriveConfigModal = async function(tenant_id, connection_id, label, site_name) {
    _ctx.tenant_id = tenant_id;
    _ctx.connection_id = connection_id;
    _ctx.connection_label = label || 'Drive';
    _ctx.site_name = site_name || '';
    document.getElementById('drive-config-title').textContent = '📂 Configuration dossiers — ' + _ctx.connection_label;
    document.getElementById('drive-config-sub').textContent =
      `Tenant : ${tenant_id} / Connection ID : ${connection_id}` +
      (site_name ? ' / Site : ' + site_name : '');
    document.getElementById('modal-drive-config').classList.add('open');
    await reloadAll();
  };

  window.closeDriveConfigModal = function() {
    document.getElementById('modal-drive-config').classList.remove('open');
    _ctx = { tenant_id: null, connection_id: null, connection_label: '', site_name: '' };
  };

  // Permettre fermeture par clic sur fond
  document.addEventListener('DOMContentLoaded', function() {
    const modal = document.getElementById('modal-drive-config');
    if (modal) {
      modal.addEventListener('click', function(e) {
        if (e.target === modal) closeDriveConfigModal();
      });
    }
    // Fermeture par Echap
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape') {
        const m = document.getElementById('modal-drive-config');
        if (m && m.classList.contains('open')) closeDriveConfigModal();
      }
    });
  });

  // ===== Internal helpers =====

  function setAlert(msg, type) {
    const el = document.getElementById('drive-config-alert');
    if (!el) return;
    el.textContent = msg;
    el.className = 'alert ' + (type === 'ok' ? 'ok' : 'err');
    setTimeout(() => { if (el) el.className = 'alert'; }, 5000);
  }

  async function reloadAll() {
    await Promise.all([reloadRoots(), reloadRules()]);
  }

  // ----- Racines -----

  async function reloadRoots() {
    const tbody = document.getElementById('drive-config-roots-tbody');
    if (!tbody) return;
    tbody.innerHTML = '<tr class="loading-row"><td colspan="6"><span class="loader"></span> Chargement...</td></tr>';
    try {
      const r = await fetch('/admin/drive_config/drives/' + _ctx.tenant_id);
      const data = await r.json();
      if (data.status !== 'ok') {
        tbody.innerHTML = '<tr><td colspan="6" style="color:var(--red)">Erreur : ' + (data.message || 'inconnue') + '</td></tr>';
        return;
      }
      // Filtrer les racines de cette connexion (par site_name si defini)
      // Note : drive_folders n a pas connection_id, on filtre par tenant
      // (c est OK : si plusieurs drives, l UI est par-card donc utilisateur
      // sait que c est le bon contexte)
      const roots = data.roots || [];
      if (roots.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="color:var(--text3);text-align:center;font-family:var(--mono);font-size:12px;padding:24px">Aucune racine. Ajoute-en une ci-dessous.</td></tr>';
        return;
      }
      tbody.innerHTML = roots.map(r => {
        // Formatage robuste du timestamp (peut etre string ISO, datetime serialise, ou null)
        let lastScan = '<span style="color:var(--text3)">—</span>';
        if (r.last_full_scan_at) {
          try {
            const d = new Date(r.last_full_scan_at);
            if (!isNaN(d.getTime())) {
              lastScan = d.toISOString().slice(0,16).replace('T', ' ');
            } else {
              lastScan = String(r.last_full_scan_at).slice(0, 19);
            }
          } catch(e) {
            lastScan = String(r.last_full_scan_at).slice(0, 19);
          }
        }
        const pathDisplay = r.folder_path
          ? '<code class="kbd">' + escapeHtml(r.folder_path) + '</code>'
          : '<i style="color:var(--text3)">(racine du site)</i>';
        const enabled = r.enabled
          ? '<span style="color:var(--green)">●</span> oui'
          : '<span style="color:var(--text3)">○</span> non';
        return `
          <tr>
            <td>${escapeHtml(r.site_name || '—')}</td>
            <td><strong>${escapeHtml(r.folder_name || '—')}</strong></td>
            <td>${pathDisplay}</td>
            <td>${enabled}</td>
            <td style="font-family:var(--mono);font-size:11px;color:var(--text3)">${lastScan}</td>
            <td style="white-space:nowrap">
              <button class="btn btn-ghost" style="padding:4px 9px;font-size:11px"
                onclick='openEditRootForm(${JSON.stringify(r)})'>Modifier</button>
              <button class="btn btn-danger" style="padding:4px 9px;font-size:11px"
                onclick='deleteRoot(${r.id})'>Retirer</button>
            </td>
          </tr>
        `;
      }).join('');
    } catch (e) {
      tbody.innerHTML = '<tr><td colspan="6" style="color:var(--red)">Erreur reseau : ' + e.message + '</td></tr>';
    }
  }

  window.openAddRootForm = function() {
    document.getElementById('drive-root-form-title').textContent = 'Ajouter une racine';
    document.getElementById('drive-root-id').value = '';
    document.getElementById('drive-root-provider').value = 'sharepoint';
    document.getElementById('drive-root-folder-name').value = '';
    document.getElementById('drive-root-site-name').value = _ctx.site_name || '';
    document.getElementById('drive-root-folder-path').value = '';
    document.getElementById('drive-root-enabled').checked = true;
    document.getElementById('drive-root-form').style.display = 'block';
  };

  window.openEditRootForm = function(root) {
    document.getElementById('drive-root-form-title').textContent = 'Modifier la racine';
    document.getElementById('drive-root-id').value = root.id || '';
    document.getElementById('drive-root-provider').value = root.provider || 'sharepoint';
    document.getElementById('drive-root-folder-name').value = root.folder_name || '';
    document.getElementById('drive-root-site-name').value = root.site_name || '';
    document.getElementById('drive-root-folder-path').value = root.folder_path || '';
    document.getElementById('drive-root-enabled').checked = !!root.enabled;
    document.getElementById('drive-root-form').style.display = 'block';
  };

  window.closeRootForm = function() {
    document.getElementById('drive-root-form').style.display = 'none';
  };

  window.saveRoot = async function() {
    const id = document.getElementById('drive-root-id').value;
    const payload = {
      provider: document.getElementById('drive-root-provider').value,
      folder_name: document.getElementById('drive-root-folder-name').value.trim(),
      site_name: document.getElementById('drive-root-site-name').value.trim(),
      folder_path: document.getElementById('drive-root-folder-path').value.trim(),
      enabled: document.getElementById('drive-root-enabled').checked,
    };
    if (id) payload.id = parseInt(id);
    if (!payload.folder_name) {
      setAlert('Libelle requis', 'err');
      return;
    }
    try {
      const r = await fetch('/admin/drive_config/roots/' + _ctx.tenant_id, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await r.json();
      if (data.status === 'ok') {
        setAlert('Racine ' + (data.action === 'created' ? 'creee' : 'mise a jour') + ' ✓', 'ok');
        closeRootForm();
        await reloadRoots();
      } else {
        setAlert('Erreur : ' + (data.message || 'inconnue'), 'err');
      }
    } catch (e) {
      setAlert('Erreur reseau : ' + e.message, 'err');
    }
  };

  window.deleteRoot = async function(root_id) {
    if (!confirm('Retirer cette racine ?\nLe contenu deja indexe ne sera PAS supprime, juste la config.')) return;
    try {
      const r = await fetch('/admin/drive_config/roots/' + root_id, { method: 'DELETE' });
      const data = await r.json();
      if (data.status === 'ok') {
        setAlert('Racine retiree ✓', 'ok');
        await reloadRoots();
      } else {
        setAlert('Erreur : ' + (data.message || 'inconnue'), 'err');
      }
    } catch (e) {
      setAlert('Erreur reseau : ' + e.message, 'err');
    }
  };

  // ----- Regles include / exclude -----

  async function reloadRules() {
    const tbody = document.getElementById('drive-config-rules-tbody');
    if (!tbody) return;
    tbody.innerHTML = '<tr class="loading-row"><td colspan="5"><span class="loader"></span> Chargement...</td></tr>';
    try {
      const r = await fetch('/admin/drive_config/rules/' + _ctx.connection_id);
      const data = await r.json();
      if (data.status !== 'ok') {
        tbody.innerHTML = '<tr><td colspan="5" style="color:var(--red)">Erreur : ' + (data.message || 'inconnue') + '</td></tr>';
        return;
      }
      const rules = data.rules || [];
      if (rules.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="color:var(--text3);text-align:center;font-family:var(--mono);font-size:12px;padding:24px">Aucune regle. Sans regle, seules les racines surveillees seront indexees.</td></tr>';
        return;
      }
      tbody.innerHTML = rules.map(r => {
        const badgeCls = r.rule_type === 'include' ? 'badge-green' : 'badge-red';
        return `
          <tr>
            <td><code class="kbd">${escapeHtml(r.folder_path)}</code></td>
            <td><span class="badge ${badgeCls}">${r.rule_type}</span></td>
            <td style="color:var(--text2);font-size:12px">${escapeHtml(r.reason || '—')}</td>
            <td style="font-family:var(--mono);font-size:11px;color:var(--text3)">${escapeHtml(r.created_by || '—')}</td>
            <td style="white-space:nowrap">
              <button class="btn btn-danger" style="padding:4px 9px;font-size:11px" onclick='deleteRule(${r.id})'>Retirer</button>
            </td>
          </tr>
        `;
      }).join('');
    } catch (e) {
      tbody.innerHTML = '<tr><td colspan="5" style="color:var(--red)">Erreur reseau : ' + e.message + '</td></tr>';
    }
  }

  window.openAddRuleForm = function() {
    document.getElementById('drive-rule-path').value = '';
    document.getElementById('drive-rule-type').value = 'exclude';
    document.getElementById('drive-rule-reason').value = '';
    document.getElementById('drive-rule-form').style.display = 'block';
  };

  window.closeRuleForm = function() {
    document.getElementById('drive-rule-form').style.display = 'none';
  };

  window.saveRule = async function() {
    const payload = {
      folder_path: document.getElementById('drive-rule-path').value.trim(),
      rule_type: document.getElementById('drive-rule-type').value,
      reason: document.getElementById('drive-rule-reason').value.trim(),
    };
    if (!payload.folder_path) {
      setAlert('Chemin requis', 'err');
      return;
    }
    try {
      const r = await fetch('/admin/drive_config/rules/' + _ctx.connection_id, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await r.json();
      if (data.status === 'ok') {
        setAlert('Regle enregistree ✓', 'ok');
        closeRuleForm();
        await reloadRules();
      } else {
        setAlert('Erreur : ' + (data.message || 'inconnue'), 'err');
      }
    } catch (e) {
      setAlert('Erreur reseau : ' + e.message, 'err');
    }
  };

  window.deleteRule = async function(rule_id) {
    if (!confirm('Retirer cette regle ?')) return;
    try {
      const r = await fetch('/admin/drive_config/rules/' + rule_id, { method: 'DELETE' });
      const data = await r.json();
      if (data.status === 'ok') {
        setAlert('Regle retiree ✓', 'ok');
        await reloadRules();
      } else {
        setAlert('Erreur : ' + (data.message || 'inconnue'), 'err');
      }
    } catch (e) {
      setAlert('Erreur reseau : ' + e.message, 'err');
    }
  };

  // ----- Test d un chemin -----

  window.openTestPathForm = function() {
    document.getElementById('drive-test-input').value = '';
    document.getElementById('drive-test-result').innerHTML = '';
    document.getElementById('drive-test-form').style.display = 'block';
  };

  window.closeTestForm = function() {
    document.getElementById('drive-test-form').style.display = 'none';
  };

  window.runTestPath = async function() {
    const path = document.getElementById('drive-test-input').value.trim();
    if (!path) { setAlert('Path requis', 'err'); return; }
    const out = document.getElementById('drive-test-result');
    out.innerHTML = '<span class="loader"></span> Test en cours...';
    try {
      const r = await fetch('/admin/drive_config/preview/' + _ctx.connection_id + '?path=' + encodeURIComponent(path));
      const data = await r.json();
      if (data.status !== 'ok') {
        out.innerHTML = '<div style="color:var(--red);font-family:var(--mono);font-size:12px">Erreur : ' + (data.message || 'inconnue') + '</div>';
        return;
      }
      const e = data.explanation;
      let html = '<div style="background:var(--bg3);border:1px solid var(--border);border-radius:6px;padding:12px;margin-top:8px;font-family:var(--mono);font-size:12px;line-height:1.7">';
      html += '<div><span style="color:var(--text3)">Path :</span> <code class="kbd">' + escapeHtml(e.path) + '</code></div>';
      html += '<div><span style="color:var(--text3)">Decision :</span> ' + (e.indexable
        ? '<span class="badge badge-green">INDEXE</span>'
        : '<span class="badge badge-red">NON INDEXE</span>') + '</div>';
      html += '<div><span style="color:var(--text3)">Sous une racine :</span> ' + (e.in_root
        ? '<span style="color:var(--green)">✓ ' + escapeHtml(e.matching_root || '') + '</span>'
        : '<span style="color:var(--red)">✗ Non</span>') + '</div>';
      if (e.winning_rule) {
        html += '<div><span style="color:var(--text3)">Regle gagnante :</span> <code class="kbd">' + escapeHtml(e.winning_rule[0]) + '</code> <span class="badge ' + (e.winning_rule[1] === 'include' ? 'badge-green' : 'badge-red') + '">' + e.winning_rule[1] + '</span></div>';
      } else {
        html += '<div style="color:var(--text3)">Aucune regle ne matche (defaut = sous racine -> indexe)</div>';
      }
      if (e.all_matching_rules && e.all_matching_rules.length > 1) {
        html += '<div style="margin-top:8px"><span style="color:var(--text3)">Toutes les regles qui matchaient :</span><ul style="margin:6px 0 0 20px;padding:0">';
        for (const r of e.all_matching_rules) {
          html += '<li><code class="kbd">' + escapeHtml(r[0]) + '</code> <span class="badge ' + (r[1] === 'include' ? 'badge-green' : 'badge-red') + '">' + r[1] + '</span></li>';
        }
        html += '</ul></div>';
      }
      html += '</div>';
      out.innerHTML = html;
    } catch (err) {
      out.innerHTML = '<div style="color:var(--red);font-family:var(--mono);font-size:12px">Erreur reseau : ' + err.message + '</div>';
    }
  };

  // ----- Utilitaire -----

  function escapeHtml(s) {
    if (s === null || s === undefined) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

})();
