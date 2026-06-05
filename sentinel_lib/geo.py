"""Géolocalisation des transactions — coordonnées pays et couches carte.

Couche d'affichage uniquement : n'altère jamais detect_fraud().
"""

from __future__ import annotations

from datetime import datetime, timezone

# Coordonnées approximatives (centroïde) par code ISO pays.
COUNTRY_COORDS = {
    "FR": (46.2276, 2.2137, "France"),
    "JP": (36.2048, 138.2529, "Japon"),
    "US": (37.0902, -95.7129, "États-Unis"),
    "GB": (55.3781, -3.4360, "Royaume-Uni"),
    "DE": (51.1657, 10.4515, "Allemagne"),
    "ES": (40.4637, -3.7492, "Espagne"),
    "IT": (41.8719, 12.5674, "Italie"),
    "CN": (35.8617, 104.1954, "Chine"),
    "RU": (61.5240, 105.3188, "Russie"),
    "BR": (-14.2350, -51.9253, "Brésil"),
    "IN": (20.5937, 78.9629, "Inde"),
    "CA": (56.1304, -106.3468, "Canada"),
    "AU": (-25.2744, 133.7751, "Australie"),
    "ZA": (-30.5595, 22.9375, "Afrique du Sud"),
    "NG": (9.0820, 8.6753, "Nigéria"),
    "MA": (31.7917, -7.0926, "Maroc"),
    "SN": (14.4974, -14.4524, "Sénégal"),
    "CI": (7.5400, -5.5471, "Côte d'Ivoire"),
    "TG": (8.6195, 0.8248, "Togo"),
    "AE": (23.4241, 53.8478, "Émirats"),
    "CH": (46.8182, 8.2275, "Suisse"),
    "BE": (50.5039, 4.4699, "Belgique"),
    "NL": (52.1326, 5.2913, "Pays-Bas"),
    "PT": (39.3999, -8.2245, "Portugal"),
    "MX": (23.6345, -102.5528, "Mexique"),
    "SG": (1.3521, 103.8198, "Singapour"),
}


def country_coord(code):
    """Retourne (lat, lon, nom) ou None si le pays est inconnu."""
    if not code:
        return None
    return COUNTRY_COORDS.get(code.upper())


def _parse_ts(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (TypeError, ValueError):
        return None


def build_points(transactions, results):
    """Construit les points carte (un par transaction géolocalisable)."""
    points = []
    for tx, result in zip(transactions, results):
        coord = country_coord(tx.get("country"))
        if not coord:
            continue
        lat, lon, name = coord
        suspicious = bool(result.get("is_suspicious"))
        score = float(result.get("fraud_score") or 0)
        points.append({
            "lat": lat,
            "lon": lon,
            "pays": name,
            "client": tx.get("user_id") or "—",
            "ref": result.get("transaction_id") or "—",
            "montant": tx.get("amount"),
            "devise": tx.get("currency") or "",
            "score": score,
            "suspect": suspicious,
            "radius": 90000 + score * 320000,
            "color": [220, 38, 38, 200] if suspicious else [34, 197, 94, 170],
        })
    return points


def build_alert_arcs(transactions, results):
    """Trace des arcs entre pays pour les sauts géographiques suspects.

    Relie deux transactions d'un même client situées dans des pays
    différents — la signature d'un déplacement impossible.
    """
    by_user = {}
    for tx, result in zip(transactions, results):
        uid = tx.get("user_id")
        coord = country_coord(tx.get("country"))
        if not uid or not coord:
            continue
        by_user.setdefault(uid, []).append((tx, result, coord))

    arcs = []
    for uid, items in by_user.items():
        items.sort(key=lambda it: _parse_ts(it[0].get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc))
        for i in range(len(items) - 1):
            (_, _, (lat1, lon1, name1)) = items[i]
            (tx2, res2, (lat2, lon2, name2)) = items[i + 1]
            if name1 == name2:
                continue
            flagged = bool(res2.get("is_suspicious")) or "pays" in (res2.get("reason", "").lower())
            arcs.append({
                "from_lat": lat1,
                "from_lon": lon1,
                "to_lat": lat2,
                "to_lon": lon2,
                "client": uid,
                "trajet": f"{name1} → {name2}",
                "source_color": [37, 99, 235, 180],
                "target_color": [220, 38, 38, 220] if flagged else [34, 197, 94, 180],
            })
    return arcs


def build_country_summary(transactions, results):
    """Agrège les alertes par pays pour un classement."""
    summary = {}
    for tx, result in zip(transactions, results):
        coord = country_coord(tx.get("country"))
        name = coord[2] if coord else (tx.get("country") or "Inconnu")
        entry = summary.setdefault(name, {"pays": name, "total": 0, "alertes": 0})
        entry["total"] += 1
        if result.get("is_suspicious"):
            entry["alertes"] += 1
    return sorted(summary.values(), key=lambda e: e["alertes"], reverse=True)
