# Onboarding nouveau tenant Raya
**Document de référence pour l'ajout d'un nouveau tenant.**
Rédigé après la Phase 2 (multi-tenant + couche LLM).

---

## Contexte

Raya supporte maintenant plusieurs tenants en parallèle avec une isolation stricte des données. Chaque tenant a :
- Ses propres règles dans `aria_rules` (scopées par `tenant_id`)
- Ses propres insights dans `aria_insights`
- Ses propres mails dans `mail_memory`
- Son propre profil de seeding (catégories, comportement)

Le premier tenant beta supplémentaire prévu : **l'entreprise de la femme de Guillaume** (organisation d'événements).

---

## Étape 1 — Créer le tenant en base

Se connecter à la PG Railway et exécuter :

```sql
-- Adapter les valeurs selon le cas
INSERT INTO tenants (id, name, settings)
VALUES (
  'evenements_perrin',
  'Événements Perrin',
  '{"email_provider": "microsoft", "metier": "organisation_evenements"}'
)
ON CONFLICT (id) DO NOTHING;
```

Vérifier :
```sql
SELECT * FROM tenants;
-- Doit afficher deux lignes : couffrant_solar et evenements_perrin
```

---

## Étape 2 — Créer le compte utilisateur

Via le panel admin Railway (`/admin/panel`) ou en SQL :

```sql
-- Remplacer 'HASH_ICI' par le bcrypt du mot de passe choisi
-- Générer le hash : python -c "import bcrypt; print(bcrypt.hashpw(b'motdepasse', bcrypt.gensalt()).decode())"

INSERT INTO users (username, password_hash, email, scope, tenant_id)
VALUES (
  'sophie',           -- à adapter
  'HASH_ICI',
  'sophie@email.com', -- à adapter
  'user',
  'evenements_perrin'
)
ON CONFLICT (username) DO NOTHING;
```

---

## Étape 3 — Seeder les règles initiales

Via la console Python Railway ou un endpoint admin dédié :

```python
from app.seeding import seed_tenant, is_tenant_seeded

if not is_tenant_seeded('sophie'):
    counts = seed_tenant('evenements_perrin', 'sophie', profile='event_planner')
    print(f"Seeding terminé : {counts}")
else:
    print("Déjà seedé")
```

Résultat attendu :
```
Seeding terminé : {
  'categories_mail': 8,
  'regroupement': 5,
  'tri_mails': 5,
  'comportement': 3,
  'memoire': 3
}
```

Vérifier en base :
```sql
SELECT category, COUNT(*) FROM aria_rules
WHERE username = 'sophie' AND source = 'seed'
GROUP BY category;
```

---

## Étape 4 — Connecter Microsoft 365

Sophie se connecte via `/login` avec son compte Microsoft 365.
Le flow OAuth standard stocke son token dans `oauth_tokens` avec `username='sophie'` et `tenant_id='evenements_perrin'`.

Vérifier après connexion :
```sql
SELECT username, provider, expires_at
FROM oauth_tokens WHERE username = 'sophie';
```

---

## Étape 5 — Première session de test

Ouvrir le chat en tant que Sophie et valider :

1. **Raya se présente** — "Tu ne connais pas encore Sophie. Commence à observer et mémoriser."
2. **Demander** : "Montre-moi mes catégories de mail" → Raya doit citer : client, prestataire, lieu, logistique, commercial, interne, notification, autre
3. **Demander** : "Liste mes derniers mails" → doit afficher les mails de Sophie (pas ceux de Guillaume)
4. **Vérifier l'isolation** : se reconnecter en tant que Guillaume et demander les règles → les règles `event_planner` de Sophie ne doivent pas apparaître

---

## Étape 6 — Vérifications post-onboarding

```sql
-- Isolation : aucune règle d'un tenant ne doit apparaître dans l'autre
SELECT tenant_id, username, COUNT(*) as nb_regles
FROM aria_rules
WHERE source = 'seed'
GROUP BY tenant_id, username;
-- Attendu : 2 lignes, une par tenant

-- Coûts LLM (après quelques conversations)
SELECT tenant_id, SUM(input_tokens + output_tokens) as total_tokens
FROM llm_usage
GROUP BY tenant_id;
```

---

## Checklist de déploiement Phase 2 complète

- [ ] Railway redémarre sans erreur (`Application startup complete`)
- [ ] Migrations passent dans les logs (`[Migration] Skip` pour les déjà faites, pas d'erreurs)
- [ ] Table `llm_usage` créée et se remplit après une conversation Raya
- [ ] Couffrant : Raya répond normalement, les règles seedées sont visibles (`/admin/panel`)
- [ ] Tests Phase 0 passent : `pytest tests/test_phase0_blockers.py -v`
- [ ] Tests Phase 2 passent : `pytest tests/test_phase2_isolation.py -v`
- [ ] Nouveau tenant créé (étapes 1-4 ci-dessus)
- [ ] Première session Sophie validée (étape 5)

---

## Rollback si problème

```bash
# Revert Git
git revert <sha> && git push

# Supprimer le tenant de test si nécessaire
DELETE FROM users WHERE username = 'sophie';
DELETE FROM tenants WHERE id = 'evenements_perrin';
DELETE FROM aria_rules WHERE username = 'sophie';
```

---

## Notes pour la Phase 3

Une fois ce déploiement stable depuis 2-3 jours d'usage réel avec les deux tenants, les prochaines étapes (document `raya_roadmap_phase3_et_au_dela.md`) sont :

- **Phase 3** — Tools Framework : système de tools modulaires pour les features métier custom (devis, documents Enedis, analyse qualité PV pour Guillaume ; coordination prestataires, timelines événements pour Sophie)
- **Phase 4** — MCP : intégration Model Context Protocol pour connecter des sources externes
- **Phase 5+** — Skills métier : features avancées propres à chaque secteur
