"""
Script de preview Run #1 : Raya auto-reflexive sur sa propre base de regles.

Charge le CONTEXTE complet Raya (regles + profil + insights + hot_summary
+ 20 dernieres convs) et demande a Opus de proposer une optimisation
intelligente globale avec 6 axes :
  1. Contradictions
  2. Chevauchements
  3. Fusions
  4. Complementarites
  5. Simplifications / suppressions
  6. Propositions de nouvelles regles

NE MODIFIE RIEN. Sauvegarde le rapport JSON dans /tmp/raya_preview_run1.json
pour analyse.
"""
import os
import sys
import json
import re
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


def load_context():
    """Charge tout le contexte Raya pour auto-reflexion."""
    conn = psycopg2.connect(DATABASE_URL)
    c = conn.cursor()

    # 1. Toutes les regles actives (max 100)
    c.execute("""
        SELECT id, category, rule, confidence, reinforcements, level, source,
               created_at, last_reinforced_at
        FROM aria_rules
        WHERE username = %s AND tenant_id = %s AND active = true
        ORDER BY confidence DESC, reinforcements DESC
        LIMIT 100
    """, (USERNAME, TENANT_ID))
    rules = c.fetchall()

    # 2. Profil de style utilisateur
    c.execute("""
        SELECT content FROM aria_profile
        WHERE username = %s AND profile_type = 'style'
          AND (tenant_id = %s OR tenant_id IS NULL)
        ORDER BY id DESC LIMIT 1
    """, (USERNAME, TENANT_ID))
    row = c.fetchone()
    profile = row[0] if row else ""

    # 3. Hot summary
    c.execute("""
        SELECT content FROM aria_hot_summary
        WHERE username = %s AND (tenant_id = %s OR tenant_id IS NULL)
    """, (USERNAME, TENANT_ID))
    row = c.fetchone()
    hot_summary = row[0] if row else ""

    # 4. Insights recents
    c.execute("""
        SELECT topic, insight, reinforcements FROM aria_insights
        WHERE username = %s AND (tenant_id = %s OR tenant_id IS NULL)
        ORDER BY reinforcements DESC, updated_at DESC LIMIT 20
    """, (USERNAME, TENANT_ID))
    insights = c.fetchall()

    # 5. 20 dernieres conversations (question + reponse tronquees)
    c.execute("""
        SELECT user_input, aria_response, created_at
        FROM aria_memory
        WHERE username = %s AND (tenant_id = %s OR tenant_id IS NULL)
        ORDER BY id DESC LIMIT 20
    """, (USERNAME, TENANT_ID))
    conversations = c.fetchall()

    conn.close()
    return {
        "rules": rules,
        "profile": profile,
        "hot_summary": hot_summary,
        "insights": insights,
        "conversations": conversations,
    }


def build_prompt(ctx):
    """Construit le prompt complet pour Raya-Opus en mode auto-reflexion."""
    rules_text = "\n".join([
        f"[id:{r[0]}][{r[1]}][conf:{r[3]:.2f}][reinf:{r[4]}][level:{r[5]}][src:{r[6]}] {r[2]}"
        for r in ctx["rules"]
    ])

    insights_text = "\n".join([
        f"- [{i[0]}] {i[1]} (reinf:{i[2]})"
        for i in ctx["insights"]
    ])

    convs_text = "\n".join([
        f"- Q: {c[0][:200]}\n  R: {(c[1] or '')[:200]}"
        for c in ctx["conversations"][:10]  # Limite pour tokens
    ])

    profile_extract = ctx["profile"][:1500] if ctx["profile"] else "(aucun profil de style)"
    hot_extract = ctx["hot_summary"][:1500] if ctx["hot_summary"] else "(pas de hot summary)"

    prompt = f"""Tu es Raya, l'assistante de Guillaume (Couffrant Solar, PV French).
Ce soir, tu fais une seance d'INTROSPECTION sur ta propre base de regles apprises.

Tu connais Guillaume. Voici ton contexte habituel :

=== TON PROFIL DE STYLE (comment tu ecris) ===
{profile_extract}

=== TON RESUME OPERATIONNEL RECENT ===
{hot_extract}

=== TES INSIGHTS SUR GUILLAUME ===
{insights_text}

=== TES 10 DERNIERES CONVERSATIONS (pour re-sentir le contexte vecu) ===
{convs_text}

=== TES {len(ctx['rules'])} REGLES ACTIVES A REVOIR ===
{rules_text}

==========================================================
MISSION : Optimisation intelligente globale de ta base de regles.
==========================================================
"""
    return prompt


