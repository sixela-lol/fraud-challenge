"""
Défi — Détection de fraude financière.

Vous devez implémenter la fonction `detect_fraud`.
La fonction `load_transactions` vous est FOURNIE (ne la modifiez pas).
"""

import csv
import statistics
from copy import deepcopy
from datetime import datetime, timezone

import numpy as np

# ---------------------------------------------------------------------------
# Configuration par défaut (utilisée par la CI)
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "fusion_mode": "rules_only",
    "ml_enabled": False,
    "ml_weight": 0.35,
    "rules_weight": 0.65,
    "ml_threshold": 0.55,
    "required_fields": [
        "transaction_id",
        "user_id",
        "amount",
        "currency",
        "merchant",
        "country",
    ],
    "thresholds": {
        "geo_window_hours": 24,
        "amount_history_min": 3,
        "amount_spike_factor": 10,
        "freq_window_hours": 1,
        "freq_threshold": 5,
        "card_not_present_min": 500,
        "card_spike_factor": 3,
    },
    "ml": {
        "model_type": "isolation_forest",
        "max_depth": 6,
        "n_estimators": 120,
        "contamination": 0.12,
        "random_state": 42,
    },
    "rules": {
        "amount_invalid": {
            "enabled": True,
            "score": 0.9,
            "label": "Montant invalide",
            "message": "Montant nul ou négatif",
        },
        "missing_fields": {
            "enabled": True,
            "score": 0.85,
            "label": "Intégrité des données",
            "message": "Champs obligatoires manquants: {fields}",
        },
        "duplicate": {
            "enabled": True,
            "score": 0.87,
            "label": "Doublon",
            "message": "Transaction en double détectée",
        },
        "geo_anomaly": {
            "enabled": True,
            "score": 0.88,
            "label": "Anomalie géographique",
            "message": "Deux pays différents en trop peu de temps",
        },
        "frequency": {
            "enabled": True,
            "score": 0.86,
            "label": "Vélocité",
            "message": "Fréquence de transactions anormale",
        },
        "amount_spike": {
            "enabled": True,
            "score": 0.9,
            "label": "Dépense atypique",
            "message": "Montant très supérieur à l'habitude du client",
        },
        "card_not_present": {
            "enabled": True,
            "score": 0.84,
            "label": "Paiement à distance",
            "message": "Paiement sans carte physique inhabituel",
        },
    },
    "safe": {
        "score": 0.0,
        "message": "Transaction conforme au profil du client",
    },
}

RULE_TREE = [
    {"id": "amount_invalid", "condition": "Montant absent, nul ou négatif", "config_key": "amount_invalid"},
    {"id": "missing_fields", "condition": "Champs obligatoires incomplets", "config_key": "missing_fields"},
    {"id": "duplicate", "condition": "Identifiant déjà observé dans le lot", "config_key": "duplicate"},
    {"id": "geo_anomaly", "condition": "Pays différent en < {geo_window_hours}h", "config_key": "geo_anomaly"},
    {"id": "frequency", "condition": "≥ {freq_threshold} opérations en {freq_window_hours}h", "config_key": "frequency"},
    {"id": "amount_spike", "condition": "Montant ≥ {amount_spike_factor}× médiane client", "config_key": "amount_spike"},
    {"id": "card_not_present", "condition": "Sans carte + montant ou profil atypique", "config_key": "card_not_present"},
]

FEATURE_NAMES = [
    "amount", "amount_log", "hour", "card_present_flag",
    "country_code", "currency_code", "history_count",
    "amount_vs_median", "freq_1h", "geo_changes_24h",
]


def get_default_config():
    """Retourne une copie de la configuration par défaut."""
    return deepcopy(DEFAULT_CONFIG)


def format_condition(template, thresholds):
    """Formate une condition d'arbre avec les seuils courants."""
    return template.format(**thresholds)


