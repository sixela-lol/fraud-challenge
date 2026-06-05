"""Deuxième couche — vérification croisée des transactions « normales ».

Principe : les règles métier (couche 1) restent la référence. Cette couche
fait passer un modèle de prédiction (couche 2) sur TOUTES les transactions,
puis CONFRONTE les deux avis. Son intérêt principal : repérer les
transactions que les règles ont laissées passer mais que le modèle juge
douteuses → statut « À vérifier ». On ne modifie jamais le verdict des
règles, on ajoute un second regard.

Couche d'affichage / sécurité : n'altère pas detect_fraud().
"""

from __future__ import annotations

from fraud_detection import (
    build_training_labels,
    detect_fraud,
    predict_fraud_scores,
    train_fraud_model,
)

# Statuts du croisement règles × modèle.
CONFIRME = "confirme"            # règles OK + modèle OK  → sain confirmé
A_VERIFIER = "a_verifier"        # règles OK + modèle doute → filet de sécurité
ALERTE_CONFIRMEE = "alerte_ok"   # règles alerte + modèle d'accord
ALERTE_ATTENUEE = "alerte_att"   # règles alerte + modèle rassure

STATUS_LABELS = {
    CONFIRME: ("Sain confirmé", "#22c55e"),
    A_VERIFIER: ("À vérifier", "#f59e0b"),
    ALERTE_CONFIRMEE: ("Alerte confirmée", "#dc2626"),
    ALERTE_ATTENUEE: ("Alerte (modèle rassure)", "#3b82f6"),
}


def ensure_model(transactions, ml_bundle=None, model_type="isolation_forest"):
    """Retourne un modèle utilisable. En entraîne un à la volée si besoin.

    Les libellés d'entraînement viennent des règles (couche 1), donc la
    couche 2 apprend à reconnaître ce que les règles considèrent sain.
    """
    if ml_bundle is not None:
        return ml_bundle
    labels = build_training_labels(detect_fraud(transactions))
    return train_fraud_model(
        transactions, labels, {"model_type": model_type, "max_depth": 6},
    )


def verify_transactions(transactions, rule_results, ml_bundle, threshold=0.55):
    """Confronte couche 1 (règles) et couche 2 (modèle).

    Retourne (lignes, résumé). Chaque ligne contient le verdict des règles,
    le score du modèle et le statut du croisement.
    """
    scores = predict_fraud_scores(ml_bundle, transactions)
    rows = []
    summary = {CONFIRME: 0, A_VERIFIER: 0, ALERTE_CONFIRMEE: 0, ALERTE_ATTENUEE: 0}

    for tx, res, score in zip(transactions, rule_results, scores):
        score = round(float(score), 2)
        rule_flag = bool(res.get("is_suspicious"))
        model_flag = score >= threshold

        if rule_flag and model_flag:
            status = ALERTE_CONFIRMEE
        elif rule_flag and not model_flag:
            status = ALERTE_ATTENUEE
        elif not rule_flag and model_flag:
            status = A_VERIFIER
        else:
            status = CONFIRME
        summary[status] += 1

        label, color = STATUS_LABELS[status]
        rows.append({
            "transaction_id": res.get("transaction_id"),
            "user_id": tx.get("user_id"),
            "amount": tx.get("amount"),
            "currency": tx.get("currency"),
            "country": tx.get("country"),
            "rule_flag": rule_flag,
            "rule_reason": res.get("reason"),
            "model_score": score,
            "model_flag": model_flag,
            "status": status,
            "status_label": label,
            "status_color": color,
            # Accord entre les deux couches (sécurité).
            "agree": rule_flag == model_flag,
        })

    total = len(rows) or 1
    summary["accord_pct"] = round(
        100 * sum(1 for r in rows if r["agree"]) / total, 1
    )
    return rows, summary
