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

### ⚠️ CORRECTION IMPORTANTE : Rapport matinal (discussion Guillaume 12/04/2026 soir)

Le heartbeat matinal actuel (job 7h00 → WhatsApp systématique) est FAUX.
Guillaume veut un système beaucoup plus intelligent :

**Le rapport n'est pas ENVOYÉ, il est PRÉPARÉ et DISPONIBLE.**

Le workflow correct :
1. Raya PRÉPARE le rapport en arrière-plan (job scheduler, comme aujourd'hui)
2. Raya envoie un SIMPLE PING : "Ton rapport matinal est prêt" (notification légère)
3. L'UTILISATEUR DÉCIDE de la suite :
   - "Lis-le moi" → ElevenLabs à l'oral (séquence par séquence OU tout d'un coup)
   - "Envoie-le dans le chat" → texte dans l'interface
   - "Envoie-le par mail" → mail
   - "Envoie-le sur la messagerie" → WhatsApp/Telegram
   - Silence → le rapport reste disponible, pas de relance

**Le rapport est PERSONNALISABLE :**
- L'utilisateur dit "Ajoute la météo, mes RDV, un point sur les factures Odoo"
- Raya apprend le format préféré et le reproduit automatiquement
- L'utilisateur peut modifier quand il veut : "Enlève la météo, ajoute le solde"
- Chaque utilisateur a SON format de rapport

**Canal de notification :**
- Idéalement une app de messagerie qui fait sonner le téléphone (Twilio WhatsApp Business / Telegram bot)
- Le ping dit juste "rapport prêt", pas le contenu
- L'utilisateur commande la livraison du rapport par voix ou texte

**À FAIRE :** Redesigner le heartbeat (7-6) pour correspondre à cette vision.
Le code actuel dans scheduler.py (_job_heartbeat_morning + _build_morning_summary)
doit être refactoré : préparer + stocker le rapport, envoyer seulement un ping,
attendre la commande utilisateur pour livrer sous la forme choisie.

## 3. PROCHAINE ÉTAPE
1. **Redesign heartbeat** → rapport à la demande personnalisable
2. **7-1 Multi-mailbox Gmail** → couvrir toutes les boîtes
3. **Workflow intelligence** → étendre le pattern engine sur l'activity_log
4. **7-7 Monitoring + fallbacks** → fiabilité absolue

## 4. Reprise
« Bonjour Opus. Projet Raya, Guillaume. On se tutoie, en français, vocabulaire Terminal, concis. Lis `docs/raya_session_state.md` puis `docs/raya_roadmap_v2.md` sur `per1gyom/couffrant-assistant` main via GitHub MCP. Règle d'or : aucune écriture sans mon ok. Reprends où on en était. »

## 5. RÈGLE
À chaque jalon, Opus met à jour ce fichier. Non négociable.

## 6. Variables Railway
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`
- `NOTIFICATION_PHONE_GUILLAUME=+33xxxxxxxxx`
