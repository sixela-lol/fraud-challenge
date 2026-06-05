"""
Sentinel — Console anti-fraude (carte mondiale, thème personnalisable).

Lancer : streamlit run app.py
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import pydeck as pdk
import streamlit as st

from fraud_detection import (
    RULE_TREE,
    build_training_labels,
    detect_fraud,
    format_condition,
    get_default_config,
    load_transactions,
    train_fraud_model,
)
from sentinel_lib.geo import (
    build_alert_arcs,
    build_country_summary,
    build_points,
    country_coord,
)
from sentinel_lib.history_store import clear_history, list_runs
from sentinel_lib.model_registry import get_model, list_trainable_models
from sentinel_lib.model_store import (
    delete_model,
    list_saved_models,
    load_model,
    save_model,
)
from sentinel_lib.orchestrator import run_session_analysis
from sentinel_lib.pipeline import apply_data_edits, run_chain, trace_steps
from sentinel_lib.verification_layer import (
    STATUS_LABELS,
    ensure_model,
    verify_transactions,
)
from ui.theme import APP_NAME, APP_TAGLINE, THEME_PRESETS, build_css, get_theme

SAMPLE_CSV = Path(__file__).parent / "data" / "sample_transactions.csv"

# Fonds de carte Carto (aucun token requis, contrairement à Mapbox).
CARTO_DARK = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
CARTO_LIGHT = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"

VIEWS = {
    "home": "Tableau de bord",
    "map": "Carte mondiale",
    "alerts": "Alertes",
    "verify": "Double contrôle",
    "list": "Liste complète",
    "pipeline": "Chaîne de traitement",
    "data": "Éditer les données",
    "history": "Historique",
    "rules": "Règles (expert)",
    "ml": "Modèles (expert)",
}

# Navigation horizontale : (id, icône, libellé court)
NAV_PRIMARY = [
    ("home", "📊", "Tableau"),
    ("map", "🌍", "Carte"),
    ("alerts", "🚨", "Alertes"),
    ("verify", "🔍", "Contrôle"),
    ("list", "📋", "Liste"),
    ("pipeline", "🔀", "Pipeline"),
    ("history", "🕘", "Historique"),
]
NAV_EXPERT = [
    ("data", "✏️", "Données"),
    ("rules", "📐", "Règles"),
    ("ml", "🧠", "Modèles"),
]


def _init_state() -> None:
    defaults = {
        "config": get_default_config(),
        "ml_bundle": None,
        "transactions": [],
        "results": [],
        "analyzed": False,
        "view": "home",
        "alert_index": 0,
        "list_filter": "Tout",
        "expert_mode": False,
        "human_mode": True,
        "persist_history": True,
        # Apparence
        "theme_name": "nuit",
        "accent": THEME_PRESETS["nuit"]["accent"],
        "radius": 12,
        "density": "confort",
        # Modèles & chaîne
        "chain": [],
        "chain_active": False,
        # Double contrôle (2e couche)
        "verify_rows": [],
        "verify_summary": {},
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _risk_label(score: float) -> str:
    if score >= 0.85:
        return "Risque élevé"
    if score >= 0.5:
        return "À surveiller"
    return "Risque faible"


def _display_reason(result: dict) -> str:
    if st.session_state.get("human_mode") and result.get("human_reason"):
        return result["human_reason"]
    return result.get("reason", "")


def _run_analysis(transactions: list[dict]) -> list[dict]:
    return run_session_analysis(
        transactions,
        st.session_state.config,
        st.session_state.ml_bundle,
        humanize=st.session_state.get("human_mode", True),
        persist_history=st.session_state.get("persist_history", True),
    )


def _to_local(iso_ts: str) -> str:
    """Convertit un horodatage ISO (souvent UTC) en heure locale lisible."""
    if not iso_ts:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return iso_ts[:19].replace("T", " ")


def _alert_pairs(transactions, results):
    return [(tx, r) for tx, r in zip(transactions, results) if r.get("is_suspicious")]


def _build_table_rows(transactions, results) -> pd.DataFrame:
    rows = []
    for tx, result in zip(transactions, results):
        rows.append({
            "Réf.": result.get("transaction_id"),
            "Client": tx.get("user_id"),
            "Montant": f"{tx.get('amount')} {tx.get('currency')}",
            "Pays": tx.get("country") or "—",
            "Verdict": "Suspecte" if result.get("is_suspicious") else "Normale",
            "Explication": _display_reason(result),
        })
    return pd.DataFrame(rows)


def _render_header() -> None:
    if st.session_state.analyzed:
        status = '<span class="pulse-dot"></span>Surveillance active'
    else:
        status = "En attente de données"
    st.markdown(
        f"""
        <div class="dash-header">
            <div>
                <h1>🛡️ {APP_NAME}</h1>
                <span>{APP_TAGLINE}</span>
            </div>
            <span>{status}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _nav_button_row(items) -> None:
    cols = st.columns(len(items))
    for col, (vid, icon, label) in zip(cols, items):
        with col:
            active = st.session_state.view == vid
            if st.button(
                f"{icon} {label}", key=f"nav_{vid}",
                type="primary" if active else "secondary",
                use_container_width=True,
            ):
                st.session_state.view = vid
                st.rerun()


