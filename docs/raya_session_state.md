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
  pour cet utilisateur, et propose/utilise en conséquence. Si un canal n'existe pas
  et que l'utilisateur le demande, Raya répond "je n'ai pas encore ce canal,
  mais je peux te l'envoyer par X ou Y."

- Les **préférences utilisateur** (format du rapport, canal préféré, contenu souhaité)
  sont des règles apprises dans `aria_rules` — pas du code. L'utilisateur modifie
  ses préférences en parlant à Raya, pas dans un panneau de configuration.

- Pour ajouter un **nouveau canal** (ex: Telegram) : un développeur crée le connecteur
  (`app/connectors/telegram_connector.py`), l'enregistre dans `tools_registry`,
  et Raya le propose automatiquement — sans toucher à sa logique.

C'est le même principe que pour les outils métier : LLM-agnostic, tools-agnostic,
channel-agnostic. La MÉMOIRE et l'INTELLIGENCE sont l'asset, les tuyaux sont
interchangeables.

## 1. Stack
FastAPI Python 3.13, Railway, PostgreSQL+pgvector, Anthropic 3 tiers, OpenAI embeddings.
Repo `github.com/per1gyom/couffrant-assistant` main.

## 2. État
**PHASES 5 : TERMINÉES ✅** | **PHASE 7 EN COURS (8/10+)**

| Fait Phase 7 | Détail |
|---|---|
| urgency_model ✅ | Score 0-100, 4 étages (règles→contacts→patterns→Haiku), certitude |
| Shadow mode ✅ | Alertes [SHADOW] en chat, pas de WhatsApp tant qu'actif |
| Heartbeat matinal ⚠️ | Code poussé MAIS à redesigner (voir section Rapport ci-dessous) |
| Notification prefs ✅ | Plages silencieuses, VIP emails/domaines, boost urgence |
| WhatsApp structuré ✅ | Messages formatés avec 4 options de réponse rapide |
| Activity log ✅ | Table + log dans 4 handlers (mail/drive/teams/memory) + conversations |
| Mémoire narrative ✅ | Table dossier_narratives, vectorisée, injection RAG dans prompt |
| Briefings réunions ✅ | Job 6h30, prépare briefing par événement via Haiku + narratives |

### ⚠️ REDESIGN NÉCESSAIRE : Rapport matinal (7-6)

Le heartbeat actuel (push WhatsApp systématique) ne correspond pas à la vision.

**Vision correcte :**
1. Raya PRÉPARE le rapport en arrière-plan (stocké, pas envoyé)
2. Raya envoie un PING léger : "Ton rapport est prêt" (fait sonner le téléphone)
3. L'utilisateur COMMANDE la livraison sous la forme qu'il veut
4. Le format du rapport est PERSONNALISABLE par l'utilisateur via la conversation
5. Raya APPREND le format préféré et le reproduit automatiquement

**Les canaux de livraison ne sont PAS codés en dur.** Ce sont des outils du
`tools_registry`. Aujourd'hui : chat, WhatsApp, vocal (ElevenLabs), mail (Outlook).
Demain : Telegram, SMS, Push PWA, ou tout autre canal ajouté par un développeur.
Raya ne propose que les canaux disponibles pour cet utilisateur.

**Le contenu du rapport est personnalisable.** L'utilisateur dit "ajoute la météo,
mes RDV, les factures Odoo". Raya stocke ces préférences comme des règles apprises
(pas du code). Chaque utilisateur a SON format.

**À FAIRE :** Refactorer `_job_heartbeat_morning` + `_build_morning_summary` :
- Stocker le rapport dans une table (ex: `daily_reports`) au lieu de l'envoyer
- Envoyer uniquement un ping notification
- Ajouter une commande "rapport" dans le chat pour livraison à la demande
- Ajouter les canaux de livraison comme outils dans tools_registry

## 3. PROCHAINE ÉTAPE
1. **Redesign heartbeat** → rapport à la demande, canaux dynamiques
2. **7-1 Multi-mailbox Gmail**
3. **Workflow intelligence** → pattern engine sur activity_log
4. **7-7 Monitoring + fallbacks**

## 4. Reprise
« Bonjour Opus. Projet Raya, Guillaume. On se tutoie, en français, vocabulaire Terminal, concis. Lis `docs/raya_session_state.md` puis `docs/raya_roadmap_v2.md` sur `per1gyom/couffrant-assistant` main via GitHub MCP. Règle d'or : aucune écriture sans mon ok. Reprends où on en était. »

## 5. RÈGLE
À chaque jalon, Opus met à jour ce fichier. Non négociable.

## 6. Variables Railway
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`
- `NOTIFICATION_PHONE_GUILLAUME=+33xxxxxxxxx`
