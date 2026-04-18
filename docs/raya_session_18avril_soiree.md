# Session du 18/04/2026 — SOIRÉE

Document séparé pour consigner la session du soir sans risque d'écraser
`docs/raya_session_state.md`. À intégrer plus tard si besoin.

## Contexte global

Session intensive de ~11h (de 8h à 19h30). 24 commits sur la journée.
Guillaume et Claude ont tracé le chantier Scanner Universel Odoo : plan
détaillé de 1142 lignes, 10 questions clés validées, 32 manifests générés
automatiquement, code des 4 premières phases.

## Documentation livrée aujourd'hui

- `docs/raya_scanner_universel_plan.md` (1142 lignes) — plan complet Scanner
- `docs/raya_bugs_et_securite_plan.md` (247 lignes) — bug tracking + sécurité
- `docs/raya_memory_architecture.md` — règle universelle 4 couches mémoire
- `docs/raya_session_18avril_soiree.md` — ce document

## Code Scanner Universel livré

Modules créés dans `app/scanner/` :
- `__init__.py` — package
- `orchestrator.py` — cycle de vie runs + `cleanup_stale_runs()`
- `adapter_odoo.py` — fetch paginé Odoo via XML-RPC
- `processor.py` — écriture graphe + vectorisation + chunks pgvector
- `manifest_generator.py` — 32 manifests auto-générés à partir des champs Odoo
- `runner.py` — worker background avec garde-fous anti-saturation
- `document_extractors.py` — Phase 6 PDF/DOCX/XLSX/Image (Claude Vision)

Nouvelles tables DB (via `app/database_migrations.py`) :
- `scanner_runs` — checkpointing des runs
- `connector_schemas` — manifests JSONB par modèle
- `vectorization_queue` — webhooks async (structure seulement, pas encore utilisé)

## UI admin ajoutée

Bumps cache-bust : `admin-panel.js` v=34 → v=38

Boutons ajoutés sur la carte Connexion Odoo :
- 🔍 Inventaire Odoo (717 modèles détectés, 186 non-vides)
- 📋 Manifests (32 manifests générés)
- 🚀 Scanner P1 (lance le scan avec polling 10s)

## Endpoints admin créés

- `POST /admin/scanner/run/start` — lance un scan
- `GET /admin/scanner/run/status` — statut temps réel
- `POST /admin/scanner/manifests/generate` — génère les 32 manifests
- `GET /admin/scanner/manifests` — liste les manifests
- `GET /admin/scanner/manifests/{model_name}` — détail manifest
- `PATCH /admin/scanner/manifests/{model_name}` — édite un manifest
- `POST /admin/scanner/purge` — purge données vectorisées (danger)
- `GET /admin/scanner/health` — statut global Scanner
- `GET /admin/scanner/db-size` — surveillance volume (% usage sur 5 Go)
- `GET /admin/scanner/debug/embed-test` — diagnostic OpenAI embed + pgvector
- `POST /admin/scanner/debug/extract-document` — test extraction fichier

## Bugs découverts et corrigés en séance

### Bug 1 — `_PooledConn` pas context manager (commit 428e26a)

15/32 manifests échouaient avec `'_PooledConn' object does not support the context manager protocol`. Ajout de `__enter__`/`__exit__` sur la classe dans `app/database.py`.

### Bug 2 — Colonne `content_text` vs `text_content` (commit 40891a6)

Scan P1 avait 0 chunks avec 1200 records traités. Diagnostic via endpoint `/admin/scanner/debug/embed-test` : OpenAI OK, embed OK, INSERT KO avec `column content_text does not exist`. Corrigé dans processor.py + super_admin_system.py.

### Bug 3 — Railway tue l'app pendant le scan (commit 440b824)

Scan intensif (CPU + réseau) → endpoint `/health` trop lent à répondre → Railway considère l'app "unhealthy" → restart → thread du scan tué. Fix : rate limit 100ms → 500ms, batch 100 → 50, cleanup runs fantômes au startup.

