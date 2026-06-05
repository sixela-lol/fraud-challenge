"""Chaîne de traitement — trace les étapes et orchestre plusieurs modèles.

Couche d'affichage / orchestration : appelle le moteur officiel sans le modifier.
"""

from __future__ import annotations

import statistics

from fraud_detection import (
    _clean_row,  # réutilise le nettoyage officiel (lecture seule)
    analyze_fraud,
    predict_fraud_scores,
)


def trace_steps(transactions, config, results):
    """Retourne la liste des étapes de traitement avec un compteur lisible.

    Sert à visualiser le parcours de la donnée, sans rien recalculer
    qui modifierait le verdict.
    """
    n = len(transactions)
    amounts = [t.get("amount") for t in transactions if isinstance(t.get("amount"), (int, float))]
    missing = sum(
        1 for t in transactions
        if any(t.get(f) is None for f in config.get("required_fields", []))
    )
    alerts = sum(1 for r in results if r.get("is_suspicious"))
    ml_on = bool(config.get("ml_enabled"))

    return [
        {
            "step": "1 · Ingestion",
            "desc": "Lecture du fichier CSV et chargement en mémoire",
            "detail": f"{n} transaction(s) reçue(s)",
            "icon": "📥",
        },
        {
            "step": "2 · Nettoyage",
            "desc": "Normalisation des types, gestion des champs vides",
            "detail": f"{missing} transaction(s) avec champ manquant",
            "icon": "🧹",
        },
        {
            "step": "3 · Profil client",
            "desc": "Calcul de l'historique et de la médiane par client",
            "detail": (
                f"médiane montants ≈ {statistics.median(amounts):.0f}"
                if amounts else "aucun montant exploitable"
            ),
            "icon": "👤",
        },
        {
            "step": "4 · Règles métier",
            "desc": "Application de l'arbre de décision configurable",
            "detail": f"{sum(1 for k,v in config.get('rules',{}).items() if v.get('enabled'))} règle(s) active(s)",
            "icon": "📐",
        },
        {
            "step": "5 · Modèle IA",
            "desc": "Score d'anomalie (optionnel)",
            "detail": "activé" if ml_on else "désactivé",
            "icon": "🧠",
        },
        {
            "step": "6 · Fusion",
            "desc": f"Combinaison des signaux ({config.get('fusion_mode','rules_only')})",
            "detail": f"{alerts} alerte(s) retenue(s)",
            "icon": "🔀",
        },
        {
            "step": "7 · Verdict",
            "desc": "Score final, statut et explication par transaction",
            "detail": f"{n - alerts} conforme(s) · {alerts} suspecte(s)",
            "icon": "✅",
        },
    ]


def apply_data_edits(edited_rows):
    """Reconstruit des transactions propres à partir de lignes éditées (UI).

    Réutilise le nettoyage officiel `_clean_row` pour rester cohérent.
    """
    cleaned = []
    for row in edited_rows:
        raw = {
            "transaction_id": row.get("transaction_id"),
            "timestamp": row.get("timestamp"),
            "user_id": row.get("user_id"),
            "amount": "" if row.get("amount") is None else str(row.get("amount")),
            "currency": row.get("currency"),
            "merchant": row.get("merchant"),
            "country": row.get("country"),
            "card_present": str(row.get("card_present")).lower(),
        }
        cleaned.append(_clean_row(raw))
    return cleaned


def run_chain(transactions, config, stages):
    """Orchestration multi-modèles : exécute une chaîne d'étapes.

    `stages` est une liste de dicts :
      {"kind": "rules"} ou {"kind": "model", "bundle": <bundle>, "weight": float, "name": str}

    Stratégie : on part du verdict des règles (toujours fiable, garde
    l'explication), puis chaque modèle ajoute un score pondéré. Le statut
    final passe à "suspect" si le score combiné dépasse le seuil OU si une
    règle a déjà alerté. Les verdicts des règles ne sont jamais affaiblis.
    """
    base = analyze_fraud(transactions, config, None)  # règles seules
    threshold = float(config.get("ml_threshold", 0.55))

    contributions = [{"name": "Règles métier", "kind": "rules"}]
    combined = []
    for i, item in enumerate(base):
        combined.append({
            "transaction_id": item["transaction_id"],
            "rule_score": float(item["fraud_score"]),
            "rule_flag": bool(item["is_suspicious"]),
            "reason": item["reason"],
            "human_reason": item.get("human_reason"),
            "model_scores": {},
        })

    total_weight = 0.0
    for stage in stages:
        if stage.get("kind") != "model" or stage.get("bundle") is None:
            continue
        name = stage.get("name", "Modèle")
        weight = float(stage.get("weight", 0.5))
        total_weight += weight
        scores = predict_fraud_scores(stage["bundle"], transactions)
        contributions.append({"name": name, "kind": "model", "weight": weight})
        for idx, s in enumerate(scores):
            combined[idx]["model_scores"][name] = round(float(s), 2)

    final = []
    for row in combined:
        rule_score = row["rule_score"]
        model_vals = list(row["model_scores"].values())
        if model_vals and total_weight > 0:
            model_avg = sum(
                row["model_scores"][c["name"]] * c["weight"]
                for c in contributions if c["kind"] == "model"
            ) / total_weight
            final_score = max(rule_score, round(0.5 * rule_score + 0.5 * model_avg, 2))
        else:
            model_avg = 0.0
            final_score = rule_score

        suspicious = row["rule_flag"] or final_score >= threshold
        final.append({
            "transaction_id": row["transaction_id"],
            "fraud_score": round(min(1.0, final_score), 2),
            "is_suspicious": suspicious,
            "reason": row["reason"],
            "human_reason": row["human_reason"],
            "model_scores": row["model_scores"],
        })

    return final, contributions
