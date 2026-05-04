"""
Requetes SQL du dashboard Raya.
Extrait de dashboard_service.py -- SPLIT-7.
"""
import json
from app.database import get_pg_conn
from app.dashboard_service import (
    normalize_text, build_group_key, choose_group_title,
    choose_group_priority, choose_group_reason, choose_group_action, build_summary,
)


def get_dashboard(days: int = 2, username: str = None,
                  tenant_id: str = None) -> dict:
    conn = get_pg_conn()
    c = conn.cursor()
    start_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
    c.execute("""
        SELECT id, message_id, received_at, from_email, display_title,
               category, priority, reason, suggested_action, short_summary,
               suggested_reply, response_type, missing_fields, confidence_level,
               raw_body_preview
        FROM mail_memory
        WHERE username = %s
          AND (tenant_id = %s OR tenant_id IS NULL)
          AND received_at >= %s
          AND deleted_at IS NULL
        ORDER BY received_at DESC
    """, (username, tenant_id, start_date))
    columns = [desc[0] for desc in c.description]
    rows = [dict(zip(columns, row)) for row in c.fetchall()]
    conn.close()

    regroupement_rules = get_rules_by_category(username, "Regroupement")

    groups = defaultdict(list)
    for row in rows:
        key = build_group_key(row, regroupement_rules)
        groups[key].append(row)

    grouped_items = []
    for _, items in groups.items():
        items_sorted = sorted(items, key=lambda x: x["received_at"] or "", reverse=True)
        missing_fields = items_sorted[0].get("missing_fields")
        if not missing_fields:
            missing_fields = []
        elif isinstance(missing_fields, str):
            try: missing_fields = json.loads(missing_fields)
            except Exception: missing_fields = []

        grouped_items.append({
            "id": items_sorted[0].get("id"),
            "topic": choose_group_title(items_sorted, regroupement_rules),
            "priority": choose_group_priority(items_sorted),
            "reason": choose_group_reason(items_sorted),
            "action": choose_group_action(items_sorted),
            "summary": build_summary(items_sorted),
            "mail_count": len(items_sorted),
            "latest_date": items_sorted[0].get("received_at"),
            "category": items_sorted[0].get("category"),
            "senders": list(dict.fromkeys([i.get("from_email") for i in items_sorted if i.get("from_email")])),
            "suggested_reply": items_sorted[0].get("suggested_reply"),
            "response_type": items_sorted[0].get("response_type"),
            "missing_fields": missing_fields,
            "confidence_level": items_sorted[0].get("confidence_level"),
            "raw_body_preview": items_sorted[0].get("raw_body_preview"),
        })

    priority_order = {"haute": 0, "moyenne": 1, "basse": 2}
    grouped_items.sort(key=lambda x: (
        priority_order.get(x["priority"], 99), x.get("latest_date") or ""
    ))

    urgent, normal, low = [], [], []
    for item in grouped_items:
        bp = parse_business_priority(item.get("category", ""), item.get("topic", ""), username)
        if bp == "urgent": urgent.append(item)
        elif bp == "faible": low.append(item)
        else: normal.append(item)

    return {
        "days": days,
        "username": username,
        "count": len(grouped_items),
        "urgent": urgent,
        "normal": normal,
        "low": low,
        "all": grouped_items,
    }



