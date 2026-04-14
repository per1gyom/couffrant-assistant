// chat-voice.js — Synthèse vocale + reconnaissance micro
// A3: paramètre fromAutoSpeak — skip silencieux sur iOS (WebKit autoplay policy)

function speak(text, btn, fromAutoSpeak) {
  // A3: iOS bloque l'autoplay audio sans geste utilisateur — skip autoSpeak sur iOS
  const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);
  if (fromAutoSpeak === true && isIOS) return;

  stopSpeech(); speakAborted = false; currentSpeakBtn = btn || null;
  if (currentSpeakBtn) { currentSpeakBtn.textContent='⏹ Stop'; currentSpeakBtn.classList.add('playing'); }
  fetch('/speak', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({text, speed: speakSpeed}) })
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
function setSpeakSpeed(newSpeed) {
  speakSpeed = Math.max(0.5, Math.min(2.5, newSpeed));
  showToast('Vitesse de lecture : ' + speakSpeed.toFixed(1) + 'x', 'ok', 2000);
}

function toggleMic() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { alert('Reconnaissance vocale non supportée.\nUtilisez Chrome ou Edge.'); return; }
  if (isListening) stopListening(); else startListening();
}
function startListening() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition; if (!SR) return;
  const target = _micTarget || inputEl;
  finalTextBase = _micTarget ? _finalTextBaseTarget : inputEl.value;
  const rec = new SR(); rec.lang='fr-FR'; rec.continuous=false; rec.interimResults=true; rec.maxAlternatives=1;
  rec.onstart = () => {
    isListening=true;
    if (!_micTarget) { micBtn.classList.add('listening'); micBtn.textContent='⏹'; micStatus.classList.add('visible'); inputWrapper.classList.add('mic-active'); }
  };
  rec.onresult = (e) => {
    clearSilenceTimer(); let interim='', final='';
    for (let i=e.resultIndex; i<e.results.length; i++) {
      if (e.results[i].isFinal) final+=e.results[i][0].transcript+' '; else interim+=e.results[i][0].transcript;
    }
    if (interim) { target.value=(finalTextBase+' '+interim).trim(); if (!_micTarget) { target.classList.add('interim'); autoResize(target); } }
    if (final) { finalTextBase=(finalTextBase+' '+final).trim(); target.value=finalTextBase; if (!_micTarget) { target.classList.remove('interim'); autoResize(target); } }
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
function stopListening() {
  isListening=false; clearSilenceTimer(); cleanupMicUI();
  if (!_micTarget) { inputEl.classList.remove('interim'); if(inputEl.value) autoResize(inputEl); inputEl.focus(); }
}
function cleanupMicUI() {
  if (!_micTarget) {
    micBtn.classList.remove('listening'); micBtn.textContent='🎤';
    micStatus.classList.remove('visible'); inputWrapper.classList.remove('mic-active');
  }
}
