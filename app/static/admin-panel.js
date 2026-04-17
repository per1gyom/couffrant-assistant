/* Admin Panel — JS */
let allRules=[], allInsights=[];
let currentEditUser=null, usernameToDelete=null;
let isSuperAdmin=false, currentUserScope='', currentUserTenantId='';
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
  if(name==='companies') loadCompanies();
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
    <td><span class="badge ${u.scope==='admin'?'badge-blue':u.scope==='tenant_admin'?'badge-green':'badge-gray'}">${u.scope||'user'}</span></td>
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
      <td><span class="badge ${u.scope==='admin'?'badge-blue':u.scope==='tenant_admin'?'badge-green':'badge-gray'}">${u.scope||'user'}</span></td>
      <td class="mono" style="font-size:11px;color:var(--text2)">${fmtDateShort(u.last_login)}</td>
      <td class="mono" style="font-size:11px;color:var(--text3)">${fmtDate(u.created_at)}</td>
      <td style="display:flex;gap:6px;flex-wrap:wrap">
        <button class="btn btn-ghost" style="padding:4px 9px;font-size:11px" onclick="showTools('${u.username}')">Outils</button>
        <button class="btn btn-accent" style="padding:4px 9px;font-size:11px" onclick="editUser('${u.username}','${u.email||''}','${u.scope||'user'}','${u.phone||''}')">Modifier</button>
        <button class="btn btn-ghost" style="padding:4px 9px;font-size:11px" onclick="seedUser('${u.username}')">🌱</button>
        ${u.suspended?`<button class="btn btn-unlock" style="padding:4px 9px;font-size:11px" onclick="unsuspendUser('${u.username}')">▶️ Réactiver</button>`:`<button class="btn btn-ghost" style="padding:4px 9px;font-size:11px;color:var(--yellow)" onclick="suspendUser('${u.username}')">⏸️</button>`}
        ${u.account_locked?`<button class="btn btn-unlock" style="padding:4px 9px;font-size:11px" onclick="unlockUser('${u.username}')">🔓 Débloquer</button>`:''}
        ${u.scope!=='admin'?`<button class="btn btn-danger" style="padding:4px 9px;font-size:11px" onclick="askDeleteUser('${u.username}')">Suppr.</button>`:''}
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
const toolsApiBase=()=>currentUserScope==='admin'?'/admin':'/tenant';

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
const connApiBase=()=>currentUserScope==='admin'?'/admin':'/tenant';
const TOOL_ICONS={'outlook':'📧','gmail':'✉️','drive':'📁','odoo':'🔧','teams':'💬','whatsapp':'📱','microsoft':'🔵','google':'🟢'};

function showAddConnection(tenantId,idx){document.getElementById('conn-add-'+idx).style.display='block';}

async function loadConnections(tenantId,idx){
  const el=document.getElementById('conn-list-'+idx);
  const summaryEl=document.getElementById('conn-summary-'+idx);
  if(!el) return;
  try{
    const url=currentUserScope==='admin'?`/admin/connections/${tenantId}`:'/tenant/connections';
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
    el.innerHTML=conns.map(c=>{
      const icon=TOOL_ICONS[c.tool_type]||'🔌';
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
          <div style="flex:1;min-width:120px"><strong style="color:var(--text1);font-size:12px;cursor:pointer;border-bottom:1px dashed var(--text3)" onclick="renameConn(${c.id},'${tenantId}',${idx},'${c.label.replace(/'/g,"\\'")}')" title="Cliquer pour renommer">${c.label}</strong><br><span style="font-size:10px;color:var(--text3)">${c.tool_type}</span> ${statusBadge}</div>
          ${oauthBtn}
          ${['odoo'].includes(c.tool_type)?`<button class="btn btn-accent" style="padding:2px 10px;font-size:10px" onclick="discoverTool('${tenantId}','${c.tool_type}',this)">🔍 Découvrir</button>`:''}
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
  const url=currentUserScope==='admin'?`/admin/connections/${tenantId}`:'/tenant/connections';
  try{
    const d=await(await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tool_type:type,label})})).json();
    if(d.status==='ok'){document.getElementById('conn-add-'+idx).style.display='none';document.getElementById('conn-type-'+idx).value='';document.getElementById('conn-label-'+idx).value='';loadConnections(tenantId,idx);}
    else setAlert('companies-alert','❌ '+(d.message||'Erreur'),'err');
  }catch(e){setAlert('companies-alert','❌ '+e.message,'err');}
}

async function discoverTool(tenantId,toolType,btn){
  const orig=btn.innerHTML;
  btn.disabled=true;btn.innerHTML='⏳ Exploration…';
  try{
    const r=await fetch(`/admin/discover/${tenantId}/${toolType}`);
    const d=await r.json();
    if(d.discovered>0){
      btn.innerHTML=`✅ ${d.discovered} modèle(s)`;
      setAlert('companies-alert',`${d.discovered} schéma(s) ${toolType} découvert(s) et vectorisé(s)`,'ok');
    }else{
      btn.innerHTML='❌ Échec';
      setAlert('companies-alert',d.errors?d.errors[0]:'Aucun modèle découvert','err');
    }
  }catch(e){btn.innerHTML='❌ Erreur';setAlert('companies-alert','Erreur réseau','err');}
  setTimeout(()=>{btn.innerHTML=orig;btn.disabled=false;},5000);
}

