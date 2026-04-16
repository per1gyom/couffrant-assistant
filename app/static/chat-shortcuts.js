// chat-shortcuts.js — Raccourcis rapides avec pastilles colorées

const SHORTCUT_COLORS = ['#4f46e5','#059669','#d97706','#dc2626','#7c3aed','#0891b2','#db2777','#65a30d','#ea580c','#6366f1','#14b8a6','#f59e0b'];

const DEFAULT_SHORTCUTS = [
  { color:'#4f46e5', label:'Mails urgents', query:'Quels sont mes mails urgents ?' },
  { color:'#059669', label:'Planning', query:"Quel est mon planning aujourd'hui ?" },
  { color:'#d97706', label:'Chantiers', query:'Donne-moi un point sur mes chantiers en cours' },
  { color:'#dc2626', label:'Point semaine', query:'Fais-moi un point de la semaine' },
  { color:'#7c3aed', label:'Relances', query:'Quelles sont mes relances en attente ?' },
  { color:'#0891b2', label:'Trier mes mails', query:'__TRIAGE__' },
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
    const dot = `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${s.color||SHORTCUT_COLORS[i%SHORTCUT_COLORS.length]};flex-shrink:0"></span>`;
    btn.innerHTML = `${dot} ${s.label}`;
    if (shortcutsEditMode) { btn.onclick = () => removeShortcutDirect(i); btn.title = 'Cliquer pour supprimer'; }
    else { btn.onclick = () => s.query === '__TRIAGE__' ? startTriage() : quickAsk(s.query); }
    row.appendChild(btn);
  });
  const addBtn = document.createElement('button'); addBtn.className = 'quick-add-btn'; addBtn.textContent = '+ Ajouter';
  addBtn.style.display = shortcutsEditMode ? 'inline-flex' : 'none'; addBtn.onclick = openShortcuts; row.appendChild(addBtn);
  const editBtn = document.createElement('button'); editBtn.className = 'quick-edit-btn';
  editBtn.innerHTML = shortcutsEditMode ? '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>' : '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>';
  editBtn.title = shortcutsEditMode ? "Terminer" : 'Personnaliser';
  editBtn.onclick = toggleShortcutsEdit; row.appendChild(editBtn);
}

function toggleShortcutsEdit() { shortcutsEditMode = !shortcutsEditMode; renderQuickActions(); if (shortcutsEditMode) showToast('Cliquez sur un raccourci pour le supprimer', 'info', 2500); }
function removeShortcutDirect(index) { const s = getShortcuts(); const removed = s[index]; s.splice(index,1); saveShortcutsToStorage(s); renderQuickActions(); showToast(`"${removed.label}" supprimé`, 'ok', 2000); }
function openShortcuts() { pendingShortcuts = [...getShortcuts()]; renderShortcutList(); document.getElementById('modalShortcuts').classList.add('open'); }
function closeShortcuts() { document.getElementById('modalShortcuts').classList.remove('open'); }
function renderShortcutList() {
  document.getElementById('shortcutList').innerHTML = pendingShortcuts.map((s,i) => {
    const dot = `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${s.color||SHORTCUT_COLORS[i%SHORTCUT_COLORS.length]}"></span>`;
    return `<div class="shortcut-item">${dot} <span>${s.label}</span><button class="shortcut-del" onclick="removePendingShortcut(${i})">✕</button></div>`;
  }).join('');
}
function removePendingShortcut(i) { pendingShortcuts.splice(i,1); renderShortcutList(); }
function addShortcut() {
  const input = document.getElementById('newShortcutText'); const text = input.value.trim(); if (!text) return;
  const color = SHORTCUT_COLORS[pendingShortcuts.length % SHORTCUT_COLORS.length];
  pendingShortcuts.push({ color, label: text, query: text });
  renderShortcutList(); input.value = ''; input.focus();
}
function saveShortcuts() { saveShortcutsToStorage(pendingShortcuts); renderQuickActions(); closeShortcuts(); showToast('Raccourcis enregistrés ✓', 'ok'); }

document.getElementById('modalShortcuts').addEventListener('click', e => { if(e.target===document.getElementById('modalShortcuts')) closeShortcuts(); });
