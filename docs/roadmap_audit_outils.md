# Roadmap — Audit des outils Raya

**Créé le 25 avril 2026 suite au Run #2 agent** qui a mis en lumière des limitations silencieuses dans les outils que Raya utilise.

## 🚨 Contexte — ce qui a déclenché cette roadmap

Pendant le Run #2 du rules_optimizer en mode agent, Raya a cherché "SOCOTEC rapport"
dans les mails et a trouvé 0 résultat. Elle en a déduit à tort que les règles 107 et 89
sur SOCOTEC étaient "anticipatives" et a proposé de les downgrader.

En réalité, il y avait **6 mails SOCOTEC** dans la base. Le bug vient de l'outil
`search_mails` : il fait un `ILIKE '%SOCOTEC rapport%'` (chaîne exacte) au lieu de
splitter les mots et faire un ILIKE sur chacun. Résultat : Raya "improvise" parce
qu'elle croit de bonne foi qu'un pattern n'existe pas.


## 🎯 Objectif

Faire un audit exhaustif des outils utilisés par Raya (en chat ET en mode agent)
pour identifier les bugs silencieux, les limitations non-documentées, et les
cas où l'outil renvoie "rien trouvé" alors qu'il y a quelque chose.

## 📋 Outils à auditer

### Outils centraux (usage quotidien)

1. **`search_mails`** — recherche dans mail_memory
   - BUG CONFIRMÉ : ILIKE sur chaîne complète au lieu de tokenisation
   - À faire : splitter la query par espaces, AND sur chaque mot
   - À faire : gérer les synonymes (SOCOTEC → socotec.com, controle, rapport)
   - À tester : seuils de pertinence, tri par date vs par pertinence

2. **`search_drive`** — liste dossiers configurés
   - Limitation connue : ne liste que les dossiers racine, pas les fichiers
   - À faire : permettre recherche dans les fichiers indexés (si on les indexe)
   - À tester : gestion SharePoint vs Google Drive

3. **`query_odoo`** — partners/sale_order/invoice
   - Nécessite APP_USERNAME défini (sinon échec silencieux en script isolé)
   - À tester : recherche par champs autres que name (email, réf)
   - À améliorer : permettre filtrage par état (sale_order : brouillon vs confirmé)


### Outils en chat Raya (à lister exhaustivement)

À auditer plus tard, session dédiée :
- web_search (tool natif Anthropic)
- read_mail / send_mail / draft_mail
- list_drive_files / search_drive_files / get_drive_file_content
- create_calendar_event / list_calendar_events
- post_teams_message
- query_odoo_* (multiples)
- memory_save_rule / memory_search_rule
- Tous les autres (liste à extraire depuis le code)

## 🛠️ Méthode d'audit proposée

Pour chaque outil :
1. Lire le code source
2. Identifier les paramètres acceptés vs documentés
3. Tester 5-10 requêtes réelles avec variations (1 mot, plusieurs mots, accents, synonymes)
4. Comparer ce que l'outil trouve vs ce qui existe réellement en base
5. Documenter les limitations et bugs
6. Corriger les bugs critiques
7. Améliorer la doc (description) que voit Raya pour mieux les utiliser

## 🔒 Garde-fou provisoire ajouté

En attendant l'audit complet, le prompt du rules_optimizer a été renforcé :
- Raya ne peut plus proposer de fusion/suppression/modif pour une règle à
  confidence >= 0.9 OU source = 'user_explicit'
- Ces règles vont systématiquement en AMBIGUË si Raya pense qu'elles doivent
  évoluer, pour validation humaine

## 📅 Quand faire cet audit ?

- Phase actuelle (expérimentale) : pas de priorité haute, on corrige au fil de l'eau
- Avant passage en mode production réel : OBLIGATOIRE
- Après connexion de toutes les boîtes mail et outils : session dédiée recommandée
