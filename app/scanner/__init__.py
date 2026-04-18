"""
Scanner Universel — vectorisation exhaustive pilotee par manifest.

Voir docs/raya_scanner_universel_plan.md pour l architecture complete.

Architecture en 3 couches :
- orchestrator : lit manifest, planifie runs, gere checkpointing
- adapter_odoo : fetch pagine + transversaux (mail.message, tracking, attach)
- processor : texte composite + embedding + ecriture DB

Chaque couche est independante et reutilisable pour d autres sources
(Drive, Teams, SharePoint...).
"""

from app.scanner.orchestrator import (
    create_run, update_progress, finish_run, fail_run,
    get_run_status, list_recent_runs,
)

__all__ = [
    "create_run", "update_progress", "finish_run", "fail_run",
    "get_run_status", "list_recent_runs",
]