MISSION_SPEC = """
Tu analyses TA propre base de regles selon 6 axes :

1. CONTRADICTIONS : regles qui s'opposent frontalement
2. CHEVAUCHEMENTS : regles qui se recouvrent partiellement sur le meme sujet
3. FUSIONS : plusieurs regles proches a consolider en UNE seule plus riche,
   mieux formulee, qui capture l'essence de toutes
4. COMPLEMENTARITES : regles qui gagneraient a etre combinees
5. SIMPLIFICATIONS / SUPPRESSIONS : regles mal formulees, trop vagues,
   redondantes ou obsoletes au vu du contexte actuel de Guillaume
6. NOUVELLES REGLES : patterns recurrents dans tes conversations ou
   insights qui meritent d'etre formalises en regles (tu as le droit
   d'en proposer si tu as des preuves solides dans ton vecu)

Retourne un JSON strict (sans backticks, sans markdown) :
{
  "contradictions_claires": [
    {"loser_id": 12, "winner_id": 45, "reason": "..."}
  ],
  "contradictions_ambigues": [
    {"rule_ids": [12, 45], "question": "Question claire a poser a Guillaume"}
  ],
  "fusions_proposees": [
    {"source_ids": [12, 45, 78], "new_rule": "Texte complet de la nouvelle regle consolidee", "category": "...", "level": "moyenne", "reason": "..."}
  ],
  "simplifications": [
    {"rule_id": 12, "new_text": "Nouvelle formulation plus claire", "reason": "..."}
  ],
  "suppressions_proposees": [
    {"rule_id": 12, "reason": "Obsolete car..."}
  ],
  "nouvelles_regles": [
    {"rule": "Texte de la nouvelle regle", "category": "...", "level": "moyenne", "justification": "J'ai observe dans X conversations que..."}
  ],
  "bilan_global": "Ton evaluation de la qualite de ta base de regles actuelle, forces et axes d'amelioration, en 4-5 phrases."
}

IMPORTANT :
- Sois conservatrice : ne propose que ce qui AMELIORE VRAIMENT la clarte ou la coherence
- Justifie chaque proposition en t'appuyant sur TON contexte vecu (insights, convs)
- Pour les fusions, redige la nouvelle regle complete, pas une instruction
- Pour les suppressions et nouvelles regles, sois prudente : il vaut mieux proposer peu mais bien
- Tu connais Guillaume, n'hesite pas a donner tes intuitions ("je sens que...", "j'ai remarque que...")
"""


def call_opus(prompt):
    """Appelle Opus avec le prompt d'auto-reflexion."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    full_prompt = prompt + MISSION_SPEC
    print(f"  Prompt : {len(full_prompt)} caracteres (~{len(full_prompt)//4} tokens)")

    response = client.messages.create(
        model=MODEL_OPUS,
        max_tokens=4096,
        messages=[{"role": "user", "content": full_prompt}],
    )
    text = response.content[0].text
    usage = response.usage
    return text, usage


def main():
    if not DATABASE_URL or not ANTHROPIC_KEY:
        print("ERREUR : variables env manquantes")
        sys.exit(1)

    print(f"=== Raya Auto-Reflection Preview — {USERNAME}@{TENANT_ID} ===\n")

    print("1. Chargement du contexte Raya...")
    ctx = load_context()
    print(f"   - {len(ctx['rules'])} regles actives")
    print(f"   - Profil : {len(ctx['profile'])} chars")
    print(f"   - Hot summary : {len(ctx['hot_summary'])} chars")
    print(f"   - {len(ctx['insights'])} insights")
    print(f"   - {len(ctx['conversations'])} conversations recentes")

    print("\n2. Construction du prompt...")
    prompt = build_prompt(ctx)

    print("\n3. Appel Opus (~30-60s)...")
    try:
        text, usage = call_opus(prompt)
        print(f"   Tokens in/out : {usage.input_tokens}/{usage.output_tokens}")
        # Prix Opus : $15 / 1M in, $75 / 1M out
        cost_usd = (usage.input_tokens * 15 + usage.output_tokens * 75) / 1_000_000
        print(f"   Cout estime : ~${cost_usd:.4f} (~{cost_usd * 0.92:.3f} EUR)")
    except Exception as e:
        print(f"   ERREUR Opus : {e}")
        sys.exit(1)

    print("\n4. Parsing JSON...")
    raw = re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=re.MULTILINE)
    raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE).strip()
    try:
        report = json.loads(raw)
    except Exception as e:
        print(f"   ERREUR parsing : {e}")
        print(f"\n   Reponse brute :\n{text[:2000]}")
        sys.exit(1)


    # Resume lisible
    print("\n" + "=" * 60)
    print("RAPPORT RAYA")
    print("=" * 60)

    print(f"\nBILAN GLOBAL :\n{report.get('bilan_global', '(vide)')}\n")

    for key, label in [
        ("contradictions_claires", "CONTRADICTIONS CLAIRES"),
        ("contradictions_ambigues", "CONTRADICTIONS AMBIGUES"),
        ("fusions_proposees", "FUSIONS PROPOSEES"),
        ("simplifications", "SIMPLIFICATIONS"),
        ("suppressions_proposees", "SUPPRESSIONS PROPOSEES"),
        ("nouvelles_regles", "NOUVELLES REGLES PROPOSEES"),
    ]:
        items = report.get(key, [])
        print(f"\n--- {label} : {len(items)} ---")
        for i, item in enumerate(items[:10], 1):
            print(f"  {i}. {json.dumps(item, ensure_ascii=False)[:250]}")

    # Sauvegarde JSON complet
    out_path = "/tmp/raya_preview_run1.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "report": report,
            "meta": {
                "tokens_in": usage.input_tokens,
                "tokens_out": usage.output_tokens,
                "cost_usd": cost_usd,
                "rules_analyzed": len(ctx["rules"]),
                "model": MODEL_OPUS,
            }
        }, f, ensure_ascii=False, indent=2)
    print(f"\nRapport complet sauvegarde : {out_path}")


if __name__ == "__main__":
    main()
