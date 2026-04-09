"""
DEPRECATED — shim de compatibilité.
Importer directement depuis app.routes.aria_context.
"""
from app.routes.aria_context import (  # noqa
    load_user_tools, load_db_context, load_live_mails,
    load_agenda, load_teams_context, load_mail_filter_summary,
    build_system_prompt, GUARDRAILS,
)
