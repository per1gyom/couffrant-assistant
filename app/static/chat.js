// Raya Chat — JavaScript

// ─── ÉTAT GLOBAL ───
const messagesEl = document.getElementById('messages');
const inputEl = document.getElementById('input');
const sendBtn = document.getElementById('sendBtn');
const micBtn = document.getElementById('micBtn');
const triageBar = document.getElementById('triageBar');
const micStatus = document.getElementById('micStatus');
const inputWrapper = document.getElementById('inputWrapper');

let isListening=false, currentAudio=null, speakAborted=false, currentSpeakBtn=null;
let triageQueue=[], triageCurrent=null, silenceTimer=null;
let finalTextBase='';
let autoSpeak=true;
let currentFile=null;
let currentUser='';
let isAdmin=false;
let shortcutsEditMode=false;
let pendingShortcuts=[];

// État onboarding conversationnel
let _onboardingActive = false;

// ─── INIT ───
async function init() {
  renderQuickActions();
  checkHealth();
  loadUserInfo();
  loadMailCount();
  checkTokenStatus();
  checkOnboarding();
  document.getElementById('autoSpeakBtn').classList.add('active');
  messagesEl.addEventListener('scroll', onMessagesScroll);
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

async function checkHealth() {
  const dot = document.getElementById('msStatus');
  try { const d = await (await fetch('/health')).json(); dot.className = d.status === 'ok' ? 'logo-dot' : 'logo-dot off'; }
  catch(e) { dot.className = 'logo-dot off'; }
}

// ─── ONBOARDING CONVERSATIONNEL v2 ───
// Moteur d'elicitation dynamique : questions open ou choice (boutons).
// sendMessage() intercepte _onboardingActive et route vers /onboarding/answer.

async function checkOnboarding() {
  try {
    const r = await fetch('/onboarding/status');
    if (!r.ok) return;
    const d = await r.json();
    if (d.status === 'pending' || d.status === 'in_progress') {
      await _startOnboardingChat();
    }
  } catch(e) {}
}

async function _startOnboardingChat() {
  const loading = addLoading();
  try {
    const r = await fetch('/onboarding/start', { method: 'POST' });
    if (!r.ok) { loading.remove(); return; }
    const d = await r.json();
    loading.remove();
    _onboardingActive = true;

    // Message d'intro (séparé de la question)
    if (d.intro) addMessage(d.intro, 'raya');

    // Rend la première question selon son type
    _renderOnboardingStep(d);

    // Lien Passer discret
    const skipBar = document.createElement('div');
    skipBar.id = 'onb-skip-bar';
    skipBar.className = 'onb-chat-skip';
    skipBar.innerHTML = '<a href="#" onclick="skipOnboarding(); return false;">Passer l\'onboarding pour l\'instant →</a>';
    messagesEl.appendChild(skipBar);

    inputEl.placeholder = 'Réponds ici ou utilise le 🎤 micro…';
    scrollToBottom();
  } catch(e) { loading.remove(); }
}

function _renderOnboardingStep(step) {
  // Retire les anciens boutons s'il y en avait
  document.querySelectorAll('.onb-choices').forEach(el => el.remove());

  if (step.type === 'done' || step.done) {
    _onboardingDone(step);
    return;
  }

  // Affiche la question dans le chat
  const question = step.question || step.next_message;
  if (question) addMessage(question, 'raya');

  // Si type choice : affiche les boutons cliquables
  if (step.type === 'choice' && step.options && step.options.length > 0) {
    const container = document.createElement('div');
    container.className = 'onb-choices';
    step.options.forEach(opt => {
      const btn = document.createElement('button');
      btn.className = 'onb-choice-btn';
      btn.textContent = opt;
      btn.onclick = () => {
        container.querySelectorAll('button').forEach(b => b.disabled = true);
        container.style.opacity = '0.5';
        _sendOnboardingAnswer(opt);
      };
      container.appendChild(btn);
    });
    const skipBtn = document.createElement('button');
    skipBtn.className = 'onb-choice-skip';
    skipBtn.textContent = 'Passer →';
    skipBtn.onclick = () => { container.remove(); _sendOnboardingAnswer('(passe)'); };
    container.appendChild(skipBtn);
    messagesEl.appendChild(container);
  }
  scrollToBottom();
}

function _onboardingDone(step) {
  _onboardingActive = false;
  document.getElementById('onb-skip-bar')?.remove();
  document.querySelectorAll('.onb-choices').forEach(el => el.remove());
  inputEl.placeholder = 'Envoie un message à Raya…';
  const msg = step.next_message || step.summary || 'Parfait, je construis ton profil en arrière-plan.';
  addMessage(msg, 'raya');
  _pollOnboardingCompletion();
}

async function _sendOnboardingAnswer(text) {
  addMessage(text, 'user');
  inputEl.value = '';
  inputEl.style.height = 'auto';
  document.querySelectorAll('.onb-choices').forEach(el => el.remove());

  const loading = addLoading();
  try {
    const r = await fetch('/onboarding/answer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answer: text }),
    });
    const d = await r.json();
    loading.remove();
    _renderOnboardingStep(d);
  } catch(e) {
    loading.remove();
    _onboardingActive = false;
    inputEl.placeholder = 'Envoie un message à Raya…';
  }
}

