"""
Attachment Pipeline — couche universelle de compréhension de contenu.

Phase Connexions Universelles (1er mai 2026).
Voir docs/vision_connexions_universelles_01mai.md.

PHILOSOPHIE — PIPELINE EN CASCADE (decisions Q2, Q13, Q14) :
─────────────────────────────────────────────────────────────
Pour chaque pièce jointe (mail) ou fichier Drive, on applique :

  ETAPE 1 - Extraction texte (toujours, peu cher)
    PDF natif    -> pdftotext / pypdf
    PDF scanne   -> OCR Tesseract
    Word/Excel   -> python-docx / openpyxl
    Images       -> métadonnées EXIF + nom de fichier
    HTML/email   -> BeautifulSoup
    Cout : ~0.0001 EUR/document

  ETAPE 2 - Triage (a-t-on besoin de Vision IA ?)
    Approche en cascade cheap -> expensive :
    2a. Regles generiques (nom, extension, type MIME, signal contenu)
    2b. Pre-filtrage par embeddings (proximite avec categories d interet)
    2c. Triage Haiku (~0.001 EUR) si les 2a/2b indecis

  ETAPE 3 - Vision IA (sur les cas qui meritent vraiment, ~0.05 EUR)
    Anthropic Files API : upload une fois + analyse multi-aspect
    Sortie : texte + resume + tags structures (entites, montants, dates)
    Embedding global du document + embeddings par paragraphe (chunks)

REUTILISATION TABLES (Etape 1.1) :
  - attachment_index : record principal par PJ/fichier
  - attachment_chunks : embeddings 2 niveaux
  - tenant_attachment_rules : regles metier paramatrables

NOTE D IMPLEMENTATION :
  Ce module fournit l ARCHITECTURE et le SQUELETTE. Les implementations
  concretes des extractions binaires (pdftotext, Tesseract, openpyxl) seront
  ajoutees Semaines 2-6 au moment ou les connecteurs reels (mails, drive)
  seront branches dessus. Le pattern est en place pour eviter le patch
  sur patch ulterieur.
"""

import json
import logging
import os
from datetime import datetime
from typing import Optional

from app.database import get_pg_conn

logger = logging.getLogger("raya.attachment_pipeline")


# ─── REGLES GENERIQUES (NOTE GUILLAUME Q13) ───
#
# Mots-cles GENERIQUES (pas specifiques au solaire). Chaque tenant peut
# AJOUTER ses regles via tenant_attachment_rules sans toucher au code.

GENERIC_VISION_KEYWORDS = (
    # Documents commerciaux
    "facture", "invoice", "devis", "quote", "estimate", "proposal",
    "bon_commande", "purchase_order", "po_",
    # Documents contractuels
    "contrat", "contract", "agreement", "convention",
    "avenant", "amendment", "addendum",
    # Documents bancaires/financiers
    "rib", "iban", "bilan", "compte_resultat", "tva",
    # Documents administratifs
    "kbis", "siret", "siren", "attestation", "certificate",
    # Documents transport/logistique
    "bl_", "bordereau", "delivery_note",
)

GENERIC_VISION_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".heic", ".webp"}


# ─── PIPELINE PRINCIPAL ───

