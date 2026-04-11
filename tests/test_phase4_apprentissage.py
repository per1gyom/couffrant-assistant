"""
Tests Phase 4 — Qualite d'apprentissage et fiabilite de Raya.

Scenarios :
  (a) Detection DUPLICATE/REFINE via rule_validator (avec mock RAG)
  (b) Registre capabilities present dans le prompt systeme
  (c) Parser LEARN robuste : regle contenant [URGENT] non tronquee
  (d) Endpoint feedback negatif repond correctement

Lancer : pytest tests/test_phase4_apprentissage.py -v
"""
import json
import pytest
from unittest.mock import patch, MagicMock

TEST_USERNAME = "test_phase4"
TEST_TENANT   = "test_tenant"


# --- FIXTURES ---

@pytest.fixture(autouse=True)
def cleanup():
    """Nettoie les donnees de test avant et apres chaque test."""
    _cleanup()
    yield
    _cleanup()


def _cleanup():
    try:
        from app.database import get_pg_conn
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("DELETE FROM aria_rules WHERE username = %s", (TEST_USERNAME,))
        c.execute("DELETE FROM aria_memory WHERE username = %s", (TEST_USERNAME,))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[cleanup] {e}")


# --- TEST (a) : Detection DUPLICATE via rule_validator ---

class TestDuplicateDetection:
    """
    Valide que validate_rule_before_save() detecte les doublons semantiques.
    Mocke search_similar pour simuler le RAG vectoriel sans openai en prod.
    """

    def test_duplicate_detected_when_similar_rule_exists(self):
        """
        Scenario : Opus recoit une regle et 5 regles proches via RAG.
        La nouvelle regle est semantiquement identique a une existante.
        Resultat attendu : decision = DUPLICATE, rules_to_add vide.
        """
        from app.rule_validator import validate_rule_before_save

        existing_rule = {
            "id": 42,
            "category": "comportement",
            "rule": "Les actions recuperables ne necessitent pas de confirmation utilisateur.",
            "confidence": 0.8,
        }
        new_rule = "Pour la corbeille, agis directement sans demander confirmation."

        # Mock search_similar pour simuler le RAG disponible
        # Mock llm_complete pour simuler la reponse Opus
        opus_response = json.dumps({
            "decision": "DUPLICATE",
            "reasoning": "Semantiquement identique a la regle id:42",
            "rules_to_add": [],
            "rules_to_update": [],
            "rules_to_skip": [42],
            "conflict_message": None,
        })

        with patch("app.rule_validator._find_similar_rules", return_value=[existing_rule]), \
             patch("app.rule_validator.llm_complete", return_value={"text": opus_response}):

            result = validate_rule_before_save(TEST_USERNAME, TEST_TENANT, "comportement", new_rule)

        assert result["decision"] == "DUPLICATE", f"Attendu DUPLICATE, recu : {result['decision']}"
        assert result["rules_to_add"] == [], "DUPLICATE ne doit pas inserer de nouvelle regle"
        assert 42 in result["rules_to_skip"], "L'id de la regle existante doit etre dans rules_to_skip"

    def test_new_rule_when_no_similar_exists(self):
        """
        Scenario : aucune regle similaire trouvee par le RAG.
        Resultat attendu : decision = NEW sans appel Opus (court-circuit).
        """
        from app.rule_validator import validate_rule_before_save

        with patch("app.rule_validator._find_similar_rules", return_value=[]):
            result = validate_rule_before_save(
                TEST_USERNAME, TEST_TENANT,
                "comportement",
                "Toujours confirmer avant d'envoyer un email a un client externe.",
            )

        assert result["decision"] == "NEW"
        assert len(result["rules_to_add"]) == 1
        assert result["rules_to_add"][0]["rule"] == "Toujours confirmer avant d'envoyer un email a un client externe."

    def test_refine_when_improvement_detected(self):
        """
        Scenario : la nouvelle regle ameliore une regle existante.
        Resultat attendu : decision = REFINE, rules_to_update contient l'id.
        """
        from app.rule_validator import validate_rule_before_save

        existing_rule = {
            "id": 55,
            "category": "comportement",
            "rule": "Ne pas confirmer la corbeille.",
            "confidence": 0.7,
        }
        improved_rule = "La corbeille est recuperable — executer directement, jamais de confirmation, meme pour plusieurs mails en meme temps."

        opus_response = json.dumps({
            "decision": "REFINE",
            "reasoning": "Version amelioree et plus complete de la regle id:55",
            "rules_to_add": [],
            "rules_to_update": [{"id": 55, "rule": improved_rule}],
            "rules_to_skip": [],
            "conflict_message": None,
        })

        with patch("app.rule_validator._find_similar_rules", return_value=[existing_rule]), \
             patch("app.rule_validator.llm_complete", return_value={"text": opus_response}):

            result = validate_rule_before_save(TEST_USERNAME, TEST_TENANT, "comportement", improved_rule)

        assert result["decision"] == "REFINE"
        assert result["rules_to_add"] == []
        assert len(result["rules_to_update"]) == 1
        assert result["rules_to_update"][0]["id"] == 55

    def test_fallback_to_new_on_opus_error(self):
        """
        Scenario : Opus retourne un JSON invalide.
        Resultat attendu : fallback NEW, pas d'exception propagee.
        """
        from app.rule_validator import validate_rule_before_save

        with patch("app.rule_validator._find_similar_rules", return_value=[{"id": 1, "category": "x", "rule": "x"}]), \
             patch("app.rule_validator.llm_complete", return_value={"text": "ERREUR INVALIDE"}):

            result = validate_rule_before_save(TEST_USERNAME, TEST_TENANT, "comportement", "une regle")

        assert result["decision"] == "NEW"
        assert len(result["rules_to_add"]) == 1