function _pollOnboardingCompletion() {
  let attempts = 0;
  const iv = setInterval(async () => {
    attempts++;
    if (attempts > 10) { clearInterval(iv); return; }
    try {
      const r = await fetch('/onboarding/status');
      const d = await r.json();
      if (d.status === 'done' || d.status === 'completed') {
        clearInterval(iv);
        showToast('✨ Profil configuré par Raya !', 'ok', 4000);
      }
    } catch(e) { clearInterval(iv); }
  }, 3000);
}

async function skipOnboarding() {
  try { await fetch('/onboarding/skip', { method: 'POST' }); } catch(e) {}
  _onboardingActive = false;
  document.getElementById('onb-skip-bar')?.remove();
  document.querySelectorAll('.onb-choices').forEach(el => el.remove());
  inputEl.placeholder = 'Envoie un message à Raya…';
  addMessage('Pas de problème — tu pourras relancer la configuration depuis le menu ⚙️ Admin.', 'raya');
}

function closeOnboarding() {
  const overlay = document.getElementById('onboardingOverlay');
  if (overlay) overlay.classList.remove('open');
}

// ─── TOKEN ALERT ───
async function checkTokenStatus() {
  try {
    const r = await fetch('/token-status');
    if (!r.ok) return;
    const d = await r.json();
    if (d.warnings && d.warnings.length > 0) {
      window._tokenWarnings = d.warnings;
      const btn = document.getElementById('tokenAlertBtn');
      if (btn) btn.style.display = 'inline-flex';
    }
  } catch(e) {}
}

function renderTokenBanner() {
  const banner = document.getElementById('tokenBanner');
  const warnings = window._tokenWarnings || [];
  banner.innerHTML = warnings.map(w => `
    <div class="token-banner-item">
      <span class="token-banner-msg"><strong>${w.provider}</strong> — ${w.message}</span>
      ${w.action_url ? `<a href="${w.action_url}" class="token-banner-link">${w.action}</a>` : ''}
    </div>
  `).join('') + `<button class="token-banner-close" onclick="closeTokenBanner()" title="Fermer">✕</button>`;
}

function toggleTokenBanner() {
  const banner = document.getElementById('tokenBanner');
  if (!banner.classList.contains('visible')) renderTokenBanner();
  banner.classList.toggle('visible');
}

function closeTokenBanner() { document.getElementById('tokenBanner').classList.remove('visible'); }

// ─── TOASTS ───
function showToast(msg, type='ok', duration=3000) {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = 'toast ' + type;
  const icons = { ok: '✓', err: '✕', info: 'ℹ' };
  toast.innerHTML = `<span>${icons[type]||'ℹ'}</span> <span>${msg}</span>`;
  container.appendChild(toast);
  setTimeout(() => { toast.style.animation = 'toastOut 0.3s ease forwards'; setTimeout(() => toast.remove(), 300); }, duration);
}

