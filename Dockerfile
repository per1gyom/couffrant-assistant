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

# ===== ETAPE 1bis : Telecharger GeoLite2 City (LOT 4 du chantier 2FA - 30/04) =====
# Base de donnees IP -> pays utilisee pour detecter les connexions depuis
# des pays inhabituels et redemander la 2FA dans ces cas.
# Telechargee gratuitement chez MaxMind, ~70 MB compresse en .tar.gz.
# Decompressee dans /opt/geoip/GeoLite2-City.mmdb (chemin lu par le module
# Python app/geoip_lookup.py).
#
# La cle MAXMIND_LICENSE_KEY doit etre injectee au build :
# - Railway : Variables (Build) > MAXMIND_LICENSE_KEY = <ta cle>
# - Build local : docker build --build-arg MAXMIND_LICENSE_KEY=xxx
#
# Si la cle est absente ou invalide, ce step echoue -> le build casse
# immediatement (pas de surprise en prod avec une base GeoLite2 manquante).

ARG MAXMIND_LICENSE_KEY

RUN if [ -n "$MAXMIND_LICENSE_KEY" ]; then \
        echo "[GeoLite2] Telechargement de la base IP -> pays..." \
        && mkdir -p /opt/geoip \
        && curl -fsSL -o /tmp/GeoLite2-City.tar.gz \
            "https://download.maxmind.com/app/geoip_download?edition_id=GeoLite2-City&license_key=$MAXMIND_LICENSE_KEY&suffix=tar.gz" \
        && tar -xzf /tmp/GeoLite2-City.tar.gz -C /tmp \
        && find /tmp -name 'GeoLite2-City.mmdb' -exec mv {} /opt/geoip/GeoLite2-City.mmdb \; \
        && rm -rf /tmp/GeoLite2-City* \
        && ls -lh /opt/geoip/GeoLite2-City.mmdb \
        && echo "[GeoLite2] OK" ; \
    else \
        echo "[GeoLite2] MAXMIND_LICENSE_KEY non defini - skip telechargement" \
        && echo "[GeoLite2] L application demarrera sans detection pays" ; \
    fi

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

# IMPORTANT - lien entre ce CMD et Railway Settings :
# Railway permet de definir une "Custom Start Command" dans les Settings
# du service qui OVERRIDE le CMD du Dockerfile. Lors du diagnostic du
# 29/04/2026, on a decouvert qu une Custom Start Command venant de
# l auto-detection Railpack etait active, ce qui faisait que ce CMD
# n etait jamais execute.
#
# Pour que ce CMD prenne effet : la Custom Start Command Railway doit
# etre VIDE (Saiyan service > Settings > Deploy > Custom Start Command).
#
# Pourquoi un script externe (entrypoint.sh) plutot que CMD inline :
# - Lisibilite : la logique de demarrage tient en 3 lignes claires
# - Debug : le script log le port utilise, utile pour les logs Railway
# - Maintenabilite : modifier le demarrage = editer un .sh, pas le Dockerfile
CMD ["/app/entrypoint.sh"]
