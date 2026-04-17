// Raya Chat — Core (globales, DOM refs, utilitaires)
// Chargé dans raya_chat.html — après chat-shortcuts.js

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
let pendingShortcuts=[];
let _onboardingActive = false;
let _micTarget = null;
let _finalTextBaseTarget = '';
let _isSending = false;
let _abortController = null;

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
    const name = d.display_name || d.username || d.email || '';
    // Nom dans le footer (à côté des 3 points)
    const userEl = document.getElementById('headerUser');
    if (userEl) userEl.textContent = name;
    // Nom dans le logo en haut (remplace "Raya")
    const logoEl = document.getElementById('logoUserName');
    if (logoEl) logoEl.textContent = name;
    if (scope === 'admin' || scope === 'super_admin' || scope === 'couffrant_solar') {
      isAdmin = true;
      const sa = document.getElementById('superAdminBtn');
      const ap = document.getElementById('adminPanelBtn');
      if (sa) sa.style.display = 'inline-flex';
      if (ap) ap.style.display = 'inline-flex';
    } else if (scope === 'tenant_admin') {
      isAdmin = true;
      const ap = document.getElementById('adminPanelBtn');
      if (ap) ap.style.display = 'inline-flex';
    }
    if (scope === 'tenant_admin') {
      document.querySelectorAll('.d-group').forEach(g => {
        const title = (g.querySelector('.d-group-title') || {}).textContent || '';
        if (['Mémoire', 'État du', 'Actions sensibles', 'Urgence'].some(k => title.includes(k))) g.style.display = 'none';
      });
      document.querySelectorAll('.d-sep').forEach((s, i) => { if (i < 3) s.style.display = 'none'; });
    }
  } catch(e) {}
}

async function loadMailCount() {
  try {
    const r = await fetch('/memory-status');
    const d = await r.json();
    const count = (d.niveau_2 || {}).mail_memory || 0;
    if (count > 0) {
      const el = document.getElementById('mailCount');
      if (el) { el.textContent = count > 99 ? '99+' : count; el.classList.add('visible'); }
    }
  } catch(e) {}
}

// --- TOASTS ---
function showToast(msg, type='ok', duration=3000) {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = 'toast ' + type;
  const icons = { ok: '✓', err: '✕', info: 'ℹ' };
  toast.innerHTML = `<span>${icons[type]||'ℹ'}</span> `;
  const msgSpan = document.createElement('span');
  msgSpan.textContent = msg;
  toast.appendChild(msgSpan);
  container.appendChild(toast);
  setTimeout(() => { toast.style.animation = 'toastOut 0.3s ease forwards'; setTimeout(() => toast.remove(), 300); }, duration);
}

// --- AUTO SPEAK ---
function toggleAutoSpeak() {
  autoSpeak = !autoSpeak;
  const btn = document.getElementById('autoSpeakBtn');
  if (autoSpeak) { btn.classList.add('active'); btn.innerHTML='<svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 010 7.07"/></svg> Lecture auto'; }
  else { btn.classList.remove('active'); btn.innerHTML='<svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><line x1="23" y1="9" x2="17" y2="15"/><line x1="17" y1="9" x2="23" y2="15"/></svg> Muet'; }
}

// --- SCROLL ---
function scrollToBottom(smooth=true) { messagesEl.scrollTo({ top: messagesEl.scrollHeight, behavior: smooth ? 'smooth' : 'instant' }); }
function onMessagesScroll() {
  const dist = messagesEl.scrollHeight - messagesEl.scrollTop - messagesEl.clientHeight;
  document.getElementById('scrollDownBtn').classList.toggle('visible', dist > 150);
}

// --- INPUT ---
function autoResize(el) { el.style.height='auto'; el.style.height=Math.min(el.scrollHeight,160)+'px'; el.scrollTop=el.scrollHeight; }
function handleKey(e) { if (e.key==='Enter' && !e.shiftKey) { e.preventDefault(); if (!_isSending) sendMessage(); } }

function cleanText(t) {
  return t.replace(/#{1,6}\s+/g,'').replace(/\*\*(.*?)\*\*/g,'$1').replace(/\*(.*?)\*/g,'$1')
    .replace(/`(.*?)`/g,'$1').replace(/---+/g,'').replace(/\|.*?\|/g,'')
    .replace(/^\s*[-•]\s/gm,'').replace(/\[([^\]]+)\]\([^\)]+\)/g,'$1')
    .replace(/\n{3,}/g,'\n\n').trim();
}
