// Raya Chat — Messages (addMessage, addLoading, bug report, ask_choice, pending actions)
// Chargé en 2ème dans raya_chat.html — dépend de chat-core.js

// --- HELPERS ---
// Les timestamps venant de Postgres/Railway sont en UTC mais parfois sans indicateur
// de timezone (ex: "2026-04-17 13:22:03"). On force l'interprétation UTC pour éviter
// un décalage de 2h affiché en local (bug "13:22 au lieu de 15:22").
function parseServerTimestamp(ts) {
  if (!ts) return new Date();
  let s = String(ts).trim();
  if (!/[+-]\d{2}:?\d{2}$|Z$/.test(s)) {
    s = s.replace(' ', 'T') + 'Z';
  }
  return new Date(s);
}

// Insère un élément dans le chat, AVANT le scroll-spacer s'il existe.
// Le spacer est un div invisible ajouté en fin pour permettre à la question user
// de remonter en haut du viewport quand Raya réfléchit. Sans cette insertion
// ciblée, les messages Raya s'ajouteraient après le spacer (donc hors écran).
function appendToChat(row) {
  if (!messagesEl) return;
  const spacer = document.getElementById('raya-scroll-spacer');
  if (spacer) {
    messagesEl.insertBefore(row, spacer);
  } else {
    messagesEl.appendChild(row);
  }
}

// Affichage progressif type ChatGPT : le texte brut se déroule mot-par-mot
// puis est remplacé par le rendu markdown final (liens, bold, listes…).
// Désactivable via window.RAYA_FAKE_STREAMING = false.
// La vitesse s'adapte à la longueur : 0,8s min, 3s max.
function streamRenderToContent(content, rawText, finalizeFn) {
  if (window.RAYA_FAKE_STREAMING === false || !rawText) {
    finalizeFn();
    return;
  }
  const text = String(rawText);
  // Tokenisation par mots (en préservant espaces et retours ligne)
  const chunks = text.match(/(\S+)|(\s+)/g) || [text];
  const totalMs = Math.max(800, Math.min(3000, text.length * 6));
  const tickMs = Math.max(8, Math.floor(totalMs / Math.max(1, chunks.length)));
  content.style.whiteSpace = 'pre-wrap';
  content.classList.add('raya-streaming');
  content.textContent = '';
  let idx = 0;
  const interval = setInterval(() => {
    if (idx >= chunks.length) {
      clearInterval(interval);
      content.style.whiteSpace = '';
      content.classList.remove('raya-streaming');
      finalizeFn();
      return;
    }
    content.textContent += chunks[idx];
    idx++;
  }, tickMs);
}

