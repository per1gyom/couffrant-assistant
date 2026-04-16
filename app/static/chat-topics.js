// chat-topics.js v3 — Design miroir des raccourcis (sans statuts actif/pause)

let _topicsData = { topics: [] };
let topicsEditMode = false;

// Stubs compatibilité
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
  const topics = _topicsData.topics || _topicsData || [];
  el.innerHTML = '';

  topics.forEach(t => {
    const btn = document.createElement('button');
    btn.className = 'quick-btn' + (topicsEditMode ? ' edit-mode' : '');
    if (topicsEditMode) {
      btn.innerHTML = `<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${t.title}</span><span class="shortcut-x">\u2715</span>`;
      btn.querySelector('.shortcut-x').onclick = (e) => { e.stopPropagation(); deleteTopic(t.id); };
      btn.onclick = () => renameTopic(t.id, t.title);
      btn.title = 'Cliquer pour renommer';
    } else {
      btn.innerHTML = `<span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${t.title}</span>`;
      btn.onclick = () => askAboutTopic(t.title);
      btn.title = t.title;
    }
    el.appendChild(btn);
  });

  const addBtn = document.createElement('button');
  addBtn.className = 'quick-add-btn';
  addBtn.textContent = '+ Ajouter';
  addBtn.style.display = topicsEditMode ? 'inline-flex' : 'none';
  addBtn.onclick = () => createTopic();
  el.appendChild(addBtn);

  const editBtn = document.createElement('button');
  editBtn.className = 'quick-edit-btn';
  editBtn.innerHTML = topicsEditMode
    ? '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>'
    : '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>';
  editBtn.title = topicsEditMode ? 'Terminer' : 'G\u00e9rer mes sujets';
  editBtn.onclick = toggleTopicsEdit;
  el.appendChild(editBtn);
}

function toggleTopicsEdit() {
  topicsEditMode = !topicsEditMode;
  renderTopicsSidebar();
  if (topicsEditMode) showToast('Clic\u00a0= renommer \u00b7 \u2715\u00a0= supprimer', 'info', 2500);
}

function askAboutTopic(title) {
  const inp = document.getElementById('input');
  if (inp) {
    inp.value = 'Fais-moi un point sur le sujet\u00a0: ' + title;
    if (typeof sendMessage === 'function') sendMessage();
  }
}

async function createTopic() {
  const title = prompt('Nom du nouveau sujet\u00a0:');
  if (!title || !title.trim()) return;
  try {
    const r = await fetch('/topics', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ title: title.trim() })
    });
    if (r.ok) {
      await loadTopics();
      renderTopicsSidebar();
      showToast('Sujet cr\u00e9\u00e9\u00a0: ' + title.trim(), 'ok', 2000);
    }
  } catch(e) { showToast('Erreur cr\u00e9ation sujet', 'err', 3000); }
}

async function deleteTopic(id) {
  try {
    await fetch('/topics/' + id, { method: 'DELETE' });
    await loadTopics();
    renderTopicsSidebar();
    showToast('Sujet supprim\u00e9', 'ok', 2000);
  } catch(e) { showToast('Erreur suppression', 'err', 3000); }
}

async function renameTopic(id, currentTitle) {
  const newTitle = prompt('Nouveau nom du sujet\u00a0:', currentTitle);
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

// Stub compatibilité descendante
async function cycleTopic(id, current) {}
