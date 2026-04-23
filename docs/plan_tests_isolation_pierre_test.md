# Plan tests non-régression isolation — user pierre_test

**Objectif** : Valider que l'isolation user+tenant fonctionne bien après
les 14 commits de correction du 24/04.

**Contexte** : Pierre existe déjà dans Couffrant Solar (user réel). On
utilise un user fictif `pierre_test` pour tester sans polluer la base
de Pierre le vrai.

---

## Phase A — Setup initial

### 1. Créer pierre_test en DB

```sql
INSERT INTO users (username, password_hash, email, tenant_id, scope, created_at)
VALUES (
  'pierre_test',
  -- Mot de passe à changer après création via /admin
  '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewKyO5zDhJzXmXHS',
  'pierre_test@couffrant-solar.fr',
  'couffrant_solar',
  'user',
  NOW()
);

-- Lier au tenant via user_tenant_access
INSERT INTO user_tenant_access (username, tenant_id, role)
VALUES ('pierre_test', 'couffrant_solar', 'user')
ON CONFLICT DO NOTHING;
```

### 2. Semer quelques données propres à pierre_test

```sql
-- Une règle personnelle
INSERT INTO aria_rules (username, tenant_id, category, rule, confidence,
                        reinforcements, active, source)
VALUES ('pierre_test', 'couffrant_solar', 'style',
        'Pierre utilise le vouvoiement systematique avec les clients',
        0.8, 3, true, 'test');

-- Une conversation
INSERT INTO aria_memory (username, tenant_id, user_input, aria_response,
                         archived, created_at)
VALUES ('pierre_test', 'couffrant_solar', 'test isolation',
        'Reponse test isolation pierre_test', false, NOW());
```

---

## Phase B — Tests négatifs (ce qui NE doit PAS fuir)

### Test 1 : pierre_test ne voit pas les règles de guillaume

```sql
-- Attendu : 0 ligne (pierre_test ne doit PAS voir les 141 regles de guillaume)
SELECT COUNT(*) FROM aria_rules
WHERE username = 'pierre_test'
  AND tenant_id = 'couffrant_solar'
  AND rule LIKE '%Couffrant%';

-- Attendu : Les regles de guillaume sont bien rattachees a lui
SELECT COUNT(*) FROM aria_rules
WHERE username = 'guillaume'
  AND tenant_id = 'couffrant_solar';
```

### Test 2 : pierre_test ne voit pas les mails de guillaume

```sql
-- Attendu : 0 ligne
SELECT COUNT(*) FROM mail_memory
WHERE username = 'pierre_test';

-- Attendu : les mails guillaume sont la
SELECT COUNT(*) FROM mail_memory
WHERE username = 'guillaume';
```

### Test 3 : pierre_test ne voit pas les conversations de guillaume

```sql
-- Attendu : 1 ligne (la conversation de seed ci-dessus)
SELECT COUNT(*) FROM aria_memory
WHERE username = 'pierre_test'
  AND tenant_id = 'couffrant_solar';
```

---

## Phase C — Tests positifs (ce qui DOIT être partagé)

### Test 4 : pierre_test voit les contacts Odoo du tenant

```sql
-- Attendu : même COUNT que guillaume (donnees partagees tenant)
SELECT COUNT(*) FROM aria_contacts
WHERE tenant_id = 'couffrant_solar';

-- Attendu : idem pour les donnees Odoo semantic
SELECT COUNT(*) FROM odoo_semantic_content
WHERE tenant_id = 'couffrant_solar';
```

### Test 5 : Les deux users voient les mêmes connecteurs du tenant

```sql
-- tenant_connections : partage par tenant
SELECT COUNT(*) FROM tenant_connections
WHERE tenant_id = 'couffrant_solar';

-- drive_folders : partage par tenant
SELECT COUNT(*) FROM drive_folders
WHERE tenant_id = 'couffrant_solar';
```

---

## Phase D — Tests fonctionnels via l'app

