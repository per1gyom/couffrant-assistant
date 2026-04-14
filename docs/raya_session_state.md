# Raya — État de session vivant

**Dernière mise à jour : 14/04/2026 21h00** — Opus

---

## ⚠️ RÈGLES IMPÉRATIVES (NON NÉGOCIABLES)

### Rôles
- **Opus = architecte UNIQUEMENT** : audite via GitHub MCP, conçoit, rédige des prompts pour Sonnet. NE CODE PAS.
- **Sonnet = exécutant** : reçoit les prompts copiés par Guillaume, code, pousse sur `main`.
- **Guillaume = décideur** : valide, teste, copie les prompts entre Opus et Sonnet.

### Workflow des prompts Opus → Sonnet
- Opus rédige des prompts avec les specs, Sonnet écrit le code
- **⚠️ COMMITS COURTS OBLIGATOIRES** : 1 fichier par commit max. Fichiers >15KB timeout MCP.
- Fichiers volumineux : modifications CHIRURGICALES uniquement
- Fin de chaque prompt : « Rapport pour Opus : fichier(s) modifié(s), SHA du commit. »
- JAMAIS `push_files` pour du code Python — corrompt les `\n`.

### Règles projet
- Cache-bust : bumper `?v=N` dans aria_chat.html à chaque modif CSS/JS (actuellement **v=6**, bump v=7 en attente)
- Aucune écriture sans ok explicite de Guillaume
- Langue : français, vocabulaire "Terminal", concis

---

## ⭐ ÂME DU PROJET
Raya = cerveau supplémentaire pour dirigeant. LLM-agnostic, tools-agnostic, channel-agnostic.
Raya ne connait PAS le mot "Jarvis".

## 1. Stack
FastAPI Python 3.13, Railway, PostgreSQL+pgvector, Anthropic 3 tiers, OpenAI embeddings.
Repo `github.com/per1gyom/couffrant-assistant` branche `main`.
URL : `https://app.raya-ia.fr` | Technique : `https://couffrant-assistant-production.up.railway.app`

## 2. CONNECTIVITÉ — 5/5 ✅
Microsoft 365, Gmail, Odoo, Twilio/WhatsApp, ElevenLabs.

## 3. OUTILS DE CRÉATION ✅
- Création PDF (reportlab) — [ACTION:CREATE_PDF]
- Création Excel (openpyxl) — [ACTION:CREATE_EXCEL]
- Création images (DALL-E 3) — [ACTION:CREATE_IMAGE]
- Lecture PDF uploadé (pdfplumber) — texte injecté dans contexte LLM
- Téléchargement — GET /download/{file_id}

## 4. PWA ✅
- Icône smiley vert clin d'oeil, SW v3 Network-First, cache-bust ?v=6
- Safe-area iPhone 16 Pro Max, 100dvh, sw.js no-store
- AutoSpeak désactivé automatiquement sur iOS (A3)

## 5. SÉCURITÉ ✅
- Anti-injection P0-1 : GUARDRAILS + balises `<donnees_externes>`
- CSP headers, X-Frame-Options DENY, session inactivity timeout
- Bcrypt passwords, account lockout, rate limiting
- SESSION_SECRET overridé dans Railway
- Connexions DB sécurisées try/finally
- Discipline des apprentissages (FIX-LEARN) : garde-fous sur quand apprendre
- À faire : CSRF tokens sur les POST

## 6. SIGNATURE EMAIL ✅
### V1 — fallback statique Guillaume
### V2 — en place (B3)
- `email_signature.py` : `get_email_signature()` DB→fallback, `extract_and_save_signature()` Graph+Haiku
- Table `email_signatures`, endpoint `POST /admin/extract-signatures`
- Bouton 💌 dans le tiroir admin

## 7. BOUTON SAV / BUG REPORT ✅
- `app/bug_reports.py` : POST /raya/bug-report, GET /admin/bug-reports, PATCH status
- Bouton 🐛 dans chat.js, dialog inline Bug/Amélioration

## 8. RGPD ✅ (C3)
- Export données : GET /account/export (JSON complet, 16 tables)
- Suppression compte : DELETE /account/delete?confirm=yes (anonymisation collective)
- Page mentions légales : GET /legal (publique, accessible sans auth)
- Boutons 📦 Export et ⛔ Supprimer dans le tiroir admin
- Lien mentions légales sur page login + drawer
- Purge RGPD couvre : email_signatures + bug_reports