# ---------------------------------------------------------------------------
# Chargement CSV (fourni — ne pas modifier le comportement)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Fonction principale — contrat hackathon
# ---------------------------------------------------------------------------

def analyze_fraud(transactions, config=None, ml_bundle=None):
    """Analyse complète avec métadonnées (source, ml_score) pour l'interface."""
    active_config = config or get_default_config()
    return _analyze_transactions(transactions, active_config, ml_bundle)


def detect_fraud(transactions, config=None, ml_bundle=None):
    """Analyse une liste de transactions et renvoie un verdict pour chacune.

    Retour : list[dict] avec transaction_id, fraud_score (0-1),
    is_suspicious (bool), reason (str) — un résultat par transaction, même ordre.

    Paramètres optionnels (interface uniquement) :
      - config : règles et seuils personnalisés
      - ml_bundle : modèle entraîné via train_fraud_model()

    Sans paramètres, la CI utilise la configuration par défaut (règles seules).
    """
    results = analyze_fraud(transactions, config, ml_bundle)
    return [
        {
            "transaction_id": item["transaction_id"],
            "fraud_score": item["fraud_score"],
            "is_suspicious": item["is_suspicious"],
            "reason": item["reason"],
        }
        for item in results
    ]


# ---------------------------------------------------------------------------
# Moteur de règles
# ---------------------------------------------------------------------------

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


def _missing_fields(transaction, required_fields):
    return [field for field in required_fields if transaction.get(field) is None]


def _user_history(transactions, user_id, current_index, current_tx):
    current_ts = _parse_timestamp(current_tx.get("timestamp"))
    history = []
    for idx, tx in enumerate(transactions):
        if idx == current_index or tx.get("user_id") != user_id:
            continue
        if current_ts is not None:
            tx_ts = _parse_timestamp(tx.get("timestamp"))
            if tx_ts is not None:
                if tx_ts >= current_ts:
                    continue
            elif idx >= current_index:
                continue
        elif idx >= current_index:
            continue
        history.append(tx)
    return history


def _user_batch(transactions, user_id):
    return [tx for tx in transactions if tx.get("user_id") == user_id]


def _prior_amounts(history):
    return [
        tx.get("amount")
        for tx in history
        if isinstance(tx.get("amount"), (int, float)) and tx.get("amount") > 0
    ]


def _build_result(transaction_id, fraud_score, is_suspicious, reason, rule_id=None):
    result = {
        "transaction_id": transaction_id,
        "fraud_score": round(max(0.0, min(1.0, fraud_score)), 2),
        "is_suspicious": is_suspicious,
        "reason": reason,
    }
    if rule_id:
        result["rule_id"] = rule_id
    return result