// --- MESSAGES ---
function addMessage(text, type, fileInfo=null, ariaMemoryId=null, timestamp=null) {
  const welcome = messagesEl.querySelector('.welcome');
  if (welcome) welcome.remove();
  const row = document.createElement('div'); row.className = 'message-row ' + type;

  // TIMESTAMP-2 : horodatage au-dessus des bulles
  const dateObj = timestamp ? parseServerTimestamp(timestamp) : new Date();
  const timeStr = dateObj.toLocaleString('fr-FR', {
    weekday:'short', day:'2-digit', month:'short',
    hour:'2-digit', minute:'2-digit',
    timeZone: 'Europe/Paris'
  });
  const lastTimeEl = messagesEl.querySelector('.msg-time:last-of-type');
  if (!lastTimeEl || lastTimeEl.textContent !== timeStr) {
    const timeEl = document.createElement('div');
    timeEl.className = 'msg-time';
    timeEl.style.cssText = 'font-size:11px;color:#999;text-align:center;width:100%;margin:8px 0 2px;';
    timeEl.textContent = timeStr;
    appendToChat(timeEl);
  }

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
    // Le rendu markdown + tout le post-processing (liens, memoryNotes, etc.)
    // sont encapsulés dans finalize() pour être appliqués soit directement
    // soit à la fin de l'animation de streaming progressif.
    const finalize = () => {
      try {
        const rawHtml = marked.parse(text || '', { breaks: true, gfm: true });
        const cleanHtml = DOMPurify.sanitize(rawHtml, {
          ADD_ATTR: ['target', 'rel'],
          ADD_TAGS: ['img'],
          ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto|tel|data):|[^a-z]|[a-z+.\-]+(?:[^a-z+.\-:]|$))/i,
        });
        content.innerHTML = cleanHtml;
        content.classList.add('markdown-content');
        content.querySelectorAll('a').forEach(a => { a.setAttribute('target', '_blank'); a.setAttribute('rel', 'noopener noreferrer'); });
        content.querySelectorAll('a').forEach(a => {
          const href = a.getAttribute('href') || '';
          if (href.includes('/download/') || href.match(/\.(pdf|xlsx|xls|csv|png|jpg|jpeg)(\?|$)/i)) {
            a.addEventListener('click', (e) => { e.preventDefault(); window.open(href, '_blank'); });
          }
        });
        // FIX-LEARN-UI: nettoyer les notifications mémoire brutes du contenu affiché
        const memoryNotes = [];
        content.innerHTML = content.innerHTML.replace(
          /<p>(?:🧠|⚠️\s*Conflit)[^<]*<\/p>/gi,
          (match) => { if (match.includes('🧠')) memoryNotes.push(match.replace(/<\/?p>/g, '').trim()); return ''; }
        );
        content.innerHTML = content.innerHTML.replace(
          /(?:🧠|⚠️\s*Conflit de regle)[^\n<]*/gi,
          (match) => { if (match.includes('🧠')) memoryNotes.push(match.trim()); return ''; }
        );
        if (memoryNotes.length > 0) {
          const memDiv = document.createElement('div');
          memDiv.style.cssText = 'margin-top:6px;padding:4px 10px;background:rgba(34,197,94,0.1);border-radius:6px;font-size:12px;color:#16a34a;cursor:pointer;display:inline-block;';
          memDiv.innerHTML = `✅ ${memoryNotes.length} ${memoryNotes.length > 1 ? 'règles mises' : 'règle mise'} à jour`;
          const detailDiv = document.createElement('div');
          detailDiv.style.cssText = 'display:none;margin-top:4px;font-size:11px;color:#666;';
          detailDiv.innerHTML = memoryNotes.map(n => n.replace(/🧠\s*Memorise\s*[+~]\s*/i, '').replace(/🧠\s*/g, '')).join('<br>');
          memDiv.onclick = () => { detailDiv.style.display = detailDiv.style.display === 'none' ? 'block' : 'none'; };
          memDiv.appendChild(detailDiv);
          bubble.appendChild(memDiv);
        }
      } catch(e) {
        console.error('[Raya] Erreur rendu markdown:', e, 'marked:', typeof marked);
        content.style.whiteSpace = 'pre-wrap';
        content.textContent = text;
      }
    };
    // Streaming progressif du texte brut puis switch vers rendu markdown
    streamRenderToContent(content, text, finalize);
  } else {
    content.style.whiteSpace = 'pre-wrap'; content.textContent = text;
  }
  bubble.appendChild(content);
  if (type === 'raya' && ariaMemoryId) row.dataset.ariaMemoryId = String(ariaMemoryId);
  if (type === 'raya') {
    const actions = document.createElement('div'); actions.className = 'bubble-actions';
    const speakBtn = document.createElement('button'); speakBtn.className = 'speak-btn'; speakBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 010 7.07"/><path d="M19.07 4.93a10 10 0 010 14.14"/></svg> Écouter';
    speakBtn.onclick = () => { if (speakBtn.classList.contains('playing')) stopSpeech(); else speak(text, speakBtn); };
    actions.appendChild(speakBtn);
    if (ariaMemoryId) {
      const sep = document.createElement('span'); sep.className = 'bubble-actions-sep'; actions.appendChild(sep);
      const thumbUp = document.createElement('button'); thumbUp.className = 'feedback-btn'; thumbUp.title = 'Bonne réponse'; thumbUp.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 9V5a3 3 0 00-3-3l-4 9v11h11.28a2 2 0 002-1.7l1.38-9a2 2 0 00-2-2.3H14z"/><path d="M7 22H4a2 2 0 01-2-2v-7a2 2 0 012-2h3"/></svg>';
      thumbUp.onclick = () => {
        sendFeedback(ariaMemoryId, 'positive', thumbUp);
        const pendingZone = document.getElementById('pending-actions-zone');
        if (pendingZone) {
          const confirmBtns = pendingZone.querySelectorAll('.pending-btn.confirm');
          confirmBtns.forEach(btn => { if (!btn.disabled) btn.click(); });
        }
      }; actions.appendChild(thumbUp);
      const thumbDown = document.createElement('button'); thumbDown.className = 'feedback-btn'; thumbDown.title = 'À améliorer'; thumbDown.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 15v4a3 3 0 003 3l4-9V2H5.72a2 2 0 00-2 1.7l-1.38 9a2 2 0 002 2.3H10z"/><path d="M17 2h2.67A2.31 2.31 0 0122 4v7a2.31 2.31 0 01-2.33 2H17"/></svg>';
      thumbDown.onclick = () => openFeedbackDialog(ariaMemoryId, thumbDown); actions.appendChild(thumbDown);
      const whyBtn = document.createElement('button'); whyBtn.className = 'feedback-btn why-btn'; whyBtn.title = 'Pourquoi cette réponse ?'; whyBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3"/><circle cx="12" cy="12" r="10"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>';
      whyBtn.onclick = () => showWhy(ariaMemoryId, whyBtn); actions.appendChild(whyBtn);
      const bugSep = document.createElement('span'); bugSep.className = 'bubble-actions-sep'; actions.appendChild(bugSep);
      const bugBtn = document.createElement('button'); bugBtn.className = 'feedback-btn bug-btn'; bugBtn.title = 'Signaler un bug'; bugBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>';
      bugBtn.onclick = () => openBugReportDialog(ariaMemoryId, text, row, bugBtn); actions.appendChild(bugBtn);
    }
    bubble.appendChild(actions);
  }
  row.appendChild(avatar); row.appendChild(bubble); appendToChat(row);
  if (messagesEl.scrollHeight - messagesEl.scrollTop - messagesEl.clientHeight < 200) scrollToBottom();
  return row;
}

