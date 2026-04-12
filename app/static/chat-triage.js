// chat-triage.js — Triage mails

async function startTriage() {
  stopSpeech(); triageBar.classList.remove('visible');
  const loading = addLoading();
  const data = await (await fetch('/triage-queue')).json(); loading.remove();
  triageQueue = data.mails || [];
  if (triageQueue.length===0) { const row=addMessage('Aucun mail en attente.','raya'); if(autoSpeak)speak('Aucun mail.',row.querySelector('.speak-btn')); return; }
  const intro = triageQueue.length+" mails à trier. C'est parti !";
  const introRow = addMessage(intro,'raya'); if(autoSpeak) speak(intro, introRow.querySelector('.speak-btn'));
  setTimeout(()=>nextTriage(), 1500);
}

function nextTriage() {
  if (triageQueue.length===0) { triageBar.classList.remove('visible'); const row=addMessage('Triage terminé !','raya'); if(autoSpeak) speak('Triage terminé !',row.querySelector('.speak-btn')); triageCurrent=null; return; }
  triageCurrent = triageQueue.shift();
  const msg='De : '+(triageCurrent.from_email||'Inconnu')+'\nSujet : '+(triageCurrent.subject||'(Sans objet)')+'\n\n'+(triageCurrent.raw_body_preview||'').slice(0,200)+'\n\n— Que je fasse ? ('+(triageQueue.length+' restants)');
  const row=addMessage(msg,'raya'); if(autoSpeak) speak(msg,row.querySelector('.speak-btn'));
  triageBar.classList.add('visible');
}

async function handleTriage(action) {
  if (!triageCurrent) return; triageBar.classList.remove('visible'); stopSpeech();
  if (action==='skip') { addMessage('Passé.','raya'); setTimeout(()=>nextTriage(),500); return; }
  const actionMap={
    'archive':'Archive le mail '+triageCurrent.message_id,
    'delete':'Supprime le mail '+triageCurrent.message_id,
    'reply':'Prépare une réponse pour le mail '+triageCurrent.message_id
  };
  const loading=addLoading();
  try {
    const data=(await (await fetch('/raya',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:actionMap[action]})})).json()); loading.remove();
    const row=addMessage(data.answer,'raya'); if(autoSpeak) speak(data.answer,row.querySelector('.speak-btn'));
    if (data.actions && data.actions.some(a=>a.startsWith('✅'))) showToast('Action effectuée ✓','ok');
  } catch { loading.remove(); }
  setTimeout(()=>nextTriage(),3000);
}
