// Raya Chat — Core (globales, DOM refs, utilitaires)
// Chargé dans raya_chat.html — après chat-shortcuts.js

// --- INTERCEPTEUR SESSION EXPIREE (isolé au chat uniquement) ---
// Detecte les reponses 401 du backend et redirige vers /login-app au lieu
// de laisser le chat "orphelin" quand la session serveur a expire.
// Garde-fous :
//   - Try/catch partout : si le wrapper plante, comportement normal preserve
//   - Exclusion des paths publics pour eviter toute boucle de redirection
//   - Flag unique pour ne pas empiler les overlays
//   - Heartbeat 60s pour detection proactive sans attendre un envoi utilisateur
(function installSessionGuard() {
  try {
    const PUBLIC_PATHS = ['/login-app', '/webhook/', '/health', '/static/', '/sw.js'];
    const originalFetch = window.fetch.bind(window);
    let expiredShown = false;

    function isPublicPath(url) {
      try {
        const path = (typeof url === 'string') ? url : (url.url || '');
        return PUBLIC_PATHS.some(function(p) { return path.indexOf(p) !== -1; });
      } catch (e) { return false; }
    }

    function showSessionExpiredOverlay() {
      if (expiredShown) return;
      expiredShown = true;
      try {
        const overlay = document.createElement('div');
        overlay.id = 'raya-session-expired-overlay';
        overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.88);z-index:99999;display:flex;align-items:center;justify-content:center;font-family:system-ui,sans-serif;';
        const box = document.createElement('div');
        box.style.cssText = 'background:#1a1a2e;color:white;padding:28px 32px;border-radius:10px;max-width:420px;text-align:center;box-shadow:0 10px 40px rgba(0,0,0,0.5);';
        box.innerHTML = '<div style="font-size:44px;margin-bottom:10px;">🔒</div><h2 style="margin:0 0 10px;font-size:19px;">Session expirée</h2><p style="margin:0 0 18px;opacity:0.85;line-height:1.5;">Votre session a expiré par inactivité. Redirection automatique dans <span id="rc">5</span>s vers la page de connexion.</p>';
        const btn = document.createElement('button');
        btn.textContent = 'Se reconnecter maintenant';
        btn.style.cssText = 'background:#FFC107;color:#1a1a2e;border:0;padding:10px 22px;border-radius:4px;cursor:pointer;font-weight:600;font-size:14px;';
        btn.onclick = function() { window.location.href = '/login-app'; };
        box.appendChild(btn);
        overlay.appendChild(box);
        document.body.appendChild(overlay);
        // Countdown visuel
        let n = 5;
        const interval = setInterval(function() {
          n -= 1;
          const el = document.getElementById('rc');
          if (el) el.textContent = n;
          if (n <= 0) { clearInterval(interval); window.location.href = '/login-app'; }
        }, 1000);
      } catch (e) {
        // Fallback si le DOM n'est pas pret : redirection directe
        window.location.href = '/login-app';
      }
    }

    // Wrapper fetch : intercepte les 401 sur paths proteges
    window.fetch = async function(input, init) {
      const response = await originalFetch(input, init);
      try {
        if (response && response.status === 401 && !isPublicPath(input)) {
          showSessionExpiredOverlay();
        }
      } catch (e) { /* ne jamais casser l'appelant */ }
      return response;
    };

    // Heartbeat leger : check la session toutes les 60s meme sans action user
    // /profile est un endpoint protege qui existe deja (admin_tenants.py)
    setInterval(function() {
      if (expiredShown) return;
      try {
        fetch('/profile', { method: 'GET', credentials: 'same-origin' })
          .catch(function() { /* ignore erreurs reseau */ });
      } catch (e) { /* silencieux */ }
    }, 60000);

    console.log('[Raya] Session guard installe');
  } catch (e) {
    console.warn('[Raya] Session guard non installe:', e);
  }
})();

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
let autoSpeak=false;  // OFF par défaut — l'utilisateur active via /settings → Profil, persistance DB
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
    // Synchro auto_speak depuis les preferences DB (null/undefined -> on garde false)
    if (d.settings && d.settings.auto_speak === true) autoSpeak = true;
    const scope = d.scope || '';
    const name = d.display_name || d.username || d.email || '';
    // Nom dans le footer (à côté des 3 points)
    const userEl = document.getElementById('headerUser');
    if (userEl) userEl.textContent = name;
    // Nom dans le logo en haut (remplace "Raya")
    const logoEl = document.getElementById('logoUserName');
    if (logoEl) logoEl.textContent = name;
    // Rôles cumulatifs : super_admin inclut admin qui inclut tenant_admin qui inclut user.
    // Le lien "Ma société" s'affiche pour tenant_admin et au-dessus.
    // Le lien "Super Admin" s'affiche uniquement pour super_admin (et admin collaborateurs Raya).
    const isTenantAdminOrAbove = ['tenant_admin', 'admin', 'super_admin'].includes(scope);
    const isAdminOrAbove = ['admin', 'super_admin'].includes(scope);
    if (isTenantAdminOrAbove) {
      isAdmin = true;
      const ap = document.getElementById('adminPanelBtn');
      if (ap) ap.style.display = 'inline-flex';
    }
    if (isAdminOrAbove) {
      const sa = document.getElementById('superAdminBtn');
      if (sa) sa.style.display = 'inline-flex';
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
function handleKey(e) { if (e.key==='Enter' && !e.shiftKey) { e.preventDefault(); if (!_isSending && !sendBtn.disabled) sendMessage(); } }

function cleanText(t) {
  return t.replace(/#{1,6}\s+/g,'').replace(/\*\*(.*?)\*\*/g,'$1').replace(/\*(.*?)\*/g,'$1')
    .replace(/`(.*?)`/g,'$1').replace(/---+/g,'').replace(/\|.*?\|/g,'')
    .replace(/^\s*[-•]\s/gm,'').replace(/\[([^\]]+)\]\([^\)]+\)/g,'$1')
    .replace(/\n{3,}/g,'\n\n').trim();
}
