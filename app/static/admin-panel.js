/* Admin Panel — JS */
let allRules=[], allInsights=[];
let currentEditUser=null, usernameToDelete=null;
let isSuperAdmin=false, currentUserScope='', currentUserTenantId='';
// Helper : true si l user est admin Raya OU super_admin (hardcode ou non).
// Utilise partout a la place de currentUserScope==='admin' qui ne reconnait
// pas les super_admin et les fait basculer sur les endpoints /tenant en 403.
function isAdminOrSuper(){ return currentUserScope==='admin' || currentUserScope==='super_admin'; }

// Modale de confirmation "Etes-vous sur ?" pour les actions destructives.
// Remplace confirm() natif qui bloque le thread et empeche le repaint.
// Retourne une Promise<boolean>, true si Oui, false si Non.
// Usage : if(!(await confirmAction('Titre', 'Message'))) return;
function confirmAction(title, message, okLabel='Oui', cancelLabel='Non'){
  return new Promise(resolve => {
    // Supprime toute modale existante pour eviter les doublons
    const old = document.getElementById('raya-confirm-modal');
    if(old) old.remove();
    const overlay = document.createElement('div');
    overlay.id = 'raya-confirm-modal';
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:99999;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(4px)';
    overlay.innerHTML = `
      <div style="background:#1a1a1a;border:1px solid #333;border-radius:8px;max-width:500px;width:90%;padding:24px;box-shadow:0 10px 40px rgba(0,0,0,.5)">
        <h3 style="margin:0 0 12px;color:#fff;font-size:18px">${title}</h3>
        <div style="color:#ccc;font-size:14px;line-height:1.5;margin-bottom:20px;white-space:pre-line">${message}</div>
        <div style="display:flex;gap:10px;justify-content:flex-end">
          <button id="raya-confirm-cancel" class="btn btn-ghost" style="padding:8px 18px">${cancelLabel}</button>
          <button id="raya-confirm-ok" class="btn btn-danger" style="padding:8px 18px">${okLabel}</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    const cleanup = (val) => { overlay.remove(); resolve(val); };
    document.getElementById('raya-confirm-ok').onclick = () => cleanup(true);
    document.getElementById('raya-confirm-cancel').onclick = () => cleanup(false);
    overlay.onclick = (e) => { if(e.target === overlay) cleanup(false); };
    // Esc pour annuler
    const onKey = (e) => { if(e.key==='Escape'){ document.removeEventListener('keydown', onKey); cleanup(false); } };
    document.addEventListener('keydown', onKey);
  });
}
let _lastTenants=[];
let currentEditTenantId=null, tenantToDelete=null;

function updateClock(){document.getElementById('clock').textContent=new Date().toLocaleString('fr-FR',{weekday:'short',day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit',second:'2-digit'});}
setInterval(updateClock,1000); updateClock();

async function checkHealth(){
  try{const d=await(await fetch('/health')).json();document.getElementById('health-dot').className='dot';document.getElementById('health-text').textContent=d.memory_module?'Online • mémoire OK':'Online • mémoire KO';}
  catch(e){document.getElementById('health-dot').className='dot off';document.getElementById('health-text').textContent='Hors ligne';}
}
checkHealth();setInterval(checkHealth,30000);

function switchTab(name){
  const tabs=['memory','users','rules','insights','actions','companies','profile'];
  document.querySelectorAll('.tab').forEach((t,i)=>t.classList.toggle('active',tabs[i]===name));
  document.querySelectorAll('.section').forEach(s=>s.classList.remove('active'));
  document.getElementById('tab-'+name).classList.add('active');
  if(name==='memory') loadMemoryStatus();
  if(name==='users') loadUsers();
  if(name==='rules'){populateUserFilters();loadRules();}
  if(name==='insights'){populateUserFilters();loadInsights();}
  if(name==='usage') loadUsage();
  if(name==='companies'){ loadCompanies(); loadSystemAlerts(); }
  if(name==='profile') loadProfile();
}

const fmt=n=>(n||0).toLocaleString('fr-FR');
const fmtDate=d=>d?new Date(d).toLocaleDateString('fr-FR',{day:'2-digit',month:'short',year:'numeric'}):'—';
const fmtDateShort=d=>{if(!d)return'—';const dt=new Date(d);return dt.toLocaleDateString('fr-FR',{day:'2-digit',month:'short'})+' '+dt.toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'});};

function normalizeTenantId(value){
  const withoutAccents=value.normalize('NFD').replace(/[\u0300-\u036f]/g,'');
  return withoutAccents.toLowerCase().replace(/[\s\-]+/g,'_').replace(/[^a-z0-9_]/g,'');
}

async function loadMemoryStatus(){
  try{
  const data=await(await fetch('/admin/memory-status')).json();
  const tot=k=>data.reduce((s,u)=>s+(u[k]||0),0);
  document.getElementById('memory-stats').innerHTML=`
    <div class="stat-card"><div class="stat-label">Utilisateurs</div><div class="stat-value accent">${data.length}</div></div>
    <div class="stat-card"><div class="stat-label">Mails</div><div class="stat-value">${fmt(tot('mails'))}</div></div>
    <div class="stat-card"><div class="stat-label">Conversations</div><div class="stat-value">${fmt(tot('conv')||tot('conversations'))}</div></div>
    <div class="stat-card"><div class="stat-label">Règles</div><div class="stat-value green">${fmt(tot('rules'))}</div></div>
    <div class="stat-card"><div class="stat-label">Insights</div><div class="stat-value">${fmt(tot('insights'))}</div></div>`;
  document.getElementById('memory-tbody').innerHTML=data.map(u=>`
    <tr><td><strong class="mono">${u.username}</strong></td><td style="font-size:12px;color:var(--text2)">${u.email||'—'}</td>
    <td><span class="badge ${u.scope==='super_admin'?'badge-blue':u.scope==='admin'?'badge-blue':u.scope==='tenant_admin'?'badge-green':'badge-gray'}">${u.scope||'tenant_user'}</span></td>
    <td class="mono">${fmt(u.conv||u.conversations||0)}</td>
    <td><span class="badge badge-green">${fmt(u.rules||0)}</span></td>
    <td class="mono">${fmt(u.insights||0)}</td><td class="mono">${fmt(u.mails||0)}</td></tr>`).join('');
  }catch(e){
    document.getElementById('memory-stats').innerHTML='<div class="stat-card"><div class="stat-label">Erreur</div><div class="stat-value">—</div></div>';
    document.getElementById('memory-tbody').innerHTML='<tr><td colspan="7" style="color:var(--red)">Erreur de chargement</td></tr>';
    console.warn('[Admin] loadMemoryStatus:', e);
  }
}

async function loadUsers(){
  document.getElementById('users-tbody').innerHTML='<tr class="loading-row"><td colspan="6"><span class="loader"></span> Chargement...</td></tr>';
  const data=await(await fetch('/admin/users')).json();
  const locked=data.filter(u=>u.account_locked).length;
  const lcEl=document.getElementById('locked-count');
  lcEl.textContent=locked>0?`⚠️ ${locked} compte(s) bloqué(s)`:'';
  lcEl.style.color=locked>0?'var(--red)':'';
  document.getElementById('users-tbody').innerHTML=data.map(u=>`
    <tr class="${u.account_locked?'row-locked':u.suspended?'row-locked':''}">
      <td><strong class="mono">${u.username}</strong>${u.account_locked?'<span class="badge badge-red" style="margin-left:7px;font-size:9px">🔒 BLOQUÉ</span>':''}${u.suspended?'<span class="badge badge-yellow" style="margin-left:7px;font-size:9px">⏸️ SUSPENDU</span>':''}${u.must_reset_password&&!u.account_locked?'<span class="badge badge-yellow" style="margin-left:7px;font-size:9px">⚠️ Reset MDP</span>':''}</td>
      <td style="font-size:12px;color:var(--text2)">${u.email||'—'}</td>
      <td><span class="badge ${u.scope==='super_admin'?'badge-blue':u.scope==='admin'?'badge-blue':u.scope==='tenant_admin'?'badge-green':'badge-gray'}">${u.scope||'tenant_user'}</span></td>
      <td class="mono" style="font-size:11px;color:var(--text2)">${fmtDateShort(u.last_login)}</td>
      <td class="mono" style="font-size:11px;color:var(--text3)">${fmtDate(u.created_at)}</td>
      <td style="display:flex;gap:6px;flex-wrap:wrap">
        <button class="btn btn-ghost" style="padding:4px 9px;font-size:11px" onclick="showTools('${u.username}')">Outils</button>
        <button class="btn btn-accent" style="padding:4px 9px;font-size:11px" onclick="editUser('${u.username}','${u.email||''}','${u.scope||'tenant_user'}','${u.phone||''}')">Modifier</button>
        <button class="btn btn-ghost" style="padding:4px 9px;font-size:11px" onclick="seedUser('${u.username}')">🌱</button>
        ${u.suspended?`<button class="btn btn-unlock" style="padding:4px 9px;font-size:11px" onclick="unsuspendUser('${u.username}')">▶️ Réactiver</button>`:`<button class="btn btn-ghost" style="padding:4px 9px;font-size:11px;color:var(--yellow)" onclick="suspendUser('${u.username}')">⏸️</button>`}
        ${u.account_locked?`<button class="btn btn-unlock" style="padding:4px 9px;font-size:11px" onclick="unlockUser('${u.username}')">🔓 Débloquer</button>`:''}
        ${u.scope!=='admin'&&u.scope!=='super_admin'?`<button class="btn btn-danger" style="padding:4px 9px;font-size:11px" onclick="askDeleteUser('${u.username}')">Suppr.</button>`:''}
      </td>
    </tr>`).join('');
}
async function showTools(username){
  const section=document.getElementById('tools-section'),grid=document.getElementById('tools-grid');
  document.getElementById('tools-title').innerHTML=`Outils de <strong style="color:#fff">${username}</strong>`;
  grid.innerHTML='<span class="loader"></span>';section.style.display='block';
  section.scrollIntoView({behavior:'smooth',block:'nearest'});
  const tools=await(await fetch(`/admin/user-tools/${username}`)).json();
  if(!tools.length){grid.innerHTML='<p style="color:var(--text3);font-family:var(--mono);font-size:12px">Aucun outil configuré.</p>';return;}
  grid.innerHTML=tools.map(t=>`<div class="tool-card"><div class="tool-name">${t.tool}</div><div class="tool-meta">Niveau : <span class="badge ${t.access_level==='full'?'badge-green':t.access_level==='write'?'badge-blue':'badge-gray'}">${t.access_level}</span></div><div class="tool-meta">Actif : <span class="badge ${t.enabled?'badge-green':'badge-red'}">${t.enabled?'oui':'non'}</span></div>${Object.keys(t.config||{}).length?`<div class="tool-meta" style="margin-top:6px;font-size:10px;color:var(--text3)">${JSON.stringify(t.config)}</div>`:''}</div>`).join('');
}
function hideTools(){document.getElementById('tools-section').style.display='none';}

// ─── OUTILS PAR USER (fiche société) ───
let currentToolsUser=null;
const toolsApiBase=()=>isAdminOrSuper()?'/admin':'/tenant';

async function showToolsCompany(username){
  currentToolsUser=username;
  const panel=document.getElementById('companies-tools-panel');
  const grid=document.getElementById('companies-tools-grid');
  document.getElementById('companies-tools-title').innerHTML=`🔧 Outils de <strong style="color:#fff">${username}</strong>`;
  grid.innerHTML='<span class="loader"></span>';
  panel.style.display='block';
  panel.scrollIntoView({behavior:'smooth',block:'nearest'});
  try{
    const tools=await(await fetch(`${toolsApiBase()}/user-tools/${username}`)).json();
    if(!tools.length){grid.innerHTML='<p style="color:var(--text3);font-family:var(--mono);font-size:12px">Aucun outil configuré.</p>';return;}
    grid.innerHTML=tools.map(t=>`<div class="tool-card">
      <div class="tool-name">${t.tool}</div>
      <div class="tool-meta">Niveau : <select onchange="updateToolLevel('${username}','${t.tool}',this.value)" style="padding:2px 6px;background:var(--bg1);border:1px solid var(--border);border-radius:4px;color:var(--text1);font-size:11px">
        <option value="read_only" ${t.access_level==='read_only'?'selected':''}>Lecture seule</option>
        <option value="write" ${t.access_level==='write'?'selected':''}>Lecture + écriture</option>
        <option value="full" ${t.access_level==='full'?'selected':''}>Accès complet</option>
      </select></div>
      <div class="tool-meta">Actif : <button class="btn ${t.enabled?'btn-accent':'btn-ghost'}" style="padding:2px 8px;font-size:10px;min-width:40px" onclick="toggleToolEnabled('${username}','${t.tool}',${!t.enabled},'${t.access_level}')">${t.enabled?'🟢 ON':'🔴 OFF'}</button></div>
      <button class="btn btn-danger" style="padding:2px 8px;font-size:10px;margin-top:6px" onclick="removeToolFromUser('${username}','${t.tool}')">Retirer</button>
    </div>`).join('');
  }catch(e){grid.innerHTML=`<p style="color:var(--red);font-size:12px">❌ ${e.message}</p>`;}
}
function hideToolsCompany(){document.getElementById('companies-tools-panel').style.display='none';currentToolsUser=null;}

async function toggleToolEnabled(username,tool,enabled,level){
  try{
    await fetch(`${toolsApiBase()}/user-tools/${username}/${tool}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({access_level:level,enabled})});
    showToolsCompany(username);
  }catch(e){setAlert('companies-alert','❌ '+e.message,'err');}
}
async function updateToolLevel(username,tool,level){
  try{
    await fetch(`${toolsApiBase()}/user-tools/${username}/${tool}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({access_level:level,enabled:true})});
    showToolsCompany(username);
  }catch(e){setAlert('companies-alert','❌ '+e.message,'err');}
}
async function removeToolFromUser(username,tool){
  if(!confirm(`Retirer l'outil "${tool}" de ${username} ?`)) return;
  try{
    await fetch(`${toolsApiBase()}/user-tools/${username}/${tool}`,{method:'DELETE'});
    showToolsCompany(username);
  }catch(e){setAlert('companies-alert','❌ '+e.message,'err');}
}
async function addToolToUser(){
  const tool=document.getElementById('new-tool-name').value;
  const level=document.getElementById('new-tool-level').value;
  if(!tool||!currentToolsUser){setAlert('companies-alert','Sélectionnez un outil.','err');return;}
  try{
    await fetch(`${toolsApiBase()}/user-tools/${currentToolsUser}/${tool}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({access_level:level,enabled:true,config:{}})});
    document.getElementById('new-tool-name').value='';
    showToolsCompany(currentToolsUser);
  }catch(e){setAlert('companies-alert','❌ '+e.message,'err');}
}

// ─── CONNEXIONS V2 ───
const connApiBase=()=>isAdminOrSuper()?'/admin':'/tenant';
const TOOL_ICONS={'outlook':'📧','gmail':'✉️','drive':'🗂️','odoo':'🔧','teams':'💬','whatsapp':'📱','microsoft':'🟦','google':'🟢'};

function showAddConnection(tenantId,idx){document.getElementById('conn-add-'+idx).style.display='block';}

// ─── Helpers dropdown natif HTML pour la ligne Odoo du panel admin ────
// Refonte UI 19/04/2026 : passage de 10 a 5 boutons grace a des <details>
// regroupant 'Setup' (3 actions rares) et 'Scanner' (4 actions de scan).
const _ddItemStyle = "display:block;width:100%;text-align:left;padding:7px 12px;font-size:11px;background:transparent;color:#e2e8f0;border:none;border-radius:4px;cursor:pointer;white-space:nowrap";
const _ddItemHover = "onmouseover=\"this.style.background='#1e293b'\" onmouseout=\"this.style.background='transparent'\"";

function _ddItem(onclick, label, title){
  return `<button onclick="this.closest('details').removeAttribute('open');${onclick}" style="${_ddItemStyle}" ${_ddItemHover} title="${title||''}">${label}</button>`;
}

function _ddMenu(summaryColor, summaryLabel, items){
  return `<details style="position:relative;display:inline-block">
    <summary style="list-style:none;cursor:pointer;padding:2px 10px;font-size:10px;background:${summaryColor};color:white;border:1px solid rgba(0,0,0,0.25);border-radius:6px;user-select:none;font-weight:600;display:inline-block">${summaryLabel} <span style="font-size:8px;opacity:0.8">▾</span></summary>
    <div style="position:absolute;top:calc(100% + 4px);left:0;background:#0b1220;border:1px solid #334155;border-radius:6px;padding:4px;z-index:100;min-width:260px;box-shadow:0 6px 18px rgba(0,0,0,0.6)">${items.join('')}</div>
  </details>`;
}

function renderMicrosoftActions(tenantId, connId){
  // Refonte 20/04 soir : la ligne microsoft ne porte PLUS les boutons Drive.
  // Ces boutons ont ete deplaces sur la ligne 'drive' (SharePoint Commun)
  // car c est semantiquement la que se trouve le SharePoint vectorise
  // (scope tenant partage, pas scope user individuel).
  // La ligne microsoft reste utile uniquement pour detenir les tokens
  // OAuth du user (Outlook / OneDrive / SharePoint acces personnel).
  return '';
}

function renderDriveActions(tenantId, connId){
  // Nouveau 20/04 soir : boutons associes a la connexion 'drive' =
  // SharePoint commun au tenant. Scope tenant, pas user.
  const driveMenu = _ddMenu('#2563eb', '🗂️ Scanner SharePoint', [
    _ddItem('scanDriveStart(this, false)', '🚀 Scanner (incremental)',
      'Scanne le dossier SharePoint configure. Skip les fichiers deja a jour, retraite les nouveaux / modifies / en erreur.'),
    _ddItem('scanDriveStart(this, true)', '♻️ Rescan complet (tous fichiers)',
      'Retraite TOUS les fichiers meme deja OK. A utiliser apres correction majeure de la logique d extraction.'),
    _ddItem('scanDriveStatus(this)', '📊 Etat du dernier scan',
      'Affiche le resultat du dernier scan : fichiers traites, chunks crees, erreurs.'),
    _ddItem('driveGraphStats(this)', '🌐 Etat du graphe Drive',
      'Affiche combien de fichiers et dossiers Drive sont presents dans le graphe semantique unifie + couverture par rapport au total vectorise.'),
    _ddItem('driveGraphMigrate(this)', '⚡ Migrer Drive vers graphe',
      'Rattrape les fichiers vectorises avant le commit 2/5 en creant leurs noeuds File + Folder + edges contains. Idempotent, relancable sans risque.'),
  ]);
  const auditBtn = `<button class="btn btn-accent" style="padding:2px 10px;font-size:10px;background:#8b5cf6;color:white;font-weight:600" onclick="showAudit(this)" title="Audit des connexions (doublons, emails croises) + arborescence SharePoint scannee niveaux 1 et 2">🔎 Audit</button>`;
  return `${driveMenu} ${auditBtn}`;
}

function renderOdooActions(tenantId, connId){
  const setup = _ddMenu('#475569', '⚙️ Setup', [
    _ddItem(`discoverTool('${tenantId}','odoo',this)`, '🔍 Découverte des connecteurs', 'Peuple entity_links pour drive/calendar/contacts/odoo. Une fois a la mise en place.'),
    _ddItem('introspectOdoo(this)', '📂 Inventaire des modèles Odoo', 'Scanne tous les modeles Odoo + leurs champs. Peuple connector_schemas.'),
    _ddItem('generateManifests(this)', '📋 Générer les manifests', 'Genere les manifests de vectorisation (vectorize_fields, metadata_fields, graph_edges).'),
  ]);
  const scanner = _ddMenu('#dc2626', '🚀 Scanner', [
    _ddItem('scanTestMissing(this, 200)', '🧪 Test P1 rapide (200 records)', 'Teste les modeles P1 sans chunks. Diagnostic rapide ~10 min. Pas de purge.'),
    _ddItem('scanTestMissing(this, 200, 2)', '🧪 Test P2 rapide (200 records)', 'Teste les modeles P2 sur 200 records. Diagnostic 5-15 min. Pas de purge.'),
    _ddItem('scanTestMissing(this, 999999)', '📈 Compléter les manquants (volume réel)', 'Complete au volume reel les modeles vides ou partiels. Pas de purge. 10-20 min.'),
    `<div style="height:1px;background:#334155;margin:4px 0"></div>`,
    _ddItem('scanNuitComplet(this)', '🌙 Scan de nuit COMPLET (2h-3h)', 'Enchaine 4 etapes : mail.tracking + res.partner + products utiles + P2 complet. Tourne sur Railway, tu peux fermer le navigateur.'),
    `<div style="height:1px;background:#334155;margin:4px 0"></div>`,
    _ddItem('scanP1(this)', '⚠️ Scan P1 COMPLET (purge + rebuild)', 'DESTRUCTIF : purge tout puis re-vectorise les 16 modeles P1. 30-60 min.'),
  ]);
  const integrite = `<button class="btn btn-accent" style="padding:2px 10px;font-size:10px;background:#10b981;color:white;font-weight:600" onclick="showIntegrity(this)" title="Tableau d'integrite de la vectorisation par modele Odoo">📊 Intégrité</button>`;
  const webhooks = `<button class="btn btn-accent" style="padding:2px 10px;font-size:10px;background:#2563eb;color:white;font-weight:600" onclick="showWebhookStatus(this)" title="Dashboard temps-reel des webhooks Odoo : worker, queue, dedup, ronde de nuit">🔌 Webhooks</button>`;
  const stop = `<button class="btn btn-accent" style="padding:2px 10px;font-size:10px;background:#ef4444;color:white;font-weight:600" onclick="scanStop(this)" title="Arrete proprement le scan Odoo en cours (finit le modele actuel puis stop)">⏹️ Stop</button>`;
  return `${setup} ${scanner} ${integrite} ${webhooks} ${stop}`;
}

// Fermer automatiquement les autres <details> quand on en ouvre un
// (comportement natif du browser ne le fait pas seul)
document.addEventListener('click', e => {
  const opened = document.querySelector('details[open]');
  if(!opened) return;
  if(!opened.contains(e.target)) opened.removeAttribute('open');
});

async function loadConnections(tenantId,idx){
  const el=document.getElementById('conn-list-'+idx);
  const summaryEl=document.getElementById('conn-summary-'+idx);
  if(!el) return;
  try{
    const url=isAdminOrSuper()?`/admin/connections/${tenantId}`:'/tenant/connections';
    const conns=await(await fetch(url)).json();

    // ── Résumé dans l'entête de la carte ──
    if(summaryEl){
      const byType={};
      for(const c of conns){
        const grp = c.tool_type==='gmail'||c.tool_type==='microsoft' ? 'mail'
                  : c.tool_type==='sharepoint'||c.tool_type==='google_drive' ? 'drive' : 'autre';
        if(!byType[grp]) byType[grp]={total:0,connected:0};
        byType[grp].total++;
        if(c.status==='connected') byType[grp].connected++;
      }
      const pills = Object.entries(byType).map(([g,v])=>{
        const icon = g==='mail'?'📧': g==='drive'?'📁':'🔧';
        const ok = v.connected===v.total;
        const color = ok?'var(--green)':v.connected>0?'var(--orange)':'var(--text3)';
        return `<span style="font-size:10px;color:${color};font-family:var(--mono)">${icon} ${v.connected}/${v.total}</span>`;
      });
      summaryEl.innerHTML = pills.length ? pills.join('&nbsp;·&nbsp;') : '<span style="font-size:10px;color:var(--text3)">aucune connexion</span>';
    }

    if(!conns.length){el.innerHTML='<span style="color:var(--text3)">Aucune connexion configurée.</span>';return;}
    // Tooltips explicatifs par tool_type (refonte 20/04 soir)
    // But : dire clairement a Guillaume/l admin a quoi sert chaque ligne
    // de connexion (scope tenant vs scope user, role metier).
    const TOOL_HELP = {
      drive:     'SharePoint commun au tenant. Vectorisation au scope TENANT (1 fois pour toute la boite). Les users assignes peuvent questionner Raya sur ce contenu.',
      microsoft: 'Compte Microsoft 365 d un user (tokens OAuth). Donne acces a SA boite Outlook, SON OneDrive, ET sert a alimenter le scanner SharePoint commun. Scope USER.',
      outlook:   'Ligne de droits sur la boite Outlook du user. Les users assignes ici peuvent interroger Raya sur ces mails. Scope USER.',
      gmail:     'Compte Gmail d un user. Les users assignes peuvent interroger Raya sur ces mails. Scope USER.',
      odoo:      'Connexion API Odoo du tenant (aujourd hui 1 seule API key partagee). Scope TENANT. Le polling + la vectorisation se font avec cette cle. A terme : 1 API key par user pour tracabilite des actions.',
    };
    el.innerHTML=conns.map(c=>{
      const icon=TOOL_ICONS[c.tool_type]||'🔌';
      const helpText = TOOL_HELP[c.tool_type] || '';
      const helpBadge = helpText ? `<span style="display:inline-block;width:14px;height:14px;border-radius:50%;background:var(--bg2);border:1px solid var(--border);text-align:center;font-size:9px;line-height:13px;color:var(--text3);cursor:help;margin-left:4px;vertical-align:middle" title="${helpText.replace(/"/g,'&quot;')}">?</span>` : '';
      const statusBadge=c.status==='connected'
        ?`<span class="badge badge-green" style="font-size:9px">✅ ${c.connected_email||'connecté'}</span>`
        :c.status==='expired'
        ?'<span class="badge badge-red" style="font-size:9px">⚠️ expiré</span>'
        :'<span class="badge badge-gray" style="font-size:9px">non connecté</span>';
      let oauthBtn='';
      if(c.status!=='connected'){
        if(c.tool_type==='microsoft') oauthBtn=`<a href="/admin/connections/${tenantId}/oauth/microsoft/start?connection_id=${c.id}" class="btn btn-primary" style="padding:2px 10px;font-size:10px;text-decoration:none">🔵 Connecter Microsoft</a>`;
        else if(c.tool_type==='gmail') oauthBtn=`<a href="/admin/connections/${tenantId}/oauth/gmail/start?connection_id=${c.id}" class="btn btn-accent" style="padding:2px 10px;font-size:10px;text-decoration:none">✉️ Connecter Gmail</a>`;
      }else{
        if(c.tool_type==='microsoft') oauthBtn=`<a href="/admin/connections/${tenantId}/oauth/microsoft/start?connection_id=${c.id}" class="btn btn-ghost" style="padding:2px 10px;font-size:10px;text-decoration:none">🔄 Reconnecter</a>`;
        else if(c.tool_type==='gmail') oauthBtn=`<a href="/admin/connections/${tenantId}/oauth/gmail/start?connection_id=${c.id}" class="btn btn-ghost" style="padding:2px 10px;font-size:10px;text-decoration:none">🔄 Reconnecter</a>`;
      }
      const userBadges=c.assignments.map(a=>`<span class="badge ${a.enabled?'badge-blue':'badge-gray'}" style="font-size:9px;cursor:pointer" title="${a.access_level}" onclick="unassignConn(${c.id},'${a.username}','${tenantId}',${idx})">${a.username} ✕</span>`);
      const usersInline=c.assignments.length<=5;
      const usersHtml=!c.assignments.length?'<span style="color:var(--text3);font-size:10px">aucun user assigné</span>'
        :usersInline?userBadges.join(' ')
        :`<details style="display:inline"><summary style="cursor:pointer;font-size:10px;color:var(--accent)">${c.assignments.length} utilisateurs ▾</summary><div style="margin-top:4px;display:flex;gap:4px;flex-wrap:wrap">${userBadges.join(' ')}</div></details>`;
      return `<div style="padding:8px 12px;background:var(--bg1);border:1px solid var(--border);border-radius:8px;margin-bottom:6px">
        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
          <span style="font-size:16px">${icon}</span>
          <div style="flex:1;min-width:120px"><strong style="color:var(--text1);font-size:12px;cursor:pointer;border-bottom:1px dashed var(--text3)" onclick="renameConn(${c.id},'${tenantId}',${idx},'${c.label.replace(/'/g,"\\'")}')" title="Cliquer pour renommer">${c.label}</strong><br><span style="font-size:10px;color:var(--text3)">${c.tool_type}</span>${helpBadge} ${statusBadge}</div>
          ${oauthBtn}
          ${['microsoft','gmail'].includes(c.tool_type)?`<button class="btn btn-accent" style="padding:2px 10px;font-size:10px" onclick="discoverTool('${tenantId}','${c.tool_type}',this)">🔍 Découvrir</button>`:''}
          ${c.tool_type==='microsoft'?renderMicrosoftActions(tenantId, c.id):''}
          ${c.tool_type==='drive'?renderDriveActions(tenantId, c.id):''}
          ${c.tool_type==='odoo'?renderOdooActions(tenantId, c.id):''}
          <button class="btn btn-ghost" style="padding:2px 8px;font-size:10px" onclick="toggleAssignPanel(${c.id},'${tenantId}',${idx})">👥 Gérer accès</button>
          <button class="btn btn-danger" style="padding:2px 8px;font-size:10px" onclick="deleteConn(${c.id},'${tenantId}',${idx})">🗑️</button>
        </div>
        <div style="margin-top:6px;display:flex;gap:4px;flex-wrap:wrap;align-items:center">${usersHtml}</div>
        <div id="assign-panel-${c.id}" style="display:none;margin-top:8px;padding:8px;background:rgba(99,102,241,.04);border-radius:6px"></div>
      </div>`;
    }).join('');
  }catch(e){el.innerHTML='<span style="color:var(--red)">❌ '+e.message+'</span>';}
}

