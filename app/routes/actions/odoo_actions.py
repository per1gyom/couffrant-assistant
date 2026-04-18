"""
Gestion des actions Odoo (ODOO_SEARCH, ODOO_CREATE, ODOO_UPDATE, ODOO_NOTE).
Permet à Raya d'interroger et manipuler Odoo en conversation.
"""
import re
import json
from app.activity_log import log_activity


def _format_field_value(v) -> str:
    """
    Formate la valeur d'un champ Odoo pour affichage lisible au LLM.

    Cas gérés :
    - None/False/'' → "" (sera filtré avant par le check `if v`)
    - many2one Odoo [id, "Nom"] → "Nom"
    - many2many enrichi [{"id": X, "name": "Y"}, ...] → "Y1, Y2, Y3"
    - many2many brut [14, 13, 15] → "[14, 13, 15]" (fallback, pas de résolution)
    - int/float/str → str(v)
    - dict → json court (rare)
    """
    # many2one au format Odoo [id, "Nom"] — 2 éléments, int + str
    if isinstance(v, list) and len(v) == 2 and isinstance(v[0], int) and isinstance(v[1], str):
        return v[1]
    # Liste enrichie par odoo_enrich : [{"id": X, "name": "Y"}, ...]
    if isinstance(v, list) and v and all(isinstance(x, dict) and "name" in x for x in v):
        names = [x.get("name") or f"#{x.get('id','?')}" for x in v]
        return ", ".join(names)
    # Liste d'IDs bruts non résolus
    if isinstance(v, list) and v and all(isinstance(x, int) for x in v):
        return ", ".join(f"#{i}" for i in v)
    # Dict simple (rare)
    if isinstance(v, dict):
        return json.dumps(v, ensure_ascii=False)[:100]
    return str(v)


def _extract_action_tags(text, action_type):
    """Extrait les tags ACTION avec gestion des crochets imbriqués (domaines Odoo JSON)."""
    prefix = f'[ACTION:{action_type}:'
    results = []
    i = 0
    while i < len(text):
        idx = text.find(prefix, i)
        if idx == -1:
            break
        depth = 0
        j = idx
        while j < len(text):
            if text[j] == '[':
                depth += 1
            elif text[j] == ']':
                depth -= 1
                if depth == 0:
                    content = text[idx + len(prefix):j]
                    results.append(content)
                    j += 1
                    break
            j += 1
        i = j if j > idx else idx + 1
    return results


def _safe_parse_domain(domain_str):
    """Parse un domaine Odoo de manière robuste (simple quotes, vide, malformé)."""
    if not domain_str or domain_str.strip() in ('', '[]'):
        return []
    cleaned = domain_str.strip().replace("'", '"')
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return []


