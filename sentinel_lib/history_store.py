"""Historique des analyses — persistance locale optionnelle."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

HISTORY_FILE = Path(__file__).parent.parent / "data" / "analysis_history.json"
MAX_RUNS = 50


def _load_raw() -> list:
    if not HISTORY_FILE.exists():
        return []
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save_raw(runs: list) -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(
        json.dumps(runs, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def save_run(transactions: list, results: list, meta: dict | None = None) -> dict:
    """Enregistre une analyse. N'interfère pas avec detect_fraud."""
    runs = _load_raw()
    alerts = sum(1 for r in results if r.get("is_suspicious"))

    entry = {
        "id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "at": datetime.now(timezone.utc).isoformat(),
        "transactions": len(transactions),
        "alerts": alerts,
        "fusion_mode": (meta or {}).get("fusion_mode", "rules_only"),
        "ml_enabled": (meta or {}).get("ml_enabled", False),
        "human_mode": (meta or {}).get("human_mode", False),
        "summary": {
            "transaction_ids": [r.get("transaction_id") for r in results[:20]],
            "alert_ids": [
                r.get("transaction_id")
                for r in results
                if r.get("is_suspicious")
            ][:20],
        },
    }

    runs.insert(0, entry)
    _save_raw(runs[:MAX_RUNS])
    return entry


def list_runs(limit: int = 10) -> list:
    """Retourne les dernières analyses enregistrées."""
    return _load_raw()[:limit]


def clear_history() -> None:
    """Vide l'historique local."""
    if HISTORY_FILE.exists():
        HISTORY_FILE.unlink()
