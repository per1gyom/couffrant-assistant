# Raya — État de session vivant

**Dernière mise à jour : 12/04/2026 soir** — Opus

---

## ⭐ ÂME DU PROJET
Raya = cerveau supplémentaire Jarvis pour dirigeant. 8 dimensions (compréhension cumulative, vision transversale, intelligence workflow, mémoire narrative, préparation anticipée, intelligence d'équipe, rythme business, méta-apprentissage). 3 modes (dirigeant multi-tenant / collaborateur pro / collaborateur perso avantage en nature). Supervision managériale (métriques oui, contenu conversations jamais). Voir commits précédents pour le détail complet de la vision.

## 0. CONSIGNES
- **Opus = architecte, Sonnet = exécutant. Opus ne code PAS.**
- **Prompts directement dans le chat, entre barres de code.**
- **JAMAIS push_files pour du code Python.**
- **Aucune écriture sans ok explicite de Guillaume.**

## 1. Stack
FastAPI Python 3.13, Railway, PostgreSQL+pgvector, Anthropic 3 tiers, OpenAI embeddings.
Repo `github.com/per1gyom/couffrant-assistant` main.

## 2. État
**PHASES 5 : TERMINÉES ✅** | **PHASE 7 EN COURS (6/10+)**

| Fait Phase 7 | Détail |
|---|---|
| urgency_model ✅ | Score 0-100, 4 étages, certitude, niveaux |
| Shadow mode ✅ | Alertes [SHADOW] en chat, pas de WhatsApp tant qu'actif |
| Heartbeat matinal ✅ | Job 7h00, résumé WhatsApp quotidien |
| Notification prefs ✅ | Plages silencieuses, VIP emails/domaines, boost urgence, calendar_aware |
| WhatsApp structuré ✅ | Messages formatés avec 4 options de réponse rapide |
| Activity log ✅ | Table + log dans 4 handlers (mail/drive/teams/memory) + conversations |

## 3. PROCHAINE ÉTAPE
- 7-NAR : Mémoire narrative des dossiers
- 7-BRIEF : Préparation anticipée (briefings avant réunions)
- 7-1 : Multi-mailbox Gmail (infrastructure)

## 4. Reprise
« Bonjour Opus. Projet Raya, Guillaume. On se tutoie, en français, vocabulaire Terminal, concis. Lis `docs/raya_session_state.md` puis `docs/raya_roadmap_v2.md` sur `per1gyom/couffrant-assistant` main via GitHub MCP. Règle d'or : aucune écriture sans mon ok. Reprends où on en était. »
