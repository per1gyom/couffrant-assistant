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
**PHASES 5 : TERMINÉES ✅** | **PHASE 7 JARVIS : 11 tâches ✅** (Sprint 1 terminé)

| Fait Phase 7 | Détail |
|---|---|
| urgency_model ✅ | Score 0-100, 4 étages, certitude, VIP boost |
| Shadow mode ✅ | Alertes [SHADOW] en chat |
| Notification prefs ✅ | Plages silencieuses, VIP, should_notify() |
| WhatsApp structuré ✅ | Options de réponse rapide |
| Activity log ✅ | Log dans 4 handlers + conversations |
| Mémoire narrative ✅ | dossier_narratives vectorisée, injection RAG |
| Briefings réunions ✅ | Job 6h30, Haiku + narratives |
| Rapport stocké + ping ✅ | daily_reports, ping léger, livraison à la demande |
| Workflow intelligence ✅ | Pattern engine lit activity_log |

## 3. PROCHAINE ÉTAPE (Sprint 2 — planning V3)

1. **7-1 Multi-mailbox Gmail** — OAuth2 + polling + pipeline webhook
2. **7-7 Monitoring + fallbacks** — alertes si scan inactif > 10min, fallback SMS
3. **7-8 Canal WhatsApp bidirectionnel** — recevoir les réponses, parser, exécuter

## 4. CHANTIERS IDENTIFIÉS (discussion Guillaume 12/04/2026 soir)

### Volet A — Outils de création (nouvelles capacités Raya)
Raya doit pouvoir PRODUIRE des livrables, pas juste informer.
Tous ces outils = nouveaux connecteurs dans `tools_registry`.

| Outil | Complexité | Technologie probable |
|---|---|---|
| Créer des fichiers Excel | Faible | openpyxl (Python) |
| Créer des PDF | Faible | reportlab ou weasyprint (Python) |
| Créer des visuels / images | Moyenne | DALL-E API ou Stable Diffusion |
| Modifier des images | Moyenne | Pillow + IA génération |
| Créer des posts LinkedIn (texte + visuel) | Moyenne | Template + génération |
| Publier directement sur LinkedIn | Haute | LinkedIn API (OAuth2) |
| Publier sur Instagram | Haute | Instagram Graph API |

Même principe que les autres outils : connecteur + tools_registry + description
fonctionnelle. Raya propose de créer un fichier quand c'est pertinent.
Exemple : "Prépare-moi un récap chantier Dupont en PDF" → Raya génère le PDF
depuis les données qu'elle a en mémoire (mails, narrative, Odoo).

### Volet B — Ergonomie / UI
Le site fonctionne mais peut être amélioré :

- **Design épuré** — simplifier, alléger, moderniser
- **Largeur du chat** — le texte est trop étroit, doit occuper plus de largeur
- **Responsive / zoom** — le layout doit s'adapter correctement à tous les zooms
- **UX globale** — à évaluer quand les features Jarvis seront testables

Chantier frontend (HTML/CSS/JS templates) indépendant du backend.
Peut être fait en parallèle sans bloquer Phase 7/8.

### Volet C — Application mobile (futur)
Objectif : Raya accessible depuis le téléphone.
Deux options à évaluer :
- **PWA** (Progressive Web App) — le plus rapide. L'app web actuelle devient
  installable. Le `sw.js` (service worker) existe déjà. Push notifications via PWA.
- **App native** (React Native / Flutter) — plus lourd, projet en soi. À évaluer
  uniquement si la PWA ne suffit pas (notifications fiables, accès micro pour vocal).

À planifier APRÈS la beta Charlotte (mi-juin). Pas prioritaire avant.

## 5. NOTES PRÉ-COMMERCIALISATION

### Raya et ses limites → redirection vers l'humain
- **Si collaborateur** → contacter l'admin de son tenant
- **Si admin/dirigeant** → contacter le support Raya
- `SUPPORT_EMAIL` existe dans `config.py`, étendre avec `SUPPORT_PHONE` + admin par tenant

## 6. Reprise
« Bonjour Opus. Projet Raya, Guillaume. On se tutoie, en français, vocabulaire Terminal, concis. Lis `docs/raya_session_state.md` puis `docs/raya_roadmap_v2.md` sur `per1gyom/couffrant-assistant` main via GitHub MCP. Règle d'or : aucune écriture sans mon ok. Reprends où on en était. »

## 7. RÈGLE
À chaque jalon, Opus met à jour ce fichier. Non négociable.

## 8. Variables Railway
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`
- `NOTIFICATION_PHONE_GUILLAUME=+33xxxxxxxxx`
- `SUPPORT_EMAIL` (existe déjà dans config.py)
