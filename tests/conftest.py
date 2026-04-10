"""
Fixtures pytest pour les tests Raya.
Tous les tests utilisent un username isolé pour ne pas polluer la prod.
"""
import pytest
from app.database import get_pg_conn

TEST_USERNAME = "test_phase0"
TEST_TENANT = "test_tenant"


@pytest.fixture(autouse=True)
def cleanup_test_data():
    """Nettoie les données de test avant et après chaque test."""
    _cleanup()
    yield
    _cleanup()


def _cleanup():
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("DELETE FROM aria_rules WHERE username = %s", (TEST_USERNAME,))
    c.execute("DELETE FROM pending_actions WHERE username = %s", (TEST_USERNAME,))
    c.execute("DELETE FROM reply_learning_memory WHERE username = %s", (TEST_USERNAME,))
    c.execute("DELETE FROM aria_style_examples WHERE username = %s", (TEST_USERNAME,))
    conn.commit()
    conn.close()