def _top_nav() -> None:
    """Barre de navigation horizontale (remplace le menu vertical)."""
    st.markdown('<div class="nav-wrap">', unsafe_allow_html=True)
    _nav_button_row(NAV_PRIMARY)
    st.markdown("</div>", unsafe_allow_html=True)

    if st.session_state.get("expert_mode"):
        st.markdown('<p class="section-label">Mode expert</p>', unsafe_allow_html=True)
        st.markdown('<div class="nav-wrap">', unsafe_allow_html=True)
        _nav_button_row(NAV_EXPERT)
        st.markdown("</div>", unsafe_allow_html=True)


def _render_welcome() -> None:
    st.markdown(
        """
        <div class="welcome-panel">
            <h2>Centre de surveillance prêt</h2>
            <p>
                Chargez un fichier dans le menu de gauche puis lancez l'analyse.
                Vous obtiendrez une carte mondiale des transactions, des alertes
                expliquées en langage clair, et un thème personnalisable en direct.
            </p>
            <div>
                <span class="chip">Carte 3D</span>
                <span class="chip">Explications humaines</span>
                <span class="chip">Thème live</span>
                <span class="chip">Historique</span>
                <span class="chip">IA optionnelle</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _metric_tile(col, label, value, accent=False):
    with col:
        cls = "value accent" if accent else "value"
        st.markdown(
            f'<div class="metric-tile"><div class="label">{label}</div>'
            f'<div class="{cls}">{value}</div></div>',
            unsafe_allow_html=True,
        )


def _build_report(transactions, results) -> str:
    """Génère un rapport texte (Markdown) téléchargeable."""
    alerts = _alert_pairs(transactions, results)
    rate = (len(alerts) / len(results) * 100) if results else 0
    summary = build_country_summary(transactions, results)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        f"# {APP_NAME} — Rapport d'analyse anti-fraude",
        f"_Généré le {now}_",
        "",
        "## Synthèse",
        f"- Transactions analysées : **{len(results)}**",
        f"- Alertes détectées : **{len(alerts)}**",
        f"- Taux de suspicion : **{rate:.1f}%**",
        f"- Pays couverts : **{len({tx.get('country') for tx in transactions if tx.get('country')})}**",
        f"- Mode de fusion : **{st.session_state.config.get('fusion_mode', 'rules_only')}**",
        f"- IA activée : **{'oui' if st.session_state.config.get('ml_enabled') else 'non'}**",
        "",
        "## Détail des alertes",
    ]
    if alerts:
        for tx, r in alerts:
            lines.append(
                f"- **{r.get('transaction_id')}** · client {tx.get('user_id')} · "
                f"{tx.get('amount')} {tx.get('currency')} · {tx.get('country') or '—'} "
                f"· score {float(r.get('fraud_score') or 0):.2f} → {_display_reason(r)}"
            )
    else:
        lines.append("- Aucune alerte sur ce lot.")

    lines += ["", "## Répartition par pays"]
    for s in summary:
        lines.append(f"- {s['pays']} : {s['alertes']} alerte(s) / {s['total']} transaction(s)")
    return "\n".join(lines)


def _render_home(transactions, results) -> None:
    alerts = _alert_pairs(transactions, results)
    ok_count = len(results) - len(alerts)
    countries = len({tx.get("country") for tx in transactions if tx.get("country")})
    rate = (len(alerts) / len(results) * 100) if results else 0

    c1, c2, c3, c4, c5 = st.columns(5)
    _metric_tile(c1, "Analysées", len(results))
    _metric_tile(c2, "Alertes", len(alerts), accent=True)
    _metric_tile(c3, "Normales", ok_count)
    _metric_tile(c4, "Pays", countries)
    _metric_tile(c5, "Taux suspicion", f"{rate:.0f}%")

    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

    # --- Rangée de graphiques ---
    g1, g2, g3 = st.columns(3)
    with g1:
        st.markdown('<p class="panel-title">Répartition</p>', unsafe_allow_html=True)
        df = pd.DataFrame({"Type": ["Alertes", "Normales"], "Nb": [len(alerts), ok_count]})
        st.bar_chart(df.set_index("Type"), color=st.session_state.accent, height=190)
    with g2:
        st.markdown('<p class="panel-title">Niveaux de risque</p>', unsafe_allow_html=True)
        buckets = {"Faible (0-0.4)": 0, "Moyen (0.4-0.7)": 0, "Élevé (0.7-1)": 0}
        for r in results:
            s = float(r.get("fraud_score") or 0)
            key = "Faible (0-0.4)" if s < 0.4 else "Moyen (0.4-0.7)" if s < 0.7 else "Élevé (0.7-1)"
            buckets[key] += 1
        st.bar_chart(
            pd.DataFrame({"Niveau": list(buckets), "Nb": list(buckets.values())}).set_index("Niveau"),
            color=st.session_state.accent, height=190,
        )
    with g3:
        st.markdown('<p class="panel-title">Alertes par pays</p>', unsafe_allow_html=True)
        summary = build_country_summary(transactions, results)
        top = [s for s in summary if s["alertes"] > 0][:6] or summary[:6]
        if top:
            st.bar_chart(
                pd.DataFrame({"Pays": [s["pays"] for s in top],
                              "Alertes": [s["alertes"] for s in top]}).set_index("Pays"),
                color="#dc2626", height=190,
            )
        else:
            st.caption("Aucune alerte géolocalisée.")

    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

    left, right = st.columns([1.4, 1])
    with left:
        st.markdown('<p class="panel-title">Aperçu géographique</p>', unsafe_allow_html=True)
        deck = _build_deck(transactions, results, compact=True)
        if deck:
            st.pydeck_chart(deck, use_container_width=True)
        else:
            st.info("Aucune transaction géolocalisable.")

    with right:
        st.markdown('<p class="panel-title">Classement pays</p>', unsafe_allow_html=True)
        st.dataframe(
            pd.DataFrame(build_country_summary(transactions, results)).rename(
                columns={"pays": "Pays", "total": "Total", "alertes": "Alertes"}
            ),
            use_container_width=True, hide_index=True, height=230,
        )

    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

    # --- Zone rapport + zone orchestration ---
    rep, orch = st.columns([1.3, 1])
    with rep:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown('<p class="panel-title">📄 Rapport d\'analyse</p>', unsafe_allow_html=True)
        report = _build_report(transactions, results)
        verdict = "🔴 Risque élevé" if rate >= 30 else "🟠 Vigilance" if rate >= 10 else "🟢 Situation saine"
        st.markdown(f"**Verdict global : {verdict}** — {len(alerts)} alerte(s) sur {len(results)} transactions.")
        st.download_button(
            "Télécharger le rapport (Markdown)", report,
            file_name="rapport_sentinel.md", mime="text/markdown",
            use_container_width=True,
        )
        with st.expander("Aperçu du rapport"):
            st.markdown(report)
        st.markdown("</div>", unsafe_allow_html=True)

    with orch:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown('<p class="panel-title">🔀 Orchestration</p>', unsafe_allow_html=True)
        config = st.session_state.config
        active_rules = sum(1 for v in config.get("rules", {}).values() if v.get("enabled"))
        saved = list_saved_models()
        st.markdown(
            f"""
            <ul style="margin:0;padding-left:18px;line-height:1.8">
                <li>Règles actives : <strong>{active_rules}</strong></li>
                <li>Mode de fusion : <strong>{config.get('fusion_mode', 'rules_only')}</strong></li>
                <li>IA : <strong>{'activée' if config.get('ml_enabled') else 'désactivée'}</strong></li>
                <li>Modèles sauvegardés : <strong>{len(saved)}</strong></li>
            </ul>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Ouvrir la chaîne de traitement", use_container_width=True):
            st.session_state.view = "pipeline"
            st.rerun()
        if st.button("Lancer un double contrôle", use_container_width=True):
            st.session_state.view = "verify"
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)