function addLoading() {
  const row = document.createElement('div'); row.className = 'message-row raya';
  const avatar = document.createElement('div'); avatar.className = 'avatar raya-avatar'; avatar.textContent = '✦';
  const bubble = document.createElement('div'); bubble.className = 'bubble loading-bubble';

  const thinking = document.createElement('div'); thinking.className = 'raya-thinking';
  const sigil = document.createElement('span'); sigil.className = 'raya-thinking-sigil'; sigil.textContent = '✦';
  const textEl = document.createElement('span'); textEl.className = 'raya-thinking-text';
  const messages = [
    'Raya réfléchit…',
    'Analyse du contexte…',
    'Consultation de tes outils…',
    'Recherche dans tes données…',
    'Croisement des sources…',
    'Préparation de la réponse…',
  ];
  textEl.textContent = messages[0];
  thinking.appendChild(sigil); thinking.appendChild(textEl);
  bubble.appendChild(thinking);

  // Rotation des messages toutes les 2.8s avec fondu
  let idx = 0;
  const interval = setInterval(() => {
    idx = (idx + 1) % messages.length;
    textEl.style.opacity = '0';
    setTimeout(() => { textEl.textContent = messages[idx]; textEl.style.opacity = '1'; }, 250);
  }, 2800);
  // On stocke l'interval sur le row et on override remove() pour le nettoyer
  const origRemove = row.remove.bind(row);
  row.remove = () => { clearInterval(interval); origRemove(); };

  row.appendChild(avatar); row.appendChild(bubble); appendToChat(row); scrollToBottom(); return row;
}

