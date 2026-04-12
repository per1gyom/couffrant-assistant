# Raya — État de session vivant

**Dernière mise à jour : 12/04/2026 soir** — Opus

---

## ⭐ ÂME DU PROJET
Raya = cerveau supplémentaire pour dirigeant. 8 dimensions, 3 modes, supervision managériale. LLM-agnostic, tools-agnostic, channel-agnostic. Voir `docs/raya_roadmap_v2.2.md`.

## 0. CONSIGNES
- **Opus = architecte, Sonnet = exécutant. Opus ne code PAS.**
- **Prompts directement dans le chat, entre barres de code.**
- **JAMAIS push_files pour du code Python.**
- **Aucune écriture sans ok explicite de Guillaume.**
- Raya ne connait PAS le mot "Jarvis". Elle est Raya.

## 1. Stack
FastAPI Python 3.13, Railway, PostgreSQL+pgvector, Anthropic 3 tiers, OpenAI embeddings.
Repo `github.com/per1gyom/couffrant-assistant` main.

## 2. État
**PHASES 5 ✅** | **PHASE 7 : 13 tâches ✅** | **Security timeout ✅**

Phase 7 fait : urgency_model, shadow mode, notification prefs, WhatsApp structuré, activity log, mémoire narrative, briefings réunions, rapport stocké+ping+livraison, workflow intelligence, Gmail connector+pipeline+polling.
Security : inactivité 2h, cookie max 24h.

## 3. PROMPTS PRÊTS (à envoyer à Sonnet)

3 prompts en attente dans la conversation :
1. **FIX-SPEED-JARVIS** — vitesse lecture ElevenLabs dynamique + purge Jarvis
2. **7-7** — Monitoring système + fallback SMS
3. **7-8** — WhatsApp bidirectionnel (webhook entrant + commandes)

## 4. APRÈS LES PROMPTS EN ATTENTE

### Phase 8 — Intelligence avancée (validée par Guillaume)

| Tâche | Effort | Description |
|---|---|---|
| 8-CYCLES | Faible (0.5 session) | Rythme business dans pattern engine (fin de mois, trimestre) |
| 8-TON | Faible (0.5 session) | Apprentissage ton/personnalité par utilisateur |
| 8-ANOMALIES | Moyen (1 session) | Détection anomalies cross-outils (Odoo vs mails) |
| 8-OBSERVE | Moyen (2-3 sessions) | Observation externe (scan changements Drive/mails/cal hors Raya) |
| 8-COLLAB | Haute (3-4 sessions) | Collaboration inter-Rayas (événements tenant partagés) |

### Volet A — Outils de création
Excel (openpyxl), PDF (reportlab), images (DALL-E + Pillow), posts LinkedIn, publication LinkedIn/Instagram.

### Volet B — Ergonomie UI
Design épuré, largeur chat, responsive/zoom.

### Volet C — Application mobile
PWA ou app native. Après beta Charlotte.

### Web search
Prompt WEB-SEARCH rédigé (dans la conversation). Ajoute l'accès internet à Raya via l'outil web_search Anthropic.

## 5. AUDIT PERFORMANCE (à planifier)

Le temps de réponse de Raya est correct mais peut être optimisé.
Planifier un audit dédié pour :
- Profiler les appels réseau parallèles (étape 2 de _raya_core)
- Mesurer le temps de chaque bloc du prompt (hot_summary, RAG, narratives, patterns)
- Identifier les requêtes SQL lentes (EXPLAIN ANALYZE sur les plus fréquentes)
- Évaluer si certaines injections prompt peuvent être cachées plus agressivement
- Tester la réduction du max_tokens si la réponse est simple
- Benchmark avant/après chaque optimisation

Objectif : réduire le temps de réponse SANS perdre en qualité. Ne pas sacrifier la précision contextuelle pour la vitesse.

## 6. NOTES PRÉ-COMMERCIALISATION
- Raya redirige vers admin/support quand elle a une limite
- `SUPPORT_EMAIL` existe dans config.py

## 7. Reprise
« Bonjour Opus. Projet Raya, Guillaume. On se tutoie, en français, vocabulaire Terminal, concis. Lis `docs/raya_session_state.md` puis `docs/raya_roadmap_v2.md` sur `per1gyom/couffrant-assistant` main via GitHub MCP. Règle d'or : aucune écriture sans mon ok. Reprends où on en était. »

## 8. Variables Railway
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`
- `NOTIFICATION_PHONE_GUILLAUME=+33xxxxxxxxx`
- `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `SCHEDULER_GMAIL_ENABLED=true`
- `RAYA_WEB_SEARCH_ENABLED=true`
- `ELEVENLABS_SPEED=1.2` (configurable)
- `SUPPORT_EMAIL`
