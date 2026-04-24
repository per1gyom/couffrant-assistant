"""
Migration one-shot : reclasser les règles en catégorie 'auto' qui ont
un tag [xxx] implicite au début de leur texte.

Usage : depuis un endpoint admin (GET /admin/maintenance/migrate-auto-tags)
ou via script local :
    python3 -m scripts.migrate_auto_category_tags --username guillaume
    python3 -m scripts.migrate_auto_category_tags --username guillaume --dry-run

Le script :
1. Parcourt toutes les règles active=true, category='auto' de l'utilisateur
2. Détecte un tag [xxx] au début du texte via regex
3. Normalise le tag (accent, casse) + applique les fusions prévues
4. Met à jour category, retire le tag du texte, augmente confidence (+0.1)
5. Logge chaque modification dans rule_modifications pour traçabilité

Idempotent : rejouer le script ne change rien si tous les tags sont déjà traités.
"""
import argparse
import json
import re
import sys
import os

# Permettre d'être importé en tant que module app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_pg_conn
from app.logging_config import get_logger

logger = get_logger("raya.migrate_auto_tags")

# Mapping tag brut (LOWER) -> catégorie finale normalisée
# Les fusions sont explicites ici (équipe/collaborateur/contact/contacts -> Équipe)
TAG_MAPPING = {
    # Fusion "Équipe"
    "équipe": "Équipe",
    "collaborateur": "Équipe",
    "collaborateurs": "Équipe",
    "contact": "Équipe",
    "contacts": "Équipe",
    # Fusion "Clients"
    "client": "Clients",
    "clients": "Clients",
    # Fusion "Patrimoine"
    "patrimoine": "Patrimoine",
    "holding": "Patrimoine",
    # Fusion "Projets & roadmap"
    "roadmap": "Projets & roadmap",
    "projet": "Projets & roadmap",
    "projets": "Projets & roadmap",
    "workflow": "Projets & roadmap",
    # Fusion "Identité"
    "identité": "Identité",
    "presentation": "Identité",
    "présentation": "Identité",
    # Fusion "Tri mails" (harmonise avec categorie existante)
    "tri-mails": "Tri mails",
    "tri_mails": "Tri mails",
    "mail": "Tri mails",
    # Catégories "simples" - majuscule sur la 1re lettre
    "outils": "Outils",
    "comportement": "Comportement",
    "odoo": "Odoo",
    # Catégories rares (1 règle chacune) : on les garde individuellement
    # elles atterriront dans "Divers" à l'affichage puisque <= 2 règles
    "accès": "Accès",
    "affichage": "Affichage",
    "météo": "Météo",
    "sujet": "Sujet",
    "données": "Données",
}

TAG_REGEX = re.compile(r"^\[([^\]]+)\]\s*")


def migrate_user_rules(username, dry_run=True):
    """Migre les règles 'auto' d'un utilisateur."""
    stats = {
        "total_auto": 0,
        "with_tag": 0,
        "migrated": 0,
        "no_mapping": 0,
        "by_new_category": {},
        "skipped_examples": [],
    }
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        # Récupérer toutes les règles 'auto' actives
        c.execute(
            "SELECT id, rule, category, confidence, reinforcements, tenant_id "
            "FROM aria_rules "
            "WHERE username=%s AND active=true AND category='auto' "
            "ORDER BY id",
            (username,)
        )
        rows = c.fetchall()
        stats["total_auto"] = len(rows)

        for rule_id, rule_text, old_cat, old_conf, old_reinf, tenant_id in rows:
            m = TAG_REGEX.match(rule_text)
            if not m:
                continue
            stats["with_tag"] += 1
            raw_tag = m.group(1).strip().lower()
            new_cat = TAG_MAPPING.get(raw_tag)
            if not new_cat:
                stats["no_mapping"] += 1
                if len(stats["skipped_examples"]) < 5:
                    stats["skipped_examples"].append({
                        "id": rule_id,
                        "tag": raw_tag,
                        "preview": rule_text[:80],
                    })
                continue
            # Retirer le tag du texte : "[équipe] Karen = ..." -> "Karen = ..."
            new_text = TAG_REGEX.sub("", rule_text).strip()
            # +0.1 de confidence car on a maintenant une catégorie certaine
            new_conf = min(1.0, (old_conf or 0.5) + 0.1)
            stats["by_new_category"][new_cat] = stats["by_new_category"].get(new_cat, 0) + 1

            if not dry_run:
                c.execute(
                    "UPDATE aria_rules "
                    "SET category=%s, rule=%s, confidence=%s, updated_at=NOW() "
                    "WHERE id=%s",
                    (new_cat, new_text, new_conf, rule_id)
                )
                # Log dans rule_modifications (traçabilité + preparation vectorisation)
                c.execute(
                    "INSERT INTO rule_modifications "
                    "(rule_id, username, tenant_id, action_type, dialogue_turns, "
                    " feedback_text, old_rule, new_rule, old_category, new_category, "
                    " old_confidence, new_confidence) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (rule_id, username, tenant_id, 'edit', json.dumps([]),
                     "[migration_auto_tags] Tag implicite extrait comme catégorie",
                     rule_text, new_text, old_cat, new_cat,
                     old_conf, new_conf)
                )
            stats["migrated"] += 1

        if not dry_run:
            conn.commit()
            logger.info(f"[migrate_auto_tags] Commit OK: {stats['migrated']} regles migrees pour {username}")
        else:
            logger.info(f"[migrate_auto_tags] DRY-RUN: aurait migre {stats['migrated']} regles pour {username}")
        return stats
    except Exception as e:
        if conn:
            conn.rollback()
        logger.exception(f"[migrate_auto_tags] Error: {e}")
        stats["error"] = str(e)
        return stats
    finally:
        if conn:
            conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", required=True, help="Utilisateur à migrer")
    parser.add_argument("--dry-run", action="store_true", help="Ne pas écrire en DB")
    args = parser.parse_args()
    stats = migrate_user_rules(args.username, dry_run=args.dry_run)
    print(json.dumps(stats, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
