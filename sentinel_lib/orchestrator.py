"""Orchestration optionnelle — enveloppe analyze_fraud sans la modifier."""

from __future__ import annotations

from fraud_detection import analyze_fraud

from sentinel_lib.history_store import save_run
from sentinel_lib.human_responses import humanize_result


def run_session_analysis(
    transactions: list,
    config: dict | None,
    ml_bundle=None,
    *,
    humanize: bool = False,
    persist_history: bool = True,
):
    """
    Lance l'analyse via le moteur officiel et enrichit le résultat pour l'UI.

    - Ne modifie jamais fraud_score / is_suspicious / reason (contrat intact)
    - Ajoute human_reason (affichage seulement)
    - Sauvegarde l'historique si demandé
    """
    raw_results = analyze_fraud(transactions, config, ml_bundle)
    enriched = []

    for tx, result in zip(transactions, raw_results):
        item = dict(result)
        item["human_reason"] = humanize_result(tx, result) if humanize else None
        enriched.append(item)

    if persist_history:
        save_run(
            transactions,
            enriched,
            meta={
                "fusion_mode": (config or {}).get("fusion_mode", "rules_only"),
                "ml_enabled": (config or {}).get("ml_enabled", False),
                "human_mode": humanize,
            },
        )

    return enriched
