// chat-admin.js — Tiroir administration

function toggleDrawer() { const d=document.getElementById('drawer'); if(d.classList.contains('open')) closeDrawer(); else openDrawer(); }
function openDrawer() { document.getElementById('drawer').classList.add('open'); document.getElementById('drawerOverlay').classList.add('open'); document.getElementById('adminBtn').classList.add('active'); }
function closeDrawer() { document.getElementById('drawer').classList.remove('open'); document.getElementById('drawerOverlay').classList.remove('open'); document.getElementById('adminBtn').classList.remove('active'); }

async function drawerAction(btn, url, id) {
  const el=document.getElementById('result-'+id);
  el.className='d-btn-result loading'; el.textContent='⏳ En cours…'; btn.disabled=true;
  try {
    const d=await (await fetch(url)).json(); const txt=formatDrawerResult(d);
    el.className='d-btn-result ok'; el.textContent=txt; showToast(txt.split('\n')[0].substring(0,60),'ok');
  } catch(e) { el.className='d-btn-result err'; el.textContent='❌ Erreur: '+e.message; showToast("Erreur lors de l'action",'err'); }
  btn.disabled=false;
}
async function drawerConfirmAction(e, url, id) { e.stopPropagation(); drawerHideConfirm(e,'confirm-'+id); await drawerAction(e.target.closest('.d-btn'), url, id); }
function drawerShowConfirm(id) { document.getElementById(id).classList.add('visible'); }
function drawerHideConfirm(e, id) { e.stopPropagation(); document.getElementById(id).classList.remove('visible'); }

async function drawerMemoryStatus(btn) {
  const el=document.getElementById('result-status'); el.className='d-btn-result loading'; el.textContent='⏳ Chargement…'; btn.disabled=true;
  try {
    const d=await (await fetch('/memory-status')).json(); const n1=d.niveau_1||{}, n2=d.niveau_2||{};
    el.className='d-btn-result info';
    el.textContent=`📬 Mails : ${n2.mail_memory||0}\n💬 Conversations : ${n2.conversations_brutes||0}\n📋 Règles actives : ${n1.regles_actives||0}\n💡 Insights : ${n1.insights||0}\n👥 Contacts : ${n1.contacts||0}\n✍️ Style : ${n2.style_examples||0} exemples`;
  } catch(e) { el.className='d-btn-result err'; el.textContent='❌ Erreur'; }
  btn.disabled=false;
}

async function drawerRules(btn) {
  const el=document.getElementById('result-rules'); el.className='d-btn-result loading'; el.textContent='⏳ Chargement…'; btn.disabled=true;
  try {
    const rules=await (await fetch('/rules')).json(); const active=rules.filter(r=>r.active);
    if (!active.length) { el.className='d-btn-result info'; el.textContent='Aucune règle active.'; }
    else {
      const cats={}; active.forEach(r=>{cats[r.category]=(cats[r.category]||0)+1;});
      el.className='d-btn-result info';
      el.textContent=`${active.length} règles actives :\n`+Object.entries(cats).map(([k,v])=>`${k} : ${v}`).join('\n');
    }
  } catch(e) { el.className='d-btn-result err'; el.textContent='❌ Erreur'; }
  btn.disabled=false;
}

function formatDrawerResult(d) {
  if (d.error) return '❌ '+d.error;
  if (d.status==='ok'||d.status==='termine') {
    const parts=[];
    if (d.analyzed!==undefined) parts.push(`✅ ${d.analyzed} analysés`);
    if (d.remaining!==undefined) parts.push(`${d.remaining} restants`);
    if (d.inserted!==undefined) parts.push(`✅ ${d.inserted} importés`);
    if (d.deleted!==undefined) parts.push(`✅ ${d.deleted} supprimés`);
    if (d.conversations_synthesized!==undefined) parts.push(`✅ ${d.conversations_synthesized} synthétisées`);
    if (d.rules_extracted!==undefined) parts.push(`${d.rules_extracted} règles extraites`);
    if (parts.length) return parts.join('\n'); return '✅ OK';
  }
  if (d.status==='mail_memory_cleared') return '✅ Historique mails vidé.';
  if (d.status) return '✅ '+d.status;
  return JSON.stringify(d).replace(/[{}"]/g,'').replace(/,/g,'\n').substring(0,200);
}
