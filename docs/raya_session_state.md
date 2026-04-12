# Raya — État de session vivant

**Dernière mise à jour : 13/04/2026 après-midi** — Opus

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

La mémoire de Raya (règles, patterns, contacts, insights, style) est le vrai asset. Le modèle IA (Claude, GPT, Mistral) est interchangeable. Quand un meilleur modèle sort, on change UNE variable et Raya est immédiatement plus intelligente. Sa mémoire cumulée reste intacte.

**La proactivité — Raya INITIE les interactions :**

Raya ne se contente pas de répondre. Elle surveille, évalue, et décide d'elle-même de prévenir l'utilisateur. Elle connaît ses outils et ne propose que ce qui est faisable avec les outils connectés.

**L'entonnoir de triage — 5 étages :**

1. Filtre par règles apprises (gratuit, ~70% éliminés)
2. Triage Haiku (~0.0003$/mail)
3. Analyse Sonnet (score de certitude)
4. Escalade Opus (si certitude < 0.8)
5. Décision d'alerte + message sortant

**Guillaume n'est PAS programmeur.** Expliquer simplement, sans jargon.

---

## 0. CONSIGNES GUILLAUME
- Vocabulaire : « Terminal ». Concis. Langage simple.
- **Règle d'or : aucune écriture sans « ok vas-y » explicite.**
- **Rôle Opus = architecte uniquement.**
- **Repo local Mac abandonné.** Tout via GitHub MCP ou interface web.

## 1. Rôles
Guillaume (dirigeant, vision) / Opus (architecte, MCP GitHub+Postgres) / Sonnet (exécutant, code+push).

## 2. Stack
FastAPI Python 3.13 sur Railway. Repo `github.com/per1gyom/couffrant-assistant` main.

## 3. État vérifié 13/04/2026
**PHASE 5A TERMINÉE ✅ (14/14)**
**PHASE 5B TERMINÉE ✅ (5/5)**
**PHASE 5C TERMINÉE ✅ (4/4)**
**RAG vectoriel ✅** — 1045 embeddings.
**Agnosticisme LLM ✅**
**Injection dynamique actions ✅** — 30-60% tokens économisés.
**Cache mémoire TTL 5min ✅**
**Hot_summary 3 niveaux + vectorisé ✅**
**Structured logging ✅** (main.py + scheduler.py, reste progressif)
**Health check profond ✅** (DB + LLM)
**Timeout 30s sur /raya ✅**

## 4. AVANCEMENT

**Phases 5A, 5B, 5C : TERMINÉES ✅**

**Prochaine étape : Phase 5D — Mode Dirigeant multi-société**

| # | Tâche | Complexité |
|---|---|---|
| 5D-1 | Table `user_tenant_access` (many-to-many user/tenant/rôle) | moyenne |
| 5D-2 | Contexte multi-tenant dans le prompt | haute |
| 5D-3 | Deuxième compte super_admin | faible |
| 5D-4 | Onboarding par tenant | moyenne |

## 5. ROADMAP
Ordre : ~~5A~~ → ~~5B~~ → ~~5C~~ → **5D** → 5E → 5G → 5F → Phase 7 (Jarvis) → Phase 6.
Voir `docs/raya_roadmap_v2.md` pour détails complets.

## 6. Utilisateurs cibles
- **Guillaume Perrin** — Couffrant Solar. MS365 + Odoo + SharePoint. ~10 boîtes mail.
- **Charlotte Couffrant** — Juillet (événementiel). Gmail + LinkedIn + Instagram. Beta ~mi-juin.

## 7. Pièges
- Repo local Mac abandonné.
- MCP écriture : `push_files` plus fiable que `create_or_update_file`.
- MCP ne peut PAS supprimer de fichiers → GitHub web.
- Scanner TOUT le repo (`search_code`) après migration d'imports.

## 8. Modèle prompt Sonnet
```
Projet Raya — Tâche [NUM] assignée par Opus.
Repo `per1gyom/couffrant-assistant` branche `main`. Pousse directement.
[PROBLÈME EN 2-3 LIGNES]
Ce que tu dois faire : [INSTRUCTIONS]
Commit message : `[TYPE](scope): description — [NUM]`
Rapport pour Opus : fichier(s) modifié(s), ligne(s) changée(s), SHA du commit.
```

## 9. Reprise nouvelle conversation
« Bonjour Opus. Projet Raya, Guillaume. On se tutoie, en français, vocabulaire Terminal, concis. Lis `docs/raya_session_state.md` puis `docs/raya_roadmap_v2.md` sur `per1gyom/couffrant-assistant` main via GitHub MCP. Règle d'or : aucune écriture sans mon ok. Reprends où on en était. »

## 10. RÈGLE — Mise à jour obligatoire
À chaque jalon, Opus met à jour ce fichier + le changelog. Non négociable.
