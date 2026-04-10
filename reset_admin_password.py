#!/usr/bin/env python3
"""
reset_admin_password.py — Outil opérationnel de gestion des mots de passe Raya.

Usage :
  python reset_admin_password.py <username>
      Génère un mot de passe temporaire aléatoire pour l'utilisateur.

  python reset_admin_password.py <username> --password <nouveau_mdp>
      Applique un mot de passe choisi manuellement.

  python reset_admin_password.py --list
      Liste tous les utilisateurs et leur statut.

Prérequis :
  pip install psycopg2-binary python-dotenv
  DATABASE_URL dans .env ou variable d'environnement.

Algorithme de hachage : PBKDF2-SHA256, sel 16 bytes, 100 000 itérations.
Identique à app/security_auth.py — les mots de passe sont compatibles.
"""
import argparse
import base64
import hashlib
import os
import secrets
import string
import sys


def _load_env():
    """Charge .env si présent, sans dépendance obligatoire à python-dotenv."""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)
    except ImportError:
        # Fallback manuel si python-dotenv n'est pas installé
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                val = val.strip().strip('"').strip("'")
                os.environ.setdefault(key.strip(), val)


def _get_conn():
    """Connexion PostgreSQL via DATABASE_URL."""
    import psycopg2
    db_url = os.environ.get("DATABASE_URL", "").strip()
    if not db_url:
        print("[ERREUR] DATABASE_URL non défini. Vérifiez votre fichier .env.")
        sys.exit(1)
    try:
        return psycopg2.connect(db_url)
    except Exception as e:
        print(f"[ERREUR] Impossible de se connecter à la base : {e}")
        sys.exit(1)


def _hash_password(password: str) -> str:
    """
    Même algorithme que app/security_auth.py :
    PBKDF2-SHA256, sel 16 bytes aléatoires, 100 000 itérations, encodé base64.
    """
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return base64.b64encode(salt + dk).decode("utf-8")


def _generate_password(length: int = 12) -> str:
    """
    Génère un mot de passe aléatoire.
    Alphanumérique uniquement pour éviter les problèmes de copier-coller
    et les caractères ambigus (0/O, 1/l/I sont conservés — lisibles en contexte).
    """
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def cmd_list():
    """Liste tous les utilisateurs avec leur statut."""
    conn = _get_conn()
    try:
        c = conn.cursor()
        c.execute("""
            SELECT username, email, scope, tenant_id, last_login,
                   COALESCE(account_locked, false),
                   COALESCE(must_reset_password, false)
            FROM users
            ORDER BY tenant_id, username
        """)
        rows = c.fetchall()
        if not rows:
            print("Aucun utilisateur en base.")
            return

        print(f"\n{'USERNAME':<20} {'SCOPE':<16} {'TENANT':<20} {'DERNIER LOGIN':<22} {'BLOQUÉ':<8} {'RESET?'}")
        print("-" * 100)
        for username, email, scope, tenant_id, last_login, locked, must_reset in rows:
            login_str = str(last_login)[:19] if last_login else "jamais"
            locked_str = "OUI ⚠️" if locked else "non"
            reset_str = "OUI" if must_reset else "non"
            print(f"{username:<20} {(scope or 'user'):<16} {(tenant_id or ''):<20} {login_str:<22} {locked_str:<8} {reset_str}")
        print(f"\n{len(rows)} utilisateur(s) au total.\n")
    finally:
        conn.close()


def cmd_reset(username: str, new_password: str = None):
    """Réinitialise le mot de passe d'un utilisateur."""
    conn = _get_conn()
    try:
        c = conn.cursor()

        # Vérifie que l'utilisateur existe
        c.execute("SELECT username, scope, tenant_id FROM users WHERE username = %s", (username,))
        row = c.fetchone()
        if not row:
            print(f"[ERREUR] Utilisateur '{username}' introuvable.")
            print("\nUtilisateurs disponibles :")
            c.execute("SELECT username FROM users ORDER BY username")
            for (u,) in c.fetchall():
                print(f"  - {u}")
            sys.exit(1)

        _, scope, tenant_id = row

        # Génère le mot de passe si non fourni
        if new_password is None:
            new_password = _generate_password(12)
            generated = True
        else:
            generated = False

        # Confirmation si mot de passe fourni manuellement
        if not generated:
            confirm = input(f"Appliquer le mot de passe fourni pour '{username}' ? [o/N] ").strip().lower()
            if confirm != "o":
                print("Annulé.")
                sys.exit(0)

        # Hash et mise à jour
        hashed = _hash_password(new_password)
        c.execute(
            "UPDATE users SET password_hash = %s, must_reset_password = true WHERE username = %s",
            (hashed, username),
        )
        # Déverrouille le compte si bloqué (pratique si c'est pour ça qu'on reset)
        c.execute("""
            UPDATE users SET
                account_locked = false,
                login_attempts_count = 0,
                login_attempts_round = 0,
                login_locked_until = NULL
            WHERE username = %s
        """, (username,))
        conn.commit()

        # Affichage du résultat
        print("\n" + "=" * 50)
        print("  MOT DE PASSE RÉINITIALISÉ")
        print("=" * 50)
        print(f"  Utilisateur : {username}")
        print(f"  Scope       : {scope or 'user'}")
        print(f"  Tenant      : {tenant_id or 'N/A'}")
        print(f"  Nouveau MDP : {new_password}")
        if generated:
            print("  (généré automatiquement)")
        print("=" * 50)
        print("  L'utilisateur devra changer ce mot de passe")
        print("  à sa prochaine connexion.")
        print("=" * 50 + "\n")

    finally:
        conn.close()


def main():
    _load_env()

    parser = argparse.ArgumentParser(
        description="Outil de gestion des mots de passe Raya",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python reset_admin_password.py --list
  python reset_admin_password.py guillaume
  python reset_admin_password.py alice --password MonMdpSécurisé42!
        """,
    )
    parser.add_argument("username", nargs="?", help="Nom d'utilisateur cible")
    parser.add_argument("--password", "-p", help="Mot de passe à appliquer (optionnel, généré si absent)")
    parser.add_argument("--list", "-l", action="store_true", help="Lister tous les utilisateurs")

    args = parser.parse_args()

    if args.list:
        cmd_list()
    elif args.username:
        cmd_reset(args.username, args.password)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
