#!/usr/bin/env python3
"""
scripts/backfill_embeddings.py — Calcule les embeddings manquants pour toutes les tables RAG.

Usage :
  python3 scripts/backfill_embeddings.py
  python3 scripts/backfill_embeddings.py --limit 500          # limite sur mail_memory
  python3 scripts/backfill_embeddings.py --table aria_rules   # une seule table
  python3 scripts/backfill_embeddings.py --dry-run            # compte sans ecrire

Prerequis :
  - OPENAI_API_KEY dans .env ou variable d'environnement
  - DATABASE_URL dans .env

Cout estime : text-embedding-3-small = 0.02 USD / 1M tokens
  - aria_rules : ~200 regles x ~20 tokens = 4000 tokens = ~0.0001 USD
  - aria_insights : ~100 insights x ~30 tokens = 3000 tokens = ~0.00006 USD
  - aria_memory : 1000 echanges x ~200 tokens = 200k tokens = ~0.004 USD
  - mail_memory : 1000 mails x ~100 tokens = 100k tokens = ~0.002 USD
  Total typique : < 0.01 USD
"""
import argparse
import os
import sys
import time

# Charge .env si present
def _load_env():
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)
    except ImportError:
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                val = val.strip().strip('"').strip("'")
                os.environ.setdefault(key.strip(), val)

_load_env()

# Verifie l'OPENAI_API_KEY avant tout
if not os.environ.get("OPENAI_API_KEY"):
    print("ERREUR : OPENAI_API_KEY manquant.")
    print("Ajoutez-la dans .env ou dans les variables d'environnement Railway.")
    sys.exit(1)


import psycopg2
from openai import OpenAI

DB_URL = os.environ.get("DATABASE_URL", "").strip()
if not DB_URL:
    print("ERREUR : DATABASE_URL manquant.")
    sys.exit(1)

OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
MODEL      = "text-embedding-3-small"
DIMS       = 1536
BATCH_SIZE = 50

client = OpenAI(api_key=OPENAI_KEY)


# --- Configuration des tables a backfiller ---

TABLES = {
    "aria_rules": {
        "id_col":   "id",
        "text_col": "rule",
        "label":    "regles",
    },
    "aria_insights": {
        "id_col":   "id",
        "text_col": "insight",
        "label":    "insights",
    },
    "aria_memory": {
        "id_col":   "id",
        "text_col": "user_input",  # on embeds la question utilisateur
        "label":    "conversations",
    },
    "mail_memory": {
        "id_col":   "id",
        "text_col": "short_summary",  # plus compact que raw_body_preview
        "label":    "mails",
    },
}


# --- Helpers ---

def get_conn():
    return psycopg2.connect(DB_URL)


def count_missing(conn, table: str, id_col: str) -> int:
    c = conn.cursor()
    c.execute(f"SELECT COUNT(*) FROM {table} WHERE embedding IS NULL")
    return c.fetchone()[0]


def fetch_missing(conn, table: str, id_col: str, text_col: str, limit: int = None) -> list:
    c = conn.cursor()
    sql = f"""
        SELECT {id_col}, {text_col}
        FROM {table}
        WHERE embedding IS NULL
          AND {text_col} IS NOT NULL
          AND {text_col} != ''
        ORDER BY {id_col}
    """
    if limit:
        sql += f" LIMIT {limit}"
    c.execute(sql)
    return c.fetchall()


def embed_batch_openai(texts: list) -> list:
    """Appel API OpenAI en batch, retourne une liste d'embeddings."""
    clean = [t.strip()[:8000] if t else "" for t in texts]
    response = client.embeddings.create(model=MODEL, input=clean, dimensions=DIMS)
    return [item.embedding for item in sorted(response.data, key=lambda x: x.index)]


def write_embeddings(conn, table: str, id_col: str, id_embedding_pairs: list):
    """Ecrit les embeddings en base par batch."""
    c = conn.cursor()
    for row_id, vec in id_embedding_pairs:
        vec_str = "[" + ",".join(str(x) for x in vec) + "]"
        c.execute(
            f"UPDATE {table} SET embedding = %s::vector WHERE {id_col} = %s",
            (vec_str, row_id),
        )
    conn.commit()


def estimate_tokens(texts: list) -> int:
    """Estimation grossiere : 4 caracteres par token."""
    return sum(len(t or "") for t in texts) // 4


# --- Barre de progression simple ---

def progress(current: int, total: int, prefix: str = "") -> str:
    pct = current / total * 100 if total > 0 else 0
    bar_len = 30
    filled = int(bar_len * current / total) if total > 0 else 0
    bar = "█" * filled + "░" * (bar_len - filled)
    return f"\r{prefix} [{bar}] {current}/{total} ({pct:.0f}%)"


# --- Traitement d'une table ---

