"""
Tests de régression Phase 0.
Chaque test verrouille un fix spécifique. S'il échoue, c'est qu'un bug est revenu.

Pour lancer :
    pytest tests/test_phase0_blockers.py -v
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.rule_engine import get_memoire_param, get_rules_by_category
from app.memory_rules import save_rule
from app.pending_actions import (
    queue_action, get_pending, confirm_action, cancel_action, is_sensitive,
)
from tests.conftest import TEST_USERNAME, TEST_TENANT

client = TestClient(app)


# ─── B1 : Auth bypass ───

def test_b1_raya_endpoint_requires_auth():
    """Une requête /raya sans session doit retourner 401."""
    response = client.post("/raya", json={"query": "test"})
    assert response.status_code == 401
    assert "Authentification requise" in response.json().get("detail", "")


def test_b1_token_status_requires_auth():
    """L'endpoint /token-status doit aussi exiger l'auth."""
    response = client.get("/token-status")
    assert response.status_code == 401


# ─── B4 : Signatures unifiées ───

def test_b4_get_memoire_param_canonical_signature():
    """get_memoire_param doit prendre (username, param, default)."""
    save_rule(category="memoire", rule="test_param:42", username=TEST_USERNAME)
    result = get_memoire_param(TEST_USERNAME, "test_param", 0)
    assert result == 42
    assert isinstance(result, int)


def test_b4_get_memoire_param_inverted_args_raises():
    """L'ancien ordre (param, default, username) doit lever TypeError."""
    from app.memory_rules import get_memoire_param as deprecated
    with pytest.raises(TypeError):
        deprecated("synth_threshold", 15, TEST_USERNAME)


def test_b4_get_rules_by_category_canonical_signature():
    """get_rules_by_category doit prendre (username, category)."""
    save_rule(category="test_cat", rule="règle test", username=TEST_USERNAME)
    rules = get_rules_by_category(TEST_USERNAME, "test_cat")
    assert isinstance(rules, list)
    assert "règle test" in rules


# ─── B5 : save_rule ne fusionne pas les contradictoires ───

def test_b5_save_rule_does_not_merge_contradictory():
    """
    Deux règles différentes (même catégorie) doivent coexister, pas se fusionner.
    """
    rule1 = "les mails d'Enedis sont automatiques et à archiver"
    rule2 = "les mails d'Enedis sont urgents et à traiter immédiatement"

    id1 = save_rule(category="test_contradict", rule=rule1, username=TEST_USERNAME)
    id2 = save_rule(category="test_contradict", rule=rule2, username=TEST_USERNAME)

    assert id1 != id2, "Les deux règles contradictoires ont été fusionnées"
    rules = get_rules_by_category(TEST_USERNAME, "test_contradict")
    assert len(rules) == 2
    assert rule1 in rules
    assert rule2 in rules


def test_b5_save_rule_reinforces_exact_duplicate():
    """Une règle identique (modulo casse/espaces) doit être renforcée, pas dupliquée."""
    rule = "Les contacts internes ont la priorité"
    id1 = save_rule(category="test_dup", rule=rule, username=TEST_USERNAME)
    id2 = save_rule(category="test_dup", rule="  les contacts internes ont la priorité  ", username=TEST_USERNAME)

    assert id1 == id2, "Les règles identiques doivent renforcer, pas dupliquer"
    rules = get_rules_by_category(TEST_USERNAME, "test_dup")
    assert len(rules) == 1


# ─── B2 : Queue de confirmation ───

def test_b2_sensitive_actions_recognized():
    """Les actions sensibles doivent être reconnues comme telles."""
    assert is_sensitive("REPLY")
    assert is_sensitive("DELETE")
    assert is_sensitive("TEAMS_MSG")
    assert is_sensitive("MOVEDRIVE")
    assert is_sensitive("CREATEEVENT")
    assert not is_sensitive("LISTDRIVE")
    assert not is_sensitive("READ")
    assert not is_sensitive("ARCHIVE")
    assert not is_sensitive("LEARN")
    assert not is_sensitive("SYNTH")


