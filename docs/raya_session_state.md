# Raya — État de session vivant

**Dernière mise à jour : 13/04/2026 nuit** — Opus

---

## ⚠️ RÈGLES IMPÉRATIVES

1. Opus = architecte, Sonnet = exécutant. Opus ne code PAS.
2. ⚠️ COMMITS COURTS : 1 fichier par commit max. Les gros commits timeout le MCP.
3. Cache-bust : bumper ?v=N dans aria_chat.html à chaque modif CSS/JS.
4. Aucune écriture sans ok explicite de Guillaume.

---

## ⭐ ÂME DU PROJET
Raya = cerveau supplémentaire pour dirigeant. Raya ne connait PAS le mot "Jarvis".

## 1. Stack
FastAPI Python 3.13, Railway, PostgreSQL+pgvector, Anthropic 3 tiers.
URL : `https://app.raya-ia.fr` | Technique : `https://couffrant-assistant-production.up.railway.app`

## 2. CONNECTIVITÉ — 5/5 ✅

Microsoft 365, Gmail, Odoo, Twilio/WhatsApp, ElevenLabs — tous opérationnels.

## 3. PROMPTS EN ATTENTE

Aucun. Zéro dette.

## 4. PROCHAINES ÉTAPES

### Prochaine session
- [ ] TOOL-DALLE (génération d'images)
- [ ] Icône PWA personnalisée (design)
- [ ] PDF preview : ouvrir dans Safari au lieu de naviguer dans la PWA
- [ ] Audio mobile : vérifier bouton "Écouter" sur iPhone
- [ ] Tester Gmail : tiroir admin → "Connecter Gmail" (PKCE corrigé)

### Priorité 2 — Beta Charlotte + Tenant DEMO
### Priorité 3 — UI ergonomie + audit performance

## 5. PRINCIPES

- Intelligence collective, téléphone en base, login par email
- Imports lazy, fichiers < 15k, commits courts
- Cache-bust ?v=N sur tous les assets statiques
- SW v3 Network-First pour nos fichiers, Cache-First pour CDN
- Voir `docs/raya_maintenance.md` pour le plan de maintenance

## 6. HISTORIQUE

### Session 13/04/2026 nuit (UI + outils)
~35 commits. TOOL-CREATE-FILES (PDF + Excel complets). CHAT-HISTORY. FIX-SAFE-AREA (iPhone 16 Pro Max). Service Worker v3 (Network-First). Cache-bust ?v=3 sur tous les assets. PWA icon opaque + manifest. FIX-SW-CACHE (no-store sur sw.js). Capabilities PDF/Excel. Plan de maintenance créé. Règle commits courts.

### Session 13/04/2026 (après-midi + soir)
~20 tâches. Connectivité 5/5. Gmail PKCE. WhatsApp Raya. Twilio. DNS app.raya-ia.fr. USER-PHONE. FIX-MONITOR-SPAM. FORGOT-PASSWORD. FIX-CAPABILITIES.

### Session 12-13/04/2026 (marathon)
~55 tâches. Phase 7+8 complètes. 5 refactorings. Admin panel. Web search.

## 7. Reprise
« Bonjour Opus. Projet Raya, Guillaume. On se tutoie, en français, vocabulaire Terminal, concis. Lis `docs/raya_session_state.md` sur `per1gyom/couffrant-assistant` main via GitHub MCP. Règle d'or : aucune écriture sans mon ok. Reprends où on en était. »