def process_attachment(
    tenant_id: str,
    username: str,
    source_type: str,
    source_ref: str,
    file_name: str,
    file_bytes: bytes,
    mime_type: Optional[str] = None,
    connection_id: Optional[int] = None,
) -> dict:
    """Traite une pièce jointe ou un fichier de bout en bout.

    Args:
        tenant_id: tenant proprietaire
        username: utilisateur proprietaire
        source_type: 'mail_attachment' / 'drive_file' / etc.
        source_ref: identifiant unique (mail_id pour PJ, file_id pour Drive)
        file_name: nom du fichier
        file_bytes: contenu binaire
        mime_type: type MIME (deduit du filename si non fourni)
        connection_id: connexion d origine (pour tracabilite)

    Returns:
        Dict avec :
            - attachment_id : id en base
            - text_content : extraction etape 1
            - vision_processed : bool, True si Vision IA appelee
            - tags : dict des tags si Vision faite
            - status : 'ok' / 'error'
    """
    file_size = len(file_bytes)
    if mime_type is None:
        mime_type = _guess_mime_type(file_name)

    # ETAPE 1 : extraction texte (toujours)
    try:
        text_content = extract_text(file_bytes, file_name, mime_type)
    except Exception as e:
        logger.error("[Pipeline] Extraction echouee %s : %s",
                     file_name, str(e)[:200])
        text_content = ""

    # ETAPE 2 : triage
    needs_vision = _should_apply_vision(
        tenant_id=tenant_id,
        file_name=file_name,
        mime_type=mime_type,
        text_content=text_content,
    )

    summary_content = None
    tags = None
    embedding_global = None
    chunks_data = []
    vision_processed = False

    # ETAPE 3 : Vision IA si necessaire
    if needs_vision:
        try:
            vision_result = apply_vision_ia(
                file_bytes=file_bytes,
                file_name=file_name,
                mime_type=mime_type,
                text_content=text_content,
            )
            summary_content = vision_result.get("summary")
            tags = vision_result.get("tags")
            embedding_global = vision_result.get("embedding_global")
            chunks_data = vision_result.get("chunks", [])
            vision_processed = True
        except Exception as e:
            logger.error("[Pipeline] Vision IA echouee %s : %s",
                         file_name, str(e)[:200])

    # Si pas de Vision : on calcule quand meme l embedding global du texte
    # extrait pour permettre les recherches semantiques de base.
    if embedding_global is None and text_content:
        try:
            embedding_global = compute_embedding(text_content[:4000])
        except Exception as e:
            logger.debug("[Pipeline] Embedding base echec : %s", str(e)[:200])

    # Stockage dans attachment_index + attachment_chunks
    attachment_id = _store_attachment(
        tenant_id=tenant_id,
        username=username,
        source_type=source_type,
        source_ref=source_ref,
        connection_id=connection_id,
        file_name=file_name,
        file_size=file_size,
        mime_type=mime_type,
        text_content=text_content,
        summary_content=summary_content,
        tags=tags,
        embedding_global=embedding_global,
        vision_processed=vision_processed,
    )

    if attachment_id and chunks_data:
        _store_chunks(attachment_id, chunks_data)

    return {
        "status": "ok" if attachment_id else "error",
        "attachment_id": attachment_id,
        "text_content": text_content,
        "vision_processed": vision_processed,
        "tags": tags,
    }


# ─── ETAPE 1 : EXTRACTION TEXTE ───

def extract_text(file_bytes: bytes, file_name: str,
                 mime_type: str) -> str:
    """Extrait le texte d un fichier selon son type.

    NOTE : implémentations binaires complètes (pdftotext, Tesseract,
    python-docx, openpyxl) seront ajoutées au moment ou les connecteurs
    reels (mail, drive) seront branches sur ce pipeline (Semaines 2-6).
    Le squelette ci-dessous montre la dispatch logique mais retourne
    actuellement une chaine vide pour les types binaires.
    """
    name_lower = file_name.lower()

    # Texte / HTML
    if mime_type and ("text/plain" in mime_type or name_lower.endswith(".txt")):
        try:
            return file_bytes.decode("utf-8", errors="replace")[:50000]
        except Exception:
            return ""

    if mime_type and ("text/html" in mime_type or name_lower.endswith(".html")):
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(file_bytes, "html.parser")
            return soup.get_text(separator=" ", strip=True)[:50000]
        except Exception:
            return file_bytes.decode("utf-8", errors="replace")[:50000]

    # PDF
    if name_lower.endswith(".pdf") or (mime_type and "pdf" in mime_type):
        try:
            from pypdf import PdfReader
            from io import BytesIO
            reader = PdfReader(BytesIO(file_bytes))
            text_parts = []
            for page in reader.pages[:50]:  # limite a 50 pages
                try:
                    text_parts.append(page.extract_text() or "")
                except Exception:
                    pass
            return "\n".join(text_parts)[:50000]
        except Exception as e:
            logger.debug("[Pipeline] PDF extract echec %s : %s",
                         file_name, str(e)[:100])
            return ""

    # Word (.docx) - implementation a brancher Semaines 2-6
    # Excel (.xlsx) - implementation a brancher Semaines 2-6
    # Images (jpg, png) - extraction EXIF + nom uniquement pour le moment
    if any(name_lower.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".heic", ".webp")):
        # Pour les images, le "texte" extrait = le nom du fichier + metadonnees
        # de base. La vraie comprehension passe par Vision IA (Etape 3).
        return f"[IMAGE: {file_name}]"

    # Type non reconnu
    return ""


# ─── ETAPE 2 : TRIAGE ───

