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

      // ──── V2.4 : PASTILLE MODELE (Sonnet/Opus) ────
      // Petit badge dans la bulle pour indiquer quel modele a repondu.
      // Aide lutilisateur a juger si la reponse merite un clic "Approfondir".
      addModelBadge(msgRow, data.model_tier);

      // ──── BOUTONS SUGGEST (suggestions de suite) ────
      // Si Raya a ecrit [ACTION:SUGGEST:...] dans sa reponse, le backend
      // les a extraits dans data.suggestions. On affiche des boutons
      // cliquables qui re-soumettent le texte comme nouveau message.
      if (data.suggestions && data.suggestions.length > 0) {
        renderSuggestions(msgRow, data.suggestions);
      }

      // ──── V2.4 : BOUTON "APPROFONDIR AVEC OPUS" ────
      // Si Sonnet a repondu (tier smart), on propose lapprofondissement Opus.
      // Conditions internes a renderDeepenButton : pas derreur, pas de
      // continuation (sinon le bouton Etendre prime).
      renderDeepenButton(msgRow, data);

      // ──── CONTINUATION P2/P3+ : bouton "Etendre" si garde-fou ────
      // Si le backend renvoie un continuation_id, afficher un bouton
      // qui permet d etendre la reflexion sans redemarrer.
      if (data.continuation_id && data.continuation_palier_next) {
        renderContinuationButton(msgRow, data);
      }
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
  //
  // FIX 18/04/2026 : même avec la transition, le scroll pouvait sauter en
  // bas à la fin de la réponse (remarqué par Guillaume sur des réponses
  // courtes type erreurs Odoo). Cause : la transition réduit max-height
  // mais le navigateur recalcule la position de scroll une fois le spacer
  // à 0, ce qui fait remonter naturellement les messages et donne l'impression
  // d'un "tout redescend".
  //
  // Correction : on ancre la position de la question user AVANT la
  // transition, et on corrige le scroll après la transition pour que la
  // question reste là où l'user la voyait. De plus, on NE supprime PLUS
  // le spacer : on le réduit à 0 mais on le laisse dans le DOM, ce qui
  // évite un 2e recalcul au .remove(). Il sera remove proprement à la
  // prochaine question par le code ci-dessus qui fait oldSpacer.remove().
  setTimeout(() => {
    try {
      const s = document.getElementById('raya-scroll-spacer');
      if (!s) return;
      // Ancrage : mémoriser la position de la dernière bulle user pour la
      // restaurer après l'animation (évite le saut visuel).
      const lastUserRow = Array.from(
        messagesEl.querySelectorAll('.message-row.user')
      ).pop();
      const userTopBefore = lastUserRow
        ? lastUserRow.getBoundingClientRect().top
        : null;
      // Mesurer la hauteur actuelle pour animer proprement
      s.style.maxHeight = s.offsetHeight + 'px';
      s.style.overflow = 'hidden';
      s.style.transition = 'max-height 0.5s ease-out, opacity 0.4s ease-out';
      requestAnimationFrame(() => {
        s.style.maxHeight = '0';
        s.style.opacity = '0';
      });
      // Après la transition : corriger le scroll pour que la question reste
      // ancrée en haut, au lieu de laisser le navigateur recalculer et
      // potentiellement faire un saut en bas.
      setTimeout(() => {
        try {
          if (lastUserRow && userTopBefore !== null) {
            const userTopAfter = lastUserRow.getBoundingClientRect().top;
            const delta = userTopAfter - userTopBefore;
            if (Math.abs(delta) > 8) {
              messagesEl.scrollTop += delta;
            }
          }
          // NOTE : on ne fait PAS s.remove() ici. Le spacer réduit à 0 ne
          // gêne plus rien, et il sera remove par la prochaine question.
          // Supprimer ici causait parfois un 2e recalcul de scroll.
        } catch(_) {}
      }, 550);
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
    // NOTE 30/04/2026 : closeDrawer() supprimé en même temps que le drawer
    // (Note UX #7). Le test typeof était défensif mais devient inutile.
    if(typeof closeShortcutEdit==='function') closeShortcutEdit();
    if(typeof closeOnboarding==='function') closeOnboarding();
    if(typeof _releaseMicFromFeedback==='function') _releaseMicFromFeedback();
    document.querySelectorAll('.bug-report-dialog').forEach(el => el.remove());
  }
});