def _handle_odoo_actions(response, username, tenant_id, tools):
    confirmed = []
    if not tools.get("odoo_enabled"):
        return confirmed

    odoo_access = tools.get("odoo_access", "read_only")

    # ODOO_SEARCH : [ACTION:ODOO_SEARCH:model|fields|domain_json]
    odoo_searches = _extract_action_tags(response, "ODOO_SEARCH")
    if odoo_searches:
        from app.logging_config import get_logger as _gl
        _gl("raya.odoo").info("[Odoo] %d ODOO_SEARCH tag(s) trouvé(s)", len(odoo_searches))
    for content in odoo_searches:
        parts = content.split('|', 2)
        model = parts[0].strip()
        fields_str = parts[1].strip() if len(parts) > 1 else "name"
        domain_str = parts[2].strip() if len(parts) > 2 else "[]"
        try:
            from app.connectors.odoo_connector import odoo_call
            fields = [f.strip() for f in fields_str.split(',')]
            domain = _safe_parse_domain(domain_str)
            try:
                results = odoo_call(
                    model=model, method="search_read",
                    kwargs={"domain": domain, "fields": fields, "limit": 50}
                )
            except Exception as field_err:
                # Retry avec champs minimaux si KeyError (champ inconnu)
                if "KeyError" in str(field_err) or "field" in str(field_err).lower():
                    results = odoo_call(
                        model=model, method="search_read",
                        kwargs={"domain": domain, "fields": ["name"], "limit": 50}
                    )
                    confirmed.append(f"⚠️ Certains champs demandés n'existent pas sur {model}. Résultats avec champs par défaut :")
                else:
                    raise
            # ENRICHISSEMENT : résoudre les IDs en noms (user_ids, partner_ids,
            # attendee_ids, etc.) pour que Raya voit "Aurélien, Benoît" au lieu
            # de "[14, 13]". Fait en best-effort : si l'enrichissement échoue
            # (modèle inconnu, appel Odoo qui foire), on continue avec les
            # résultats bruts — pas de régression.
            try:
                from app.connectors.odoo_enrich import enrich_records
                results = enrich_records(model, results)
            except Exception as enrich_err:
                from app.logging_config import get_logger as _gl
                _gl("raya.odoo").warning(
                    "[Odoo] Enrichissement échoué pour %s: %s",
                    model, str(enrich_err)[:150]
                )
            if results:
                # Formater proprement pour le chat, avec résolution des IDs
                # en noms via _format_field_value.
                lines = []
                for r in results[:30]:
                    parts = [f"{k}: {_format_field_value(v)}" for k, v in r.items() if k != 'id' and v]
                    lines.append(f"  #{r.get('id','')} — {' | '.join(parts[:5])}")
                confirmed.append(f"📊 Odoo {model} ({len(results)} résultat{'s' if len(results)>1 else ''}) :\n" + "\n".join(lines))
            else:
                confirmed.append(f"📊 Odoo {model} — aucun résultat.")
            log_activity(username, "odoo_search", model, f"{len(results or [])} results", tenant_id=tenant_id)
        except Exception as e:
            confirmed.append(f"❌ Odoo : {str(e)[:150]}")

    # ODOO_CLIENT_360 : [ACTION:ODOO_CLIENT_360:nom_ou_id]
    # Vue 360° agrégée d'un client : contact + chantiers + factures +
    # paiements + leads + tickets + mails + indicateurs + anomalies.
    # En 1 tag au lieu de 6-8 ODOO_SEARCH séparés. Voir odoo_client_360.py
    # pour la liste des données et la détection d'anomalies intelligente.
    for content in _extract_action_tags(response, "ODOO_CLIENT_360"):
        key = content.strip()
        if not key:
            confirmed.append("❌ CLIENT_360 : clé manquante (attendu : nom ou ID partner)")
            continue
        try:
            from app.connectors.odoo_client_360 import get_client_360, format_client_360
            data = get_client_360(key, include_mails=True, mail_username=username)
            formatted = format_client_360(data)
            confirmed.append(formatted)
            partner_id = (data.get("partner") or {}).get("id", "?")
            log_activity(username, "odoo_client_360", str(partner_id),
                         f"key={key[:50]}", tenant_id=tenant_id)
        except Exception as e:
            confirmed.append(f"❌ CLIENT_360 : {str(e)[:200]}")

    # ODOO_MODELS : [ACTION:ODOO_MODELS:] — liste les modèles accessibles
    for _ in re.finditer(r'\[ACTION:ODOO_MODELS:\]', response):
        try:
            from app.connectors.odoo_connector import odoo_call
            models = odoo_call(
                model="ir.model", method="search_read",
                kwargs={"domain": [["transient", "=", False]], "fields": ["model", "name"], "limit": 100, "order": "model"}
            )
            if models:
                lines = [f"  {m['model']} — {m['name']}" for m in models[:60]]
                confirmed.append(f"📋 Modèles Odoo ({len(models)}) :\n" + "\n".join(lines))
            log_activity(username, "odoo_models", "", f"{len(models or [])} models", tenant_id=tenant_id)
        except Exception as e:
            confirmed.append(f"❌ Odoo modèles : {str(e)[:150]}")


    # ODOO_CREATE : [ACTION:ODOO_CREATE:model|values_json]
    if odoo_access == "full":
        for content in _extract_action_tags(response, "ODOO_CREATE"):
            parts = content.split('|', 1)
            model = parts[0].strip()
            values_str = parts[1].strip().replace("'", '"') if len(parts) > 1 else "{}"
            try:
                from app.connectors.odoo_connector import odoo_call
                values = json.loads(values_str)
                result_id = odoo_call(model=model, method="create", args=[values])
                confirmed.append(f"✅ Odoo : {model} #{result_id} créé.")
                log_activity(username, "odoo_create", model, str(result_id), tenant_id=tenant_id)
            except Exception as e:
                confirmed.append(f"❌ Odoo création : {str(e)[:150]}")

        # ODOO_UPDATE : [ACTION:ODOO_UPDATE:model|id|values_json]
        for content in _extract_action_tags(response, "ODOO_UPDATE"):
            parts = content.split('|', 2)
            if len(parts) < 3:
                continue
            model = parts[0].strip()
            try:
                record_id = int(parts[1].strip())
            except ValueError:
                continue
            values_str = parts[2].strip().replace("'", '"')
            try:
                from app.connectors.odoo_connector import odoo_call
                values = json.loads(values_str)
                odoo_call(model=model, method="write", args=[[record_id], values])
                confirmed.append(f"✅ Odoo : {model} #{record_id} mis à jour.")
                log_activity(username, "odoo_update", model, str(record_id), tenant_id=tenant_id)
            except Exception as e:
                confirmed.append(f"❌ Odoo mise à jour : {str(e)[:150]}")

        # ODOO_NOTE : [ACTION:ODOO_NOTE:partner_id|texte]
        for match in re.finditer(r'\[ACTION:ODOO_NOTE:(\d+)\|(.+?)\]', response, re.DOTALL):
            partner_id = int(match.group(1))
            note = match.group(2).strip()
            try:
                from app.connectors.odoo_connector import add_note_to_partner
                add_note_to_partner(partner_id, note)
                confirmed.append(f"✅ Note ajoutée au contact #{partner_id}.")
                log_activity(username, "odoo_note", str(partner_id), note[:100], tenant_id=tenant_id)
            except Exception as e:
                confirmed.append(f"❌ Odoo note : {str(e)[:150]}")

    return confirmed
