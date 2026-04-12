"""Redirige vers le nouveau module actions/ — retrocompatibilite."""
from app.routes.actions import execute_actions, _ASK_CHOICE_PREFIX

__all__ = ["execute_actions", "_ASK_CHOICE_PREFIX"]