init();


// ════════════════════════════════════════════════════════════════════
// CONTINUATION P2/P3+ : bouton "Etendre la reflexion"
// ════════════════════════════════════════════════════════════════════
// Quand un garde-fou saute (tokens/iter/timeout), le backend renvoie
// un continuation_id. On affiche un bouton qui POSTe vers /raya/continue
// pour reprendre exactement la ou la reflexion s est arretee, avec un
// budget etendu (P2 = +150k, P3+ = +200k par clic, repetable a l infini).
//
// L utilisateur decide de s arreter : il voit le compteur cumule et
// peut refuser de continuer a tout moment. Un avertissement est injecte
// par le backend dans la reponse de Raya quand on passe les 500k tokens
// cumules (3e extension), via build_reflection_prompt cote Python.
function renderContinuationButton(msgRow, data) {
  if (!msgRow || !data || !data.continuation_id) return;

  // Zone dediee sous le message
  const wrap = document.createElement('div');
  wrap.className = 'raya-continuation-wrap';
  wrap.style.cssText = 'margin:10px 0 4px 0;display:flex;flex-direction:column;gap:6px;align-items:flex-start;';

  // Info : tokens consommes jusqu ici + delta prochain palier
  const info = document.createElement('div');
  info.style.cssText = 'font-size:12px;color:#6c757d;';
  const tokensUsed = data.agent_tokens || 0;
  const delta = data.continuation_delta_tokens || 0;
  const palierNext = data.continuation_palier_next || 'P2';
  info.innerHTML = (
    '\u23f1\ufe0f <b>' + tokensUsed.toLocaleString('fr-FR') + '</b> tokens utilises. ' +
    'Palier suivant : <b>' + palierNext + '</b> (+' + delta.toLocaleString('fr-FR') + ' tokens)'
  );
  wrap.appendChild(info);

  // Bouton
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'raya-continuation-btn';
  btn.textContent = palierNext === 'P2'
    ? 'Etendre la reflexion (+' + (delta/1000).toFixed(0) + 'k tokens)'
    : 'Continuer l exploration (+' + (delta/1000).toFixed(0) + 'k tokens)';
  btn.style.cssText = 'background:#FFC107;color:#1a1a2e;border:0;padding:8px 16px;border-radius:4px;cursor:pointer;font-weight:600;font-size:13px;';
  btn.onmouseenter = () => { btn.style.background = '#FFB300'; };
  btn.onmouseleave = () => { btn.style.background = '#FFC107'; };

  btn.onclick = async () => {
    btn.disabled = true;
    btn.textContent = 'Raya reprend sa reflexion...';
    btn.style.background = '#888';
    btn.style.cursor = 'not-allowed';

    const loading = (typeof addLoading === 'function') ? addLoading() : null;
    try {
      const resp = await fetch('/raya/continue', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ continuation_id: data.continuation_id }),
      });
      const extData = await resp.json();
      if (loading) loading.remove();

      // Retire le bouton et l info maintenant que l extension a abouti
      wrap.remove();

      if (extData.is_error) {
        addMessage(extData.answer || 'Erreur lors de l extension.', 'raya');
      } else {
        const newRow = addMessage(
          extData.answer, 'raya', null, extData.aria_memory_id || null
        );
        // V2.4 : pastille modele. Une continuation force toujours Opus.
        if (typeof addModelBadge === 'function') {
          addModelBadge(newRow, extData.model_tier || 'deep');
        }
        if (typeof _anchorToQuestion === 'function') {
          requestAnimationFrame(_anchorToQuestion);
        }
        if (typeof autoSpeak !== 'undefined' && autoSpeak) {
          speak(extData.answer, newRow.querySelector('.speak-btn'), true);
        }
        // Si la reponse d extension contient ELLE AUSSI un continuation_id
        // (ex : on a atteint P2 mais pas encore fini), on re-affiche le bouton
        // pour permettre d aller en P3+ (repetable a l infini).
        if (extData.continuation_id && extData.continuation_palier_next) {
          renderContinuationButton(newRow, extData);
        }
        // Pending actions eventuelles
        if (extData.pending_actions && extData.pending_actions.length > 0) {
          extData.pending_actions.forEach(a => {
            if (typeof appendPendingActionToChat === 'function') {
              appendPendingActionToChat(a);
            }
          });
        }
      }
    } catch (e) {
      if (loading) loading.remove();
      wrap.remove();
      addMessage('Erreur reseau pendant l extension : ' + e.message, 'raya');
    }
  };

  wrap.appendChild(btn);
  msgRow.appendChild(wrap);
}


