// chat-feedback.js — Feedback 👍👎 + explication réponse

async function sendFeedback(ariaMemoryId, type, btn) {
  if (btn) { btn.disabled = true; btn.style.opacity = '0.5'; }
  try {
    const r = await fetch('/raya/feedback', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ aria_memory_id: ariaMemoryId, feedback_type: type, comment: '' })
    });
    const d = await r.json();
    if (d.ok || d.status === 'ok') {
      if (btn) btn.textContent = type === 'positive' ? '👍✅' : '👎✅';
      if (type === 'positive') showToast('👍 Noté, merci !', 'ok', 2000);
    } else { if (btn) { btn.disabled = false; btn.style.opacity = ''; } }
  } catch(e) { if (btn) { btn.disabled = false; btn.style.opacity = ''; } }
}

function openFeedbackDialog(ariaMemoryId, btn) {
  const existing = document.getElementById('feedback-dialog-' + ariaMemoryId);
  if (existing) { existing.remove(); _releaseMicFromFeedback(); return; }

  const dialog = document.createElement('div');
  dialog.id = 'feedback-dialog-' + ariaMemoryId;
  dialog.className = 'feedback-dialog';
  dialog.innerHTML = `
    <div class="feedback-dialog-label">Qu'est-ce qui n'était pas satisfaisant ?</div>
    <div class="feedback-dialog-input-row">
      <textarea class="feedback-dialog-input" placeholder="(optionnel) Décris le problème... ou utilise le 🎤" rows="2"></textarea>
      <button class="feedback-dialog-mic" title="Dicter ma réponse">🎤</button>
    </div>
    <div class="feedback-dialog-btns">
      <button class="feedback-dialog-send">👎 Envoyer</button>
      <button class="feedback-dialog-cancel">✕ Annuler</button>
    </div>
  `;

  const textarea = dialog.querySelector('.feedback-dialog-input');
  const micDialogBtn = dialog.querySelector('.feedback-dialog-mic');

  micDialogBtn.onclick = () => {
    if (isListening) { stopListening(); _releaseMicFromFeedback(); }
    else {
      _micTarget = textarea; _finalTextBaseTarget = textarea.value;
      micDialogBtn.textContent = '⏹'; micDialogBtn.style.color = 'var(--danger, #ef4444)';
      startListening();
    }
  };

  dialog.querySelector('.feedback-dialog-send').onclick = async () => {
    const comment = textarea.value.trim();
    dialog.remove(); _releaseMicFromFeedback();
    if (btn) { btn.textContent = '👎⏳'; btn.disabled = true; btn.style.opacity = '0.7'; }
    const userMsg = comment ? `Tu as signalé un problème : "${comment}"` : 'Tu as signalé que cette réponse était insatisfaisante.';
    addMessage(userMsg, 'user');
    const loading = addLoading();
    const r = await fetch('/raya/feedback', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ aria_memory_id: ariaMemoryId, feedback_type: 'negative', comment })
    });
    const d = await r.json();
    loading.remove();
    if (d.ok || d.status === 'ok') {
      if (btn) { btn.textContent = '👎✅'; btn.disabled = true; btn.style.opacity = '0.5'; }
      if (d.rule_text) {
        const ruleMsg = `J'ai analysé le problème. Voici la règle que je propose de retenir :\n\n**${d.rule_text}**\n\nC'est correct ?`;
        const rayaRow = addMessage(ruleMsg, 'raya');
        const btnZone = document.createElement('div'); btnZone.className = 'onb-choices'; btnZone.style.marginTop = '8px';
        const yesBtn = document.createElement('button'); yesBtn.className = 'onb-choice-btn'; yesBtn.textContent = '✓ Oui, apprends';
        yesBtn.onclick = async () => {
          btnZone.querySelectorAll('button').forEach(b => b.disabled = true); btnZone.style.opacity = '0.5';
          await fetch('/raya/feedback', { method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ aria_memory_id: ariaMemoryId, feedback_type: 'negative', comment, confirm_rule: true }) });
          addMessage('Règle retenue. ✅', 'raya'); showToast('Règle apprise', 'ok', 2000);
        };
        const noBtn = document.createElement('button'); noBtn.className = 'onb-choice-btn'; noBtn.textContent = '✕ Non, oublie';
        noBtn.onclick = () => { btnZone.querySelectorAll('button').forEach(b => b.disabled = true); btnZone.style.opacity = '0.5'; addMessage("Ok, je n'apprends rien cette fois.", 'raya'); };
        btnZone.appendChild(yesBtn); btnZone.appendChild(noBtn); rayaRow.after(btnZone);
      } else { addMessage('Feedback enregistré, merci. Je vais m\'améliorer.', 'raya'); }
    } else { addMessage('Désolée, impossible de traiter le feedback pour l\'instant.', 'raya'); }
  };

  dialog.querySelector('.feedback-dialog-cancel').onclick = () => { dialog.remove(); _releaseMicFromFeedback(); };
  btn.closest('.message-row').after(dialog);
}

function _releaseMicFromFeedback() {
  if (_micTarget) {
    _micTarget = null; _finalTextBaseTarget = '';
    document.querySelectorAll('.feedback-dialog-mic').forEach(b => { b.textContent = '🎤'; b.style.color = ''; });
    if (isListening) stopListening();
  }
}

async function showWhy(ariaMemoryId, btn) {
  const existing = document.getElementById('why-panel-' + ariaMemoryId);
  if (existing) { existing.remove(); return; }
  try {
    const d = await (await fetch('/raya/why/' + ariaMemoryId)).json();
    if (!d.ok) return;
    const panel = document.createElement('div'); panel.id = 'why-panel-' + ariaMemoryId; panel.className = 'why-panel';
    const tierLabel = d.model_tier === 'deep' ? '🧠 Opus (analyse complexe)' : '⚡ Sonnet (réponse rapide)';
    const ragLabel = d.via_rag ? `RAG actif — ${(d.rule_ids||[]).length} règle(s) ciblée(s)` : 'Injection en bloc (RAG non actif)';
    const rulesHtml = d.rules_detail && d.rules_detail.length > 0
      ? d.rules_detail.map(r => `<div class="why-rule"><span class="why-cat">[${r.category}]</span> ${r.rule.substring(0,80)}${r.rule.length>80?'...':''} <span class="why-conf">${(r.confidence*100).toFixed(0)}%</span></div>`).join('')
      : '<div class="why-empty">Aucune règle injectée</div>';
    panel.innerHTML = `
      <div class="why-header"><span>💡 Pourquoi cette réponse ?</span><button class="why-close" onclick="this.closest('.why-panel').remove()">✕</button></div>
      <div class="why-row">🤖 Modèle : <strong>${tierLabel}</strong></div>
      <div class="why-row">🔍 Mémoire : <strong>${ragLabel}</strong></div>
      <div class="why-rules-title">Règles utilisées :</div>
      ${rulesHtml}
    `;
    btn.closest('.message-row').after(panel);
  } catch(e) {}
}