// ─── AUTO SPEAK ───
function toggleAutoSpeak() {
  autoSpeak = !autoSpeak;
  const btn = document.getElementById('autoSpeakBtn');
  if (autoSpeak) { btn.classList.add('active'); btn.textContent='🔊 Auto'; }
  else { btn.classList.remove('active'); btn.textContent='🔇 Muet'; }
}

// ─── RACCOURCIS ───
const DEFAULT_SHORTCUTS = [
  { icon:'📬', label:'Mails urgents', query:'Quels sont mes mails urgents ?' },
  { icon:'📅', label:'Planning', query:"Quel est mon planning aujourd'hui ?" },
  { icon:'⚡', label:'Chantiers', query:'Donne-moi un point sur mes chantiers en cours' },
  { icon:'📊', label:'Point semaine', query:'Fais-moi un point de la semaine' },
  { icon:'🔔', label:'Relances', query:'Quelles sont mes relances en attente ?' },
  { icon:'📋', label:'Trier mes mails', query:'__TRIAGE__' },
];

function getShortcuts() {
  try { const s = localStorage.getItem('raya_shortcuts'); if (s) return JSON.parse(s); } catch(e) {}
  return DEFAULT_SHORTCUTS;
}
function saveShortcutsToStorage(s) { try { localStorage.setItem('raya_shortcuts', JSON.stringify(s)); } catch(e) {} }

function renderQuickActions() {
  const row = document.getElementById('quickRow');
  const shortcuts = getShortcuts();
  row.innerHTML = '';
  shortcuts.forEach((s, i) => {
    const btn = document.createElement('button');
    btn.className = 'quick-btn' + (shortcutsEditMode ? ' edit-mode' : '');
    btn.innerHTML = `${s.icon||''} ${s.label}`;
    if (shortcutsEditMode) { btn.onclick = () => removeShortcutDirect(i); btn.title = 'Cliquer pour supprimer'; }
    else { btn.onclick = () => s.query === '__TRIAGE__' ? startTriage() : quickAsk(s.query); }
    row.appendChild(btn);
  });
  const addBtn = document.createElement('button'); addBtn.className = 'quick-add-btn'; addBtn.textContent = '+ Ajouter';
  addBtn.style.display = shortcutsEditMode ? 'inline-flex' : 'none'; addBtn.onclick = openShortcuts; row.appendChild(addBtn);
  const editBtn = document.createElement('button'); editBtn.className = 'quick-edit-btn';
  editBtn.textContent = shortcutsEditMode ? '✓ Terminer' : '✏️';
  editBtn.title = shortcutsEditMode ? "Terminer l'édition" : 'Personnaliser les raccourcis';
  editBtn.onclick = toggleShortcutsEdit; row.appendChild(editBtn);
}

function toggleShortcutsEdit() { shortcutsEditMode = !shortcutsEditMode; renderQuickActions(); if (shortcutsEditMode) showToast('Cliquez sur un raccourci pour le supprimer', 'info', 2500); }
function removeShortcutDirect(index) { const s = getShortcuts(); const removed = s[index]; s.splice(index,1); saveShortcutsToStorage(s); renderQuickActions(); showToast(`"${removed.label}" supprimé`, 'ok', 2000); }
function openShortcuts() { pendingShortcuts = [...getShortcuts()]; renderShortcutList(); document.getElementById('modalShortcuts').classList.add('open'); }
function closeShortcuts() { document.getElementById('modalShortcuts').classList.remove('open'); }
function renderShortcutList() {
  document.getElementById('shortcutList').innerHTML = pendingShortcuts.map((s,i) =>
    `<div class="shortcut-item"><span>${s.icon||''} ${s.label}</span><button class="shortcut-del" onclick="removePendingShortcut(${i})">\u2715</button></div>`
  ).join('');
}
function removePendingShortcut(i) { pendingShortcuts.splice(i,1); renderShortcutList(); }
function addShortcut() {
  const input = document.getElementById('newShortcutText'); const text = input.value.trim(); if (!text) return;
  const emojis = ['💬','🔧','📌','🗂','📝','🎯','💡','🔍'];
  pendingShortcuts.push({ icon: emojis[pendingShortcuts.length % emojis.length], label: text, query: text });
  renderShortcutList(); input.value = ''; input.focus();
}
function saveShortcuts() { saveShortcutsToStorage(pendingShortcuts); renderQuickActions(); closeShortcuts(); showToast('Raccourcis enregistrés ✓', 'ok'); }