def _evaluate_rules(transactions, config):
    """Applique l'arbre de règles configurable."""
    results = []
    seen_ids = set()
    thresholds = config["thresholds"]
    required_fields = config["required_fields"]
    safe = config["safe"]

    for index, transaction in enumerate(transactions):
        transaction_id = transaction.get("transaction_id") or f"UNKNOWN-{index}"
        amount = transaction.get("amount")
        missing = _missing_fields(transaction, required_fields)
        rules = config["rules"]

        if rules["amount_invalid"]["enabled"] and (amount is None or amount <= 0):
            results.append(_build_result(
                transaction_id, rules["amount_invalid"]["score"], True,
                rules["amount_invalid"]["message"], "amount_invalid",
            ))
            if transaction_id and not transaction_id.startswith("UNKNOWN-"):
                seen_ids.add(transaction_id)
            continue

        if rules["missing_fields"]["enabled"] and missing:
            message = rules["missing_fields"]["message"].format(fields=", ".join(missing))
            results.append(_build_result(
                transaction_id, rules["missing_fields"]["score"], True,
                message, "missing_fields",
            ))
            if transaction_id and not transaction_id.startswith("UNKNOWN-"):
                seen_ids.add(transaction_id)
            continue

        if rules["duplicate"]["enabled"] and transaction_id in seen_ids:
            results.append(_build_result(
                transaction_id, rules["duplicate"]["score"], True,
                rules["duplicate"]["message"], "duplicate",
            ))
            continue

        user_id = transaction.get("user_id")
        history = _user_history(transactions, user_id, index, transaction)
        batch = _user_batch(transactions, user_id)

        if rules["geo_anomaly"]["enabled"] and _has_rapid_country_change(
            transaction, batch, thresholds["geo_window_hours"]
        ):
            results.append(_build_result(
                transaction_id, rules["geo_anomaly"]["score"], True,
                rules["geo_anomaly"]["message"], "geo_anomaly",
            ))
            seen_ids.add(transaction_id)
            continue

        if rules["frequency"]["enabled"] and _has_abnormal_frequency(
            transaction, batch,
            thresholds["freq_window_hours"], thresholds["freq_threshold"],
        ):
            results.append(_build_result(
                transaction_id, rules["frequency"]["score"], True,
                rules["frequency"]["message"], "frequency",
            ))
            seen_ids.add(transaction_id)
            continue

        if rules["amount_spike"]["enabled"] and _is_amount_spike(
            amount, history,
            thresholds["amount_history_min"], thresholds["amount_spike_factor"],
        ):
            results.append(_build_result(
                transaction_id, rules["amount_spike"]["score"], True,
                rules["amount_spike"]["message"], "amount_spike",
            ))
            seen_ids.add(transaction_id)
            continue

        if rules["card_not_present"]["enabled"] and _is_card_not_present_risk(
            transaction, history,
            thresholds["amount_history_min"],
            thresholds["card_not_present_min"],
            thresholds["card_spike_factor"],
        ):
            results.append(_build_result(
                transaction_id, rules["card_not_present"]["score"], True,
                rules["card_not_present"]["message"], "card_not_present",
            ))
            seen_ids.add(transaction_id)
            continue

        results.append(_build_result(
            transaction_id, safe["score"], False, safe["message"], "safe",
        ))
        seen_ids.add(transaction_id)

    return results


def _has_rapid_country_change(transaction, batch, geo_window_hours):
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
        if hours is not None and hours <= geo_window_hours:
            return True
    return False


def _has_abnormal_frequency(transaction, batch, freq_window_hours, freq_threshold):
    ts = _parse_timestamp(transaction.get("timestamp"))
    if ts is None:
        return False
    count = 0
    for other in batch:
        other_ts = _parse_timestamp(other.get("timestamp"))
        if other_ts is None:
            continue
        if abs((ts - other_ts).total_seconds()) / 3600 <= freq_window_hours:
            count += 1
    return count >= freq_threshold


def _is_amount_spike(amount, history, amount_history_min, amount_spike_factor):
    if amount is None or amount <= 0:
        return False
    prior_amounts = _prior_amounts(history)
    if len(prior_amounts) < amount_history_min:
        return False
    baseline = statistics.median(prior_amounts)
    if baseline <= 0:
        return False
    return amount >= baseline * amount_spike_factor


def _is_card_not_present_risk(transaction, history, amount_history_min,
                               card_not_present_min, card_spike_factor):
    if transaction.get("card_present") is not False:
        return False
    amount = transaction.get("amount")
    if not isinstance(amount, (int, float)) or amount <= 0:
        return False
    if amount >= card_not_present_min:
        return True
    prior_amounts = _prior_amounts(history)
    prior_card_flags = [
        tx.get("card_present") for tx in history if tx.get("card_present") is not None
    ]
    if len(prior_amounts) < amount_history_min or len(prior_card_flags) < amount_history_min:
        return False
    if all(prior_card_flags):
        baseline = statistics.median(prior_amounts)
        if baseline > 0 and amount >= baseline * card_spike_factor:
            return True
    return False


# ---------------------------------------------------------------------------
# Couche ML optionnelle
# ---------------------------------------------------------------------------