## Incident Railway Live Resize beta

Symptôme : volume PostgreSQL 1 Go saturé par product.template (133k records), Postgres crash-loop avec `No space left on device` sur `pg_wal/xlogtemp.33`.

Cause : Live Resize (beta) de Railway n'a pas étendu le filesystem du container après avoir étendu le volume sous-jacent. Bug confirmé officiellement (même issue résolue 6h plus tôt pour user `gil4business-commits`).

Résolution : ticket support Railway ouvert à 18h40, résolu par employé brody en 40 min avec expansion manuelle du filesystem + redéploiement Postgres.

Leçons :
- Live Resize beta Railway peut ne pas étendre le filesystem
- Les garde-fous MODEL_RECORD_LIMITS sont essentiels
- Endpoint `/admin/scanner/db-size` permet de surveiller avant que ça explose
- Support Railway répond en 30min-3h (bug déjà documenté = plus rapide)

## Garde-fous en place (commits 85659f9 + 440b824)

### MODEL_RECORD_LIMITS dans runner.py

- `product.template` : 5000 records au lieu de 133k
- `product.product` : 5000 records
- `product.supplierinfo` : 10000 au lieu de 124k
- `mail.message` : 10000 au lieu de 29k
- `mail.tracking.value` : 10000 au lieu de 22k
- `res.city` / `res.city.zip` : 0 (skip, géo référence seulement)

### Rate limiting plus doux

- Batch size : 50 records (au lieu de 100)
- Délai entre batches : 500ms (au lieu de 100ms)
- Scan plus lent (~45 min au lieu de 20 min) mais **ne tue plus l'app**

### cleanup_stale_runs au startup

Au redémarrage de l'app, les runs en statut "running" dont `updated_at > 10 min` sont marqués "error" automatiquement. Évite les runs fantômes.

## État Scanner P1 au moment de l'arrêt de session

3 runs fantômes en DB (status "running" mais threads morts) :
- Run 14:40:59 — bug text_content, 1600 records sans chunks
- Run 14:52:21 — fix text_content appliqué, 12000 records / 7975 chunks
- Run 17:53:04 — tué par Railway restart, 11800 records / 11800 chunks

Ces runs seront marqués "error" au prochain redéploiement Railway grâce à `cleanup_stale_runs()`.

