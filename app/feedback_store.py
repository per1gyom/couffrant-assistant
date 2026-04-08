from app.database import get_pg_conn


def init_db():
    from app.database import init_postgres
    init_postgres()


def add_global_instruction(instruction: str, tenant_id: str = 'couffrant_solar'):
    """Ajoute une consigne globale pour un tenant."""
    instruction = (instruction or "").strip()
    if not instruction:
        return
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO global_instructions (instruction, tenant_id) VALUES (%s, %s)",
        (instruction, tenant_id),
    )
    conn.commit()
    conn.close()


def get_global_instructions(tenant_id: str = 'couffrant_solar', limit: int = 20) -> list[str]:
    """Retourne les consignes globales d'un tenant."""
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("""
        SELECT instruction FROM global_instructions
        WHERE tenant_id = %s
        ORDER BY id DESC LIMIT %s
    """, (tenant_id, limit))
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]
