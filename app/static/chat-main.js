// Raya Chat — Main (sendMessage, loadHistory, init, fichiers, keyboard)
// Chargé EN DERNIER dans raya_chat.html — dépend de chat-core.js + chat-messages.js

// --- HISTORIQUE ---
async function loadHistory() {
  try {
    const r = await fetch('/chat/history?limit=20');
    if (!r.ok) return;
    const data = await r.json();
    // data peut être un tableau ou un objet {error: ...}
    const history = Array.isArray(data) ? data : [];
    if (history.length === 0) return;
    const welcome = messagesEl ? messagesEl.querySelector('.welcome') : null;
    if (welcome) welcome.remove();
    history.forEach(item => {
      if (item.user) addMessage(item.user, 'user', null, null, item.created_at || item.ts);
      if (item.raya) addMessage(item.raya, 'raya', null, item.id, item.created_at || item.ts);
      // Réinjecter les action cards liées à cet échange
      if (item.actions && item.actions.length > 0) {
        item.actions.forEach(a => {
          if (typeof appendPendingActionToChat === 'function') appendPendingActionToChat(a);
        });
      }
    });
    const sep = document.createElement('div');
    sep.className = 'history-sep';
    sep.textContent = '\u2014 conversation précédente \u2014';
    if (messagesEl) messagesEl.appendChild(sep);
    scrollToBottom(false);
  } catch(e) { console.warn('[History] erreur chargement:', e); }
}

// --- TOKEN STATUS — pastilles persistantes boîtes mail expirées ---
let _tokenCheckInterval = null;

async function checkTokenStatus() {
  try {
    const r = await fetch('/token-status');
    if (!r.ok) return;
    const data = await r.json();
    _renderTokenBanner(data.warnings || []);
    // Polling toutes les 3 min pour auto-disparaître quand reconnecté
    if (!_tokenCheckInterval) {
      _tokenCheckInterval = setInterval(checkTokenStatus, 3 * 60 * 1000);
    }
  } catch(e) {}
}

function _renderTokenBanner(warnings) {
  const banner = document.getElementById('tokenBanner');
  if (!banner) return;
  if (!warnings || warnings.length === 0) {
    banner.innerHTML = '';
    banner.style.display = 'none';
    return;
  }
  banner.style.display = 'flex';
  banner.innerHTML = warnings.map(w => {
    const email = (w.mailbox && w.mailbox !== w.provider && w.mailbox.includes('@')) ? w.mailbox : '';
    return `<div class="token-warning-pill">
      <span class="token-warning-icon">⚠️</span>
      <span class="token-warning-label">${w.provider}</span>
      ${email ? `<span class="token-warning-email">${email}</span>` : ''}
      <span class="token-warning-msg">Connexion expirée</span>
      <a href="${w.action_url}" class="token-warning-btn">Reconnecter →</a>
    </div>`;
  }).join('');
}

// --- INIT ---
async function init() {
  if (typeof initShortcuts === 'function') initShortcuts();
  if (typeof initTopicsSidebar === 'function') initTopicsSidebar();
  checkHealth();
  loadUserInfo();
  loadMailCount();
  // Si retour OAuth Gmail → afficher succès + masquer le bandeau immédiatement
  const params = new URLSearchParams(window.location.search);
  if (params.get('gmail_connected') === '1') {
    showToast('Gmail connecté ✅', 'ok', 4000);
    window.history.replaceState({}, '', '/chat');
  }
  // checkTokenStatus désactivé temporairement (faux positifs fréquents)
  // checkTokenStatus();
  await loadHistory();
  // Afficher les actions en attente existantes dans le chat (depuis la session précédente)
  try {
    const r = await fetch('/raya/pending');
    if (r.ok) {
      const data = await r.json();
      if (data.pending_actions && data.pending_actions.length > 0) {
        data.pending_actions.forEach(a => {
          if (typeof appendPendingActionToChat === 'function') appendPendingActionToChat(a);
        });
      }
    }
  } catch(e) { console.warn('[Raya] Pending actions fetch error', e); }
  if (typeof checkOnboarding === 'function') checkOnboarding();
  const autoSpeakBtn = document.getElementById('autoSpeakBtn');
  if (autoSpeakBtn) autoSpeakBtn.classList.add('active');
  if (messagesEl) messagesEl.addEventListener('scroll', onMessagesScroll);
}

// --- SEND MESSAGE ---
const _SEND_ICON = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>';
const _STOP_ICON = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>';