def _build_deck(transactions, results, compact=False, show_arcs=True):
    points = build_points(transactions, results)
    arcs = build_alert_arcs(transactions, results) if show_arcs else []
    if not points:
        return None

    theme = get_theme(st.session_state.theme_name)
    map_style = CARTO_LIGHT if theme["map_style"] == "light" else CARTO_DARK

    scatter = pdk.Layer(
        "ScatterplotLayer",
        data=points,
        get_position="[lon, lat]",
        get_radius="radius",
        get_fill_color="color",
        pickable=True,
        opacity=0.85,
        stroked=True,
        get_line_color=[255, 255, 255, 120],
        line_width_min_pixels=1,
    )
    layers = [scatter]

    if arcs:
        arc_layer = pdk.Layer(
            "ArcLayer",
            data=arcs,
            get_source_position="[from_lon, from_lat]",
            get_target_position="[to_lon, to_lat]",
            get_source_color="source_color",
            get_target_color="target_color",
            get_width=3,
            pickable=True,
            auto_highlight=True,
        )
        layers.append(arc_layer)

    lats = [p["lat"] for p in points]
    lons = [p["lon"] for p in points]
    view = pdk.ViewState(
        latitude=sum(lats) / len(lats),
        longitude=sum(lons) / len(lons),
        zoom=1.1 if len(set(lons)) > 2 else 3,
        pitch=45 if not compact else 30,
        bearing=0,
    )

    return pdk.Deck(
        layers=layers,
        initial_view_state=view,
        map_provider="carto",
        map_style=map_style,
        tooltip={
            "html": "<b>{pays}</b><br/>Client {client} · {ref}<br/>"
                    "{montant} {devise} · score {score}",
            "style": {"backgroundColor": "#0f172a", "color": "white"},
        },
    )


