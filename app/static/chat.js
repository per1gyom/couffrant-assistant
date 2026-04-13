// Raya Chat — Core
// Dépendances : chat-onboarding.js, chat-shortcuts.js, chat-voice.js,
//               chat-feedback.js, chat-triage.js, chat-admin.js
// (chargés avant ce fichier dans aria_chat.html)

// --- ETAT GLOBAL ---
const messagesEl = document.getElementById('messages');
const inputEl = document.getElementById('input');
const sendBtn = document.getElementById('sendBtn');
const micBtn = document.getElementById('micBtn');
const triageBar = document.getElementById('triageBar');
const micStatus = document.getElementById('micStatus');
const inputWrapper = document.getElementById('inputWrapper');

let speakSpeed = 1.2;
let isListening=false, currentAudio=null, speakAborted=false, currentSpeakBtn=null;
let triageQueue=[], triageCurrent=null, silenceTimer=null;
let finalTextBase='';
let autoSpeak=true;
let currentFile=null;
let currentUser='';
let isAdmin=false;
let shortcutsEditMode=false;
let pendingShortcuts=[];
let _onboardingActive = false;
let _micTarget = null;
let _finalTextBaseTarget = '';

// --- HORLOGE ---
function updateClock(){document.getElementById('clock') && (document.getElementById('clock').textContent=new Date().toLocaleString('fr-FR',{weekday:'short',day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit',second:'2-digit'}));}
setInterval(updateClock,1000); updateClock();

// --- SANTE ---
async function checkHealth() {
  const dot = document.getElementById('msStatus');
  try { const d = await (await fetch('/health')).json(); dot.className = d.status === 'ok' ? 'logo-dot' : 'logo-dot off'; }
  catch(e) { dot.className = 'logo-dot off'; }
}

async function loadUserInfo() {
  try {
    const r = await fetch('/admin/users');
    if (r.ok) { isAdmin = true; document.getElementById('adminPanelBtn').style.display = 'inline-flex'; }
  } catch(e) {}
}

async function loadMailCount() {
  try {
    const r = await fetch('/memory-status');
    const d = await r.json();
    const count = (d.niveau_2 || {}).mail_memory || 0;
    if (count > 0) { const el = document.getElementById('mailCount'); el.textContent = count > 99 ? '99+' : count; el.classList.add('visible'); }
  } catch(e) {}
}

// --- HISTORIQUE (CHAT-HISTORY) ---
async function loadHistory() {
  try {
    const r = await fetch('/chat/history?limit=20');
    if (!r.ok) return;
    const history = await r.json();
    if (!Array.isArray(history) || history.length === 0) return;

    // Supprimer le message de bienvenue s'il est encore là
    const welcome = messagesEl.querySelector('.welcome');
    if (welcome) welcome.remove();

    // Afficher chaque échange de la session précédente
    history.forEach(item => {
      if (item.user) addMessage(item.user, 'user');
      if (item.raya) addMessage(item.raya, 'raya', null, item.id);
    });

    // Séparateur visuel entre l'historique et la session courante
    const sep = document.createElement('div');
    sep.className = 'history-sep';
    sep.textContent = '— conversation précédente —';
    messagesEl.appendChild(sep);

    scrollToBottom(false);
  } catch(e) {
    // Silencieux — l'historique est optionnel, ne pas casser le chat si l'endpoint échoue
  }
}

// --- INIT ---
async function init() {
  renderQuickActions();
  checkHealth();
  loadUserInfo();
  loadMailCount();
  checkTokenStatus();
  await loadHistory();   // CHAT-HISTORY : charger avant l'onboarding
  checkOnboarding();
  document.getElementById('autoSpeakBtn').classList.add('active');
  messagesEl.addEventListener('scroll', onMessagesScroll);
}

// --- TOASTS ---
function showToast(msg, type='ok', duration=3000) {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = 'toast ' + type;
  const icons = { ok: '✓', err: '✕', info: 'ℹ' };
  toast.innerHTML = `<span>${icons[type]||'ℹ'}</span> <span>${msg}</span>`;
  container.appendChild(toast);
  setTimeout(() => { toast.style.animation = 'toastOut 0.3s ease forwards'; setTimeout(() => toast.remove(), 300); }, duration);
}

// --- AUTO SPEAK ---
function toggleAutoSpeak() {
  autoSpeak = !autoSpeak;
  const btn = document.getElementById('autoSpeakBtn');
  if (autoSpeak) { btn.classList.add('active'); btn.textContent='🔊 Auto'; }
  else { btn.classList.remove('active'); btn.textContent='🔇 Muet'; }
}

// --- SCROLL ---
function scrollToBottom(smooth=true) { messagesEl.scrollTo({ top: messagesEl.scrollHeight, behavior: smooth ? 'smooth' : 'instant' }); }
function onMessagesScroll() {
  const dist = messagesEl.scrollHeight - messagesEl.scrollTop - messagesEl.clientHeight;
  document.getElementById('scrollDownBtn').classList.toggle('visible', dist > 150);
}

// --- INPUT ---
function autoResize(el) { el.style.height='auto'; el.style.height=Math.min(el.scrollHeight,120)+'px'; }
function handleKey(e) { if (e.key==='Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } }

function cleanText(t) {
  return t.replace(/#{1,6}\s+/g,'').replace(/\*\*(.*?)\*\*/g,'$1').replace(/\*(.*?)\*/g,'$1')
    .replace(/`(.*?)`/g,'$1').replace(/---+/g,'').replace(/\|.*?\|/g,'')
    .replace(/^\s*[-•]\s/gm,'').replace(/\[([^\]]+)\]\([^\)]+\)/g,'$1')
    .replace(/\n{3,}/g,'\n\n').trim();
}

// --- MESSAGES (partagées avec autres modules) ---
function addMessage(text, type, fileInfo=null, ariaMemoryId=null) {
  const welcome = messagesEl.querySelector('.welcome');
  if (welcome) welcome.remove();
  const row = document.createElement('div'); row.className = 'message-row ' + type;
  const avatar = document.createElement('div'); avatar.className = 'avatar ' + type + '-avatar';
  avatar.textContent = type === 'raya' ? '✦' : (currentUser ? currentUser[0].toUpperCase() : 'G');
  const bubble = document.createElement('div'); bubble.className = 'bubble';
  if (fileInfo && fileInfo.type && fileInfo.type.startsWith('image/')) {
    const img = document.createElement('img'); img.className = 'attached-image';
    img.src = 'data:' + fileInfo.type + ';base64,' + fileInfo.data; bubble.appendChild(img);
  } else if (fileInfo) {
    const badge = document.createElement('div'); badge.style = 'font-size:12px;color:var(--text-muted);margin-bottom:4px';
    badge.textContent = '📎 ' + fileInfo.name; bubble.appendChild(badge);
  }
  const content = document.createElement('div');
  if (type === 'raya') {
    try {
      const rawHtml = marked.parse(text || '');
      const cleanHtml = DOMPurify.sanitize(rawHtml, { ADD_ATTR: ['target', 'rel'] });
      content.innerHTML = cleanHtml;
      content.classList.add('markdown-content');
      content.querySelectorAll('a').forEach(a => { a.setAttribute('target', '_blank'); a.setAttribute('rel', 'noopener noreferrer'); });
    } catch(e) {
      console.error('[Raya] Erreur rendu markdown:', e, 'marked:', typeof marked);
      content.style.whiteSpace = 'pre-wrap';
      content.textContent = text;
    }
  } else {
    content.style.whiteSpace = 'pre-wrap'; content.textContent = text;
  }
  bubble.appendChild(content);
  if (type === 'raya') {
    const actions = document.createElement('div'); actions.className = 'bubble-actions';
    const speakBtn = document.createElement('button'); speakBtn.className = 'speak-btn'; speakBtn.textContent = '🔊 Écouter';
    speakBtn.onclick = () => { if (speakBtn.classList.contains('playing')) stopSpeech(); else speak(text, speakBtn); };
    actions.appendChild(speakBtn);
    if (ariaMemoryId) {
      const sep = document.createElement('span'); sep.className = 'bubble-actions-sep'; actions.appendChild(sep);
      const thumbUp = document.createElement('button'); thumbUp.className = 'feedback-btn'; thumbUp.title = 'Bonne réponse'; thumbUp.textContent = '👍';
      thumbUp.onclick = () => sendFeedback(ariaMemoryId, 'positive', thumbUp); actions.appendChild(thumbUp);
      const thumbDown = document.createElement('button'); thumbDown.className = 'feedback-btn'; thumbDown.title = 'À améliorer'; thumbDown.textContent = '👎';
      thumbDown.onclick = () => openFeedbackDialog(ariaMemoryId, thumbDown); actions.appendChild(thumbDown);
      const whyBtn = document.createElement('button'); whyBtn.className = 'feedback-btn why-btn'; whyBtn.title = 'Pourquoi cette réponse ?'; whyBtn.textContent = '💡';
      whyBtn.onclick = () => showWhy(ariaMemoryId, whyBtn); actions.appendChild(whyBtn);
    }
    bubble.appendChild(actions);
  }
  row.appendChild(avatar); row.appendChild(bubble); messagesEl.appendChild(row);
  if (messagesEl.scrollHeight - messagesEl.scrollTop - messagesEl.clientHeight < 200) scrollToBottom();
  return row;
}

function addLoading() {
  const row = document.createElement('div'); row.className = 'message-row raya';
  const avatar = document.createElement('div'); avatar.className = 'avatar raya-avatar'; avatar.textContent = '✦';
  const bubble = document.createElement('div'); bubble.className = 'bubble loading-bubble';
  bubble.innerHTML = '<div class="dot-anim"></div><div class="dot-anim"></div><div class="dot-anim"></div>';
  row.appendChild(avatar); row.appendChild(bubble); messagesEl.appendChild(row); scrollToBottom(); return row;
}

// --- ASK_CHOICE ---
function renderAskChoice(choiceData) {
  if (!choiceData || !choiceData.question || !choiceData.options) return;
  document.querySelectorAll('.ask-choice-zone').forEach(el => el.remove());
  const zone = document.createElement('div'); zone.className = 'ask-choice-zone onb-choices'; zone.style.marginTop = '8px';
  choiceData.options.forEach(opt => {
    const btn = document.createElement('button'); btn.className = 'onb-choice-btn'; btn.textContent = opt;
    btn.onclick = () => { zone.querySelectorAll('button').forEach(b => b.disabled = true); zone.style.opacity = '0.5'; inputEl.value = opt; sendMessage(); };
    zone.appendChild(btn);
  });
  messagesEl.appendChild(zone); scrollToBottom();
}

// --- ACTIONS EN ATTENTE ---
function renderPendingActions(pendingList) {
  const existing = document.getElementById('pending-actions-zone'); if (existing) existing.remove();
  if (!pendingList || pendingList.length === 0) return;
  const zone = document.createElement('div'); zone.id = 'pending-actions-zone'; zone.className = 'pending-actions-zone';
  const title = document.createElement('div'); title.className = 'pending-title';
  title.textContent = `⏸️ ${pendingList.length} action(s) en attente de confirmation`; zone.appendChild(title);
  pendingList.forEach(action => {
    const card = document.createElement('div'); card.className = 'pending-card';
    const label = document.createElement('div'); label.className = 'pending-label';
    label.textContent = action.label || `${action.action_type} #${action.id}`; card.appendChild(label);
    if (action.payload && action.payload.reply_text) {
      const preview = document.createElement('div'); preview.className = 'pending-preview';
      preview.textContent = action.payload.reply_text.substring(0, 300); card.appendChild(preview);
    }
    const btns = document.createElement('div'); btns.className = 'pending-btns';
    const confirmBtn = document.createElement('button'); confirmBtn.className = 'pending-btn confirm'; confirmBtn.textContent = '✓ Confirmer';
    confirmBtn.onclick = () => { if (confirmBtn.disabled) return; confirmBtn.disabled=true; confirmBtn.textContent='⏳ En cours...'; card.querySelectorAll('button').forEach(b=>b.disabled=true); inputEl.value=`Confirme l'action ${action.id}`; sendMessage(); };
    btns.appendChild(confirmBtn);
    const cancelBtn = document.createElement('button'); cancelBtn.className = 'pending-btn cancel'; cancelBtn.textContent = '✕ Annuler';
    cancelBtn.onclick = () => { if (cancelBtn.disabled) return; cancelBtn.disabled=true; cancelBtn.textContent='⏳ En cours...'; card.querySelectorAll('button').forEach(b=>b.disabled=true); inputEl.value=`Annule l'action ${action.id}`; sendMessage(); };
    btns.appendChild(cancelBtn);
    card.appendChild(btns); zone.appendChild(card);
  });
  const inputZone = document.querySelector('.input-zone');
  inputZone.parentNode.insertBefore(zone, inputZone);
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
    // Détection commande vitesse
    if (data.answer) {
      const speedMatch = data.answer.match(/\[SPEAK_SPEED:([\d.]+)\]/);
      if (speedMatch) { setSpeakSpeed(parseFloat(speedMatch[1])); data.answer = data.answer.replace(/\[SPEAK_SPEED:[\d.]+\]/,'').trim(); }
    }
    const msgRow = addMessage(data.answer,'raya',null,data.aria_memory_id||null);
    if (autoSpeak) speak(data.answer, msgRow.querySelector('.speak-btn'));
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
  }
});

init();