function _setSendMode(mode) {
  if (mode === 'sending') {
    // Pendant que Raya réfléchit : bouton devient "Stop" rouge (cliquable pour
    // annuler), MAIS l'input reste actif pour permettre à l'user de préparer
    // sa prochaine question pendant la réflexion (demande Guillaume 17/04).
    sendBtn.innerHTML = _STOP_ICON;
    sendBtn.classList.add('stop-mode');
    sendBtn.classList.remove('waiting');
    sendBtn.onclick = cancelMessage;
    sendBtn.disabled = false;
    inputEl.disabled = false;
    inputEl.placeholder = 'Prépare ta prochaine question (envoi dispo dès que Raya a fini)…';
  } else if (mode === 'streaming') {
    // Réponse Raya en cours d'affichage (streaming ou fade-in) :
    // bouton envoi visible mais GRISÉ pour empêcher l'envoi tant que
    // la réponse n'est pas 100% affichée → évite les collisions.
    sendBtn.innerHTML = _SEND_ICON;
    sendBtn.classList.remove('stop-mode');
    sendBtn.classList.add('waiting');
    sendBtn.onclick = sendMessage;
    sendBtn.disabled = true;
    inputEl.disabled = false;
    inputEl.placeholder = 'Raya finit sa réponse…';
  } else {
    sendBtn.innerHTML = _SEND_ICON;
    sendBtn.classList.remove('stop-mode', 'waiting');
    sendBtn.onclick = sendMessage;
    sendBtn.disabled = false;
    inputEl.disabled = false;
    inputEl.placeholder = 'Envoie un message a Raya...';
    inputEl.focus();
  }
}

function cancelMessage() {
  if (_abortController) {
    _abortController.abort();
    _abortController = null;
  }
}