def _render_map(transactions, results) -> None:
    # --- Barre de filtres ---
    ctrl = st.columns([1.4, 2, 1])
    with ctrl[0]:
        mode = st.radio(
            "Afficher", ["Toutes", "Suspectes", "Normales"],
            horizontal=True, label_visibility="collapsed",
        )
    countries = sorted({tx.get("country") for tx in transactions if tx.get("country")})
    with ctrl[1]:
        chosen_countries = st.multiselect(
            "Pays", countries, default=countries, placeholder="Tous les pays",
            label_visibility="collapsed",
        )
    with ctrl[2]:
        show_arcs = st.toggle("Trajets", value=True)

    # --- Filtrage des paires (transaction, résultat) ---
    pairs = []
    for tx, res in zip(transactions, results):
        if mode == "Suspectes" and not res.get("is_suspicious"):
            continue
        if mode == "Normales" and res.get("is_suspicious"):
            continue
        if chosen_countries and tx.get("country") not in chosen_countries:
            continue
        pairs.append((tx, res))

    f_tx = [p[0] for p in pairs]
    f_res = [p[1] for p in pairs]

    deck = _build_deck(f_tx, f_res, compact=False, show_arcs=show_arcs)
    arcs = build_alert_arcs(f_tx, f_res) if show_arcs else []

    # --- Légende ---
    n_susp = sum(1 for _, r in pairs if r.get("is_suspicious"))
    n_norm = len(pairs) - n_susp
    st.markdown(
        f"""
        <div style="display:flex;gap:18px;align-items:center;margin:6px 0 10px;font-size:.85rem">
            <span><span style="color:#dc2626">●</span> Suspectes ({n_susp})</span>
            <span><span style="color:#22c55e">●</span> Normales ({n_norm})</span>
            <span style="opacity:.7">La taille du point = niveau de risque</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    top = st.columns([3, 1])
    with top[1]:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown('<p class="panel-title">Trajets suspects</p>', unsafe_allow_html=True)
        flagged = [a for a in arcs if a["target_color"][0] > 200]
        if flagged:
            for a in flagged:
                st.markdown(
                    f'<span class="chip">{a["client"]}</span> {a["trajet"]}',
                    unsafe_allow_html=True,
                )
        else:
            st.caption("Aucun déplacement géographique anormal.")
        st.markdown("</div>", unsafe_allow_html=True)

    with top[0]:
        if deck:
            st.pydeck_chart(deck, use_container_width=True)
        else:
            st.info("Aucune transaction géolocalisable avec ces filtres.")


def _render_alerts(transactions, results) -> None:
    alerts = _alert_pairs(transactions, results)
    if not alerts:
        st.markdown('<div class="ok-panel">✅ Aucune alerte — tout est normal.</div>', unsafe_allow_html=True)
        return

    # Tri par score décroissant (les plus graves en premier)
    alerts = sorted(alerts, key=lambda p: float(p[1].get("fraud_score") or 0), reverse=True)

    st.markdown(
        f'<p class="panel-title">⚠️ {len(alerts)} alerte(s) détectée(s) — triées par gravité</p>',
        unsafe_allow_html=True,
    )

    # Toutes les alertes en cartes (2 colonnes)
    cols = st.columns(2)
    for i, (tx, result) in enumerate(alerts):
        score = float(result.get("fraud_score") or 0)
        with cols[i % 2]:
            st.markdown(
                f"""
                <div class="alert-panel">
                    <h3>⚠️ {result.get("transaction_id")} — {_risk_label(score)}</h3>
                    <p><strong>Client :</strong> {tx.get("user_id")}
                       · <strong>Score :</strong> {score:.2f}</p>
                    <p><strong>Montant :</strong> {tx.get("amount")} {tx.get("currency")}
                       · <strong>Commerçant :</strong> {tx.get("merchant")}</p>
                    <p><strong>Pays :</strong> {tx.get("country") or "inconnu"}</p>
                    <p><strong>Pourquoi ?</strong><br>{_display_reason(result)}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # Carte de l'ensemble des alertes
    st.markdown('<p class="panel-title">Localisation des alertes</p>', unsafe_allow_html=True)
    pts = [
        {"lat": c[0], "lon": c[1], "ref": r.get("transaction_id")}
        for tx, r in alerts
        if (c := country_coord(tx.get("country")))
    ]
    if pts:
        st.pydeck_chart(
            pdk.Deck(
                layers=[pdk.Layer(
                    "ScatterplotLayer", data=pts,
                    get_position="[lon, lat]", get_radius=180000,
                    get_fill_color=[220, 38, 38, 200], pickable=True,
                )],
                initial_view_state=pdk.ViewState(
                    latitude=sum(p["lat"] for p in pts) / len(pts),
                    longitude=sum(p["lon"] for p in pts) / len(pts),
                    zoom=1.2, pitch=30,
                ),
                map_provider="carto", map_style=CARTO_DARK,
                tooltip={"text": "{ref}"},
            ),
            use_container_width=True,
        )
    else:
        st.info("Localisation indisponible pour ces alertes.")


def _render_list(transactions, results) -> None:
    df = _build_table_rows(transactions, results)
    c1, c2 = st.columns([1, 2])
    with c1:
        filt = st.selectbox(
            "Filtre", ["Tout", "Alertes seulement", "Normales seulement"],
            label_visibility="collapsed",
        )
    with c2:
        query = st.text_input(
            "Recherche", placeholder="Rechercher (réf., client, pays, montant…)",
            label_visibility="collapsed",
        )
    if filt == "Alertes seulement":
        df = df[df["Verdict"] == "Suspecte"]
    elif filt == "Normales seulement":
        df = df[df["Verdict"] == "Normale"]
    if query:
        mask = df.apply(lambda row: query.lower() in " ".join(map(str, row.values)).lower(), axis=1)
        df = df[mask]
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.dataframe(df, use_container_width=True, hide_index=True, height=420)
    st.markdown("</div>", unsafe_allow_html=True)


def _render_history() -> None:
    runs = list_runs(15)
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    if not runs:
        st.info("Aucune analyse enregistrée pour l'instant.")
    else:
        st.dataframe(
            pd.DataFrame([
                {
                    "Date (heure locale)": _to_local(r.get("at", "")),
                    "Transactions": r.get("transactions"),
                    "Alertes": r.get("alerts"),
                    "Mode": r.get("fusion_mode"),
                    "IA": "Oui" if r.get("ml_enabled") else "Non",
                }
                for r in runs
            ]),
            use_container_width=True, hide_index=True, height=320,
        )
        if st.button("Vider l'historique"):
            clear_history()
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


def _render_verify(transactions, results) -> None:
    st.markdown('<p class="panel-title">Double contrôle — règles vs modèle</p>', unsafe_allow_html=True)
    st.caption(
        "La couche 2 (modèle de prédiction) re-vérifie chaque transaction et "
        "confronte son avis à celui des règles. Objectif : repérer les "
        "transactions jugées « normales » par les règles mais douteuses pour le modèle."
    )

    c0 = st.columns([1.4, 1.4, 1])
    with c0[0]:
        threshold = st.slider("Seuil de doute du modèle", 0.30, 0.90, 0.55, 0.05)
    with c0[1]:
        model_type = st.selectbox(
            "Modèle de la 2ᵉ couche", ["isolation_forest", "decision_tree"],
            format_func=lambda m: {"isolation_forest": "Détection d'anomalies",
                                   "decision_tree": "Arbre de décision"}[m],
        )
    with c0[2]:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        run = st.button("Lancer le double contrôle", type="primary", use_container_width=True)

    if not run and not st.session_state.get("verify_rows"):
        st.info("Choisissez un modèle puis lancez le double contrôle.")
        return

    if run:
        try:
            bundle = ensure_model(transactions, st.session_state.get("ml_bundle"), model_type)
            rows, summary = verify_transactions(transactions, results, bundle, threshold)
            st.session_state.verify_rows = rows
            st.session_state.verify_summary = summary
        except Exception as exc:
            st.error(f"Impossible d'entraîner/lancer la 2ᵉ couche : {exc}")
            return

    rows = st.session_state.get("verify_rows", [])
    summary = st.session_state.get("verify_summary", {})
    if not rows:
        return

    # KPI : 4 quadrants du croisement
    tiles = [
        ("alerte_ok", "Alerte confirmée", summary.get("alerte_ok", 0)),
        ("a_verifier", "À vérifier", summary.get("a_verifier", 0)),
        ("alerte_att", "Alerte atténuée", summary.get("alerte_att", 0)),
        ("confirme", "Sain confirmé", summary.get("confirme", 0)),
    ]
    cols = st.columns(4)
    for col, (key, label, value) in zip(cols, tiles):
        color = STATUS_LABELS[key][1]
        with col:
            st.markdown(
                f"""
                <div class="metric-tile" style="border-left:4px solid {color}">
                    <div class="label">{label}</div>
                    <div class="value" style="color:{color}">{value}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown(
        f"<p style='margin-top:10px'>Les deux couches sont d'accord à "
        f"<strong>{summary.get('accord_pct', 0)}%</strong>.</p>",
        unsafe_allow_html=True,
    )

    # Le coeur de la demande : transactions « normales » que le modèle conteste
    a_verifier = [r for r in rows if r["status"] == "a_verifier"]
    st.markdown('<p class="panel-title">⚠️ À vérifier (passées par les règles, douteuses pour le modèle)</p>', unsafe_allow_html=True)
    if a_verifier:
        st.dataframe(
            pd.DataFrame([{
                "Réf.": r["transaction_id"], "Client": r["user_id"],
                "Montant": r["amount"], "Devise": r["currency"], "Pays": r["country"],
                "Score modèle": r["model_score"],
            } for r in a_verifier]),
            use_container_width=True, hide_index=True,
        )
    else:
        st.success("Aucune transaction normale contestée par le modèle — bon accord.")

    with st.expander("Voir le détail complet du croisement"):
        st.dataframe(
            pd.DataFrame([{
                "Réf.": r["transaction_id"], "Client": r["user_id"],
                "Règles": "Alerte" if r["rule_flag"] else "Normale",
                "Score modèle": r["model_score"],
                "Modèle": "Suspecte" if r["model_flag"] else "Normale",
                "Verdict croisé": r["status_label"],
                "Accord": "Oui" if r["agree"] else "Non",
            } for r in rows]),
            use_container_width=True, hide_index=True, height=320,
        )


def _render_pipeline(transactions, results) -> None:
    steps = trace_steps(transactions, st.session_state.config, results)

    st.markdown('<p class="panel-title">Parcours de la donnée</p>', unsafe_allow_html=True)
    cols = st.columns(len(steps))
    for col, step in zip(cols, steps):
        with col:
            st.markdown(
                f"""
                <div class="metric-tile" style="height:auto;min-height:120px;">
                    <div style="font-size:1.4rem">{step['icon']}</div>
                    <div class="label">{step['step']}</div>
                    <div style="font-size:0.72rem;opacity:0.85;margin-top:4px">{step['detail']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    with st.expander("Détail de chaque étape", expanded=False):
        for step in steps:
            st.markdown(f"**{step['icon']} {step['step']}** — {step['desc']} · _{step['detail']}_")

    # Orchestration multi-modèles
    st.markdown('<p class="panel-title">Chaîne de modèles</p>', unsafe_allow_html=True)
    saved = list_saved_models()
    if not saved:
        st.info("Aucun modèle sauvegardé. Entraînez et nommez un modèle dans l'onglet **Modèles**.")
        return

    names = [m["name"] for m in saved]
    chosen = st.multiselect("Modèles à enchaîner", names, default=names[: min(2, len(names))])
    if chosen:
        stages = [{"kind": "rules"}]
        for m in saved:
            if m["name"] in chosen:
                bundle = load_model(m["slug"])
                if bundle:
                    stages.append({"kind": "model", "name": m["name"], "bundle": bundle, "weight": 0.5})

        final, contributions = run_chain(transactions, st.session_state.config, stages)
        flow = "  →  ".join(c["name"] for c in contributions)
        st.markdown(f'<span class="chip">{flow}</span>', unsafe_allow_html=True)

        alerts = sum(1 for r in final if r["is_suspicious"])
        st.caption(f"Résultat de la chaîne : {alerts} alerte(s) sur {len(final)} transactions.")
        rows = []
        for tx, r in zip(transactions, final):
            row = {"Réf.": r["transaction_id"], "Client": tx.get("user_id"),
                   "Score final": r["fraud_score"],
                   "Verdict": "Suspecte" if r["is_suspicious"] else "Normale"}
            row.update({f"Score {k}": v for k, v in r["model_scores"].items()})
            rows.append(row)
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=280)


def _render_data_editor(transactions) -> None:
    st.markdown('<p class="panel-title">Modifier les transactions</p>', unsafe_allow_html=True)
    st.caption("Éditez les valeurs puis relancez l'analyse pour voir l'impact.")

    df = pd.DataFrame(transactions)
    edited = st.data_editor(
        df, use_container_width=True, num_rows="dynamic", height=320, key="data_editor",
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Analyser les données modifiées", type="primary", use_container_width=True):
            new_tx = apply_data_edits(edited.to_dict("records"))
            st.session_state.transactions = new_tx
            st.session_state.results = _run_analysis(new_tx)
            st.session_state.view = "home"
            st.rerun()
    with c2:
        if st.button("Annuler les modifications", use_container_width=True):
            st.rerun()


def _render_rules() -> None:
    config = st.session_state.config
    thresholds = config["thresholds"]
    c1, c2 = st.columns(2)
    with c1:
        thresholds["geo_window_hours"] = st.number_input(
            "Délai max entre 2 pays (h)", 1, 168, int(thresholds["geo_window_hours"]))
        thresholds["amount_spike_factor"] = st.number_input(
            "× médiane = suspect", 2.0, 50.0, float(thresholds["amount_spike_factor"]), 0.5)
    with c2:
        thresholds["freq_threshold"] = st.number_input(
            "Max transactions / 1 h", 2, 20, int(thresholds["freq_threshold"]))
        thresholds["card_not_present_min"] = st.number_input(
            "Seuil sans carte (€)", 50, 10000, int(thresholds["card_not_present_min"]), 50)

    rule_id = st.selectbox(
        "Règle à modifier", [n["id"] for n in RULE_TREE],
        format_func=lambda i: config["rules"][i]["label"] if i in config["rules"] else i)
    node = next(n for n in RULE_TREE if n["id"] == rule_id)
    rule = config["rules"][node["config_key"]]
    st.caption(format_condition(node["condition"], thresholds))
    rule["enabled"] = st.toggle("Active", rule["enabled"])
    rule["message"] = st.text_input("Message d'alerte", rule["message"])
    config["safe"]["message"] = st.text_input("Message « normale »", config["safe"]["message"])


def _render_ml(transactions) -> None:
    config = st.session_state.config
    ml_config = config["ml"]
    config["ml_enabled"] = st.toggle("Activer l'IA", config.get("ml_enabled", False))
    config["fusion_mode"] = st.selectbox(
        "Mode", ["rules_only", "rules_first", "weighted"],
        index=["rules_only", "rules_first", "weighted"].index(
            config.get("fusion_mode", "rules_only")
            if config.get("fusion_mode") in ("rules_only", "rules_first", "weighted")
            else "rules_only"),
        format_func=lambda x: {
            "rules_only": "Règles seules", "rules_first": "Règles + IA", "weighted": "Mélange",
        }[x])
    tab_train, tab_store = st.tabs(["Entraîner", "Bibliothèque de modèles"])

    with tab_train:
        trainable = list_trainable_models()
        ids = [m["id"] for m in trainable]
        current = ml_config.get("model_type", "isolation_forest")
        ml_config["model_type"] = st.selectbox(
            "Type de modèle", ids, index=ids.index(current) if current in ids else 0,
            format_func=lambda mid: get_model(mid)["name"] if get_model(mid) else mid)
        selected = get_model(ml_config["model_type"])
        if selected:
            st.caption(selected["description"])
        ml_config["max_depth"] = st.slider("Complexité", 2, 12, int(ml_config.get("max_depth", 6)))

        model_name = st.text_input("Nom du modèle", value=f"{ml_config['model_type']}-v1")
        note = st.text_input("Note (optionnel)", value="")

        if transactions and st.button("Entraîner et sauvegarder", type="primary", use_container_width=True):
            labels = build_training_labels(detect_fraud(transactions))
            try:
                bundle = train_fraud_model(transactions, labels, ml_config)
                st.session_state.ml_bundle = bundle
                meta = save_model(model_name, bundle, note)
                st.success(f"Modèle « {meta['name']} » entraîné et sauvegardé.")
            except Exception as exc:
                st.error(str(exc))

    with tab_store:
        saved = list_saved_models()
        if not saved:
            st.info("Aucun modèle sauvegardé pour l'instant.")
            return
        for m in saved:
            cols = st.columns([3, 1, 1])
            with cols[0]:
                st.markdown(
                    f"**{m['name']}** · `{m['model_type']}`  \n"
                    f"<span style='opacity:.7;font-size:.8rem'>{m.get('note') or 'sans note'} · "
                    f"{m.get('saved_at','')[:19].replace('T',' ')}</span>",
                    unsafe_allow_html=True,
                )
            with cols[1]:
                if st.button("Charger", key=f"load_{m['slug']}", use_container_width=True):
                    bundle = load_model(m["slug"])
                    if bundle:
                        st.session_state.ml_bundle = bundle
                        st.session_state.config["ml_enabled"] = True
                        st.success(f"« {m['name']} » chargé et actif.")
            with cols[2]:
                if st.button("Suppr.", key=f"del_{m['slug']}", use_container_width=True):
                    delete_model(m["slug"])
                    st.rerun()


def _appearance_controls() -> None:
    """Personnalisation de l'interface en direct."""
    names = list(THEME_PRESETS.keys())
    st.session_state.theme_name = st.selectbox(
        "Thème", names,
        index=names.index(st.session_state.theme_name),
        format_func=lambda n: THEME_PRESETS[n]["label"],
    )
    # Réaligne l'accent sur le preset si l'utilisateur change de thème
    preset_accent = THEME_PRESETS[st.session_state.theme_name]["accent"]
    st.session_state.accent = st.color_picker(
        "Couleur d'accent", st.session_state.get("accent", preset_accent),
    )
    st.session_state.radius = st.slider("Arrondi", 0, 24, int(st.session_state.radius))
    st.session_state.density = st.radio(
        "Densité", ["confort", "compact"], horizontal=True,
        index=0 if st.session_state.density == "confort" else 1,
    )


def _sidebar() -> list[dict]:
    transactions: list[dict] = []
    with st.sidebar:
        st.markdown(f"## 🛡️ {APP_NAME}")

        step_file = bool(st.session_state.transactions)
        step_done = st.session_state.analyzed
        st.markdown(
            f'<p class="step-item {"step-done" if step_file else "step-active"}">'
            f'{"✓" if step_file else "1."} Choisir un fichier</p>', unsafe_allow_html=True)
        st.markdown(
            f'<p class="step-item {"step-done" if step_done else ("step-active" if step_file else "")}">'
            f'{"✓" if step_done else "2."} Analyser</p>', unsafe_allow_html=True)
        st.markdown(
            f'<p class="step-item {"step-active" if step_done else ""}">'
            f'3. Explorer les résultats</p>', unsafe_allow_html=True)

        st.divider()
        source = st.radio(
            "Fichier", ["Exemple", "Mon CSV"], horizontal=True,
            label_visibility="collapsed",
        )
        if source == "Exemple":
            transactions = load_transactions(str(SAMPLE_CSV))
            st.caption(f"{len(transactions)} transactions")
        else:
            uploaded = st.file_uploader("CSV", type=["csv"], label_visibility="collapsed")
            if uploaded:
                tmp = Path(".streamlit_upload.csv")
                tmp.write_bytes(uploaded.getvalue())
                transactions = load_transactions(str(tmp))
                tmp.unlink(missing_ok=True)
                st.caption(f"{len(transactions)} importées")

        if transactions:
            st.session_state.transactions = transactions

        if st.button("▶ Analyser", type="primary", use_container_width=True):
            if transactions:
                st.session_state.results = _run_analysis(transactions)
                st.session_state.analyzed = True
                st.session_state.view = "home"
                st.session_state.alert_index = 0
                st.rerun()
            else:
                st.warning("Chargez un fichier.")

        if st.session_state.analyzed:
            st.divider()
            export = _build_table_rows(st.session_state.transactions, st.session_state.results)
            st.download_button(
                "⬇ Export CSV", export.to_csv(index=False).encode("utf-8"),
                "rapport_sentinel.csv", "text/csv", use_container_width=True)

        st.divider()
        with st.expander("🎨 Apparence"):
            _appearance_controls()

        st.session_state.human_mode = st.toggle(
            "Explications humaines", st.session_state.get("human_mode", True))
        st.session_state.persist_history = st.toggle(
            "Sauver l'historique", st.session_state.get("persist_history", True))
        st.session_state.expert_mode = st.toggle(
            "Mode expert", st.session_state.get("expert_mode", False))
        if st.session_state.get("expert_mode") and st.button("Reset config", use_container_width=True):
            st.session_state.config = get_default_config()
            st.rerun()

    return st.session_state.transactions if st.session_state.transactions else transactions


def main() -> None:
    st.set_page_config(
        page_title=f"{APP_NAME} — Anti-fraude",
        page_icon="🛡️", layout="wide", initial_sidebar_state="expanded",
    )
    _init_state()
    theme = get_theme(st.session_state.theme_name)
    st.markdown(
        build_css(theme, st.session_state.accent, st.session_state.radius, st.session_state.density),
        unsafe_allow_html=True,
    )

    _sidebar()
    _render_header()

    if not st.session_state.analyzed:
        _render_welcome()
        return

    _top_nav()

    transactions = st.session_state.transactions
    results = st.session_state.results
    view = st.session_state.view

    if view == "home":
        _render_home(transactions, results)
    elif view == "map":
        _render_map(transactions, results)
    elif view == "alerts":
        _render_alerts(transactions, results)
    elif view == "verify":
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        _render_verify(transactions, results)
        st.markdown("</div>", unsafe_allow_html=True)
    elif view == "list":
        _render_list(transactions, results)
    elif view == "pipeline":
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        _render_pipeline(transactions, results)
        st.markdown("</div>", unsafe_allow_html=True)
    elif view == "data":
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        _render_data_editor(transactions)
        st.markdown("</div>", unsafe_allow_html=True)
    elif view == "history":
        _render_history()
    elif view == "rules":
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        _render_rules()
        st.markdown("</div>", unsafe_allow_html=True)
    elif view == "ml":
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        _render_ml(transactions)
        st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
