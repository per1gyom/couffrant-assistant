"""
Mémoire Teams pour Raya.

Philosophie :
- Le système fournit les outils, pas les règles
- Raya décide librement quand utiliser ces outils
- Les marqueurs sont posés à l'initiative de Raya, jamais automatiquement
- Raya peut mémoriser ses propres habitudes via [ACTION:LEARN:teams_ingestion|...]
"""
import re
import json
from datetime import datetime, timezone

from app.database import get_pg_conn
from app.ai_client import client
from app.config import ANTHROPIC_MODEL_FAST, ANTHROPIC_MODEL_SMART


# ─── MARQUEURS ───

def get_teams_markers(username: str, tenant_id: str | None = None) -> list:
    """
    Retourne les marqueurs que Raya a posés sur ses chats/canaux Teams.
    Utilisé pour construire le contexte de départ.

    Audit isolation 28/04 (I.7) : ajout tenant_id optionnel pour eviter
    de melanger les markers d homonymes cross-tenant. Si non fourni,
    on resout via users (compat ascendante, pas de fuite).
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        # Resolution tenant_id si non fourni
        if not tenant_id:
            try:
                c.execute("SELECT tenant_id FROM users WHERE username=%s LIMIT 1", (username,))
                row = c.fetchone()
                tenant_id = row[0] if row else None
            except Exception:
                tenant_id = None
            if not tenant_id:
                return []
        c.execute("""
            SELECT chat_id, chat_type, chat_label, last_message_id,
                   last_synced_at, notes
            FROM teams_sync_state
            WHERE username = %s AND tenant_id = %s
            ORDER BY last_synced_at DESC
        """, (username, tenant_id))
        rows = c.fetchall()
        return [{
            "chat_id": r[0], "type": r[1], "label": r[2] or r[0][:20],
            "last_message_id": r[3], "last_synced_at": str(r[4]) if r[4] else None,
            "notes": r[5] or ""
        } for r in rows]
    except Exception as e:
        print(f"[Teams] Erreur get_markers: {e}")
        return []
    finally:
        if conn: conn.close()


def set_teams_marker(username: str, chat_id: str, message_id: str,
                     chat_label: str = "", chat_type: str = "chat",
                     notes: str = "", tenant_id: str | None = None) -> dict:
    """
    Raya pose un curseur sur un chat ou canal.
    Appelé uniquement par Raya via [ACTION:TEAMS_MARK:...].

    Audit isolation 28/04 (I.7) : tenant_id optionnel, resolu via users
    si absent. Note : la PK est (username, chat_id) en DB - une migration
    vers (username, chat_id, tenant_id) serait plus propre mais hors LOT 3.
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        # Resolution tenant_id si non fourni
        if not tenant_id:
            c.execute("SELECT tenant_id FROM users WHERE username=%s LIMIT 1", (username,))
            row = c.fetchone()
            tenant_id = row[0] if row else None
        c.execute("""
            INSERT INTO teams_sync_state
            (username, chat_id, chat_type, chat_label, last_message_id, last_synced_at, notes, tenant_id)
            VALUES (%s, %s, %s, %s, %s, NOW(), %s, %s)
            ON CONFLICT (username, chat_id, tenant_id) DO UPDATE SET
                last_message_id = EXCLUDED.last_message_id,
                last_synced_at = NOW(),
                chat_label = COALESCE(EXCLUDED.chat_label, teams_sync_state.chat_label),
                notes = COALESCE(NULLIF(EXCLUDED.notes,''), teams_sync_state.notes),
                tenant_id = COALESCE(EXCLUDED.tenant_id, teams_sync_state.tenant_id)
        """, (username, chat_id, chat_type, chat_label or "", message_id, notes or "", tenant_id))
        conn.commit()
        label = chat_label or chat_id[:20]
        return {"status": "ok", "message": f"✅ Curseur posé sur '{label}'"}
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()


