"""
Permissions hardcodees dans le code, non modifiables via UI ni via SQL direct
depuis un formulaire d admin.

Raison d etre :
Le statut de super_admin du fondateur de Raya doit etre inamovible. Il ne
doit PAS pouvoir etre retire accidentellement (bug, UI defaillante, faux
clic) ni malicieusement (admin compromis, tenant_admin malveillant).

Seule maniere de retirer un super_admin hardcode : modifier cette liste
dans le code, committer et deployer. C est un acte conscient.

Cle utilisee : l email (plus robuste que le username qui peut changer).

Ajout d un nouveau super_admin hardcode : ajouter son email a la liste.
Retrait : retirer son email. Dans les 2 cas, commit + push + deploy.
"""

# Audit isolation 28/04 (A.6) : utilisation systematique des constantes
# SCOPE_* au lieu de magic strings pour clarifier l intention et eviter
# les fautes de frappe silencieuses.
from app.security_tools import (
    SCOPE_SUPER_ADMIN, SCOPE_ADMIN, SCOPE_TENANT_ADMIN, SCOPE_USER,
)


# Liste des emails des super_admins hardcodes, normalises en minuscules
HARDCODED_SUPER_ADMINS_BY_EMAIL = [
    "per1.guillaume@gmail.com",
]


def is_hardcoded_super_admin(email: str) -> bool:
    """Retourne True si l email appartient a la liste hardcodee."""
    if not email:
        return False
    return email.strip().lower() in HARDCODED_SUPER_ADMINS_BY_EMAIL


def get_effective_scope(email: str, db_scope: str) -> str:
    """Retourne le scope effectif d un user.

    Si son email est dans la liste hardcodee -> 'super_admin' force.
    Sinon -> le scope en DB (tel quel).
    """
    if is_hardcoded_super_admin(email):
        return SCOPE_SUPER_ADMIN
    return db_scope or SCOPE_USER


def is_super_admin(email: str, db_scope: str = None) -> bool:
    """Retourne True si l user est super admin (hardcode OU db_scope='super_admin')."""
    if is_hardcoded_super_admin(email):
        return True
    return (db_scope or "").strip().lower() == SCOPE_SUPER_ADMIN


def can_modify_user(actor: dict, target: dict) -> tuple:
    """Verifie qu un acteur a le droit de modifier un utilisateur cible.

    Args:
        actor : dict {username, email, scope, tenant_id} - celui qui fait l action
        target: dict {username, email, scope, tenant_id} - celui qu on modifie

    Retourne (bool allowed, str reason).

    Regles :
    1. Un hardcoded super_admin ne peut JAMAIS etre modifie (ni scope, ni email)
       meme par un autre super_admin. Seul une modif de ce fichier + deploy peut.
    2. Un super_admin peut modifier tout le monde sauf les hardcoded.
    3. Un admin peut modifier tenant_admin, user mais PAS super_admin ni autre admin.
    4. Un tenant_admin peut modifier uniquement les users de SON tenant,
       et jamais lui-meme (pour ne pas se retirer le statut).
    5. Personne ne peut modifier son propre scope via UI (empeche retrogradation
       accidentelle).
    """
    actor_scope = actor.get("scope", SCOPE_USER)
    actor_email = actor.get("email", "")
    actor_username = actor.get("username", "")
    actor_tenant = actor.get("tenant_id", "")
    target_scope = target.get("scope", SCOPE_USER)
    target_email = target.get("email", "")
    target_username = target.get("username", "")
    target_tenant = target.get("tenant_id", "")

    # Regle 1 : hardcoded super_admin intouchable
    if is_hardcoded_super_admin(target_email):
        if actor_username != target_username:
            return (False, "Ce compte est un super-admin protege. Modification impossible via UI.")
        # Cas du super_admin hardcode qui se modifie lui-meme : autorise
        # sur email/display_name/phone MAIS pas sur scope (verifie plus loin)
        return (True, "ok_hardcoded_self")

    # Regle 2 : super_admin peut tout (sauf hardcoded ci-dessus)
    if actor_scope == SCOPE_SUPER_ADMIN:
        return (True, "ok_super_admin")

    # Regle 3 : admin peut modifier tenant_admin/user/couffrant_solar mais pas super_admin ni autre admin
    if actor_scope == SCOPE_ADMIN:
        if target_scope in (SCOPE_SUPER_ADMIN, SCOPE_ADMIN) and actor_username != target_username:
            return (False, "Un admin ne peut pas modifier un autre admin ni un super_admin.")
        return (True, "ok_admin")

    # Regle 4 : tenant_admin, cloisonnement tenant strict
    if actor_scope == SCOPE_TENANT_ADMIN:
        if actor_tenant != target_tenant:
            return (False, "Cloisonnement tenant : tu ne peux modifier que les utilisateurs de ton tenant.")
        if target_scope in (SCOPE_SUPER_ADMIN, SCOPE_ADMIN):
            return (False, "Un tenant_admin ne peut pas modifier un admin Raya ni un super_admin.")
        if actor_username == target_username:
            # Un tenant_admin NE PEUT PAS se modifier lui-meme (empeche auto-retrogradation)
            # Mais il peut modifier son email/display_name/phone via le profil perso
            return (False, "Tu ne peux pas modifier ton propre statut depuis ce panel.")
        return (True, "ok_tenant_admin")

    return (False, "Privileges insuffisants.")


def can_change_scope(actor: dict, target: dict, new_scope: str) -> tuple:
    """Verifie qu un acteur peut changer le scope d un utilisateur vers new_scope.

    En plus de can_modify_user, verifie :
    - Personne ne peut changer le scope d un hardcoded super_admin (meme lui-meme)
    - Personne ne peut s auto-promouvoir super_admin (sauf hardcode)
    - Un admin ne peut pas promouvoir quelqu un en super_admin
    """
    target_email = target.get("email", "")
    actor_scope = actor.get("scope", SCOPE_USER)
    actor_username = actor.get("username", "")
    target_username = target.get("username", "")

    # Protection hardcode : jamais changer le scope d un hardcoded
    if is_hardcoded_super_admin(target_email):
        return (False, "Ce compte est un super-admin protege. Scope non modifiable via UI.")

    # Auto-modification du scope interdite (empeche retrogradation accidentelle)
    if actor_username == target_username:
        return (False, "Tu ne peux pas modifier ton propre scope. Demande a un autre admin.")

    # Seul un super_admin peut nommer un super_admin
    if new_scope == SCOPE_SUPER_ADMIN and actor_scope != SCOPE_SUPER_ADMIN:
        return (False, "Seul un super_admin peut promouvoir quelqu un en super_admin.")

    # Deleguation standard via can_modify_user
    return can_modify_user(actor, target)
