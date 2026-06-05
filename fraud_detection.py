"""
Défi — Détection de fraude financière.

Vous devez implémenter la fonction `detect_fraud`.
La fonction `load_transactions` vous est FOURNIE (ne la modifiez pas).
"""

import csv
import statistics
from datetime import datetime, timezone


def load_transactions(path):
    """Lit un fichier CSV de transactions et renvoie une liste de dicts."""
    transactions = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            transactions.append(_clean_row(row))
    return transactions


def _clean_row(row):
    def get(key):
        v = row.get(key)
        return v.strip() if isinstance(v, str) and v.strip() != "" else None

    amount_raw = get("amount")
    try:
        amount = float(amount_raw) if amount_raw is not None else None
    except ValueError:
        amount = None

    card_raw = get("card_present")
    if card_raw is None:
        card_present = None
    else:
        card_present = card_raw.lower() in ("true", "1", "yes", "oui")

    return {
        "transaction_id": get("transaction_id"),
        "timestamp": get("timestamp"),
        "user_id": get("user_id"),
        "amount": amount,
        "currency": get("currency"),
        "merchant": get("merchant"),
        "country": get("country"),
        "card_present": card_present,
    }


_REQUIRED_FIELDS = ("transaction_id", "user_id", "amount", "currency", "merchant", "country")
_GEO_WINDOW_HOURS = 24
_AMOUNT_HISTORY_MIN = 3
_AMOUNT_SPIKE_FACTOR = 10


def _parse_timestamp(value):
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (TypeError, ValueError):
        return None


def _hours_apart(left, right):
    left_ts = _parse_timestamp(left.get("timestamp"))
    right_ts = _parse_timestamp(right.get("timestamp"))
    if left_ts is None or right_ts is None:
        return None
    return abs((left_ts - right_ts).total_seconds()) / 3600


def _missing_fields(transaction):
    missing = []
    for field in _REQUIRED_FIELDS:
        if transaction.get(field) is None:
            missing.append(field)
    return missing


def _user_history(transactions, user_id, before_index):
    return [
        tx
        for idx, tx in enumerate(transactions)
        if idx < before_index and tx.get("user_id") == user_id
    ]


def _user_batch(transactions, user_id):
    return [tx for tx in transactions if tx.get("user_id") == user_id]


def _has_rapid_country_change(transaction, batch):
    country = transaction.get("country")
    if not country:
        return False

    for other in batch:
        if other is transaction:
            continue
        other_country = other.get("country")
        if not other_country or other_country == country:
            continue
        hours = _hours_apart(transaction, other)
        if hours is not None and hours <= _GEO_WINDOW_HOURS:
            return True
    return False


def _is_amount_spike(amount, history):
    if amount is None or amount <= 0:
        return False

    prior_amounts = [
        tx.get("amount")
        for tx in history
        if isinstance(tx.get("amount"), (int, float)) and tx.get("amount") > 0
    ]
    if len(prior_amounts) < _AMOUNT_HISTORY_MIN:
        return False

    baseline = statistics.median(prior_amounts)
    if baseline <= 0:
        return False
    return amount >= baseline * _AMOUNT_SPIKE_FACTOR


def _build_result(transaction_id, fraud_score, is_suspicious, reason):
    return {
        "transaction_id": transaction_id,
        "fraud_score": round(max(0.0, min(1.0, fraud_score)), 2),
        "is_suspicious": is_suspicious,
        "reason": reason,
    }


def detect_fraud(transactions):
    """Analyse une liste de transactions et renvoie un verdict pour chacune.

    Retour : list[dict] avec transaction_id, fraud_score (0-1),
    is_suspicious (bool), reason (str) — un résultat par transaction, même ordre.
    """
    results = []

    for index, transaction in enumerate(transactions):
        transaction_id = transaction.get("transaction_id") or f"UNKNOWN-{index}"
        amount = transaction.get("amount")
        missing = _missing_fields(transaction)

        if amount is None or amount <= 0:
            results.append(
                _build_result(
                    transaction_id,
                    0.9,
                    True,
                    "Montant nul ou négatif",
                )
            )
            continue

        if missing:
            fields = ", ".join(missing)
            results.append(
                _build_result(
                    transaction_id,
                    0.85,
                    True,
                    f"Champs obligatoires manquants: {fields}",
                )
            )
            continue

        user_id = transaction.get("user_id")
        history = _user_history(transactions, user_id, index)
        batch = _user_batch(transactions, user_id)

        if _has_rapid_country_change(transaction, batch):
            results.append(
                _build_result(
                    transaction_id,
                    0.88,
                    True,
                    "Deux pays différents en trop peu de temps",
                )
            )
            continue

        if _is_amount_spike(amount, history):
            results.append(
                _build_result(
                    transaction_id,
                    0.9,
                    True,
                    "Montant très supérieur à l'habitude du client",
                )
            )
            continue

        results.append(
            _build_result(
                transaction_id,
                0.0,
                False,
                "Transaction conforme au profil du client",
            )
        )

    return results