def backfill_table(
    table: str,
    id_col: str,
    text_col: str,
    label: str,
    limit: int = None,
    dry_run: bool = False,
) -> dict:
    conn = get_conn()
    try:
        missing_total = count_missing(conn, table, id_col)
        effective_limit = min(limit, missing_total) if limit else missing_total

        print(f"\n{'='*60}")
        print(f"Table : {table} ({label})")
        print(f"  Lignes sans embedding : {missing_total}")
        if limit and limit < missing_total:
            print(f"  Limite appliquee : {limit} (--limit)")
        if effective_limit == 0:
            print(f"  Rien a faire — toutes les lignes ont deja un embedding.")
            return {"table": table, "processed": 0, "errors": 0, "tokens_estimated": 0}

        rows = fetch_missing(conn, table, id_col, text_col, limit=effective_limit)
        print(f"  Lignes a traiter : {len(rows)}")

        if dry_run:
            total_tokens = estimate_tokens([r[1] for r in rows])
            cost_usd = total_tokens / 1_000_000 * 0.02
            print(f"  [DRY-RUN] Tokens estimes : {total_tokens:,} (~{cost_usd:.4f} USD)")
            return {"table": table, "processed": 0, "errors": 0, "tokens_estimated": total_tokens}

        total_tokens = 0
        processed = 0
        errors = 0

        # Traitement par lots
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i : i + BATCH_SIZE]
            ids   = [r[0] for r in batch]
            texts = [r[1] for r in batch]

            batch_tokens = estimate_tokens(texts)
            total_tokens += batch_tokens

            try:
                embeddings = embed_batch_openai(texts)
                pairs = [(row_id, vec) for row_id, vec in zip(ids, embeddings) if vec is not None]
                write_embeddings(conn, table, id_col, pairs)
                processed += len(pairs)
                errors += len(batch) - len(pairs)
            except Exception as e:
                print(f"\n  ERREUR batch {i//BATCH_SIZE + 1} : {e}")
                errors += len(batch)

            # Affiche la progression
            print(progress(processed, len(rows), prefix=f"  {label}"), end="", flush=True)

            # Pause courte pour respecter les rate limits OpenAI
            if i + BATCH_SIZE < len(rows):
                time.sleep(0.1)

        print()  # saut de ligne apres la barre
        cost_usd = total_tokens / 1_000_000 * 0.02
        print(f"  Traites : {processed} | Erreurs : {errors} | Tokens : {total_tokens:,} (~{cost_usd:.4f} USD)")
        return {"table": table, "processed": processed, "errors": errors, "tokens_estimated": total_tokens}

    finally:
        conn.close()


# --- Main ---

def main():
    parser = argparse.ArgumentParser(
        description="Backfill des embeddings manquants pour le RAG Raya",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--limit",   type=int, default=None,
                        help="Limite le nombre de lignes traitees pour mail_memory et aria_memory")
    parser.add_argument("--table",   type=str, default=None,
                        choices=list(TABLES.keys()),
                        help="Traite uniquement cette table")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simule sans ecrire en base, affiche l'estimation de cout")
    args = parser.parse_args()

    print("=" * 60)
    print("BACKFILL EMBEDDINGS — Raya RAG")
    print(f"Modele : {MODEL} ({DIMS} dims)")
    print(f"Batch  : {BATCH_SIZE} lignes")
    if args.dry_run:
        print("MODE DRY-RUN — aucune ecriture en base")
    print("=" * 60)

    tables_to_process = (
        {args.table: TABLES[args.table]} if args.table
        else TABLES
    )

    # mail_memory et aria_memory peuvent etre volumineuses -> applique --limit
    big_tables = {"mail_memory", "aria_memory"}

    total_processed = 0
    total_errors    = 0
    total_tokens    = 0
    start           = time.time()

    for table, cfg in tables_to_process.items():
        table_limit = args.limit if table in big_tables else None
        result = backfill_table(
            table    = table,
            id_col   = cfg["id_col"],
            text_col = cfg["text_col"],
            label    = cfg["label"],
            limit    = table_limit,
            dry_run  = args.dry_run,
        )
        total_processed += result["processed"]
        total_errors    += result["errors"]
        total_tokens    += result["tokens_estimated"]

    elapsed = time.time() - start
    cost_usd = total_tokens / 1_000_000 * 0.02

    print(f"\n{'='*60}")
    print("RESUME FINAL")
    print(f"  Lignes traitees : {total_processed}")
    print(f"  Erreurs         : {total_errors}")
    print(f"  Tokens estimes  : {total_tokens:,}")
    print(f"  Cout estime     : ~{cost_usd:.4f} USD")
    print(f"  Duree           : {elapsed:.1f}s")
    if args.dry_run:
        print("\n  [DRY-RUN] Aucune donnee ecrite. Relancez sans --dry-run pour executer.")
    else:
        print("\n  Le RAG vectoriel est maintenant operationnel.")
        print("  Verifiez avec : python3 scripts/backfill_embeddings.py --dry-run")
    print("=" * 60)


if __name__ == "__main__":
    main()