def _hash_code(value, modulo=97):
    if not value:
        return 0.0
    return float(sum(ord(ch) for ch in str(value)) % modulo) / modulo


def extract_fraud_features(transactions):
    """Extrait les features numériques pour le modèle ML."""
    rows = []
    for index, tx in enumerate(transactions):
        amount = tx.get("amount")
        amount_value = float(amount) if isinstance(amount, (int, float)) else 0.0
        ts = _parse_timestamp(tx.get("timestamp"))
        user_id = tx.get("user_id")
        history = _user_history(transactions, user_id, index, tx)
        batch = _user_batch(transactions, user_id)

        prior_amounts = [
            float(item.get("amount"))
            for item in history
            if isinstance(item.get("amount"), (int, float)) and item.get("amount") > 0
        ]
        median_amount = statistics.median(prior_amounts) if prior_amounts else amount_value or 1.0
        amount_ratio = amount_value / median_amount if median_amount else 1.0

        freq_1h = 0
        geo_changes = 0
        if ts is not None:
            for other in batch:
                other_ts = _parse_timestamp(other.get("timestamp"))
                if other_ts is None:
                    continue
                hours = abs((ts - other_ts).total_seconds()) / 3600
                if hours <= 1:
                    freq_1h += 1
                if hours <= 24 and tx.get("country") and other.get("country"):
                    if tx.get("country") != other.get("country"):
                        geo_changes += 1

        rows.append([
            amount_value, np.log1p(max(amount_value, 0.0)),
            float(ts.hour if ts else 12) / 24.0,
            1.0 if tx.get("card_present") else 0.0,
            _hash_code(tx.get("country")), _hash_code(tx.get("currency")),
            float(len(history)), amount_ratio, float(freq_1h), float(geo_changes),
        ])
    return np.array(rows, dtype=float)


def build_training_labels(rule_results):
    """Crée des labels 0/1 à partir des verdicts des règles."""
    return np.array(
        [1 if r.get("is_suspicious") else 0 for r in rule_results], dtype=int,
    )


def train_fraud_model(transactions, labels, ml_config):
    """Entraîne un modèle ML (Isolation Forest ou arbre de décision)."""
    features = extract_fraud_features(transactions)
    model_type = ml_config.get("model_type", "isolation_forest")

    if model_type == "decision_tree":
        from sklearn.tree import DecisionTreeClassifier
        model = DecisionTreeClassifier(
            max_depth=int(ml_config.get("max_depth", 6)),
            random_state=int(ml_config.get("random_state", 42)),
        )
        model.fit(features, labels)
        predictions = model.predict(features)
        metrics = {
            "mode": "supervised",
            "accuracy": round(float((predictions == labels).mean()), 3),
            "samples": len(labels),
        }
        return {"model": model, "model_type": model_type, "feature_names": FEATURE_NAMES, "metrics": metrics}

    from sklearn.ensemble import IsolationForest
    model = IsolationForest(
        n_estimators=int(ml_config.get("n_estimators", 120)),
        contamination=float(ml_config.get("contamination", 0.12)),
        random_state=int(ml_config.get("random_state", 42)),
    )
    model.fit(features)
    return {
        "model": model, "model_type": "isolation_forest",
        "feature_names": FEATURE_NAMES,
        "metrics": {"mode": "anomaly_detection", "samples": len(transactions)},
    }


def predict_fraud_scores(ml_bundle, transactions):
    """Retourne un score de risque 0-1 par transaction via le modèle ML."""
    if ml_bundle is None:
        return [0.0 for _ in transactions]

    model = ml_bundle["model"]
    features = extract_fraud_features(transactions)
    model_type = ml_bundle.get("model_type", "isolation_forest")

    if model_type == "decision_tree":
        proba = model.predict_proba(features)
        col = 1 if proba.shape[1] > 1 else 0
        return [float(proba[i, col]) for i in range(len(transactions))]

    raw = model.decision_function(features)
    min_val, max_val = float(np.min(raw)), float(np.max(raw))
    span = max(max_val - min_val, 1e-6)
    normalized = 1.0 - ((raw - min_val) / span)
    return [round(float(max(0.0, min(1.0, s))), 2) for s in normalized]


