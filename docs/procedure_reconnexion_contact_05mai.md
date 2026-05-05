# Procédure de reconnexion propre — boîte contact@couffrant-solar.fr

**Date** : 05/05/2026
**Contexte** : la connexion 12 (contact@) utilise un token OAuth qui appartient en réalité à `guillaume@couffrant-solar.fr` (problème mis en évidence par l'audit du 05/05). Il faut la déconnecter et la reconnecter en s'authentifiant avec le **vrai compte contact@**.

---

## Pré-requis

Avant de reconnecter, **vérifier qu'aucun job critique ne tourne** :

```sql
SELECT id, connection_id, status FROM mail_bootstrap_runs 
WHERE status IN ('pending','running');
-- Doit retourner aucune ligne
```

---

## Étapes

### 1. Identification chez Microsoft (CRUCIAL)

Avant de cliquer sur le bouton "Reconnecter" dans le panel admin, il faut **se déconnecter de TOUS les comptes Microsoft du navigateur**.

Sinon Microsoft te re-reconnecte automatiquement avec le compte actuellement actif (probablement guillaume@) et le bug recommence.

**Solution simple** : utiliser une **fenêtre de navigation privée**.

### 2. Désactivation de la connexion 12

Dans le panel admin Couffrant Solar :
- Connexions → "Contact Couffrant Solar"
- Cliquer sur "Déconnecter" / "Supprimer"
- Confirmer

(Le code suivra son cours : status passe à 'disconnected', credentials vidés.)

### 3. Re-création de la connexion contact@

Dans le panel admin :
- "Ajouter une connexion mail" → Outlook/Microsoft
- **IMPORTANT** : se loguer cette fois avec le **mot de passe de contact@couffrant-solar.fr** directement (pas avec ton compte guillaume@ qui a un accès délégué)
- Si Microsoft propose un choix de compte, choisir contact@ (ou "Utiliser un autre compte" puis saisir contact@)
- Accorder les permissions

### 4. Vérification

Après la connexion, dans la console JS du navigateur :

```javascript
fetch('/admin/mail/diag/all-token-identities', {credentials: 'include'})
  .then(r => r.json())
  .then(d => {
    console.log(`Mismatches: ${d.mismatches}`);
    console.table(d.results.map(r => ({
      id: r.connection_id,
      label: r.label,
      attendu: r.expected_email,
      reel: r.real_email_from_token,
      mismatch: r.mismatch
    })));
  })
```

Toutes les lignes doivent avoir `mismatch: false`.

### 5. Bootstrap historique de contact@

Une fois la connexion validée :
- Panel super admin → "Lancer bootstrap historique" sur contact@
- Choisir 12 mois (ou plus)
- Attendre la fin (~5-15 min selon volume)

### 6. Vérification post-bootstrap

```sql
-- Doit montrer beaucoup plus que les 111 actuels
SELECT COUNT(*) FROM mail_memory 
WHERE mailbox_email='contact@couffrant-solar.fr';

-- Top expediteurs : doit etre des prospects/clients, pas guillaume@
SELECT from_email, COUNT(*) FROM mail_memory 
WHERE mailbox_email='contact@couffrant-solar.fr' 
GROUP BY 1 ORDER BY 2 DESC LIMIT 10;
```

---

## En cas de problème

### "Microsoft me reconnecte automatiquement avec mon compte guillaume@"

→ Te déloguer du compte Microsoft à fond :
1. https://login.microsoftonline.com/common/oauth2/v2.0/logout
2. Puis ouvrir une nouvelle fenêtre privée
3. Recommencer l'étape 3

### "Le mot de passe de contact@ ne marche plus"

contact@couffrant-solar.fr est probablement une **boîte partagée** (shared mailbox) ou une **alias** dans le tenant Microsoft 365. Dans ce cas, il n'a pas de mot de passe propre et Microsoft te logue automatiquement avec le compte qui a l'accès délégué.

**Solutions** :

**A. Convertir contact@ en boîte normale dans Microsoft 365 admin** (si tu en as le contrôle), puis lui définir un mot de passe.

**B. Modifier l'app pour gérer les boîtes partagées** : au lieu d'utiliser `/me/mailFolders/...`, utiliser `/users/{contact@-objectId}/mailFolders/...` avec le token de guillaume@. Cette modification permet de cibler une boîte spécifique en utilisant le token d'un compte qui y a accès délégué. Chantier moyen (modifier les calls Graph dans bootstrap + delta-sync).

**C. Décision finale** : si tu ne peux pas convertir contact@ en compte autonome ET tu ne veux pas du chantier B, on peut simplement **fusionner contact@ avec guillaume@** (les mails de contact@ ne sont qu'une copie déléguée vu la config). Garde juste guillaume@.

---

## Pour les autres connexions

Si le diagnostic révèle d'autres mismatches, la même procédure s'applique. Pour Gmail, l'audit a montré que c'est OK.

Pour les futures connexions, le commit `8eb31ab` du 05/05 (token V2 par-connexion) devrait empêcher le bug de se reproduire — chaque connexion utilise désormais SES propres credentials, pas un pool global.
