# Raya — État de session vivant

**Dernière mise à jour : 13/04/2026 matin** — Opus

---

## ⭐ ÂME DU PROJET — LIRE EN PREMIER

**Ce que Guillaume veut construire :**

Raya n'est PAS un chatbot. Raya n'est PAS un outil de tri de mails. Raya n'est PAS un assistant classique qui répond quand on lui parle.

Raya est un **cerveau supplémentaire** pour un dirigeant d'entreprise. Comme Jarvis pour Tony Stark dans Iron Man. Quelqu'un qui connaît son utilisateur en profondeur, qui comprend comment il fonctionne, qui anticipe ses besoins, et qui AGIT de façon autonome dans les limites que l'utilisateur a fixées.

**L'expérience visée :**

Guillaume a ~10 boîtes mail. Aujourd'hui, il est noyé sous les notifications. Le rêve : désactiver TOUTES les alertes mail de son téléphone et ne garder qu'un seul canal — Raya. Raya surveille tout en permanence. Si un mail important arrive, Raya envoie un message WhatsApp avec le résumé et les options d'action. Si c'est critique (avocat, banque, deadline), Raya appelle sur WhatsApp avec un résumé vocal et attend une décision. Le matin, Raya envoie un résumé de la nuit même s'il n'y a rien d'urgent — preuve de vie.

Guillaume possède plusieurs sociétés. Raya fait le lien entre elles : « Dupont relance sur le chantier (Couffrant Solar) ET la facture est en attente (autre société) ». Vision transversale que personne d'autre n'a.

**L'apprentissage — le cœur de Raya :**

Raya apprend comme deux humains qui se rencontrent. Au début (Découverte), elle est attentive, curieuse, elle confirme ce qu'elle croit comprendre. Avec le temps (Consolidation), elle connaît les habitudes, les contacts clés, les patterns. À maturité, elle anticipe et propose des automatisations : « Tu fais X chaque semaine, je peux le faire pour toi. »

Les règles ne sont PAS figées dans le code. Raya les crée, les modifie, les supprime elle-même. L'utilisateur peut corriger une erreur de classement et Raya met à jour ses règles instantanément. Plus elle apprend, moins elle se trompe, moins elle coûte.

**L'agnosticisme LLM — la force stratégique :**

La mémoire de Raya (règles, patterns, contacts, insights, style) est le vrai asset. Le modèle IA (Claude, GPT, Mistral) est interchangeable. Quand un meilleur modèle sort, on change UNE variable et Raya est immédiatement plus intelligente. Sa mémoire cumulée reste intacte. C'est le meilleur des deux mondes : intelligence de pointe + mémoire permanente. Ça n'existe pas sur le marché.

**La proactivité — Raya INITIE les interactions :**

Raya ne se contente pas de répondre. Elle surveille, évalue, et décide d'elle-même de prévenir l'utilisateur. Elle connaît ses outils (Outlook, Teams, Drive, Odoo, réseaux sociaux) et ne propose que ce qui est faisable avec les outils connectés. Un utilisateur avec Drive en lecture seule ne se verra jamais proposer « je crée un dossier pour toi ».

**L'entonnoir de triage — 5 étages (pas tout par IA) :**

1. Filtre par règles apprises (gratuit, code pur, ~70% éliminés)
2. Triage Haiku (prompt minimal, ~0.0003$/mail)
3. Analyse Sonnet (mails importants, avec score de certitude)
4. Escalade Opus (si Sonnet hésite, certitude < 0.8, ~2-5/semaine)
5. Décision d'alerte + composition message sortant

L'utilisateur peut corriger un mail mal classé → la règle se met à jour → l'entonnoir s'affine par le bas.

**Stratégie commerciale :**

Raya n'est pas un outil SaaS à 150€/mois. C'est un cerveau supplémentaire pour dirigeant : gain de productivité, de rigueur, de sérénité. Sa mémoire se bonifie avec le temps. Son prix doit refléter cette valeur. Tester sur Guillaume (Couffrant Solar) et Charlotte (Juillet), extraire un modèle générique de démarrage, commercialiser à quelques sociétés locales, recruter pour SAV.

**Guillaume n'est PAS programmeur.** Il a une vision très nette mais pas les compétences techniques. Il faut lui expliquer simplement, sans jargon. Il prend les décisions, Opus conçoit l'architecture, Sonnet exécute le code.

---

## 0. CONSIGNES GUILLAUME
- Ne JAMAIS suggérer de changer de conversation. Relire ce fichier si besoin.
- Vocabulaire : « Terminal » (jamais « shell SSH »).
- Concis. Langage simple, jamais de jargon non expliqué.
- 🟢 lecture / 🟡 modifie / 🔴 sensible. Une commande à la fois.
- **Règle d'or : aucune écriture sans « ok vas-y » explicite.**
- Après push GitHub : `exit` puis `railway ssh` pour récupérer code à jour.
- **Rôle Opus = architecte uniquement** : vision, prompts courts pour Sonnet, vérification post-push via lecture code, mise à jour state file. Pas de pilotage en direct, pas de code, pas de push applicatif.
- **Prompts pour Sonnet** : inclure instruction de push direct (Guillaume ne peut pas juger le code). Ajouter en fin de prompt : « Rapport pour Opus : fichier(s) modifié(s), ligne(s) changée(s), SHA du commit. »
- **Repo local Mac abandonné.** Ne jamais travailler en local. Tout passe par GitHub MCP ou l'interface web GitHub.