def get_costs_dashboard(tenant_id: str = None, days: int = 30) -> dict:
    """
    Retourne les donnees de couts LLM pour le dashboard admin (5F-1).
    Si tenant_id fourni, filtre sur ce tenant. Sinon, tous les tenants.

    Retourne :
    {
        "period_days": int,
        "total_cost_usd": float,
        "total_input_tokens": int,
        "total_output_tokens": int,
        "by_model": [{"model": str, "calls": int, "tokens": int, "cost_usd": float}],
        "by_user": [{"username": str, "calls": int, "tokens": int, "cost_usd": float}],
        "by_purpose": [{"purpose": str, "calls": int, "tokens": int, "cost_usd": float}],
        "by_day": [{"date": str, "calls": int, "cost_usd": float}],
    }
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()

        # Filtre tenant optionnel
        tenant_filter = "AND tenant_id = %s" if tenant_id else ""
        params_base = [days]
        if tenant_id:
            params_base.append(tenant_id)

        # Totaux
        c.execute(f"""
            SELECT
                COUNT(*) AS calls,
                COALESCE(SUM(input_tokens), 0) AS total_input,
                COALESCE(SUM(output_tokens), 0) AS total_output,
                COALESCE(SUM(COALESCE(cost_usd_estimate, 0)), 0) AS total_cost
            FROM llm_usage
            WHERE created_at > NOW() - INTERVAL '%s days'
            {tenant_filter}
        """, params_base)
        row = c.fetchone()
        total_calls, total_input, total_output, total_cost = row

        # Par modele
        c.execute(f"""
            SELECT model, COUNT(*) AS calls,
                   COALESCE(SUM(input_tokens + output_tokens), 0) AS tokens,
                   COALESCE(SUM(COALESCE(cost_usd_estimate, 0)), 0) AS cost
            FROM llm_usage
            WHERE created_at > NOW() - INTERVAL '%s days'
            {tenant_filter}
            GROUP BY model ORDER BY cost DESC
        """, params_base)
        by_model = [
            {"model": r[0], "calls": r[1], "tokens": r[2], "cost_usd": float(r[3])}
            for r in c.fetchall()
        ]

        # Par utilisateur
        c.execute(f"""
            SELECT lu.username, u.tenant_id, COUNT(*) AS calls,
                   COALESCE(SUM(lu.input_tokens), 0)  AS input_tokens,
                   COALESCE(SUM(lu.output_tokens), 0) AS output_tokens,
                   COALESCE(SUM(lu.input_tokens + lu.output_tokens), 0) AS tokens
            FROM llm_usage lu
            LEFT JOIN users u ON u.username = lu.username
            WHERE lu.created_at > NOW() - INTERVAL '%s days'
            {tenant_filter}
            GROUP BY lu.username, u.tenant_id ORDER BY tokens DESC
        """, params_base)
        by_user = [
            {"username": r[0], "tenant_id": r[1] or "", "calls": r[2],
             "input_tokens": r[3], "output_tokens": r[4], "tokens": r[5]}
            for r in c.fetchall()
        ]

        # Par purpose
        c.execute(f"""
            SELECT COALESCE(purpose, 'unknown'), COUNT(*) AS calls,
                   COALESCE(SUM(input_tokens + output_tokens), 0) AS tokens,
                   COALESCE(SUM(COALESCE(cost_usd_estimate, 0)), 0) AS cost
            FROM llm_usage
            WHERE created_at > NOW() - INTERVAL '%s days'
            {tenant_filter}
            GROUP BY COALESCE(purpose, 'unknown') ORDER BY cost DESC
        """, params_base)
        by_purpose = [
            {"purpose": r[0], "calls": r[1], "tokens": r[2], "cost_usd": float(r[3])}
            for r in c.fetchall()
        ]

        # Par jour
        c.execute(f"""
            SELECT DATE(created_at) AS day, COUNT(*) AS calls,
                   COALESCE(SUM(COALESCE(cost_usd_estimate, 0)), 0) AS cost
            FROM llm_usage
            WHERE created_at > NOW() - INTERVAL '%s days'
            {tenant_filter}
            GROUP BY DATE(created_at) ORDER BY day DESC
        """, params_base)
        by_day = [
            {"date": str(r[0]), "calls": r[1], "cost_usd": float(r[2])}
            for r in c.fetchall()
        ]

        return {
            "period_days": days,
            "total_calls": int(total_calls),
            "total_cost_usd": float(total_cost),
            "total_input_tokens": int(total_input),
            "total_output_tokens": int(total_output),
            "by_model": by_model,
            "by_user": by_user,
            "by_purpose": by_purpose,
            "by_day": by_day,
        }
    except Exception as e:
        return {"error": str(e)[:200], "period_days": days,
                "total_cost_usd": 0.0, "total_input_tokens": 0,
                "total_output_tokens": 0, "by_model": [], "by_user": [],
                "by_purpose": [], "by_day": []}
    finally:
        if conn: conn.close()

