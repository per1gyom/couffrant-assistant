# Raya — Roadmap Démo & Prospection

**Créé le : 13/04/2026** — Opus + Guillaume
**Statut : EN ATTENTE — à développer quand Raya sera prête**

---

## 1. CONCEPT

Accès démo temporaire pour des prospects. Raya pré-chargée avec des données
réalistes correspondant au secteur du prospect.

## 2. CINQ PROFILS SECTORIELS

### Profil 1 — BTP / Photovoltaïque (`demo_btp`)
### Profil 2 — Services / Commerce / Conseil (`demo_services`)
### Profil 3 — Industrie / Production (`demo_industrie`)
### Profil 4 — Médical / Santé (`demo_medical`)
### Profil 5 — Solo / Indépendant (`demo_solo`)

(Détails complets dans la version précédente de ce document)

## 3-6. ARCHITECTURE, FLUX, ESTIMATION

(Voir historique git pour les détails complets)

---

# Roadmap Capacités Fichiers & Médias

## ✅ FAIT
- Création PDF (reportlab) — [ACTION:CREATE_PDF]
- Création Excel (openpyxl) — [ACTION:CREATE_EXCEL]
- Création images (DALL-E 3) — [ACTION:CREATE_IMAGE]
- Lecture PDF uploadé dans le chat (pdfplumber) — EN COURS

## À FAIRE — Manipulation de fichiers
| Capacité | Effort | Approche | Priorité |
|---|---|---|---|
| Lire un PDF uploadé | ✅ En cours | pdfplumber → extraction texte | IMMÉDIAT |
| Lire un PDF depuis SharePoint | Moyen | Download + pdfplumber | Haute |
| Chercher/remplacer dans un PDF | Moyen | Lire → remplacer → régénérer reportlab | Moyenne |
| Modifier une image existante | Lourd | Service d'édition (pas DALL-E) — ex: GPT-Image ou Stability AI inpainting | Basse |
| Créer un Word (.docx) | Faible | python-docx | Moyenne |
| Lire un Word (.docx) | Faible | python-docx | Moyenne |

## Notes techniques
- PDF modification : les PDF positionnent le texte en absolu, un remplacement peut casser la mise en page. Approche fiable = lire → modifier texte → générer un nouveau PDF propre.
- Image modification : DALL-E 3 ne modifie pas les images existantes. Il faudrait un service d'inpainting/outpainting (Stability AI, ou GPT-Image quand disponible).
- Priorité : lecture PDF immédiate (beaucoup de PDF dans le Drive de Guillaume).
