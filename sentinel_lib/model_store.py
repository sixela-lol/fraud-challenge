"""Stockage des modèles entraînés — nommer, sauvegarder, charger, lister.

Persistance locale via pickle. Couche optionnelle : n'altère pas le moteur.
"""

from __future__ import annotations

import pickle
import re
from datetime import datetime, timezone
from pathlib import Path

MODELS_DIR = Path(__file__).parent.parent / "models"


def _safe_name(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", (name or "").strip())
    return slug.strip("_") or "modele"


def _meta_path(slug: str) -> Path:
    return MODELS_DIR / f"{slug}.meta.pkl"


def _model_path(slug: str) -> Path:
    return MODELS_DIR / f"{slug}.model.pkl"


def save_model(name: str, bundle: dict, note: str = "") -> dict:
    """Sauvegarde un modèle entraîné sous un nom lisible."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    slug = _safe_name(name)

    with open(_model_path(slug), "wb") as f:
        pickle.dump(bundle, f)

    meta = {
        "slug": slug,
        "name": name,
        "note": note,
        "model_type": bundle.get("model_type", "?"),
        "metrics": bundle.get("metrics", {}),
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(_meta_path(slug), "wb") as f:
        pickle.dump(meta, f)
    return meta


def list_saved_models() -> list[dict]:
    """Liste les modèles sauvegardés (métadonnées)."""
    if not MODELS_DIR.exists():
        return []
    metas = []
    for meta_file in MODELS_DIR.glob("*.meta.pkl"):
        try:
            with open(meta_file, "rb") as f:
                metas.append(pickle.load(f))
        except (pickle.PickleError, OSError):
            continue
    return sorted(metas, key=lambda m: m.get("saved_at", ""), reverse=True)


def load_model(slug: str):
    """Charge le bundle d'un modèle par son slug. None si absent."""
    path = _model_path(slug)
    if not path.exists():
        return None
    try:
        with open(path, "rb") as f:
            return pickle.load(f)
    except (pickle.PickleError, OSError):
        return None


def delete_model(slug: str) -> bool:
    """Supprime un modèle sauvegardé."""
    removed = False
    for path in (_model_path(slug), _meta_path(slug)):
        if path.exists():
            path.unlink()
            removed = True
    return removed