# ---------------------------------------------------------------------------
# Fusion hybride règles + ML
# ---------------------------------------------------------------------------

def _analyze_transactions(transactions, config, ml_bundle=None):
    """Analyse complète avec métadonnées (utilisée par l'interface)."""
    fusion_mode = config.get("fusion_mode", "rules_only")
    ml_enabled = bool(config.get("ml_enabled")) and ml_bundle is not None

    if fusion_mode == "ml_only" and ml_enabled:
        return _analyze_ml_only(transactions, ml_bundle, config)

    rule_results = _evaluate_rules(transactions, config)
    if not ml_enabled or fusion_mode == "rules_only":
        return [_public_result(r) for r in rule_results]

    ml_scores = predict_fraud_scores(ml_bundle, transactions)
    return _fuse_results(rule_results, ml_scores, config)


def _public_result(result):
    return {
        "transaction_id": result["transaction_id"],
        "fraud_score": result["fraud_score"],
        "is_suspicious": result["is_suspicious"],
        "reason": result["reason"],
    }


def _analyze_ml_only(transactions, ml_bundle, config):
    ml_scores = predict_fraud_scores(ml_bundle, transactions)
    threshold = float(config.get("ml_threshold", 0.55))
    results = []
    for index, tx in enumerate(transactions):
        score = ml_scores[index]
        suspicious = score >= threshold
        results.append({
            "transaction_id": tx.get("transaction_id") or f"UNKNOWN-{index}",
            "fraud_score": round(score, 2),
            "is_suspicious": suspicious,
            "reason": (
                f"Anomalie détectée par le modèle ({ml_bundle.get('model_type', 'ml')})"
                if suspicious else config["safe"]["message"]
            ),
            "source": "ml",
        })
    return results


def _fuse_results(rule_results, ml_scores, config):
    fusion_mode = config.get("fusion_mode", "weighted")
    threshold = float(config.get("ml_threshold", 0.55))
    rules_weight = float(config.get("rules_weight", 0.65))
    ml_weight = float(config.get("ml_weight", 0.35))
    fused = []

    for index, rule_result in enumerate(rule_results):
        ml_score = ml_scores[index]
        rule_score = float(rule_result["fraud_score"])
        rule_reason = rule_result["reason"]

        if fusion_mode == "rules_first" and rule_result["is_suspicious"]:
            final_score, suspicious, reason, source = rule_score, True, rule_reason, "rules"
        elif fusion_mode == "max_score":
            final_score = max(rule_score, ml_score)
            suspicious = final_score >= threshold or rule_result["is_suspicious"]
            reason = _compose_reason(rule_reason, ml_score, suspicious, rule_result["is_suspicious"])
            source = "hybrid_max"
        else:
            final_score = round((rules_weight * rule_score) + (ml_weight * ml_score), 2)
            suspicious = final_score >= threshold or rule_result["is_suspicious"]
            reason = _compose_reason(rule_reason, ml_score, suspicious, rule_result["is_suspicious"])
            source = "hybrid_weighted"

        fused.append({
            "transaction_id": rule_result["transaction_id"],
            "fraud_score": round(max(0.0, min(1.0, final_score)), 2),
            "is_suspicious": suspicious,
            "reason": reason,
            "ml_score": round(ml_score, 2),
            "source": source,
        })
    return fused


def _compose_reason(rule_reason, ml_score, suspicious, rule_flagged):
    if not suspicious:
        return rule_reason
    if rule_flagged and ml_score >= 0.55:
        return f"{rule_reason} · corroboration modèle ({ml_score:.2f})"
    if rule_flagged:
        return rule_reason
    return f"Signal modèle ({ml_score:.2f}) · surveillance renforcée"
