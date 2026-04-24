"""
Validation des nouvelles regles avant ecriture en base (B30).

Utilise la recherche semantique (RAG) pour trouver les 5 regles
les plus proches, puis soumet ce sous-ensemble cible a Opus.

Avantage : precision de detection beaucoup plus haute que la comparaison
textuelle en bloc, et cout Opus reduit (5 regles vs 30+).

Decisions :
    NEW          — regle genuinement nouvelle, inserer
    DUPLICATE    — doublon semantique d'une regle existante, ignorer
    REFINE       — ameliore une regle existante, remplacer
    SPLIT        — contient deux idees, separer en deux LEARN
    CONFLICT     — contredit une regle existante, demander a l'utilisateur
    RECATEGORIZE — texte OK mais categorie a corriger (Phase 3)
"""
import json
import re
from app.database import get_pg_conn
from app.llm_client import llm_complete


# Regex pour detecter un tag [xxx] au debut du texte d'une regle
# Ex : "[equipe] Karen adore le cafe" -> tag="equipe", texte="Karen adore le cafe"
_TAG_REGEX = re.compile(r"^\[([^\]]+)\]\s*")


def extract_tag_from_text(rule_text: str) -> tuple:
    """Extrait un tag [xxx] en debut de texte s'il existe.

    Returns:
        (tag_or_None, texte_nettoye)
    """
    if not rule_text:
        return None, rule_text or ""
    m = _TAG_REGEX.match(rule_text.strip())
    if not m:
        return None, rule_text.strip()
    return m.group(1).strip(), _TAG_REGEX.sub("", rule_text.strip()).strip()


def get_canonical_categories(username: str, tenant_id: str = None) -> list:
    """Liste des categories canoniques de l'utilisateur + leur volume.

    Utilise pour :
      - le validateur (Sonnet voit les categories existantes avant de decider)
      - le frontend (combobox categorie dans la modale d'edition)

    Retourne :
      [{"category": "Comportement", "count": 23}, ...] trie par count DESC
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        if tenant_id:
            c.execute(
                "SELECT category, COUNT(*) FROM aria_rules "
                "WHERE active=true AND username=%s "
                "AND (tenant_id=%s OR tenant_id IS NULL) "
                "AND category IS NOT NULL AND category != '' "
                "GROUP BY category ORDER BY COUNT(*) DESC",
                (username, tenant_id)
            )
        else:
            c.execute(
                "SELECT category, COUNT(*) FROM aria_rules "
                "WHERE active=true AND username=%s "
                "AND category IS NOT NULL AND category != '' "
                "GROUP BY category ORDER BY COUNT(*) DESC",
                (username,)
            )
        return [{"category": row[0], "count": row[1]} for row in c.fetchall()]
    except Exception as e:
        print(f"[rule_validator] get_canonical_categories error: {e}")
        return []
    finally:
        if conn:
            conn.close()


def validate_rule_before_save(
    username: str,
    tenant_id: str,
    category: str,
    new_rule_text: str,
) -> dict:
    """
    Valide une regle avant insertion.

    Returns:
        {
            "decision": "NEW|DUPLICATE|REFINE|SPLIT|CONFLICT",
            "rules_to_add": [{"category": str, "rule": str}],
            "rules_to_update": [{"id": int, "rule": str}],
            "rules_to_skip": [int],
            "conflict_message": str | None,
        }
    """
    similar = _find_similar_rules(new_rule_text, username, tenant_id)
    canonical_cats = get_canonical_categories(username, tenant_id)

    if not similar and not canonical_cats:
        # Premiere regle de l'utilisateur -> NEW direct, pas d'appel LLM
        return {
            "decision": "NEW",
            "rules_to_add": [{"category": category, "rule": new_rule_text}],
            "rules_to_update": [],
            "rules_to_skip": [],
            "conflict_message": None,
        }

    return _call_llm(category, new_rule_text, similar, canonical_cats)


def _find_similar_rules(rule_text: str, username: str, tenant_id: str) -> list:
    """Cherche les 5 regles existantes les plus proches semantiquement (toutes categories)."""
    try:
        from app.embedding import search_similar, is_available
        if not is_available():
            return _fallback_rules(username, tenant_id)

        rows = search_similar(
            table="aria_rules",
            username=username,
            query_text=rule_text,
            limit=5,
            tenant_id=tenant_id,
            extra_filter="active = true AND category != 'memoire'",
        )
        return rows or []
    except Exception as e:
        print(f"[rule_validator] search_similar error: {e}")
        return []


def _fallback_rules(username: str, tenant_id: str) -> list:
    """Fallback sans embedding : retourne les 10 regles actives par confiance."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id, category, rule, confidence
            FROM aria_rules
            WHERE username = %s AND active = true AND category != 'memoire'
              AND (tenant_id = %s OR tenant_id IS NULL)
            ORDER BY confidence DESC, reinforcements DESC
            LIMIT 10
        """, (username, tenant_id))
        rows = c.fetchall()
        return [{"id": r[0], "category": r[1], "rule": r[2], "confidence": float(r[3] or 0)} for r in rows]
    except Exception:
        return []
    finally:
        if conn: conn.close()


def _call_llm(category: str, new_rule: str, similar_rules: list, canonical_cats: list) -> dict:
    """Appelle Sonnet pour decider NEW/DUPLICATE/REFINE/SPLIT/CONFLICT/RECATEGORIZE.

    Phase 3 : le validateur recoit la liste des categories existantes pour que
    Sonnet puisse recommander une categorie canonique plutot qu'une nouvelle
    forme (comportement/Comportement/COMPORTEMENT -> Comportement).

    Phase 3 : extraction auto d'un tag [xxx] au debut du texte.
    """
    # Extraction du tag implicite [xxx] si present dans le texte
    extracted_tag, clean_text = extract_tag_from_text(new_rule)
    if extracted_tag and not category:
        # Si aucune categorie n'etait fournie mais qu'il y a un tag -> utilise le tag
        category = extracted_tag
        new_rule = clean_text
    elif extracted_tag:
        # Le tag est extrait du texte dans tous les cas (Sonnet decidera quoi en faire)
        new_rule = clean_text

    # Listing des categories existantes avec leur volume
    if canonical_cats:
        cats_text = "\n".join([
            f"  • {c['category']} ({c['count']} regle{'s' if c['count'] > 1 else ''})"
            for c in canonical_cats
        ])
    else:
        cats_text = "  (aucune categorie existante, creation libre)"

    # Listing des regles proches
    if similar_rules:
        rules_text = "\n".join([
            f"  [id:{r.get('id', '?')}][{r.get('category', '?')}] {r.get('rule', '')}"
            for r in similar_rules
        ])
    else:
        rules_text = "  (aucune regle similaire detectee)"

    tag_note = ""
    if extracted_tag:
        tag_note = (f"\nNOTE : le texte original commencait par un tag "
                    f"[{extracted_tag}] qui a ete retire automatiquement. "
                    f"Tu peux l'utiliser comme indication pour choisir la categorie.\n")

    prompt = f"""Tu es un validateur de regles comportementales pour un assistant IA.

