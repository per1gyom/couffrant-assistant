"""
DEPRECATED — shim de compatibilité, conservé uniquement pour eviter
de casser des imports externes non répertoriés.
Le code réel est dans raya.py. Importer directement depuis app.routes.raya.
"""
from app.routes.raya import router, RayaQuery, _build_user_content  # noqa
