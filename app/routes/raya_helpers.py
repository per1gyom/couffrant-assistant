"""
raya_helpers : utilitaires partages entre raya.py (endpoint) et
raya_agent_core.py (V2 mode agent).

Historique :
  - 21/04/2026 : split de raya.py en plusieurs fichiers (R1).
  - 05/05/2026 soir : SUPPRESSION DE LA V1 (_raya_core,
    _get_microsoft_token, _extract_suggestions). 15 jours sans aucun
    appel V1 en production -> code mort. La logique conversationnelle
    vit desormais entierement dans raya_agent_core.py (boucle agent V2).

Ce qui reste ici est uniquement ce qui est partage avec V2 :
  - _strip_action_tags (post-traitement reponse)
  - RayaQuery, FeedbackPayload (modeles Pydantic d entree d API)
  - _build_user_content (reexport noqa depuis raya_content)
"""
from typing import Optional
from pydantic import BaseModel

# Reexport pour retrocompat : raya.py importe _build_user_content depuis ici.
from app.routes.raya_content import _build_user_content  # noqa: F401


def _strip_action_tags(text: str) -> str:
    """Retire les tags [ACTION:...] en gerant les crochets imbriques (domaines Odoo, JSON)."""
    result = []
    i = 0
    n = len(text)
    while i < n:
        rest = text[i:]
        if rest.startswith('[ACTION:') or rest.startswith('`[ACTION:'):
            skip_bt = 1 if text[i] == '`' else 0
            j = i + skip_bt
            depth = 0
            while j < n:
                if text[j] == '[':
                    depth += 1
                elif text[j] == ']':
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
                j += 1
            if j < n and text[j] == '`':
                j += 1
            i = j
        else:
            result.append(text[i])
            i += 1
    return ''.join(result)


class RayaQuery(BaseModel):
    query: str
    file_data: Optional[str] = None
    file_type: Optional[str] = None
    file_name: Optional[str] = None


class FeedbackPayload(BaseModel):
    aria_memory_id: int
    feedback_type: str
    comment: Optional[str] = None