def test_b2_queue_and_confirm_action():
    """Une action mise en queue doit être confirmable."""
    action_id = queue_action(
        tenant_id=TEST_TENANT, username=TEST_USERNAME,
        action_type="REPLY",
        payload={"message_id": "test_msg_id_with_more_than_20_chars", "reply_text": "Bonjour"},
        label="Test reply",
    )

    pending = get_pending(username=TEST_USERNAME, tenant_id=TEST_TENANT)
    assert any(p["id"] == action_id for p in pending)

    action = confirm_action(action_id, TEST_USERNAME, TEST_TENANT)
    assert action is not None
    assert action["action_type"] == "REPLY"

    # Après confirmation, ne doit plus apparaître en pending
    pending = get_pending(username=TEST_USERNAME, tenant_id=TEST_TENANT)
    assert not any(p["id"] == action_id for p in pending)


def test_b2_cancel_action():
    """Une action en queue doit pouvoir être annulée."""
    action_id = queue_action(
        tenant_id=TEST_TENANT, username=TEST_USERNAME,
        action_type="DELETE",
        payload={"message_id": "test_msg_id_with_more_than_20_chars"},
        label="Test delete",
    )
    ok = cancel_action(action_id, TEST_USERNAME, TEST_TENANT, reason="Test")
    assert ok

    pending = get_pending(username=TEST_USERNAME, tenant_id=TEST_TENANT)
    assert not any(p["id"] == action_id for p in pending)


def test_b2_cannot_confirm_other_user_action():
    """Un user ne doit pas pouvoir confirmer l'action d'un autre user."""
    action_id = queue_action(
        tenant_id=TEST_TENANT, username=TEST_USERNAME,
        action_type="REPLY",
        payload={"message_id": "test_msg_id_with_more_than_20_chars", "reply_text": "x"},
        label="Test",
    )
    result = confirm_action(action_id, "other_user", TEST_TENANT)
    assert result is None


# ─── M3 : learn_from_correction ne pollue pas ───

def test_m3_learn_from_correction_skips_empty_original():
    """
    Ne doit rien stocker si l'original est vide ou identique au corrected.
    """
    from app.memory_style import learn_from_correction
    from app.database import get_pg_conn

    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM aria_style_examples WHERE username = %s", (TEST_USERNAME,))
    count_before = c.fetchone()[0]
    conn.close()

    learn_from_correction(original="", corrected="Bonjour Madame", context="test", username=TEST_USERNAME)
    learn_from_correction(original="Hi there", corrected="Hi there", context="test", username=TEST_USERNAME)
    learn_from_correction(original="  Hi there  ", corrected="Hi there", context="test", username=TEST_USERNAME)

    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM aria_style_examples WHERE username = %s", (TEST_USERNAME,))
    count_after = c.fetchone()[0]
    conn.close()

    assert count_after == count_before, "learn_from_correction a stocké une fausse correction"


def test_m3_learn_from_correction_stores_real_correction():
    """Une vraie correction (original != corrected) doit être stockée."""
    from app.memory_style import learn_from_correction
    from app.database import get_pg_conn

    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM aria_style_examples WHERE username = %s", (TEST_USERNAME,))
    count_before = c.fetchone()[0]
    conn.close()

    learn_from_correction(
        original="Bonjour, je vous envoie le devis demandé.",
        corrected="Bonjour Monsieur Bruneau, veuillez trouver ci-joint le devis demandé. Cordialement.",
        context="réponse mail",
        username=TEST_USERNAME,
    )

    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM aria_style_examples WHERE username = %s", (TEST_USERNAME,))
    count_after = c.fetchone()[0]
    conn.close()

    assert count_after == count_before + 1, "La vraie correction n'a pas été stockée"
