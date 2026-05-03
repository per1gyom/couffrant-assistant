"""
Logique de matching des chemins Drive (SharePoint, Google Drive, NAS futurs).

Cette logique est UNIVERSELLE : elle s applique a tous les types de stockage
de fichiers connectables a Raya. Cf docs/journal_02mai_2026_drive_multi_racines.md

REGLE PRINCIPALE : "Le chemin le plus long gagne"
==================================================

Pour decider si un fichier doit etre indexe par Raya, on regarde toutes les
regles configurees pour la connexion correspondante :

1. La connexion doit avoir au moins une RACINE configuree dans drive_folders.
   Le path doit tomber sous l une de ces racines (sinon non indexe).

2. Parmi les regles include/exclude (table tenant_drive_blacklist), on
   selectionne celles dont folder_path est un prefixe du path teste.

3. La regle au folder_path le plus long gagne. Si rule_type='include' on
   indexe, si rule_type='exclude' on n indexe pas.

4. Si aucune regle ne matche : on indexe (le path est dans une racine
   surveillee, donc inclus par defaut, comme le comportement actuel).

EXEMPLE :
   Path teste : /Drive Direction/RH/Politiques_Publiques/contrat.docx
   Regles configurees :
     - /Drive Direction         (include) [longueur 16]
     - /Drive Direction/RH      (exclude) [longueur 19]
     - /Drive Direction/RH/Politiques_Publiques (include) [longueur 47]
   -> Resultat : INCLUS (la 3eme regle est la plus longue qui matche)
"""
from __future__ import annotations

from typing import Iterable, Optional

# IMPORTANT : les imports DB sont fait en LAZY a l interieur des fonctions
# qui en ont besoin, pour permettre :
#   - tests unitaires de la logique pure (is_path_indexable avec args)
#   - import du module sans environnement DB initialise
# Voir get_drive_roots() et get_path_rules() pour le pattern.

import logging
logger = logging.getLogger("raya.drive_path_rules")


# ---- Normalisation du path ---------------------------------------------

def _normalize_path(path: Optional[str]) -> str:
    """
    Normalise un path pour comparaison :
      - lstrip('/') puis rstrip('/')
      - garde la casse (les paths SharePoint sont case-sensitive)
    Resultat : 'Drive Direction/RH/Salaires' (sans slashs en debut/fin).
    """
    if not path:
        return ""
    return path.strip().strip("/")


def _is_prefix_of(prefix: str, full: str) -> bool:
    """
    Retourne True si 'prefix' est un prefixe de 'full' au sens des dossiers.
    Doit matcher dossier complet : 'RH' n est PAS prefixe de 'RH_Confidentiel'.

    Cas geres :
      _is_prefix_of('', 'a/b')              -> True (racine matche tout)
      _is_prefix_of('a', 'a/b')             -> True
      _is_prefix_of('a/b', 'a/b')           -> True
      _is_prefix_of('a/b', 'a/b/c')         -> True
      _is_prefix_of('a/b', 'a/bc')          -> False (different dossier)
      _is_prefix_of('a/b', 'a')             -> False (full plus court)
    """
    p = _normalize_path(prefix)
    f = _normalize_path(full)
    if p == "":
        return True  # path vide = racine du drive, prefixe de tout
    if p == f:
        return True
    return f.startswith(p + "/")


# ---- Lecture des racines surveillees -----------------------------------

def get_drive_roots(connection_id: int) -> list[str]:
    """
    Retourne la liste des folder_path declares comme RACINES surveillees
    pour cette connexion. Provient de la table drive_folders.

    Si la connexion n a aucune racine declaree -> liste vide -> rien indexe.

    NOTE : drive_folders.folder_path peut etre NULL ou vide -> on l ignore.
    Une racine vide est invalide (ambigue).
    """
    # Import lazy : permet d importer ce module sans env DB
    from app.database import get_pg_conn
    roots: list[str] = []
    conn = None
    try:
        conn = get_pg_conn()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT folder_path
            FROM drive_folders
            WHERE enabled = TRUE
              AND folder_path IS NOT NULL
              AND folder_path <> ''
            """
        )
        for row in cur.fetchall():
            fp = row[0] if not isinstance(row, dict) else row.get("folder_path")
            if fp:
                roots.append(_normalize_path(fp))
    except Exception:
        logger.exception("[drive_path_rules] erreur get_drive_roots(connection_id=%s)", connection_id)
        return []
    finally:
        if conn:
            conn.close()
    return roots


def get_drive_roots_for_connection(connection_id: int) -> list[str]:
    """
    Variante filtree par connection_id. Aujourd hui drive_folders n a pas de
    colonne connection_id directe, mais elle a tenant_id + provider + site_name.
    On utilise donc plutot get_drive_roots() global pour le tenant et on filtre
    cote appelant si necessaire.

    Pour l instant, on retourne TOUTES les racines du tenant (la connexion
    sera filtree au niveau du scanner, pas ici).
    """
    return get_drive_roots(connection_id)


# ---- Lecture des regles include/exclude --------------------------------

def get_path_rules(connection_id: int, scope: str = "tenant") -> list[tuple[str, str]]:
    """
    Retourne les regles configurees pour cette connexion sous forme de
    tuples (folder_path_normalise, rule_type) ou rule_type est 'include'
    ou 'exclude'.

    Filtre par defaut : scope='tenant' (regles de l admin tenant).
    Plus tard, on pourra appeler avec scope='user' pour les drives prives.
    """
    # Import lazy
    from app.database import get_pg_conn
    rules: list[tuple[str, str]] = []
    conn = None
    try:
        conn = get_pg_conn()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT folder_path, rule_type
            FROM tenant_drive_blacklist
            WHERE connection_id = %s
              AND scope = %s
            """,
            (connection_id, scope),
        )
        for row in cur.fetchall():
            if isinstance(row, dict):
                fp = row.get("folder_path")
                rt = row.get("rule_type") or "exclude"
            else:
                fp = row[0]
                rt = row[1] if len(row) > 1 else "exclude"
            if fp is None:
                continue
            rules.append((_normalize_path(fp), rt))
    except Exception:
        logger.exception("[drive_path_rules] erreur get_path_rules(connection_id=%s)", connection_id)
        return []
    finally:
        if conn:
            conn.close()
    return rules