async function createConnection(tenantId,idx){
  const type=document.getElementById('conn-type-'+idx).value.trim().toLowerCase();
  const label=document.getElementById('conn-label-'+idx).value.trim();
  if(!type||!label){setAlert('companies-alert','Type et nom requis.','err');return;}
  const url=isAdminOrSuper()?`/admin/connections/${tenantId}`:'/tenant/connections';
  try{
    const d=await(await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tool_type:type,label})})).json();
    if(d.status==='ok'){document.getElementById('conn-add-'+idx).style.display='none';document.getElementById('conn-type-'+idx).value='';document.getElementById('conn-label-'+idx).value='';loadConnections(tenantId,idx);}
    else setAlert('companies-alert','❌ '+(d.message||'Erreur'),'err');
  }catch(e){setAlert('companies-alert','❌ '+e.message,'err');}
}

async function loadSystemAlerts(){
  // Chantier memoire 4 couches (Bloc 2.5) : affichage des alertes systeme
  // actives en haut du panel Societes. Rafraichi automatiquement a chaque
  // ouverture de l'onglet. Alertes : limites fetch atteintes/approchees,
  // modules Odoo manquants, OpenAI quota faible, etc.
  const banner = document.getElementById('system-alerts-banner');
  if(!banner) return;
  try{
    const r = await fetch('/admin/alerts');
    const d = await r.json();
    if(d.status !== 'ok' || !d.alerts || d.alerts.length === 0){
      banner.style.display = 'none';
      return;
    }
    const sevColors = {
      'critical': {bg:'#fef2f2', border:'#dc2626', txt:'#991b1b', icon:'🔴'},
      'warning':  {bg:'#fffbeb', border:'#d97706', txt:'#92400e', icon:'🟠'},
      'info':     {bg:'#eff6ff', border:'#2563eb', txt:'#1e40af', icon:'🔵'},
    };
    const items = d.alerts.map(a => {
      const s = sevColors[a.severity] || sevColors['warning'];
      const dateStr = a.updated_at ? a.updated_at.slice(0, 16).replace('T', ' ') : '';
      return `<div style="display:flex;gap:10px;align-items:flex-start;padding:10px 12px;background:${s.bg};border-left:3px solid ${s.border};border-radius:6px;margin-bottom:6px">
        <span style="font-size:14px">${s.icon}</span>
        <div style="flex:1;min-width:0">
          <div style="font-size:11px;color:${s.txt};font-weight:600">${a.component} · ${a.alert_type}</div>
          <div style="font-size:12px;color:${s.txt};margin-top:2px">${escapeHtml(a.message)}</div>
          <div style="font-size:10px;color:${s.txt};opacity:0.7;margin-top:4px">${dateStr}</div>
        </div>
        <button class="btn btn-ghost" style="padding:2px 8px;font-size:10px;white-space:nowrap" onclick="acknowledgeAlert(${a.id})">✓ Accuser</button>
      </div>`;
    }).join('');
    banner.innerHTML = `<div style="padding:10px 12px;background:var(--bg1);border:1px solid var(--border);border-radius:10px">
      <div style="font-size:11px;font-weight:600;color:var(--text2);margin-bottom:8px;text-transform:uppercase;letter-spacing:0.5px">⚠️ Alertes système actives (${d.alerts.length})</div>
      ${items}
    </div>`;
    banner.style.display = 'block';
  }catch(e){
    console.warn('loadSystemAlerts:', e);
    banner.style.display = 'none';
  }
}

async function acknowledgeAlert(alertId){
  try{
    await fetch(`/admin/alerts/${alertId}/acknowledge`, {method:'POST'});
    await loadSystemAlerts();
  }catch(e){ setAlert('companies-alert','❌ '+e.message,'err'); }
}

