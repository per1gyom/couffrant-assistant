"""
Run #2 : Raya AGENT auto-reflexive avec outils.

Contrairement au Run #1 (one-shot), Raya peut ici utiliser des OUTILS
pour verifier ses intuitions pendant son introspection :
  - web_search : recherche Internet (SARL vs SAS, orthographes, etc.)
  - search_mails : patterns reels dans les mails stockes
  - search_drive : verifier existence de docs mentionnes
  - query_odoo : donnees metier reelles

Max 8 appels d'outils, lecture seule, timeout 5 min.

NE MODIFIE AUCUNE REGLE. Sauvegarde le rapport dans /tmp/raya_preview_run2.json
"""
import os
import sys
import json
import re
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

import psycopg2
import anthropic

DATABASE_URL = os.getenv("DATABASE_URL")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL_OPUS = os.getenv("LLM_MODEL_DEEP", "claude-opus-4-7")

USERNAME = "guillaume"
TENANT_ID = "couffrant_solar"
MAX_TOOL_ITERATIONS = 8


# ===== CHARGEMENT DU CONTEXTE =============================================

def load_context():
    """Charge tout le contexte Raya pour auto-reflexion."""
    conn = psycopg2.connect(DATABASE_URL)
    c = conn.cursor()

    c.execute("""
        SELECT id, category, rule, confidence, reinforcements, level, source,
               created_at, last_reinforced_at
        FROM aria_rules
        WHERE username = %s AND tenant_id = %s AND active = true
        ORDER BY confidence DESC, reinforcements DESC
        LIMIT 100
    """, (USERNAME, TENANT_ID))
    rules = c.fetchall()

    c.execute("""
        SELECT content FROM aria_profile
        WHERE username = %s AND profile_type = 'style'
          AND (tenant_id = %s OR tenant_id IS NULL)
        ORDER BY id DESC LIMIT 1
    """, (USERNAME, TENANT_ID))
    row = c.fetchone()
    profile = row[0] if row else ""

    c.execute("""
        SELECT content FROM aria_hot_summary
        WHERE username = %s AND (tenant_id = %s OR tenant_id IS NULL)
    """, (USERNAME, TENANT_ID))
    row = c.fetchone()
    hot_summary = row[0] if row else ""

    c.execute("""
        SELECT topic, insight, reinforcements FROM aria_insights
        WHERE username = %s AND (tenant_id = %s OR tenant_id IS NULL)
        ORDER BY reinforcements DESC, updated_at DESC LIMIT 20
    """, (USERNAME, TENANT_ID))
    insights = c.fetchall()

    conn.close()
    return {"rules": rules, "profile": profile, "hot_summary": hot_summary,
            "insights": insights}


# ===== OUTILS DISPONIBLES POUR RAYA =======================================

TOOLS = [
    {
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": 3,
    },
    {
        "name": "search_mails",
        "description": "Cherche dans les mails stockes de Guillaume. Utile pour verifier si un pattern de regle correspond a la realite vecue (ex: combien de mails Enedis recus recemment, qui ecrit le plus, etc.).",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Mot-cle ou phrase a chercher dans les mails (sujet, expediteur, corps)."},
                "limit": {"type": "integer", "description": "Nombre max de resultats (defaut 10, max 20)."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_drive",
        "description": "Liste les dossiers/fichiers du Drive ou SharePoint connectes. Utile pour verifier si un document mentionne dans une regle existe reellement.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Nom partiel du fichier ou dossier a chercher."},
                "limit": {"type": "integer", "description": "Nombre max de resultats (defaut 10)."},
            },
            "required": ["query"],
        },
    },
]


# ===== EXECUTION DES OUTILS (cote serveur) ================================

def tool_search_mails(query: str, limit: int = 10) -> dict:
    """Cherche dans mail_memory."""
    limit = min(max(1, int(limit or 10)), 20)
    try:
        conn = psycopg2.connect(DATABASE_URL)
        c = conn.cursor()
        c.execute("""
            SELECT id, from_email, display_title, subject, short_summary, received_at, priority, category
            FROM mail_memory
            WHERE username = %s AND (tenant_id = %s OR tenant_id IS NULL)
              AND (
                subject ILIKE %s OR
                from_email ILIKE %s OR
                display_title ILIKE %s OR
                short_summary ILIKE %s
              )
            ORDER BY received_at DESC NULLS LAST
            LIMIT %s
        """, (USERNAME, TENANT_ID, f"%{query}%", f"%{query}%",
              f"%{query}%", f"%{query}%", limit))
        rows = c.fetchall()
        conn.close()
        results = [
            {"id": r[0], "from": r[1], "title": r[2] or "", "subject": r[3] or "",
             "summary": (r[4] or "")[:200], "received_at": str(r[5]) if r[5] else "",
             "priority": r[6], "category": r[7]}
            for r in rows
        ]
        return {"query": query, "count": len(results), "results": results}
    except Exception as e:
        return {"query": query, "error": str(e)[:200], "results": []}