// ─── SCROLL ───
function scrollToBottom(smooth=true) { messagesEl.scrollTo({ top: messagesEl.scrollHeight, behavior: smooth ? 'smooth' : 'instant' }); }
function onMessagesScroll() {
  const dist = messagesEl.scrollHeight - messagesEl.scrollTop - messagesEl.clientHeight;
  document.getElementById('scrollDownBtn').classList.toggle('visible', dist > 150);
}

// ─── MESSAGES ───
function autoResize(el) { el.style.height='auto'; el.style.height=Math.min(el.scrollHeight,120)+'px'; }
function handleKey(e) { if (e.key==='Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } }

function cleanText(t) {
  return t.replace(/#{1,6}\s+/g,'').replace(/\*\*(.*?)\*\*/g,'$1').replace(/\*(.*?)\*/g,'$1')
    .replace(/`(.*?)`/g,'$1').replace(/---+/g,'').replace(/\|.*?\|/g,'')
    .replace(/^\s*[-•]\s/gm,'').replace(/\[([^\]]+)\]\([^\)]+\)/g,'$1')
    .replace(/\n{3,}/g,'\n\n').trim();
}

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
    } catch(e) { content.style.whiteSpace = 'pre-wrap'; content.textContent = text; }
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

// ─── FEEDBACK 👍👎 ───
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
      if (type === 'positive') showToast('Merci ! Les règles utilisées ont été renforcées.', 'ok', 3000);
    } else { if (btn) { btn.disabled = false; btn.style.opacity = ''; } }
  } catch(e) { if (btn) { btn.disabled = false; btn.style.opacity = ''; } }
}

function openFeedbackDialog(ariaMemoryId, btn) {
  const existing = document.getElementById('feedback-dialog-' + ariaMemoryId);
  if (existing) { existing.remove(); return; }
  const dialog = document.createElement('div');
  dialog.id = 'feedback-dialog-' + ariaMemoryId; dialog.className = 'feedback-dialog';
  dialog.innerHTML = `
    <div class="feedback-dialog-label">Qu'est-ce qui n'était pas satisfaisant ?</div>
    <textarea class="feedback-dialog-input" placeholder="(optionnel) Décris le problème..." rows="2"></textarea>
    <div class="feedback-dialog-btns">
      <button class="feedback-dialog-send">👎 Envoyer</button>
      <button class="feedback-dialog-cancel">✕ Annuler</button>
    </div>
  `;
  dialog.querySelector('.feedback-dialog-send').onclick = async () => {
    const comment = dialog.querySelector('.feedback-dialog-input').value.trim();
    dialog.remove();
    const r = await fetch('/raya/feedback', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ aria_memory_id: ariaMemoryId, feedback_type: 'negative', comment })
    });
    const d = await r.json();
    if (d.ok || d.status === 'ok') {
      if (btn) { btn.textContent = '👎✅'; btn.disabled = true; btn.style.opacity = '0.5'; }
      showToast(d.rule_text ? 'Règle corrective créée par Opus ✔' : 'Feedback enregistré', 'ok', 3000);
    }
  };
  dialog.querySelector('.feedback-dialog-cancel').onclick = () => dialog.remove();
  btn.closest('.message-row').after(dialog);
}

