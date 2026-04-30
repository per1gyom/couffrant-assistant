/**
 * Step-up authentication helper (LOT 5b - 30/04/2026)
 *
 * Demande un code TOTP 6 chiffres dans une modal AVANT d executer une
 * action critique (purge user, reset 2FA d un autre, etc.).
 *
 * Usage :
 *
 *   await ensureStepUp();   // bloque jusqu a saisie OK ou rejette
 *   await fetch('/admin/users/X/confirm-permanent-deletion', {...});
 *
 * Si le serveur retourne 401 stepup_required, l UI peut aussi
 * recapturer ça via :
 *
 *   const r = await fetch(...);
 *   if (!r.ok && (await r.clone().json())?.detail?.error === 'stepup_required') {
 *     await ensureStepUp();
 *     return fetch(...);  // retry
 *   }
 *
 * Cycle de vie :
 * - 1ere fois : modal s affiche, user saisit code, on POST step-up-verify
 * - Succes : pose stepup_validated_at en session (5 min), modal se ferme
 * - Action peut alors se lancer
 * - Pendant 5 min, ensureStepUp() retourne immediatement sans re-modal
 *   (cache cote client : __stepupValidUntil)
 */

// Cache local : timestamp jusqu auquel on considere le step-up valide
let __stepupValidUntil = 0;
const STEPUP_VALIDITY_MS = 5 * 60 * 1000;  // 5 min, doit matcher backend

/**
 * S assure qu un step-up TOTP est valide. Si non, affiche une modal
 * et bloque jusqu a ce que l user valide ou annule.
 *
 * Returns : Promise<bool> — true si valide, false si user annule.
 */
async function ensureStepUp() {
  // Si on a un step-up encore valide cote client, on retourne direct
  if (Date.now() < __stepupValidUntil) {
    return true;
  }

  return new Promise((resolve) => {
    showStepUpModal(resolve);
  });
}

function showStepUpModal(resolveCallback) {
  // Construire la modal si elle n existe pas
  let modal = document.getElementById('stepup-modal');
  if (modal) {
    modal.remove();
  }

  modal = document.createElement('div');
  modal.id = 'stepup-modal';
  modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:10000;display:flex;align-items:center;justify-content:center;padding:20px';

  modal.innerHTML = `
    <div style="background:var(--bg-card,#16161d);border:1px solid var(--border,#2a2a35);border-radius:12px;max-width:420px;width:100%;padding:30px">
      <h3 style="margin:0 0 8px 0;font-family:var(--mono,'JetBrains Mono',monospace);color:var(--text,#e0e0e0)">🔐 Verification 2FA requise</h3>
      <p style="margin:0 0 18px 0;color:var(--text2,#a0a0a0);font-size:13px;line-height:1.5">
        Cette action est <strong style="color:var(--red,#ef4444)">irreversible</strong>.
        Saisissez votre code 2FA Authenticator a 6 chiffres pour confirmer votre identite.
      </p>

      <div id="stepup-error" style="display:none;color:var(--red,#ef4444);font-size:12px;margin-bottom:12px;padding:10px;background:rgba(239,68,68,.1);border-radius:6px;border-left:3px solid var(--red,#ef4444)"></div>

      <input type="text" id="stepup-code-input"
             placeholder="000000"
             maxlength="6"
             inputmode="numeric"
             pattern="\\d*"
             autocomplete="one-time-code"
             autofocus
             style="width:100%;padding:14px;background:var(--bg,#1e1e28);border:1px solid var(--border,#2a2a35);border-radius:8px;color:var(--text,#fff);font-size:22px;font-family:var(--mono,monospace);letter-spacing:.3em;text-align:center;margin-bottom:14px;box-sizing:border-box">

      <div style="display:flex;gap:10px;justify-content:flex-end">
        <button id="stepup-cancel-btn" style="padding:10px 18px;background:transparent;color:var(--text2,#a0a0a0);border:1px solid var(--border,#2a2a35);border-radius:8px;cursor:pointer;font-size:13px">
          Annuler
        </button>
        <button id="stepup-submit-btn" style="padding:10px 18px;background:var(--accent,#6366f1);color:#fff;border:none;border-radius:8px;cursor:pointer;font-size:13px;font-weight:600">
          Valider
        </button>
      </div>
    </div>
  `;

  document.body.appendChild(modal);

  const input = document.getElementById('stepup-code-input');
  const errBox = document.getElementById('stepup-error');
  const submitBtn = document.getElementById('stepup-submit-btn');
  const cancelBtn = document.getElementById('stepup-cancel-btn');

  function showError(msg) {
    errBox.textContent = msg;
    errBox.style.display = 'block';
  }

  function close(success) {
    modal.remove();
    resolveCallback(success);
  }

  async function submit() {
    const code = input.value.trim();
    if (!/^\d{6}$/.test(code)) {
      showError('Code invalide : 6 chiffres requis');
      return;
    }
    submitBtn.disabled = true;
    submitBtn.textContent = 'Verification...';
    errBox.style.display = 'none';
    try {
      const r = await fetch('/admin/2fa/step-up-verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code }),
      });
      const d = await r.json();
      if (r.ok && d.success) {
        // Cache cote client pour eviter de re-poser la modal pendant 5 min
        __stepupValidUntil = Date.now() + STEPUP_VALIDITY_MS - 5000;  // 5s de marge
        close(true);
      } else {
        showError(d.error || 'Code incorrect');
        submitBtn.disabled = false;
        submitBtn.textContent = 'Valider';
        input.value = '';
        input.focus();
      }
    } catch (e) {
      showError('Erreur reseau : ' + e.message);
      submitBtn.disabled = false;
      submitBtn.textContent = 'Valider';
    }
  }

  submitBtn.addEventListener('click', submit);
  cancelBtn.addEventListener('click', () => close(false));
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') submit();
    if (e.key === 'Escape') close(false);
  });

  // Auto-submit quand on a 6 chiffres tapes
  input.addEventListener('input', (e) => {
    if (/^\d{6}$/.test(e.target.value)) {
      setTimeout(submit, 100);  // petit delai pour permettre le rendu
    }
  });

  setTimeout(() => input.focus(), 50);
}
