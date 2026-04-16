// chat-signatures.js — Éditeur de signatures email WYSIWYG

let _sigList = [];
let _sigMailboxes = [];
let _sigEditing = null; // id en cours d'édition, null = nouvelle

// ── EMOJIS ────────────────────────────────────────────────────────────────
const SIG_EMOJIS = [
  // Communication
  '📞','📱','☎️','📟','📠','📧','✉️','📨','📩','📬','📭','📮',
  '🌐','🔗','💬','💭','📢','📣','🔔','🔕',
  // Localisation
  '📍','📌','🗺️','🏠','🏢','🏭','🏗️',
  // Business
  '💼','📁','📂','📄','📃','📑','📊','📈','📉','🗂️','📋','📝',
  '✅','☑️','✔️','❌','⚠️','ℹ️','💡','🔍','🔎',
  // Personnes
  '👤','👥','🤝','👋','✍️','🖊️','🖋️','📖','🎯',
  // Solaire / Énergie
  '☀️','⚡','🔋','💡','🌱','♻️','🌍','🌿','⚙️','🔧','🔨','🛠️',
  // Symboles pro
  '©️','®️','™️','🔒','🔓','🔑','🏆','⭐','🌟','💎','🎖️',
  // Flèches & Déco
  '▶️','◀️','🔺','🔻','➡️','⬅️','⬆️','⬇️','↗️','↘️',
  '—','·','|','»','«','•',
];

// ── POLICES ───────────────────────────────────────────────────────────────
const SIG_FONTS = [
  {label:'Arial', value:'Arial, Helvetica, sans-serif'},
  {label:'Georgia', value:'Georgia, serif'},
  {label:'Times New Roman', value:'"Times New Roman", Times, serif'},
  {label:'Calibri', value:'Calibri, sans-serif'},
  {label:'Verdana', value:'Verdana, Geneva, sans-serif'},
  {label:'Trebuchet MS', value:'"Trebuchet MS", Helvetica, sans-serif'},
  {label:'Tahoma', value:'Tahoma, Geneva, sans-serif'},
  {label:'Courier New', value:'"Courier New", Courier, monospace'},
];

const SIG_SIZES = ['10','11','12','13','14','16','18','20','22','24','28','32','36'];

// ── INIT ──────────────────────────────────────────────────────────────────
async function initSignaturesTab() {
  await Promise.all([_loadSigList(), _loadMailboxes()]);
  _renderSigList();
}

async function _loadSigList() {
  try {
    const r = await fetch('/signatures');
    _sigList = r.ok ? await r.json() : [];
  } catch(e) { _sigList = []; }
}

async function _loadMailboxes() {
  try {
    const r = await fetch('/signatures/mailboxes');
    _sigMailboxes = r.ok ? await r.json() : [];
  } catch(e) { _sigMailboxes = []; }
}

// ── LISTE DES SIGNATURES ──────────────────────────────────────────────────
function _renderSigList() {
  const zone = document.getElementById('sigListZone');
  if (!zone) return;
  if (_sigList.length === 0) {
    zone.innerHTML = '<div style="color:var(--text-muted);font-size:13px;padding:8px 0">Aucune signature — créez-en une ci-dessous.</div>';
  } else {
    zone.innerHTML = _sigList.map(s => `
      <div class="sig-item" data-id="${s.id}">
        <div class="sig-item-header">
          <span class="sig-item-name">${s.is_default ? '⭐ ' : ''}${_esc(s.name)}</span>
          <div class="sig-item-actions">
            <button class="sig-btn-sm" onclick="openSigEditor(${s.id})">✏️ Éditer</button>
            <button class="sig-btn-sm danger" onclick="deleteSig(${s.id})">🗑️</button>
          </div>
        </div>
        <div class="sig-item-emails">${(s.apply_to_emails||[]).length ? s.apply_to_emails.join(', ') : '<em>Toutes les boîtes</em>'}</div>
      </div>
    `).join('');
  }
  const editor = document.getElementById('sigEditorZone');
  if (editor) editor.style.display = 'none';
}

// ── OUVRIR L'ÉDITEUR ──────────────────────────────────────────────────────
function openSigEditor(sigId) {
  const sig = sigId ? _sigList.find(s => s.id === sigId) : null;
  _sigEditing = sigId || null;
  const zone = document.getElementById('sigEditorZone');
  if (!zone) return;
  zone.style.display = 'block';
  document.getElementById('sigEditorTitle').textContent = sig ? `Modifier : ${sig.name}` : 'Nouvelle signature';
  document.getElementById('sigName').value = sig ? sig.name : '';
  document.getElementById('sigDefault').checked = sig ? sig.is_default : false;
  // Contenu éditeur
  const ed = document.getElementById('sigEditor');
  ed.innerHTML = sig ? sig.signature_html : '';
  // Boîtes mail assignées
  _renderMailboxCheckboxes(sig ? (sig.apply_to_emails || []) : []);
  zone.scrollIntoView({behavior:'smooth', block:'start'});
}