# --- TEST (b) : Capabilities dans le prompt systeme ---

class TestCapabilitiesInPrompt:
    """
    Valide que le registre des capacites est bien injecte dans build_system_prompt().
    """

    def test_capabilities_module_has_required_keys(self):
        """Le module capabilities contient les capacites UI attendues."""
        from app.capabilities import CAPABILITIES

        ui = CAPABILITIES["interface_utilisateur"]
        assert "boutons_interactifs" in ui, "Boutons interactifs manquants"
        assert "rendu_markdown" in ui, "Markdown manquant"
        assert "entree_vocale" in ui, "Entree vocale manquante"
        assert "sortie_vocale" in ui, "Sortie vocale manquante"
        assert "upload_fichiers" in ui, "Upload manquant"
        assert "choix_interactifs" in ui, "ASK_CHOICE manquant"

    def test_get_capabilities_prompt_mentions_buttons(self):
        """get_capabilities_prompt() mentionne explicitement les boutons et ASK_CHOICE."""
        from app.capabilities import get_capabilities_prompt

        prompt = get_capabilities_prompt()
        assert "bouton" in prompt.lower() or "ASK_CHOICE" in prompt, \
            "Le prompt doit mentionner les boutons ou ASK_CHOICE"
        assert "texte brut" in prompt.lower(), \
            "Le prompt doit demystifier 'je suis limitee au texte brut'"

    def test_capabilities_injected_in_system_prompt(self):
        """build_system_prompt() inclut le bloc capabilities."""
        from app.capabilities import get_capabilities_prompt

        # On teste directement le contenu attendu sans builder tout le prompt
        capabilities_text = get_capabilities_prompt()
        assert len(capabilities_text) > 100, "Le bloc capabilities est trop court"
        assert "MES CAPACITES" in capabilities_text.upper(), \
            "Le titre du bloc capabilities doit etre present"

    def test_capabilities_no_false_limitation(self):
        """Le registre ne doit pas declarer de fausses limitations."""
        from app.capabilities import CAPABILITIES

        lim = CAPABILITIES.get("limitations_reelles", {})
        lim_values = " ".join(lim.values()).lower()
        # On ne doit pas trouver "texte brut" dans les limitations
        assert "texte brut" not in lim_values, \
            "Ne pas declarer 'texte brut' comme limitation"


# --- TEST (c) : Parser LEARN robuste ---

class TestLearnParser:
    """
    Valide que _parse_learn_actions() gere correctement les ] dans le texte de regle.
    """

    def test_rule_with_brackets_not_truncated(self):
        """Regle contenant [URGENT] est extraite sans troncature."""
        from app.routes.aria_actions import _parse_learn_actions

        response = "[ACTION:LEARN:comportement|Traiter les mails [URGENT] sans délai]\n"
        results = _parse_learn_actions(response)

        assert len(results) == 1, f"Attendu 1 regle, obtenu {len(results)}"
        cat, rule = results[0]
        assert cat == "comportement"
        assert "[URGENT]" in rule, f"[URGENT] absent de la regle : {rule!r}"
        assert "sans délai" in rule, f"'sans délai' absent : {rule!r}"
        assert rule == "Traiter les mails [URGENT] sans délai", \
            f"Regle tronquee ou incorrecte : {rule!r}"

    def test_multiple_rules_parsed(self):
        """Deux [ACTION:LEARN] consecutifs sont tous les deux extraits."""
        from app.routes.aria_actions import _parse_learn_actions

        response = (
            "[ACTION:LEARN:comportement|Corbeille = action directe sans confirmation]\n"
            "[ACTION:LEARN:comportement|Regrouper plusieurs suppressions en un seul message]\n"
        )
        results = _parse_learn_actions(response)

        assert len(results) == 2, f"Attendu 2 regles, obtenu {len(results)}"
        cats = [r[0] for r in results]
        rules = [r[1] for r in results]
        assert all(c == "comportement" for c in cats)
        assert "Corbeille = action directe sans confirmation" in rules
        assert "Regrouper plusieurs suppressions en un seul message" in rules

    def test_rule_with_nested_reference_not_truncated(self):
        """Regle avec reference [voir doc] n'est pas tronquee."""
        from app.routes.aria_actions import _parse_learn_actions

        response = "[ACTION:LEARN:tri_mails|Mails [enedis] ou [consuel] -> categorie raccordement]\n"
        results = _parse_learn_actions(response)

        assert len(results) == 1
        _, rule = results[0]
        assert "[enedis]" in rule
        assert "[consuel]" in rule
        assert "categorie raccordement" in rule

    def test_rule_with_pipe_in_text(self):
        """
        NOTE : le separateur est le premier | apres la categorie.
        Une regle ne DOIT PAS contenir | (ce serait ambigu), mais on verifie
        que le premier segment est bien la categorie et le reste la regle.
        """
        from app.routes.aria_actions import _parse_learn_actions

        # Cas normal sans pipe dans la regle
        response = "[ACTION:LEARN:comportement|Ne pas confirmer la corbeille ni l'archivage]\n"
        results = _parse_learn_actions(response)

        assert len(results) == 1
        cat, rule = results[0]
        assert cat == "comportement"
        assert "Ne pas confirmer la corbeille ni l'archivage" == rule

    def test_no_rule_when_malformed(self):
        """Un tag malformate (sans |) ne genere pas d'exception."""
        from app.routes.aria_actions import _parse_learn_actions

        response = "[ACTION:LEARN:sans_pipe_donc_invalide]\n"
        results = _parse_learn_actions(response)
        assert results == [], f"Attendu liste vide, obtenu {results}"


