"""
Tests d'isolation multi-tenant — Phase 2.

Vérifient que deux tenants distincts ne peuvent jamais accéder aux données
l'un de l'autre, même par accident ou par oubli de filtre.

Pour lancer :
    pytest tests/test_phase2_isolation.py -v
"""
import pytest
from app.database import get_pg_conn
from app.memory_rules import save_rule
from app.rule_engine import get_rules_by_category, get_memoire_param
from app.memory_synthesis import save_insight, get_aria_insights

TENANT_A = "test_tenant_alpha"
TENANT_B = "test_tenant_beta"
USER_A   = "alice_alpha"
USER_B   = "bob_beta"


@pytest.fixture(autouse=True)
def cleanup():
    _cleanup_all()
    yield
    _cleanup_all()


def _cleanup_all():
    conn = get_pg_conn()
    c = conn.cursor()
    for table in ['aria_rules', 'aria_insights']:
        c.execute(
            f"DELETE FROM {table} WHERE username IN (%s, %s)",
            (USER_A, USER_B)
        )
    conn.commit()
    conn.close()


# ─── TEST 1 : règles isolées entre tenants ───

def test_isolation_rules_between_tenants():
    """Une règle créée dans tenant A ne doit JAMAIS apparaître dans tenant B."""
    save_rule(category="test", rule="Règle exclusive A",
              username=USER_A, tenant_id=TENANT_A)
    save_rule(category="test", rule="Règle exclusive B",
              username=USER_B, tenant_id=TENANT_B)

    rules_a = get_rules_by_category(USER_A, "test", tenant_id=TENANT_A)
    rules_b = get_rules_by_category(USER_B, "test", tenant_id=TENANT_B)

    assert "Règle exclusive A" in rules_a
    assert "Règle exclusive B" not in rules_a, "Fuite : règle B visible dans tenant A"

    assert "Règle exclusive B" in rules_b
    assert "Règle exclusive A" not in rules_b, "Fuite : règle A visible dans tenant B"


# ─── TEST 2 : même username dans deux tenants différents ───

def test_isolation_same_username_different_tenants():
    """
    Cas critique : deux tenants peuvent avoir un user 'admin' chacun.
    Leurs règles ne doivent JAMAIS se mélanger.
    """
    save_rule(category="test", rule="Admin tenant A",
              username="admin_shared", tenant_id=TENANT_A)
    save_rule(category="test", rule="Admin tenant B",
              username="admin_shared", tenant_id=TENANT_B)

    rules_a = get_rules_by_category("admin_shared", "test", tenant_id=TENANT_A)
    rules_b = get_rules_by_category("admin_shared", "test", tenant_id=TENANT_B)

    assert "Admin tenant A" in rules_a
    assert "Admin tenant B" not in rules_a, "Fuite : règle tenant B visible dans tenant A (même username)"

    assert "Admin tenant B" in rules_b
    assert "Admin tenant A" not in rules_b, "Fuite : règle tenant A visible dans tenant B (même username)"

    # Nettoyage spécifique pour cet utilisateur partagé
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("DELETE FROM aria_rules WHERE username = 'admin_shared'")
    conn.commit()
    conn.close()


# ─── TEST 3 : insights isolés entre tenants ───

def test_isolation_insights_between_tenants():
    """Les insights sont aussi étanches entre tenants."""
    save_insight(topic="test_topic", insight="Insight propre à A",
                 username=USER_A, tenant_id=TENANT_A)
    save_insight(topic="test_topic_b", insight="Insight propre à B",
                 username=USER_B, tenant_id=TENANT_B)

    insights_a = get_aria_insights(limit=50, username=USER_A, tenant_id=TENANT_A)
    insights_b = get_aria_insights(limit=50, username=USER_B, tenant_id=TENANT_B)

    assert "Insight propre à A" in insights_a
    assert "Insight propre à B" not in insights_a, "Fuite : insight B visible dans tenant A"

    assert "Insight propre à B" in insights_b
    assert "Insight propre à A" not in insights_b, "Fuite : insight A visible dans tenant B"


# ─── TEST 4 : save_rule stocke bien le tenant_id en base ───

def test_save_rule_stores_tenant_id():
    """Vérifier que tenant_id est bien écrit dans la table aria_rules."""
    save_rule(category="test_tenant_check", rule="Règle avec tenant",
              username=USER_A, tenant_id=TENANT_A)

    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("""
        SELECT tenant_id FROM aria_rules
        WHERE username = %s AND category = 'test_tenant_check'
        LIMIT 1
    """, (USER_A,))
    row = c.fetchone()
    conn.close()

    assert row is not None, "La règle n'a pas été insérée"
    assert row[0] == TENANT_A, f"tenant_id attendu '{TENANT_A}', obtenu '{row[0]}'"


# ─── TEST 5 : save_insight stocke bien le tenant_id en base ───

def test_save_insight_stores_tenant_id():
    """Vérifier que tenant_id est bien écrit dans la table aria_insights."""
    save_insight(topic="tenant_check_topic", insight="Contenu de l'insight",
                 username=USER_B, tenant_id=TENANT_B)

    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("""
        SELECT tenant_id FROM aria_insights
        WHERE username = %s AND topic = 'tenant_check_topic'
        LIMIT 1
    """, (USER_B,))
    row = c.fetchone()
    conn.close()

    assert row is not None, "L'insight n'a pas été inséré"
    assert row[0] == TENANT_B, f"tenant_id attendu '{TENANT_B}', obtenu '{row[0]}'"