async function sendMessage() {
  if (_isSending) return;
  const text = inputEl.value.trim(); if (!text && !currentFile) return;
  if (_onboardingActive && text && !currentFile) {
    inputEl.value=''; inputEl.style.height='auto';
    await _sendOnboardingAnswer(text); return;
  }
  _isSending = true;
  _abortController = new AbortController();
  document.querySelectorAll('.ask-choice-zone').forEach(el => el.remove());
  const fileSnapshot = currentFile ? {...currentFile} : null;
  if(typeof stopListening==='function'&&isListening) stopListening();
  inputEl.value=''; inputEl.style.height='auto'; inputEl.classList.remove('interim');
  removeAttachment(); stopSpeech();
  _setSendMode('sending');
  const userMsgRow = addMessage(text||'[Fichier joint]','user',fileSnapshot);
  const loading = addLoading();
  // UX : pousser la question tout en haut du viewport dès que Raya commence à réfléchir.
  // Technique : ajouter un spacer invisible de la hauteur du viewport APRÈS le loader
  // pour garantir qu'il y a assez de contenu pour scroller, même quand l'historique
  // est court. Puis scroller la question en haut via getBoundingClientRect (robuste).
  // Le spacer est retiré quand la nouvelle question arrive (ou reste sans impact).
  try {
    const oldSpacer = document.getElementById('raya-scroll-spacer');
    if (oldSpacer) oldSpacer.remove();
    const spacer = document.createElement('div');
    spacer.id = 'raya-scroll-spacer';
    spacer.setAttribute('aria-hidden', 'true');
    // Hauteur = viewport du chat - marge pour garder loader visible. Minimum 400px.
    const vh = messagesEl ? messagesEl.clientHeight : 600;
    spacer.style.minHeight = Math.max(400, vh - 180) + 'px';
    spacer.style.pointerEvents = 'none';
    messagesEl.appendChild(spacer);
  } catch(_) {}
  // Scroll smooth avec calcul robuste via getBoundingClientRect (indépendant du DOM parent)
  setTimeout(() => {
    try {
      if (!messagesEl || !userMsgRow) return;
      const rowRect = userMsgRow.getBoundingClientRect();
      const containerRect = messagesEl.getBoundingClientRect();
      const delta = rowRect.top - containerRect.top - 12;  // 12px de marge en haut
      messagesEl.scrollTo({ top: messagesEl.scrollTop + delta, behavior: 'smooth' });
    } catch(_) {}
  }, 120);
  // Anchor anti-sursaut : après loading.remove() ou tout ajout de message,
  // la hauteur du DOM change et la bulle user peut visuellement sauter. On
  // re-verrouille sa position en mode 'instant' (imperceptible). Défini ici
  // (hors try) pour être accessible aussi dans le catch en cas d'erreur.
  const _anchorToQuestion = () => {
    try {
      if (!messagesEl || !userMsgRow) return;
      const rowRect = userMsgRow.getBoundingClientRect();
      const containerRect = messagesEl.getBoundingClientRect();
      const delta = rowRect.top - containerRect.top - 12;
      if (Math.abs(delta) > 2) {
        messagesEl.scrollTo({ top: messagesEl.scrollTop + delta, behavior: 'instant' });
      }
    } catch(_) {}
  };
  try {
    const body = { query: text||(fileSnapshot?'Analyse ce fichier.':'') };
    if (fileSnapshot) { body.file_data=fileSnapshot.data; body.file_type=fileSnapshot.type; body.file_name=fileSnapshot.name; }
    const response = await fetch('/raya',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify(body),
      signal: _abortController.signal,
    });
    const data = await response.json(); loading.remove();
    _anchorToQuestion();
    if (data.answer) {
      if (data.speak_speed) { setSpeakSpeed(data.speak_speed); }
    }
    // Cas d'erreur timeout côté backend : le thread Python continue à s'exécuter
    // (Python ne peut pas tuer un thread), donc la vraie réponse peut arriver en DB
    // quelques secondes plus tard. On affiche un message transitoire et on polle
    // /chat/history pendant 90s pour récupérer la réponse "fantôme".
    if (data.is_error && data.error_type === 'timeout') {
      const errorRow = addMessage(data.answer, 'raya');
      errorRow.classList.add('raya-error-transient');
      showToast('Raya met plus de temps que prévu, je surveille sa réponse…', 'info', 4000);
      _pollGhostResponse(text || (fileSnapshot ? 'Analyse ce fichier.' : ''), errorRow);
      requestAnimationFrame(_anchorToQuestion);
    } else if (data.is_error) {
      addMessage(data.answer, 'raya');
      requestAnimationFrame(_anchorToQuestion);
    } else {
      const msgRow = addMessage(data.answer,'raya',null,data.aria_memory_id||null);
      requestAnimationFrame(_anchorToQuestion);
      if (autoSpeak) speak(data.answer, msgRow.querySelector('.speak-btn'), true);
      if (data.ask_choice) renderAskChoice(data.ask_choice);
      if (data.actions && data.actions.length > 0) {
        // Résultats informatifs (Odoo, contacts, drive, etc.) → dans le chat
        const infoResults = [];
        data.actions.forEach(a => {
          if (a.startsWith('\u2705')) showToast(a.replace('\u2705','').trim(),'ok',3000);
          else if (a.startsWith('\u274c')) showToast(a.replace('\u274c','').trim(),'err',5000);
          else if (a.startsWith('\u23f8\ufe0f')) { /* pending — géré par pending_actions */ }
          else infoResults.push(a);
        });
        if (infoResults.length > 0) {
          addMessage(infoResults.join('\n\n'), 'raya');
          requestAnimationFrame(_anchorToQuestion);
        }
      }
      if (data.pending_actions && data.pending_actions.length>0) {
        data.pending_actions.forEach(a => { if (typeof appendPendingActionToChat==='function') appendPendingActionToChat(a); });
      } else { const zone=document.getElementById('pending-actions-zone'); if(zone) zone.remove(); }
    }
  } catch(e) {
    loading.remove();
    if (e.name === 'AbortError') {
      addMessage('Requête annulée.','raya');
      showToast('Annulé','info',2000);
    } else {
      addMessage('Erreur de connexion \u00e0 Raya. Réessayez.','raya');
      showToast('Erreur de connexion','err');
    }
    requestAnimationFrame(_anchorToQuestion);
  }
  _isSending = false;
  _abortController = null;
  // Au lieu de passer directement à 'ready', on passe en 'streaming' :
  // bouton envoi grisé le temps que la réponse finisse de s'afficher.
  // L'event 'raya-message-rendered' est émis par addMessage(raya) quand
  // le rendu est complet → on attend +500ms de sécurité puis on libère.
  _setSendMode('streaming');
  const _onRendered = () => {
    clearTimeout(_fallbackTimer);
    messagesEl.removeEventListener('raya-message-rendered', _onRendered);
    setTimeout(() => { if (!_isSending) _setSendMode('ready'); }, 500);
  };
  // Sécurité : si pour une raison X l'event n'arrive pas en 10s, on libère
  // quand même le bouton pour ne pas bloquer l'utilisateur.
  const _fallbackTimer = setTimeout(() => {
    messagesEl.removeEventListener('raya-message-rendered', _onRendered);
    if (!_isSending) _setSendMode('ready');
  }, 10000);
  messagesEl.addEventListener('raya-message-rendered', _onRendered, { once: true });
  // Nettoyage du spacer : une fois la réponse affichée, le spacer n'a plus
  // d'utilité. Suppression en DOUCEUR via transition CSS (max-height +
  // opacity) pour éviter le 'tout redescend' perçu par Guillaume quand
  // on retirait le spacer brutalement (500+ px disparaissent d'un coup).
  setTimeout(() => {
    try {
      const s = document.getElementById('raya-scroll-spacer');
      if (!s) return;
      // Mesurer la hauteur actuelle pour animer proprement
      s.style.maxHeight = s.offsetHeight + 'px';
      s.style.overflow = 'hidden';
      s.style.transition = 'max-height 0.5s ease-out, opacity 0.4s ease-out';
      requestAnimationFrame(() => {
        s.style.maxHeight = '0';
        s.style.opacity = '0';
      });
      setTimeout(() => { try { s.remove(); } catch(_) {} }, 550);
    } catch(_) {}
  }, 800);
}

