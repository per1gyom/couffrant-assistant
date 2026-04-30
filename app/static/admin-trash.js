/**
 * Admin Trash — gestion des comptes supprimes (soft-delete)
 *
 * Onglet 'Corbeille' du panel super_admin.
 * Liste les users avec deleted_at IS NOT NULL et propose deux actions :
 * - 🔄 Restaurer : remet deleted_at = NULL, redonne acces au user
 * - 🔥 Purger definitivement : hard-delete via /admin/users/{username}/confirm-permanent-deletion
 *   en mode force (super_admin uniquement, motivation 10 chars min obligatoire)
 *
 * Implemente le 30/04/2026 suite au bug repere par Guillaume :
 * apres avoir clique 'Suppr.' sur 4 users, ils restaient visibles
 * dans le panel car /tenant/users renvoyait include_deleted=True par defaut.
 */

async function loadTrash() {
  const tbody = document.getElementById('trash-tbody');
  if (!tbody) return;
  tbody.innerHTML = '<tr class="loading-row"><td colspan="7"><span class="loader"></span> Chargement...</td></tr>';
  try {
    // Endpoint /admin/users avec include_deleted=true pour avoir TOUS les users
    const r = await fetch('/admin/users?include_deleted=true');
    if (!r.ok) {
      tbody.innerHTML = `<tr><td colspan="7" style="color:var(--red)">❌ HTTP ${r.status}</td></tr>`;
      return;
    }
    const all = await r.json();
    const trashed = (all || []).filter(u => u.deleted_at);
    document.getElementById('trash-count').textContent = trashed.length
      ? `${trashed.length} compte(s) dans la corbeille`
      : '';
    if (!trashed.length) {
      tbody.innerHTML = '<tr><td colspan="7" style="color:var(--text3);text-align:center;padding:20px">✨ Corbeille vide</td></tr>';
      return;
    }
    tbody.innerHTML = trashed.map(u => {
      const purgePending = u.permanent_deletion_requested_at
        ? `<span class="badge badge-yellow" style="font-size:9px;margin-left:6px">⏳ Purge demandée</span>`
        : '';
      return `<tr style="opacity:0.85">
        <td><strong class="mono">${u.username}</strong>${purgePending}</td>
        <td style="font-size:12px;color:var(--text2)">${u.email||'—'}</td>
        <td><span class="badge badge-gray">${u.scope||'tenant_user'}</span></td>
        <td class="mono" style="font-size:11px;color:var(--text3)">${u.tenant_id||'—'}</td>
        <td class="mono" style="font-size:11px;color:var(--red)">${fmtDateShort(u.deleted_at)}</td>
        <td class="mono" style="font-size:11px;color:var(--text3)">${u.deleted_by||'—'}</td>
        <td style="display:flex;gap:6px;flex-wrap:wrap">
          <button class="btn btn-accent" style="padding:4px 9px;font-size:11px" onclick="trashRestore('${u.username}')" title="Remettre l utilisateur en service">🔄 Restaurer</button>
          <button class="btn btn-danger" style="padding:4px 9px;font-size:11px" onclick="trashPurge('${u.username}','${u.tenant_id||''}')" title="Suppression definitive (irreversible)">🔥 Purger</button>
        </td>
      </tr>`;
    }).join('');
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="7" style="color:var(--red)">❌ ${e.message}</td></tr>`;
  }
}

async function trashRestore(username) {
  const ok = await confirmAction(
    `🔄 Restaurer ${username} ?`,
    `L'utilisateur sera réactivé et pourra à nouveau se connecter.\n\nSes données (règles, conversations) ont été préservées et seront à nouveau accessibles.`,
    'Oui, restaurer', 'Annuler'
  );
  if (!ok) return;
  try {
    const r = await fetch(`/admin/users/${encodeURIComponent(username)}/restore`, { method: 'POST' });
    const d = await r.json();
    if (d.status === 'ok') {
      setAlert('trash-alert', '✅ ' + (d.message || `${username} restauré`), 'ok');
      await loadTrash();
      // Rafraichir aussi la liste principale si visible
      if (typeof loadUsers === 'function') loadUsers();
      if (typeof loadCompanies === 'function') loadCompanies();
    } else {
      setAlert('trash-alert', '❌ ' + (d.message || d.detail || 'Erreur'), 'err');
    }
  } catch (e) {
    setAlert('trash-alert', '❌ ' + e.message, 'err');
  }
}

async function trashPurge(username, tenantId) {
  // Workflow en 2 etapes : (1) demande raison, (2) confirme avec saisie textuelle
  const reason = prompt(
    `🔥 PURGE DEFINITIVE de ${username}\n\nCette action est IRREVERSIBLE :\n• Suppression de toutes les données personnelles\n• Anonymisation des données collectives en "ancien_${username}"\n• Aucun retour en arriere possible\n\nSi tu as un doute, restaure-le plutôt et purge plus tard.\n\nMotivation (10 caractères min) :`,
    ''
  );
  if (reason === null) return; // annulé
  if (!reason || reason.trim().length < 10) {
    setAlert('trash-alert', '❌ Motivation obligatoire (10 caractères min)', 'err');
    return;
  }
  const tenantInfo = tenantId ? ` (tenant: ${tenantId})` : '';
  const confirm = await confirmAction(
    `🔥 Confirmer la purge de ${username} ?`,
    `Tu es sur le point de PURGER DEFINITIVEMENT le compte ${username}${tenantInfo}.\n\nMotif : ${reason.trim()}\n\nCette action est IRREVERSIBLE.\n\nDernière chance pour annuler.`,
    '🔥 OUI, PURGER', 'Annuler'
  );
  if (!confirm) return;
  try {
    const r = await fetch(`/admin/users/${encodeURIComponent(username)}/confirm-permanent-deletion`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ force: true, reason: reason.trim() }),
    });
    const d = await r.json();
    if (d.status === 'ok') {
      setAlert('trash-alert', '🔥 ' + (d.message || `${username} purgé définitivement`), 'ok');
      await loadTrash();
      if (typeof loadUsers === 'function') loadUsers();
      if (typeof loadCompanies === 'function') loadCompanies();
    } else {
      setAlert('trash-alert', '❌ ' + (d.message || d.detail || 'Erreur'), 'err');
    }
  } catch (e) {
    setAlert('trash-alert', '❌ ' + e.message, 'err');
  }
}
