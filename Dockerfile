# Dockerfile pour Raya - 29 avril 2026
#
# POURQUOI UN DOCKERFILE ?
# ========================
# Railway utilise par defaut Railpack (depuis 2025) qui ne permet pas
# d ajouter facilement des packages systeme comme pg_dump. On a besoin
# de pg_dump version 18 pour faire des backups PostgreSQL natifs
# (le serveur Railway tourne en Postgres 18.3).
#
# Sans pg_dump : fallback CSV, ~9 minutes par backup, format custom.
# Avec pg_dump : ~30-60 secondes, format SQL standard restoreable via psql.
#
# CHOIX TECHNIQUES
# ================
# - python:3.13-slim-bookworm : Debian 12 Bookworm (LTS, stable jusqu en 2028).
#   Le suffixe -slim retire les outils inutiles pour reduire la taille image.
# - postgresql-client-18 depuis le repo officiel apt.postgresql.org
#   (les depots Debian standard ne contiennent que des versions plus anciennes).
# - Build en deux temps (requirements.txt avant le code) pour optimiser
#   le cache Docker : si seul le code Python change, pas besoin de tout
#   reinstaller.

FROM python:3.13-slim-bookworm

# ===== ETAPE 1 : Installer pg_dump 18 =====
# On ajoute le repository officiel PostgreSQL pour avoir la version 18
# (matche la version du serveur Railway, regle stricte de PostgreSQL :
# pg_dump doit avoir la meme version majeure que le serveur).

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        gnupg \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
       | gpg --dearmor -o /etc/apt/keyrings/postgresql.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/postgresql.gpg] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
       > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-18 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ===== GARDE-FOU =====
# Si pg_dump 18 n est pas dispo, le BUILD CASSE ICI (avant deploiement),
# au lieu de silently passer et avoir un bug en prod.
RUN pg_dump --version

# ===== ETAPE 2 : Code Python =====

WORKDIR /app

# requirements.txt copie AVANT le code pour optimiser le cache Docker :
# si seul le code change (sans nouvelle dependance), Docker reutilise
# le layer pip install (gain ~30-60 sec a chaque rebuild).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie de tout le code applicatif (.dockerignore exclut les non-pertinents)
COPY . .

# Garantie que entrypoint.sh est executable (au cas ou le bit + serait perdu
# par certains systemes de fichiers entre Mac et Linux)
RUN chmod +x /app/entrypoint.sh

# ===== ETAPE 3 : Lancement =====

# Railway injecte $PORT a runtime, fallback 8080 en local
EXPOSE 8080

# On utilise un script externe pour la substitution de variables.
# La syntaxe CMD ["sh", "-c", "..."] ne marche pas sur Railway car la
# variable ${PORT} n est pas substituee correctement (raison inconnue,
# probablement un wrapper Railway). Un script .sh externe garantit la
# bonne resolution.
CMD ["/app/entrypoint.sh"]