function escapeHtml(str){
  if(!str) return '';
  return String(str).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

// ─── Permissions par tenant (super admin) — bouton par tenant avec confirmation textuelle ───
// Cache local de l etat de verrouillage par tenant (cle = tenant_id)
// Mis a jour par updateLockButtonState() a chaque rechargement.
const _tenantLockState = {};

async function toggleReadOnlyForTenant(tenantId, tenantName){
  // Toujours recharger l etat depuis le backend avant le modal, pour ne pas
  // utiliser un cache obsolete (la DB a pu changer entre temps).
  let cached;
  try{
    console.log('[toggleReadOnlyForTenant] Rechargement etat avant toggle...');
    cached = await (await fetch(`/admin/tenant/${encodeURIComponent(tenantId)}/lock-status?_=` + Date.now(), {cache: 'no-store'})).json();
    _tenantLockState[tenantId] = cached;
    console.log('[toggleReadOnlyForTenant] Etat lu :', cached);
  }catch(e){
    setAlert('companies-alert', '❌ Impossible de lire l etat actuel : '+e.message, 'err');
    return;
  }
  // BUGFIX CRITIQUE : prompt() bloque le thread principal. Forcer un repaint
  // entre l update DOM et l ouverture du prompt pour eviter l incoherence
  // visuelle (bouton ancien etat + modal nouvel etat).
  await new Promise(r => requestAnimationFrame(r));
  await new Promise(r => requestAnimationFrame(r));
  await new Promise(r => setTimeout(r, 50));
  const isLocked = cached.is_locked === true;
  const total = cached.total_connections || 0;
  if(total === 0){
    setAlert('companies-alert', '❌ Aucune connexion a modifier pour ce tenant', 'err');
    return;
  }
  const stateText = isLocked ? 'VERROUILLE en lecture seule' : 'OUVERT (permissions actives)';
  const actionText = isLocked ? 'RESTAURER les permissions precedentes' : 'VERROUILLER toutes les connexions en lecture seule';
  const answer = prompt(`⚠️ Tenant : ${tenantName}\n\nEtat actuel : ${stateText}\nAction : ${actionText}\n\n(${total} connexion(s))\n\nTape "oui" pour confirmer :`);
  if(!answer || answer.trim().toLowerCase() !== 'oui') return;
  try{
    console.log('[toggleReadOnlyForTenant] POST /admin/tenant/'+tenantId+'/toggle-read-only...');
    const r = await fetch(`/admin/tenant/${encodeURIComponent(tenantId)}/toggle-read-only`, {method:'POST'});
    const d = await r.json();
    console.log('[toggleReadOnlyForTenant] Reponse backend :', d);
    if(d.status === 'ok'){
      const msg = d.action === 'locked'
        ? `🔒 ${tenantName} : ${d.affected} connexion(s) basculee(s) en lecture seule`
        : `🔓 ${tenantName} : ${d.affected} connexion(s) restauree(s)`;
      setAlert('companies-alert', msg, 'ok');
      // Invalider le cache + recharger toute la liste
      delete _tenantLockState[tenantId];
      // BUGFIX : forcer un reflow + 2 animation frames pour que le bouton
      // se mette a jour visuellement (sinon il faut recliquer pour voir
      // le changement a cause du prompt() bloquant precedent)
      await new Promise(r => requestAnimationFrame(r));
      loadCompanies();
      await new Promise(r => requestAnimationFrame(r));
      await new Promise(r => requestAnimationFrame(r));
    } else {
      setAlert('companies-alert', '❌ '+(d.message||'Erreur'), 'err');
    }
  }catch(e){
    console.error('[toggleReadOnlyForTenant] Erreur :', e);
    setAlert('companies-alert', '❌ '+e.message, 'err');
  }
}

// ============================================================================
// HELPERS DASHBOARDS (Phase dashboards neophyte-friendly, 20/04/2026)
// Reutilisables par showIntegrity / showWebhookStatus / scanDriveStatus
// ============================================================================

// Bannière verdict coloree en haut d une modale. Affiche une phrase claire
// + accordeon optionnel pour afficher les criteres du verdict.
// Params : verdict = {level, icon, title, message, details: []}
function renderVerdictBanner(verdict){
  if(!verdict) return '';
  const colors = {
    ok:        {bg:'#065f46', border:'#10b981', text:'#d1fae5'},
    warning:   {bg:'#78350f', border:'#f59e0b', text:'#fef3c7'},
    attention: {bg:'#7c2d12', border:'#ea580c', text:'#fed7aa'},
    critical:  {bg:'#7f1d1d', border:'#dc2626', text:'#fecaca'},
  };
  const c = colors[verdict.level] || colors.ok;
  const detailsHtml = (verdict.details || []).map(d =>
    `<li style="margin:2px 0">${d}</li>`).join('');
  const detailsBlock = detailsHtml
    ? `<details style="margin-top:8px;cursor:pointer">
         <summary style="font-size:11px;opacity:0.85">▼ Voir les criteres du verdict</summary>
         <ul style="margin:6px 0 0 18px;font-size:11px;opacity:0.9">${detailsHtml}</ul>
       </details>`
    : '';
  return `<div style="background:${c.bg};border:2px solid ${c.border};border-radius:10px;padding:14px 18px;margin-bottom:14px;color:${c.text}">
    <div style="display:flex;align-items:center;gap:10px">
      <div style="font-size:28px">${verdict.icon || 'ℹ️'}</div>
      <div style="flex:1">
        <div style="font-size:15px;font-weight:700;margin-bottom:2px">${verdict.title || ''}</div>
        <div style="font-size:12px;opacity:0.9">${verdict.message || ''}</div>
      </div>
    </div>
    ${detailsBlock}
  </div>`;
}

async function showIntegrity(btn){
  // Scanner Universel Phase 8 : dashboard d integrite visuel
  // Affiche une modale avec un tableau du % de vectorisation par modele
  const orig = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '⏳ Chargement...';
  try{
    const r = await fetch('/admin/scanner/integrity');
    const d = await r.json();
    if(d.status !== 'ok') throw new Error(d.message || 'Erreur inconnue');
    const ov = d.overall;
    // Couleur de la barre de progression globale
    const overallPct = ov.overall_integrity_pct || 0;
    const overallColor = overallPct >= 90 ? '#10b981' : overallPct >= 50 ? '#f59e0b' : '#dc2626';
    // Icones & couleurs etendus (19/04 puis 20/04) : on distingue desormais
    // - limited        : modele plafonne volontairement (orange doux)
    // - graph_only     : modele sans vectorize_fields, normal a 0 (gris)
    // - pending_rights : droits Odoo manquants, en attente OpenFire (bleu)
    // - deactivated    : manifest cassé, desactive volontaire (gris violet)
    // - ignored        : pas d usage metier, ignore definitif (gris)
    const sevIcon = s => ({
      ok: '✅', warning: '⚠️', critical: '🔴',
      limited: '🟡', graph_only: '⚙️',
      pending_rights: '🔐', deactivated: '🚫', ignored: '💤',
      unknown: '⚪'
    })[s] || '⚪';
    const sevColor = s => ({
      ok: '#10b981', warning: '#f59e0b', critical: '#dc2626',
      limited: '#f59e0b', graph_only: '#6b7280',
      pending_rights: '#0ea5e9', deactivated: '#8b5cf6', ignored: '#6b7280',
      unknown: '#6b7280'
    })[s] || '#6b7280';
    const sevLabel = s => ({
      ok: 'OK', warning: 'Warning', critical: 'Erreur',
      limited: 'Limité', graph_only: 'Graph-only',
      pending_rights: 'En attente droits', deactivated: 'Désactivé',
      ignored: 'Ignoré (pas d usage metier)',
      unknown: 'Non scanné'
    })[s] || 'Inconnu';
    // Formattage des chiffres
    const fmt = n => (n === null || n === undefined) ? '-' : n.toLocaleString('fr-FR');
    const fmtPct = p => (p === null || p === undefined) ? '-' : p.toFixed(1) + '%';
    const fmtDate = s => !s ? '<span style="color:var(--text3)">Jamais</span>' : new Date(s).toLocaleString('fr-FR', {day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
    // Construction du tableau — on affiche different selon severity :
    // - graph_only        : "graph-only" a la place de chiffres trompeurs
    // - limited           : affiche X/LIMITE (100% de la limite) au lieu de X/totalOdoo
    // - pending_rights    : affiche la raison + lien doc dans le tableau
    // - deactivated/ignored : idem
    const rows = d.models.map(m => {
      let integrityCell, chunksCell;
      if(m.severity === 'graph_only'){
        integrityCell = `<span style="color:#6b7280;font-style:italic">graph-only</span>`;
        chunksCell = `<span style="color:#6b7280">—</span>`;
      }else if(m.severity === 'limited'){
        const pctVsLimit = m.applicative_limit ? Math.round(100*(m.records_count_raya||0)/m.applicative_limit) : 100;
        integrityCell = `<span style="color:#f59e0b;font-weight:700">${pctVsLimit}% (cap)</span>`;
        chunksCell = fmt(m.chunks_in_db);
      }else if(m.severity === 'pending_rights' || m.severity === 'deactivated' || m.severity === 'ignored'){
        integrityCell = `<span style="color:${sevColor(m.severity)};font-weight:700;font-style:italic">${sevLabel(m.severity)}</span>`;
        chunksCell = fmt(m.chunks_in_db);
      }else{
        integrityCell = `<span style="color:${sevColor(m.severity)};font-weight:700">${fmtPct(m.integrity_pct)}</span>`;
        chunksCell = fmt(m.chunks_in_db);
      }
      const recordsOdooCell = m.severity === 'limited' && m.applicative_limit
        ? `${fmt(m.records_count_odoo)} <span style="color:#f59e0b;font-size:10px">(cap ${fmt(m.applicative_limit)})</span>`
        : fmt(m.records_count_odoo);
      // Ligne raison sous le nom si modele documente
      const reasonLine = m.deactivated_reason
        ? `<div style="font-size:10px;color:var(--text3);margin-top:2px;font-weight:400">💡 ${m.deactivated_reason}${m.deactivated_doc ? ` <span style="color:#0ea5e9">(voir ${m.deactivated_doc})</span>` : ''}</div>`
        : '';
      return `
      <tr style="border-bottom:1px solid var(--border)" title="${sevLabel(m.severity)}">
        <td style="padding:8px 10px;font-weight:600">${sevIcon(m.severity)} ${m.model_name}${reasonLine}</td>
        <td style="padding:8px 10px;text-align:center"><span style="background:${m.priority===1?'#7c3aed':'#0ea5e9'};color:white;padding:1px 6px;border-radius:4px;font-size:10px;font-weight:700">P${m.priority}</span></td>
        <td style="padding:8px 10px;text-align:right;font-variant-numeric:tabular-nums">${recordsOdooCell}</td>
        <td style="padding:8px 10px;text-align:right;font-variant-numeric:tabular-nums">${fmt(m.records_count_raya)}</td>
        <td style="padding:8px 10px;text-align:right;font-variant-numeric:tabular-nums">${chunksCell}</td>
        <td style="padding:8px 10px;text-align:right;font-variant-numeric:tabular-nums">${integrityCell}</td>
        <td style="padding:8px 10px;text-align:right;font-size:11px;color:var(--text2)">${fmtDate(m.last_scanned_at)}</td>
      </tr>`;
    }).join('');
    // Construction de la modale
    const backdrop = document.createElement('div');
    backdrop.id = 'integrity-backdrop';
    backdrop.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.85);z-index:9998;display:flex;align-items:center;justify-content:center';
    const modal = document.createElement('div');
    modal.style.cssText = 'background:#0b1220;border:1px solid var(--border);border-radius:12px;padding:16px 20px 20px;width:95vw;max-width:1100px;height:90vh;display:flex;flex-direction:column;box-shadow:0 10px 40px rgba(0,0,0,0.8)';
    modal.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px;flex-shrink:0">
        <div>
          <h3 style="margin:0 0 4px 0">📊 Intégrité de la vectorisation</h3>
          <div style="font-size:12px;color:var(--text3)">Tenant : <code>${d.tenant_id}</code> · Source : <code>${d.source}</code> · Intégrité globale : <span style="color:${overallColor};font-weight:700">${overallPct.toFixed(1)}%</span></div>
        </div>
        <button class="btn" id="integrity-close-btn" style="background:#ef4444;color:white;padding:6px 14px;border:none;border-radius:6px;cursor:pointer;font-weight:700">✕ Fermer</button>
      </div>
      ${renderVerdictBanner(d.verdict)}
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-bottom:14px;flex-shrink:0">
        ${renderMetricCard('📦','Modèles total',ov.models_total,'#64748b',
          'Nombre total de modèles Odoo suivis pour le tenant.')}
        ${renderMetricCard('✅','OK (≥90%)',ov.models_ok,'#10b981',
          'Modèles dont au moins 90% des records Odoo sont vectorisés côté Raya. État nominal.')}
        ${renderMetricCard('⚠️','Warning',ov.models_warning||0,'#f59e0b',
          'Modèles partiellement vectorisés (entre 50% et 90%). Probablement un scan interrompu, relancer.')}
        ${renderMetricCard('🔴','Critique',ov.models_critical||0,ov.models_critical?'#dc2626':'#64748b',
          'Modèles sous 50% de vectorisation QUI NE SONT PAS documentés comme suspens. Ce sont de vraies erreurs à investiguer.')}
        ${renderMetricCard('🟡','Cap volontaire',ov.models_limited||0,'#f59e0b',
          'Modèles plafonnés intentionnellement via MODEL_RECORD_LIMITS (ex: product.template à 5000). Pas une erreur.')}
        ${renderMetricCard('⚙️','Graph-only',ov.models_graph_only||0,'#6b7280',
          'Modèles sans champs à vectoriser (juste des edges de graphe). Normal à 0 chunks.')}
        ${renderMetricCard('🔐','Droits attendus',ov.models_pending_rights||0,'#0ea5e9',
          'Modèles documentés en attente d ouverture de droits côté OpenFire (mail.message, account.payment.line, etc.). Sans impact sur le reste.')}
        ${renderMetricCard('🚫','Désactivés',(ov.models_deactivated||0)+(ov.models_ignored||0),'#8b5cf6',
          'Modèles volontairement désactivés (manifest cassé) ou ignorés (pas d usage métier).')}
      </div>
      <div style="flex:1;overflow:auto;border:1px solid var(--border);border-radius:8px">
        <table style="width:100%;border-collapse:collapse;font-size:12px">
          <thead style="background:var(--bg2);position:sticky;top:0;z-index:1">
            <tr style="border-bottom:2px solid var(--border)">
              <th style="padding:10px;text-align:left">Modèle</th>
              <th style="padding:10px">Priorité</th>
              <th style="padding:10px;text-align:right">Records Odoo</th>
              <th style="padding:10px;text-align:right">Records Raya</th>
              <th style="padding:10px;text-align:right">Chunks DB</th>
              <th style="padding:10px;text-align:right">Intégrité</th>
              <th style="padding:10px;text-align:right">Dernier scan</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
      <div style="margin-top:8px;font-size:11px;color:var(--text3);flex-shrink:0">Chunks DB = nombre réel de chunks vectorisés en base (source de vérité live). Records Raya = comptage du dernier scan complet. Les modèles avec 💡 sont documentés (en attente droits, désactivés, ignorés).</div>`;
    backdrop.appendChild(modal);
    document.body.appendChild(backdrop);
    const close = () => { backdrop.remove(); document.removeEventListener('keydown', onEsc); };
    const onEsc = e => { if(e.key === 'Escape') close(); };
    document.addEventListener('keydown', onEsc);
    backdrop.addEventListener('click', e => { if(e.target === backdrop) close(); });
    document.getElementById('integrity-close-btn').onclick = close;
  }catch(e){
    setAlert('companies-alert', '❌ Intégrité échouée : '+e.message, 'err');
  }finally{
    btn.disabled = false;
    btn.innerHTML = orig;
  }
}

async function scanNuitComplet(btn){
  // Scan de nuit COMPLET (Option 1 validee 19/04/2026, refonte UI 20/04) :
  // Enchaine les 4 etapes (mail.tracking + res.partner + products utiles + P2
  // complet) cote Railway (et non plus en terminal local). Guillaume peut
  // fermer le navigateur : Railway tourne seul 2h a 3h. Le suivi se fait
  // via le bouton 📊 Integrite.
  const ok = await confirmAction(
    '🌙 Lancer le scan de nuit COMPLET ?',
    'Cette operation va :\n' +
    '• Completer mail.tracking.value (~22 850 records)\n' +
    '• Rattraper res.partner (~1 226 records)\n' +
    '• Vectoriser product.template uniquement pour les articles utiles (~500-2000)\n' +
    '• Scanner TOUS les modeles P2 au volume reel\n\n' +
    'Duree estimee : 2h a 3h.\n' +
    'Tourne sur Railway : tu peux fermer le navigateur.\n' +
    'Suivi de progression : bouton 📊 Integrite.\n\n' +
    'Lancer maintenant ?',
    'Oui, lancer le scan de nuit', 'Annuler'
  );
  if(!ok) return;
  const orig = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '⏳ Démarrage...';
  try{
    const r = await fetch('/admin/scanner/scan-nuit-complet', {method: 'POST'});
    const d = await r.json();
    if(d.status === 'already_running'){
      setAlert('companies-alert',
        '⚠️ Un scan de nuit est deja en cours. Attends qu\u2019il se termine (voir 📊 Integrite).', 'warn');
      return;
    }
    if(d.status !== 'started') throw new Error(d.message || 'Démarrage échoué');
    setAlert('companies-alert',
      '🌙 Scan de nuit COMPLET lance sur Railway. Duree estimee 2h-3h. ' +
      'Tu peux fermer le navigateur — Railway continue tout seul. ' +
      'Suis la progression via 📊 Integrite.', 'ok');
  }catch(e){
    setAlert('companies-alert', '❌ Scan de nuit echoue : '+e.message, 'err');
  }finally{
    btn.disabled = false;
    btn.innerHTML = orig;
  }
}

async function showWebhookStatus(btn){
  // Dashboard webhooks Odoo (Phase A.2 roadmap v4).
  // Affiche l etat du worker, les compteurs 24h, la file d attente,
  // les derniers rapports de ronde de nuit et les derniers jobs traites.
  const orig = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '⏳ Chargement...';
  try{
    const r = await fetch('/admin/webhooks/status');
    const d = await r.json();
    if(d.status !== 'ok') throw new Error(d.message || 'Erreur inconnue');
    const s = d.stats;
    const workerOk = s.worker_alive;
    const workerColor = workerOk ? '#10b981' : '#dc2626';
    const workerLabel = workerOk ? '✅ Actif' : '❌ Arrêté';
    const fmt = n => (n === null || n === undefined) ? '-' : n.toLocaleString('fr-FR');
    const fmtDate = s => !s ? '<span style="color:var(--text3)">Jamais</span>' : new Date(s).toLocaleString('fr-FR', {day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'});

    // Tableau des derniers jobs
    const jobRows = (d.recent_jobs || []).map(j => {
      const statusIcon = j.completed_at && !j.error ? '✅'
                        : j.error ? '❌'
                        : '⏳';
      const sourceIcon = j.via_webhook ? '🔌' : '🌙';
      return `<tr style="border-bottom:1px solid var(--border)">
        <td style="padding:6px 10px;font-size:11px">${sourceIcon} ${statusIcon}</td>
        <td style="padding:6px 10px;font-size:11px;color:var(--text2)">${j.tenant_id}</td>
        <td style="padding:6px 10px;font-size:11px;font-weight:600">${j.model}</td>
        <td style="padding:6px 10px;font-size:11px;text-align:right">${j.record_id}</td>
        <td style="padding:6px 10px;font-size:11px">${j.action}</td>
        <td style="padding:6px 10px;font-size:11px;color:${j.error?'#dc2626':'var(--text2)'}">${j.error || '—'}</td>
        <td style="padding:6px 10px;font-size:10px;color:var(--text3)">${fmtDate(j.completed_at || j.created_at)}</td>
      </tr>`;
    }).join('');

    // Section rapports de ronde de nuit
    const patrolRows = (d.patrol_reports || []).map(p => {
      const sevColor = p.severity==='warning'?'#f59e0b':p.severity==='critical'?'#dc2626':'#6b7280';
      const sevIcon = p.severity==='warning'?'⚠️':p.severity==='critical'?'🔴':'ℹ️';
      const ackIcon = p.acknowledged ? '✓' : '';
      return `<tr style="border-bottom:1px solid var(--border)">
        <td style="padding:6px 10px;font-size:11px;color:${sevColor}">${sevIcon} ${ackIcon}</td>
        <td style="padding:6px 10px;font-size:11px">${p.tenant_id}</td>
        <td style="padding:6px 10px;font-size:11px">${p.message}</td>
        <td style="padding:6px 10px;font-size:10px;color:var(--text3)">${fmtDate(p.updated_at)}</td>
      </tr>`;
    }).join('') || '<tr><td colspan="4" style="padding:10px;color:var(--text3);text-align:center;font-size:11px">Aucun rapport de ronde de nuit encore.</td></tr>';

    // Construction de la modale — Phase dashboards neophyte (20/04/2026)
    // Structure : verdict (niveau 1) + resume (niveau 2) + details (niveau 3)
    const backdrop = document.createElement('div');
    backdrop.id = 'webhooks-backdrop';
    backdrop.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.85);z-index:9998;display:flex;align-items:center;justify-content:center';
    const modal = document.createElement('div');
    modal.style.cssText = 'background:#0b1220;border:1px solid var(--border);border-radius:12px;padding:16px 20px 20px;width:95vw;max-width:1200px;height:90vh;display:flex;flex-direction:column;box-shadow:0 10px 40px rgba(0,0,0,0.8);overflow:auto';

    // Niveau 2 : cartes metriques cles avec tooltips
    const recentMin = s.recent_window_minutes || 15;
    const metricsHtml = `<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:14px">
      ${renderMetricCard('✅','Traités ('+recentMin+' min)',fmt(s.processed_recent),'#10b981',
        'Nombre de jobs Odoo traités avec succès dans les '+recentMin+' dernières minutes. C est l indicateur principal de santé : si > 0, ça marche bien maintenant.')}
      ${renderMetricCard('❌','Erreurs ('+recentMin+' min)',fmt(s.errors_recent),s.errors_recent>0?'#dc2626':'#64748b',
        'Erreurs survenues dans les '+recentMin+' dernières minutes. Si 0 = tout va bien. Si > 0 = à investiguer via l accordéon détails plus bas.')}
      ${renderMetricCard('⏳','En attente',fmt(s.pending_now),'#f59e0b',
        'Jobs en file d attente prêts à être traités. Normal en flux continu (0 à quelques dizaines). Si gros chiffre qui ne baisse pas = worker saturé.')}
      ${renderMetricCard('🌙','Erreurs fantômes 24h',fmt(s.phantom_errors_24h),'#8b5cf6',
        'Erreurs sur des modèles officiellement désactivés (ex: of.survey.answers, mail.message). Sans impact. Peuvent être purgées pour nettoyer l affichage.')}
      ${renderMetricCard('⚠️','Erreurs réelles 24h',fmt(s.real_errors_24h),s.real_errors_24h>0?'#f59e0b':'#64748b',
        'Erreurs sur des modèles encore actifs. À investiguer quand tu as un moment, sans urgence si le verdict global est vert.')}
      ${renderMetricCard('🚦','OpenAI (dernière min)',fmt(s.rate_limit_calls_last_min)+'/2000','#64748b',
        'Nombre d appels à l API OpenAI dans la dernière minute. Limite configurée à 2000. Si on s approche = throttling auto.')}
    </div>`;

    // Niveau 3 : detail technique regroupé par modèle
    const errorsByModelRows = (s.errors_by_model_24h || []).map(em => {
      const tag = em.is_phantom
        ? '<span style="background:#7c3aed20;color:#a78bfa;padding:2px 6px;border-radius:4px;font-size:10px">🌙 fantôme</span>'
        : '<span style="background:#f59e0b20;color:#fbbf24;padding:2px 6px;border-radius:4px;font-size:10px">⚠️ réelle</span>';
      const reason = em.reason ? `<div style="font-size:10px;color:var(--text3);margin-top:2px">${em.reason}</div>` : '';
      return `<tr style="border-bottom:1px solid var(--border)">
        <td style="padding:6px 10px;font-size:11px">${tag}</td>
        <td style="padding:6px 10px;font-size:11px;font-weight:600">${em.model}${reason}</td>
        <td style="padding:6px 10px;font-size:11px;text-align:right">${em.count}</td>
        <td style="padding:6px 10px;font-size:10px;color:var(--text3);max-width:400px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${(em.sample_error||'').replace(/"/g,'&quot;')}">${(em.sample_error||'').substring(0,100)}</td>
      </tr>`;
    }).join('') || '<tr><td colspan="4" style="padding:14px;text-align:center;color:var(--text3);font-size:11px">Aucune erreur sur les dernières 24h 🎉</td></tr>';

    const errorsByModelTable = `<div style="overflow:auto;border:1px solid var(--border);border-radius:8px">
      <table style="width:100%;border-collapse:collapse">
        <thead style="background:var(--bg2);position:sticky;top:0">
          <tr style="border-bottom:2px solid var(--border)">
            <th style="padding:8px;text-align:left;font-size:11px">Catégorie</th>
            <th style="padding:8px;text-align:left;font-size:11px">Modèle</th>
            <th style="padding:8px;text-align:right;font-size:11px">Nb erreurs</th>
            <th style="padding:8px;text-align:left;font-size:11px">Exemple d erreur</th>
          </tr>
        </thead>
        <tbody>${errorsByModelRows}</tbody>
      </table>
    </div>`;

    // Tableau jobs bruts (20 derniers)
    const jobsTable = `<div style="overflow:auto;border:1px solid var(--border);border-radius:8px;max-height:400px">
      <table style="width:100%;border-collapse:collapse">
        <thead style="background:var(--bg2);position:sticky;top:0">
          <tr style="border-bottom:2px solid var(--border)">
            <th style="padding:8px;text-align:left;font-size:11px">État</th>
            <th style="padding:8px;text-align:left;font-size:11px">Tenant</th>
            <th style="padding:8px;text-align:left;font-size:11px">Modèle</th>
            <th style="padding:8px;text-align:right;font-size:11px">Record</th>
            <th style="padding:8px;text-align:left;font-size:11px">Action</th>
            <th style="padding:8px;text-align:left;font-size:11px">Erreur</th>
            <th style="padding:8px;text-align:left;font-size:11px">Date</th>
          </tr>
        </thead>
        <tbody>${jobRows || '<tr><td colspan="7" style="padding:14px;text-align:center;color:var(--text3);font-size:11px">Aucun job traité récemment</td></tr>'}</tbody>
      </table>
    </div>`;

    const patrolTable = `<div style="overflow:auto;border:1px solid var(--border);border-radius:8px;max-height:150px">
      <table style="width:100%;border-collapse:collapse">
        <thead style="background:var(--bg2);position:sticky;top:0">
          <tr style="border-bottom:2px solid var(--border)">
            <th style="padding:8px;text-align:left;font-size:11px">Sévérité</th>
            <th style="padding:8px;text-align:left;font-size:11px">Tenant</th>
            <th style="padding:8px;text-align:left;font-size:11px">Message</th>
            <th style="padding:8px;text-align:left;font-size:11px">Date</th>
          </tr>
        </thead>
        <tbody>${patrolRows}</tbody>
      </table>
    </div>`;

    modal.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px;flex-shrink:0">
        <div>
          <h3 style="margin:0 0 4px 0">🔌 Webhooks Odoo — Monitoring</h3>
          <div style="font-size:12px;color:var(--text3)">Worker : <span style="color:${workerColor};font-weight:700">${workerLabel}</span> · Tenants configurés : <code>${d.configured_tenants.join(', ') || 'aucun'}</code> · Dernière activité : ${fmtDate(s.last_activity)}</div>
        </div>
        <button class="btn" id="webhooks-close-btn" style="background:#ef4444;color:white;padding:6px 14px;border:none;border-radius:6px;cursor:pointer;font-weight:700">✕ Fermer</button>
      </div>
      ${renderVerdictBanner(d.verdict)}
      ${s.phantom_errors_24h > 0 ? `<div style="display:flex;justify-content:flex-end;margin-bottom:10px">
        <button id="webhooks-purge-btn" style="background:#8b5cf6;color:white;padding:6px 14px;border:none;border-radius:6px;cursor:pointer;font-weight:600;font-size:12px" title="Supprime de la queue les ${fmt(s.phantom_errors_24h)} jobs en erreur sur les modeles officiellement desactives. Sans impact - ces erreurs sont des fantomes residuels.">🧹 Purger les ${fmt(s.phantom_errors_24h)} erreurs fantômes</button>
      </div>` : ''}
      ${metricsHtml}
      ${renderAccordion('🎯 Erreurs 24h regroupées par modèle (cliquer pour comprendre les fantômes vs réelles)', errorsByModelTable, true)}
      ${renderAccordion('🌙 Dernières rondes de nuit (5h)', patrolTable, false)}
      ${renderAccordion('📋 20 derniers jobs traités (détail technique brut)', jobsTable, false)}
      <div style="margin-top:8px;font-size:11px;color:var(--text3)">Historique 24h : ${fmt(s.processed_24h)} traités · ${fmt(s.received_24h)} reçus · ${fmt(s.errors_24h)} erreurs (${fmt(s.phantom_errors_24h)} fantômes + ${fmt(s.real_errors_24h)} réelles) · Actualisation manuelle (re-cliquer sur 🔌 Webhooks)</div>`;
    backdrop.appendChild(modal);
    document.body.appendChild(backdrop);
    const close = () => { backdrop.remove(); document.removeEventListener('keydown', onEsc); };
    const onEsc = e => { if(e.key === 'Escape') close(); };
    document.addEventListener('keydown', onEsc);
    backdrop.addEventListener('click', e => { if(e.target === backdrop) close(); });
    document.getElementById('webhooks-close-btn').onclick = close;
    // Bouton purge fantomes (optionnel, visible seulement si phantom_errors_24h > 0)
    const purgeBtn = document.getElementById('webhooks-purge-btn');
    if(purgeBtn){
      purgeBtn.onclick = async () => {
        const ok = await confirmAction(
          '🧹 Purger les erreurs fantômes ?',
          'Cette opération va supprimer de la queue les jobs en erreur sur les modèles officiellement désactivés (of.survey.answers, mail.message, etc.).\n\n' +
          'Aucun impact : ces erreurs sont des fantômes résiduels qui polluent simplement les compteurs 24h.\n\n' +
          'Continuer ?',
          'Oui, purger', 'Annuler'
        );
        if(!ok) return;
        const originalPurge = purgeBtn.innerHTML;
        purgeBtn.disabled = true;
        purgeBtn.innerHTML = '⏳ Purge...';
        try{
          const res = await fetch('/admin/webhooks/purge-phantoms', {method:'POST'});
          const pd = await res.json();
          if(pd.status !== 'ok') throw new Error(pd.message || 'Purge echouee');
          setAlert('companies-alert', '🧹 '+pd.message+' Re-clique sur 🔌 Webhooks pour rafraichir.', 'ok');
          close();
        }catch(e){
          setAlert('companies-alert', '❌ Purge echouee : '+e.message, 'err');
          purgeBtn.disabled = false;
          purgeBtn.innerHTML = originalPurge;
        }
      };
    }
  }catch(e){
    setAlert('companies-alert', '❌ Webhooks status échoué : '+e.message, 'err');
  }finally{
    btn.disabled = false;
    btn.innerHTML = orig;
  }
}

async function scanP1(btn){
  // Scanner Universel Phase 3 : vectorisation complete des 16 modeles P1
  // avec purge prealable. Peut prendre 30-60 min selon volume (product.template = 133k).
  const ok = await confirmAction(
    '⚠️ Lancer le Scanner P1 complet ?',
    'Cette opération va :\n• PURGER toutes les données vectorisées actuelles\n• RE-VECTORISER les 16 modèles P1\n• Durée estimée : 30-60 min\n• Coût OpenAI estimé : 5-10€\n\nÊtes-vous sûr ?',
    'Oui, purger et relancer', 'Annuler'
  );
  if(!ok) return;
  const orig = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '⏳ Démarrage...';
  try{
    const r = await fetch('/admin/scanner/run/start?priority_max=1&purge_first=true', {method:'POST'});
    const d = await r.json();
    if(d.status !== 'started' || !d.run_id) throw new Error(d.message || 'Démarrage échoué');
    const runId = d.run_id;
    setAlert('companies-alert', `🚀 Scan P1 lancé (run_id: ${runId}). Patience, cela peut prendre 30-60 min...`, 'ok');

    // Polling toutes les 10s (pas trop souvent, ça tourne longtemps)
    let tries = 0;
    const maxTries = 720; // 720 * 10s = 2h max
    while(tries < maxTries){
      await new Promise(res => setTimeout(res, 10000));
      tries++;
      const sr = await fetch(`/admin/scanner/run/status?run_id=${runId}`);
      const sd = await sr.json();
      if(sd.status === 'running' || sd.status === 'pending'){
        const p = sd.progress || {};
        const s = sd.stats || {};
        const cm = p.current_model || 'init';
        const step = p.step || 'running';
        const modelsDone = s.models_processed || 0;
        const modelsTotal = s.models_total || 16;
        const recordsTotal = s.records_processed || 0;
        const chunks = s.chunks_vectorized || 0;
        btn.innerHTML = `⏳ ${step} ${modelsDone}/${modelsTotal} — ${cm} (${recordsTotal} rec, ${chunks} chunks)`;
        continue;
      }
      if(sd.status === 'ok'){
        const s = sd.stats || {};
        const dur = sd.finished_at && sd.started_at ? Math.round((new Date(sd.finished_at) - new Date(sd.started_at))/1000) : '?';
        setAlert('companies-alert', `✅ Scan P1 terminé en ${dur}s : ${s.models_processed}/${s.models_total} modèles, ${s.records_processed} records, ${s.nodes_created} nœuds, ${s.edges_created} arêtes, ${s.chunks_vectorized} chunks vectorisés, ${s.errors||0} erreurs`, 'ok');
        return;
      }
      if(sd.status === 'error'){
        throw new Error(sd.error || sd.message || 'Erreur inconnue');
      }
      if(sd.status === 'stopped'){
        setAlert('companies-alert', `⏹️ Scan arrêté manuellement : ${sd.error || 'stop demandé'}`, 'ok');
        return;
      }
    }
    throw new Error('Timeout 2h');
  }catch(e){
    setAlert('companies-alert', '❌ Scan P1 échoué : '+e.message, 'err');
  }finally{
    btn.disabled = false;
    btn.innerHTML = orig;
  }
}

