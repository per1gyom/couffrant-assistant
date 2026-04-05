from app.database import get_pg_conn


def init_db():
    from app.database import init_postgres
    init_postgres()


def add_global_instruction(instruction: str):
    instruction = (instruction or "").strip()
    if not instruction:
        return

    conn = get_pg_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO global_instructions (instruction) VALUES (%s)",
        (instruction,),
    )
    conn.commit()
    conn.close()


def get_global_instructions(limit: int = 20) -> list[str]:
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("""
        SELECT instruction
        FROM global_instructions
        ORDER BY id DESC
        LIMIT %s
    """, (limit,))
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]