# Raya — État de session vivant

**Dernière mise à jour : 12/04/2026 soir** — Opus

---

## ⭐ ÂME DU PROJET
Raya = cerveau supplémentaire Jarvis pour dirigeant. 8 dimensions, 3 modes, supervision managériale. Voir `docs/raya_roadmap_v2.2.md` et commits précédents.

## 0. CONSIGNES
- **Opus = architecte, Sonnet = exécutant. Opus ne code PAS.**
- **Prompts directement dans le chat, entre barres de code.**
- **JAMAIS push_files pour du code Python.**
- **Aucune écriture sans ok explicite de Guillaume.**
- LLM-agnostic, tools-agnostic, channel-agnostic.

## 1. Stack
FastAPI Python 3.13, Railway, PostgreSQL+pgvector, Anthropic 3 tiers, OpenAI embeddings.
Repo `github.com/per1gyom/couffrant-assistant` main.

## 2. État
**PHASES 5 : TERMINÉES ✅** | **PHASE 7 JARVIS : 13 tâches ✅**

| Fait Phase 7 | Détail |
|---|---|
| urgency_model ✅ | Score 0-100, 4 étages, certitude, VIP boost |
| Shadow mode ✅ | Alertes [SHADOW] en chat, calibration 14j |
| Notification prefs ✅ | Plages silencieuses, VIP, should_notify() |
| WhatsApp structuré ✅ | send_whatsapp_structured() avec options |
| Activity log ✅ | Log dans 4 handlers + conversations |
| Mémoire narrative ✅ | dossier_narratives vectorisée, injection RAG |
| Briefings réunions ✅ | Job 6h30, Haiku + narratives |
| Rapport stocké + ping ✅ | daily_reports, ping léger, livraison à la demande |
| Livraison rapport ✅ | report_actions.py, injection prompt, marquage auto |
| Workflow intelligence ✅ | Pattern engine lit activity_log (type workflow) |
| **Gmail connector ✅** | OAuth2 + polling incrémental historyId |
| **Pipeline source-agnostic ✅** | process_incoming_mail() — Microsoft + Gmail même entonnoir |
| **Gmail polling job ✅** | IntervalTrigger 3min, SCHEDULER_GMAIL_ENABLED |

Sprint 1 ✅ + Sprint 2 (Gmail) ✅

## 3. PROCHAINE ÉTAPE

Reste Sprint 2 :
1. **7-7 Monitoring + fallbacks** — alertes si scan inactif > 10min, fallback SMS
2. **7-8 Canal WhatsApp bidirectionnel** — webhook Twilio entrant, parser, exécuter

Sprint 3-4 :
3. **7-4 Appel vocal sortant** — ElevenLabs + Twilio Voice
4. **Canaux dans tools_registry** — chat, WhatsApp, vocal, mail comme outils dynamiques

## 4. CHANTIERS IDENTIFIÉS (discussion Guillaume 12/04/2026)

### Volet A — Outils de création
Excel (openpyxl), PDF (reportlab), visuels/images (DALL-E), posts LinkedIn, publication LinkedIn/Instagram.

### Volet B — Ergonomie UI
Design épuré, largeur chat, responsive/zoom.

### Volet C — Application mobile (futur)
PWA (sw.js existe) ou app native. Après beta Charlotte.

## 5. NOTES PRÉ-COMMERCIALISATION
- Raya redirige vers admin/support quand elle a une limite
- `SUPPORT_EMAIL` existe dans config.py

## 6. Reprise
« Bonjour Opus. Projet Raya, Guillaume. On se tutoie, en français, vocabulaire Terminal, concis. Lis `docs/raya_session_state.md` puis `docs/raya_roadmap_v2.md` sur `per1gyom/couffrant-assistant` main via GitHub MCP. Règle d'or : aucune écriture sans mon ok. Reprends où on en était. »

## 7. Variables Railway
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`
- `NOTIFICATION_PHONE_GUILLAUME=+33xxxxxxxxx`
- `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `SCHEDULER_GMAIL_ENABLED=true`
- `SUPPORT_EMAIL`
