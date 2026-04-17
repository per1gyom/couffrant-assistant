"""
Gestion des actions Odoo (ODOO_SEARCH, ODOO_CREATE, ODOO_UPDATE, ODOO_NOTE).
Permet à Raya d'interroger et manipuler Odoo en conversation.
"""
import re
import json
from app.activity_log import log_activity


def _handle_odoo_actions(response, username, tenant_id, tools):
    confirmed = []
    if not tools.get("odoo_enabled"):
        return confirmed

    odoo_access = tools.get("odoo_access", "read_only")

    # ODOO_SEARCH : [ACTION:ODOO_SEARCH:model|fields|domain_json]
    for match in re.finditer(r'\[ACTION:ODOO_SEARCH:([^\|]+)\|([^\|]+)\|(.+?)\]', response, re.DOTALL):
        model = match.group(1).strip()
        fields_str = match.group(2).strip()
        domain_str = match.group(3).strip()
        try:
            from app.connectors.odoo_connector import odoo_call
            fields = [f.strip() for f in fields_str.split(',')]
            # Nettoyer le domaine JSON
            domain_str = domain_str.replace("'", '"')
            domain = json.loads(domain_str) if domain_str and domain_str != '[]' else []
            results = odoo_call(
                model=model, method="search_read",
                kwargs={"domain": domain, "fields": fields, "limit": 50}
            )
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
        for match in re.finditer(r'\[ACTION:ODOO_CREATE:([^\|]+)\|(.+?)\]', response, re.DOTALL):
            model = match.group(1).strip()
            values_str = match.group(2).strip().replace("'", '"')
            try:
                from app.connectors.odoo_connector import odoo_call
                values = json.loads(values_str)
                result_id = odoo_call(model=model, method="create", args=[values])
                confirmed.append(f"✅ Odoo : {model} #{result_id} créé.")
                log_activity(username, "odoo_create", model, str(result_id), tenant_id=tenant_id)
            except Exception as e:
                confirmed.append(f"❌ Odoo création : {str(e)[:150]}")

        # ODOO_UPDATE : [ACTION:ODOO_UPDATE:model|id|values_json]
        for match in re.finditer(r'\[ACTION:ODOO_UPDATE:([^\|]+)\|(\d+)\|(.+?)\]', response, re.DOTALL):
            model = match.group(1).strip()
            record_id = int(match.group(2))
            values_str = match.group(3).strip().replace("'", '"')
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
