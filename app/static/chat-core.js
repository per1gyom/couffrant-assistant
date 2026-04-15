// Raya Chat — Core (globales, DOM refs, utilitaires)
// Chargé EN PREMIER dans raya_chat.html

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
    const d = await (await fetch('/profile')).json();
    const scope = d.scope || '';
    if (scope === 'admin' || scope === 'tenant_admin') {
      isAdmin = true;
      document.getElementById('adminPanelBtn').style.display = 'inline-flex';
    }
    // Masquer les sections super-admin du drawer pour les tenant_admin
    if (scope === 'tenant_admin') {
      document.querySelectorAll('.d-group').forEach(g => {
        const title = (g.querySelector('.d-group-title') || {}).textContent || '';
        if (['Mémoire', 'État du', 'Actions sensibles', 'Urgence'].some(k => title.includes(k))) g.style.display = 'none';
      });
      // Masquer aussi les séparateurs orphelins
      document.querySelectorAll('.d-sep').forEach((s, i) => { if (i < 3) s.style.display = 'none'; });
    }
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