// Polling fantôme : quand /raya a renvoyé un timeout mais que le thread Python
// a continué à s'exécuter en arrière-plan. On vérifie /chat/history pendant 90s
// pour récupérer la vraie réponse si elle finit par arriver.
async function _pollGhostResponse(userText, errorRow) {
  const maxAttempts = 30; // 30 × 3s = 90s
  const userTextNorm = (userText || '').trim().slice(0, 200);
  const startTs = Date.now() - 15000; // tolérance 15s avant l'envoi
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise(r => setTimeout(r, 3000));
    try {
      const r = await fetch('/chat/history?limit=3');
      if (!r.ok) continue;
      const data = await r.json();
      const history = Array.isArray(data) ? data : [];
      const match = history.find(item => {
        if (!item.user || !item.raya) return false;
        const itemUser = (item.user || '').trim().slice(0, 200);
        let itemTs = 0;
        try { itemTs = new Date(parseServerTimestamp(item.created_at || item.ts)).getTime(); } catch(_){}
        return itemUser === userTextNorm && itemTs >= startTs;
      });
      if (match) {
        // La réponse fantôme est arrivée — on remplace le message d'erreur.
        if (errorRow && errorRow.parentNode) errorRow.remove();
        const msgRow = addMessage(match.raya, 'raya', null, match.id, match.created_at || match.ts);
        if (match.actions && match.actions.length > 0) {
          match.actions.forEach(a => { if (typeof appendPendingActionToChat === 'function') appendPendingActionToChat(a); });
        }
        showToast('Réponse récupérée ✨', 'ok', 3000);
        return true;
      }
    } catch(_) {}
  }
  return false;
}

function quickAsk(text) { inputEl.value=text; sendMessage(); }

// --- FICHIERS ---
function handleFileSelect(e) {
  const file=e.target.files[0]; if(!file) return;
  if(file.size>10*1024*1024){alert('Fichier trop volumineux (max 10 Mo).');return;}
  const reader=new FileReader();
  reader.onload=(ev)=>{
    currentFile={data:ev.target.result.split(',')[1],type:file.type,name:file.name};
    document.getElementById('attachmentName').textContent='\uD83D\uDCCE '+file.name;
    document.getElementById('attachmentPreview').classList.add('visible');
    document.getElementById('attachBtn').classList.add('has-file');
  };
  reader.readAsDataURL(file); e.target.value='';
}

function removeAttachment() {
  currentFile=null;
  document.getElementById('attachmentPreview').classList.remove('visible');
  document.getElementById('attachBtn').classList.remove('has-file');
}

// --- KEYBOARD ---
document.addEventListener('keydown', e => {
  if (e.key==='Escape') {
    if(typeof closeDrawer==='function') closeDrawer();
    if(typeof closeShortcutEdit==='function') closeShortcutEdit();
    if(typeof closeOnboarding==='function') closeOnboarding();
    if(typeof _releaseMicFromFeedback==='function') _releaseMicFromFeedback();
    document.querySelectorAll('.bug-report-dialog').forEach(el => el.remove());
  }
});

init();
