// chat-shortcuts.js — Raccourcis rapides

const DEFAULT_SHORTCUTS = [
  { icon:'📬', label:'Mails urgents', query:'Quels sont mes mails urgents ?' },
  { icon:'📅', label:'Planning', query:"Quel est mon planning aujourd'hui ?" },
  { icon:'⚡', label:'Chantiers', query:'Donne-moi un point sur mes chantiers en cours' },
  { icon:'📊', label:'Point semaine', query:'Fais-moi un point de la semaine' },
  { icon:'🔔', label:'Relances', query:'Quelles sont mes relances en attente ?' },
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
    `<div class="shortcut-item"><span>${s.icon||''} ${s.label}</span><button class="shortcut-del" onclick="removePendingShortcut(${i})">✕</button></div>`
  ).join('');
}
function removePendingShortcut(i) { pendingShortcuts.splice(i,1); renderShortcutList(); }
function addShortcut() {
  const input = document.getElementById('newShortcutText'); const text = input.value.trim(); if (!text) return;
  const emojis = ['💬','🔧','📌','?ddc2','📝','🎯','💡','🔍'];
  pendingShortcuts.push({ icon: emojis[pendingShortcuts.length % emojis.length], label: text, query: text });
  renderShortcutList(); input.value = ''; input.focus();
}
function saveShortcuts() { saveShortcutsToStorage(pendingShortcuts); renderQuickActions(); closeShortcuts(); showToast('Raccourcis enregistrés ✓', 'ok'); }

document.getElementById('modalShortcuts').addEventListener('click', e => { if(e.target===document.getElementById('modalShortcuts')) closeShortcuts(); });