// Scanner TEST / COMPLET sur modeles manquants :
// - sampleSize=200 (default) : test rapide diagnostique
// - sampleSize=999999 : scan COMPLET des modeles manquants (sans purge,
//   non destructif pour les chunks deja en DB). Pratique pour finir la
//   vectorisation apres avoir corrige un manifest cassé.
// - priorityMax=1 (default) : P1 uniquement
// - priorityMax=2 : P1+P2 (teste les modeles P2 sans toucher P1)
async function scanTestMissing(btn, sampleSize, priorityMax){
  sampleSize = sampleSize || 200;
  priorityMax = priorityMax || 1;
  const isComplet = sampleSize >= 10000;
  const isP2 = priorityMax >= 2;
  const prioLabel = isP2 ? 'P1+P2' : 'P1';
  let titre;
  if(isP2 && !isComplet){
    titre = '🧪 Test P2 (200 records/modèle) ?';
  }else if(isComplet){
    titre = '🚀 Compléter les modèles manquants (volume réel) ?';
  }else{
    titre = '🧪 Lancer un Scanner test (200 records/modèle) ?';
  }
  let msg;
  if(isP2 && !isComplet){
    msg = 'Cette opération va :\n• Scanner les 16 modèles P2 sur 200 records chacun\n• Ne PAS toucher aux modèles déjà vectorisés (P1)\n• Identifier rapidement quels modèles P2 plantent / fonctionnent\n• Durée estimée : 5-15 min\n\nÊtes-vous sûr ?';
  }else if(isComplet){
    msg = `Cette opération va :\n• Détecter les modèles sans chunks (ou partiels sur 200)\n• Les scanner au VOLUME COMPLET (pas de limite 200)\n• Scope : ${prioLabel}\n• Ne PAS toucher aux modèles déjà vectorisés\n• Durée estimée : 10-20 min selon volumes\n\nÊtes-vous sûr ?`;
  }else{
    msg = 'Cette opération va :\n• Détecter les modèles sans chunks\n• Les scanner sur 200 records chacun (rapide)\n• Ne PAS toucher aux modèles déjà vectorisés\n• Durée estimée : 5-10 min\n\nÊtes-vous sûr ?';
  }
  const ok = await confirmAction(titre, msg,
    isComplet ? 'Oui, compléter' : 'Oui, lancer le test', 'Annuler');
  if(!ok) return;
  const orig = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = isComplet ? '⏳ Complétion démarrage...' : '⏳ Test démarrage...';
  try{
    const url = `/admin/scanner/run/test-missing?sample_size=${sampleSize}&priority_max=${priorityMax}`;
    const r = await fetch(url, {method:'POST'});
    const d = await r.json();
    if(d.status !== 'started' || !d.run_id) throw new Error(d.message || 'Démarrage échoué');
    const runId = d.run_id;
    const missing = (d.missing_models||[]).join(', ') || 'aucun';
    setAlert('companies-alert', `${isComplet?'🚀 Complétion':'🧪 Scanner test'} lancé (run_id: ${runId.slice(0,8)}...). Modèles : ${missing}`, 'ok');
    // Polling toutes les 5s, timeout 30min pour mode complet (10278 records a scanner)
    let tries = 0;
    const maxTries = isComplet ? 720 : 240; // 720*5s=60min pour complet, 240*5s=20min pour test
    while(tries < maxTries){
      await new Promise(res => setTimeout(res, 5000));
      tries++;
      const sr = await fetch(`/admin/scanner/run/status?run_id=${runId}`);
      const sd = await sr.json();
      if(sd.status === 'running' || sd.status === 'pending'){
        const p = sd.progress || {};
        const s = sd.stats || {};
        const prefix = isComplet ? '🚀 Complétion' : '⏳ Test';
        btn.innerHTML = `${prefix} ${s.models_processed||0}/${s.models_total||'?'} — ${p.current_model||'...'} (${s.chunks_vectorized||0} chunks)`;
        continue;
      }
      if(sd.status === 'ok'){
        const s = sd.stats || {};
        const aborted = s.models_aborted || [];
        const label = isComplet ? 'Complétion' : 'Test';
        let msg = `✅ ${label} terminé : ${s.chunks_vectorized||0} chunks créés, ${s.errors||0} erreurs`;
        if(aborted.length) msg += `, ${aborted.length} modèle(s) abandonné(s) : ${aborted.map(a=>a.model).join(', ')}`;
        setAlert('companies-alert', msg, aborted.length ? 'err' : 'ok');
        return;
      }
      if(sd.status === 'error'){ throw new Error(sd.error || 'Erreur inconnue'); }
      if(sd.status === 'stopped'){
        setAlert('companies-alert', '⏹️ Scan arrêté manuellement', 'ok');
        return;
      }
    }
    throw new Error(`Timeout ${isComplet?'60 min':'20 min'}`);
  }catch(e){
    setAlert('companies-alert', '❌ Scan échoué : '+e.message, 'err');
  }finally{
    btn.disabled = false;
    btn.innerHTML = orig;
  }
}

// Bouton Stop : arrete proprement le run en cours (option A, finit le
// modele courant puis stoppe avant le suivant)
async function scanStop(btn, runId){
  if(!runId){
    // Auto-detect le run actif via /admin/scanner/run/list
    try{
      const r = await fetch('/admin/scanner/run/list?limit=1');
      const d = await r.json();
      const last = (d.runs || [])[0];
      if(last && last.status === 'running') runId = last.run_id;
    }catch(e){}
  }
  if(!runId){
    setAlert('companies-alert', 'Aucun scan en cours à arrêter.', 'err');
    return;
  }
  const ok = await confirmAction(
    '⏹️ Arrêter le scan en cours ?',
    'Le worker finira le modèle actuel (quelques minutes) puis s\'arrêtera avant le modèle suivant.\n\nLes chunks déjà vectorisés sont conservés.\n\nÊtes-vous sûr ?',
    'Oui, arrêter', 'Annuler'
  );
  if(!ok) return;
  const orig = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '⏹️ Arrêt...';
  try{
    const r = await fetch(`/admin/scanner/run/stop?run_id=${runId}`, {method:'POST'});
    const d = await r.json();
    if(d.status === 'ok'){
      setAlert('companies-alert', '⏹️ Stop demandé. Le scan s\'arrêtera après le modèle en cours.', 'ok');
    }else{
      setAlert('companies-alert', '❌ '+(d.message||'Stop échoué'), 'err');
    }
  }catch(e){
    setAlert('companies-alert', '❌ Stop échoué : '+e.message, 'err');
  }finally{
    btn.disabled = false;
    btn.innerHTML = orig;
  }
}

async function generateManifests(btn){
  // Scanner Universel Phase 2 : genere les manifests pour les 31 modeles P1+P2
  // en fetchant les champs de chaque modele via ir.model.fields et en classifiant
  // automatiquement chaque champ (vectorize/edge/metadata/ignore).
  const orig = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '⏳ Génération...';
  try{
    setAlert('companies-alert', '📋 Génération des 31 manifests en cours (~30-60s)...', 'ok');
    const r = await fetch('/admin/scanner/manifests/generate', {method:'POST'});
    const d = await r.json();
    if(d.status === 'error') throw new Error(d.message || 'Erreur inconnue');
    if(!d.generated) throw new Error('Réponse inattendue');
    // Construction du recap
    const lines = d.generated.map(g => `  [P${g.priority}] ${g.model} (${g.records_count||0} records) → ${g.vectorize_count} vectorize, ${g.edges_count} edges, ${g.metadata_count} meta, ${g.ignored_count} ignored`).join('\n');
    const errLines = (d.errors||[]).length ? '\n\nERREURS :\n  ' + d.errors.join('\n  ') : '';
    const summary = `✅ Manifests générés : ${d.generated_count}/31\n\n${lines}${errLines}`;
    // Reutilise le meme pattern de modale que introspection
    const fullText = summary + '\n\n=== JSON COMPLET ===\n' + JSON.stringify(d, null, 2);
    const backdrop = document.createElement('div');
    backdrop.id = 'manifests-backdrop';
    backdrop.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.85);z-index:9998;display:flex;align-items:center;justify-content:center';
    const modal = document.createElement('div');
    modal.style.cssText = 'background:#0b1220;border:1px solid var(--border);border-radius:12px;padding:16px 20px 20px;width:90vw;max-width:1000px;height:85vh;display:flex;flex-direction:column;box-shadow:0 10px 40px rgba(0,0,0,0.8)';
    const escapeHtml = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;');
    modal.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;flex-shrink:0">
        <h3 style="margin:0">📋 Manifests générés</h3>
        <div style="display:flex;gap:8px">
          <button class="btn" id="manifests-copy-btn" style="background:#10b981;color:white;padding:6px 14px;border:none;border-radius:6px;cursor:pointer;font-weight:600">📋 Tout copier</button>
          <button class="btn" id="manifests-close-btn" style="background:#ef4444;color:white;padding:6px 14px;border:none;border-radius:6px;cursor:pointer;font-weight:700">✕ Fermer</button>
        </div>
      </div>
      <textarea id="manifests-textarea" readonly style="flex:1;width:100%;font-family:var(--mono);font-size:11px;padding:10px;background:var(--bg2);color:var(--text1);border:1px solid var(--border);border-radius:8px;overflow:auto;resize:none">${escapeHtml(fullText)}</textarea>
      <div style="margin-top:8px;font-size:11px;color:var(--text3);flex-shrink:0">Échap ou clic en dehors pour fermer</div>`;
    backdrop.appendChild(modal);
    document.body.appendChild(backdrop);
    const close = () => { backdrop.remove(); document.removeEventListener('keydown', onEsc); };
    const onEsc = e => { if(e.key === 'Escape') close(); };
    document.addEventListener('keydown', onEsc);
    backdrop.addEventListener('click', e => { if(e.target === backdrop) close(); });
    document.getElementById('manifests-close-btn').onclick = close;
    document.getElementById('manifests-copy-btn').onclick = async () => {
      const b = document.getElementById('manifests-copy-btn');
      try{ await navigator.clipboard.writeText(fullText); b.innerHTML = '✓ Copié !'; }
      catch(err){ const ta = document.getElementById('manifests-textarea'); ta.focus(); ta.select(); document.execCommand('copy'); b.innerHTML = '✓ Copié (fb)'; }
      setTimeout(()=>{ b.innerHTML = '📋 Tout copier'; }, 2000);
    };
    setAlert('companies-alert', `✅ ${d.generated_count} manifests générés`, 'ok');
  }catch(e){
    setAlert('companies-alert', '❌ Génération échoué : '+e.message, 'err');
  }finally{
    btn.disabled = false;
    btn.innerHTML = orig;
  }
}

async function introspectOdoo(btn){
  // Scanner Universel Odoo (18/04/2026) : lance un inventaire complet via
  // /admin/odoo/introspect/start (async en background thread) + polling sur
  // /admin/odoo/introspect/status?run_id=xxx jusqu a completion.
  const orig = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '⏳ Demarrage...';
  try{
    // Lancer le run
    const r = await fetch('/admin/odoo/introspect/start', {method:'POST'});
    const d = await r.json();
    if(d.status !== 'started' || !d.run_id) throw new Error(d.message || 'Demarrage echoue');
    const runId = d.run_id;
    setAlert('companies-alert', `🔍 Inventaire Odoo lancé (run_id: ${runId}). Patience, cela peut prendre 2-5 min...`, 'ok');
    // Polling toutes les 3 secondes
    let tries = 0;
    const maxTries = 200; // 200 * 3s = 10 min max
    while(tries < maxTries){
      await new Promise(res => setTimeout(res, 3000));
      tries++;
      const sr = await fetch(`/admin/odoo/introspect/status?run_id=${runId}`);
      const sd = await sr.json();
      if(sd.status === 'running'){
        const p = sd.progress || {};
        btn.innerHTML = `⏳ ${p.step||''} ${p.current||0}/${p.total||0} (${p.pct||0}%)`;
        continue;
      }
      if(sd.status === 'ok' && sd.result){
        // Affichage du resume
        const res = sd.result;
        const stats = res.stats || {};
        const byCat = res.by_category || {};
        const allModels = res.models || [];
        const topModels = allModels.slice(0, 30);
        const catLine = Object.entries(byCat).sort((a,b)=>b[1]-a[1]).map(([k,v])=>`${k}=${v}`).join(', ');
        const topLines = topModels.map(m => `  ${m.model} (${m.records_count} records, ${m.fields_count||'?'} fields) [${m.category}]`).join('\n');
        // Regrouper par categorie : liste tous les modeles avec leur volume
        const byCatDetails = {};
        for(const m of allModels){
          if(!byCatDetails[m.category]) byCatDetails[m.category] = [];
          byCatDetails[m.category].push(`    ${m.model} (${m.records_count})`);
        }
        const catDetailsLines = Object.entries(byCatDetails).sort().map(([cat,lines]) =>
          `\n[${cat}] ${lines.length} modeles:\n${lines.slice(0,30).join('\n')}${lines.length>30?'\n    ... et '+(lines.length-30)+' de plus':''}`
        ).join('\n');
        const summary = `✅ Inventaire terminé en ${sd.duration_sec}s.\n\nSTATS : ${stats.total_models_filtered} modèles non-vides / ${stats.total_models_discovered} découverts. Total ${stats.total_records_all} records. ${stats.custom_models} modèles custom.\n\nPAR CATEGORIE : ${catLine}\n\nTOP 30 MODELES :\n${topLines}\n\n=== DETAIL PAR CATEGORIE ===${catDetailsLines}`;
        // Modale amelioree : bouton fermer visible, bouton copier, scroll, Escape, click externe
        const fullText = `${summary}\n\n\n=== JSON COMPLET (pour partager a Claude) ===\n${JSON.stringify({stats, by_category: byCat, top_30_models: topModels}, null, 2)}`;
        const backdrop = document.createElement('div');
        backdrop.id = 'introspect-backdrop';
        backdrop.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.85);z-index:9998;display:flex;align-items:center;justify-content:center';
        const modal = document.createElement('div');
        modal.style.cssText = 'background:#0b1220;border:1px solid var(--border);border-radius:12px;padding:16px 20px 20px;width:90vw;max-width:1000px;height:85vh;display:flex;flex-direction:column;box-shadow:0 10px 40px rgba(0,0,0,0.8)';
        const escapeHtml = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;');
        modal.innerHTML = `
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;flex-shrink:0">
            <h3 style="margin:0">🔍 Inventaire Odoo</h3>
            <div style="display:flex;gap:8px">
              <button class="btn" id="introspect-copy-btn" style="background:#10b981;color:white;padding:6px 14px;border:none;border-radius:6px;cursor:pointer;font-weight:600">📋 Tout copier</button>
              <button class="btn" id="introspect-close-btn" style="background:#ef4444;color:white;padding:6px 14px;border:none;border-radius:6px;cursor:pointer;font-weight:700">✕ Fermer</button>
            </div>
          </div>
          <textarea id="introspect-textarea" readonly style="flex:1;width:100%;font-family:var(--mono);font-size:11px;padding:10px;background:var(--bg2);color:var(--text1);border:1px solid var(--border);border-radius:8px;overflow:auto;resize:none">${escapeHtml(fullText)}</textarea>
          <div style="margin-top:8px;font-size:11px;color:var(--text3);flex-shrink:0">Échap ou clic en dehors pour fermer — le bouton vert copie tout en un clic</div>`;
        backdrop.appendChild(modal);
        document.body.appendChild(backdrop);
        const closeModal = () => { backdrop.remove(); document.removeEventListener('keydown', onEsc); };
        const onEsc = e => { if(e.key === 'Escape') closeModal(); };
        document.addEventListener('keydown', onEsc);
        backdrop.addEventListener('click', e => { if(e.target === backdrop) closeModal(); });
        document.getElementById('introspect-close-btn').onclick = closeModal;
        document.getElementById('introspect-copy-btn').onclick = async () => {
          const b = document.getElementById('introspect-copy-btn');
          try{
            await navigator.clipboard.writeText(fullText);
            b.innerHTML = '✓ Copié !';
          }catch(err){
            // Fallback si clipboard API bloquee : select all dans le textarea
            const ta = document.getElementById('introspect-textarea');
            ta.focus(); ta.select();
            document.execCommand('copy');
            b.innerHTML = '✓ Copié (fallback)';
          }
          setTimeout(()=>{ b.innerHTML = '📋 Tout copier'; }, 2000);
        };
        setAlert('companies-alert', `✅ Inventaire OK : ${stats.total_models_filtered} modeles. Resultats dans la fenetre.`, 'ok');
        return;
      }
      if(sd.status === 'error'){
        throw new Error(sd.error || sd.message || 'Erreur inconnue');
      }
    }
    throw new Error('Timeout 10 min');
  }catch(e){
    setAlert('companies-alert', '❌ Inventaire echoue : '+e.message, 'err');
  }finally{
    btn.disabled = false;
    btn.innerHTML = orig;
  }
}

// NOTE : la fonction vectorizeOdoo() a ete supprimee le 19/04/2026.
// C etait l ancien pipeline de vectorisation Odoo hardcode du 18/04
// (partners + devis + leads + events avec logique metier dans le route
// /admin/odoo/vectorize). Elle est remplacee integralement par le
// Scanner Universel (Setup > Manifests + Scanner > Test/Completer/P1).
// L endpoint backend est conserve pour compatibilite mais plus appele.

async function discoverTool(tenantId,toolType,btn){
  const orig=btn.innerHTML;
  btn.disabled=true;
  // Pour Odoo → une seule découverte. Pour Microsoft/Gmail → enchaîner drive + calendar + contacts.
  const batteries = (toolType === 'odoo') ? ['odoo'] : ['drive','calendar','contacts'];
  const totals = {discovered:0, matched:0, errors:[]};
  // Accumulateur pour les stats détaillées (entités réellement ingérées dans
  // entity_links, cf. populate_from_odoo/drive/calendar/contacts) — séparé
  // du simple "discovered" qui n'est que le nombre de modèles/schémas détectés.
  const graphStats = {};
  try{
    for (const batt of batteries) {
      btn.innerHTML = `⏳ ${batt}…`;
      const r = await fetch(`/admin/discover/${tenantId}/${batt}`);
      const d = await r.json();
      totals.discovered += (d.discovered || 0);
      if (d.graph && d.graph.matched) totals.matched += d.graph.matched;
      if (d.errors && d.errors.length) totals.errors.push(...d.errors.slice(0, 3));
      // Cumuler les stats d'ingestion (team_members, contacts, invoices,
      // orders, folders, files, events, etc. selon le type de connecteur)
      if (d.graph && typeof d.graph === 'object') {
        Object.entries(d.graph).forEach(([k, v]) => {
          if (typeof v === 'number') graphStats[k] = (graphStats[k] || 0) + v;
        });
      }
    }
    if(totals.discovered > 0){
      btn.innerHTML = `✅ ${totals.discovered} schéma(s)`;
      // Construire le détail lisible : "7 équipiers · 342 contacts · 156 factures · 42 devis"
      const statLabels = {
        team_members: 'équipier(s)', contacts: 'contact(s)',
        invoices: 'facture(s)', orders: 'devis',
        leads: 'lead(s)', projects: 'projet(s)', tasks: 'tâche(s)',
        planning_slots: 'créneau(x) planning', tickets: 'ticket(s) SAV',
        payments: 'paiement(s)',
        folders: 'dossier(s)', files: 'fichier(s)',
        events: 'événement(s)', matched: 'match(s) graphe',
      };
      const details = Object.entries(graphStats)
        .filter(([k, v]) => v > 0 && statLabels[k])
        .map(([k, v]) => `${v} ${statLabels[k]}`)
        .join(' · ');
      const message = details
        ? `${toolType} : ${totals.discovered} schéma(s) · ${details}`
        : `${totals.discovered} schéma(s) ${toolType} découvert(s)`;
      setAlert('companies-alert', message, 'ok');
    } else {
      btn.innerHTML = '❌ Rien trouvé';
      setAlert('companies-alert',
        totals.errors[0] || `Aucun élément découvert pour ${toolType}`, 'err');
    }
  }catch(e){
    btn.innerHTML='❌ Erreur';
    setAlert('companies-alert','Erreur réseau : '+e.message, 'err');
  }
  setTimeout(()=>{btn.innerHTML=orig;btn.disabled=false;}, 6000);
}

async function deleteConn(connId,tenantId,idx){
  if(!confirm('Supprimer cette connexion et tous ses accès ?')) return;
  const url=isAdminOrSuper()?`/admin/connections/${tenantId}/${connId}`:'/tenant/connections/'+connId;
  try{await fetch(url,{method:'DELETE'});loadConnections(tenantId,idx);}catch(e){setAlert('companies-alert','❌ '+e.message,'err');}
}

function toggleAssignPanel(connId,tenantId,idx){
  const panel=document.getElementById('assign-panel-'+connId);
  if(panel.style.display==='block'){panel.style.display='none';return;}
  // Trouver les users de ce tenant
  const tenant=_lastTenants.find(t=>t.tenant_id===tenantId);
  if(!tenant){panel.innerHTML='Erreur: tenant introuvable';panel.style.display='block';return;}
  const users=tenant.users||[];
  panel.innerHTML=`
    <div style="margin-bottom:6px;display:flex;gap:6px">
      <button class="btn btn-accent" style="padding:2px 10px;font-size:10px" onclick="assignAll(${connId},'${tenantId}',${idx})">✅ Tous</button>
      <button class="btn btn-ghost" style="padding:2px 10px;font-size:10px" onclick="unassignAll(${connId},'${tenantId}',${idx})">❌ Aucun</button>
      <select id="assign-level-${connId}" style="padding:2px 6px;background:var(--bg1);border:1px solid var(--border);border-radius:4px;color:var(--text1);font-size:10px">
        <option value="read_only">Lecture seule</option><option value="write" selected>Lecture + écriture</option><option value="full">Accès complet</option>
      </select>
    </div>
    <div style="display:flex;gap:4px;flex-wrap:wrap">${users.map(u=>
      `<button class="btn btn-ghost" style="padding:3px 10px;font-size:11px" onclick="assignOneUser(${connId},'${u.username}','${tenantId}',${idx})">${u.username}</button>`
    ).join('')}</div>`;
  panel.style.display='block';
}

async function assignOneUser(connId,username,tenantId,idx){
  const level=document.getElementById('assign-level-'+connId).value;
  const url=isAdminOrSuper()?`/admin/connections/${connId}/assign`:'/tenant/connections/'+connId+'/assign';
  try{
    await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,access_level:level})});
    await loadConnections(tenantId,idx);
    toggleAssignPanel(connId,tenantId,idx);
  }catch(e){setAlert('companies-alert','❌ '+e.message,'err');}
}

async function assignAll(connId,tenantId,idx){
  const tenant=_lastTenants.find(t=>t.tenant_id===tenantId);
  if(!tenant) return;
  const level=document.getElementById('assign-level-'+connId).value;
  const url=isAdminOrSuper()?`/admin/connections/${connId}/assign`:'/tenant/connections/'+connId+'/assign';
  for(const u of tenant.users){
    try{await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u.username,access_level:level})});}catch(e){}
  }
  await loadConnections(tenantId,idx);
  toggleAssignPanel(connId,tenantId,idx);
}

async function unassignAll(connId,tenantId,idx){
  const tenant=_lastTenants.find(t=>t.tenant_id===tenantId);
  if(!tenant) return;
  for(const u of tenant.users){
    const url=isAdminOrSuper()?`/admin/connections/${connId}/assign/${u.username}`:'/tenant/connections/'+connId+'/assign/'+u.username;
    try{await fetch(url,{method:'DELETE'});}catch(e){}
  }
  await loadConnections(tenantId,idx);
  toggleAssignPanel(connId,tenantId,idx);
}

async function renameConn(connId,tenantId,idx,currentLabel){
  const newLabel=prompt('Nouveau nom de la connexion :',currentLabel);
  if(!newLabel||newLabel===currentLabel) return;
  const url=isAdminOrSuper()?`/admin/connections/${tenantId}/${connId}`:'/tenant/connections/'+connId;
  try{
    await fetch(url,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({label:newLabel})});
    loadConnections(tenantId,idx);
  }catch(e){setAlert('companies-alert','❌ '+e.message,'err');}
}

async function unassignConn(connId,username,tenantId,idx){
  if(!confirm(`Retirer l'accès de ${username} ?`)) return;
  const url=isAdminOrSuper()?`/admin/connections/${connId}/assign/${username}`:'/tenant/connections/'+connId+'/assign/'+username;
  const panelWasOpen=document.getElementById('assign-panel-'+connId)?.style.display==='block';
  try{await fetch(url,{method:'DELETE'});await loadConnections(tenantId,idx);if(panelWasOpen)toggleAssignPanel(connId,tenantId,idx);}catch(e){setAlert('companies-alert','❌ '+e.message,'err');}
}