def tool_search_drive(query: str, limit: int = 10) -> dict:
    """Cherche dans drive_folders + drive_files si existent."""
    limit = min(max(1, int(limit or 10)), 20)
    try:
        conn = psycopg2.connect(DATABASE_URL)
        c = conn.cursor()
        c.execute("""
            SELECT folder_id, folder_name, provider, site_name, folder_path, created_at
            FROM drive_folders
            WHERE tenant_id = %s AND (folder_name ILIKE %s OR site_name ILIKE %s OR folder_path ILIKE %s)
            LIMIT %s
        """, (TENANT_ID, f"%{query}%", f"%{query}%", f"%{query}%", limit))
        folders = c.fetchall()
        conn.close()
        return {
            "query": query,
            "folders_count": len(folders),
            "folders": [{"folder_id": f[0], "name": f[1], "provider": f[2],
                        "site_name": f[3], "path": f[4]} for f in folders],
            "note": "Seuls les dossiers configures dans drive_folders sont visibles. Les fichiers internes ne sont pas indexes en DB."
        }
    except Exception as e:
        return {"query": query, "error": str(e)[:200]}


def tool_query_odoo(object_type: str, search_text: str, limit: int = 5) -> dict:
    """Cherche dans Odoo via le connecteur existant."""
    limit = min(max(1, int(limit or 5)), 10)
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from app.connectors.odoo_connector import odoo_call
        model_map = {
            "partner": "res.partner",
            "sale_order": "sale.order",
            "invoice": "account.move",
        }
        model = model_map.get(object_type)
        if not model:
            return {"error": f"object_type invalide: {object_type}"}
        fields_map = {
            "res.partner": ["id", "name", "email", "phone", "is_company"],
            "sale.order": ["id", "name", "partner_id", "amount_total", "state"],
            "account.move": ["id", "name", "partner_id", "amount_total", "state", "move_type"],
        }
        # odoo_call(model, method, args, kwargs) utilise execute_kw
        # search_read : args = [domain], kwargs = {fields, limit}
        domain = [("name", "ilike", search_text)]
        results = odoo_call(
            model=model, method="search_read",
            args=[domain],
            kwargs={"fields": fields_map[model], "limit": limit},
        )
        return {
            "object_type": object_type,
            "search_text": search_text,
            "count": len(results) if results else 0,
            "results": results or [],
        }
    except Exception as e:
        return {"object_type": object_type, "error": str(e)[:300]}


def execute_tool(name: str, input_args: dict) -> dict:
    """Route un appel d'outil vers la bonne fonction."""
    if name == "search_mails":
        return tool_search_mails(input_args.get("query", ""), input_args.get("limit", 10))
    if name == "search_drive":
        return tool_search_drive(input_args.get("query", ""), input_args.get("limit", 10))
    if name == "query_odoo":
        return tool_query_odoo(
            input_args.get("object_type", ""),
            input_args.get("search_text", ""),
            input_args.get("limit", 5),
        )
    return {"error": f"outil inconnu: {name}"}


# ===== PROMPT =============================================================

