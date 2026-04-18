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
        return "super_admin"
    return db_scope or "user"


def is_super_admin(email: str, db_scope: str = None) -> bool:
    """Retourne True si l user est super admin (hardcode OU db_scope='super_admin')."""
    if is_hardcoded_super_admin(email):
        return True
    return (db_scope or "").strip().lower() == "super_admin"
