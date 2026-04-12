# Raya — État de session vivant

**Dernière mise à jour : 12/04/2026 soir** — Opus

---

## ⭐ ÂME DU PROJET
Raya = cerveau supplémentaire Jarvis pour dirigeant. 8 dimensions (compréhension cumulative, vision transversale, intelligence workflow, mémoire narrative, préparation anticipée, intelligence d'équipe, rythme business, méta-apprentissage). 3 modes (dirigeant multi-tenant / collaborateur pro / collaborateur perso avantage en nature). Supervision managériale (métriques oui, contenu conversations jamais). Voir `docs/raya_roadmap_v2.2.md` et commits précédents pour le détail complet.

## 0. CONSIGNES
- **Opus = architecte, Sonnet = exécutant. Opus ne code PAS.**
- **Prompts directement dans le chat, entre barres de code.**
- **JAMAIS push_files pour du code Python.**
- **Aucune écriture sans ok explicite de Guillaume.**

### Principe architectural fondamental (discussion 12/04/2026 soir)

**RIEN n'est codé en dur dans la logique de Raya.** Les canaux de communication,
les formats de rapport, les actions disponibles — tout est dynamique :

- Les **canaux de livraison** (chat, WhatsApp, mail, vocal, Telegram...) sont des OUTILS
  dans le `tools_registry`. Raya consulte la liste, sait lesquels sont disponibles
  pour cet utilisateur, et propose/utilise en conséquence.

- Les **préférences utilisateur** (format du rapport, canal préféré, contenu souhaité)
  sont des règles apprises dans `aria_rules` — pas du code.

- Pour ajouter un **nouveau canal** : connecteur + enregistrement dans `tools_registry`.
  Raya le propose automatiquement — zéro changement dans sa logique.

LLM-agnostic, tools-agnostic, channel-agnostic.

## 1. Stack
FastAPI Python 3.13, Railway, PostgreSQL+pgvector, Anthropic 3 tiers, OpenAI embeddings.
Repo `github.com/per1gyom/couffrant-assistant` main.

## 2. État
**PHASES 5 : TERMINÉES ✅** | **PHASE 7 JARVIS : 11 tâches ✅**

| Fait Phase 7 | Détail |
|---|---|
| urgency_model ✅ | Score 0-100, 4 étages (règles→contacts→patterns→Haiku), certitude, VIP boost |
| Shadow mode ✅ | shadow_mode + shadow_mode_until sur users, alertes [SHADOW] en chat |
| Notification prefs ✅ | Plages silencieuses, VIP emails/domaines, calendar_aware, should_notify() |
| WhatsApp structuré ✅ | send_whatsapp_structured() avec 4 options de réponse rapide |
| Activity log ✅ | Table + log dans 4 handlers (mail/drive/teams/memory) + conversations |
| Mémoire narrative ✅ | dossier_narratives vectorisée, injection RAG dans prompt |
| Briefings réunions ✅ | Job 6h30, Haiku + narratives, alerte par événement |
| Rapport stocké + ping ✅ | daily_reports table, _prepare_daily_report() stocke, _send_report_ping() ping léger |
| Livraison rapport ✅ | report_actions.py (get/mark/section), injection prompt, marquage auto dans raya.py |
| Workflow intelligence ✅ | _analyze_patterns() lit activity_log (150 actions 30j), type workflow dans prompt |

Sprint 1 du planning V3 : TERMINÉ ✅

## 3. PROCHAINE ÉTAPE (Sprint 2 — planning V3)

1. **7-1 Multi-mailbox Gmail** — OAuth2 + polling + brancher sur le même pipeline webhook
2. **7-7 Monitoring + fallbacks** — alertes si scan inactif > 10min, fallback SMS
3. **7-8 Canal WhatsApp bidirectionnel** — recevoir les réponses, parser, exécuter

Voir `docs/raya_planning_v3.md` pour le calendrier complet.

## 4. NOTES POUR PLUS TARD (pré-commercialisation)

### Raya et ses limites → redirection vers l'humain
- **Si collaborateur** → contacter l'admin de son tenant
- **Si admin/dirigeant** → contacter le support Raya
- `SUPPORT_EMAIL` existe déjà dans `config.py`, étendre avec `SUPPORT_PHONE` + contact admin par tenant
- Raya ne dit jamais "je ne peux pas" sans donner une alternative ou un recours humain

## 5. Reprise
« Bonjour Opus. Projet Raya, Guillaume. On se tutoie, en français, vocabulaire Terminal, concis. Lis `docs/raya_session_state.md` puis `docs/raya_roadmap_v2.md` sur `per1gyom/couffrant-assistant` main via GitHub MCP. Règle d'or : aucune écriture sans mon ok. Reprends où on en était. »

## 6. RÈGLE
À chaque jalon, Opus met à jour ce fichier. Non négociable.

## 7. Variables Railway
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`
- `NOTIFICATION_PHONE_GUILLAUME=+33xxxxxxxxx`
- `SUPPORT_EMAIL` (existe déjà dans config.py)
