// chat-topics.js v2 — Sujets intégrés dans la sidebar (plus de drawer noir)

let _topicsData = { section_title: 'Mes sujets', topics: [] };

// Stubs compatibilité (anciens appels peuvent subsister)
function toggleTopics() {}
function openTopics() { initTopicsSidebar(); }
function closeTopics() {}

async function initTopicsSidebar() {
  await loadTopics();
  renderTopicsSidebar();
}

async function loadTopics() {
  try {
    const r = await fetch('/topics');
    if (r.ok) _topicsData = await r.json();
  } catch(e) { console.warn('[Topics] load error:', e); }
}

function renderTopicsSidebar() {
  const el = document.getElementById('topicsSidebarList');
  if (!el) return;
  const { topics } = _topicsData;
  let html = `<div class="topics-sidebar-add">
    <input type="text" id="newTopicInput" placeholder="Nouveau sujet…" maxlength="255"
      onkeydown="if(event.key==='Enter')createTopic()">
    <button onclick="createTopic()" title="Ajouter">+</button>
  </div>`;
  if (topics.length === 0) {
    html += '<div style="font-size:12px;color:var(--text-muted);padding:2px 8px 6px;">Aucun sujet pour le moment.</div>';
  } else {
    topics.forEach(t => {
      const st = t.status === 'active' ? '\uD83D\uDFE2' : t.status === 'paused' ? '\u23F8' : '\uD83D\uDCE6';
      const op = t.status === 'archived' ? 'opacity:0.45;' : t.status === 'paused' ? 'opacity:0.65;' : '';
      html += `<div class="topic-sidebar-item" style="${op}">
        <span class="topic-sb-status">${st}</span>
        <span class="topic-sb-title" onclick="askAboutTopic('${t.title.replace(/'/g,"\\'").replace(/"/g,'&quot;')}')" title="${t.title}">${t.title}</span>
        <div class="topic-sidebar-actions">
          <button onclick="cycleTopic(${t.id},'${t.status}')" title="Changer statut">🔄</button>
          <button onclick="renameTopic(${t.id},'${t.title.replace(/'/g,"\\'").replace(/"/g,'&quot;')}')" title="Renommer">✏️</button>
          <button onclick="deleteTopic(${t.id})" title="Supprimer" style="color:var(--text-muted);font-size:13px">✕</button>
        </div>
      </div>`;
    });
  }
  el.innerHTML = html;
}

function askAboutTopic(title) {
  if (typeof inputEl !== 'undefined') {
    inputEl.value = 'Fais-moi un point sur le sujet : ' + title;
    sendMessage();
  }
}

async function createTopic() {
  const input = document.getElementById('newTopicInput');
  const title = (input ? input.value : '').trim();
  if (!title) return;
  try {
    const r = await fetch('/topics', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ title })
    });
    if (r.ok) {
      input.value = '';
      await loadTopics();
      renderTopicsSidebar();
      showToast('Sujet créé : ' + title, 'ok', 2000);
    }
  } catch(e) { showToast('Erreur création sujet', 'err', 3000); }
}

async function deleteTopic(id) {
  if (!confirm('Supprimer ce sujet ?')) return;
  try {
    await fetch('/topics/' + id, { method: 'DELETE' });
    await loadTopics();
    renderTopicsSidebar();
  } catch(e) { showToast('Erreur suppression', 'err', 3000); }
}

async function cycleTopic(id, current) {
  const next = current === 'active' ? 'paused' : current === 'paused' ? 'archived' : 'active';
  try {
    await fetch('/topics/' + id, {
      method: 'PATCH', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ status: next })
    });
    await loadTopics();
    renderTopicsSidebar();
  } catch(e) { showToast('Erreur changement statut', 'err', 3000); }
}

async function renameTopic(id, currentTitle) {
  const newTitle = prompt('Nouveau nom du sujet :', currentTitle);
  if (!newTitle || newTitle.trim() === currentTitle) return;
  try {
    await fetch('/topics/' + id, {
      method: 'PATCH', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ title: newTitle.trim() })
    });
    await loadTopics();
    renderTopicsSidebar();
  } catch(e) { showToast('Erreur renommage', 'err', 3000); }
}