function closeSigEditor() {
  const zone = document.getElementById('sigEditorZone');
  if (zone) zone.style.display = 'none';
  _sigEditing = null;
}

// ── CHECKBOXES BOÎTES MAIL ─────────────────────────────────────────────────
function _renderMailboxCheckboxes(selected) {
  const box = document.getElementById('sigMailboxes');
  if (!box) return;
  if (_sigMailboxes.length === 0) {
    box.innerHTML = '<span style="font-size:12px;color:var(--text-muted)">Aucune boîte connectée</span>';
    return;
  }
  box.innerHTML = _sigMailboxes.map(mb => `
    <label class="sig-mailbox-label">
      <input type="checkbox" value="${mb.address}" ${selected.includes(mb.address) ? 'checked' : ''}>
      <span>${mb.label}</span>
    </label>
  `).join('') + `
    <div style="font-size:11px;color:var(--text-muted);margin-top:4px">
      Si aucune case cochée → signature appliquée à toutes les boîtes
    </div>`;
}

// ── TOOLBAR ACTIONS ───────────────────────────────────────────────────────
function sigCmd(cmd, val) {
  document.getElementById('sigEditor').focus();
  document.execCommand(cmd, false, val || null);
}

function sigFont(sel) { if (sel.value) sigCmd('fontName', sel.value); }
function sigSize(sel) { if (sel.value) sigCmd('fontSize', sel.value); }
function sigColor(inp) { sigCmd('foreColor', inp.value); }
function sigBgColor(inp) { sigCmd('hiliteColor', inp.value); }

function sigInsertEmoji(e) { sigCmd('insertText', e); }

function sigInsertImage() {
  const input = document.createElement('input');
  input.type = 'file'; input.accept = 'image/*';
  input.onchange = async (ev) => {
    const file = ev.target.files[0]; if (!file) return;
    if (file.size > 500 * 1024) { showToast('Image trop lourde (max 500 KB)', 'err', 3000); return; }
    const reader = new FileReader();
    reader.onload = (e2) => {
      const img = `<img src="${e2.target.result}" style="max-width:500px;height:auto;" data-sig-img="1">`;
      document.getElementById('sigEditor').focus();
      document.execCommand('insertHTML', false, img);
      // Activer le redimensionnement sur l'image insérée
      setTimeout(_activateImgResize, 100);
    };
    reader.readAsDataURL(file);
  };
  input.click();
}

function _activateImgResize() {
  document.querySelectorAll('#sigEditor img[data-sig-img]').forEach(img => {
    if (img._resizeActive) return;
    img._resizeActive = true;
    img.style.cursor = 'pointer';
    img.title = 'Cliquez pour redimensionner';
    img.onclick = () => {
      const w = prompt('Largeur en pixels (actuel : ' + img.offsetWidth + 'px) :', img.offsetWidth);
      if (w && !isNaN(parseInt(w))) { img.style.width = parseInt(w) + 'px'; img.style.height = 'auto'; }
    };
  });
}

// ── SAUVEGARDE ────────────────────────────────────────────────────────────
async function saveSig() {
  const name = document.getElementById('sigName').value.trim();
  if (!name) { showToast('Nom requis', 'err', 2500); return; }
  const html = document.getElementById('sigEditor').innerHTML.trim();
  if (!html) { showToast('Contenu vide', 'err', 2500); return; }
  const isDefault = document.getElementById('sigDefault').checked;
  const checkedEmails = Array.from(document.querySelectorAll('#sigMailboxes input[type=checkbox]:checked'))
    .map(cb => cb.value);

  const payload = {name, signature_html: html, apply_to_emails: checkedEmails, is_default: isDefault};
  const url = _sigEditing ? `/signatures/${_sigEditing}` : '/signatures';
  const method = _sigEditing ? 'PATCH' : 'POST';

  try {
    const r = await fetch(url, {method, headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
    const data = await r.json();
    if (data.ok || data.id) {
      showToast(_sigEditing ? 'Signature mise à jour ✓' : 'Signature créée ✓', 'ok', 2500);
      await _loadSigList();
      _renderSigList();
    } else {
      showToast('Erreur : ' + (data.error || '?'), 'err', 4000);
    }
  } catch(e) { showToast('Erreur réseau', 'err', 3000); }
}

async function deleteSig(sigId) {
  const sig = _sigList.find(s => s.id === sigId);
  if (!confirm(`Supprimer "${sig?.name || 'cette signature'}" ?`)) return;
  try {
    await fetch(`/signatures/${sigId}`, {method: 'DELETE'});
    await _loadSigList(); _renderSigList();
    showToast('Signature supprimée', 'ok', 2000);
  } catch(e) { showToast('Erreur', 'err', 3000); }
}

// ── HELPERS ───────────────────────────────────────────────────────────────
function _esc(s) { return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