## 9. BACKUP DB ✅ (B4)
- Bouton 💾 dans tiroir admin → GET /admin/backup
- pg_dump ou fallback CSV Python
- **À compléter** : backup auto quotidien vers S3 (Scaleway — compte à créer par Guillaume)

## 10. UX / QUALITÉ RÉPONSES (FIX-LEARN) ✅
- Capabilities mises à jour : DALL-E + lecture PDF ajoutés, limitation images supprimée
- GUARDRAILS : discipline des apprentissages (pas de LEARN sur faits ponctuels, max 2/réponse en découverte)
- Chat UI : notifications mémoire 🧠 remplacées par pilule verte discrète, conflits masqués

## 11. MULTI-TENANT
- Infrastructure prête : tenant_id sur toutes les tables, user_tenant_access, seeding par profil
- Tenant `couffrant_solar` : Guillaume (admin)
- Tenant `juillet` : Charlotte (beta) — compte à créer via panel admin
- Profils seeding : `pv_french`, `event_planner`, `generic`

## 12. ROADMAP

### Bloc A — Nettoyage ✅ TERMINÉ
### Bloc B — Fonctionnalités ✅ QUASI TERMINÉ
- [x] B1 : PDF preview mobile
- [ ] B2 : Tests Gmail OAuth + outils en prod (Guillaume cet après-midi)
- [x] B3 : Signature email v2
- [x] B4 : Backup DB (manuel — auto S3 à compléter)

### Bloc C — Préparation commerciale — EN COURS
- [x] C1-prep : RGPD purge email_signatures + bug_reports
- [ ] C1 : Beta Charlotte (créer compte tenant `juillet`)
- [ ] C2 : Tenant DEMO (5 profils sectoriels)
- [x] C3 : RGPD complet (export + suppression + mentions légales)
- [ ] C4 : WhatsApp production (sortir sandbox)
- [ ] C5 : Facturation Stripe
- [ ] CSRF tokens
- **Objectif : premier client payant juillet 2026**

### À faire (rappels Guillaume)
- [ ] A2b : Supprimer 7 fichiers morts (git rm)
- [ ] B2 : Tester Gmail OAuth + PDF/Excel/DALL-E en prod
- [ ] B4+ : Créer compte Scaleway pour backup auto
- [ ] Cache bust v=7 (après FIX-LEARN-UI)
- [ ] Tester bouton 💌 signatures

### Phase 2 — App native iOS (août-sept 2026) — Flutter
### Phase 3 — App native Android (fin 2026)
### Phase 4 — Maturité (2027)

## 13. HISTORIQUE DES SESSIONS

### Session 14/04/2026 (~30 commits — audit + sécurité + SAV + RGPD + UX)
AUDIT COMPLET (~35 fichiers). P0-1 anti-injection. P1-1→P1-5 bouton SAV. Bloc A complet (imports, iOS autoSpeak, logging, connexions DB). B1 PDF mobile. B3 signature v2. B4 backup DB. C1-prep RGPD purge. C3 complet (export, suppression, mentions légales). FIX-LEARN (capabilities, discipline apprentissages, pilule verte UI).

### Session 13-14/04/2026 (marathon nuit — ~50 commits)
TOOL-CREATE-FILES. TOOL-DALLE. TOOL-READ-PDF. Capabilities. CHAT-HISTORY. FIX-SAFE-AREA. SW v3. PWA icon. EMAIL-SIGNATURE v1. Roadmap démo. Décision Flutter iOS.

### Sessions précédentes
13/04 : Connectivité 5/5, Gmail PKCE, WhatsApp, DNS.
12-13/04 : ~55 tâches, Phase 7+8, Admin panel, Web search.

## 14. REPRISE
« Bonjour Opus. Projet Raya, Guillaume Perrin (Couffrant Solar). On se tutoie, en français, vocabulaire Terminal, concis. Tu es l'ARCHITECTE du projet. Tu ne codes JAMAIS. Tu rédiges des prompts pour Sonnet (l'exécutant). Lis `docs/raya_session_state.md` sur `per1gyom/couffrant-assistant` main via GitHub MCP. Règle d'or : aucune écriture sans mon ok. Reprends où on en était. »