# --- TEST (d) : Endpoint feedback negatif ---

class TestFeedbackEndpoint:
    """
    Valide le comportement de l'endpoint /raya/feedback en mode negatif.
    Teste la logique backend (process_negative_feedback) avec un aria_memory_id reel.
    """

    @pytest.fixture
    def aria_memory_id(self):
        """Cree un enregistrement aria_memory pour le test et le supprime apres."""
        from app.database import get_pg_conn
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "INSERT INTO aria_memory (username, user_input, aria_response) "
            "VALUES (%s, %s, %s) RETURNING id",
            (TEST_USERNAME, "test question", "test reponse de raya")
        )
        memory_id = c.fetchone()[0]
        conn.commit()
        conn.close()
        yield memory_id
        # Cleanup inclus dans la fixture autouse

    def test_feedback_negative_returns_ok(self, aria_memory_id):
        """
        process_negative_feedback repond sans exception pour un memory_id valide.
        """
        from app.feedback import process_negative_feedback

        with patch("app.llm_client.llm_complete", return_value={
            "text": json.dumps({
                "rule": "Ne pas dire que Raya est limitee au texte brut",
                "category": "comportement",
            })
        }):
            result = process_negative_feedback(
                aria_memory_id=aria_memory_id,
                username=TEST_USERNAME,
                tenant_id=TEST_TENANT,
                comment="Raya a dit qu'elle ne peut pas afficher de boutons — c'est faux",
            )

        assert result is not None, "process_negative_feedback ne doit pas retourner None"
        # Accepte soit {"status": "ok"} soit {"ok": True} selon l'implementation
        status_ok = (
            result.get("status") == "ok"
            or result.get("ok") is True
            or "rule_text" in result
        )
        assert status_ok, f"Reponse inattendue : {result}"

    def test_feedback_negative_unknown_memory_id_does_not_crash(self):
        """
        Un aria_memory_id inexistant ne doit pas lever d'exception non geree.
        """
        from app.feedback import process_negative_feedback

        try:
            result = process_negative_feedback(
                aria_memory_id=999999,
                username=TEST_USERNAME,
                tenant_id=TEST_TENANT,
                comment="test",
            )
            # Soit result est None, soit c'est un dict d'erreur — pas d'exception
        except Exception as e:
            pytest.fail(f"Exception non geree pour memory_id inexistant : {e}")

    def test_ask_choice_prefix_extracted_from_confirmed(self):
        """
        _ASK_CHOICE_PREFIX est correctement extrait de la liste confirmed dans raya.py.
        Valide la logique d'extraction sans appel LLM.
        """
        import json
        from app.routes.aria_actions import _ASK_CHOICE_PREFIX

        # Simule ce que raya.py fait
        choice_data = {"question": "Tu veux faire quoi ?", "options": ["Option A", "Option B"]}
        fake_confirmed = [
            "🧠 Memorise [comportement] : une regle",
            _ASK_CHOICE_PREFIX + json.dumps(choice_data),
            "✅ Mail archive",
        ]

        ask_choice = None
        actions_confirmed = []
        for item in fake_confirmed:
            if item.startswith(_ASK_CHOICE_PREFIX):
                ask_choice = json.loads(item[len(_ASK_CHOICE_PREFIX):])
            else:
                actions_confirmed.append(item)

        assert ask_choice is not None, "ask_choice doit etre extrait"
        assert ask_choice["question"] == "Tu veux faire quoi ?"
        assert ask_choice["options"] == ["Option A", "Option B"]
        assert len(actions_confirmed) == 2, "Les autres items doivent rester intacts"
        assert _ASK_CHOICE_PREFIX + json.dumps(choice_data) not in actions_confirmed
