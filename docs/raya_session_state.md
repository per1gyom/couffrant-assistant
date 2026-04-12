# Raya — État de session vivant

**Dernière mise à jour : 12/04/2026 soir** — Opus

---

## ⭐ ÂME DU PROJET — LIRE EN PREMIER

(Voir sections complètes dans les versions précédentes de ce fichier — la vision,
les 8 dimensions, les 3 modes d'utilisation, la supervision managériale.
Le prochain Opus doit lire l'historique git de ce fichier si ces sections manquent.)

Résumé : Raya = cerveau supplémentaire Jarvis pour dirigeant. Vision transversale
multi-sociétés. Intelligence de workflow (séquences, oublis, améliorations).
Mémoire narrative des dossiers. Préparation anticipée. Intelligence d'équipe.
3 modes : dirigeant multi-tenant / collaborateur pro / collaborateur perso (avantage en nature).
Supervision managériale (métriques oui, contenu conversations jamais).

---

## 0. CONSIGNES
- Vocabulaire : « Terminal ». Concis. Langage simple.
- **Règle d'or : aucune écriture sans « ok vas-y » explicite.**
- **Prompts pour Sonnet : directement dans le chat, entre barres de code.**
- **Opus ne code PAS, ne pousse PAS de commits. Sonnet exécute.**
- **JAMAIS push_files pour du code Python** (corrompt les \\n).

## 1. Stack
FastAPI Python 3.13, Railway, PostgreSQL+pgvector, Anthropic 3 tiers, OpenAI embeddings.
Repo `github.com/per1gyom/couffrant-assistant` main.

## 2. État 12/04/2026 soir
**PHASES 5 : TERMINÉES ✅** | **PHASE 7 EN COURS (3/10+)**

| Fait Phase 7 | Détail |
|---|---|
| **urgency_model.py ✅** | Score 0-100, 4 étages (règles→contacts→patterns→Haiku), certitude, niveaux silent/normal/important/critical |
| **Shadow mode ✅** | shadow_mode + shadow_mode_until sur users, alertes [SHADOW] dans le chat, pas de WhatsApp |
| **Heartbeat matinal ✅** | Job APScheduler 7h00, résumé WhatsApp (mails/alertes/stats), preuve de vie |

Reste Phase 7 :
- 7-1 Multi-mailbox (Gmail)
- 7-3 WhatsApp structuré (options de réponse)
- 7-5 Préférences de sollicitation
- 7-NEW Activity log + workflow patterns
- 7-NEW Mémoire narrative des dossiers
- 7-NEW Préparation anticipée (briefings avant réunions)
- 7-4 Appel vocal (futur)
- 7-7 Monitoring + fallbacks (futur)
- 7-8 Réponse par WhatsApp (futur)

## 3. PROCHAINE ÉTAPE

1. **7-5 Préférences de sollicitation** — plages horaires, VIP, seuils personnalisés
2. **7-3 WhatsApp structuré** — messages avec résumé + boutons de réponse rapide
3. **7-NEW Activity log** — table + logging des actions pour intelligence de workflow

## 4. Reprise
« Bonjour Opus. Projet Raya, Guillaume. On se tutoie, en français, vocabulaire Terminal, concis. Lis `docs/raya_session_state.md` puis `docs/raya_roadmap_v2.md` sur `per1gyom/couffrant-assistant` main via GitHub MCP. Règle d'or : aucune écriture sans mon ok. Reprends où on en était. »

## 5. Variables Railway
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`
- `NOTIFICATION_PHONE_GUILLAUME=+33xxxxxxxxx`
