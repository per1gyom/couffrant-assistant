/**
 * Admin 2FA Management — gestion 2FA/PIN/devices d autres users
 *
 * LOT 6 du chantier 2FA (30/04/2026) : permet au super_admin de
 * reinitialiser la 2FA d un user qui a perdu son telephone.
 *
 * 3 actions :
 *   - reset-2fa             : reset complet (TOTP + recovery + PIN + devices)
 *   - reset-pin             : reset SEUL le PIN
 *   - reset-trusted-devices : vide les devices trusted (force re-2FA)
 */

async function open2FAModal(username, tenantId) {
  // Charger l etat 2FA du user
  let state;
  try {
    const r = await fetch(`/admin/users/${encodeURIComponent(username)}/2fa-status`);
    if (!r.ok) {
      alert(`Erreur HTTP ${r.status} : impossible de charger l etat 2FA de ${username}`);
      return;
    }
    state = await r.json();
  } catch (e) {
    alert('Erreur reseau : ' + e.message);
    return;
  }

  // Construire le contenu du modal
  const content = `
    <div style="padding:18px;max-width:520px">
      <h3 style="margin:0 0 12px 0;font-family:var(--mono)">🔐 Gerer la 2FA de ${username}</h3>
      <div style="margin-bottom:14px;padding:10px;background:rgba(99,102,241,.08);border-radius:8px;font-size:12px;line-height:1.6">
        <strong>Etat actuel :</strong><br>
        ${state.totp_enabled ? '✅' : '❌'} 2FA Authenticator ${state.totp_enabled ? 'active' : 'non configuree'}
          ${state.totp_enabled_at ? `(depuis ${new Date(state.totp_enabled_at).toLocaleDateString('fr-FR')})` : ''}<br>
        ${state.pin_configured ? '✅' : '❌'} PIN admin ${state.pin_configured ? 'configure' : 'non configure'}
          ${state.pin_locked ? '<span style="color:var(--red)"><b>🔒 BLOQUE</b></span>' : ''}<br>
        🖥️ ${state.trusted_devices_count} appareil(s) trusted<br>
        🔑 ${state.recovery_codes_remaining} / 8 codes de recuperation restants
      </div>

      <div style="border-top:1px solid var(--border);padding-top:14px;margin-bottom:14px">
        <div style="font-weight:600;margin-bottom:8px">Actions de reinitialisation</div>
        <p style="font-size:11px;color:var(--text3);margin-bottom:12px;line-height:1.5">
          Chaque action demande une motivation (10 chars min) et est tracee dans les logs.
        </p>

        <button class="btn btn-danger" style="width:100%;margin-bottom:8px"
                onclick="resetUser2FA('${username}', '${tenantId}')">
          🔥 Reset COMPLET 2FA (TOTP + PIN + devices)
        </button>
        <p style="font-size:11px;color:var(--text3);margin-bottom:12px;margin-top:-4px;line-height:1.4">
          Pour user qui a perdu son telephone ET ses codes recovery.
          Devra tout reactiver depuis zero.
        </p>

        <button class="btn btn-accent" style="width:100%;margin-bottom:8px"
                ${!state.pin_configured ? 'disabled' : ''}
                onclick="resetUserPin('${username}', '${tenantId}')">
          🔢 Reset PIN seul (sans toucher 2FA)
        </button>
        <p style="font-size:11px;color:var(--text3);margin-bottom:12px;margin-top:-4px;line-height:1.4">
          User a oublie son PIN mais a toujours son telephone.
        </p>

        <button class="btn btn-ghost" style="width:100%"
                ${state.trusted_devices_count === 0 ? 'disabled' : ''}
                onclick="resetUserDevices('${username}', '${tenantId}')">
          🖥️ Vider les ${state.trusted_devices_count} appareil(s) trusted
        </button>
        <p style="font-size:11px;color:var(--text3);margin-top:-4px;line-height:1.4">
          Force re-validation 2FA sur tous les navigateurs (suspicion vol).
        </p>
      </div>

      <div style="text-align:right">
        <button class="btn btn-ghost" onclick="close2FAModal()">Fermer</button>
      </div>
    </div>
  `;

  // Afficher dans un modal
  let modal = document.getElementById('mgmt-2fa-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'mgmt-2fa-modal';
    modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
    document.body.appendChild(modal);
  }
  modal.innerHTML = `<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:12px;max-width:520px;width:100%;max-height:90vh;overflow-y:auto">${content}</div>`;
  modal.style.display = 'flex';
}