Snapshot db-size (18h20) :
- Taille DB totale : 304 Mo / 5 Go (5.9% d'usage)
- `odoo_semantic_content` : 169 Mo (9464 chunks vectorisés)
- `semantic_graph_edges` : 69 Mo (154k arêtes)
- `semantic_graph_nodes` : 27 Mo (19k nœuds)

Les données persistent sur le volume, rien n'est perdu.

## 3 chantiers validés en backlog

### Chantier 1 — Finir Scanner Universel (~30h réparties)

- Phase 3 : relancer le scan P1 une dernière fois avant dodo pour validation
- Phase 4 : scan P2+P3 (~3h)
- Phase 5 : transversaux mail.message / tracking / attachments (~5h)
- Phase 6 : ✅ Extraction documents FAITE (commit b8378aa)
- Phase 7 : cas spéciaux Couffrant kits/tournées/templates (~4h)
- Phase 8 : dashboard intégrité visuel (~2h) — prochaine étape session
- Phase 9 : audit cron nocturne (~3h)
- Phase 10 : extension multi-tenant (~4h)

### Chantier 2 — Bug Tracking System (~8h30)

Architecture validée : table SQL `bugs` + bouton admin "📋 Générer prompt debug" + archivage mensuel automatique. Debug flow : Guillaume copie le markdown généré dans une conversation Claude sur claude.ai (pas d'API, pas de logiciel local). Auto-correction UNIQUEMENT sur actions outils Odoo, jamais sur le code Raya.

### Chantier 3 — Sécurité d'accès via Clerk (~17h internes + externe)

Solution retenue : Clerk (SaaS avec MFA intégré, gratuit jusqu'à 10k users). Phase A (9h) avant testeurs : migration auth + MFA admins + isolation tenant + chiffrement + rate limiting. Phase B (8h) pendant tests : logs audit + détection anomalies + backup + version essai. Phase C (externe) avant commercial : RGPD + pentest + cyber-assurance.

## Cartographie Odoo réelle de Guillaume

Stack : Odoo 16 Community + module OpenFire (éditeur FR BTP/PV)
Total : 717 modèles disponibles, 186 non-vides

### 16 modèles P1 (cœur métier)

res.partner(1226), crm.lead(139), sale.order(310), sale.order.line(3743), sale.order.template(9), sale.order.template.line(119), calendar.event(1162), product.template(133112), of.product.pack.lines(5518) = KITS, product.pack.line(715), mail.message(29139), mail.tracking.value(22850), of.planning.tour(5373), of.planning.tour.line(2753), of.survey.answers(5320), of.survey.user_input.line(687)

### 16 modèles P2 (support métier)

account.move(408), account.move.line(2450), account.payment(175), of.sale.payment.schedule(6203), of.account.move.payment.schedule(434), of.invoice.product.pack.lines(1340), stock.picking(206), of.image(1577), of.custom.document(3), of.custom.document.field(56), of.service.request(2), of.planning.intervention.template(25), of.planning.intervention.section(8), of.planning.task(31), hr.employee(7), mail.activity(107)

## Commits du 18/04 (24 au total)

Matin/après-midi (fixes mémoire + plan Scanner) :
4808fe8, 78d9367, 340ada8, d081530, 4be4053, 89865e4, 28be470, 47f3823, 0f6dfec, 73945f5, 5af57c1, 6edfb35, aa6fc09

Soirée (implémentation Scanner) :
- `fbab358` — Phase 1 Fondations Scanner
- `1e31a4c` — Phase 2 Manifest generator
- `428e26a` — fix _PooledConn context manager
- `6f72c7f` — Phase 3 Runner background
- `c54ce7d` — endpoint diagnostic embed-test
- `40891a6` — fix text_content column name
- `85659f9` — MODEL_RECORD_LIMITS + /db-size
- `b0cea2f` + `6f350a4` + `a246873` — doc Bugs+Sécurité (3 versions, finale 247L)
- `440b824` — ralentissement scanner (500ms/batch + cleanup stale runs)
- `b8378aa` — Phase 6 Extraction PDF/DOCX/XLSX/Image via Claude Vision

## Prochaines actions concrètes

1. **Tout de suite** : Phase 8 Dashboard intégrité visuel (~2h de code)
2. **Avant dodo** : relance Scanner P1 (tourne en arrière-plan toute la nuit si besoin)
3. **Demain au réveil** : vérifier résultat scan via dashboard intégrité
4. **Semaine prochaine** : Phases 4+5+7 Scanner
5. **Avant early adopters** : Sécurité Phase A (Clerk + MFA + isolation)
6. **Dès les premiers bugs** : activer le Bug Tracking System

## Règles impératives (rappel pour reprise de session)

- `/admin/panel` = super admin / `/tenant/panel` = tenant admin
- Routes admin dans `app/routes/admin/`
- JAMAIS supprimer `async function init()` dans `chat-main.js`
- TOUJOURS bumper `v=` lors modif JS/CSS (actuel v=38)
- OpenFire = Odoo (un seul accès)
- Ton Guillaume : vérité d'abord, politesse ensuite, tutoiement, français
- Raya JAMAIS connectée à son propre code (dangereux)
- Claude doit éviter le terminal pour Guillaume (préférer interfaces UI)

## Notes importantes sur les colonnes DB

- `app/database.py` → fonction `get_pg_conn` (pas `get_db_connection`)
- `app/embedding.py` → fonction `embed` (pas `embed_text`)
- `odoo_semantic_content` → colonne `text_content` (pas `content_text`)
- `app/semantic_graph.py` → paramètre `node_properties` (pas `properties`)
</content>
<mode>rewrite</mode>