async function deleteConn(connId,tenantId,idx){
  if(!confirm('Supprimer cette connexion et tous ses accès ?')) return;
  const url=currentUserScope==='admin'?`/admin/connections/${tenantId}/${connId}`:'/tenant/connections/'+connId;
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
  const url=currentUserScope==='admin'?`/admin/connections/${connId}/assign`:'/tenant/connections/'+connId+'/assign';
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
  const url=currentUserScope==='admin'?`/admin/connections/${connId}/assign`:'/tenant/connections/'+connId+'/assign';
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
    const url=currentUserScope==='admin'?`/admin/connections/${connId}/assign/${u.username}`:'/tenant/connections/'+connId+'/assign/'+u.username;
    try{await fetch(url,{method:'DELETE'});}catch(e){}
  }
  await loadConnections(tenantId,idx);
  toggleAssignPanel(connId,tenantId,idx);
}

async function renameConn(connId,tenantId,idx,currentLabel){
  const newLabel=prompt('Nouveau nom de la connexion :',currentLabel);
  if(!newLabel||newLabel===currentLabel) return;
  const url=currentUserScope==='admin'?`/admin/connections/${tenantId}/${connId}`:'/tenant/connections/'+connId;
  try{
    await fetch(url,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({label:newLabel})});
    loadConnections(tenantId,idx);
  }catch(e){setAlert('companies-alert','❌ '+e.message,'err');}
}

async function unassignConn(connId,username,tenantId,idx){
  if(!confirm(`Retirer l'accès de ${username} ?`)) return;
  const url=currentUserScope==='admin'?`/admin/connections/${connId}/assign/${username}`:'/tenant/connections/'+connId+'/assign/'+username;
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
          <div class="tenant-meta"><span>👥 ${t.user_count} collaborateur(s)</span><span>📬 ${fmt(t.total_mails)} mails</span><span>💬 ${fmt(t.total_conv)} conversations</span><span id="conn-summary-${i}" style="display:inline-flex;gap:6px;align-items:center">…</span>${siret?`<span style="color:var(--text3)">SIRET: ${siret}</span>`:''}</div>
        </div>
        <div class="tenant-body" id="body-${i}">
          <table><thead><tr><th>Identifiant</th><th>Email</th><th>Rôle</th><th>MS</th><th>Mails</th><th>Conv.</th><th>Dernière connexion</th><th>Actions</th></tr></thead>
          <tbody>${t.users.map(u=>`<tr class="${u.account_locked||u.suspended?'row-locked':''}">
            <td><strong class="mono">${u.username}</strong>${u.account_locked?'<span class="badge badge-red" style="margin-left:6px;font-size:9px">🔒</span>':''}${u.suspended?'<span class="badge badge-yellow" style="margin-left:6px;font-size:9px">⏸️</span>':''}${u.must_reset_password&&!u.account_locked?'<span class="badge badge-yellow" style="margin-left:6px;font-size:9px">⚠️</span>':''}</td>
            <td style="font-size:12px;color:var(--text2)">${u.email||'—'}</td>
            <td><span class="badge ${u.scope==='admin'?'badge-blue':u.scope==='tenant_admin'?'badge-green':'badge-gray'}">${u.scope}</span></td>
            <td><span class="badge ${u.ms_connected?'badge-ms-ok':'badge-red'}">${u.ms_connected?'✅ OK':'❌ Non'}</span></td>
            <td class="mono">${fmt(u.mails)}</td><td class="mono">${fmt(u.conv)}</td>
            <td class="mono" style="font-size:11px;color:var(--text2)">${fmtDateShort(u.last_login)}</td>
            <td style="display:flex;gap:5px;flex-wrap:wrap">
              <button class="btn btn-ghost" style="padding:4px 9px;font-size:11px" onclick="showToolsCompany('${u.username}')">🔧</button>
              <button class="btn btn-accent" style="padding:4px 9px;font-size:11px" onclick="editUser('${u.username}','${u.email||''}','${u.scope}','${u.phone||''}')">Modifier</button>
              <button class="btn btn-ghost" style="padding:4px 9px;font-size:11px" onclick="seedUser('${u.username}')">🌱</button>
              ${!isSuperAdmin&&u.scope!=='admin'?`<button class="btn ${u.direct_actions_override===true?'btn-accent':u.direct_actions_override===false?'btn-danger':'btn-ghost'}" style="padding:4px 9px;font-size:10px" onclick="cycleUserDirectActions('${u.username}',${u.direct_actions_override===null||u.direct_actions_override===undefined?'null':u.direct_actions_override})" title="Actions directes fichiers">${u.direct_actions_override===true?'📂 ON':u.direct_actions_override===false?'📂 OFF':'📂 ='}</button>`:''}
              ${u.suspended?`<button class="btn btn-unlock" style="padding:4px 9px;font-size:11px" onclick="unsuspendUser('${u.username}')">▶️</button>`:`${u.scope!=='admin'?`<button class="btn btn-ghost" style="padding:4px 9px;font-size:11px;color:var(--yellow)" onclick="suspendUser('${u.username}')">⏸️</button>`:''}`}
              ${u.account_locked?`<button class="btn btn-unlock" style="padding:4px 9px;font-size:11px" onclick="unlockUser('${u.username}')">🔓</button>`:''}
              ${u.scope!=='admin'?`<button class="btn btn-danger" style="padding:4px 9px;font-size:11px" onclick="askDeleteUser('${u.username}')">Suppr.</button>`:''}
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
}usernameToDelete=username;document.getElementById('delete-username-label').textContent=username;document.getElementById('delete-user-confirm-input').value='';document.getElementById('delete-user-confirm-input').placeholder=username;document.getElementById('delete-user-btn').disabled=true;openModal('delete-user');}

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
    currentUserScope=d.scope||'';currentUserTenantId=d.tenant_id||'';isSuperAdmin=(currentUserScope==='admin');
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

loadMemoryStatus().catch(e=>console.warn('[Admin] loadMemoryStatus failed:',e));
initUserScope().catch(e=>console.warn('[Admin] initUserScope failed:',e));