async function showWhy(ariaMemoryId, btn) {
  const existing = document.getElementById('why-panel-' + ariaMemoryId);
  if (existing) { existing.remove(); return; }
  try {
    const d = await (await fetch('/raya/why/' + ariaMemoryId)).json();
    if (!d.ok) return;
    const panel = document.createElement('div');
    panel.id = 'why-panel-' + ariaMemoryId; panel.className = 'why-panel';
    const tierLabel = d.model_tier === 'deep' ? '🧠 Opus (analyse complexe)' : '⚡ Sonnet (réponse rapide)';
    const ragLabel = d.via_rag ? `RAG actif — ${(d.rule_ids||[]).length} règle(s) ciblée(s)` : 'Injection en bloc (RAG non actif)';
    const rulesHtml = d.rules_detail && d.rules_detail.length > 0
      ? d.rules_detail.map(r => `<div class="why-rule"><span class="why-cat">[${r.category}]</span> ${r.rule.substring(0,80)}${r.rule.length>80?'...':''} <span class="why-conf">${(r.confidence*100).toFixed(0)}%</span></div>`).join('')
      : '<div class="why-empty">Aucune règle injectée</div>';
    panel.innerHTML = `
      <div class="why-header"><span>💡 Pourquoi cette réponse ?</span><button class="why-close" onclick="this.closest('.why-panel').remove()">✕</button></div>
      <div class="why-row">🤖 Modèle : <strong>${tierLabel}</strong></div>
      <div class="why-row">🔍 Mémoire : <strong>${ragLabel}</strong></div>
      <div class="why-rules-title">Règles utilisées :</div>
      ${rulesHtml}
    `;
    btn.closest('.message-row').after(panel);
  } catch(e) {}
}

// ─── ACTIONS EN ATTENTE ───
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
    confirmBtn.onclick = () => { inputEl.value = `Confirme l'action ${action.id}`; sendMessage(); }; btns.appendChild(confirmBtn);
    const cancelBtn = document.createElement('button'); cancelBtn.className = 'pending-btn cancel'; cancelBtn.textContent = '✕ Annuler';
    cancelBtn.onclick = () => { inputEl.value = `Annule l'action ${action.id}`; sendMessage(); }; btns.appendChild(cancelBtn);
    card.appendChild(btns); zone.appendChild(card);
  });
  const inputZone = document.querySelector('.input-zone');
  inputZone.parentNode.insertBefore(zone, inputZone);
}

// ─── SEND MESSAGE ───
async function sendMessage() {
  const text = inputEl.value.trim(); if (!text && !currentFile) return;

  // Interception onboarding
  if (_onboardingActive && text && !currentFile) {
    inputEl.value = ''; inputEl.style.height = 'auto';
    await _sendOnboardingAnswer(text);
    return;
  }

  const fileSnapshot = currentFile ? {...currentFile} : null;
  inputEl.value = ''; inputEl.style.height = 'auto'; inputEl.classList.remove('interim');
  removeAttachment(); sendBtn.disabled = true; stopSpeech();
  addMessage(text||'[Fichier joint]', 'user', fileSnapshot);
  const loading = addLoading();
  try {
    const body = { query: text||(fileSnapshot?'Analyse ce fichier.':'') };
    if (fileSnapshot) { body.file_data=fileSnapshot.data; body.file_type=fileSnapshot.type; body.file_name=fileSnapshot.name; }
    const response = await fetch('/raya', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) });
    const data = await response.json(); loading.remove();
    const msgRow = addMessage(data.answer, 'raya', null, data.aria_memory_id || null);
    if (autoSpeak) speak(data.answer, msgRow.querySelector('.speak-btn'));
    if (data.actions && data.actions.length > 0) {
      const ok = data.actions.filter(a => a.startsWith('✅')); const err = data.actions.filter(a => a.startsWith('❌')); const pend = data.actions.filter(a => a.startsWith('⏸️'));
      if (ok.length) showToast(ok[0].replace('✅','').trim(), 'ok', 3000);
      if (err.length) showToast(err[0].replace('❌','').trim(), 'err', 4000);
      if (pend.length) showToast(`${pend.length} action(s) en attente`, 'info', 4000);
    }
    if (data.pending_actions && data.pending_actions.length > 0) renderPendingActions(data.pending_actions);
    else { const zone = document.getElementById('pending-actions-zone'); if (zone) zone.remove(); }
  } catch(e) {
    loading.remove(); addMessage('Erreur de connexion à Raya. Réessayez.', 'raya');
    showToast('Erreur de connexion', 'err');
  }
  sendBtn.disabled = false;
}
function quickAsk(text) { inputEl.value = text; sendMessage(); }