async function unlockUser(username){
  if(!confirm(`Débloquer le compte "${username}" ?\n\nAssurez-vous d'avoir vérifié l'identité.`)) return;
  const d=await(await fetch(`/admin/unlock-user/${username}`,{method:'POST'})).json();
  if(d.status==='ok'){setAlert('user-alert','🔓 '+d.message,'ok');loadUsers();}
  else{setAlert('user-alert','❌ '+(d.message||d.error),'err');}
}

// ─ DIAGNOSTIC CONNECTEURS ─
async function runDiag(btn){
  const el=document.getElementById('diag-result');
  el.innerHTML='<span class="loader"></span> Test en cours… (5s max par connecteur)';
  if(btn) btn.disabled=true;
  try{
    const d=await(await fetch('/admin/diag')).json();
    const icons={ok:'🟢', error:'🔴', not_configured:'⚫'};
    const labels={microsoft:'Microsoft 365',gmail:'Gmail',odoo:'Odoo',twilio:'Twilio',elevenlabs:'ElevenLabs'};
    el.innerHTML='<div class="diag-grid">'+Object.entries(d).map(([key,v])=>`
      <div class="diag-item">
        <div class="diag-item-name">${icons[v.status]||'⚫'} ${labels[key]||key}</div>
        <div class="diag-item-detail">${v.detail||''}</div>
      </div>`).join('')+'</div>';
  }catch(e){el.textContent='❌ Erreur: '+e.message;}
  if(btn){btn.disabled=false;}
}

// ─ ALERTES SYSTEME (Bloc 2.5, 18/04/2026) ─
// Affiche un bandeau rouge/orange en haut du panel admin pour toute alerte
// active (limites fetch approchees, modules Odoo manquants, etc.).
async function loadSystemAlerts(){
  try{
    const r = await fetch('/admin/alerts');
    const d = await r.json();
    const box = document.getElementById('system-alerts-banner');
    if (!box) return;
    const alerts = (d.alerts || []).filter(a => !a.acknowledged);
    if (alerts.length === 0){ box.innerHTML = ''; box.style.display = 'none'; return; }
    const bySev = {critical: [], warning: [], info: []};
    alerts.forEach(a => (bySev[a.severity] || bySev.warning).push(a));
    const colors = {
      critical: {bg:'#7f1d1d', border:'#dc2626', icon:'🚨', label:'CRITIQUE'},
      warning:  {bg:'#78350f', border:'#f59e0b', icon:'⚠️', label:'ALERTE'},
      info:     {bg:'#1e3a8a', border:'#3b82f6', icon:'ℹ️', label:'INFO'},
    };
    let html = '';
    ['critical','warning','info'].forEach(sev => {
      if (!bySev[sev].length) return;
      const c = colors[sev];
      bySev[sev].forEach(a => {
        const detailsBits = [];
        if (a.details && typeof a.details === 'object'){
          if (a.details.usage_pct) detailsBits.push(`${a.details.usage_pct}% utilise`);
          if (a.details.total_in_source) detailsBits.push(`total Odoo: ${a.details.total_in_source}`);
          if (a.details.fetched) detailsBits.push(`recupere: ${a.details.fetched}`);
          if (a.details.limit) detailsBits.push(`limite: ${a.details.limit}`);
        }
        const detailsStr = detailsBits.length ? ` (${detailsBits.join(' · ')})` : '';
        html += `<div style="padding:10px 14px;background:${c.bg};border-left:4px solid ${c.border};border-radius:6px;margin-bottom:6px;color:#fff;display:flex;align-items:center;gap:10px;font-size:12px">
          <span style="font-size:16px">${c.icon}</span>
          <div style="flex:1">
            <strong>${c.label}</strong> — <span style="opacity:0.8">${a.component}</span><br>
            ${a.message}${detailsStr}
          </div>
          <button class="btn btn-ghost" style="padding:4px 10px;font-size:11px;background:rgba(255,255,255,0.15);color:#fff;border:1px solid rgba(255,255,255,0.3)" onclick="acknowledgeAlert(${a.id})">✓ Acquitter</button>
        </div>`;
      });
    });
    box.innerHTML = html;
    box.style.display = 'block';
  }catch(e){ /* silencieux : une erreur de chargement d'alertes ne doit pas casser l'UI */ }
}

async function acknowledgeAlert(alertId){
  try{
    await fetch(`/admin/alerts/${alertId}/acknowledge`, {method: 'POST'});
    await loadSystemAlerts();  // recharger pour refleter l'acquittement
  }catch(e){}
}

// ─ SOCIÉTÉS ─
async function loadCompanies(){
  // Mémoriser les cartes ouvertes avant rechargement
  const openCards=[];
  document.querySelectorAll('.tenant-body.open').forEach(el=>{const m=el.id.match(/body-(\d+)/);if(m)openCards.push(parseInt(m[1]));});
  document.getElementById('companies-list').innerHTML='<div style="color:var(--text3);font-family:var(--mono);font-size:12px"><span class="loader"></span> Chargement...</div>';
  document.getElementById('companies-alert').className='alert';
  try{
    const url=isSuperAdmin?'/admin/tenants-overview':'/tenant/my-overview';
    const tenants=await(await fetch(url)).json();
    document.getElementById('companies-count').textContent=`${tenants.length} société(s)`;
    _lastTenants=tenants;
    if(!tenants.length){document.getElementById('companies-list').innerHTML='<div style="color:var(--text3);font-family:var(--mono);font-size:12px">Aucune société.</div>';return;}
    document.getElementById('companies-list').innerHTML=tenants.map((t,i)=>{
      const msBar=t.user_count>0?`${t.ms_connected_count}/${t.user_count} MS connectés`:'—';
      const spSite=t.sharepoint_site||'';const spFolder=t.sharepoint_folder||'';const spDrive=t.sharepoint_drive||'';
      const settingsEscaped=JSON.stringify(t.settings||{}).replace(/'/g,"&apos;").replace(/"/g,'&quot;');
      const legalForm=(t.settings||{}).legal_form||'';const siret=(t.settings||{}).siret||'';
      return `<div class="tenant-card">
        <div class="tenant-header" onclick="toggleTenant(${i})">
          <span class="tenant-toggle" id="toggle-${i}">›</span>
          <span class="tenant-name">🏢 ${t.name}${(t.settings||{}).suspended?'<span class="badge badge-yellow" style="margin-left:8px;font-size:10px">⏸️ SUSPENDU</span>':''}${legalForm?' <span style="font-size:11px;color:var(--text3);font-weight:400">'+legalForm+'</span>':''}</span>
          <div class="tenant-meta"><span>👥 ${t.user_count} collaborateur(s)</span><span>📬 ${fmt(t.total_mails)} mails</span><span>💬 ${fmt(t.total_conv)} conversations</span><span id="conn-summary-${i}" style="display:inline-flex;gap:6px;align-items:center">…</span>${siret?`<span style="color:var(--text3)">SIRET: ${siret}</span>`:''}${isAdminOrSuper()?`<button class="btn tenant-lock-btn" id="lock-btn-${i}" data-tenant-id="${t.tenant_id}" data-tenant-name="${(t.name||'').replace(/"/g,'&quot;')}" onclick="event.stopPropagation();const btn=this;toggleReadOnlyForTenant(btn.dataset.tenantId,btn.dataset.tenantName)" style="background:transparent;border:1px solid var(--border);color:var(--text2);padding:2px 8px;font-size:11px;border-radius:6px;cursor:pointer;margin-left:auto" title="Chargement de l etat...">🔓 Lecture écriture</button>`:''}</div>
        </div>
        <div class="tenant-body" id="body-${i}">
          <table><thead><tr><th>Identifiant</th><th>Email</th><th>Rôle</th><th>MS</th><th>Mails</th><th>Conv.</th><th>Dernière connexion</th><th>Actions</th></tr></thead>
          <tbody>${t.users.map(u=>`<tr class="${u.account_locked||u.suspended?'row-locked':''}">
            <td><strong class="mono">${u.username}</strong>${u.account_locked?'<span class="badge badge-red" style="margin-left:6px;font-size:9px">🔒</span>':''}${u.suspended?'<span class="badge badge-yellow" style="margin-left:6px;font-size:9px">⏸️</span>':''}${u.must_reset_password&&!u.account_locked?'<span class="badge badge-yellow" style="margin-left:6px;font-size:9px">⚠️</span>':''}</td>
            <td style="font-size:12px;color:var(--text2)">${u.email||'—'}</td>
            <td><span class="badge ${u.scope==='super_admin'?'badge-blue':u.scope==='admin'?'badge-blue':u.scope==='tenant_admin'?'badge-green':'badge-gray'}">${u.scope}</span></td>
            <td><span class="badge ${u.ms_connected?'badge-ms-ok':'badge-red'}">${u.ms_connected?'✅ OK':'❌ Non'}</span></td>
            <td class="mono">${fmt(u.mails)}</td><td class="mono">${fmt(u.conv)}</td>
            <td class="mono" style="font-size:11px;color:var(--text2)">${fmtDateShort(u.last_login)}</td>
            <td style="display:flex;gap:5px;flex-wrap:wrap">
              <button class="btn btn-ghost" style="padding:4px 9px;font-size:11px" onclick="showToolsCompany('${u.username}')">🔧</button>
              <button class="btn btn-accent" style="padding:4px 9px;font-size:11px" onclick="editUser('${u.username}','${u.email||''}','${u.scope}','${u.phone||''}')">Modifier</button>
              <button class="btn btn-ghost" style="padding:4px 9px;font-size:11px" onclick="seedUser('${u.username}')">🌱</button>
              ${!isSuperAdmin&&u.scope!=='admin'&&u.scope!=='super_admin'?`<button class="btn ${u.direct_actions_override===true?'btn-accent':u.direct_actions_override===false?'btn-danger':'btn-ghost'}" style="padding:4px 9px;font-size:10px" onclick="cycleUserDirectActions('${u.username}',${u.direct_actions_override===null||u.direct_actions_override===undefined?'null':u.direct_actions_override})" title="Actions directes fichiers">${u.direct_actions_override===true?'📂 ON':u.direct_actions_override===false?'📂 OFF':'📂 ='}</button>`:''}
              ${u.suspended?`<button class="btn btn-unlock" style="padding:4px 9px;font-size:11px" onclick="unsuspendUser('${u.username}')">▶️</button>`:`${u.scope!=='admin'&&u.scope!=='super_admin'?`<button class="btn btn-ghost" style="padding:4px 9px;font-size:11px;color:var(--yellow)" onclick="suspendUser('${u.username}')">⏸️</button>`:''}`}
              ${u.account_locked?`<button class="btn btn-unlock" style="padding:4px 9px;font-size:11px" onclick="unlockUser('${u.username}')">🔓</button>`:''}
              ${u.scope!=='admin'&&u.scope!=='super_admin'?`<button class="btn btn-danger" style="padding:4px 9px;font-size:11px" onclick="askDeleteUser('${u.username}')">Suppr.</button>`:''}
            </td></tr>`).join('')}</tbody></table>
          <div class="sp-config-panel">
            <div style="margin-bottom:12px"><button class="btn btn-primary" style="font-size:12px;padding:6px 14px" onclick="openCreateUserForTenant('${t.tenant_id}','${t.name.replace(/'/g,"\\'")}')">➕ Ajouter un collaborateur</button></div>
            ${!isSuperAdmin?`<div style="margin-bottom:16px;padding:10px 14px;background:rgba(99,102,241,.06);border-radius:8px;display:flex;align-items:center;gap:12px;flex-wrap:wrap">
              <span style="font-size:13px;font-weight:600">Actions directes fichiers</span>
              <button class="btn ${(t.settings||{}).direct_actions?'btn-accent':'btn-ghost'}" style="padding:4px 14px;font-size:11px;min-width:80px" onclick="toggleTenantDirectActions('${t.tenant_id}',${!!(t.settings||{}).direct_actions})">${(t.settings||{}).direct_actions?'🟢 ON':'🔴 OFF'} (société)</button>
              <span style="font-size:11px;color:var(--text3)">${(t.settings||{}).direct_actions?'Actions fichiers sans validation':'Validation humaine requise'}</span>
            </div>`:''}
            <div class="sp-config-title">⚙️ Configuration SharePoint (optionnel)</div>
            <div class="sp-config-grid">
              <div><label>Site SharePoint</label><input type="text" id="sp-site-${i}" value="${spSite}" placeholder="Commun"></div>
              <div><label>Dossier racine</label><input type="text" id="sp-folder-${i}" value="${spFolder}" placeholder="1_Photovoltaïque"></div>
              <div><label>Bibliothèque</label><input type="text" id="sp-drive-${i}" value="${spDrive}" placeholder="Documents"></div>
              <div><button class="btn btn-accent" onclick="saveSharePointConfig('${t.tenant_id}',${i})">💾 Enregistrer</button></div>
            </div><div class="sp-result" id="sp-result-${i}"></div>
            <div style="margin-top:20px">
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
                <div class="sp-config-title" style="margin:0">📡 Connexions</div>
                <button class="btn btn-accent" style="font-size:11px;padding:4px 12px" onclick="showAddConnection('${t.tenant_id}',${i})">+ Ajouter</button>
              </div>
              <div id="conn-add-${i}" style="display:none;margin-bottom:12px;padding:10px;background:rgba(99,102,241,.04);border-radius:8px">
                <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
                  <input type="text" id="conn-type-${i}" placeholder="Type (outlook, gmail, drive...)" style="padding:5px 8px;background:var(--bg1);border:1px solid var(--border);border-radius:6px;color:var(--text1);font-size:11px;width:140px">
                  <input type="text" id="conn-label-${i}" placeholder="Nom (ex: Boîte contact@...)" style="padding:5px 8px;background:var(--bg1);border:1px solid var(--border);border-radius:6px;color:var(--text1);font-size:11px;flex:1;min-width:180px">
                  <button class="btn btn-primary" style="font-size:11px;padding:4px 12px" onclick="createConnection('${t.tenant_id}',${i})">Créer</button>
                  <button class="btn btn-ghost" style="font-size:11px;padding:4px 8px" onclick="document.getElementById('conn-add-${i}').style.display='none'">✕</button>
                </div>
              </div>
              <div id="conn-list-${i}" style="font-family:var(--mono);font-size:11px;color:var(--text3)">Chargement...</div>
            </div>
            <div style="margin-top:20px">
              <div class="sp-config-title" style="margin-bottom:10px">🔐 Permissions des connexions (plafond super admin)</div>
              <div id="perms-list-${i}" style="font-family:var(--mono);font-size:11px;color:var(--text3)">Chargement...</div>
              <div style="font-size:10px;color:var(--text3);margin-top:6px;font-style:italic">Le plafond super admin definit le maximum que le tenant admin peut appliquer.</div>
            </div>
          </div>
          ${isSuperAdmin?`<div class="tenant-admin-bar">
            ${(t.settings||{}).suspended?`<button class="btn btn-unlock" style="font-size:11px;padding:5px 12px" onclick="unsuspendTenant('${t.tenant_id}')">▶️ Réactiver</button>`:`<button class="btn btn-ghost" style="font-size:11px;padding:5px 12px;color:var(--yellow)" onclick="suspendTenant('${t.tenant_id}','${t.name.replace(/'/g,"\\'")}')">⏸️ Suspendre</button>`}
            <button class="btn btn-accent" style="font-size:11px;padding:5px 12px" onclick="openEditTenant('${t.tenant_id}','${t.name.replace(/'/g,"\\'")}','${settingsEscaped}','${spSite}','${spFolder}')">✏️ Modifier</button>
            <button class="btn btn-danger" style="font-size:11px;padding:5px 12px" onclick="openDeleteTenant('${t.tenant_id}','${t.name.replace(/'/g,"\\'")}')">🗑️ Supprimer</button>
            <span class="tenant-id-tag">ID : ${t.tenant_id}</span></div>`:''}
        </div></div>`;
    }).join('');
  }catch(e){document.getElementById('companies-list').innerHTML=`<div style="color:var(--red);font-family:var(--mono);font-size:12px">❌ Erreur: ${e.message}</div>`;}
  // Restaurer les cartes qui étaient ouvertes
  openCards.forEach(i=>toggleTenant(i));
  // Charger les connexions pour chaque tenant
  if(typeof _lastTenants!=='undefined') _lastTenants.forEach((t,i)=>loadConnections(t.tenant_id,i));
  // Charger l etat de verrouillage (🔒/🔓) de chaque tenant — Fix 2 du plan
  if(typeof _lastTenants!=='undefined') _lastTenants.forEach((t,i)=>updateLockButtonState(t.tenant_id,i));
  // Charger les permissions par connexion — Fix 3 du plan
  if(typeof _lastTenants!=='undefined') _lastTenants.forEach((t,i)=>loadPermissionsForTenant(t.tenant_id,i));
}

async function updateLockButtonState(tenantId, idx){
  try{
    const d = await (await fetch(`/admin/tenant/${encodeURIComponent(tenantId)}/lock-status?_=` + Date.now(), {cache: 'no-store'})).json();
    _tenantLockState[tenantId] = d;
    const btn = document.getElementById('lock-btn-'+idx);
    if(!btn) return;
    if(d.is_locked === true){
      btn.innerHTML = '🔒 Lecture seule';
      btn.style.background = '#7f1d1d';  // rouge fonce
      btn.style.borderColor = '#dc2626';
      btn.style.color = '#fca5a5';
      btn.title = `Ce tenant a ${d.locked_connections}/${d.total_connections} connexion(s) en lecture seule. Cliquer pour restaurer.`;
    } else {
      btn.innerHTML = '🔓 Lecture écriture';
      btn.style.background = 'transparent';
      btn.style.borderColor = 'var(--border)';
      btn.style.color = 'var(--text2)';
      btn.title = 'Toutes les connexions ont leurs permissions actives. Cliquer pour verrouiller tout en lecture seule.';
    }
  }catch(e){ /* silencieux */ }
}

