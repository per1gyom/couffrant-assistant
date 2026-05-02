# 🌅 Récap nuit du 2-3 mai — À lire au réveil

Bonjour Guillaume,

Pendant que tu dormais, j'ai produit deux audits complets :

```
📂 docs/audits/audit3_exemples_impersonnels.md     (514 lignes)
📂 docs/audits/audit4_robustesse_prompt_v2.md      (403 lignes)
```

Voici ce que tu dois retenir pour démarrer la journée.

---

## 🎯 Bilan en 30 secondes

```
Charlotte ne peut PAS utiliser Raya en l'état.

3 problèmes critiques :

🔴 1. Le prompt v2 dit littéralement
       "Tu es Raya, IA de Charlotte chez Couffrant Solar
       (photovoltaïque, Romorantin-Lanthenay)"
   → Hardcodé dans raya_agent_core.py ligne 74

🔴 2. Tous les tools sont exposés à tout le monde
       Charlotte verrait search_odoo, send_teams_message
       alors qu'elle n'a ni Odoo ni Teams
   → TODO non fait dans get_tools_for_user (raya_tools.py:555)

🔴 3. L'analyseur de mails dit aussi "Couffrant Solar"
   → ai_client.py ligne 178

LE RESTE est nettoyage cosmétique mais important :
🟠 Placeholders Drive ("Drive Direction", "Comptabilité/Salaires")
🟠 Description tools (SharePoint en dur, Outlook par défaut)
🟠 Exemples prompts (SARL Des Moines, Cordialement Guillaume)
🟠 Valeurs HTML par défaut (Guillaume Perrin, faux numéro de tél)
```

---

## 📋 Le plan de bataille proposé

### Phase 1 — BLOQUANTE pour Charlotte (~4-6h)

```
1. Créer table/champ tenant_profile (1h)
   Pour stocker : nom société, métier, ton, default_mail, etc.
   Remplir pour couffrant_solar et juillet.

2. Refactor le prompt v2 (45 min)
   Plus de Couffrant en dur. Le prompt charge le profil tenant.

3. Refactor le filtrage des tools (1h)
   get_tools_for_user filtre selon les connecteurs actifs.
   Charlotte ne voit que ses outils réels.

4. Refactor ai_client.py (30 min)
   L'analyseur de mails dépend du tenant aussi.

5. Nettoyage descriptions tools (45 min)
   "SharePoint" → "Drive". "Outlook par défaut" → dynamique.

6. Nettoyage HTML user_settings (15 min)
   Plus de "Guillaume Perrin" en valeur par défaut.

7. Nettoyage exemples prompts/guardrails (15 min)
   SARL Des Moines → exemple générique
   Cordialement Guillaume → Cordialement [Prenom]

8. Tests bout-en-bout (45 min)
   Logger en tant que Charlotte, vérifier le prompt envoyé,
   tester quelques requêtes.

TOTAL : ~5 heures
```

### Phase 2 — Après les premiers retours Charlotte (~2-3h)

```
- Construction dynamique de la liste des sources dans le prompt
- Glossaire métier basique
- Placeholders Drive (Drive Direction → Documents)
```

### Phase 3 — Plus tard

```
- Code mort, commentaires, branding email
```

---

## ✅ La bonne nouvelle

```
🟢 Charlotte est DÉJÀ correctement seedée en DB
   10 règles dans aria_rules pour tenant=juillet, source=onboarding
   → Style direct synthétique, agence événementielle B2B
   → Outils Google, scénographie, etc.
   → Le RAG va bien charger ces règles dans son prompt

🟢 L'architecture v2 est solide
   - Boucle agent OK
   - Tool use OK
   - Garde-fous (anti-injection, etc.) OK
   - RAG OK
   - Mécanique multi-tenant déjà en place

🟢 Les 8 profils de seeding existent
   pv_french, event_planner, generic, artisan, immobilier,
   conseil, commerce, medical

→ TOUT EST PRÊT structurellement.
   Il faut juste désincruster ton métier des 10-15 endroits où
   il a été codé en dur "pour aller plus vite".
```

---

## 🎬 Comment je propose qu'on commence demain

```
1. Tu lis cet audit + au moins l'audit 4 (le plus court)
2. Tu valides le plan Phase 1
3. On attaque dans l'ordre :
   a. Migration DB tenant_profile
   b. Refactor prompt v2
   c. Filtrage tools
   d. Le reste
4. À la fin de la journée, Charlotte peut commencer à tester

Estimation : on en a pour la journée de demain.
Si tu valides la priorité Charlotte, tout le reste passe au second
plan (UI connexions, signature Microsoft, etc.)
```

---

## 🌙 Au passage cette nuit

```
À 03h00 le rules_optimizer va tourner pour la première fois avec
le Layer A0 que j'ai poussé tout à l'heure. Au réveil tu pourras
voir le résultat dans :
  SELECT * FROM rules_optimization_log
  WHERE run_at > NOW() - INTERVAL '6 hours'
  ORDER BY run_at DESC;

Attendu : 21+ règles recatégorisées, 11+ doublons fusionnés
sur ton tenant guillaume@couffrant_solar.
```

Bonne nuit. À demain.
