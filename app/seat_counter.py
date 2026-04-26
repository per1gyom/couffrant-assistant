"""
Seat counter pour le modele SaaS multi-tenant.

Cree le 26/04/2026 (etape B.1b).

Philosophie : chaque tenant a un quota max_users (fixe par le super_admin
a la creation du tenant ou via endpoint quota update). Le tenant_admin
peut creer/supprimer/restaurer des users librement DANS la limite du
quota. Pour augmenter le quota, il doit faire la demande au super_admin
(= acte de facturation).

Regle de comptage :
- Compte : users actifs + users suspended + users en demande de
  suppression RGPD (deletion_requested_at IS NOT NULL mais pas encore
  soft-delete)
- Ne compte PAS : users soft-delete (deleted_at IS NOT NULL).
  Le seat est libere des le soft-delete. Permet a Charlotte de
  "remplacer" Marc par Sophie sans demander d'augmentation.
"""

from fastapi import HTTPException
from app.database import get_pg_conn


def get_tenant_quota(tenant_id: str) -> dict:
    """Retourne l'etat du quota d'un tenant.

    Returns:
        {
            'tenant_id': str,
            'max_users': int,        # quota max (defini par super_admin)
            'used': int,             # users actuels (hors soft-delete)
            'available': int,        # max_users - used (peut etre 0 ou negatif)
            'soft_deleted': int,     # users soft-delete (libere des seats)
            'is_full': bool,         # True si used >= max_users
        }
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "SELECT max_users FROM tenants WHERE id = %s",
            (tenant_id,),
        )
        row = c.fetchone()
        if not row:
            raise HTTPException(404, f"Tenant '{tenant_id}' introuvable.")
        max_users = row[0]

        c.execute(
            "SELECT count(*) FILTER (WHERE deleted_at IS NULL) AS used, "
            "       count(*) FILTER (WHERE deleted_at IS NOT NULL) AS soft_deleted "
            "FROM users WHERE tenant_id = %s",
            (tenant_id,),
        )
        used, soft_deleted = c.fetchone()

        return {
            "tenant_id": tenant_id,
            "max_users": max_users,
            "used": used,
            "available": max(0, max_users - used),
            "soft_deleted": soft_deleted,
            "is_full": used >= max_users,
        }
    finally:
        if conn:
            conn.close()


def assert_seat_available(tenant_id: str) -> None:
    """Verifie qu'il y a au moins un seat libre dans le tenant.
    Leve HTTPException(403) si plein, avec message explicite indiquant
    quoi faire (contacter super_admin pour augmenter max_users, ou
    soft-delete un autre user pour liberer un seat).

    A appeler systematiquement AVANT tout INSERT INTO users dans
    les endpoints de creation (ou de restauration de soft-delete).
    """
    quota = get_tenant_quota(tenant_id)
    if quota["is_full"]:
        raise HTTPException(
            403,
            f"Quota du tenant '{tenant_id}' atteint "
            f"({quota['used']}/{quota['max_users']} seats). "
            f"Pour ajouter un user, contactez le super_admin pour "
            f"augmenter max_users, ou soft-delete un autre user pour "
            f"liberer un seat (le user soft-delete est conservable et "
            f"restaurable).",
        )