// ─── Fix 3 : permissions par connexion dans le super admin panel ───
async function loadPermissionsForTenant(tenantId, idx){
  const list = document.getElementById('perms-list-'+idx);
  if(!list) return;
  try{
    const data = await (await fetch(`/admin/tenant/${encodeURIComponent(tenantId)}/permissions?_=` + Date.now(), {cache: 'no-store'})).json();
    if(!Array.isArray(data) || data.length === 0){
      list.innerHTML = '<div style="color:var(--text3)">Aucune connexion.</div>';
      return;
    }
    // Detection verrouillage : majorite en tenant=read avec previous != null
    const lockedCount = data.filter(c => c.tenant_admin_level === 'read' && c.previous_level).length;
    const isAllLocked = lockedCount > 0 && lockedCount >= data.length / 2;
    const LABELS = {'read':'Lecture','read_write':'Lect+Écrit','read_write_delete':'Tout'};
    const ICONS = {'odoo':'🗂️','gmail':'📧','outlook':'📧','microsoft':'📧','mailbox':'📧','sharepoint':'📁','drive':'📁','teams':'💬'};
    let html = '';
    if(isAllLocked){
      html += '<div style="background:#7f1d1d;border:1px solid #dc2626;color:#fca5a5;padding:8px 12px;border-radius:6px;margin-bottom:8px;font-size:11px"><strong>🔒 Verrouillé en lecture seule.</strong> Les radios "Niveau appliqué" sont désactivés. Utilise le bouton 🔒 en haut du tenant pour restaurer.</div>';
    }
    html += '<table style="width:100%;border-collapse:collapse;font-size:11px"><thead><tr style="border-bottom:1px solid var(--border);color:var(--text3)"><th style="text-align:left;padding:4px 6px">Connexion</th><th style="padding:4px 6px">Plafond super admin</th><th style="padding:4px 6px">Niveau appliqué (tenant)</th></tr></thead><tbody>';
    for(const c of data){
      const icon = ICONS[c.tool_type] || '🔧';
      const levels = ['read','read_write','read_write_delete'];
      let superRadios = '';
      // Le plafond super admin reste toujours modifiable (meme si tenant verrouille)
      for(const lvl of levels){
        const checked = c.super_admin_level === lvl;
        superRadios += `<label style="margin-right:6px;cursor:pointer;font-size:10px"><input type="radio" name="sup-${c.connection_id}" value="${lvl}" ${checked?'checked':''} onchange="updatePermissionCap('${tenantId}',${c.connection_id},'${lvl}','super_admin',${idx})"/> ${LABELS[lvl]}</label>`;
      }
      const maxRank = levels.indexOf(c.super_admin_level);
      let tenantRadios = '';
      for(let i=0;i<levels.length;i++){
        const lvl = levels[i];
        // Disable si : au-dessus plafond OU verrouille globalement
        const disabled = (i > maxRank) || isAllLocked;
        const checked = c.tenant_admin_level === lvl;
        tenantRadios += `<label style="margin-right:6px;opacity:${disabled?'0.3':'1'};cursor:${disabled?'not-allowed':'pointer'};font-size:10px"><input type="radio" name="ten-${c.connection_id}" value="${lvl}" ${checked?'checked':''} ${disabled?'disabled':''} onchange="updatePermissionCap('${tenantId}',${c.connection_id},'${lvl}','tenant_admin',${idx})"/> ${LABELS[lvl]}</label>`;
      }
      html += `<tr style="border-bottom:1px solid var(--border)"><td style="padding:6px"><strong>${icon} ${c.name}</strong><br><span style="font-size:9px;color:var(--text3)">${c.tool_type}</span></td><td style="padding:6px">${superRadios}</td><td style="padding:6px${isAllLocked ? ';opacity:0.5' : ''}">${tenantRadios}</td></tr>`;
    }
    html += '</tbody></table>';
    list.innerHTML = html;
  }catch(e){
    list.innerHTML = '<div style="color:var(--red)">Erreur: '+e.message+'</div>';
  }
}

async function updatePermissionCap(tenantId, connectionId, newLevel, scopeType, idx){
  try{
    const r = await fetch(`/admin/tenant/${encodeURIComponent(tenantId)}/permissions/update`, {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({connection_id: connectionId, new_level: newLevel, scope_type: scopeType})
    });
    const d = await r.json();
    if(d.status === 'ok'){
      const lab = scopeType === 'super_admin' ? 'Plafond super admin' : 'Niveau applique';
      setAlert('companies-alert', `✅ ${lab} : ${newLevel}`, 'ok');
      loadPermissionsForTenant(tenantId, idx);
      updateLockButtonState(tenantId, idx);
    } else {
      setAlert('companies-alert', '❌ '+(d.message||'Erreur'), 'err');
    }
  }catch(e){
    setAlert('companies-alert', '❌ '+e.message, 'err');
  }
}
function toggleTenant(i){document.getElementById('body-'+i).classList.toggle('open');document.getElementById('toggle-'+i).classList.toggle('open');}
function filterCompanies(){
  const q=(document.getElementById('companies-search').value||'').toLowerCase().trim();
  document.querySelectorAll('.tenant-card').forEach(card=>{
    if(!q){card.style.display='';return;}
    const text=card.textContent.toLowerCase();
    const match=text.includes(q);
    card.style.display=match?'':'none';
    // Auto-ouvrir si match sur un utilisateur
    if(match&&q.length>1){const body=card.querySelector('.tenant-body');const toggle=card.querySelector('.tenant-toggle');if(body&&!body.classList.contains('open')){body.classList.add('open');if(toggle)toggle.classList.add('open');}}
  });
}
async function saveSharePointConfig(tenantId,i){
  const site=document.getElementById(`sp-site-${i}`).value.trim();const folder=document.getElementById(`sp-folder-${i}`).value.trim();const drive=document.getElementById(`sp-drive-${i}`).value.trim()||'Documents';
  const result=document.getElementById(`sp-result-${i}`);if(!site||!folder){result.className='sp-result err';result.textContent='❌ Site et dossier requis.';return;}
  result.className='sp-result';result.textContent='⏳ Enregistrement...';
  try{const d=await(await fetch(`/admin/tenants/${tenantId}/sharepoint`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({sharepoint_site:site,sharepoint_folder:folder,sharepoint_drive:drive})})).json();
    if(d.status==='ok'){result.className='sp-result ok';result.textContent='✅ Config mise à jour.';}else{result.className='sp-result err';result.textContent='❌ '+(d.message||'Erreur');}
  }catch(e){result.className='sp-result err';result.textContent='❌ '+e.message;}
}
async function createTenant(){
  const name=document.getElementById('tenant-new-name').value.trim();
  const id=normalizeTenantId(name);
  document.getElementById('tenant-new-id').value=id;
  const legalForm=document.getElementById('tenant-new-legal-form').value;
  const siret=document.getElementById('tenant-new-siret').value.replace(/\D/g,'');
  const rue=document.getElementById('tenant-new-rue').value.trim();
  const cp=document.getElementById('tenant-new-cp').value.trim();
  const ville=document.getElementById('tenant-new-ville').value.trim();
  if(!name){setAlert('create-tenant-alert','Le nom de la société est requis.','err');return;}
  if(!siret||siret.length!==14){setAlert('create-tenant-alert','Le SIRET est obligatoire (14 chiffres).','err');return;}
  if(!rue||!cp||!ville){setAlert('create-tenant-alert','L\'adresse complète est requise (rue, code postal, ville).','err');return;}
  if(cp.length!==5){setAlert('create-tenant-alert','Le code postal doit faire 5 chiffres.','err');return;}
  const settings={};if(legalForm) settings.legal_form=legalForm;
  settings.siret=siret;settings.rue=rue;settings.code_postal=cp;settings.ville=ville;
  settings.address=rue+', '+cp+' '+ville;
  try{const d=await(await fetch('/admin/tenants',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,name,settings})})).json();
    if(d.status==='ok'||d.tenant_id){setAlert('companies-alert',`✅ Société "${name}" créée (ID : ${d.tenant_id||id}). Ajoutez maintenant un administrateur.`,'ok');closeModal('create-tenant');['tenant-new-name','tenant-new-siret','tenant-new-rue','tenant-new-cp','tenant-new-ville'].forEach(id=>{const el=document.getElementById(id);if(el)el.value='';});document.getElementById('tenant-new-legal-form').value='';loadCompanies();}
    else{setAlert('create-tenant-alert','❌ '+(d.message||d.detail||'Erreur lors de la création.'),'err');}
  }catch(e){setAlert('create-tenant-alert','❌ '+e.message,'err');}
}
function openEditTenant(id,name,settingsStr,spSite,spFolder){
  currentEditTenantId=id;document.getElementById('edit-tenant-modal-title').textContent='✏️ Modifier — '+name;document.getElementById('tenant-edit-id-display').value=id;document.getElementById('tenant-edit-name').value=name;
  document.getElementById('tenant-edit-sp-site').value=spSite||'';document.getElementById('tenant-edit-sp-folder').value=spFolder||'';
  let settings={};try{const decoded=settingsStr.replace(/&quot;/g,'"').replace(/&apos;/g,"'");settings=JSON.parse(decoded);}catch(e){}
  document.getElementById('tenant-edit-email-provider').value=settings.email_provider||'microsoft';document.getElementById('tenant-edit-settings').value=JSON.stringify(settings,null,2);
  document.getElementById('edit-tenant-alert').className='alert';openModal('edit-tenant');
}
async function saveTenant(){
  if(!currentEditTenantId) return;const name=document.getElementById('tenant-edit-name').value.trim();const spSite=document.getElementById('tenant-edit-sp-site').value.trim();const spFolder=document.getElementById('tenant-edit-sp-folder').value.trim();const emailProvider=document.getElementById('tenant-edit-email-provider').value;
  if(!name){setAlert('edit-tenant-alert','Le nom est requis.','err');return;}
  let settings={};try{settings=JSON.parse(document.getElementById('tenant-edit-settings').value||'{}');}catch(e){setAlert('edit-tenant-alert','JSON settings invalide.','err');return;}
  settings.email_provider=emailProvider;if(spFolder) settings.sharepoint_folder=spFolder;if(spSite) settings.sharepoint_site=spSite;
  try{const d=await(await fetch(`/admin/tenants/${currentEditTenantId}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,settings})})).json();
    if(d.status==='ok'||d.tenant_id){setAlert('companies-alert','✅ Société mise à jour.','ok');closeModal('edit-tenant');loadCompanies();}else{setAlert('edit-tenant-alert','❌ '+(d.message||d.detail||'Erreur'),'err');}
  }catch(e){setAlert('edit-tenant-alert','❌ '+e.message,'err');}
}
function openDeleteTenant(id,name){tenantToDelete=id;document.getElementById('delete-tenant-label').textContent=`${name} (${id})`;document.getElementById('delete-tenant-alert').className='alert';document.getElementById('delete-tenant-confirm-input').value='';document.getElementById('delete-tenant-btn').disabled=true;openModal('delete-tenant');}
async function confirmDeleteTenant(){
  const confirmInput=document.getElementById('delete-tenant-confirm-input');
  if(!confirmInput||confirmInput.value!=='SUPPRIMER'){setAlert('delete-tenant-alert','Tapez SUPPRIMER pour confirmer.','err');return;}
  if(!tenantToDelete) return;
  try{const d=await(await fetch(`/admin/tenants/${tenantToDelete}`,{method:'DELETE'})).json();
    if(d.status==='ok'){setAlert('companies-alert','✅ Société supprimée.','ok');closeModal('delete-tenant');loadCompanies();}else{setAlert('delete-tenant-alert','❌ '+(d.message||d.detail||'Erreur lors de la suppression.'),'err');}
  }catch(e){setAlert('delete-tenant-alert','❌ '+e.message,'err');}tenantToDelete=null;
}

function openModal(name){
  document.getElementById('modal-'+name).classList.add('open');
  if(name==='create-user') loadTenantDropdown();
}
function closeModal(name){
  document.getElementById('modal-'+name).classList.remove('open');
  if(name==='create-user'){const sel=document.getElementById('new-tenant');if(sel)sel.disabled=false;}
}

async function loadTenantDropdown(){
  const sel=document.getElementById('new-tenant');
  if(sel.options.length>1) return;
  sel.innerHTML='<option value="">— Choisir —</option>';
  try{
    const tenants=await(await fetch('/admin/tenants')).json();
    tenants.forEach(t=>{const o=document.createElement('option');o.value=t.id;o.textContent=t.name+' ('+t.id+')';sel.appendChild(o);});
  }catch(e){}
}

function openCreateUserForTenant(tenantId, tenantName){
  openModal('create-user');
  // Attendre que le dropdown soit chargé puis pré-sélectionner
  setTimeout(()=>{
    const sel=document.getElementById('new-tenant');
    sel.value=tenantId;
    sel.disabled=true;
    document.getElementById('create-user-alert').className='alert';
    document.getElementById('create-user-alert').textContent='Création pour : '+tenantName;
    document.getElementById('create-user-alert').className='alert ok';
  },300);
}

async function seedUser(username){
  const profile=prompt('Profil de seeding :\\n- generic\\n- pv_french\\n- event_planner\\n- artisan\\n- immobilier\\n- conseil\\n- commerce\\n- medical','generic');
  if(!profile) return;
  try{
    const d=await(await fetch('/admin/seed-user',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,profile})})).json();
    if(d.status==='ok') setAlert('user-alert','🌱 '+d.message,'ok');
    else setAlert('user-alert','❌ '+(d.message||'Erreur'),'err');
  }catch(e){setAlert('user-alert','❌ '+e.message,'err');}
}

async function suspendUser(username){
  const reason=prompt('Raison de la suspension (optionnel) :','');
  if(reason===null) return;
  const alertId=document.getElementById('tab-companies').classList.contains('active')?'companies-alert':'user-alert';
  try{
    const d=await(await fetch(`/admin/suspend-user/${username}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({reason})})).json();
    if(d.status==='ok'){setAlert(alertId,'⏸️ '+d.message,'ok');loadUsers();loadCompanies();}
    else setAlert(alertId,'❌ '+(d.message||'Erreur'),'err');
  }catch(e){setAlert(alertId,'❌ '+e.message,'err');}
}

async function unsuspendUser(username){
  if(!confirm(`Réactiver le compte "${username}" ?`)) return;
  const alertId=document.getElementById('tab-companies').classList.contains('active')?'companies-alert':'user-alert';
  try{
    const d=await(await fetch(`/admin/unsuspend-user/${username}`,{method:'POST'})).json();
    if(d.status==='ok'){setAlert(alertId,'▶️ '+d.message,'ok');loadUsers();loadCompanies();}
    else setAlert(alertId,'❌ '+(d.message||'Erreur'),'err');
  }catch(e){setAlert(alertId,'❌ '+e.message,'err');}
}

async function suspendTenant(tenantId,tenantName){
  const reason=prompt(`Suspendre la société "${tenantName}" ?\n\nTous les utilisateurs seront bloqués.\nRaison (optionnel) :`,'');
  if(reason===null) return;
  try{
    const d=await(await fetch(`/admin/suspend-tenant/${tenantId}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({reason})})).json();
    if(d.status==='ok'){setAlert('companies-alert','⏸️ '+d.message,'ok');loadCompanies();}
    else setAlert('companies-alert','❌ '+(d.message||'Erreur'),'err');
  }catch(e){setAlert('companies-alert','❌ '+e.message,'err');}
}

async function unsuspendTenant(tenantId){
  try{
    const d=await(await fetch(`/admin/unsuspend-tenant/${tenantId}`,{method:'POST'})).json();
    if(d.status==='ok'){setAlert('companies-alert','▶️ '+d.message,'ok');loadCompanies();}
    else setAlert('companies-alert','❌ '+(d.message||'Erreur'),'err');
  }catch(e){setAlert('companies-alert','❌ '+e.message,'err');}
}

async function toggleTenantDirectActions(tenantId, currentState){
  const enabled=!currentState;
  try{
    const d=await(await fetch(`/admin/direct-actions/tenant/${tenantId}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled})})).json();
    if(d.status==='ok'){setAlert('companies-alert',(enabled?'🟢':'🔴')+' '+d.message,'ok');loadCompanies();}
    else setAlert('companies-alert','❌ '+(d.message||'Erreur'),'err');
  }catch(e){setAlert('companies-alert','❌ '+e.message,'err');}
}

async function cycleUserDirectActions(username, current){
  // Cycle : null (hérité) → true (ON) → false (OFF) → null
  let next;
  if(current===null||current===undefined) next=true;
  else if(current===true) next=false;
  else next=null;
  try{
    const d=await(await fetch(`/admin/direct-actions/user/${username}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:next})})).json();
    if(d.status==='ok'){setAlert('companies-alert',(next===true?'🟢':next===false?'🔴':'🔵')+' '+d.message,'ok');loadCompanies();}
    else setAlert('companies-alert','❌ '+(d.message||'Erreur'),'err');
  }catch(e){setAlert('companies-alert','❌ '+e.message,'err');}
}
function setAlert(id,msg,type){const el=document.getElementById(id);el.className='alert '+type;el.textContent=msg;}

// USER-PHONE : createUser envoie phone, email obligatoire + tenant + profil seeding
async function createUser(){
  const username=document.getElementById('new-username').value.trim();
  const email=document.getElementById('new-email').value.trim();
  const phone=document.getElementById('new-phone').value.trim();
  const password=document.getElementById('new-password-user').value;
  const scope=document.getElementById('new-scope').value;
  const tenant_id=document.getElementById('new-tenant').value;
  const profile=document.getElementById('new-profile').value;
  if(!username||!password){setAlert('create-user-alert','Identifiant et mot de passe requis.','err');return;}
  if(!email){setAlert('create-user-alert','L\'email est obligatoire (identifiant de connexion).','err');return;}
  if(!tenant_id){setAlert('create-user-alert','Sélectionnez une société.','err');return;}
  const d=await(await fetch('/admin/create-user',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,password,email,phone:phone||null,scope,tenant_id})})).json();
  if(d.status==='ok'){
    // Seeder avec le profil choisi
    try{await fetch('/admin/seed-user',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,profile})});}catch(e){}
    setAlert('user-alert','✅ '+d.message+' (profil: '+profile+')','ok');closeModal('create-user');['new-username','new-email','new-phone','new-password-user'].forEach(id=>document.getElementById(id).value='');loadUsers();
  }
  else{setAlert('create-user-alert','❌ '+(d.message||d.error),'err');}
}
// USER-PHONE : editUser accepte phone, le pré-remplit dans la modale
function editUser(username,email,scope,phone=''){
  currentEditUser=username;
  document.getElementById('edit-modal-title').textContent='Éditer — '+username;
  document.getElementById('edit-email').value=email;
  document.getElementById('edit-phone').value=phone||'';
  document.getElementById('edit-scope').value=scope;
  document.getElementById('edit-user-alert').className='alert';
  document.getElementById('reset-result').innerHTML='';
  openModal('edit-user');
}
// USER-PHONE : saveUser envoie phone
async function saveUser(){
  const email=document.getElementById('edit-email').value.trim();
  const phone=document.getElementById('edit-phone').value.trim();
  const scope=document.getElementById('edit-scope').value;
  const d=await(await fetch(`/admin/update-user/${currentEditUser}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,scope,phone:phone||null})})).json();
  if(d.status==='ok'){setAlert('user-alert','✅ Utilisateur mis à jour.','ok');closeModal('edit-user');loadUsers();}
  else{setAlert('edit-user-alert','❌ '+(d.message||d.error),'err');}
}
async function resetPassword(){
  const d=await(await fetch(`/admin/reset-password/${currentEditUser}`,{method:'POST'})).json();
  if(d.status==='ok'){const sent=d.email_sent?`Envoyé à ${d.email}`:'Copiez le lien ci-dessous';document.getElementById('reset-result').innerHTML=`<div class="reset-box"><div style="font-family:var(--mono);font-size:11px;color:var(--green);margin-bottom:4px">✓ Lien généré — ${sent}</div><div class="reset-link">${d.reset_url}</div><button class="btn btn-ghost" style="margin-top:8px;font-size:11px;padding:4px 10px" onclick="navigator.clipboard.writeText('${d.reset_url}').then(()=>this.textContent='Copié ✓')">Copier</button></div>`;}
}
async function loadUsage() {
  const days   = parseInt(document.getElementById('usage-period').value || '30');
  const tenant = document.getElementById('usage-tenant-filter').value || '';
  const url    = `/admin/costs?days=${days}${tenant ? '&tenant_id='+encodeURIComponent(tenant) : ''}`;

  ['usage-user-tbody','usage-tenant-tbody'].forEach(id =>
    document.getElementById(id).innerHTML =
      '<tr class="loading-row"><td colspan="6"><span class="loader"></span></td></tr>');

  try {
    const d = await (await fetch(url)).json();

    // Stats globales
    const totalTokens = (d.total_input_tokens||0)+(d.total_output_tokens||0);
    document.getElementById('usage-stats').innerHTML = `
      <div class="stat-card"><div class="stat-label">Appels LLM</div><div class="stat-value accent">${fmt(d.total_calls||0)}</div></div>
      <div class="stat-card"><div class="stat-label">Tokens entrants</div><div class="stat-value">${fmt(d.total_input_tokens||0)}</div></div>
      <div class="stat-card"><div class="stat-label">Tokens sortants</div><div class="stat-value">${fmt(d.total_output_tokens||0)}</div></div>
      <div class="stat-card"><div class="stat-label">Total tokens</div><div class="stat-value green">${fmt(totalTokens)}</div></div>`;

    // Agréger par tenant depuis by_user
    const ta = {};
    for (const u of d.by_user||[]) {
      const t = u.tenant_id || '—';
      if (!ta[t]) ta[t] = {calls:0, inp:0, out:0, users:new Set()};
      ta[t].calls += u.calls||0;
      ta[t].inp   += u.input_tokens||0;
      ta[t].out   += u.output_tokens||0;
      ta[t].users.add(u.username);
    }
    document.getElementById('usage-tenant-tbody').innerHTML =
      Object.keys(ta).length
      ? Object.entries(ta).sort((a,b)=>(b[1].inp+b[1].out)-(a[1].inp+a[1].out)).map(([t,v])=>`
          <tr>
            <td><strong class="mono">${t}</strong></td>
            <td class="mono">${v.users.size}</td>
            <td class="mono">${fmt(v.calls)}</td>
            <td class="mono">${fmt(v.inp)}</td>
            <td class="mono">${fmt(v.out)}</td>
            <td class="mono"><strong>${fmt(v.inp+v.out)}</strong></td>
          </tr>`).join('')
      : '<tr class="loading-row"><td colspan="6" style="color:var(--text3)">Aucune donnée.</td></tr>';

    // Par utilisateur
    document.getElementById('usage-user-tbody').innerHTML =
      (d.by_user||[]).length
      ? (d.by_user||[]).map(u=>`
          <tr>
            <td><strong class="mono">${u.username}</strong></td>
            <td style="font-size:11px;color:var(--text3)">${u.tenant_id||'—'}</td>
            <td class="mono">${fmt(u.calls||0)}</td>
            <td class="mono">${fmt(u.input_tokens||0)}</td>
            <td class="mono">${fmt(u.output_tokens||0)}</td>
            <td class="mono"><strong>${fmt(u.tokens||0)}</strong></td>
          </tr>`).join('')
      : '<tr class="loading-row"><td colspan="6" style="color:var(--text3)">Aucune donnée.</td></tr>';

  } catch(e) {
    document.getElementById('usage-stats').innerHTML =
      `<div class="stat-card" style="color:var(--red)">❌ ${e.message}</div>`;
  }
}

