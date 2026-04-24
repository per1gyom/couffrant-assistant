"""
Migration one-shot Phase 2 : fusionner les doublons de categories.

Fusionne les categories avec casse/slug/typo differents vers une forme
canonique, en tenant compte de l'historique des fusions precedentes.

Idempotent : rejouer le script ne change rien si tout est deja migre.

Usage (via endpoint admin) :
    POST /admin/maintenance/migrate-category-duplicates
    { "target_username": "guillaume", "dry_run": true/false }
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_pg_conn
from app.logging_config import get_logger

logger = get_logger("raya.migrate_category_duplicates")

# Mapping des categories actuelles (LOWER) -> categorie canonique finale
# Regroupe les fusions de Phase 2 decouvertes dans le feedback Guillaume
CATEGORY_CANONICAL = {
    # Fusion "Comportement"
    "comportement": "Comportement",
    # Fusion "Outils"
    "outils": "Outils",
    # Fusion "Équipe"
    "équipe": "Équipe",
    "collaborateur": "Équipe",
    "collaborateurs": "Équipe",
    # Fusion "Clients"
    "client": "Clients",
    "clients": "Clients",
    # Fusion "Patrimoine"
    "patrimoine": "Patrimoine",
    "holding": "Patrimoine",
    "structures": "Patrimoine",
    # Fusion "Projets & roadmap"
    "roadmap": "Projets & roadmap",
    "projet": "Projets & roadmap",
    "projets": "Projets & roadmap",
    "workflow": "Projets & roadmap",
    "développement": "Projets & roadmap",
    # Fusion "Tri mails"
    "tri-mails": "Tri mails",
    "tri_mails": "Tri mails",
    "categories_mail": "Tri mails",
    "tri mails": "Tri mails",  # idempotence (deja canonique)
    # Fusion "Drive"
    "drive": "Drive",
    "drive_pv": "Drive",
    # Fusion "Communication"
    "communication": "Communication",
    "ton": "Communication",
    # Fusion "Mémoire"
    "memoire": "Mémoire",
    "mémoire": "Mémoire",
    # Fusion "Données"
    "données": "Données",
    "donnees": "Données",
    # Fusion "Identité"
    "identité": "Identité",
    "identite": "Identité",
    "presentation": "Identité",
    "présentation": "Identité",
    "métier": "Identité",
    # Fusion "Odoo"
    "odoo": "Odoo",
    # Fusion "Regroupement"
    "regroupement": "Regroupement",
    # Fusion "Priorités"
    "priorités": "Priorités",
    "priorites": "Priorités",
    # Petites categories qu'on normalise juste en majuscule
    "accès": "Accès",
    "affichage": "Affichage",
    "météo": "Météo",
    "sujet": "Sujet",
    "limites": "Limites",
    "surveillance": "Surveillance",
    "ux": "UX",
}


def migrate_duplicates(username, dry_run=True):
    """Fusionne les doublons de categories pour l'utilisateur donne."""
    stats = {
        "total_rules": 0,
        "migrated": 0,
        "skipped_no_mapping": 0,
        "already_canonical": 0,
        "by_transition": {},  # "old -> new": count
        "skipped_categories": [],
    }
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        # Recuperer toutes les categories distinctes + leur count
        c.execute(
            "SELECT category, COUNT(*) FROM aria_rules "
            "WHERE username=%s AND active=true "
            "GROUP BY category",
            (username,)
        )
        all_cats = c.fetchall()
        stats["total_rules"] = sum(count for _, count in all_cats)

        for old_cat, count in all_cats:
            if not old_cat or old_cat == "auto":
                # "auto" est garde tel quel (fallback pur apres Phase 1)
                continue
            old_lower = old_cat.lower().strip()
            new_cat = CATEGORY_CANONICAL.get(old_lower)
            if not new_cat:
                stats["skipped_no_mapping"] += count
                stats["skipped_categories"].append({
                    "category": old_cat,
                    "count": count,
                })
                continue
            if new_cat == old_cat:
                # Deja dans la forme canonique
                stats["already_canonical"] += count
                continue
            # Migration : toutes les regles de old_cat -> new_cat
            transition = f"{old_cat} -> {new_cat}"
            stats["by_transition"][transition] = stats["by_transition"].get(transition, 0) + count
            stats["migrated"] += count

            if not dry_run:
                # Recuperer les regles a migrer pour log detaille
                c.execute(
                    "SELECT id, rule, category, confidence, tenant_id FROM aria_rules "
                    "WHERE username=%s AND active=true AND category=%s",
                    (username, old_cat)
                )
                rules_to_migrate = c.fetchall()
                # Update en batch
                c.execute(
                    "UPDATE aria_rules SET category=%s, updated_at=NOW() "
                    "WHERE username=%s AND active=true AND category=%s",
                    (new_cat, username, old_cat)
                )
                # Log dans rule_modifications
                for rule_id, rule_text, _, old_conf, tenant_id in rules_to_migrate:
                    c.execute(
                        "INSERT INTO rule_modifications "
                        "(rule_id, username, tenant_id, action_type, dialogue_turns, "
                        " feedback_text, old_rule, new_rule, old_category, new_category, "
                        " old_confidence, new_confidence) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (rule_id, username, tenant_id, 'edit', json.dumps([]),
                         f"[migration_duplicates] Fusion {old_cat} -> {new_cat}",
                         rule_text, rule_text, old_cat, new_cat,
                         old_conf, old_conf)
                    )

        if not dry_run:
            conn.commit()
            logger.info(f"[migrate_duplicates] Commit OK: {stats['migrated']} regles migrees pour {username}")
        else:
            logger.info(f"[migrate_duplicates] DRY-RUN: aurait migre {stats['migrated']} regles pour {username}")
        return stats
    except Exception as e:
        if conn:
            conn.rollback()
        logger.exception(f"[migrate_duplicates] Error: {e}")
        stats["error"] = str(e)
        return stats
    finally:
        if conn:
            conn.close()
