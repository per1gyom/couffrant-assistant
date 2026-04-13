# Raya — Roadmap Démo & Prospection

**Créé le : 13/04/2026** — Opus + Guillaume
**Statut : EN ATTENTE — à développer quand Raya sera prête**

---

## 1. CONCEPT

Accès démo temporaire pour des prospects. Raya pré-chargée avec des données
réalistes correspondant au secteur du prospect. Le prospect voit Raya "en action"
dès la première connexion — pas une coquille vide.

## 2. CINQ PROFILS SECTORIELS

### Profil 1 — BTP / Photovoltaïque
- **Tenant :** `demo_btp`
- **Persona :** Dirigeant PME 10-50 salariés, chantiers en cours
- **Données :** mails clients/fournisseurs, devis, suivi chantiers, planning équipes
- **Dossiers narratifs :** chantier Dupont en retard, appel d'offres mairie, litige sous-traitant

### Profil 2 — Services (commerce, conseil, comptabilité)
- **Tenant :** `demo_services`
- **Persona :** Dirigeant société de services, 5-20 collaborateurs
- **Données :** propositions commerciales, facturation, suivi clients, relances impayés
- **Dossiers narratifs :** client mécontent, nouveau contrat à signer, recrutement en cours

### Profil 3 — Industrie
- **Tenant :** `demo_industrie`
- **Persona :** Dirigeant PME industrielle, production, logistique
- **Données :** commandes fournisseurs, planning production, stocks, qualité
- **Dossiers narratifs :** panne machine, retard livraison, audit qualité

### Profil 4 — Médical
- **Tenant :** `demo_medical`
- **Persona :** Médecin, kiné, pharmacien, gérant de cabinet
- **Données :** rendez-vous patients (anonymisés), commandes matériel, comptabilité cabinet
- **Dossiers narratifs :** remplacement congés, négociation bail, CPAM en retard

### Profil 5 — Solo / Indépendant
- **Tenant :** `demo_solo`
- **Persona :** Freelance, consultant, auto-entrepreneur
- **Données :** facturation, prospection, agenda chargé, admin/comptabilité
- **Dossiers narratifs :** client en retard de paiement, proposition de mission, déclaration URSSAF

## 3. ARCHITECTURE TECHNIQUE

### Colonnes à ajouter sur users :
- `demo_expires_at` TIMESTAMP — NULL = pas de limite (compte normal)
- `demo_daily_budget_cents` INTEGER — budget quotidien en centimes (ex: 200 = 2€). 0 = illimité

### Composants à créer :
- `app/demo_guard.py` — check_demo_expired() + check_demo_budget()
- `app/demo_seeding.py` — seed_demo_tenant(profile) → charge les données pré-définies
- `app/templates/demo_expired.html` — page "Essai terminé"
- `app/templates/demo_budget.html` — page "Limite quotidienne atteinte"
- Middleware dans main.py → vérifie expiration + budget avant chaque requête
- Endpoint POST /admin/tenants/{id}/reset → purge + recharge
- Bouton "Créer un accès démo" dans le panel admin

### Flux admin :
1. Panel admin → "Créer un accès démo"
2. Choix du profil (BTP, Services, Industrie, Médical, Solo)
3. Saisie email + nom du prospect
4. Génération user + mot de passe temporaire + expiration J+7
5. Envoi email automatique au prospect avec identifiants
6. Prospect se connecte → Raya pré-chargée → wow effect
7. J+7 → page "Essai terminé, contactez-nous"
8. Admin → "Réinitialiser la démo" → purge + recharge → prêt pour le suivant

### Protections :
- Budget quotidien LLM : 2€/jour par défaut (configurable par admin)
- Dépassement → "Limite quotidienne atteinte, revenez demain"
- Pas d'accès aux connecteurs réels (Microsoft, Gmail, Odoo)
- Pas de création/suppression d'utilisateurs
- Données cloisonnées par tenant (déjà en place)
- Plusieurs démos simultanées possibles (chaque prospect = son propre user dans le tenant)

### Données pré-chargées par profil :
- 15 règles métier réalistes
- 30 mails fictifs (clients, fournisseurs, admin)
- 5 insights pertinents
- Hot_summary cohérent (impression que Raya connaît le dirigeant)
- 3-5 dossiers narratifs en cours
- 5 fiches contacts
- Calendrier avec 5-10 RDV fictifs

## 4. SCÉNARIO DE DÉMO GUIDÉ

Parcours type à suivre pendant une démo en live ou à envoyer au prospect :

1. **"Quels sont mes mails urgents ?"** → Raya trie et priorise
2. **"Fais-moi un point sur le dossier X"** → Mémoire narrative en action
3. **"Rédige une réponse à ce client"** → Style rédactionnel personnalisé
4. **"Crée-moi un PDF récap de la semaine"** → Outil de création
5. **"Rappelle-moi de relancer Dupont vendredi"** → Tâche + calendrier
6. **"Qui est M. Martin ?"** → Fiche contact enrichie
7. **WhatsApp "Rapport"** → Reçoit le briefing sur le téléphone

## 5. ESTIMATION EFFORT

| Composant | Effort estimé |
|---|---|
| Infrastructure (colonnes, guard, middleware) | 3-4 prompts |
| Page expired + budget | 2 prompts |
| Admin UI (bouton créer démo + reset) | 2-3 prompts |
| Seeding 5 profils (données fictives) | 5-8 prompts (le plus long) |
| Tests et ajustements | 2-3 prompts |
| **Total** | **~15-20 prompts** |

## 6. PRIORITÉ

À développer APRÈS :
1. ✅ Connectivité 5/5 (fait)
2. ✅ Outils de création PDF/Excel/DALL-E (fait/en cours)
3. Beta Charlotte (valider le multi-tenant)
4. UI/Design (rendre le produit montrable)
5. **→ Puis : Système démo** (ce document)
6. RGPD + facturation