Ta mission : prendre une decision PROPRE sur une nouvelle regle qu'on veut
enregistrer, en respectant la taxonomie existante.

===== NOUVELLE REGLE A EVALUER =====
Categorie proposee : "{category}"
Texte : "{new_rule}"{tag_note}

===== CATEGORIES CANONIQUES DE L'UTILISATEUR =====
{cats_text}

===== REGLES EXISTANTES PROCHES SEMANTIQUEMENT =====
{rules_text}

===== TA DECISION =====
Retourne UNIQUEMENT un objet JSON (sans markdown) :
{{
  "decision": "NEW|DUPLICATE|REFINE|SPLIT|CONFLICT|RECATEGORIZE",
  "reasoning": "explication courte en une phrase",
  "rules_to_add": [{{"category": "...", "rule": "..."}}],
  "rules_to_update": [{{"id": 0, "rule": "...", "category": "..."}}],
  "rules_to_skip": [],
  "conflict_message": null
}}

CRITERES DE DECISION :

- NEW : regle genuinement nouvelle.
  -> rules_to_add contient la regle AVEC UNE CATEGORIE CANONIQUE
  -> Tu DOIS utiliser UNE categorie existante si elle colle (meme a 80%).
  -> Creer une NOUVELLE categorie est AUTORISE mais seulement si aucune
     existante ne correspond vraiment. Respecte le style : "Majuscule initiale,
     Espaces normaux" (ex: "Tri mails", "Projets & roadmap").
  -> NE JAMAIS utiliser "auto", "general", "autre" ou similaire.

- RECATEGORIZE : le texte est OK mais la categorie proposee n'est pas canonique
  ou ne colle pas au contenu.
  -> rules_to_add contient la regle avec la categorie CORRIGEE
  Exemples : proposee="comportement" mais "Comportement" existe -> corrige
             proposee="tri-mails" mais "Tri mails" existe -> corrige
             proposee="general" -> choisis une vraie categorie

