// chat-onboarding.js — Token banner + onboarding conversationnel

// --- TOKEN ALERT ---
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

// --- ONBOARDING CONVERSATIONNEL v2 ---
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
    if (d.intro) addMessage(d.intro, 'raya');
    _renderOnboardingStep(d);
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
  document.querySelectorAll('.onb-choices').forEach(el => el.remove());
  if (step.type === 'done' || step.done) { _onboardingDone(step); return; }
  const question = step.question || step.next_message;
  if (question) addMessage(question, 'raya');
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
        showToast('✨ Profil configuré par Raya !', 'ok', 4000);
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
