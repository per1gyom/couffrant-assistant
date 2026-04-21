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
