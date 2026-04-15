// Raya Chat — Main (sendMessage, loadHistory, init, fichiers, keyboard)
// Chargé EN DERNIER dans raya_chat.html — dépend de chat-core.js + chat-messages.js

// --- HISTORIQUE ---
async function loadHistory() {
  try {
    const r = await fetch('/chat/history?limit=20');
    if (!r.ok) return;
    const history = await r.json();
    if (!Array.isArray(history) || history.length === 0) return;
    const welcome = messagesEl.querySelector('.welcome');
    if (welcome) welcome.remove();
    history.forEach(item => {
      if (item.user) addMessage(item.user, 'user', null, null, item.created_at || item.ts);
      if (item.raya) addMessage(item.raya, 'raya', null, item.id, item.created_at || item.ts);
    });
    const sep = document.createElement('div');
    sep.className = 'history-sep';
    sep.textContent = '— conversation précédente —';
    messagesEl.appendChild(sep);
    scrollToBottom(false);
  } catch(e) {}
}

// --- INIT ---
async function init() {
  renderQuickActions();
  checkHealth();
  loadUserInfo();
  loadMailCount();
  checkTokenStatus();
  await loadHistory();
  checkOnboarding();
  document.getElementById('autoSpeakBtn').classList.add('active');
  messagesEl.addEventListener('scroll', onMessagesScroll);
}

// --- SEND MESSAGE ---
async function sendMessage() {
  const text = inputEl.value.trim(); if (!text && !currentFile) return;
  if (_onboardingActive && text && !currentFile) {
    inputEl.value=''; inputEl.style.height='auto';
    await _sendOnboardingAnswer(text); return;
  }
  document.querySelectorAll('.ask-choice-zone').forEach(el => el.remove());
  const fileSnapshot = currentFile ? {...currentFile} : null;
  inputEl.value=''; inputEl.style.height='auto'; inputEl.classList.remove('interim');
  removeAttachment(); sendBtn.disabled=true; stopSpeech();
  addMessage(text||'[Fichier joint]','user',fileSnapshot);
  const loading = addLoading();
  try {
    const body = { query: text||(fileSnapshot?'Analyse ce fichier.':'') };
    if (fileSnapshot) { body.file_data=fileSnapshot.data; body.file_type=fileSnapshot.type; body.file_name=fileSnapshot.name; }
    const response = await fetch('/raya',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const data = await response.json(); loading.remove();
    if (data.answer) {
      const speedMatch = data.answer.match(/\[SPEAK_SPEED:([\d.]+)\]/);
      if (speedMatch) { setSpeakSpeed(parseFloat(speedMatch[1])); data.answer = data.answer.replace(/\[SPEAK_SPEED:[\d.]+\]/,'').trim(); }
    }
    const msgRow = addMessage(data.answer,'raya',null,data.aria_memory_id||null);
    if (autoSpeak) speak(data.answer, msgRow.querySelector('.speak-btn'), true);
    if (data.ask_choice) renderAskChoice(data.ask_choice);
    if (data.actions && data.actions.length > 0) {
      const ok=data.actions.filter(a=>a.startsWith('✅')); const err=data.actions.filter(a=>a.startsWith('❌')); const pend=data.actions.filter(a=>a.startsWith('⏸️'));
      if (ok.length) showToast(ok[0].replace('✅','').trim(),'ok',3000);
      if (err.length) showToast(err[0].replace('❌','').trim(),'err',4000);
      if (pend.length) showToast(`${pend.length} action(s) en attente`,'info',4000);
    }
    if (data.pending_actions && data.pending_actions.length>0) renderPendingActions(data.pending_actions);
    else { const zone=document.getElementById('pending-actions-zone'); if(zone) zone.remove(); }
  } catch(e) {
    loading.remove(); addMessage('Erreur de connexion à Raya. Réessayez.','raya');
    showToast('Erreur de connexion','err');
  }
  sendBtn.disabled=false;
}

function quickAsk(text) { inputEl.value=text; sendMessage(); }

// --- FICHIERS ---
function handleFileSelect(e) {
  const file=e.target.files[0]; if(!file) return;
  if(file.size>10*1024*1024){alert('Fichier trop volumineux (max 10 Mo).');return;}
  const reader=new FileReader();
  reader.onload=(ev)=>{
    currentFile={data:ev.target.result.split(',')[1],type:file.type,name:file.name};
    document.getElementById('attachmentName').textContent='📎 '+file.name;
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
    closeDrawer();
    document.getElementById('modalShortcuts').classList.remove('open');
    closeOnboarding();
    _releaseMicFromFeedback();
    document.querySelectorAll('.bug-report-dialog').forEach(el => el.remove());
  }
});

init();
