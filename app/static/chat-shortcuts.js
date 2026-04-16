// chat-shortcuts.js v2 — Raccourcis DB (titre + prompt personnalisé + couleur)

const SHORTCUT_COLORS = ['#4f46e5','#059669','#d97706','#dc2626','#7c3aed','#0891b2','#db2777','#65a30d','#ea580c','#6366f1','#14b8a6','#f59e0b'];

let _shortcuts = [];
let shortcutsEditMode = false;
let _editingShortcutId = null;
let _editingShortcutColor = SHORTCUT_COLORS[0];

async function initShortcuts() {
  try {
    const r = await fetch('/shortcuts');
    _shortcuts = r.ok ? await r.json() : [];
  } catch(e) { console.warn('[Shortcuts] load error', e); _shortcuts = []; }
  renderQuickActions();
}

function renderQuickActions() {
  const row = document.getElementById('quickRow');
  if (!row) return;
  row.innerHTML = '';
  _shortcuts.forEach(s => {
    const btn = document.createElement('button');
    btn.className = 'quick-btn' + (shortcutsEditMode ? ' edit-mode' : '');
    const dot = `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${s.color};flex-shrink:0"></span>`;
    if (shortcutsEditMode) {
      btn.innerHTML = `${dot}<span style="flex:1;overflow:hidden;text-overflow:ellipsis;margin-left:6px">${s.label}</span><span class="shortcut-x">\u2715</span>`;
      const xBtn = btn.querySelector('.shortcut-x');
      xBtn.onclick = (e) => { e.stopPropagation(); deleteShortcut(s.id); };
      btn.onclick = () => openShortcutEdit(s);
      btn.title = 'Cliquer pour éditer';
    } else {
      btn.innerHTML = `${dot} ${s.label}`;
      btn.onclick = () => s.prompt === '__TRIAGE__' ? startTriage() : quickAsk(s.prompt);
    }
    row.appendChild(btn);
  });

  const addBtn = document.createElement('button');
  addBtn.className = 'quick-add-btn';
  addBtn.textContent = '+ Ajouter';
  addBtn.style.display = shortcutsEditMode ? 'inline-flex' : 'none';
  addBtn.onclick = () => openShortcutEdit(null);
  row.appendChild(addBtn);

  const editBtn = document.createElement('button');
  editBtn.className = 'quick-edit-btn';
  editBtn.innerHTML = shortcutsEditMode
    ? '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>'
    : '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>';
  editBtn.title = shortcutsEditMode ? 'Terminer' : 'Personnaliser';
  editBtn.onclick = toggleShortcutsEdit;
  row.appendChild(editBtn);
}

function toggleShortcutsEdit() {
  shortcutsEditMode = !shortcutsEditMode;
  renderQuickActions();
  if (shortcutsEditMode) showToast('Clic = éditer · \u2715 = supprimer', 'info', 2500);
}

async function deleteShortcut(id) {
  const s = _shortcuts.find(x => x.id === id);
  if (!s) return;
  try {
    await fetch('/shortcuts/' + id, { method: 'DELETE' });
    _shortcuts = _shortcuts.filter(x => x.id !== id);
    renderQuickActions();
    showToast(`"${s.label}" supprimé`, 'ok', 2000);
  } catch(e) { showToast('Erreur suppression', 'err', 3000); }
}

function openShortcutEdit(shortcut) {
  _editingShortcutId = shortcut ? shortcut.id : null;
  _editingShortcutColor = shortcut ? shortcut.color : SHORTCUT_COLORS[_shortcuts.length % SHORTCUT_COLORS.length];
  document.getElementById('shortcutEditLabel').value = shortcut ? shortcut.label : '';
  document.getElementById('shortcutEditPrompt').value = shortcut ? shortcut.prompt : '';
  document.getElementById('shortcutEditTitle').textContent = shortcut ? 'Modifier le raccourci' : 'Nouveau raccourci';
  renderColorPicker();
  document.getElementById('modalShortcutEdit').classList.add('open');
}

function closeShortcutEdit() {
  document.getElementById('modalShortcutEdit').classList.remove('open');
}

function renderColorPicker() {
  const el = document.getElementById('shortcutColorPicker');
  el.innerHTML = SHORTCUT_COLORS.map(c => {
    const sel = c === _editingShortcutColor;
    const shadow = sel ? `box-shadow:0 0 0 2px #fff,0 0 0 4px ${c}` : '';
    return `<span class="color-dot" style="background:${c};${shadow}" onclick="selectColor('${c}')" title="${c}"></span>`;
  }).join('');
}

function selectColor(c) {
  _editingShortcutColor = c;
  renderColorPicker();
}

async function saveShortcutEdit() {
  const label = document.getElementById('shortcutEditLabel').value.trim();
  const prompt = document.getElementById('shortcutEditPrompt').value.trim();
  if (!label) { showToast('Le titre est requis', 'err', 2500); return; }
  if (!prompt) { showToast('Le prompt est requis', 'err', 2500); return; }
  try {
    if (_editingShortcutId) {
      const r = await fetch('/shortcuts/' + _editingShortcutId, {
        method: 'PATCH', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ label, prompt, color: _editingShortcutColor })
      });
      const data = await r.json();
      if (data.id) _shortcuts = _shortcuts.map(s => s.id === _editingShortcutId ? data : s);
      showToast('Raccourci mis à jour \u2713', 'ok');
    } else {
      const r = await fetch('/shortcuts', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ label, prompt, color: _editingShortcutColor })
      });
      const data = await r.json();
      if (data.id) _shortcuts.push(data);
      showToast('Raccourci ajouté \u2713', 'ok');
    }
    closeShortcutEdit();
    renderQuickActions();
  } catch(e) { showToast('Erreur sauvegarde', 'err', 3000); }
}

document.getElementById('modalShortcutEdit').addEventListener('click', e => {
  if (e.target === document.getElementById('modalShortcutEdit')) closeShortcutEdit();
});