## 1. Rôles
Guillaume (dirigeant, non-programmeur, vision) / Opus (architecte, MCP GitHub+Postgres) / Sonnet (exécutant, code+push).

## 2. Stack
FastAPI Python 3.13 sur Railway. Repo public `github.com/per1gyom/couffrant-assistant` main. Railway projet `invigorating-wholeness` / env `production` / service `Aria`. Postgres+pgvector base `railway`, tenant `couffrant_solar`. Anthropic 3 tiers + OpenAI text-embedding-3-small.

## 3. État vérifié 13/04/2026 matin
**RAG vectoriel ACTIVÉ ✅** — 1045/1045 embeddings.
**Tests Phase 4 — 16/16 VERTS ✅**.
**Webhook Teams ✅** : subscription Microsoft valide, renouvellement auto 6h.
**Audit global ✅** : réalisé le 12/04/2026, tous les fichiers lus. Roadmap V2 commitée.
**Agnosticisme LLM ✅** : plus aucun `import anthropic` en dehors de `llm_client.py`.
**Hotfix 12/04 soir** : `app/routes/memory.py` importait encore `from app.ai_client import client` → migré vers `llm_complete()`. Corrigé (SHA `9866d19`).

## 4. AVANCEMENT PHASE 5A (en cours)

| Tâche | Statut | Description |
|---|---|---|
| 5A-1 | ✅ | Mot de passe par défaut supprimé config.py |
| 5A-2 | ✅ | Cookie session 30j → 7j |
| 5A-3 | ✅ | Rate limiter 60 req/h |
| 5A-4 | ✅ | admin_audit_log (10 appels) |
| 5A-5 | ✅ | ai_client.py → llm_complete |
| 5A-6 | ✅ | memory_contacts.py → llm_complete |
| 5A-7 | ✅ | memory_style.py → llm_complete |
| 5A-8 | ✅ | Doublon get_contacts_keywords supprimé |
| 5A-9+13 | ✅ | Wrappers dépréciés supprimés |
| 5A-12 | ✅ | 9 scripts legacy supprimés (Guillaume via GitHub web) |
| Hotfix | ✅ | routes/memory.py migré vers llm_complete (4ème fichier oublié) |
| 5A-10 | ❌ à faire | Brancher aria_actions.py sur tools_registry |
| 5A-11 | ❌ à faire | Migrer webhook renewal/token refresh vers APScheduler |
| 5A-14 | ❌ à faire | Simplifier memory_loader → supprimer memory_manager.py |

**Prochaine étape : 5A-10** (brancher aria_actions.py sur tools_registry)

## 5. TODO — ROADMAP V2 (voir `docs/raya_roadmap_v2.md` pour détails complets)
Ordre : 5A (11/14 faites) → 5B → 5C → 5D → 5E → 5G → 5F → Phase 7 (Jarvis) → Phase 6.

Planning estimé : Phase 7 fonctionnelle ~mi-août 2026. Jarvis minimal (triage + WhatsApp) ~mi-juin.

## 6. Décisions B1–B32 (résumé)
B1-B2 routage ✅. B3-B7/B14/B30/B32 RAG + rule_validator ✅. B5 audit ✅. B6 décroissance ✅. B8 session thématique ✅. B9 notifs ✅. B11-B12 multi-tenant 🟡. B13 onboarding ✅. B16/B18/B23 tools_registry 🟡. B17 costs ❌. B20 rename 🟡. B21-B22 hiérarchie ✅. B24 API ❌. B25 versioning ❌. B27 Pourquoi ✅. B29 honnêteté ✅. B31 feedback ✅. B10 proactivity ❌. B15 hors-cadre ❌.

## 7. Schéma aria_rules
`id, category, rule, source, confidence, reinforcements, active(bool), created_at, updated_at, context, username, tenant_id, embedding(vector)`. Migration Alembic Phase 6-5.

## 8. Utilisateurs cibles
- **Guillaume Perrin** — Couffrant Solar (photovoltaïque, Loire). Microsoft 365 + Odoo + SharePoint. ~10 boîtes mail (mix MS/Gmail).
- **Charlotte Couffrant** — Juillet (événementiel d'entreprise). Gmail + LinkedIn + Instagram. Outils détaillés à préciser. Beta test multi-tenant prévu ~mi-juin.

## 9. Pièges
- **Repo local Mac abandonné.** Ne jamais y toucher. Tout via GitHub.
- MCP GitHub en écriture instable le soir — `push_files` plus fiable que `create_or_update_file`.
- MCP GitHub ne peut PAS supprimer de fichiers → Guillaume via interface web GitHub.
- `tools_registry` pas consulté par `aria_actions.py` → 5A-10.
- Quand on migre des imports, scanner TOUT le repo (`github:search_code`) pour éviter des oublis (leçon du hotfix memory.py).
- CLI Railway oublie linking — refaire `cd ~/couffrant-assistant && railway link`.

## 10. Outils Opus
GitHub MCP (lecture + push_files + search_code), Postgres MCP query lecture base prod `railway`. Différés via `tool_search`.

## 11. Reprise nouvelle conversation
« Bonjour Opus. Projet Raya, Guillaume. On se tutoie, en français, vocabulaire Terminal, concis. Lis `docs/raya_session_state.md` puis `docs/raya_roadmap_v2.md` sur `per1gyom/couffrant-assistant` main via GitHub MCP. Règle d'or : aucune écriture sans mon ok. Reprends où on en était. »

## 12. RÈGLE — Mise à jour obligatoire
À chaque jalon, Opus met à jour ce fichier. Non négociable.