def _should_apply_vision(tenant_id: str, file_name: str, mime_type: str,
                         text_content: str) -> bool:
    """Decide si Vision IA doit etre appliquee au document.

    Cascade en 3 etapes (decision Q13) :
      2a. Regles generiques (instantane, gratuit)
      2b. Pre-filtrage par embeddings (cheap, 0.0001 EUR)
      2c. Triage Haiku (cheap, 0.001 EUR)
    """
    name_lower = file_name.lower()
    ext = "." + name_lower.rsplit(".", 1)[-1] if "." in name_lower else ""

    # 2a. REGLES GENERIQUES
    # Mot-cle commercial/contractuel dans le nom
    for kw in GENERIC_VISION_KEYWORDS:
        if kw in name_lower:
            return True

    # Image standalone (pas signature email)
    if ext in GENERIC_VISION_EXTENSIONS and mime_type and "image" in mime_type:
        # Filet : on ignore les images < 20 KB (= souvent des signatures email)
        # Le size n est pas dispo ici, on laisse le filtre se faire en amont
        return True

    # PDF avec peu de texte extrait (probablement un scan)
    if ext == ".pdf" and len(text_content) < 100:
        return True

    # 2a etendu : regles tenant-specifiques (tenant_attachment_rules)
    tenant_rules = _get_tenant_rules(tenant_id)
    for rule in tenant_rules:
        if not rule.get("enabled"):
            continue
        pattern = rule.get("rule_pattern") or ""
        if pattern and pattern.lower() in name_lower:
            action = rule.get("rule_action")
            if action == "force_vision":
                return True
            if action == "skip_vision":
                return False

    # 2b. PRE-FILTRAGE PAR EMBEDDINGS
    # Si on a du texte extrait, comparer aux vecteurs de reference des
    # categories metier du tenant. Si proximite > seuil -> Vision.
    # NOTE : ce mecanisme necessite des "vecteurs de reference" stockes
    # par tenant. A construire au cas par cas. Pour l instant on saute
    # cette etape (placeholder) - sera affine quand les premiers
    # connecteurs alimenteront le systeme.
    if text_content and len(text_content) > 200:
        # TODO: implementer la comparaison aux vecteurs de reference
        # tenant_categories. Quand fait, decommenter :
        # if embeddings_match_category(text_content, tenant_id):
        #     return True
        pass

    # 2c. TRIAGE HAIKU (placeholder)
    # NOTE : si on arrive ici, on peut poser la question a Haiku :
    # "Ce document merite-t-il une analyse approfondie ?"
    # Cout : ~0.001 EUR. Implementation a faire au moment du branchement
    # des premiers connecteurs (pour eviter d ouvrir un appel API non utilise).

    # Defaut : pas de Vision (decision Q2 = texte par defaut)
    return False


def _get_tenant_rules(tenant_id: str) -> list:
    """Charge les regles metier du tenant depuis tenant_attachment_rules."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT rule_name, rule_pattern, rule_action, rule_priority, enabled
            FROM tenant_attachment_rules
            WHERE tenant_id = %s AND enabled = TRUE
            ORDER BY rule_priority DESC
        """, (tenant_id,))
        return [{
            "rule_name": r[0], "rule_pattern": r[1],
            "rule_action": r[2], "rule_priority": r[3], "enabled": r[4],
        } for r in c.fetchall()]
    except Exception:
        return []
    finally:
        if conn: conn.close()


# ─── ETAPE 3 : VISION IA ───

def apply_vision_ia(file_bytes: bytes, file_name: str, mime_type: str,
                    text_content: str) -> dict:
    """Applique Claude Vision IA sur le document via Anthropic Files API.

    NOTE : implementation à brancher quand les premiers connecteurs en
    auront besoin (Semaines 2-6). L API Files d Anthropic permet :
      - Upload une fois, multi-analyses (texte + résume + tags)
      - Économie ~30 pct par rapport à 3 appels séparés (decision E2)

    Pseudocode :
      1. anthropic.files.upload(file_bytes, name=file_name)
      2. Appel Sonnet 4 avec file_id + 3 questions structurees
      3. Parsing de la reponse en sortie structuree
      4. Calcul des embeddings global + chunks

    Pour le squelette, on retourne un dict vide qui declenche le fallback
    'embedding du texte extrait' dans process_attachment.
    """
    return {
        "summary": None,
        "tags": None,
        "embedding_global": None,
        "chunks": [],
    }