// --- BUG REPORT (P1-4) ---
function openBugReportDialog(ariaMemoryId, rayaText, msgRow, triggerBtn) {
  let userInput = '';
  try {
    const prev = msgRow.previousElementSibling;
    if (prev && prev.classList.contains('message-row') && prev.classList.contains('user')) {
      userInput = prev.querySelector('.bubble')?.textContent?.trim() || '';
    }
  } catch(_) {}
  document.querySelectorAll('.bug-report-dialog').forEach(el => el.remove());
  const dialog = document.createElement('div');
  dialog.className = 'feedback-dialog bug-report-dialog';
  dialog.style.marginTop = '6px';
  let selectedType = 'bug';
  dialog.innerHTML = `
    <div class="feedback-dialog-label">🐛 Signaler un bug ou suggérer une amélioration</div>
    <div style="display:flex;gap:8px;margin-bottom:10px;">
      <button class="bug-type-btn active" data-type="bug" style="flex:1;padding:6px;border-radius:6px;border:1px solid var(--danger);background:rgba(239,68,68,.1);color:var(--danger);cursor:pointer;font-size:13px;font-weight:600;">🐛 Bug</button>
      <button class="bug-type-btn" data-type="amelioration" style="flex:1;padding:6px;border-radius:6px;border:1px solid var(--accent);background:transparent;color:var(--accent);cursor:pointer;font-size:13px;font-weight:600;">💡 Amélioration</button>
    </div>
    <textarea class="feedback-dialog-input bug-desc" rows="3" placeholder="Optionnel — les derniers échanges seront envoyés automatiquement" style="width:100%;margin-bottom:8px;"></textarea>
    <div class="feedback-dialog-btns">
      <button class="feedback-dialog-send bug-submit">Envoyer</button>
      <button class="feedback-dialog-cancel bug-cancel">Annuler</button>
    </div>
  `;
  const textarea = dialog.querySelector('.bug-desc');
  dialog.querySelectorAll('.bug-type-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      selectedType = btn.dataset.type;
      dialog.querySelectorAll('.bug-type-btn').forEach(b => { b.classList.remove('active'); b.style.background = 'transparent'; });
      btn.classList.add('active');
      btn.style.background = selectedType === 'bug' ? 'rgba(239,68,68,.1)' : 'rgba(99,102,241,.1)';
      textarea.placeholder = selectedType === 'bug'
        ? 'Optionnel — les derniers échanges seront envoyés automatiquement'
        : 'Décris ta suggestion…';
    });
  });
  dialog.querySelector('.bug-cancel').addEventListener('click', () => dialog.remove());
  dialog.querySelector('.bug-submit').addEventListener('click', async () => {
    const desc = dialog.querySelector('.bug-desc').value.trim();
    if (!desc && selectedType === 'amelioration') { showToast('Décris ta suggestion avant d\'envoyer.', 'err', 2500); return; }
    const submitBtn = dialog.querySelector('.bug-submit');
    submitBtn.disabled = true; submitBtn.textContent = '⏳ Envoi…';
    try {
      const deviceInfo = (navigator.userAgent || '').slice(0, 200) + (window.innerWidth < 768 ? ' [mobile]' : ' [desktop]');
      // Collecter les 2-3 derniers échanges pour contexte
      const allRows = document.querySelectorAll('.message-row');
      const recentExchanges = [];
      const rows = Array.from(allRows).slice(-6);
      rows.forEach(r => {
        const bubbleText = r.querySelector('.bubble')?.textContent?.trim() || '';
        if (bubbleText) {
          const role = r.classList.contains('user') ? 'user' : 'raya';
          recentExchanges.push(role + ': ' + bubbleText.substring(0, 300));
        }
      });
      const contextStr = recentExchanges.join('\n---\n').substring(0, 2000);
      const r = await fetch('/raya/bug-report', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ report_type: selectedType, description: desc, aria_memory_id: ariaMemoryId,
          user_input: userInput.slice(0, 500), raya_response: (rayaText || '').slice(0, 500) + '\n\n--- CONTEXTE (derniers échanges) ---\n' + contextStr, device_info: deviceInfo }),
      });
      const data = await r.json(); dialog.remove();
      if (data.ok) { showToast('Merci ! Rapport envoyé (#' + data.id + ')', 'ok', 4000); if (triggerBtn) { triggerBtn.style.opacity='1'; triggerBtn.textContent='✅'; } }
      else { showToast('Erreur envoi rapport : ' + (data.error || '?'), 'err', 4000); }
    } catch(e) { showToast('Erreur réseau lors de l\'envoi.', 'err', 4000); submitBtn.disabled=false; submitBtn.textContent='Envoyer'; }
  });
  msgRow.insertAdjacentElement('afterend', dialog);
  dialog.querySelector('.bug-desc').focus();
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
  appendToChat(zone); scrollToBottom();
}

