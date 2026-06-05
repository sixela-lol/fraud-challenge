"""Bibliothèque de réponses naturelles — affichage UI uniquement."""

from __future__ import annotations

import random

# Clé = fragment reconnu dans le message technique d'origine
HUMAN_LIBRARY = {
    "Montant nul ou négatif": [
        "J'ai repéré un montant qui ne tient pas la route ({amount} {currency}). "
        "Je préfère alerter avant de valider.",
        "Pour le client {user_id}, ce montant ({amount} {currency}) est invalide. "
        "Je vous conseille de vérifier.",
    ],
    "Champs obligatoires manquants": [
        "Il manque des informations sur la transaction {transaction_id}. "
        "Sans ces données, je ne peux pas la valider sereinement.",
        "Données incomplètes pour {user_id} — je bloque par prudence.",
    ],
    "Transaction en double": [
        "Cette référence {transaction_id} apparaît deux fois. "
        "Ça ressemble à un doublon, je signale.",
    ],
    "Deux pays différents": [
        "Le client {user_id} est passé de {country} à un autre pays trop vite. "
        "Ce n'est pas réaliste physiquement.",
        "Déplacement géographique suspect pour {user_id} ({country}). "
        "À creuser de votre côté.",
    ],
    "Fréquence de transactions": [
        "Beaucoup d'opérations en peu de temps pour {user_id}. "
        "Le rythme est inhabituel.",
    ],
    "Montant très supérieur": [
        "Gros écart pour {user_id} : {amount} {currency} chez {merchant}, "
        "bien au-dessus de l'habitude.",
        "Cette dépense ({amount} {currency}) sort du profil habituel de {user_id}.",
    ],
    "sans carte physique": [
        "Paiement à distance inhabituel pour {user_id} ({amount} {currency}). "
        "Je recommande une vérification.",
    ],
    "Transaction conforme": [
        "Rien d'anormal ici — cette opération colle au profil de {user_id}.",
        "Tout semble cohérent pour {user_id}. Aucune action requise.",
    ],
    "Signal modèle": [
        "Mon analyse automatique détecte un comportement atypique "
        "(confiance {score}). Je vous laisse juger.",
    ],
    "corroboration modèle": [
        "Les règles et l'IA sont d'accord : cette transaction mérite votre attention.",
    ],
}


def _format_tx(tx: dict) -> dict:
    return {
        "transaction_id": tx.get("transaction_id") or "—",
        "user_id": tx.get("user_id") or "ce client",
        "amount": tx.get("amount") if tx.get("amount") is not None else "—",
        "currency": tx.get("currency") or "",
        "merchant": tx.get("merchant") or "un commerçant",
        "country": tx.get("country") or "un pays inconnu",
        "score": f"{float(tx.get('_score', 0)):.2f}",
    }


def _pick_template(reason: str) -> list[str] | None:
    for fragment, templates in HUMAN_LIBRARY.items():
        if fragment.lower() in reason.lower():
            return templates
    return None


def humanize_result(transaction: dict, result: dict) -> str:
    """Transforme un verdict technique en phrase lisible pour un non-expert."""
    reason = result.get("reason", "")
    ctx = _format_tx({**transaction, "_score": result.get("fraud_score", 0)})

    templates = _pick_template(reason)
    if templates:
        try:
            return random.choice(templates).format(**ctx)
        except KeyError:
            pass

    if result.get("is_suspicious"):
        return (
            f"Bonjour — la transaction {ctx['transaction_id']} de {ctx['user_id']} "
            f"({ctx['amount']} {ctx['currency']}) attire mon attention : {reason}"
        )
    return (
        f"La transaction {ctx['transaction_id']} de {ctx['user_id']} "
        f"me paraît normale."
    )