def compute_embedding(text: str) -> Optional[list]:
    """Calcule un embedding 1536d pour un texte.

    NOTE : utilise OpenAI text-embedding-3-small (deja le standard Raya
    pour les autres tables vector(1536)). A cabler avec le client OpenAI
    existant (cf app/embeddings.py probablement).
    """
    try:
        # Lazy import pour ne pas charger le client si pas necessaire
        try:
            from app.embeddings import get_embedding
            return get_embedding(text)
        except ImportError:
            # Fallback OpenAI direct
            import openai
            openai.api_key = os.getenv("OPENAI_API_KEY", "")
            if not openai.api_key:
                return None
            resp = openai.embeddings.create(
                model="text-embedding-3-small",
                input=text[:8000],
            )
            return resp.data[0].embedding
    except Exception as e:
        logger.debug("[Pipeline] compute_embedding echec : %s", str(e)[:200])
        return None


# ─── STOCKAGE ───

def _store_attachment(
    tenant_id: str, username: str, source_type: str, source_ref: str,
    connection_id: Optional[int], file_name: str, file_size: int,
    mime_type: str, text_content: str, summary_content: Optional[str],
    tags: Optional[dict], embedding_global: Optional[list],
    vision_processed: bool,
) -> Optional[int]:
    """UPSERT dans attachment_index. Retourne l id."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO attachment_index
              (tenant_id, username, source_type, source_ref, connection_id,
               file_name, file_size, mime_type, text_content,
               summary_content, tags, embedding_global, vision_processed,
               created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s,
                    NOW(), NOW())
            ON CONFLICT (source_type, source_ref) DO UPDATE SET
              text_content = EXCLUDED.text_content,
              summary_content = COALESCE(EXCLUDED.summary_content, attachment_index.summary_content),
              tags = COALESCE(EXCLUDED.tags, attachment_index.tags),
              embedding_global = COALESCE(EXCLUDED.embedding_global, attachment_index.embedding_global),
              vision_processed = attachment_index.vision_processed OR EXCLUDED.vision_processed,
              updated_at = NOW()
            RETURNING id
        """, (
            tenant_id, username, source_type, source_ref, connection_id,
            file_name, file_size, mime_type, text_content[:50000] if text_content else None,
            summary_content, json.dumps(tags) if tags else None,
            embedding_global, vision_processed,
        ))
        row = c.fetchone()
        conn.commit()
        return row[0] if row else None
    except Exception as e:
        logger.error("[Pipeline] _store_attachment echoue %s : %s",
                     file_name, str(e)[:200])
        return None
    finally:
        if conn: conn.close()


def _store_chunks(attachment_id: int, chunks_data: list) -> int:
    """Insert chunks vectorises (embeddings 2 niveaux). Retourne le nb inseres."""
    if not chunks_data:
        return 0
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        # On purge les anciens chunks (en cas de re-traitement)
        c.execute("DELETE FROM attachment_chunks WHERE attachment_id = %s",
                  (attachment_id,))
        inserted = 0
        for idx, ch in enumerate(chunks_data):
            try:
                c.execute("""
                    INSERT INTO attachment_chunks
                      (attachment_id, chunk_index, content, embedding, metadata, created_at)
                    VALUES (%s, %s, %s, %s, %s::jsonb, NOW())
                """, (
                    attachment_id, idx,
                    ch.get("content", "")[:5000],
                    ch.get("embedding"),
                    json.dumps(ch.get("metadata", {})),
                ))
                inserted += 1
            except Exception as e:
                logger.debug("[Pipeline] Chunk %d echoue : %s",
                             idx, str(e)[:100])
        conn.commit()
        return inserted
    except Exception as e:
        logger.error("[Pipeline] _store_chunks echoue : %s", str(e)[:200])
        return 0
    finally:
        if conn: conn.close()


# ─── HELPERS ───

def _guess_mime_type(file_name: str) -> str:
    """Deduit le type MIME depuis l extension."""
    name_lower = file_name.lower()
    mapping = {
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".heic": "image/heic",
        ".webp": "image/webp",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".txt": "text/plain",
        ".html": "text/html",
        ".htm": "text/html",
        ".json": "application/json",
        ".xml": "application/xml",
    }
    for ext, mime in mapping.items():
        if name_lower.endswith(ext):
            return mime
    return "application/octet-stream"
