"""
Moteur LLM de synthese : rebuild_hot_summary, vectorisation.
Extrait de memory_synthesis.py -- SPLIT-2.
"""
from app.database import get_pg_conn
from app.llm_client import llm_complete
from app.security_tools import DEFAULT_TENANT


def _embed(text: str):
    try:
        from app.embedding import embed
        return embed(text)
    except Exception:
        return None



def _vec_str(embedding) -> str | None:
    if embedding is None:
        return None
    return "[" + ",".join(str(x) for x in embedding) + "]"



def rebuild_hot_summary(username: str = None,
                        tenant_id: str = DEFAULT_TENANT) -> str:
    """
    Reconstruit le resume operationnel chaud (hot_summary).
    5B-2 : prompt enrichi 3 niveaux + vectorisation.
    5G-6 : prompt adapte selon la phase de maturite.
    8-TON : section "Ton et communication" incluse dans le resume.
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT from_email, display_title, category, priority, short_summary,
                   received_at, mailbox_source
            FROM mail_memory
            WHERE username = %s AND (tenant_id = %s OR tenant_id IS NULL)
            ORDER BY received_at DESC NULLS LAST LIMIT 30
        """, (username, tenant_id))
        cols = [d[0] for d in c.description]
        mails = [dict(zip(cols, row)) for row in c.fetchall()]
        c.execute("""
            SELECT name, summary FROM aria_contacts
            WHERE tenant_id = %s ORDER BY last_seen DESC LIMIT 15
        """, (tenant_id,))
        contacts = [{'name': r[0], 'summary': r[1]} for r in c.fetchall()]
        c.execute("""
            SELECT user_input, aria_response FROM aria_memory
            WHERE username = %s AND (tenant_id = %s OR tenant_id IS NULL)
            ORDER BY id DESC LIMIT 8
        """, (username, tenant_id))
        history = [{'q': r[0][:150], 'a': r[1][:200]} for r in c.fetchall()]
    finally:
        if conn: conn.close()

    display_name = username.capitalize()

    # 5G-6 : adapter le hot_summary selon la phase de maturite
    phase_instruction = ""
    try:
        from app.maturity import compute_maturity_score
        maturity = compute_maturity_score(username)
        phase = maturity["phase"]
        if phase == "discovery":
            phase_instruction = """
Phase DECOUVERTE — Resume FACTUEL :
- Situation operationnelle : societes, outils, collaborateurs connus
- Premiers apprentissages : ce que tu as compris jusqu'ici
- Questions ouvertes : ce que tu ne sais pas encore
Reste factuel. Pas de suppositions."""
        elif phase == "consolidation":
            phase_instruction = """
Phase CONSOLIDATION — Resume ANALYTIQUE :
- Situation operationnelle (mise a jour)
- Patterns d'usage detectes : quand et comment l'utilisateur travaille
- Preferences confirmees vs hypotheses
- Points de friction identifies"""
        elif phase == "maturity":
            phase_instruction = """
Phase MATURITE — PORTRAIT PROFOND :
- Situation operationnelle (vue d'ensemble transversale si multi-tenant)
- Modeles de decision : comment l'utilisateur raisonne, ses priorites
- Patterns confirmes : temporels, relationnels, thematiques
- Preferences implicites (deduites du comportement, pas declarees)
- Automatisations possibles : taches repetitives identifiees"""
    except Exception:
        pass

    prompt = f"""Tu es Raya, l'assistante personnelle de {display_name}.
Tu le connais. Tu observes ses habitudes. Tu construis un portrait operationnel vivant.
INTERDIT : ne JAMAIS inclure le mot "Jarvis". L'assistante s'appelle Raya.
{phase_instruction}

Mails recents :
{json.dumps(mails, ensure_ascii=False, default=str)}

Contacts actifs :
{json.dumps(contacts, ensure_ascii=False)}

Dernieres conversations :
{json.dumps(history, ensure_ascii=False)}

Genere un resume structure en 4 sections (~600 mots) :

1. SITUATION OPERATIONNELLE
   Ce qui est en cours, urgent, en attente. Les dossiers ouverts.
   Les deadlines proches. Factuel et direct.

2. PATTERNS DETECTES
   Les habitudes que tu observes chez {display_name} :
   - Temporels : quand traite-t-il certains sujets ?
   - Relationnels : quels contacts reviennent, pour quels sujets ?
   - Comportementaux : comment reagit-il aux urgences ? aux relances ?
   Si tu n'as pas assez de donnees pour un pattern, dis-le.

3. PREFERENCES ET MODELES DE DECISION
   Ce que tu comprends de sa facon de travailler :
   - Style de communication prefere (direct ? detaille ? formel ?)
   - Priorites implicites (qu'est-ce qui passe en premier ?)
   - Points sensibles (sujets ou il est particulierement attentif)
   Si tu manques de donnees, indique ce que tu aurais besoin d'observer.

4. TON ET COMMUNICATION
   Comment {display_name} aime etre adresse par Raya.
   Deduis ces informations des echanges observes :
   - Longueur preferee : reponses courtes et directes, ou longues et detaillees ?
   - Registre : informel/decontracte ou formel/professionnel ?
   - Niveau de detail technique : aime-t-il les explications techniques, ou prefere-t-il le resultat direct ?
   - Format prefere : listes, paragraphes, ou une seule phrase ?
   - Preferences exprimees explicitement (ex : "sois plus concis", "je prefere les details", "parle-moi comme un collegue") ?
   Si trop peu de donnees : indique-le brievement et note ce qu'il faudrait observer.

Factuel, direct, sans blabla. N'invente rien — base-toi uniquement sur les donnees."""

    result = llm_complete(
        messages=[{"role": "user", "content": prompt}],
        model_tier="deep",
        max_tokens=1400,
    )
    summary = result["text"]
    log_llm_usage(result, username=username, tenant_id=tenant_id, purpose="rebuild_hot_summary")

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO aria_hot_summary (username, content, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (username) DO UPDATE SET content = EXCLUDED.content, updated_at = NOW()
        """, (username, summary))
        conn.commit()
    finally:
        if conn: conn.close()

    # Invalider le cache en mémoire pour que le prochain appel recharge la version fraîche
    try:
        import app.cache as _cache
        _cache.set(f"hot_summary:{username}", summary, ttl=1800)
    except Exception:
        pass
        vec = _vec_str(_embed(summary[:3000]))
        if vec:
            conn2 = get_pg_conn()
            c2 = conn2.cursor()
            # Audit isolation 28/04 (I.9) : ajout filtre tenant_id pour
            # eviter d ecraser le hot_summary d un homonyme cross-tenant.
            c2.execute(
                "UPDATE aria_hot_summary SET embedding = %s::vector "
                "WHERE username = %s AND tenant_id = %s",
                (vec, username, tenant_id),
            )
            conn2.commit()
            conn2.close()
    except Exception as e:
        print(f"[HotSummary] Vectorisation echouee (non bloquant): {e}")

    return summary



def _vectorize_conversations_batch(conversations: list, username: str):
    try:
        from app.embedding import embed_batch, is_available
        if not is_available(): return
        texts = [f"{r[1][:300]}\n{r[2][:300]}" for r in conversations]
        embeddings = embed_batch(texts)
        conn = get_pg_conn()
        c = conn.cursor()
        for (conv_id, _, _, _), emb in zip(conversations, embeddings):
            if emb is None: continue
            vec = "[" + ",".join(str(x) for x in emb) + "]"
            c.execute("UPDATE aria_memory SET embedding=%s::vector WHERE id=%s", (vec, conv_id))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Embedding] Erreur vectorize_conversations: {e}")


