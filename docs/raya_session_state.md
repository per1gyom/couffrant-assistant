# Raya — État de session vivant

**Dernière mise à jour : 14/04/2026 nuit** — Opus

---

## ⚠️ RÈGLES IMPÉRATIVES

1. Opus = architecte, Sonnet = exécutant. Opus ne code PAS.
2. ⚠️ COMMITS COURTS : 1 fichier par commit max. Les gros commits timeout le MCP.
3. Cache-bust : bumper ?v=N dans aria_chat.html à chaque modif CSS/JS (actuellement v=3).
4. Aucune écriture sans ok explicite de Guillaume.
5. JAMAIS push_files pour du code Python — corrompt les \n.

---

## ⭐ ÂME DU PROJET
Raya = cerveau supplémentaire pour dirigeant. Raya ne connait PAS le mot "Jarvis".

## 1. Stack
FastAPI Python 3.13, Railway, PostgreSQL+pgvector, Anthropic 3 tiers.
URL : `https://app.raya-ia.fr` | Technique : `https://couffrant-assistant-production.up.railway.app`

## 2. CONNECTIVITÉ — 5/5 ✅

Microsoft 365, Gmail, Odoo, Twilio/WhatsApp, ElevenLabs — tous opérationnels.

## 3. PROMPTS EN ATTENTE

- TOOL-READ-PDF 3/3 — modification chirurgicale de raya.py (prompt prêt)

## 4. PROCHAINES ÉTAPES

### Immédiat (cette session / demain matin)
- [ ] TOOL-READ-PDF 3/3 — injection texte PDF dans contexte LLM (raya.py)
- [ ] Icône PWA — stocker le smiley vert dans app/static/raya_icon.png + update endpoint
- [ ] Signature email — HTML Helvetica + image bandeau Couffrant Solar
- [ ] Tester création PDF/Excel/DALL-E
- [ ] Tester safe-area iPhone 16 Pro Max

### Specs signature email (validées par Guillaume)
- Police : Helvetica partout
- "Solairement," → regular
- "Guillaume Perrin" → bold (seul élément en gras)
- "📞 06 49 43 09 17" → regular
- "🌐 couffrant-solar.fr" → regular, lien cliquable vers https://couffrant-solar.fr
- Image bandeau Couffrant Solar en dessous
- Largeur image = ~3× la ligne de texte la plus large (~500px)
- Images sources dans la conversation Opus du 13-14/04/2026

### Priorité 2
- [ ] PDF preview mobile (ouvrir dans Safari, pas dans la PWA)
- [ ] Audio "Écouter" sur iPhone
- [ ] Tester Gmail OAuth (PKCE corrigé)
- [ ] Beta Charlotte (tenant, cloisonnement, onboarding)

### Priorité 3
- [ ] Tenant DEMO (5 profils sectoriels — voir docs/raya_roadmap_demo.md)
- [ ] UI/Design refonte
- [ ] RGPD + facturation Stripe

## 5. PRINCIPES

- Intelligence collective, téléphone en base, login par email
- Imports lazy, fichiers < 15k, commits courts
- Cache-bust ?v=N sur tous les assets statiques
- SW v3 Network-First pour nos fichiers, Cache-First pour CDN
- Voir docs/raya_maintenance.md et docs/raya_roadmap_demo.md

## 6. HISTORIQUE

### Session 13-14/04/2026 nuit (marathon outils + UI)
~45 commits. TOOL-CREATE-FILES (PDF+Excel). TOOL-DALLE (images). TOOL-READ-PDF (2/3, reste raya.py). Capabilities PDF/Excel/DALL-E. CHAT-HISTORY. FIX-SAFE-AREA. SW v3 Network-First. Cache-bust ?v=3. FIX-SW-CACHE. PWA icon opaque + manifest. Plan maintenance. Roadmap démo 5 profils. Roadmap fichiers. Logo design validé (smiley vert clin d'oeil). Signature email spécifiée.

### Session 13/04/2026 (après-midi + soir)
~20 tâches. Connectivité 5/5. Gmail PKCE. WhatsApp. Twilio. DNS. USER-PHONE. FIX-MONITOR-SPAM. FORGOT-PASSWORD. FIX-CAPABILITIES.

### Session 12-13/04/2026 (marathon)
~55 tâches. Phase 7+8 complètes. 5 refactorings. Admin panel. Web search.

## 7. Reprise
« Bonjour Opus. Projet Raya, Guillaume. On se tutoie, en français, vocabulaire Terminal, concis. Lis `docs/raya_session_state.md` sur `per1gyom/couffrant-assistant` main via GitHub MCP. Règle d'or : aucune écriture sans mon ok. Reprends où on en était. »
