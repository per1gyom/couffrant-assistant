# À faire — Actions en attente côté Guillaume

Document de suivi des tâches manuelles à traiter quand Guillaume aura un moment. Pas d'urgence, juste pour ne rien oublier.

---

## 🔴 Priorité 1 — GitHub : pousser l'archive v1

**Quoi** : pousser sur GitHub les commits locaux + tag + branche d'archive.

**Pourquoi** : la v1 est archivée localement (tag + branche + doc), mais pas encore sur le remote. Perdre le Mac = perdre l'archive.

**Bloquant actuel** : auth GitHub (token à régénérer ou configurer SSH).

**Action suggérée** : passer en SSH une fois pour toutes (5 min de setup, jamais plus de problème ensuite).

Commandes à lancer une fois l'auth réglée :
```
cd /Users/per1guillaume/couffrant-assistant
git push origin main
git push origin v1-single-shot
git push origin archive/raya-v1-single-shot-21avril2026
```

**État** : en attente

---

## 🟡 Priorité 2 — OpenFire : envoyer le mail consolidé

**Quoi** : envoyer le mail de demande d'ouverture de droits API (version courte).

**Pourquoi** : débloque 80% des cas d'usage métier pour la v2 agent.

**Où est le corps du mail** : `docs/mail_openfire_consolide_21avril.md`.

**État** : rédigé, à envoyer

---

## 🟢 Priorité 3 — Sécurité / résilience

Détaillé dans `docs/plan_resilience_et_securite.md` :
- 2FA sur 6 services critiques (GitHub, Railway, Anthropic, OpenAI, Microsoft 365, Google)
- Backups auto nocturnes (AWS S3 + Backblaze B2)
- UptimeRobot pour monitoring

**État** : en attente, non bloquant pour la v2

---

## ⚪ Priorité 4 — Cohere (probablement obsolète avec v2)

Créer compte Cohere + ajouter `COHERE_API_KEY` dans Railway.

**Utilité v1** : reranking des recherches multi-source.
**Utilité v2** : probablement nulle (le tool use natif gère différemment).

**État** : à réévaluer quand la v2 sera déployée

---

## 📝 Historique

- **21/04/2026** : création du document après une session de refonte architecturale majeure.

---

## 🔮 Pistes Anthropic à explorer plus tard

Notees le 21/04 apres la session de conception v2. A tester quand la v2
sera stable en production.

### Extended thinking (thinking budget)

Permet a Claude de reflechir en interne avant de repondre. Utile sur
les questions metier complexes ou l analyse est lourde.
- Compatible avec tool use
- Gain : meilleure qualite de raisonnement
- Parametre : `thinking: {type: "enabled", budget_tokens: N}`
- Effort : ~20 min pour tester

### Batch API (50 pourcent moins cher)

Pour les jobs non-urgents : analyse nocturne des mails, indexation du
graphe, synthese de sessions passees.
- Anthropic traite sous 24h max
- Facturation a 50 pourcent du prix normal
- Candidats evidents : mail_analysis.py, graph_indexer.py
- Gain : divise par 2 les couts des jobs asynchrones

### PDF input natif

Claude peut lire un PDF directement (jusqu a 32MB, 100 pages).
- Pas besoin d OCR ou d extraction prealable
- Utile des qu OpenFire ouvrira ir.attachment
- Cas d usage : KBIS, devis PDF, cahier des charges, rapports SOCOTEC

### Vision (image input)

Claude analyse des images directement en input.
- Deja utilisable sans rien changer
- Cas d usage : photo de chantier, schema technique, capture Odoo

### Files API (beta)

Upload d un fichier une fois, reference ensuite sans re-upload.
- Utile pour docs de reference permanents (catalogue produits)

### Citations (beta)

Claude peut citer precisement ses sources tirees des documents fournis.
- Aide contre les hallucinations en mode verifiable


---

## 🔧 Fix mémoire v2 — PRIORITÉ 1 demain matin (22/04)

**Découvert en test réel ce soir sur dossier Coullet.**

Raya v2 fonctionne excellent dans la qualité de réponse (plus d'hallucinations, auto-correction, apprentissage) mais bute sur le garde-fou tokens car l'historique in-prompt est trop lourd (10 échanges x 5k tokens = 50k tokens avant de travailler).

**Voir `docs/fix_memoire_v2_22avril.md` pour le plan détaillé.**

Résumé de ce qu'il faut faire :
- Historique in-prompt : 10 → 3 échanges + troncature 3000 chars
- Batch graph_indexer : 8 → 1 (indexation immédiate, supprime trou de mémoire)
- Supprimer l'idée du résumé dans le prompt (redondant avec le graphe)
- Vérifier en DB si la règle métier RFAC a bien été mémorisée par Raya ce soir

Effort : ~20 min de code + test.