def delete_teams_marker(username: str, chat_id: str,
                        tenant_id: str | None = None) -> dict:
    """Supprime un marqueur — Raya peut effacer un curseur qu'elle a posé.

    Audit isolation 28/04 (I.8) : ajout filtre tenant_id pour eviter
    qu un homonyme efface le marker d un autre.
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        # Resolution tenant_id si non fourni
        if not tenant_id:
            c.execute("SELECT tenant_id FROM users WHERE username=%s LIMIT 1", (username,))
            row = c.fetchone()
            tenant_id = row[0] if row else None
            if not tenant_id:
                return {"status": "error", "message": "Tenant introuvable."}
        c.execute(
            "DELETE FROM teams_sync_state "
            "WHERE username=%s AND chat_id=%s AND tenant_id=%s",
            (username, chat_id, tenant_id),
        )
        conn.commit()
        return {"status": "ok"} if c.rowcount > 0 else {"status": "error", "message": "Marqueur introuvable."}
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()


def get_teams_context_summary(username: str, tenant_id: str | None = None) -> str:
    """
    Génère un résumé court des marqueurs Teams actifs pour le prompt.
    Montre à Raya ce qu'elle surveille déjà.
    """
    markers = get_teams_markers(username, tenant_id=tenant_id)
    if not markers:
        return ""
    lines = []
    for m in markers:
        synced = m["last_synced_at"][:10] if m["last_synced_at"] else "jamais"
        note = f" — {m['notes']}" if m["notes"] else ""
        lines.append(f"  [{m['type']}] {m['label']} (dernier sync: {synced}){note}")
    return "Chats/canaux surveillés :\n" + "\n".join(lines)


# ─── INGESTION + SYNTHÈSE ───

def ingest_and_synthesize(
    token: str,
    username: str,
    chat_id: str,
    chat_label: str = "",
    chat_type: str = "chat",
    since_message_id: str = None,
    top: int = 30,
    tenant_id: str | None = None,
) -> dict:
    """
    Ingère les messages d'un chat/canal Teams et synthétise les insights.

    Flux :
    1. Récupère les messages (depuis le curseur si disponible, sinon les N derniers)
    2. Synthétise via Claude → insights clés
    3. Stocke dans aria_insights avec source='teams'
    4. Vectorise les insights si OPENAI_API_KEY disponible
    5. Retourne le résumé

    Les messages bruts ne sont PAS stockés en base.

    Audit isolation 28/04 : tenant_id propage a save_insight et
    set_teams_marker pour eviter melange cross-tenant.
    """
    from app.connectors.teams_connector import read_chat_messages, read_channel_messages

    # 1. Récupère les messages
    try:
        if chat_type == "channel":
            # Format : team_id|channel_id
            parts = chat_id.split("|")
            if len(parts) == 2:
                result = read_channel_messages(token, parts[0], parts[1], top=top)
            else:
                return {"status": "error", "message": "Format canal invalide (team_id|channel_id)"}
        else:
            result = read_chat_messages(token, chat_id, top=top)

        if result.get("status") != "ok":
            return result

        messages = result.get("messages", [])
        if not messages:
            return {"status": "ok", "message": "Aucun message à ingérer.", "insights": 0}

        # Filtre : depuis le dernier message connu si curseur
        if since_message_id:
            new_msgs = []
            found = False
            for m in reversed(messages):  # du plus ancien au plus récent
                if m["id"] == since_message_id:
                    found = True
                    continue
                if found:
                    new_msgs.append(m)
            messages = new_msgs if found else messages

        if not messages:
            return {"status": "ok", "message": "Aucun nouveau message depuis le dernier curseur.", "insights": 0}

    except Exception as e:
        return {"status": "error", "message": f"Erreur récupération: {str(e)[:100]}"}

    # 2. Synthétise
    label = chat_label or chat_id[:30]
    conv_text = "\n".join([
        f"[{m.get('date','')[:10]}] {m.get('sender','?')} : {m.get('content','')[:300]}"
        for m in messages
    ])

    prompt = f"""Tu es Raya, assistante de {username.capitalize()}.
Voici des messages du chat/canal Teams '{label}' :

{conv_text}

Extrait les informations importantes : décisions prises, engagements, informations clés,
points d'attention, éléments à retenir pour le travail.

Réponds en JSON strict :
{{"insights": [{{"topic": "sujet court", "text": "information importante"}}], "summary": "résumé court de la conversation"}}"""

    parsed = None
    try:
        response = client.messages.create(
            model=ANTHROPIC_MODEL_FAST, max_tokens=800,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = re.sub(r'^```(?:json)?\s*', '', response.content[0].text.strip(), flags=re.MULTILINE)
        raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE).strip()
        parsed = json.loads(raw)
    except Exception:
        try:
            response = client.messages.create(
                model=ANTHROPIC_MODEL_SMART, max_tokens=800,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = re.sub(r'^```(?:json)?\s*', '', response.content[0].text.strip(), flags=re.MULTILINE)
            raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE).strip()
            parsed = json.loads(raw)
        except Exception as e:
            return {"status": "error", "message": f"Erreur synthèse: {str(e)[:100]}"}

    # 3. Stocke les insights
    from app.memory_synthesis import save_insight
    stored = 0
    for item in parsed.get("insights", []):
        if isinstance(item, dict) and item.get("text"):
            topic = f"[Teams/{label}] {item.get('topic', 'info')}"
            save_insight(topic, item["text"], source="teams",
                         username=username, tenant_id=tenant_id)
            stored += 1

    # 4. Met à jour le curseur si des messages ont été traités
    last_msg_id = messages[-1]["id"] if messages else since_message_id
    if last_msg_id:
        set_teams_marker(username, chat_id, last_msg_id, chat_label,
                         chat_type, tenant_id=tenant_id)

    summary = parsed.get("summary", "")
    return {
        "status": "ok",
        "message": f"✅ {len(messages)} messages de '{label}' synthétisés — {stored} insights extraits.",
        "summary": summary,
        "insights_count": stored,
        "messages_count": len(messages),
    }


def explore_history(
    token: str,
    username: str,
    chat_id: str,
    chat_label: str = "",
    chat_type: str = "chat",
    top: int = 50,
    tenant_id: str | None = None,
) -> dict:
    """
    Explore l'historique d'un chat sans tenir compte du curseur.
    Utilisé sur demande expresse — 'rappelle-toi d'une conversation de l'année dernière'.
    """
    return ingest_and_synthesize(
        token=token, username=username, chat_id=chat_id,
        chat_label=chat_label, chat_type=chat_type,
        since_message_id=None,  # Pas de curseur — tout lire
        top=top, tenant_id=tenant_id,
    )