- DUPLICATE : semantiquement identique a une regle existante
  -> rules_to_add VIDE, rules_to_skip = [id de la regle conservee]

- REFINE : ameliore une regle existante (plus precise, mieux formulee)
  -> rules_to_update contient {{"id": X, "rule": "nouveau texte", "category": "..."}}
  -> rules_to_add VIDE

- SPLIT : la regle contient 2+ idees distinctes
  -> rules_to_add contient PLUSIEURS regles separees, chacune avec une categorie canonique

- CONFLICT : contredit une regle existante
  -> rules_to_add VIDE, conflict_message explique le conflit en francais

Retourne UNIQUEMENT le JSON brut. AUCUNE explication ni balise markdown."""

    try:
        result = llm_complete(
            messages=[{"role": "user", "content": prompt}],
            model_tier="smart",  # Phase 3 : Sonnet (suffisant + rapide) au lieu d'Opus
            max_tokens=1024,
        )
        text = result["text"].strip()
        # Strip markdown fences si presentes
        if "```" in text:
            parts = text.split("```")
            for p in parts:
                p = p.strip()
                if p.startswith("json"):
                    p = p[4:].strip()
                try:
                    return _normalize(json.loads(p), category, new_rule)
                except Exception:
                    pass
        return _normalize(json.loads(text), category, new_rule)
    except Exception as e:
        print(f"[rule_validator] LLM error: {e} — fallback NEW")
        return {
            "decision": "NEW",
            "rules_to_add": [{"category": category, "rule": new_rule}],
            "rules_to_update": [],
            "rules_to_skip": [],
            "conflict_message": None,
        }


def _normalize(data: dict, category: str, new_rule: str) -> dict:
    """Normalise la reponse LLM avec valeurs par defaut."""
    decision = data.get("decision", "NEW").upper()
    # Phase 3 : ajout de RECATEGORIZE comme decision valide
    if decision not in ("NEW", "DUPLICATE", "REFINE", "SPLIT", "CONFLICT", "RECATEGORIZE"):
        decision = "NEW"

    rules_to_add = data.get("rules_to_add", [])
    if decision == "NEW" and not rules_to_add:
        rules_to_add = [{"category": category, "rule": new_rule}]
    # RECATEGORIZE se traite comme NEW mais avec la categorie corrigee par le LLM
    if decision == "RECATEGORIZE" and not rules_to_add:
        rules_to_add = [{"category": category, "rule": new_rule}]

    return {
        "decision": decision,
        "rules_to_add": rules_to_add,
        "rules_to_update": data.get("rules_to_update", []),
        "rules_to_skip": data.get("rules_to_skip", []),
        "conflict_message": data.get("conflict_message"),
    }


def apply_validation_result(result: dict, username: str, tenant_id: str) -> list:
    """
    Applique le resultat de validation en base.
    Retourne la liste des messages de confirmation.
    """
    from app.memory_loader import save_rule
    messages = []

    for item in result.get("rules_to_add", []):
        try:
            save_rule(item["category"], item["rule"], "auto", 0.7, username,
                      tenant_id=tenant_id)
            messages.append(f"+ [{item['category']}]")
        except Exception as e:
            print(f"[rule_validator] save_rule error: {e}")

    for item in result.get("rules_to_update", []):
        conn = None
        try:
            conn = get_pg_conn()
            c = conn.cursor()
            # Phase 3 : UPDATE peut maintenant changer category en plus de rule
            if "category" in item and item["category"]:
                c.execute(
                    "UPDATE aria_rules SET rule = %s, category = %s, updated_at = NOW() "
                    "WHERE id = %s AND username = %s "
                    "AND (tenant_id = %s OR tenant_id IS NULL)",
                    (item["rule"], item["category"], item["id"], username, tenant_id),
                )
            else:
                c.execute(
                    "UPDATE aria_rules SET rule = %s, updated_at = NOW() "
                    "WHERE id = %s AND username = %s "
                    "AND (tenant_id = %s OR tenant_id IS NULL)",
                    (item["rule"], item["id"], username, tenant_id),
                )
            conn.commit()
            messages.append(f"~ regle #{item['id']} mise a jour")
        except Exception as e:
            print(f"[rule_validator] update_rule error: {e}")
        finally:
            if conn: conn.close()

    return messages
