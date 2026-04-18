

---

## 🗓️ SESSION 18/04/2026 SOIRÉE — Scanner Universel + Incident Railway

### Contexte de la session
Session intensive de ~11h (de 8h à 19h). 22 commits au total sur la journée.
Guillaume et Claude ont tracé le chantier Scanner Universel Odoo de A à Z :
plan détaillé de 1142 lignes, 10 questions clés validées, 32 manifests
générés automatiquement, code des 4 premières phases.

### Ce qui a été livré

**Documentation (3 documents majeurs)** :
- `docs/raya_scanner_universel_plan.md` — 1142 lignes, plan complet Scanner
- `docs/raya_bugs_et_securite_plan.md` — 247 lignes, bug tracking + sécurité
- `docs/raya_memory_architecture.md` — règle universelle 4 couches mémoire

**Code Scanner Universel** :
- `app/scanner/__init__.py` — package
- `app/scanner/orchestrator.py` — cycle de vie des runs + cleanup_stale_runs
- `app/scanner/adapter_odoo.py` — fetch paginé Odoo
- `app/scanner/processor.py` — écriture graphe + vectorisation
- `app/scanner/manifest_generator.py` — 32 manifests auto-générés
- `app/scanner/runner.py` — worker background avec garde-fous
- `app/scanner/document_extractors.py` — Phase 6 PDF/DOCX/XLSX/Image
- `app/database_migrations.py` — 3 nouvelles tables scanner

**UI admin** (bumps v=34 → v=38) :
- 🔍 Inventaire Odoo (717 modèles détectés, 186 non-vides)
- 📋 Manifests (32 manifests générés)
- 🚀 Scanner P1 (en attente relance finale)

**Endpoints ajoutés** :
- `POST /admin/scanner/run/start` — lance un scan
- `GET /admin/scanner/run/status` — statut temps réel
- `POST /admin/scanner/manifests/generate`
- `GET/PATCH /admin/scanner/manifests[/{model}]`
- `POST /admin/scanner/purge`
- `GET /admin/scanner/health`
- `GET /admin/scanner/db-size` — surveillance volume
- `GET /admin/scanner/debug/embed-test` — diagnostic embedding
- `POST /admin/scanner/debug/extract-document` — test extraction fichier

### Bugs découverts et corrigés en séance

**Bug 1 — `_PooledConn` pas context manager** (commit 428e26a)
15/32 manifests échouaient avec `'_PooledConn' object does not support the context manager protocol`. Ajout de `__enter__`/`__exit__` sur la classe dans `app/database.py`.

**Bug 2 — Colonne `content_text` vs `text_content`** (commit 40891a6)
Scan P1 avait 0 chunks avec 1200 records traités. Diagnostic via endpoint `/admin/scanner/debug/embed-test` : OpenAI OK, embed OK, INSERT KO avec `column content_text does not exist`. Corrigé dans processor.py + super_admin_system.py.

**Bug 3 — Railway tue l'app pendant le scan** (commit 440b824)
Scan intensif (CPU + réseau) → endpoint `/health` trop lent à répondre → Railway considère l'app "unhealthy" → restart → thread du scan tué. Fix : rate limit 100ms → 500ms, batch 100 → 50, cleanup runs fantômes au startup.

### Incident Railway (bug infrastructure Live Resize beta)

**Symptôme** : volume PostgreSQL 1 Go saturé par product.template (133k records), Postgres crash-loop avec `No space left on device` sur `pg_wal/xlogtemp.33`.

**Cause** : Live Resize (beta) de Railway n'a pas étendu le filesystem du container après avoir étendu le volume sous-jacent. Bug confirmé officiellement par Railway (même issue résolue 6h plus tôt pour user `gil4business-commits`).

**Résolution** : ticket support Railway ouvert à 18h40, résolu par employé brody en 40 min avec expansion manuelle du filesystem + redéploiement Postgres.

**Leçons tirées** :
1. Live Resize beta Railway peut ne pas étendre le filesystem → toujours vérifier après resize
2. Les garde-fous MODEL_RECORD_LIMITS sont essentiels pour éviter re-saturation
3. Endpoint `/admin/scanner/db-size` permet de surveiller avant que ça explose
4. En cas de bug infra Railway, support répond en 30min-3h (bug déjà documenté = plus rapide)

### 3 chantiers validés en backlog (par ordre de priorité)

