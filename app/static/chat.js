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

// ─── ONBOARDING CONVERSATIONNEL ───
// Raya pose ses questions comme des messages normaux dans le chat.
// Le micro existant fonctionne immédiatement — il injecte dans l'input normal.
// sendMessage() détecte _onboardingActive et route vers /onboarding/answer.

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
  try {
    const r = await fetch('/onboarding/start', { method: 'POST' });
    if (!r.ok) return;
    const d = await r.json();
    _onboardingActive = true;

    // Affiche le message d'accueil + question 1 dans le chat normal
    addMessage(d.message, 'raya');

    // Petit lien "Passer" sous le message (non intrusif)
    const skipBar = document.createElement('div');
    skipBar.id = 'onb-skip-bar';
    skipBar.className = 'onb-chat-skip';
    skipBar.innerHTML = '<a href="#" onclick="skipOnboarding(); return false;">Passer l\'onboarding pour l\'instant →</a>';
    messagesEl.appendChild(skipBar);

    // Change le placeholder pour guider
    inputEl.placeholder = 'Réponds ici ou utilise le 🎤 micro…';
    scrollToBottom();
  } catch(e) {}
}

async function _sendOnboardingAnswer(text) {
  // Affiche la réponse de l'utilisateur
  addMessage(text, 'user');
  const loading = addLoading();

  try {
    const r = await fetch('/onboarding/answer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answer: text }),
    });
    const d = await r.json();
    loading.remove();

    if (d.next_message) {
      addMessage(d.next_message, 'raya');
      scrollToBottom();
    }

    if (d.done) {
      _onboardingActive = false;
      // Retire le lien "Passer"
      const skipBar = document.getElementById('onb-skip-bar');
      if (skipBar) skipBar.remove();
      // Remet le placeholder normal
      inputEl.placeholder = 'Envoie un message à Raya…';
      // Toast discret quand la génération Opus est finie (polling léger)
      _pollOnboardingCompletion();
    }
  } catch(e) {
    loading.remove();
    _onboardingActive = false;
    inputEl.placeholder = 'Envoie un message à Raya…';
  }
}

function _pollOnboardingCompletion() {
  // Vérifie toutes les 3s si Opus a fini de générer le profil (max 30s)
  let attempts = 0;
  const iv = setInterval(async () => {
    attempts++;
    if (attempts > 10) { clearInterval(iv); return; }
    try {
      const r = await fetch('/onboarding/status');
      const d = await r.json();
      if (d.status === 'completed') {
        clearInterval(iv);
        showToast('✨ Profil configuré par Raya !', 'ok', 4000);
      }
    } catch(e) { clearInterval(iv); }
  }, 3000);
}

async function skipOnboarding() {
  try { await fetch('/onboarding/skip', { method: 'POST' }); } catch(e) {}
  _onboardingActive = false;
  const skipBar = document.getElementById('onb-skip-bar');
  if (skipBar) skipBar.remove();
  inputEl.placeholder = 'Envoie un message à Raya…';
  addMessage('Pas de problème — tu pourras relancer la configuration depuis le menu ⚙️ Admin.', 'raya');
}

// Reste des fonctions overlay (conservées pour le bouton tiroir "Relancer l'onboarding")
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
  avatar.textContent = type === 'raya' ? '✦' : (currentUser ? currentUser[0].toUpperCase() : 'G