// ─── FICHIERS ───
function handleFileSelect(e) {
  const file = e.target.files[0]; if (!file) return;
  if (file.size > 10*1024*1024) { alert('Fichier trop volumineux (max 10 Mo).'); return; }
  const reader = new FileReader();
  reader.onload = (ev) => {
    currentFile = { data: ev.target.result.split(',')[1], type: file.type, name: file.name };
    document.getElementById('attachmentName').textContent = '📎 ' + file.name;
    document.getElementById('attachmentPreview').classList.add('visible');
    document.getElementById('attachBtn').classList.add('has-file');
  };
  reader.readAsDataURL(file); e.target.value = '';
}
function removeAttachment() {
  currentFile = null;
  document.getElementById('attachmentPreview').classList.remove('visible');
  document.getElementById('attachBtn').classList.remove('has-file');
}

// ─── AUDIO ───
function speak(text, btn) {
  stopSpeech(); speakAborted = false; currentSpeakBtn = btn || null;
  if (currentSpeakBtn) { currentSpeakBtn.textContent='⏹ Stop'; currentSpeakBtn.classList.add('playing'); }
  fetch('/speak', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({text}) })
    .then(r => r.ok ? r.blob() : Promise.reject())
    .then(blob => {
      if (speakAborted || blob.size < 100) { resetSpeakUI(); return; }
      const url = URL.createObjectURL(blob); currentAudio = new Audio(url);
      currentAudio.onended = resetSpeakUI; currentAudio.onerror = resetSpeakUI;
      if (!speakAborted) currentAudio.play().catch(resetSpeakUI);
    }).catch(resetSpeakUI);
}
function resetSpeakUI() { if (currentSpeakBtn) { currentSpeakBtn.textContent='🔊 Écouter'; currentSpeakBtn.classList.remove('playing'); currentSpeakBtn=null; } }
function stopSpeech() { speakAborted = true; if (currentAudio) { currentAudio.pause(); currentAudio=null; } window.speechSynthesis && window.speechSynthesis.cancel(); resetSpeakUI(); }

// ─── MICRO ───
function toggleMic() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { alert('Reconnaissance vocale non supportée.\nUtilisez Chrome ou Edge.'); return; }
  if (isListening) stopListening(); else startListening();
}
function startListening() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition; if (!SR) return;
  finalTextBase = inputEl.value;
  const rec = new SR(); rec.lang='fr-FR'; rec.continuous=false; rec.interimResults=true; rec.maxAlternatives=1;
  rec.onstart = () => { isListening=true; micBtn.classList.add('listening'); micBtn.textContent='⏹'; micStatus.classList.add('visible'); inputWrapper.classList.add('mic-active'); };
  rec.onresult = (e) => {
    clearSilenceTimer(); let interim='', final='';
    for (let i=e.resultIndex; i<e.results.length; i++) {
      if (e.results[i].isFinal) final+=e.results[i][0].transcript+' '; else interim+=e.results[i][0].transcript;
    }
    if (interim) { inputEl.value=(finalTextBase+' '+interim).trim(); inputEl.classList.add('interim'); autoResize(inputEl); }
    if (final) { finalTextBase=(finalTextBase+' '+final).trim(); inputEl.value=finalTextBase; inputEl.classList.remove('interim'); autoResize(inputEl); }
    resetSilenceTimer();
  };
  rec.onerror = (e) => {
    if (e.error==='not-allowed'||e.error==='permission-denied') alert('Microphone bloqué.\nCliquez sur 🔒 dans la barre d\'adresse.');
    else if (e.error==='network') { alert('Erreur réseau micro.'); stopListening(); }
  };
  rec.onend = () => { if (isListening) setTimeout(()=>{ if(isListening) startListening(); },100); else cleanupMicUI(); };
  try { rec.start(); resetSilenceTimer(); } catch(e) { stopListening(); }
}
function resetSilenceTimer() { clearSilenceTimer(); silenceTimer=setTimeout(()=>{ if(isListening) stopListening(); },3000); }
function clearSilenceTimer() { if(silenceTimer){clearTimeout(silenceTimer);silenceTimer=null;} }
function stopListening() { isListening=false; clearSilenceTimer(); cleanupMicUI(); inputEl.classList.remove('interim'); if(inputEl.value) autoResize(inputEl); inputEl.focus(); }
function cleanupMicUI() { micBtn.classList.remove('listening'); micBtn.textContent='🎤'; micStatus.classList.remove('visible'); inputWrapper.classList.remove('mic-active'); }

