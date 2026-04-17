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
    sendBtn.innerHTML = _STOP_ICON;
    sendBtn.classList.add('stop-mode');
    sendBtn.onclick = cancelMessage;
    sendBtn.disabled = false;
    inputEl.disabled = true;
    inputEl.placeholder = 'Raya réfléchit…';
  } else {
    sendBtn.innerHTML = _SEND_ICON;
    sendBtn.classList.remove('stop-mode');
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
  addMessage(text||'[Fichier joint]','user',fileSnapshot);
  const loading = addLoading();
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
    if (data.answer) {
      if (data.speak_speed) { setSpeakSpeed(data.speak_speed); }
    }
    const msgRow = addMessage(data.answer,'raya',null,data.aria_memory_id||null);
    if (autoSpeak) speak(data.answer, msgRow.querySelector('.speak-btn'), true);
    if (data.ask_choice) renderAskChoice(data.ask_choice);
    if (data.actions && data.actions.length > 0) {
      const ok=data.actions.filter(a=>a.startsWith('\u2705')); const err=data.actions.filter(a=>a.startsWith('\u274c')); const pend=data.actions.filter(a=>a.startsWith('\u23f8\ufe0f'));
      if (ok.length) showToast(ok[0].replace('\u2705','').trim(),'ok',3000);
      if (err.length) showToast(err[0].replace('\u274c','').trim(),'err',4000);
      if (pend.length) showToast(`${pend.length} action(s) en attente`,'info',4000);
    }
    if (data.pending_actions && data.pending_actions.length>0) {
      data.pending_actions.forEach(a => { if (typeof appendPendingActionToChat==='function') appendPendingActionToChat(a); });
    } else { const zone=document.getElementById('pending-actions-zone'); if(zone) zone.remove(); }
  } catch(e) {
    loading.remove();
    if (e.name === 'AbortError') {
      addMessage('Requête annulée.','raya');
      showToast('Annulé','info',2000);
    } else {
      addMessage('Erreur de connexion \u00e0 Raya. Réessayez.','raya');
      showToast('Erreur de connexion','err');
    }
  }
  _isSending = false;
  _abortController = null;
  _setSendMode('ready');
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