1. **Login pierre_test sur app.raya-ia.fr**
   - Doit voir un dashboard vide (pas les mails de guillaume)
   - Doit voir "0 règles actives" ou très peu
   - Doit pouvoir discuter avec Raya

2. **Poser une question Raya à pierre_test**
   - Exemple : "bonjour raya"
   - Attendu : réponse normale, rien de guillaume dans le contexte
   - Vérifier dans `aria_memory` que la conversation est taguée
     `username='pierre_test'` et `tenant_id='couffrant_solar'`

3. **Vérifier bouton "Pourquoi ?"**
   - Cliquer sur 👎 ou demander "pourquoi as-tu répondu ça ?"
   - Les règles affichées doivent être celles de pierre_test (donc
     peu nombreuses), pas de guillaume

4. **Créer un shortcut/topic pour pierre_test**
   - Doit apparaitre uniquement chez pierre_test
   - Se reconnecter en guillaume : ne doit PAS voir le shortcut/topic

5. **Ingestion mails pierre_test**
   - Activer /learn-inbox-mails
   - Les mails doivent arriver taggués username='pierre_test'
   - Verifier que guillaume ne voit pas ces mails

---

## Phase E — Tests côté guillaume (inverse)

6. **Guillaume continue de fonctionner normalement**
   - Ses 141 regles sont toujours là
   - Son historique est intact
   - Ses mails sont intacts

7. **Une règle apprise par pierre_test n'affecte pas guillaume**
   ```sql
   -- Compter les regles de pierre_test
   SELECT COUNT(*) FROM aria_rules
   WHERE username = 'pierre_test' AND active = true;
   -- Puis faire apprendre qqch a pierre_test via chat
   -- Verifier que le compteur de guillaume est inchange
   SELECT COUNT(*) FROM aria_rules
   WHERE username = 'guillaume' AND active = true;
   ```

---

## Phase F — Nettoyage après tests

```sql
-- Supprimer pierre_test et toutes ses donnees
DELETE FROM aria_rules WHERE username = 'pierre_test';
DELETE FROM aria_memory WHERE username = 'pierre_test';
DELETE FROM mail_memory WHERE username = 'pierre_test';
DELETE FROM sent_mail_memory WHERE username = 'pierre_test';
DELETE FROM aria_insights WHERE username = 'pierre_test';
DELETE FROM aria_hot_summary WHERE username = 'pierre_test';
DELETE FROM user_shortcuts WHERE username = 'pierre_test';
DELETE FROM user_topics WHERE username = 'pierre_test';
DELETE FROM email_signatures WHERE username = 'pierre_test';
DELETE FROM user_tenant_access WHERE username = 'pierre_test';
DELETE FROM users WHERE username = 'pierre_test';
```

---

## Critères de succès

- ✅ Phase B : tous les SELECT retournent 0 pour les données de guillaume
- ✅ Phase C : pierre_test voit les mêmes données tenant que guillaume
- ✅ Phase D : l'app fonctionne normalement pour les 2 users
- ✅ Phase E : guillaume n'est pas impacté
- ✅ Phase F : cleanup propre, pas de données orphelines

Si un test échoue, noter précisément :
- Quelle requête a fui
- Quel fichier contient la requête (grep)
- Quel commit corriger

---

## Monitoring en prod

Après onboarding effectif de Pierre/Sabrina, surveiller :

```sql
-- Alerte si une règle/mail/conv d'un user apparait sans tenant_id
SELECT 'aria_rules' as t, COUNT(*) FROM aria_rules WHERE tenant_id IS NULL
UNION ALL
SELECT 'aria_memory', COUNT(*) FROM aria_memory WHERE tenant_id IS NULL
UNION ALL
SELECT 'mail_memory', COUNT(*) FROM mail_memory WHERE tenant_id IS NULL
UNION ALL
SELECT 'aria_insights', COUNT(*) FROM aria_insights WHERE tenant_id IS NULL;
```

Attendu : tous à 0 sur les nouvelles lignes (les anciennes historiques
d'avant le 24/04 peuvent avoir tenant_id=NULL, c'est OK grâce au
pattern `OR tenant_id IS NULL`).