// ─── TRIAGE ───
async function startTriage() {
  stopSpeech(); triageBar.classList.remove('visible');
  const loading = addLoading();
  const data = await (await fetch('/triage-queue')).json(); loading.remove();
  triageQueue = data.mails || [];
  if (triageQueue.length===0) { const row=addMessage('Aucun mail en attente.','raya'); if(autoSpeak)speak('Aucun mail.',row.querySelector('.speak-btn')); return; }
  const intro = triageQueue.length+" mails à trier. C'est parti !";
  const introRow = addMessage(intro,'raya'); if(autoSpeak) speak(intro, introRow.querySelector('.speak-btn'));
  setTimeout(()=>nextTriage(), 1500);
}
function nextTriage() {
  if (triageQueue.length===0) { triageBar.classList.remove('visible'); const row=addMessage('Triage terminé !','raya'); if(autoSpeak) speak('Triage terminé !',row.querySelector('.speak-btn')); triageCurrent=null; return; }
  triageCurrent = triageQueue.shift();
  const msg='De : '+(triageCurrent.from_email||'Inconnu')+'\nSujet : '+(triageCurrent.subject||'(Sans objet)')+'\n\n'+(triageCurrent.raw_body_preview||'').slice(0,200)+'\n\n— Que je fasse ? ('+(triageQueue.length+' restants)');
  const row=addMessage(msg,'raya'); if(autoSpeak) speak(msg,row.querySelector('.speak-btn'));
  triageBar.classList.add('visible');
}
async function handleTriage(action) {
  if (!triageCurrent) return; triageBar.classList.remove('visible'); stopSpeech();
  if (action==='skip') { addMessage('Passé.','raya'); setTimeout(()=>nextTriage(),500); return; }
  const actionMap={'archive':'Archive le mail '+triageCurrent.message_id,'delete':'Supprime le mail '+triageCurrent.message_id,'reply':'Prépare une réponse pour le mail '+triageCurrent.message_id};
  const loading=addLoading();
  try {
    const data=(await (await fetch('/raya',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:actionMap[action]})})).json()); loading.remove();
    const row=addMessage(data.answer,'raya'); if(autoSpeak) speak(data.answer,row.querySelector('.speak-btn'));
    if (data.actions && data.actions.some(a=>a.startsWith('✅'))) showToast('Action effectuée ✓','ok');
  } catch { loading.remove(); }
  setTimeout(()=>nextTriage(),3000);
}

// ─── TIROIR ADMIN ───
function toggleDrawer() { const d=document.getElementById('drawer'); if(d.classList.contains('open')) closeDrawer(); else openDrawer(); }
function openDrawer() { document.getElementById('drawer').classList.add('open'); document.getElementById('drawerOverlay').classList.add('open'); document.getElementById('adminBtn').classList.add('active'); }
function closeDrawer() { document.getElementById('drawer').classList.remove('open'); document.getElementById('drawerOverlay').classList.remove('open'); document.getElementById('adminBtn').classList.remove('active'); }