function askDeleteUser(username){usernameToDelete=username;document.getElementById('delete-username-label').textContent=username;document.getElementById('delete-user-confirm-input').value='';document.getElementById('delete-user-confirm-input').placeholder=username;document.getElementById('delete-user-btn').disabled=true;openModal('delete-user');}

async function adminConfirmDelete() {
  if (!currentEditUser) return;
  if (!confirm(`Confirmer la suppression définitive de "${currentEditUser}" ? Irréversible.`)) return;
  const d = await (await fetch(`/admin/delete-user/${currentEditUser}`, {method:'DELETE'})).json();
  if (d.status === 'ok') { setAlert('user-alert','✅ '+d.message,'ok'); closeModal('edit-user'); loadUsers(); loadCompanies(); }
  else { setAlert('edit-user-alert','❌ '+(d.message||d.error),'err'); }
}

async function adminRejectDelete() {
  if (!currentEditUser) return;
  const d = await (await fetch(`/admin/users/${currentEditUser}/reject-delete`, {method:'POST'})).json();
  if (d.status === 'ok') { setAlert('user-alert','✅ Demande de suppression refusée.','ok'); closeModal('edit-user'); loadUsers(); }
  else { setAlert('edit-user-alert','❌ '+(d.message||d.error),'err'); }
}
async function confirmDeleteUser(){
  const confirmInput=document.getElementById('delete-user-confirm-input');
  if(!confirmInput||confirmInput.value!==usernameToDelete){setAlert('delete-user-alert','Tapez le nom d\'utilisateur exact pour confirmer.','err');return;}
  const d=await(await fetch(`/admin/delete-user/${usernameToDelete}`,{method:'DELETE'})).json();
  if(d.status==='ok'){setAlert('user-alert','✅ '+d.message,'ok');closeModal('delete-user');loadUsers();loadCompanies();}else{setAlert('user-alert','❌ '+(d.message||d.error),'err');closeModal('delete-user');}usernameToDelete=null;
}
async function populateUserFilters(){
  const users=await(await fetch('/admin/users')).json();
  ['rules-user-filter','insights-user-filter'].forEach(id=>{const sel=document.getElementById(id);if(sel.options.length<=1) users.forEach(u=>{const o=document.createElement('option');o.value=u.username;o.textContent=u.username;sel.appendChild(o);});});
}
async function loadRules(){
  document.getElementById('rules-tbody').innerHTML='<tr class="loading-row"><td colspan="7"><span class="loader"></span> Chargement...</td></tr>';
  const user=document.getElementById('rules-user-filter').value;allRules=await(await fetch(user?`/admin/rules?user=${user}`:'/admin/rules')).json();filterRulesDisplay();
}
function filterRulesDisplay(){
  const cat=document.getElementById('rules-cat-filter').value;const active=document.getElementById('rules-active-filter').value;
  let f=allRules;if(cat) f=f.filter(r=>r.category===cat);if(active==='true') f=f.filter(r=>r.active);if(active==='false') f=f.filter(r=>!r.active);
  document.getElementById('rules-count').textContent=`${f.length} règle(s)`;
  document.getElementById('rules-tbody').innerHTML=f.length?f.map(r=>`<tr><td class="mono" style="color:var(--text3);font-size:11px">${r.id}</td><td class="mono" style="font-size:12px">${r.username||'—'}</td><td><span class="badge badge-gray" style="font-size:9px">${r.category}</span></td><td style="max-width:400px;font-size:12px;color:var(--text2)">${r.rule}</td><td class="mono" style="font-size:11px">${((r.confidence||0)*100).toFixed(0)}%</td><td class="mono" style="font-size:11px">${r.reinforcements||1}</td><td><span class="badge ${r.active?'badge-green':'badge-red'}">${r.active?'active':'inactive'}</span></td></tr>`).join(''):'<tr class="loading-row"><td colspan="7" style="color:var(--text3)">Aucune règle.</td></tr>';
}
async function loadInsights(){
  document.getElementById('insights-tbody').innerHTML='<tr class="loading-row"><td colspan="4"><span class="loader"></span> Chargement...</td></tr>';
  const user=document.getElementById('insights-user-filter').value;allInsights=await(await fetch(user?`/admin/insights?user=${user}`:'/admin/insights')).json();
  document.getElementById('insights-count').textContent=`${allInsights.length} insight(s)`;
  document.getElementById('insights-tbody').innerHTML=allInsights.length?allInsights.map(i=>`<tr><td class="mono" style="font-size:12px">${i.username||'—'}</td><td><span class="badge badge-blue" style="font-size:10px">${i.topic}</span></td><td style="font-size:12px;color:var(--text2);max-width:500px">${i.insight}</td><td class="mono" style="font-size:11px">${i.reinforcements}</td></tr>`).join(''):'<tr class="loading-row"><td colspan="4" style="color:var(--text3)">Aucun insight.</td></tr>';
}
async function quickAction(url,id){
  const el=document.getElementById(id);el.className='action-result';el.textContent='En cours...';
  try{const d=await(await fetch(url)).json();el.textContent=JSON.stringify(d).replace(/[{}"]/g,' ').trim().substring(0,120);}
  catch(e){el.textContent='Erreur: '+e.message;el.className='action-result err';}
}
async function loadProfile(){
  try{const d=await(await fetch('/profile')).json();document.getElementById('profile-username').textContent=d.username||'—';document.getElementById('profile-email').value=d.email||'';}catch(e){}
}
async function initUserScope(){
  try{
    const d=await(await fetch('/profile')).json();
    currentUserScope=d.scope||'';currentUserTenantId=d.tenant_id||'';isSuperAdmin=(isAdminOrSuper());
    // Mode "Ma société" : ?view=company force la vue tenant_admin même pour le super admin
    const companyView=new URLSearchParams(window.location.search).get('view')==='company';
    if(companyView) isSuperAdmin=false;
    if(isSuperAdmin) document.getElementById('btn-create-tenant').style.display='';
    if(isSuperAdmin) { const b=document.getElementById('btn-create-user-companies'); if(b) b.style.display=''; }
    // Vue société (tenant admin OU super admin en mode company) : masquer les onglets super-admin
    if(!isSuperAdmin){
      const tabs=document.querySelectorAll('.nav-tabs .tab');
      const hiddenTabs=['memory','users','rules','insights','actions'];
      tabs.forEach(t=>{const name=t.getAttribute('onclick')||'';hiddenTabs.forEach(h=>{if(name.includes("'"+h+"'"))t.style.display='none';});});
      switchTab('companies');
    } else {
      // Super admin : masquer l'onglet Utilisateurs (doublon de Sociétés)
      const tabs=document.querySelectorAll('.nav-tabs .tab');
      tabs.forEach(t=>{if((t.getAttribute('onclick')||'').includes("'users'"))t.style.display='none';});
    }
  }catch(e){}
}
async function saveEmail(){
  const email=document.getElementById('profile-email').value.trim();const d=await(await fetch('/profile/email',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({email})})).json();
  if(d.status==='ok') setAlert('profile-alert','✅ Email mis à jour.','ok');else setAlert('profile-alert','❌ '+(d.message||d.error),'err');setTimeout(()=>{document.getElementById('profile-alert').className='alert';},4000);
}
async function changePassword(){
  const current=document.getElementById('current-password').value;const newPwd=document.getElementById('new-password').value;const confirm=document.getElementById('confirm-password').value;
  if(!current||!newPwd||!confirm){setAlert('password-alert','Tous les champs sont requis.','err');return;}
  if(newPwd!==confirm){setAlert('password-alert','Les nouveaux mots de passe ne correspondent pas.','err');return;}
  const d=await(await fetch('/profile/password',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({current_password:current,new_password:newPwd})})).json();
  if(d.status==='ok'){setAlert('password-alert','✅ Mot de passe mis à jour avec succès.','ok');['current-password','new-password','confirm-password'].forEach(id=>document.getElementById(id).value='');}else{setAlert('password-alert','❌ '+(d.message||d.error),'err');}
  setTimeout(()=>{document.getElementById('password-alert').className='alert';},5000);
}

document.addEventListener('keydown',e=>{ if(e.key==='Escape') document.querySelectorAll('.modal-overlay.open').forEach(m=>m.classList.remove('open')); });
document.querySelectorAll('.modal-overlay').forEach(o=>o.addEventListener('click',e=>{ if(e.target===o) o.classList.remove('open'); }));

async function scanDriveStart(btn, forceRescan){
  forceRescan = !!forceRescan;
  const mode = forceRescan ? 'RESCAN COMPLET' : 'scan incremental';
  const msg = forceRescan
    ? 'Cette opération RETRAITE TOUS LES FICHIERS, y compris ceux déjà OK.\n\n' +
      'Durée : 2-3h pour 3491 fichiers.\n' +
      'Coût OpenAI : ~0.40€ (re-embeddings complets).\n\n' +
      'A utiliser uniquement après correction majeure de la logique.\n' +
      'Sinon préfère le scan incrémental (très rapide après 1er passage).\n\n' +
      'Lancer le RESCAN COMPLET ?'
    : 'Cette opération va :\n' +
      '• Parcourir récursivement le dossier Photovoltaique\n' +
      '• Skip les fichiers déjà à jour en DB (gain énorme)\n' +
      '• Retraiter les nouveaux / modifiés / en erreur précédente\n' +
      '• Tourne sur Railway : tu peux fermer le navigateur\n\n' +
      'Lancer le scan incrémental ?';
  const ok = await confirmAction(
    forceRescan ? '♻️ Rescan COMPLET du Drive ?' : '🚀 Lancer le scan Drive incrémental ?',
    msg,
    forceRescan ? 'Oui, rescan complet' : 'Oui, lancer',
    'Annuler'
  );
  if(!ok) return;
  const orig = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '⏳ Démarrage...';
  try{
    const url = '/admin/drive/scan-start' + (forceRescan ? '?force_rescan=true' : '');
    const r = await fetch(url, {method: 'POST'});
    const d = await r.json();
    if(d.status === 'already_running'){
      setAlert('companies-alert',
        '⚠️ Un scan Drive est deja en cours. Attends qu il se termine.',
        'warn');
      return;
    }
    if(d.status !== 'started') throw new Error(d.message || 'Démarrage échoué');
    setAlert('companies-alert',
      `🚀 ${mode} lance sur Railway. Tu peux fermer le navigateur. ` +
      'Verifie la progression via 🚀 Drive > 📊 Etat du dernier scan.',
      'ok');
  }catch(e){
    setAlert('companies-alert', '❌ Scan Drive echoue : '+e.message, 'err');
  }finally{
    btn.disabled = false;
    btn.innerHTML = orig;
  }
}

async function scanDriveStatus(btn){
  const orig = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '⏳ Chargement...';
  try{
    const r = await fetch('/admin/drive/scan-status');
    const d = await r.json();
    if(d.status !== 'ok') throw new Error(d.message || 'Erreur');

    const fmt = n => (n === null || n === undefined) ? '-' : n.toLocaleString('fr-FR');
    const folders = (d.folders || []);

    // Agrégats pour les cartes métriques
    const sum = (key) => folders.reduce((a, f) => a + ((f.stats||{})[key]||0), 0);
    const totalFiles = sum("total_files");
    const totalOk = sum("ok");
    const totalSkip = sum("skipped");
    const totalErr = sum("errors");
    const totalN1 = sum("level1_chunks");
    const totalN2 = sum("level2_chunks");
    const errRate = totalFiles ? (totalErr / totalFiles * 100) : 0;

    // Badge état pour chaque ligne du tableau
    const stateBadge = st => ({
      done: '<span style="background:#10b98120;color:#10b981;padding:3px 10px;border-radius:10px;font-size:11px;font-weight:700">✅ TERMINÉ</span>',
      running: '<span style="background:#f59e0b20;color:#f59e0b;padding:3px 10px;border-radius:10px;font-size:11px;font-weight:700">⏳ EN COURS</span>',
      partial: '<span style="background:#ea580c20;color:#ea580c;padding:3px 10px;border-radius:10px;font-size:11px;font-weight:700">🟠 INTERROMPU</span>',
      never:   '<span style="background:#64748b20;color:#64748b;padding:3px 10px;border-radius:10px;font-size:11px;font-weight:700">⚪ JAMAIS</span>',
    })[st] || '';

    const rows = folders.map(f => {
      const s = f.stats || {};
      const lastScan = f.last_full_scan_at
        ? new Date(f.last_full_scan_at).toLocaleString('fr-FR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})
        : '<span style="color:var(--text3)">Jamais</span>';
      const rowBg = f.state === 'done' ? 'rgba(16,185,129,0.05)'
                  : f.state === 'running' ? 'rgba(245,158,11,0.05)'
                  : f.state === 'partial' ? 'rgba(234,88,12,0.05)' : '';
      return `<tr style="border-bottom:1px solid var(--border);background:${rowBg}">
        <td style="padding:8px;font-weight:600">${f.folder_name}</td>
        <td style="padding:8px;font-size:11px;color:var(--text3)">${f.folder_path || ''}</td>
        <td style="padding:8px;text-align:center">${stateBadge(f.state)}</td>
        <td style="padding:8px;text-align:right">${fmt(s.total_files || 0)}</td>
        <td style="padding:8px;text-align:right;color:#10b981">${fmt(s.ok || 0)}</td>
        <td style="padding:8px;text-align:right;color:#f59e0b">${fmt(s.skipped || 0)}</td>
        <td style="padding:8px;text-align:right;color:${s.errors?'#dc2626':'var(--text3)'}">${fmt(s.errors || 0)}</td>
        <td style="padding:8px;text-align:right;color:#0ea5e9">${fmt(s.level1_chunks || 0)}</td>
        <td style="padding:8px;text-align:right;color:#8b5cf6">${fmt(s.level2_chunks || 0)}</td>
        <td style="padding:8px;text-align:center;font-weight:700">${f.progress_pct}%</td>
        <td style="padding:8px;font-size:10px;color:var(--text3)">${lastScan}</td>
      </tr>`;
    }).join('') || '<tr><td colspan="11" style="padding:14px;text-align:center;color:var(--text3)">Aucun dossier surveille. Lance un scan pour commencer.</td></tr>';

    const backdrop = document.createElement('div');
    backdrop.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.85);z-index:9998;display:flex;align-items:center;justify-content:center';
    const modal = document.createElement('div');
    modal.style.cssText = 'background:#0b1220;border:1px solid var(--border);border-radius:12px;padding:18px 22px;width:95vw;max-width:1200px;max-height:90vh;overflow:auto;box-shadow:0 10px 40px rgba(0,0,0,0.8)';
    modal.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
        <h3 style="margin:0">🚀 État des scans Drive SharePoint</h3>
        <button id="drive-close" style="background:#ef4444;color:white;border:none;border-radius:6px;padding:6px 14px;cursor:pointer;font-weight:700">✕ Fermer</button>
      </div>
      ${renderVerdictBanner(d.verdict)}
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:14px">
        ${renderMetricCard('📦','Fichiers total',fmt(totalFiles),'#64748b',
          'Nombre total de fichiers detectes dans le(s) dossier(s) surveille(s).')}
        ${renderMetricCard('✅','Vectorises',fmt(totalOk),'#10b981',
          'Fichiers extraits et vectorises avec succes (PDF, DOCX, XLSX, images). Chacun a 1 ligne N1 meta + N chunks N2 detail.')}
        ${renderMetricCard('⏭️','Ignores',fmt(totalSkip),'#f59e0b',
          'Fichiers volontairement ignores : soit > 50 Mo, soit format non supporte (videos, archives, exe).')}
        ${renderMetricCard('❌','Erreurs',fmt(totalErr),totalErr?'#dc2626':'#64748b',
          'Fichiers qui ont echoue au download ou a l extraction. Au prochain scan incremental, ils seront re-tentes automatiquement.')}
        ${renderMetricCard('🧠','N1 meta',fmt(totalN1),'#0ea5e9',
          'Nombre de resumes meta stockes (1 par fichier OK). Permet a Raya de savoir que le fichier existe.')}
        ${renderMetricCard('🔎','N2 detail',fmt(totalN2),'#8b5cf6',
          'Nombre de chunks detailles vectorises. Permet la recherche semantique precise dans le contenu.')}
      </div>
      <div style="overflow-x:auto;border:1px solid var(--border);border-radius:8px">
        <table style="width:100%;border-collapse:collapse">
          <thead style="background:var(--bg2)">
            <tr style="border-bottom:2px solid var(--border)">
              <th style="padding:10px;text-align:left;font-size:11px">Dossier</th>
              <th style="padding:10px;text-align:left;font-size:11px">Chemin</th>
              <th style="padding:10px;text-align:center;font-size:11px">État</th>
              <th style="padding:10px;text-align:right;font-size:11px">Total</th>
              <th style="padding:10px;text-align:right;font-size:11px">✅ OK</th>
              <th style="padding:10px;text-align:right;font-size:11px">⏭️ Skip</th>
              <th style="padding:10px;text-align:right;font-size:11px">❌ Err</th>
              <th style="padding:10px;text-align:right;font-size:11px">N1</th>
              <th style="padding:10px;text-align:right;font-size:11px">N2</th>
              <th style="padding:10px;text-align:center;font-size:11px">%</th>
              <th style="padding:10px;text-align:left;font-size:11px">Dernier scan</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
      <div style="margin-top:10px;font-size:11px;color:var(--text3)">
        Taux d erreur global : <strong style="color:${errRate>20?'#dc2626':errRate>5?'#f59e0b':'#10b981'}">${errRate.toFixed(1)}%</strong> · N1 meta = Raya sait que le fichier existe · N2 detail = recherche semantique precise · Re-cliquer sur 📊 pour rafraichir
      </div>`;
    backdrop.appendChild(modal);
    document.body.appendChild(backdrop);
    const close = () => backdrop.remove();
    backdrop.addEventListener('click', e => { if(e.target === backdrop) close(); });
    document.getElementById('drive-close').onclick = close;
  }catch(e){
    setAlert('companies-alert', '❌ Status Drive echoue : '+e.message, 'err');
  }finally{
    btn.disabled = false;
    btn.innerHTML = orig;
  }
}

loadMemoryStatus().catch(e=>console.warn('[Admin] loadMemoryStatus failed:',e));
initUserScope().catch(e=>console.warn('[Admin] initUserScope failed:',e));

// ============================================================================
// 🔎 AUDIT — modale d audit des connexions + Drive scanne (20/04/2026 soir)
// ============================================================================
async function showAudit(btn){
  const orig = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '⏳ Chargement...';
  try{
    const r = await fetch('/admin/audit/connections-and-drive?tenant_id=couffrant_solar');
    const d = await r.json();
    if(d.status !== 'ok') throw new Error(d.message || 'Erreur audit');

    const fmt = n => (n === null || n === undefined) ? '-' : n.toLocaleString('fr-FR');
    const escapeAttr = s => String(s||'').replace(/"/g, '&quot;');
    const toolIcon = t => ({
      microsoft: '🟦', outlook: '📧', onedrive: '☁️', sharepoint: '🗂️',
      google: '🔴', gmail: '✉️', gdrive: '📁',
      odoo: '🟪', openfire: '🔥'
    })[t] || '🔌';

    // --- SECTION 1 : Connexions
    const connRows = (d.connections || []).map(c => {
      const status = c.status === 'connected'
        ? '<span style="color:#10b981">✅ connected</span>'
        : `<span style="color:#f59e0b">⚠️ ${c.status}</span>`;
      return `<tr style="border-bottom:1px solid var(--border)">
        <td style="padding:8px;font-size:11px;color:var(--text3)">#${c.id}</td>
        <td style="padding:8px;font-weight:600">${toolIcon(c.tool_type)} ${c.tool_type}</td>
        <td style="padding:8px">${c.label || '<span style="color:var(--text3)">-</span>'}</td>
        <td style="padding:8px;font-family:monospace;font-size:11px">${c.connected_email || '<span style="color:var(--text3)">-</span>'}</td>
        <td style="padding:8px;font-size:11px">${c.auth_type}</td>
        <td style="padding:8px;font-size:11px">${status}</td>
        <td style="padding:8px;font-size:10px;color:var(--text3)">${(c.created_at||'').substring(0,16)}</td>
      </tr>`;
    }).join('') || '<tr><td colspan="7" style="padding:14px;text-align:center;color:var(--text3)">Aucune connexion.</td></tr>';

    // Alertes doublons
    const dups = d.duplicates || [];
    const dupBlock = dups.length
      ? `<div style="background:#7f1d1d;border:2px solid #dc2626;border-radius:8px;padding:12px;margin-bottom:10px;color:#fecaca">
           <div style="font-weight:700;margin-bottom:6px">🔴 ${dups.length} doublon(s) detecte(s) (meme tool + meme email)</div>
           ${dups.map(x => `<div style="font-size:11px;margin:3px 0">• <code>${x.tool_type}</code> / <code>${x.email}</code> : ${x.count} connexions (IDs ${x.connection_ids.join(', ')}) — labels : ${x.labels.map(l=>`"${l}"`).join(', ')}</div>`).join('')}
           <div style="font-size:10px;margin-top:6px;opacity:0.8">💡 Suggestion : garder la plus recente/active, supprimer les autres dans Connecteurs V2.</div>
         </div>`
      : `<div style="background:#065f46;border:1px solid #10b981;border-radius:8px;padding:10px;margin-bottom:10px;color:#d1fae5;font-size:11px">🟢 Aucun doublon strict detecte (meme tool_type + meme email).</div>`;

    // Alertes cross-tool (meme email, tools differents) - informationnel
    const crosses = d.cross_tool_emails || [];
    const crossBlock = crosses.length
      ? `<div style="background:#78350f;border:1px solid #f59e0b;border-radius:8px;padding:10px;margin-bottom:10px;color:#fef3c7">
           <div style="font-weight:700;margin-bottom:6px;font-size:12px">🟡 ${crosses.length} email(s) utilise(s) sur plusieurs outils — a verifier visuellement</div>
           ${crosses.map(x => `<div style="font-size:11px;margin:2px 0">• <code>${x.email}</code> utilise sur : ${x.tool_types.map(t=>`<span style="background:rgba(255,255,255,0.1);padding:1px 6px;border-radius:4px;margin:0 2px">${toolIcon(t)} ${t}</span>`).join(' ')}</div>`).join('')}
           <div style="font-size:10px;margin-top:6px;opacity:0.8">💡 Si un meme email a plusieurs tool_type, c est souvent legitime (ex: Outlook + OneDrive + SharePoint = 1 seul compte Microsoft). A verifier visuellement.</div>
         </div>`
      : '';

    // Tokens gmail legacy
    const gmTokens = d.gmail_tokens_legacy || [];
    const gmBlock = gmTokens.length
      ? `<div style="background:#78350f;border:1px dashed #f59e0b;border-radius:8px;padding:10px;margin-bottom:10px;color:#fef3c7;font-size:11px">
           <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
             <div style="font-weight:700">📦 ${gmTokens.length} token(s) gmail_tokens (ancienne architecture)</div>
             <button id="audit-purge-gmail-btn" style="background:#f59e0b;color:#1e293b;padding:4px 10px;border:none;border-radius:6px;cursor:pointer;font-weight:600;font-size:11px" title="Supprime les tokens gmail_tokens legacy pour le user guillaume. Sans risque si une connexion gmail existe deja dans tenant_connections.">🧹 Purger les tokens legacy</button>
           </div>
           ${gmTokens.map(t => `<div style="margin:2px 0">• user <code>${t.username}</code> — email <code>${t.email}</code> — maj ${(t.updated_at||'').substring(0,16)}</div>`).join('')}
           <div style="font-size:10px;margin-top:4px;opacity:0.8">💡 Ces entrees viennent d une ancienne architecture. Si le user utilise deja tenant_connections, ces tokens sont potentiellement obsoletes.</div>
         </div>`
      : '';

    // --- SECTION 2 : Arborescence Drive scannee (niveau 1 + 2)
    const totals = d.drive_totals || {};
    const tree = d.drive_tree || [];
    const treeBlock = tree.length
      ? tree.map(lvl1 => {
          const subs = (lvl1.subfolders_level2 || []).map(sn => {
            const exts = Object.entries(sn.extensions || {}).sort((a,b)=>b[1]-a[1]).slice(0,5)
              .map(([e,c]) => `<code style="font-size:10px">${e}:${c}</code>`).join(' ');
            return `<tr style="border-bottom:1px solid var(--border)">
              <td style="padding:6px 10px;padding-left:28px;font-size:11px">└ ${sn.name}</td>
              <td style="padding:6px 10px;text-align:right;font-size:11px">${fmt(sn.file_count)}</td>
              <td style="padding:6px 10px;text-align:right;font-size:11px">${fmt(sn.total_size_mb)} Mo</td>
              <td style="padding:6px 10px;font-size:10px;color:var(--text3)">${exts || '-'}</td>
            </tr>`;
          }).join('');
          const exts1 = Object.entries(lvl1.extensions || {}).sort((a,b)=>b[1]-a[1]).slice(0,5)
            .map(([e,c]) => `<code style="font-size:10px">${e}:${c}</code>`).join(' ');
          return `<tr style="border-bottom:2px solid var(--border);background:rgba(139,92,246,0.05)">
            <td style="padding:8px 10px;font-weight:700;font-size:12px">📂 ${lvl1.level1_name}</td>
            <td style="padding:8px 10px;text-align:right;font-weight:700">${fmt(lvl1.file_count)}</td>
            <td style="padding:8px 10px;text-align:right;font-weight:700">${fmt(lvl1.total_size_mb)} Mo</td>
            <td style="padding:8px 10px;font-size:10px;color:var(--text3)">${exts1}</td>
          </tr>${subs}`;
        }).join('')
      : '<tr><td colspan="4" style="padding:14px;text-align:center;color:var(--text3)">Aucun fichier Drive scanne.</td></tr>';

    const driveFoldersInfo = (d.drive_folders || []).map(f =>
      `<div style="font-size:11px;margin:2px 0">📂 <strong>${f.folder_name}</strong> — chemin Drive : <code>${f.folder_path||'?'}</code> ${f.enabled?'<span style="color:#10b981">(actif)</span>':'<span style="color:#6b7280">(desactive)</span>'}</div>`
    ).join('') || '<div style="color:var(--text3);font-size:11px">Aucun dossier configure.</div>';

    // --- Construction de la modale
    const backdrop = document.createElement('div');
    backdrop.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.85);z-index:9998;display:flex;align-items:center;justify-content:center';
    const modal = document.createElement('div');
    modal.style.cssText = 'background:#0b1220;border:1px solid var(--border);border-radius:12px;padding:18px 22px;width:95vw;max-width:1200px;max-height:92vh;overflow:auto;box-shadow:0 10px 40px rgba(0,0,0,0.8)';

    const connectionsSection = `
      <h4 style="margin:0 0 10px 0;color:#a78bfa">🔌 Connexions du tenant (${d.connections.length})</h4>
      ${dupBlock}
      ${crossBlock}
      ${gmBlock}
      <div style="overflow-x:auto;border:1px solid var(--border);border-radius:8px;margin-bottom:18px">
        <table style="width:100%;border-collapse:collapse;font-size:12px">
          <thead style="background:var(--bg2)">
            <tr style="border-bottom:2px solid var(--border)">
              <th style="padding:10px;text-align:left;font-size:10px;color:var(--text3)">ID</th>
              <th style="padding:10px;text-align:left;font-size:10px;color:var(--text3)">TYPE</th>
              <th style="padding:10px;text-align:left;font-size:10px;color:var(--text3)">LABEL</th>
              <th style="padding:10px;text-align:left;font-size:10px;color:var(--text3)">EMAIL CONNECTÉ</th>
              <th style="padding:10px;text-align:left;font-size:10px;color:var(--text3)">AUTH</th>
              <th style="padding:10px;text-align:left;font-size:10px;color:var(--text3)">STATUS</th>
              <th style="padding:10px;text-align:left;font-size:10px;color:var(--text3)">CRÉÉ LE</th>
            </tr>
          </thead>
          <tbody>${connRows}</tbody>
        </table>
      </div>
    `;

    const driveSection = `
      <h4 style="margin:18px 0 10px 0;color:#a78bfa">🚀 Drive SharePoint — arborescence scannée (niveaux 1 & 2)</h4>
      <div style="background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:10px;margin-bottom:10px">
        <div style="font-size:11px;color:var(--text3);margin-bottom:4px">📦 Total : <strong style="color:#10b981">${fmt(totals.distinct_files)}</strong> fichiers distincts vectorisés · ${fmt(totals.total_size_mb)} Mo · ${totals.level1_folders_count} dossier(s) racine(s)</div>
        <div style="font-size:11px;color:var(--text3);margin-bottom:6px">Dossiers configurés :</div>
        ${driveFoldersInfo}
      </div>
      <div style="overflow-x:auto;border:1px solid var(--border);border-radius:8px">
        <table style="width:100%;border-collapse:collapse;font-size:12px">
          <thead style="background:var(--bg2)">
            <tr style="border-bottom:2px solid var(--border)">
              <th style="padding:10px;text-align:left;font-size:10px;color:var(--text3)">DOSSIER</th>
              <th style="padding:10px;text-align:right;font-size:10px;color:var(--text3)">FICHIERS</th>
              <th style="padding:10px;text-align:right;font-size:10px;color:var(--text3)">TAILLE</th>
              <th style="padding:10px;text-align:left;font-size:10px;color:var(--text3)">TOP EXTENSIONS</th>
            </tr>
          </thead>
          <tbody>${treeBlock}</tbody>
        </table>
      </div>
      <div style="margin-top:10px;font-size:11px;color:var(--text3)">💡 Les lignes en violet sont les dossiers racine. Les lignes indentées (└) sont les sous-dossiers niveau 2. Les extensions montrent le top 5 par nombre de fichiers.</div>
    `;

    modal.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
        <div>
          <h3 style="margin:0">🔎 Audit des connexions et du Drive scanné</h3>
          <div style="font-size:12px;color:var(--text3);margin-top:2px">Tenant : <code>${d.tenant_id}</code> · Lecture pure, aucune modification effectuée</div>
        </div>
        <button id="audit-close" style="background:#ef4444;color:white;border:none;border-radius:6px;padding:6px 14px;cursor:pointer;font-weight:700">✕ Fermer</button>
      </div>
      ${connectionsSection}
      ${driveSection}
    `;
    backdrop.appendChild(modal);
    document.body.appendChild(backdrop);
    const close = () => backdrop.remove();
    backdrop.addEventListener('click', e => { if(e.target === backdrop) close(); });
    document.getElementById('audit-close').onclick = close;
    const purgeBtn = document.getElementById('audit-purge-gmail-btn');
    if(purgeBtn){
      purgeBtn.onclick = async () => {
        const ok = await confirmAction(
          '🧹 Purger les tokens gmail_tokens legacy ?',
          'Cette operation supprime les entrees obsoletes de l ancienne archi.\n\n' +
          'Sans risque : ta connexion Gmail actuelle (tenant_connections #4) reste intacte.',
          'Oui, purger', 'Annuler'
        );
        if(!ok) return;
        purgeBtn.disabled = true;
        purgeBtn.innerHTML = '⏳...';
        try{
          const res = await fetch('/admin/audit/purge-gmail-legacy?username=guillaume', {method:'POST'});
          const pd = await res.json();
          if(pd.status !== 'ok') throw new Error(pd.message || 'Echec');
          setAlert('companies-alert', '🧹 '+pd.message+' Re-clique sur 🔎 Audit pour rafraichir.', 'ok');
          close();
        }catch(e){
          setAlert('companies-alert', '❌ Purge echouee : '+e.message, 'err');
          purgeBtn.disabled = false;
          purgeBtn.innerHTML = '🧹 Purger';
        }
      };
    }
  }catch(e){
    setAlert('companies-alert', '❌ Audit echoue : '+e.message, 'err');
  }finally{
    btn.disabled = false;
    btn.innerHTML = orig;
  }
}
// Fin 🔎 AUDIT
// ============================================================================


// Tooltip [?] explicatif inline. Le texte apparait au survol.
// Params : tooltipText = le texte francais a afficher au hover
function renderHelpTooltip(tooltipText){
  const safe = String(tooltipText).replace(/"/g, '&quot;');
  return `<span style="display:inline-block;width:14px;height:14px;
    border-radius:50%;background:var(--bg2);border:1px solid var(--border);
    text-align:center;font-size:9px;line-height:13px;color:var(--text3);
    cursor:help;margin-left:4px" title="${safe}">?</span>`;
}

// Accordeon generique. Titre cliquable, contenu replie par defaut.
// Params : title (avec icone), contentHtml, openByDefault (bool)
function renderAccordion(title, contentHtml, openByDefault){
  return `<details ${openByDefault?'open':''} style="margin:10px 0;
    border:1px solid var(--border);border-radius:8px;background:var(--bg2)">
    <summary style="padding:10px 14px;cursor:pointer;font-weight:600;
      font-size:12px;color:var(--text2);user-select:none">${title}</summary>
    <div style="padding:10px 14px;border-top:1px solid var(--border)">
      ${contentHtml}
    </div>
  </details>`;
}

// Metrique compacte avec tooltip. Pour les cartes de chiffres.
// Params : icon, label, value, color, tooltipText
function renderMetricCard(icon, label, value, color, tooltipText){
  const tt = tooltipText ? renderHelpTooltip(tooltipText) : '';
  return `<div style="background:var(--bg2);border:1px solid ${color};
    padding:10px;border-radius:8px">
    <div style="font-size:10px;color:var(--text3);text-transform:uppercase">
      ${icon} ${label}${tt}
    </div>
    <div style="font-size:20px;font-weight:700;color:${color}">${value}</div>
  </div>`;
}

// Fin des helpers dashboards
// ============================================================================


// ============================================================================
// GRAPHE SÉMANTIQUE DRIVE (commit 2/5 étape A - 21/04/2026)
// ============================================================================
//
// 2 fonctions qui exposent dans l UI les endpoints admin :
//   - driveGraphStats : GET /admin/drive/graph-stats -> affiche couverture
//   - driveGraphMigrate : POST /admin/drive/migrate-to-graph -> lance migration
//
// Idempotent cote serveur : relancable sans risque de duplication.
// ============================================================================

async function driveGraphStats(btn){
  const orig = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '⏳ Chargement...';
  try{
    const r = await fetch('/admin/drive/graph-stats');
    const d = await r.json();
    if(d.status !== 'ok') throw new Error(d.message || 'Erreur');

    const fmt = n => (n === null || n === undefined) ? '-' : n.toLocaleString('fr-FR');
    const nodesRows = Object.entries(d.nodes || {}).map(([type, count]) =>
      `<tr><td style="padding:6px 10px;font-weight:600">${type}</td>
           <td style="padding:6px 10px;text-align:right">${fmt(count)}</td></tr>`
    ).join('') || '<tr><td colspan="2" style="padding:10px;color:var(--text3);text-align:center">Aucun nœud Drive dans le graphe pour l instant. Lance la migration pour rattraper les fichiers deja vectorises.</td></tr>';

    const edgesRows = Object.entries(d.edges || {}).map(([type, count]) =>
      `<tr><td style="padding:6px 10px;font-weight:600">${type}</td>
           <td style="padding:6px 10px;text-align:right">${fmt(count)}</td></tr>`
    ).join('') || '<tr><td colspan="2" style="padding:10px;color:var(--text3);text-align:center">Aucune arete.</td></tr>';

    const cov = d.coverage_pct || 0;
    const covColor = cov >= 95 ? '#10b981' : cov >= 50 ? '#f59e0b' : '#dc2626';
    const covLabel = cov >= 95 ? 'COMPLET' : cov >= 50 ? 'PARTIEL' : 'A RATTRAPER';

    const backdrop = document.createElement('div');
    backdrop.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.85);z-index:9998;display:flex;align-items:center;justify-content:center';
    const modal = document.createElement('div');
    modal.style.cssText = 'background:#0b1220;border:1px solid var(--border);border-radius:12px;padding:18px 22px;width:90vw;max-width:700px;max-height:85vh;overflow:auto;box-shadow:0 10px 40px rgba(0,0,0,0.8)';
    modal.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
        <h3 style="margin:0">🌐 État du graphe sémantique Drive</h3>
        <button id="gstats-close" style="background:#ef4444;color:white;border:none;border-radius:6px;padding:6px 14px;cursor:pointer;font-weight:700">✕ Fermer</button>
      </div>
      <div style="background:${covColor}15;border:2px solid ${covColor};border-radius:10px;padding:14px;margin-bottom:14px;text-align:center">
        <div style="font-size:36px;font-weight:800;color:${covColor}">${cov}%</div>
        <div style="font-size:12px;color:${covColor};font-weight:700;margin-top:3px">COUVERTURE ${covLabel}</div>
        <div style="font-size:11px;color:var(--text3);margin-top:6px">
          ${fmt(d.file_nodes_in_graph)} nœud(s) File dans le graphe / ${fmt(d.total_files_vectorized)} fichier(s) vectorisé(s)
        </div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">
        <div>
          <h4 style="margin:0 0 8px 0;font-size:13px">🔵 Nœuds Drive</h4>
          <table style="width:100%;border-collapse:collapse;background:var(--bg1);border-radius:6px;overflow:hidden">
            <thead><tr style="background:var(--bg2)"><th style="padding:8px;text-align:left">Type</th><th style="padding:8px;text-align:right">Nombre</th></tr></thead>
            <tbody>${nodesRows}</tbody>
          </table>
        </div>
        <div>
          <h4 style="margin:0 0 8px 0;font-size:13px">🔗 Arêtes (edges)</h4>
          <table style="width:100%;border-collapse:collapse;background:var(--bg1);border-radius:6px;overflow:hidden">
            <thead><tr style="background:var(--bg2)"><th style="padding:8px;text-align:left">Type</th><th style="padding:8px;text-align:right">Nombre</th></tr></thead>
            <tbody>${edgesRows}</tbody>
          </table>
        </div>
      </div>
      ${cov < 95 ? `<div style="margin-top:14px;padding:10px;background:#f59e0b10;border-left:3px solid #f59e0b;border-radius:6px;font-size:12px">
        💡 <strong>Couverture incomplète.</strong> Utilise le bouton <em>⚡ Migrer Drive vers graphe</em> pour rattraper les fichiers vectorisés avant le commit 2/5. C est idempotent, relançable sans risque.
      </div>` : `<div style="margin-top:14px;padding:10px;background:#10b98110;border-left:3px solid #10b981;border-radius:6px;font-size:12px">
        ✅ <strong>Graphe Drive complet.</strong> Tous les fichiers vectorisés ont leurs nœuds dans le graphe sémantique unifié.
      </div>`}
    `;
    backdrop.appendChild(modal);
    document.body.appendChild(backdrop);
    modal.querySelector('#gstats-close').onclick = () => backdrop.remove();
    backdrop.onclick = e => { if(e.target === backdrop) backdrop.remove(); };
  }catch(err){
    alert('❌ ' + err.message);
  }finally{
    btn.disabled = false;
    btn.innerHTML = orig;
  }
}


async function driveGraphMigrate(btn){
  // Confirmation : la migration peut durer ~1 min sur 3252 fichiers
  if(!confirm('⚡ Lancer la migration Drive vers le graphe sémantique ?\n\n'+
              'Crée les nœuds File + Folder + edges contains pour tous les '+
              'fichiers déjà vectorisés.\n\n'+
              'Durée estimée : ~1 minute pour 3000 fichiers.\n'+
              'Idempotent : relançable sans risque.\n\n'+
              'Astuce : teste d abord avec limit=50 dans l URL directement '+
              'si tu veux valider sur un echantillon.')) return;

  const orig = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '⏳ Migration en cours...';
  try{
    const r = await fetch('/admin/drive/migrate-to-graph', {method:'POST'});
    const d = await r.json();
    if(d.status !== 'ok') throw new Error(d.message || 'Erreur');

    const s = d.stats || {};
    const fmt = n => (n === null || n === undefined) ? '-' : n.toLocaleString('fr-FR');
    const hasErrors = (s.errors || 0) > 0;

    const backdrop = document.createElement('div');
    backdrop.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.85);z-index:9998;display:flex;align-items:center;justify-content:center';
    const modal = document.createElement('div');
    modal.style.cssText = 'background:#0b1220;border:1px solid var(--border);border-radius:12px;padding:18px 22px;width:90vw;max-width:640px;max-height:85vh;overflow:auto;box-shadow:0 10px 40px rgba(0,0,0,0.8)';

    const errorsHtml = hasErrors && s.errors_sample ?
      `<div style="margin-top:12px;padding:10px;background:#dc262610;border-left:3px solid #dc2626;border-radius:6px;font-size:12px">
        <strong>⚠️ ${s.errors} erreur(s) non bloquante(s) :</strong>
        <ul style="margin:6px 0 0 16px;padding:0">
          ${s.errors_sample.map(e => `<li style="margin-bottom:3px;color:var(--text3)">${e}</li>`).join('')}
        </ul>
      </div>` : '';

    modal.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
        <h3 style="margin:0">⚡ Migration Drive → graphe sémantique</h3>
        <button id="gmig-close" style="background:#ef4444;color:white;border:none;border-radius:6px;padding:6px 14px;cursor:pointer;font-weight:700">✕ Fermer</button>
      </div>
      <div style="background:#10b98115;border:2px solid #10b981;border-radius:10px;padding:14px;margin-bottom:14px;text-align:center">
        <div style="font-size:28px;font-weight:800;color:#10b981">✅ Terminé</div>
        <div style="font-size:13px;color:var(--text2);margin-top:6px">
          ${fmt(s.files_processed)} fichier(s) traité(s)
        </div>
      </div>
      <table style="width:100%;border-collapse:collapse;background:var(--bg1);border-radius:6px;overflow:hidden;font-size:13px">
        <tr style="border-bottom:1px solid var(--border)"><td style="padding:8px 12px">Nœuds File créés / mis à jour</td><td style="padding:8px 12px;text-align:right;color:#0ea5e9;font-weight:700">${fmt(s.file_nodes_created)}</td></tr>
        <tr style="border-bottom:1px solid var(--border)"><td style="padding:8px 12px">Nœuds Folder créés / mis à jour</td><td style="padding:8px 12px;text-align:right;color:#8b5cf6;font-weight:700">${fmt(s.folder_nodes_created)}</td></tr>
        <tr style="border-bottom:1px solid var(--border)"><td style="padding:8px 12px">Arêtes contains créées</td><td style="padding:8px 12px;text-align:right;color:#10b981;font-weight:700">${fmt(s.edges_created)}</td></tr>
        <tr><td style="padding:8px 12px">Erreurs (non bloquantes)</td><td style="padding:8px 12px;text-align:right;color:${hasErrors?'#dc2626':'var(--text3)'};font-weight:700">${fmt(s.errors)}</td></tr>
      </table>
      ${errorsHtml}
      <div style="margin-top:14px;padding:10px;background:#0ea5e910;border-left:3px solid #0ea5e9;border-radius:6px;font-size:12px">
        💡 <strong>Prochaines étapes :</strong> utilise <em>🌐 Etat du graphe Drive</em> pour verifier la couverture, puis teste <code>/admin/unified-search/test?q=Legroux&enrich_graph=true</code> pour voir les resultats Drive enrichis par leur hierarchie de dossiers.
      </div>
    `;
    backdrop.appendChild(modal);
    document.body.appendChild(backdrop);
    modal.querySelector('#gmig-close').onclick = () => backdrop.remove();
    backdrop.onclick = e => { if(e.target === backdrop) backdrop.remove(); };
  }catch(err){
    alert('❌ Migration échouée : ' + err.message);
  }finally{
    btn.disabled = false;
    btn.innerHTML = orig;
  }
}
