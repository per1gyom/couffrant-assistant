# Raya — État de session vivant

**Dernière mise à jour : 14/04/2026 01h** — Opus

---

## ⚠️ RÈGLES IMPÉRATIVES

1. Opus = architecte, Sonnet = exécutant. Opus ne code PAS.
2. ⚠️ COMMITS COURTS : 1 fichier par commit max. Les gros commits timeout le MCP.
3. Cache-bust : bumper ?v=N dans aria_chat.html à chaque modif CSS/JS (actuellement v=3).
4. Aucune écriture sans ok explicite de Guillaume.
5. JAMAIS push_files pour du code Python — corrompt les \n.
6. Prompts pour Sonnet : toujours inclure "Rapport pour Opus : fichier(s), SHA."

---

## ⭐ ÂME DU PROJET
Raya = cerveau supplémentaire pour dirigeant. LLM-agnostic, tools-agnostic, channel-agnostic.
Raya ne connait PAS le mot "Jarvis".

## 1. Stack
FastAPI Python 3.13, Railway, PostgreSQL+pgvector, Anthropic 3 tiers, OpenAI embeddings.
Repo `github.com/per1gyom/couffrant-assistant` main.
URL : `https://app.raya-ia.fr` | Technique : `https://couffrant-assistant-production.up.railway.app`
Service Railway renommé "Raya".

## 2. CONNECTIVITÉ — 5/5 ✅
Microsoft 365, Gmail, Odoo, Twilio/WhatsApp, ElevenLabs.

## 3. OUTILS DE CRÉATION ✅
- Création PDF (reportlab) — [ACTION:CREATE_PDF]
- Création Excel (openpyxl) — [ACTION:CREATE_EXCEL]
- Création images (DALL-E 3) — [ACTION:CREATE_IMAGE]
- Lecture PDF uploadé (pdfplumber) — texte injecté dans contexte LLM

## 4. PWA ✅
- Icône : smiley vert clin d'oeil (app/static/5AEA8C3F...png)
- Service Worker v3 : Network-First pour nos fichiers, Cache-First CDN
- Cache-bust ?v=3 sur tous les assets
- sw.js servi avec Cache-Control: no-store
- Safe-area iPhone 16 Pro Max (Dynamic Island + barre home)

## 5. SIGNATURE EMAIL — EN ÉVOLUTION
### Implémentation actuelle (v1)
- `app/email_signature.py` : signature statique Guillaume (Helvetica, bandeau Photo_9.jpg)
- `outlook_connector.py` : `_build_email_html()` appelle `get_email_signature()`
- Fonctionne pour le compte Microsoft

### À faire (v2 — signatures dynamiques par boîte mail)
- Chaque boîte mail a sa propre signature déjà configurée
- Microsoft : Graph API n'ajoute PAS la signature auto → il faut la stocker
- Gmail : API expose les signatures via `sendAs` → récupération possible
- Créer table `email_signatures` (username, email_address, signature_html)
- Bouton admin "Récupérer mes signatures" ou saisie manuelle
- `get_email_signature(username, from_address)` → signature selon l'adresse

## 6. PROCHAINES ÉTAPES

### Immédiat
- [ ] Signatures dynamiques par boîte mail (v2)
- [ ] PDF preview mobile (ouvrir dans Safari)
- [ ] Audio "Écouter" sur iPhone
- [ ] Tester Gmail OAuth (PKCE corrigé)

### Court terme
- [ ] Beta Charlotte (tenant, cloisonnement, onboarding)
- [ ] UI/Design refonte

### Moyen terme
- [ ] Tenant DEMO (5 profils — voir docs/raya_roadmap_demo.md)
- [ ] WhatsApp production (sortir du sandbox)
- [ ] RGPD + facturation Stripe

## 7. PRINCIPES
- Intelligence collective, téléphone en base, login par email
- Imports lazy, fichiers < 15k, commits courts
- Voir docs/raya_maintenance.md et docs/raya_roadmap_demo.md

## 8. HISTORIQUE

### Session 13-14/04/2026 (marathon nuit — ~50 commits)
TOOL-CREATE-FILES (PDF+Excel). TOOL-DALLE. TOOL-READ-PDF (3/3). Capabilities. CHAT-HISTORY. FIX-SAFE-AREA. SW v3. Cache-bust. FIX-SW-CACHE. PWA icon smiley. EMAIL-SIGNATURE v1. Plan maintenance. Roadmap démo 5 profils. Roadmap fichiers.

### Session 13/04/2026 (après-midi + soir)
~20 tâches. Connectivité 5/5. Gmail PKCE. WhatsApp. DNS app.raya-ia.fr.

### Session 12-13/04/2026 (marathon)
~55 tâches. Phase 7+8. Admin panel. Web search.

## 9. Reprise
« Bonjour Opus. Projet Raya, Guillaume. On se tutoie, en français, vocabulaire Terminal, concis. Lis `docs/raya_session_state.md` sur `per1gyom/couffrant-assistant` main via GitHub MCP. Règle d'or : aucune écriture sans mon ok. Reprends où on en était. »