// ════════════════════════════════════════════════════════════════════
// V2.4 : PASTILLE MODELE + BOUTON "APPROFONDIR AVEC OPUS"
// ════════════════════════════════════════════════════════════════════
//
// Strategie de tiers :
//   - Sonnet 4.6 par defaut (model_tier="smart") : rapide, moins cher
//   - Opus 4.7 sur demande (model_tier="deep") : profondeur, analyse
//
// Affichage :
//   - Pastille discrete "Sonnet" (gris) ou "Opus" (dore) dans la bulle
//   - Si reponse Sonnet et pas erreur : bouton "Approfondir avec Opus"
//     sous le message -> POST /raya/deepen avec aria_memory_id
//   - La reponse Sonnet reste visible (historique preserve), la
//     nouvelle reponse Opus s ajoute en dessous avec sa pastille doree

function addModelBadge(msgRow, modelTier) {
  // Ajoute un petit badge discret indiquant quel modele a repondu
  // - 'smart' (Sonnet 4.6) : badge gris clair, texte "Sonnet"
  // - 'deep'  (Opus 4.7)   : badge dore, texte "Opus"
  // - autre                 : pas de badge (pas de pollution visuelle)
  if (!msgRow || !modelTier) return;
  if (modelTier !== 'smart' && modelTier !== 'deep') return;

  const bubble = msgRow.querySelector('.bubble');
  if (!bubble) return;

  // Evite les doublons si la fonction est appelee 2 fois sur le meme msg
  if (bubble.querySelector('.raya-model-badge')) return;

  const badge = document.createElement('div');
  badge.className = 'raya-model-badge raya-model-badge-' + modelTier;
  badge.textContent = modelTier === 'smart' ? 'Sonnet' : 'Opus';
  badge.style.cssText = (
    'position:absolute;top:6px;right:8px;font-size:10px;' +
    'padding:2px 7px;border-radius:10px;font-weight:600;' +
    'letter-spacing:0.3px;opacity:0.85;user-select:none;'
  );
  if (modelTier === 'smart') {
    // Sonnet : fond gris clair, texte discret
    badge.style.background = '#e9ecef';
    badge.style.color = '#6c757d';
  } else {
    // Opus : fond dore pastel, texte fonce (valorise linvestissement user)
    badge.style.background = '#FFC107';
    badge.style.color = '#1a1a2e';
  }

  // La bubble doit etre relative pour le positionnement absolu du badge
  if (getComputedStyle(bubble).position === 'static') {
    bubble.style.position = 'relative';
  }
  // FIX 27/04 soir : reserver un espace en haut de la bulle pour eviter
  // que le badge superpose le texte de la 1ere ligne (signale par
  // Guillaume sur conv 408 - capture 21:37). Le badge fait ~16px de
  // hauteur, on ajoute 22px de padding-top.
  const currentPadTop = parseInt(getComputedStyle(bubble).paddingTop, 10) || 0;
  if (currentPadTop < 22) {
    bubble.style.paddingTop = '22px';
  }
  bubble.appendChild(badge);
}