**Chantier 1 — Finir Scanner Universel** (~30h réparties)
- Phase 3 : relancer le scan P1 ce soir pour validation finale
- Phase 4 : scan P2+P3 (~3h)
- Phase 5 : transversaux mail.message / tracking / attachments (~5h)
- Phase 6 : ✅ Extraction documents FAITE (commit b8378aa)
- Phase 7 : cas spéciaux Couffrant kits/tournées/templates (~4h)
- Phase 8 : dashboard intégrité (~5h) — **prochaine étape session**
- Phase 9 : audit cron nocturne (~3h)
- Phase 10 : extension multi-tenant (~4h)

**Chantier 2 — Bug Tracking System** (~8h30)
Architecture validée : table SQL `bugs` + bouton admin "📋 Générer prompt debug" + archivage mensuel automatique. Debug flow : Guillaume copie le markdown généré dans une conversation Claude sur claude.ai (pas d'API, pas de logiciel local). Auto-correction UNIQUEMENT sur actions outils Odoo, jamais sur le code Raya.

**Chantier 3 — Sécurité d'accès via Clerk** (~17h internes + externe)
Solution retenue : Clerk (SaaS avec MFA intégré, gratuit jusqu'à 10k users, utilisé par Notion/Airbnb/Stripe). Phase A (9h) avant testeurs : migration auth + MFA admins + isolation tenant + chiffrement + rate limiting. Phase B (8h) pendant tests : logs audit + détection anomalies + backup + version essai. Phase C (externe) avant commercial : RGPD + pentest + cyber-assurance.

### État du Scanner P1 au moment de l'arrêt de session

**3 runs fantômes en DB** (status "running" mais threads morts) :
- Run 14:40:59 — bug text_content, 1600 records sans chunks
- Run 14:52:21 — fix text_content appliqué, 12000 records avec 7975 chunks
- Run 17:53:04 — tué par Railway restart, 11800 records avec 11800 chunks

Ces runs seront automatiquement marqués "error" au prochain redéploiement Railway grâce au `cleanup_stale_runs()` ajouté au startup (commit 440b824).

**Données en base (snapshot db-size)** :
- Taille DB totale : 304 Mo / 5 Go (5.9% d'usage)
- `odoo_semantic_content` : 169 Mo (9464 chunks vectorisés)
- `semantic_graph_edges` : 69 Mo (154k arêtes)
- `semantic_graph_nodes` : 27 Mo (19k nœuds)
- Tables Scanner (runs + schemas + queue) : 0.4 Mo

Données conservées même après redémarrage (PostgreSQL persiste sur le volume).

### Cartographie Odoo réelle de Guillaume (découverte pendant la session)

**Stack** : Odoo 16 Community + module OpenFire (éditeur FR BTP/PV)
**Total** : 717 modèles disponibles, 186 non-vides

**16 modèles P1 (coeur métier)** :
res.partner(1226), crm.lead(139), sale.order(310), sale.order.line(3743), sale.order.template(9), sale.order.template.line(119), calendar.event(1162), product.template(133112 ⚠️), of.product.pack.lines(5518) = KITS, product.pack.line(715), mail.message(29139), mail.tracking.value(22850), of.planning.tour(5373), of.planning.tour.line(2753), of.survey.answers(5320), of.survey.user_input.line(687)

**16 modèles P2 (support métier)** :
account.move(408), account.move.line(2450), account.payment(175), of.sale.payment.schedule(6203), of.account.move.payment.schedule(434), of.invoice.product.pack.lines(1340), stock.picking(206), of.image(1577), of.custom.document(3), of.custom.document.field(56), of.service.request(2), of.planning.intervention.template(25), of.planning.intervention.section(8), of.planning.task(31), hr.employee(7), mail.activity(107)

### Session en cours de continuation

Au moment où ces lignes sont écrites, on est encore en session :
- Option B (cette mise à jour) en cours
- Option A (Phase 8 — Dashboard intégrité visuel) à suivre
- Option D (relance Scanner P1) avant dodo

### Prochaines actions concrètes

1. **Tout de suite** : Phase 8 Dashboard intégrité visuel (~2h de code)
2. **Avant dodo** : relance Scanner P1 (fonctionne en arrière-plan toute la nuit si besoin, garde-fous actifs)
3. **Demain au réveil** : vérifier résultat scan via dashboard intégrité
4. **Semaine prochaine** : Phases 4+5+7 Scanner (P2+P3 + transversaux + cas spéciaux)
5. **Avant early adopters** : Sécurité Phase A (Clerk + MFA + isolation)
6. **Dès les premiers bugs** : activer le Bug Tracking System
</content>
<mode>append</mode>