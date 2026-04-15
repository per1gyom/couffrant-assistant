// Raya Chat — Topics (sujets utilisateur)
// Panneau latéral pour gérer les sujets/projets
// Endpoints : GET/POST/PATCH/DELETE /topics, PATCH /topics/settings

let _topicsOpen = false;
let _topicsData = { section_title: 'Mes sujets', topics: [] };

function toggleTopics() {
  _topicsOpen ? closeTopics() : openTopics();
}

async function openTopics() {
  _topicsOpen = true;
  await loadTopics();
  renderTopicsPanel();
  document.getElementById('topicsOverlay').classList.add('open');
  document.getElementById('topicsPanel').classList.add('open');
}

function closeTopics() {
  _topicsOpen = false;
  document.getElementById('topicsOverlay').classList.remove('open');
  document.getElementById('topicsPanel').classList.remove('open');
}

async function loadTopics() {
  try {
    const r = await fetch('/topics');
    if (r.ok) _topicsData = await r.json();
  } catch(e) { console.warn('[Topics] load error:', e); }
}

function renderTopicsPanel() {
  const panel = document.getElementById('topicsList');
  if (!panel) return;
  const { section_title, topics } = _topicsData;
  let html = '';
  // Titre section éditable
  html += `<div class="topics-section-title" onclick="editSectionTitle(this)">${section_title} ✏️</div>`;
  // Bouton créer
  html += `<div class="topics-add">
    <input type="text" id="newTopicInput" placeholder="Nouveau sujet…" maxlength="255"
      onkeydown="if(event.key==='Enter')createTopic()">
    <button onclick="createTopic()">+</button>
  </div>`;
  // Liste
  if (topics.length === 0) {
    html += '<div class="topics-empty">Aucun sujet pour le moment.<br>Crée ton premier sujet ci-dessus.</div>';
  } else {
    topics.forEach(t => {
      const statusClass = t.status === 'active' ? 'active' : t.status === 'paused' ? 'paused' : 'archived';
      const statusLabel = t.status === 'active' ? '🟢' : t.status === 'paused' ? '⏸️' : '📦';
      html += `<div class="topic-card ${statusClass}" data-id="${t.id}">
        <div class="topic-main" onclick="askAboutTopic('${t.title.replace(/'/g, "\\'")}')">
          <span class="topic-status">${statusLabel}</span>
          <span class="topic-title">${t.title}</span>
        </div>
        <div class="topic-actions">
          <button onclick="cycleTopic(${t.id},'${t.status}')" title="Changer statut">🔄</button>
          <button onclick="renameTopic(${t.id},'${t.title.replace(/'/g, "\\'")}')" title="Renommer">✏️</button>
          <button onclick="deleteTopic(${t.id})" title="Supprimer">🗑️</button>
        </div>
      </div>`;
    });
  }
  panel.innerHTML = html;
}

function askAboutTopic(title) {
  closeTopics();
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
      renderTopicsPanel();
      showToast('Sujet créé : ' + title, 'ok', 2000);
    }
  } catch(e) { showToast('Erreur création sujet', 'err', 3000); }
}

async function deleteTopic(id) {
  if (!confirm('Supprimer ce sujet ?')) return;
  try {
    await fetch('/topics/' + id, { method: 'DELETE' });
    await loadTopics();
    renderTopicsPanel();
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
    renderTopicsPanel();
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
    renderTopicsPanel();
  } catch(e) { showToast('Erreur renommage', 'err', 3000); }
}

async function editSectionTitle(el) {
  const current = _topicsData.section_title || 'Mes sujets';
  const newTitle = prompt('Titre de la section :', current);
  if (!newTitle || newTitle.trim() === current) return;
  try {
    await fetch('/topics/settings', {
      method: 'PATCH', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ section_title: newTitle.trim() })
    });
    _topicsData.section_title = newTitle.trim();
    renderTopicsPanel();
  } catch(e) { showToast('Erreur modification titre', 'err', 3000); }
}

// Injection CSS pour le panneau Topics
(function() {
  const style = document.createElement('style');
  style.textContent = `
    .topics-drawer { z-index: 1001; }
    .topics-section-title {
      font-size: 15px; font-weight: 700; color: var(--accent, #6366f1);
      padding: 8px 12px; cursor: pointer; border-radius: 8px;
      transition: background .2s;
    }
    .topics-section-title:hover { background: rgba(99,102,241,.08); }
    .topics-add {
      display: flex; gap: 8px; padding: 8px 0; margin-bottom: 8px;
    }
    .topics-add input {
      flex: 1; padding: 8px 12px; border: 1px solid var(--border, #e5e7eb);
      border-radius: 8px; font-size: 14px; background: var(--bg, #fff);
      color: var(--text, #1e293b);
    }
    .topics-add button {
      width: 38px; height: 38px; border-radius: 8px; border: none;
      background: var(--accent, #6366f1); color: white; font-size: 20px;
      cursor: pointer; font-weight: 700;
    }
    .topics-empty {
      text-align: center; color: var(--text-muted, #94a3b8);
      padding: 24px 12px; font-size: 14px; line-height: 1.5;
    }
    .topic-card {
      display: flex; align-items: center; justify-content: space-between;
      padding: 10px 12px; border-radius: 8px; margin-bottom: 4px;
      border: 1px solid var(--border, #e5e7eb); transition: all .2s;
    }
    .topic-card:hover { border-color: var(--accent, #6366f1); }
    .topic-card.paused { opacity: 0.7; }
    .topic-card.archived { opacity: 0.5; }
    .topic-main {
      flex: 1; cursor: pointer; display: flex; align-items: center; gap: 8px;
    }
    .topic-status { font-size: 12px; }
    .topic-title { font-size: 14px; font-weight: 500; }
    .topic-actions {
      display: flex; gap: 2px; opacity: 0; transition: opacity .2s;
    }
    .topic-card:hover .topic-actions { opacity: 1; }
    .topic-actions button {
      background: none; border: none; cursor: pointer;
      font-size: 13px; padding: 4px; border-radius: 4px;
    }
    .topic-actions button:hover { background: rgba(0,0,0,.06); }
  `;
  document.head.appendChild(style);
})();