async function drawerAction(btn, url, id) {
  const el=document.getElementById('result-'+id);
  el.className='d-btn-result loading'; el.textContent='⏳ En cours…'; btn.disabled=true;
  try {
    const d=await (await fetch(url)).json(); const txt=formatDrawerResult(d);
    el.className='d-btn-result ok'; el.textContent=txt; showToast(txt.split('\n')[0].substring(0,60),'ok');
  } catch(e) { el.className='d-btn-result err'; el.textContent='❌ Erreur: '+e.message; showToast("Erreur lors de l'action",'err'); }
  btn.disabled=false;
}
async function drawerConfirmAction(e, url, id) { e.stopPropagation(); drawerHideConfirm(e,'confirm-'+id); await drawerAction(e.target.closest('.d-btn'), url, id); }
function drawerShowConfirm(id) { document.getElementById(id).classList.add('visible'); }
function drawerHideConfirm(e, id) { e.stopPropagation(); document.getElementById(id).classList.remove('visible'); }

async function drawerMemoryStatus(btn) {
  const el=document.getElementById('result-status'); el.className='d-btn-result loading'; el.textContent='⏳ Chargement…'; btn.disabled=true;
  try {
    const d=await (await fetch('/memory-status')).json(); const n1=d.niveau_1||{}, n2=d.niveau_2||{};
    el.className='d-btn-result info';
    el.textContent=`📬 Mails : ${n2.mail_memory||0}\n💬 Conversations : ${n2.conversations_brutes||0}\n📋 Règles actives : ${n1.regles_actives||0}\n💡 Insights : ${n1.insights||0}\n👥 Contacts : ${n1.contacts||0}\n✍️ Style : ${n2.style_examples||0} exemples`;
  } catch(e) { el.className='d-btn-result err'; el.textContent='❌ Erreur'; }
  btn.disabled=false;
}
async function drawerRules(btn) {
  const el=document.getElementById('result-rules'); el.className='d-btn-result loading'; el.textContent='⏳ Chargement…'; btn.disabled=true;
  try {
    const rules=await (await fetch('/rules')).json(); const active=rules.filter(r=>r.active);
    if (!active.length) { el.className='d-btn-result info'; el.textContent='Aucune règle active.'; }
    else {
      const cats={}; active.forEach(r=>{cats[r.category]=(cats[r.category]||0)+1;});
      el.className='d-btn-result info';
      el.textContent=`${active.length} règles actives :\n`+Object.entries(cats).map(([k,v])=>`${k} : ${v}`).join('\n');
    }
  } catch(e) { el.className='d-btn-result err'; el.textContent='❌ Erreur'; }
  btn.disabled=false;
}
function formatDrawerResult(d) {
  if (d.error) return '❌ '+d.error;
  if (d.status==='ok'||d.status==='termine') {
    const parts=[];
    if (d.analyzed!==undefined) parts.push(`✅ ${d.analyzed} analysés`);
    if (d.remaining!==undefined) parts.push(`${d.remaining} restants`);
    if (d.inserted!==undefined) parts.push(`✅ ${d.inserted} importés`);
    if (d.deleted!==undefined) parts.push(`✅ ${d.deleted} supprimés`);
    if (d.conversations_synthesized!==undefined) parts.push(`✅ ${d.conversations_synthesized} synthétisées`);
    if (d.rules_extracted!==undefined) parts.push(`${d.rules_extracted} règles extraites`);
    if (parts.length) return parts.join('\n'); return '✅ OK';
  }
  if (d.status==='mail_memory_cleared') return '✅ Historique mails vidé.';
  if (d.status) return '✅ '+d.status;
  return JSON.stringify(d).replace(/[{}"]/g,'').replace(/,/g,'\n').substring(0,200);
}

// ─── KEYBOARD ───
document.addEventListener('keydown', e => {
  if (e.key==='Escape') {
    closeDrawer();
    document.getElementById('modalShortcuts').classList.remove('open');
    closeOnboarding();
  }
});
document.getElementById('modalShortcuts').addEventListener('click', e => { if(e.target===document.getElementById('modalShortcuts')) closeShortcuts(); });

init();
