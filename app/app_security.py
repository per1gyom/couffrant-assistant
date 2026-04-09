"""
DEPRECATED — couche de compatibilité, conservée pour les imports existants.
Le code réel est dans :
  app.security_auth  → hash_password, verify_password, check_rate_limit...
  app.security_tools → get_user_tools, set_user_tool, scopes...
  app.security_users → authenticate, create_user, delete_user, list_users...
"""
from app.security_auth import (  # noqa
    hash_password, verify_password,
    check_rate_limit, record_failed_attempt, clear_attempts,
    validate_password_strength, unlock_account,
)
from app.security_tools import (  # noqa
    get_user_tools, set_user_tool, remove_user_tool, init_default_tools,
    ALL_SCOPES, SCOPE_ADMIN, SCOPE_TENANT_ADMIN, SCOPE_CS, SCOPE_USER, DEFAULT_TENANT,
)
from app.security_users import (  # noqa
    authenticate, create_user, update_user, delete_user, list_users,
    get_user_scope, get_tenant_id, get_users_in_tenant, update_last_login,
    init_default_user, generate_reset_token, validate_reset_token,
    consume_reset_token, must_reset_password_check, set_must_reset_password,
)
from app.app_security import LOGIN_PAGE_HTML  # noqa (LOGIN_PAGE_HTML reste dans app_security)