function close2FAModal() {
  const m = document.getElementById('mgmt-2fa-modal');
  if (m) m.style.display = 'none';
}

async function resetUser2FA(username, tenantId) {
  const reason = prompt(
    `🔥 Reset COMPLET de la 2FA de ${username}\n\n` +
    `Cette action :\n` +
    `• Supprime le secret TOTP (le user ne pourra plus generer de code)\n` +
    `• Supprime les codes de recuperation\n` +
    `• Supprime le PIN admin\n` +
    `• Supprime tous les appareils trusted\n\n` +
    `Le user devra tout reactiver depuis zero a son prochain acces admin.\n\n` +
    `Motivation (10 chars min) :`,
    ''
  );
  if (reason === null) return;
  if (!reason || reason.trim().length < 10) {
    alert('❌ Motivation obligatoire (10 caracteres min)');
    return;
  }

  if (!confirm(`Confirmer le reset complet de la 2FA de ${username} ?\nMotif : ${reason.trim()}`)) {
    return;
  }

  // LOT 5b : step-up 2FA obligatoire
  const stepupOk = await ensureStepUp();
  if (!stepupOk) { alert("Action annulée : 2FA non validée."); return; }

  try {
    const r = await fetch(`/admin/users/${encodeURIComponent(username)}/reset-2fa`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: reason.trim() }),
    });
    const d = await r.json();
    if (r.ok && d.success) {
      alert(`✅ ${d.message}`);
      close2FAModal();
    } else {
      alert(`❌ ${d.detail || d.message || 'Erreur inconnue'}`);
    }
  } catch (e) {
    alert(`❌ Erreur reseau : ${e.message}`);
  }
}

async function resetUserPin(username, tenantId) {
  const reason = prompt(
    `🔢 Reset du PIN de ${username}\n\n` +
    `Le PIN sera supprime. La 2FA Authenticator reste active.\n` +
    `Le user devra configurer un nouveau PIN au prochain acces admin.\n\n` +
    `Motivation (10 chars min) :`,
    ''
  );
  if (reason === null) return;
  if (!reason || reason.trim().length < 10) {
    alert('❌ Motivation obligatoire (10 caracteres min)');
    return;
  }
  // LOT 5b : step-up 2FA obligatoire
  const stepupOk = await ensureStepUp();
  if (!stepupOk) { alert("Action annulée : 2FA non validée."); return; }

  try {
    const r = await fetch(`/admin/users/${encodeURIComponent(username)}/reset-pin`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: reason.trim() }),
    });
    const d = await r.json();
    if (r.ok && d.success) {
      alert(`✅ ${d.message}`);
      close2FAModal();
    } else {
      alert(`❌ ${d.detail || d.message}`);
    }
  } catch (e) {
    alert(`❌ ${e.message}`);
  }
}

async function resetUserDevices(username, tenantId) {
  const reason = prompt(
    `🖥️ Vider les appareils trusted de ${username}\n\n` +
    `Tous les navigateurs/devices marques comme trusted seront oublies.\n` +
    `Le user devra retaper sa 2FA au prochain acces admin sur chaque device.\n` +
    `(2FA et PIN restent inchanges)\n\n` +
    `Motivation (10 chars min) :`,
    ''
  );
  if (reason === null) return;
  if (!reason || reason.trim().length < 10) {
    alert('❌ Motivation obligatoire (10 caracteres min)');
    return;
  }
  // LOT 5b : step-up 2FA obligatoire
  const stepupOk = await ensureStepUp();
  if (!stepupOk) { alert("Action annulée : 2FA non validée."); return; }

  try {
    const r = await fetch(`/admin/users/${encodeURIComponent(username)}/reset-trusted-devices`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: reason.trim() }),
    });
    const d = await r.json();
    if (r.ok && d.success) {
      alert(`✅ ${d.message}`);
      close2FAModal();
    } else {
      alert(`❌ ${d.detail || d.message}`);
    }
  } catch (e) {
    alert(`❌ ${e.message}`);
  }
}