function renderDeepenButton(msgRow, data) {
  // Bouton "Approfondir avec Opus" sous une reponse Sonnet.
  // N est affiche QUE si :
  //   - La reponse provient de Sonnet (model_tier='smart')
  //   - Il y a un aria_memory_id valide (permet le lookup backend)
  //   - Pas derreur (is_error=false)
  //   - Pas de continuation_id (sinon le bouton Etendre prime : deja
  //     en garde-fou, autant continuer dans ce flow)
  if (!msgRow || !data) return;
  if (data.model_tier !== 'smart') return;
  if (!data.aria_memory_id) return;
  if (data.is_error) return;
  if (data.continuation_id) return;  // bouton Etendre prend le relais

  const wrap = document.createElement('div');
  wrap.className = 'raya-deepen-wrap';
  wrap.style.cssText = (
    'margin:8px 0 4px 0;display:flex;gap:8px;align-items:center;'
  );

  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'raya-deepen-btn';
  btn.textContent = 'Approfondir avec Opus';
  btn.style.cssText = (
    'background:transparent;color:#1a1a2e;border:1.5px solid #FFC107;' +
    'padding:6px 14px;border-radius:4px;cursor:pointer;' +
    'font-weight:600;font-size:12px;transition:all 0.15s;'
  );
  btn.onmouseenter = () => {
    btn.style.background = '#FFC107';
  };
  btn.onmouseleave = () => {
    btn.style.background = 'transparent';
  };

  btn.onclick = async () => {
    btn.disabled = true;
    btn.textContent = 'Opus reflechit...';
    btn.style.background = '#888';
    btn.style.color = 'white';
    btn.style.borderColor = '#888';
    btn.style.cursor = 'not-allowed';

    const loading = (typeof addLoading === 'function') ? addLoading() : null;
    try {
      const resp = await fetch('/raya/deepen', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ aria_memory_id: data.aria_memory_id }),
      });
      const extData = await resp.json();
      if (loading) loading.remove();

      // On laisse le bouton disparaitre une fois lapprofondissement fait
      // (la reponse Sonnet reste visible, mais le bouton est consomme)
      wrap.remove();

      if (extData.is_error) {
        addMessage(
          extData.answer || 'Erreur lors de lapprofondissement.',
          'raya'
        );
        return;
      }

      // Nouvelle bulle pour la reponse Opus
      const newRow = addMessage(
        extData.answer, 'raya', null, extData.aria_memory_id || null
      );
      // Pastille Opus doree sur la nouvelle bulle
      addModelBadge(newRow, 'deep');

      if (typeof _anchorToQuestion === 'function') {
        requestAnimationFrame(_anchorToQuestion);
      }
      if (typeof autoSpeak !== 'undefined' && autoSpeak) {
        speak(extData.answer, newRow.querySelector('.speak-btn'), true);
      }

      // Si la reponse Opus declenche a son tour un garde-fou (rare vu
      // quil n y a pas de boucle), le bouton Etendre sera gere via
      // renderContinuationButton cote data.continuation_id.
      if (extData.continuation_id && extData.continuation_palier_next) {
        renderContinuationButton(newRow, extData);
      }
    } catch (e) {
      if (loading) loading.remove();
      wrap.remove();
      addMessage('Erreur reseau pendant lapprofondissement : ' + e.message, 'raya');
    }
  };

  wrap.appendChild(btn);

  // Petit texte explicatif discret a cote du bouton
  const hint = document.createElement('span');
  hint.style.cssText = 'font-size:11px;color:#6c757d;';
  hint.textContent = 'analyse plus profonde, enrichissements, nuances';
  wrap.appendChild(hint);

  msgRow.appendChild(wrap);
}