// --- ACTIONS EN ATTENTE (inline dans le chat) ---
const _shownActionIds = new Set();

function appendPendingActionToChat(action) {
  if (_shownActionIds.has(action.id)) return;
  if (messagesEl && messagesEl.querySelector(`[data-action-id="${action.id}"]`)) {
    _shownActionIds.add(action.id);
    return;
  }
  _shownActionIds.add(action.id);

  const row = document.createElement('div');
  const isDone = action.status && action.status !== 'pending';
  row.className = isDone ? 'message-row action-done' : 'message-row action-pending';
  row.dataset.actionId = String(action.id);
  if (action.conversation_id) row.dataset.conversationId = String(action.conversation_id);

  const card = document.createElement('div');
  card.className = 'action-card';

  const isReply    = action.action_type === 'REPLY';
  const isSendMail = action.action_type === 'SEND_MAIL' || action.action_type === 'SEND_GMAIL';
  const p = action.payload || {};

  // Badge lisible selon le type d'action
  const badge = document.createElement('div');
  badge.className = 'pending-id-badge';
  const badgeLabels = {
    'SEND_MAIL':    '✉️ Mail préparé (Outlook)',
    'SEND_GMAIL':   '✉️ Mail préparé (Gmail)',
    'REPLY':        '↩️ Réponse préparée',
    'TEAMS_MSG':    '💬 Message Teams',
    'CREATEEVENT':  '📅 Événement',
    'MOVEDRIVE':    '📁 Déplacement Drive',
  };
  badge.textContent = badgeLabels[action.action_type] || `📋 ${action.action_type}`;
  card.appendChild(badge);

  // Contenu selon type
  if (isReply || isSendMail) {
    const toName    = p.sender_name || p.to_email || p.to || '';
    const fromEmail = p.from_email || '';
    const subject   = p.subject || '(sans sujet)';
    const body      = (p.reply_text || p.body || '').replace(/\\n/g, '\n');

    // Champ De — select chargé dynamiquement depuis /signatures/mailboxes
    const fromRow = document.createElement('div'); fromRow.className = 'pending-mail-from';
    const fromSelect = document.createElement('select');
    fromSelect.className = 'mail-edit-from';
    fromSelect.innerHTML = `<option value="${fromEmail}">${fromEmail || 'Chargement…'}</option>`;
    fromRow.innerHTML = 'De&nbsp;: ';
    fromRow.appendChild(fromSelect);
    card.appendChild(fromRow);
    // Charger les boîtes disponibles
    fetch('/signatures/mailboxes').then(r => r.json()).then(boxes => {
      fromSelect.innerHTML = '';
      if (!boxes.length) { fromSelect.innerHTML = `<option value="${fromEmail}">${fromEmail || '(aucune boîte)'}</option>`; return; }
      boxes.forEach(b => {
        const opt = document.createElement('option');
        opt.value = b.address; opt.textContent = b.label || b.address;
        if (b.address === fromEmail) opt.selected = true;
        fromSelect.appendChild(opt);
      });
      if (fromEmail && !boxes.find(b => b.address === fromEmail)) {
        const opt = document.createElement('option'); opt.value = fromEmail; opt.textContent = fromEmail; opt.selected = true;
        fromSelect.prepend(opt);
      }
    }).catch(() => {});

    // Champ À — input éditable
    const header = document.createElement('div'); header.className = 'pending-mail-header';
    const toInput = document.createElement('input');
    toInput.type = 'email'; toInput.className = 'mail-edit-to';
    toInput.value = toName; toInput.placeholder = 'destinataire@email.com';
    header.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg> À&nbsp;: `;
    header.appendChild(toInput);

    // Sujet — statique
    const subjectEl = document.createElement('div'); subjectEl.className = 'pending-mail-subject';
    subjectEl.innerHTML = `Sujet&nbsp;: <em>${subject}</em>`;

    // Corps — textarea éditable
    const bodyEl = document.createElement('textarea'); bodyEl.className = 'mail-edit-body';
    bodyEl.value = body;
    bodyEl.rows = 6;

    card.appendChild(header); card.appendChild(subjectEl); card.appendChild(bodyEl);
  } else {
    const label = document.createElement('div'); label.className = 'pending-label';
    label.textContent = action.label || `${action.action_type} #${action.id}`;
    card.appendChild(label);
  }

  // Boutons
  const btns = document.createElement('div'); btns.className = 'pending-btns';

  const confirmBtn = document.createElement('button'); confirmBtn.className = 'pending-btn confirm';
  confirmBtn.innerHTML = '&#10003; Envoyer';
  confirmBtn.onclick = async () => {
    if (confirmBtn.disabled) return;
    btns.querySelectorAll('button').forEach(b => b.disabled = true);
    confirmBtn.innerHTML = '&#8987;';
    // Lire les valeurs éditées si la carte est une carte mail
    let payloadOverride = null;
    if (isReply || isSendMail) {
      const toInput = card.querySelector('.mail-edit-to');
      const fromSel = card.querySelector('.mail-edit-from');
      const bodyTA  = card.querySelector('.mail-edit-body');
      if (toInput || fromSel || bodyTA) {
        payloadOverride = {
          to_email:   toInput  ? toInput.value.trim()  : (p.to_email || p.to || ''),
          from_email: fromSel  ? fromSel.value         : (p.from_email || ''),
          body:       bodyTA   ? bodyTA.value           : (p.body || p.reply_text || ''),
          subject:    p.subject || '',
          reply_text: bodyTA   ? bodyTA.value           : (p.reply_text || ''),
          message_id: p.message_id || '',
        };
      }
    }
    try {
      const r = await fetch(`/raya/confirm/${action.id}`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payloadOverride ? {payload_override: payloadOverride} : {})
      });
      const data = await r.json();
      _markActionInChat(action.id, data.ok ? 'ok' : 'err', data.message);
    } catch(e) {
      _markActionInChat(action.id, 'err', 'Erreur réseau');
    }
  };

  const cancelBtn = document.createElement('button'); cancelBtn.className = 'pending-btn cancel';
  cancelBtn.innerHTML = '&#10005; Annuler';
  cancelBtn.onclick = async () => {
    if (cancelBtn.disabled) return;
    btns.querySelectorAll('button').forEach(b => b.disabled = true);
    cancelBtn.innerHTML = '&#8987;';
    try {
      const r = await fetch(`/raya/cancel/${action.id}`, { method: 'POST' });
      const data = await r.json();
      _markActionInChat(action.id, 'cancelled', data.message);
    } catch(e) {
      _markActionInChat(action.id, 'err', 'Erreur réseau');
    }
  };

  btns.appendChild(confirmBtn);

  // Bouton Brouillon (REPLY et SEND_MAIL seulement)
  if (isReply || isSendMail) {
    const draftBtn = document.createElement('button'); draftBtn.className = 'pending-btn draft';
    draftBtn.innerHTML = '&#128196; Brouillon';
    draftBtn.title = 'Enregistrer dans Outlook Drafts pour révision';
    draftBtn.onclick = async () => {
      if (draftBtn.disabled) return;
      btns.querySelectorAll('button').forEach(b => b.disabled = true);
      draftBtn.innerHTML = '&#8987;';
      try {
        const r = await fetch(`/raya/draft/${action.id}`, { method: 'POST' });
        const data = await r.json();
        _markActionInChat(action.id, data.ok ? 'draft' : 'err', data.message);
      } catch(e) {
        _markActionInChat(action.id, 'err', 'Erreur réseau');
      }
    };
    btns.appendChild(draftBtn);
  }

  btns.appendChild(cancelBtn);
  card.appendChild(btns);
  // Si action déjà terminée (depuis historique), afficher le statut sans boutons
  if (isDone) {
    btns.remove();
    const statusEl = document.createElement('div');
    statusEl.className = 'action-done-status';
    const icon = action.status === 'executed' ? '✅' : (action.status === 'cancelled' ? '⏹️' : '❌');
    statusEl.textContent = `${icon} ${action.label || action.action_type}`;
    card.appendChild(statusEl);
  }
  row.appendChild(card);
  // Insérer après le message Raya qui a généré l'action (via conversation_id = aria_memory_id).
  // S'il y a déjà d'autres cartes liées au même échange, on se place après la dernière.
  // Fallback pour actions legacy sans conversation_id : dernier message Raya visible.
  const convId = action.conversation_id;
  let inserted = false;
  if (convId && messagesEl) {
    const siblings = messagesEl.querySelectorAll(
      `[data-aria-memory-id="${convId}"], [data-conversation-id="${convId}"]`
    );
    const lastAnchor = siblings[siblings.length - 1];
    if (lastAnchor) {
      lastAnchor.insertAdjacentElement('afterend', row);
      inserted = true;
    }
  }
  if (!inserted && messagesEl) {
    // Smart fallback : chercher le dernier message Raya du DOM
    const rayaRows = messagesEl.querySelectorAll('.message-row.raya');
    const lastRaya = rayaRows[rayaRows.length - 1];
    if (lastRaya) {
      lastRaya.insertAdjacentElement('afterend', row);
      inserted = true;
    }
  }
  if (!inserted) appendToChat(row);
  scrollToBottom();
}

function _markActionInChat(actionId, status, message) {
  const row = messagesEl.querySelector(`[data-action-id="${actionId}"]`);
  if (!row) return;
  row.className = 'message-row action-done';
  const card = row.querySelector('.action-card');
  if (!card) return;
  // Retirer uniquement les boutons — garder le contenu du mail visible
  const btns = card.querySelector('.pending-btns');
  if (btns) btns.remove();
  // Ajouter le statut horodaté en bas de la carte
  const statusEl = document.createElement('div');
  statusEl.className = 'action-done-status';
  const icon = status === 'ok' ? '✅' : status === 'draft' ? '📁' : (status === 'cancelled' ? '⏹️' : '❌');
  const timeStr = new Date().toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
  statusEl.textContent = `${icon} ${message} — ${timeStr}`;
  card.appendChild(statusEl);
}

// Compat descendante (plus utilisé, conservé pour éviter crash si appelé)
function renderPendingActions(pendingList) {
  if (!pendingList || pendingList.length === 0) return;
  pendingList.forEach(a => appendPendingActionToChat(a));
}
