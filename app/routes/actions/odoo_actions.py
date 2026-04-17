"""
Gestion des actions Odoo (ODOO_SEARCH, ODOO_CREATE, ODOO_UPDATE, ODOO_NOTE).
Permet à Raya d'interroger et manipuler Odoo en conversation.
"""
import re
import json
from app.activity_log import log_activity


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
            if results:
                # Formater proprement pour le chat
                lines = []
                for r in results[:30]:
                    parts = [f"{k}: {v}" for k, v in r.items() if k != 'id' and v]
                    lines.append(f"  #{r.get('id','')} — {' | '.join(parts[:5])}")
                confirmed.append(f"📊 Odoo {model} ({len(results)} résultat{'s' if len(results)>1 else ''}) :\n" + "\n".join(lines))
            else:
                confirmed.append(f"📊 Odoo {model} — aucun résultat.")
            log_activity(username, "odoo_search", model, f"{len(results or [])} results", tenant_id=tenant_id)
        except Exception as e:
            confirmed.append(f"❌ Odoo : {str(e)[:150]}")

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