def build_prompt(ctx):
    rules_text = "\n".join([
        f"[id:{r[0]}][{r[1]}][conf:{r[3]:.2f}][reinf:{r[4]}][level:{r[5]}][src:{r[6]}] {r[2]}"
        for r in ctx["rules"]
    ])
    insights_text = "\n".join([
        f"- [{i[0]}] {i[1]} (reinf:{i[2]})"
        for i in ctx["insights"]
    ])
    profile_extract = ctx["profile"][:1500] if ctx["profile"] else "(aucun profil de style)"
    hot_extract = ctx["hot_summary"][:1500] if ctx["hot_summary"] else "(pas de hot summary)"

    return f"""Tu es Raya, l'assistante de Guillaume (Couffrant Solar, PV French).
Ce soir, tu fais une seance d'INTROSPECTION AGENT sur ta propre base de regles.

Tu as acces a 3 OUTILS pour verifier tes intuitions pendant l'analyse :
- web_search : recherche Internet (SARL vs SAS, orthographes, termes techniques)
- search_mails : patterns reels dans les mails stockes
- search_drive : dossiers Drive/SharePoint configures

UTILISE CES OUTILS quand tu as un DOUTE ou tu veux CONFIRMER une intuition
avant de proposer une modification de regle. Par exemple :
- "Couffrant Solar est SARL ou SAS ?" -> web_search
- "Cette regle sur Enedis correspond au vecu ?" -> search_mails
- "Le dossier SC-144A existe vraiment dans SharePoint ?" -> search_drive

Limite : 8 appels d'outils maximum. Apres, tu dois rendre ton verdict.

=== TON PROFIL DE STYLE ===
{profile_extract}

=== TON RESUME OPERATIONNEL ===
{hot_extract}

=== TES INSIGHTS SUR GUILLAUME ===
{insights_text}

=== TES {len(ctx['rules'])} REGLES ACTIVES ===
{rules_text}

==========================================================
MISSION : Analyse intelligente globale de ta base de regles.
==========================================================

Tu analyses selon 6 axes :
1. CONTRADICTIONS : regles qui s'opposent frontalement
2. CHEVAUCHEMENTS : regles qui se recouvrent partiellement
3. FUSIONS : plusieurs regles proches a consolider en UNE plus riche
4. COMPLEMENTARITES : regles a combiner pour etre plus utiles
5. SIMPLIFICATIONS / SUPPRESSIONS : regles mal formulees, vagues, redondantes, obsoletes
6. NOUVELLES REGLES : patterns recurrents dans tes conversations/insights a formaliser

Quand tu as termine d'explorer, reponds UNIQUEMENT avec un bloc JSON strict
(pas de markdown, pas de backticks) dans ce format :

{{
  "contradictions_claires": [{{ "loser_id": X, "winner_id": Y, "reason": "..." }}],
  "contradictions_ambigues": [{{ "rule_ids": [X, Y], "question": "..." }}],
  "fusions_proposees": [{{ "source_ids": [X, Y], "new_rule": "...", "category": "...", "level": "moyenne", "reason": "..." }}],
  "simplifications": [{{ "rule_id": X, "new_text": "...", "reason": "..." }}],
  "suppressions_proposees": [{{ "rule_id": X, "reason": "..." }}],
  "nouvelles_regles": [{{ "rule": "...", "category": "...", "level": "moyenne", "justification": "..." }}],
  "verifications_effectuees": ["Liste courte de ce que tu as verifie avec les outils, 1 ligne par verif"],
  "bilan_global": "4-5 phrases sur la qualite de la base et les priorites."
}}

Sois conservatrice : propose peu mais bien.
IMPORTANT - FORMAT DE REPONSE :
- Reponse CONCISE et CLAIRE : justifications courtes (1 phrase max par proposition)
- Pas besoin d'expliquer 36 raisons pour une fusion, va droit au but
- Le bilan_global : 3-4 phrases maximum
- Tu peux faire autant de propositions que necessaire, mais chaque
  justification reste breve. Guillaume veut voir vite ce qui change, pas lire un essai.
"""


# ===== BOUCLE AGENT =======================================================

