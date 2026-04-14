# Raya — État de session vivant

**Dernière mise à jour : 14/04/2026 23h00** — Opus

---

## ⚠️ RÈGLES IMPÉRATIVES (NON NÉGOCIABLES)

### Rôles — MISE À JOUR
- **Opus = architecte + codeur direct** : audite, conçoit, code et pousse via GitHub MCP.
- **Sonnet Flutter** : conversation parallèle dédiée à l'app native iOS.
- **Guillaume = décideur** : valide, teste.

### Règles techniques
- 1 fichier par commit max. Fichiers >15KB risquent le timeout MCP.
- JAMAIS `push_files` pour du code Python.
- Template chat : **`app/templates/raya_chat.html`** (renommé depuis aria_chat.html)
- Cache-bust : `?v=N` dans raya_chat.html (actuellement **v=7**)
- Langue : français, vocabulaire Terminal, concis

---

## ⭐ ÂME DU PROJET
Raya = cerveau supplémentaire pour dirigeant. LLM-agnostic, tools-agnostic, channel-agnostic.

## 1. Stack
FastAPI Python 3.13, Railway, PostgreSQL+pgvector, Anthropic 3 tiers, OpenAI embeddings.
URL : `https://app.raya-ia.fr`

## 2. CONNECTIVITÉ — 5/5 ✅
## 3. OUTILS DE CRÉATION ✅ (PDF, Excel, DALL-E, lecture PDF)
## 4. PWA ✅ (v=7, iOS autoSpeak off, safe-area)

## 5. SÉCURITÉ ✅
- Anti-injection, GUARDRAILS, discipline apprentissages
- CSP, bcrypt, lockout, rate limiting, try/finally DB
- À faire : CSRF tokens

## 6. SIGNATURE EMAIL ✅ (v1 fallback + v2 extraction LLM)
## 7. SAV / BUG REPORT ✅ (bouton 🐛)
## 8. RGPD ✅ (export, suppression, mentions légales)
## 9. BACKUP DB ✅ (manuel — auto S3 à compléter)

## 10. UX CHAT ✅
- Nettoyage actions brutes (FIX-CLEAN) ✅
- Déduplication confirmations corbeille/archive ✅
- Horodatage des messages (TIMESTAMP) ✅
- Pilule verte mémoire (FIX-LEARN-UI) ✅
- Guardrail narration verbatim ✅

## 11. TOPICS — EN COURS (3/5)
- [x] `app/topics.py` : 5 endpoints CRUD (GET/POST/PATCH/DELETE /topics + PATCH /topics/settings)
- [x] `app/main.py` : router monté
- [x] `database_migrations.py` : table user_topics + users.settings JSONB
- [ ] RGPD : ajouter user_topics à export + delete (security_users.py trop gros pour MCP)
- [ ] Prompt : injecter topics actifs dans aria_context.py + action CREATE_TOPIC

## 12. MULTI-TENANT
- Tenant `couffrant_solar` : Guillaume (admin)
- Tenant `juillet` : Charlotte (beta) — compte à créer
- Profils seeding : pv_french, event_planner, generic

## 13. FLUTTER — EN PARALLÈLE
- Conversation Opus séparée, specs dans `docs/raya_flutter_ux_specs.md`
- Même backend API, nouveau frontend natif iOS
- Résout : micro instable, autoplay audio, navigation fichiers

## 14. ROADMAP

### Prochaines tâches immédiates
- [ ] TOPICS : finir RGPD + injection prompt (2 fichiers lourds)
- [ ] Suppression 9 fichiers morts (git rm manuel — voir liste ci-dessous)
- [ ] B2 : Tester Gmail OAuth + outils en prod
- [ ] B4+ : Créer compte Scaleway pour backup auto
- [ ] Tester 💌 signatures
- [ ] Créer compte Charlotte tenant juillet
- [ ] Audit performance (délai de réponse)

### Fichiers à supprimer (git rm)
```
app/routes/aria.py
app/routes/raya_actions.py
app/routes/raya_context.py
app/routes/aria_actions.py
app/database_migrations_patch_gmail.tmp
app/database_patch_jarvis.tmp
app/static/chat-markdown.css
app/templates/aria_chat.html
```

### Bloc C restant
- [ ] C1 : Beta Charlotte
- [ ] C2 : Tenant DEMO
- [ ] C4 : WhatsApp production
- [ ] C5 : Facturation Stripe
- **Objectif : premier client payant juillet 2026**

### Phase 2 — App native iOS Flutter (août-sept 2026)
### Phase 3 — Android (fin 2026)
### Phase 4 — Maturité (2027)

## 15. HISTORIQUE

### Session 14/04/2026 (~45 commits — session marathon)
AUDIT COMPLET. P0-1 anti-injection. P1-1→P1-5 SAV. Bloc A complet. B1 PDF mobile. B3 signature v2. B4 backup. C1-prep RGPD. C3 complet. FIX-LEARN. FIX-CLEAN + TIMESTAMP. RENAME raya_chat.html. TOPICS 3/5. Lancement Flutter parallèle.

### Sessions précédentes
13-14/04 nuit : ~50 commits (outils création, PWA, signature v1)
13/04 : Connectivité 5/5, Gmail, WhatsApp, DNS
12-13/04 : ~55 tâches, Phase 7+8, Admin panel, Web search

## 16. REPRISE
« Bonjour Opus. Projet Raya, Guillaume Perrin (Couffrant Solar). On se tutoie, en français, vocabulaire Terminal, concis. Lis `docs/raya_session_state.md` sur `per1gyom/couffrant-assistant` main via GitHub MCP. Reprends où on en était. »