# ---- Decision principale -----------------------------------------------

def is_path_indexable(
    connection_id: int,
    path: str,
    *,
    roots: Optional[list[str]] = None,
    rules: Optional[list[tuple[str, str]]] = None,
) -> bool:
    """
    Retourne True si le path doit etre indexe par Raya, False sinon.

    Implemente la regle "le chemin le plus long gagne" :

      1. Le path doit etre sous une racine surveillee.
      2. La regle au folder_path le plus long qui prefixe le path gagne.
      3. Sans regle qui matche : indexe par defaut (path est sous racine).

    Les arguments roots et rules permettent d eviter une requete DB par
    appel quand le scanner traite des centaines de fichiers. L appelant
    peut precharger une fois, puis passer en argument.
    """
    if not path:
        return False

    p = _normalize_path(path)

    # 1. Etre sous une racine surveillee
    if roots is None:
        roots = get_drive_roots(connection_id)
    if not roots:
        # Aucune racine declaree pour cette connexion -> rien a indexer
        return False
    in_root = any(_is_prefix_of(root, p) for root in roots)
    if not in_root:
        return False

    # 2. Regarder les regles
    if rules is None:
        rules = get_path_rules(connection_id)
    if not rules:
        return True  # sous racine, sans regle specifique = indexe

    # 3. Trouver la regle dont le folder_path est le prefixe le plus long
    matching = [(rule_path, rule_type) for rule_path, rule_type in rules
                if _is_prefix_of(rule_path, p)]
    if not matching:
        return True  # aucune regle ne matche = indexe par defaut

    # Tri par longueur de folder_path desc (le plus long gagne)
    matching.sort(key=lambda r: -len(r[0]))
    winning_path, winning_type = matching[0]
    return winning_type == "include"


# ---- Helper pour preview cote UI ---------------------------------------

def explain_path_decision(
    connection_id: int,
    path: str,
) -> dict:
    """
    Retourne un dictionnaire explicitant la decision pour ce path.
    Utile pour la page admin de simulation/preview.

    Forme :
      {
        "path": "Drive Direction/RH/Politiques_Publiques/contrat.docx",
        "indexable": True,
        "in_root": True,
        "matching_root": "Drive Direction",
        "winning_rule": ("Drive Direction/RH/Politiques_Publiques", "include"),
        "all_matching_rules": [
          ("Drive Direction", "include"),
          ("Drive Direction/RH", "exclude"),
          ("Drive Direction/RH/Politiques_Publiques", "include"),
        ],
      }
    """
    p = _normalize_path(path)
    roots = get_drive_roots(connection_id)
    rules = get_path_rules(connection_id)

    matching_root = None
    for r in roots:
        if _is_prefix_of(r, p):
            if matching_root is None or len(r) > len(matching_root):
                matching_root = r

    matching_rules = [(rule_path, rule_type) for rule_path, rule_type in rules
                      if _is_prefix_of(rule_path, p)]
    matching_rules.sort(key=lambda r: -len(r[0]))
    winning = matching_rules[0] if matching_rules else None

    indexable = False
    if matching_root is not None:
        if winning is None:
            indexable = True
        else:
            indexable = winning[1] == "include"

    return {
        "path": p,
        "indexable": indexable,
        "in_root": matching_root is not None,
        "matching_root": matching_root,
        "winning_rule": winning,
        "all_matching_rules": matching_rules,
    }
