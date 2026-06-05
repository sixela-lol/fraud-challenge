"""Catalogue des modèles disponibles — métadonnées pour l'interface."""

MODEL_REGISTRY = {
    "rules_only": {
        "id": "rules_only",
        "name": "Moteur de règles",
        "type": "rules",
        "description": "Analyse par règles métier. Rapide, explicable, sans entraînement.",
        "requires_training": False,
        "default": True,
    },
    "isolation_forest": {
        "id": "isolation_forest",
        "name": "Forêt d'isolation",
        "type": "anomaly",
        "description": "Détecte les transactions qui sortent du lot sans étiquettes manuelles.",
        "requires_training": True,
        "default": False,
    },
    "decision_tree": {
        "id": "decision_tree",
        "name": "Arbre de décision",
        "type": "supervised",
        "description": "Apprend à partir des alertes existantes. Bon pour affiner le scoring.",
        "requires_training": True,
        "default": False,
    },
}


def list_models():
    """Retourne la liste des modèles enregistrés."""
    return list(MODEL_REGISTRY.values())


def get_model(model_id: str):
    """Retourne les métadonnées d'un modèle ou None."""
    return MODEL_REGISTRY.get(model_id)


def list_trainable_models():
    """Modèles nécessitant un entraînement."""
    return [m for m in MODEL_REGISTRY.values() if m.get("requires_training")]
