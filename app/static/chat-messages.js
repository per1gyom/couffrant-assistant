// Raya Chat — Messages (addMessage, addLoading, bug report, ask_choice, pending actions)
// Chargé en 2ème dans raya_chat.html — dépend de chat-core.js

// --- MESSAGES ---
function addMessage(text, type, fileInfo=null, ariaMemoryId=null, timestamp=null) {
  const welcome = messagesEl.querySelector('.welcome');
  if (welcome) welcome.remove();
  const row = document.createElement('div'); row.className = 'message-row ' + type;

  // TIMESTAMP-2 : horodatage au-dessus des bulles
  const dateObj = timestamp ? new Date(timestamp) : new Date();
  const timeStr = dateObj.toLocaleString('fr-FR', {weekday:'short', day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit'});
  const lastTimeEl = messagesEl.querySelector('.msg-time:last-of-type');
  if (!lastTimeEl || lastTimeEl.textContent !== timeStr) {
    const timeEl = document.createElement('div');
    timeEl.className = 'msg-time';
    timeEl.style.cssText = 'font-size:11px;color:#999;text-align:center;width:100%;margin:8px 0 2px;';
    timeEl.textContent = timeStr;
    messagesEl.appendChild(timeEl);
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
        memDiv.innerHTML = `✅ ${memoryNotes.length} règle(s) mise(s) à jour`;
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
  } else {
    content.style.whiteSpace = 'pre-wrap'; content.textContent = text;
  }
  bubble.appendChild(content);
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