def agent_loop(prompt: str) -> tuple:
    """Boucle agent : Opus <-> outils jusqu'a ce qu'il rende son verdict."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    messages = [{"role": "user", "content": prompt}]

    tool_calls_log = []
    total_in = 0
    total_out = 0
    iteration = 0
    final_text = ""

    while iteration < MAX_TOOL_ITERATIONS:
        iteration += 1
        print(f"\n[ITERATION {iteration}] Appel Opus...")
        response = client.messages.create(
            model=MODEL_OPUS,
            max_tokens=16384,
            tools=TOOLS,
            messages=messages,
        )
        total_in += response.usage.input_tokens
        total_out += response.usage.output_tokens
        print(f"  -> stop_reason: {response.stop_reason}  (tokens: {response.usage.input_tokens} in / {response.usage.output_tokens} out)")

        # Si Opus veut utiliser un outil
        if response.stop_reason == "tool_use":
            # Ajouter la reponse assistant
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_name = block.name
                    tool_input = block.input
                    print(f"  [TOOL] {tool_name}({json.dumps(tool_input, ensure_ascii=False)[:150]})")

                    if tool_name == "web_search":
                        # web_search natif : Anthropic gere tout seul, on ne voit que le resultat dans la prochaine reponse
                        # Mais le tool_use apparait quand meme ici, il faut passer le result "pass-through"
                        # En realite avec web_search_20250305 natif, Anthropic gere la chaine en interne et on ne recoit PAS de tool_use pour web_search
                        # => Si on le recoit c'est un edge case, on le log
                        result_content = "(web_search natif - resultat integre par Anthropic)"
                    else:
                        result = execute_tool(tool_name, tool_input)
                        result_content = json.dumps(result, ensure_ascii=False)[:3000]
                        tool_calls_log.append({
                            "iteration": iteration, "tool": tool_name,
                            "input": tool_input,
                            "result_preview": result_content[:200],
                        })

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_content,
                    })

            messages.append({"role": "user", "content": tool_results})
            continue

        # Sinon : reponse finale
        for block in response.content:
            if hasattr(block, "text"):
                final_text += block.text
        break

    return final_text, tool_calls_log, total_in, total_out, iteration


# ===== MAIN ===============================================================

def main():
    if not DATABASE_URL or not ANTHROPIC_KEY:
        print("ERREUR : variables env manquantes")
        sys.exit(1)

    print(f"=== Raya Auto-Reflection AGENT — {USERNAME}@{TENANT_ID} ===\n")

    print("1. Chargement du contexte...")
    ctx = load_context()
    print(f"   - {len(ctx['rules'])} regles, {len(ctx['insights'])} insights")
    print(f"   - Profil: {len(ctx['profile'])} chars, hot_summary: {len(ctx['hot_summary'])} chars")

    print("\n2. Construction du prompt + demarrage boucle agent...")
    prompt = build_prompt(ctx)
    start = time.time()

    try:
        final_text, tool_calls, total_in, total_out, iterations = agent_loop(prompt)
    except Exception as e:
        print(f"ERREUR agent: {e}")
        sys.exit(1)

    duration = time.time() - start
    cost_usd = (total_in * 15 + total_out * 75) / 1_000_000
    print(f"\n3. Boucle terminee en {duration:.1f}s, {iterations} iterations")
    print(f"   Tokens: {total_in} in / {total_out} out")
    print(f"   Outils appeles: {len(tool_calls)}")
    print(f"   Cout: ~${cost_usd:.4f} (~{cost_usd * 0.92:.3f} EUR)")


    print("\n4. Parsing du rapport JSON...")
    raw = re.sub(r'^```(?:json)?\s*', '', final_text.strip(), flags=re.MULTILINE)
    raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE).strip()
    # Tentative extraction JSON si entoure de texte
    m = re.search(r'\{[\s\S]*\}', raw)
    if m:
        raw = m.group(0)
    try:
        report = json.loads(raw)
        parsing_ok = True
    except Exception as e:
        print(f"   ERREUR parsing: {e}")
        print(f"\n   Texte final brut (debut):\n{final_text[:2000]}\n")
        # Sauvegarde brute pour ne rien perdre
        fallback_path = "/tmp/raya_preview_run2_raw.txt"
        with open(fallback_path, "w", encoding="utf-8") as f:
            f.write(final_text)
        print(f"   Texte brut sauvegarde : {fallback_path}")
        report = {"_parsing_error": str(e), "_raw_text": final_text}
        parsing_ok = False

    # Affichage (seulement si parsing OK)
    if not parsing_ok:
        print("\n(Pas d'affichage structure a cause du parsing echoue - voir /tmp/raya_preview_run2_raw.txt)")
    else:
        print("\n" + "=" * 60)
        print("RAPPORT RAYA (AGENT)")
        print("=" * 60)
        print(f"\nBILAN:\n{report.get('bilan_global', '(vide)')}\n")

        verifs = report.get("verifications_effectuees", [])
        if verifs:
            print(f"--- VERIFICATIONS EFFECTUEES ({len(verifs)}) ---")
            for v in verifs:
                print(f"  * {v}")

        for key, label in [
            ("contradictions_claires", "CONTRADICTIONS CLAIRES"),
            ("contradictions_ambigues", "CONTRADICTIONS AMBIGUES"),
            ("fusions_proposees", "FUSIONS PROPOSEES"),
            ("simplifications", "SIMPLIFICATIONS"),
            ("suppressions_proposees", "SUPPRESSIONS PROPOSEES"),
            ("nouvelles_regles", "NOUVELLES REGLES"),
        ]:
            items = report.get(key, [])
            print(f"\n--- {label} : {len(items)} ---")
            for i, item in enumerate(items[:20], 1):
                print(f"  {i}. {json.dumps(item, ensure_ascii=False)[:280]}")

    # Sauvegarde
    out_path = "/tmp/raya_preview_run2.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "report": report,
            "tool_calls": tool_calls,
            "meta": {
                "tokens_in": total_in, "tokens_out": total_out,
                "cost_usd": cost_usd, "iterations": iterations,
                "duration_seconds": round(duration, 2),
                "model": MODEL_OPUS,
            }
        }, f, ensure_ascii=False, indent=2)
    print(f"\nRapport complet sauvegarde : {out_path}")


if __name__ == "__main__":
    main()
