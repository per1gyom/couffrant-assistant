/* Admin Panel — JS */
let allRules=[], allInsights=[];
let currentEditUser=null, usernameToDelete=null;
let isSuperAdmin=false, currentUserScope='';
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
}

async function loadUsers(){
  document.getElementById('users-tbody').innerHTML='<tr class="loading-row"><td colspan="6"><span class="loader"></span> Chargement...</td></tr>';
  const data=await(await fetch('/admin/users')).json();
  const locked=data.filter(u=>u.account_locked).length;
  const lcEl=document.getElementById('locked-count');
  lcEl.textContent=locked>0?`⚠️ ${locked} compte(s) bloqué(s)`:'';
  lcEl.style.color=locked>0?'var(--red)':'';
  document.getElementById('users-tbody').innerHTML=data.map(u=>`
    <tr class="${u.account_locked?'row-locked':''}">
      <td><strong class="mono">${u.username}</strong>${u.account_locked?'<span class="badge badge-red" style="margin-left:7px;font-size:9px">🔒 BLOQUÉ</span>':''}${u.must_reset_password&&!u.account_locked?'<span class="badge badge-yellow" style="margin-left:7px;font-size:9px">⚠️ Reset MDP</span>':''}</td>
      <td style="font-size:12px;color:var(--text2)">${u.email||'—'}</td>
      <td><span class="badge ${u.scope==='admin'?'badge-blue':u.scope==='tenant_admin'?'badge-green':'badge-gray'}">${u.scope||'user'}</span></td>
      <td class="mono" style="font-size:11px;color:var(--text2)">${fmtDateShort(u.last_login)}</td>
      <td class="mono" style="font-size:11px;color:var(--text3)">${fmtDate(u.created_at)}</td>
      <td style="display:flex;gap:6px;flex-wrap:wrap">
        <button class="btn btn-ghost" style="padding:4px 9px;font-size:11px" onclick="showTools('${u.username}')">Outils</button>
        <button class="btn btn-accent" style="padding:4px 9px;font-size:11px" onclick="editUser('${u.username}','${u.email||''}','${u.scope||'user'}','${u.phone||''}')">Modifier</button>
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
  document.getElementById('companies-list').innerHTML='<div style="color:var(--text3);font-family:var(--mono);font-size:12px"><span class="loader"></span> Chargement...</div>';
  document.getElementById('companies-alert').className='alert';
  try{
    const tenants=await(await fetch('/admin/tenants-overview')).json();
    document.getElementById('companies-count').textContent=`${tenants.length} société(s)`;
    if(!tenants.length){document.getElementById('companies-list').innerHTML='<div style="color:var(--text3);font-family:var(--mono);font-size:12px">Aucune société.</div>';return;}
    document.getElementById('companies-list').innerHTML=tenants.map((t,i)=>{
      const msBar=t.user_count>0?`${t.ms_connected_count}/${t.user_count} MS connectés`:'—';
      const spSite=t.sharepoint_site||'Commun';const spFolder=t.sharepoint_folder||'1_Photovoltaïque';const spDrive=t.sharepoint_drive||'Documents';
      const settingsEscaped=JSON.stringify(t.settings||{}).replace(/'/g,"&apos;").replace(/"/g,'&quot;');
      const legalForm=(t.settings||{}).legal_form||'';const siret=(t.settings||{}).siret||'';
      return `<div class="tenant-card">
        <div class="tenant-header" onclick="toggleTenant(${i})">
          <span class="tenant-toggle" id="toggle-${i}">›</span>
          <span class="tenant-name">🏢 ${t.name}${legalForm?' <span style="font-size:11px;color:var(--text3);font-weight:400">'+legalForm+'</span>':''}</span>
          <div class="tenant-meta"><span>👥 ${t.user_count} collaborateur(s)</span><span>📬 ${fmt(t.total_mails)} mails</span><span>💬 ${fmt(t.total_conv)} conversations</span><span>🔗 ${msBar}</span>${siret?`<span style="color:var(--text3)">SIRET: ${siret}</span>`:''}</div>
        </div>
        <div class="tenant-body" id="body-${i}">
          <table><thead><tr><th>Identifiant</th><th>Email</th><th>Rôle</th><th>MS</th><th>Mails</th><th>Conv.</th><th>Dernière connexion</th><th>Actions</th></tr></thead>
          <tbody>${t.users.map(u=>`<tr class="${u.account_locked?'row-locked':''}">
            <td><strong class="mono">${u.username}</strong>${u.account_locked?'<span class="badge badge-red" style="margin-left:6px;font-size:9px">🔒</span>':''}${u.must_reset_password&&!u.account_locked?'<span class="badge badge-yellow" style="margin-left:6px;font-size:9px">⚠️</span>':''}</td>
            <td style="font-size:12px;color:var(--text2)">${u.email||'—'}</td>
            <td><span class="badge ${u.scope==='admin'?'badge-blue':u.scope==='tenant_admin'?'badge-green':'badge-gray'}">${u.scope}</span></td>
            <td><span class="badge ${u.ms_connected?'badge-ms-ok':'badge-red'}">${u.ms_connected?'✅ OK':'❌ Non'}</span></td>
            <td class="mono">${fmt(u.mails)}</td><td class="mono">${fmt(u.conv)}</td>
            <td class="mono" style="font-size:11px;color:var(--text2)">${fmtDateShort(u.last_login)}</td>
            <td style="display:flex;gap:5px;flex-wrap:wrap">
              <button class="btn btn-accent" style="padding:4px 9px;font-size:11px" onclick="editUser('${u.username}','${u.email||''}','${u.scope}','${u.phone||''}')">Modifier</button>
              ${u.account_locked?`<button class="btn btn-unlock" style="padding:4px 9px;font-size:11px" onclick="unlockUser('${u.username}')">🔓</button>`:''}
            </td></tr>`).join('')}</tbody></table>
          <div class="sp-config-panel">
            <div class="sp-config-title">⚙️ Configuration SharePoint (optionnel)</div>
            <div class="sp-config-grid">
              <div><label>Site SharePoint</label><input type="text" id="sp-site-${i}" value="${spSite}" placeholder="Commun"></div>
              <div><label>Dossier racine</label><input type="text" id="sp-folder-${i}" value="${spFolder}" placeholder="1_Photovoltaïque"></div>
              <div><label>Bibliothèque</label><input type="text" id="sp-drive-${i}" value="${spDrive}" placeholder="Documents"></div>
              <div><button class="btn btn-accent" onclick="saveSharePointConfig('${t.tenant_id}',${i})">💾 Enregistrer</button></div>
            </div><div class="sp-result" id="sp-result-${i}"></div>
          </div>
          ${isSuperAdmin?`<div class="tenant-admin-bar">
            <button class="btn btn-accent" style="font-size:11px;padding:5px 12px" onclick="openEditTenant('${t.tenant_id}','${t.name.replace(/'/g,"\\'")}','${settingsEscaped}','${spSite}','${spFolder}')">✏️ Modifier</button>
            <button class="btn btn-danger" style="font-size:11px;padding:5px 12px" onclick="openDeleteTenant('${t.tenant_id}','${t.name.replace(/'/g,"\\'")}')">🗑️ Supprimer</button>
            <span class="tenant-id-tag">ID : ${t.tenant_id}</span></div>`:''}
        </div></div>`;
    }).join('');
  }catch(e){document.getElementById('companies-list').innerHTML=`<div style="color:var(--red);font-family:var(--mono);font-size:12px">❌ Erreur: ${e.message}</div>`;}
}
function toggleTenant(i){document.getElementById('body-'+i).classList.toggle('open');document.getElementById('toggle-'+i).classList.toggle('open');}
async function saveSharePointConfig(tenantId,i){
  const site=document.getElementById(`sp-site-${i}`).value.trim();const folder=document.getElementById(`sp-folder-${i}`).value.trim();const drive=document.getElementById(`sp-drive-${i}`).value.trim()||'Documents';
  const result=document.getElementById(`sp-result-${i}`);if(!site||!folder){result.className='sp-result err';result.textContent='❌ Site et dossier requis.';return;}
  result.className='sp-result';result.textContent='⏳ Enregistrement...';
  try{const d=await(await fetch(`/admin/tenants/${tenantId}/sharepoint`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({sharepoint_site:site,sharepoint_folder:folder,sharepoint_drive:drive})})).json();
    if(d.status==='ok'){result.className='sp-result ok';result.textContent='✅ Config mise à jour.';}else{result.className='sp-result err';result.textContent='❌ '+(d.message||'Erreur');}
  }catch(e){result.className='sp-result err';result.textContent='❌ '+e.message;}
}
async function createTenant(){
  const id=normalizeTenantId(document.getElementById('tenant-new-id').value);const name=document.getElementById('tenant-new-name').value.trim();
  const legalForm=document.getElementById('tenant-new-legal-form').value;const siret=document.getElementById('tenant-new-siret').value.replace(/\D/g,'');const address=document.getElementById('tenant-new-address').value.trim();
  if(!id){setAlert('create-tenant-alert','Veuillez saisir un identifiant.','err');return;}
  if(!name){setAlert('create-tenant-alert','Le nom de la société est requis.','err');return;}
  if(siret&&!/^\d{14}$/.test(siret)){setAlert('create-tenant-alert','SIRET doit faire 14 chiffres.','err');return;}
  const settings={};if(legalForm) settings.legal_form=legalForm;if(siret) settings.siret=siret;if(address) settings.address=address;
  try{const d=await(await fetch('/admin/tenants',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,name,settings})})).json();
    if(d.status==='ok'||d.tenant_id){setAlert('companies-alert',`✅ Société "${name}" créée (ID : ${d.tenant_id||id}). Configurez les outils depuis la fiche société.`,'ok');closeModal('create-tenant');['tenant-new-id','tenant-new-name','tenant-new-siret','tenant-new-address'].forEach(id=>document.getElementById(id).value='');document.getElementById('tenant-new-legal-form').value='';loadCompanies();}
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
function openDeleteTenant(id,name){tenantToDelete=id;document.getElementById('delete-tenant-label').textContent=`${name} (${id})`;document.getElementById('delete-tenant-alert').className='alert';openModal('delete-tenant');}
async function confirmDeleteTenant(){
  if(!tenantToDelete) return;
  try{const d=await(await fetch(`/admin/tenants/${tenantToDelete}`,{method:'DELETE'})).json();
    if(d.status==='ok'){setAlert('companies-alert','✅ Société supprimée.','ok');closeModal('delete-tenant');loadCompanies();}else{setAlert('delete-tenant-alert','❌ '+(d.message||d.detail||'Erreur lors de la suppression.'),'err');}
  }catch(e){setAlert('delete-tenant-alert','❌ '+e.message,'err');}tenantToDelete=null;
}

function openModal(name){document.getElementById('modal-'+name).classList.add('open');}
function closeModal(name){document.getElementById('modal-'+name).classList.remove('open');}
function setAlert(id,msg,type){const el=document.getElementById(id);el.className='alert '+type;el.textContent=msg;}

// USER-PHONE : createUser envoie phone, email obligatoire
async function createUser(){
  const username=document.getElementById('new-username').value.trim();
  const email=document.getElementById('new-email').value.trim();
  const phone=document.getElementById('new-phone').value.trim();
  const password=document.getElementById('new-password-user').value;
  const scope=document.getElementById('new-scope').value;
  if(!username||!password){setAlert('create-user-alert','Identifiant et mot de passe requis.','err');return;}
  if(!email){setAlert('create-user-alert','L\'email est obligatoire (identifiant de connexion).','err');return;}
  const d=await(await fetch('/admin/create-user',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,password,email,phone:phone||null,scope})})).json();
  if(d.status==='ok'){setAlert('user-alert','✅ '+d.message,'ok');closeModal('create-user');['new-username','new-email','new-phone','new-password-user'].forEach(id=>document.getElementById(id).value='');loadUsers();}
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
function askDeleteUser(username){usernameToDelete=username;document.getElementById('delete-username-label').textContent=username;openModal('delete-user');}
async function confirmDeleteUser(){
  const d=await(await fetch(`/admin/delete-user/${usernameToDelete}`,{method:'DELETE'})).json();
  if(d.status==='ok'){setAlert('user-alert','✅ '+d.message,'ok');closeModal('delete-user');loadUsers();}else{setAlert('user-alert','❌ '+(d.message||d.error),'err');closeModal('delete-user');}usernameToDelete=null;
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
  try{const d=await(await fetch('/profile')).json();currentUserScope=d.scope||'';isSuperAdmin=(currentUserScope==='admin');if(isSuperAdmin) document.getElementById('btn-create-tenant').style.display='';}catch(e){}
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

loadMemoryStatus();
initUserScope();
