"""
Sentinel — Plateforme de détection de fraude transactionnelle.

Lancer : streamlit run app.py
"""

from pathlib import Path

import pandas as pd
import streamlit as st

from fraud_detection import detect_fraud, load_transactions

SAMPLE_CSV = Path(__file__).parent / "data" / "sample_transactions.csv"

BRAND = "Sentinel"
TAGLINE = "Surveillance transactionnelle en temps réel"

CUSTOM_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'DM Sans', sans-serif;
    }

    .block-container {
        padding-top: 1.5rem;
        max-width: 1400px;
    }

    .sentinel-header {
        background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 55%, #0f766e 100%);
        border-radius: 16px;
        padding: 28px 32px;
        margin-bottom: 24px;
        color: white;
    }

    .sentinel-header h1 {
        margin: 0;
        font-size: 2rem;
        font-weight: 700;
        letter-spacing: -0.02em;
    }

    .sentinel-header p {
        margin: 8px 0 0 0;
        opacity: 0.85;
        font-size: 1rem;
    }

    .kpi-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06);
        height: 100%;
    }

    .kpi-label {
        color: #64748b;
        font-size: 0.8rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin-bottom: 6px;
    }

    .kpi-value {
        color: #0f172a;
        font-size: 2rem;
        font-weight: 700;
        line-height: 1.1;
    }

    .kpi-sub {
        color: #94a3b8;
        font-size: 0.85rem;
        margin-top: 4px;
    }

    .alert-card {
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 18px 20px;
        margin-bottom: 12px;
        background: #fff;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
    }

    .badge-high { color: #dc2626; background: #fef2f2; padding: 4px 10px; border-radius: 999px; font-size: 0.75rem; font-weight: 600; }
    .badge-mid  { color: #d97706; background: #fffbeb; padding: 4px 10px; border-radius: 999px; font-size: 0.75rem; font-weight: 600; }
    .badge-low  { color: #16a34a; background: #f0fdf4; padding: 4px 10px; border-radius: 999px; font-size: 0.75rem; font-weight: 600; }

    .section-title {
        font-size: 1.1rem;
        font-weight: 600;
        color: #0f172a;
        margin-bottom: 12px;
    }

    div[data-testid="stSidebar"] {
        background-color: #f8fafc;
    }
</style>
"""


def _risk_label(score: float) -> str:
    if score >= 0.85:
        return "Critique"
    if score >= 0.5:
        return "Surveillance"
    return "Normal"


def _risk_badge_class(score: float) -> str:
    if score >= 0.85:
        return "badge-high"
    if score >= 0.5:
        return "badge-mid"
    return "badge-low"


def _risk_color(score: float) -> str:
    if score >= 0.85:
        return "#dc2626"
    if score >= 0.5:
        return "#d97706"
    return "#16a34a"


def _build_dataframe(transactions: list[dict], results: list[dict]) -> pd.DataFrame:
    rows = []
    for tx, result in zip(transactions, results):
        score = float(result.get("fraud_score") or 0)
        rows.append(
            {
                "ID": result.get("transaction_id"),
                "Client": tx.get("user_id"),
                "Montant": tx.get("amount"),
                "Devise": tx.get("currency"),
                "Commerçant": tx.get("merchant"),
                "Pays": tx.get("country") or "—",
                "Date": tx.get("timestamp") or "—",
                "Carte": "Oui" if tx.get("card_present") else ("Non" if tx.get("card_present") is False else "—"),
                "Score": score,
                "Statut": "Alerte" if result.get("is_suspicious") else "Conforme",
                "Niveau": _risk_label(score),
                "Motif": result.get("reason"),
            }
        )
    return pd.DataFrame(rows)


def _render_header() -> None:
    st.markdown(
        f"""
        <div class="sentinel-header">
            <h1>{BRAND}</h1>
            <p>{TAGLINE} · Analyse comportementale & détection d'anomalies</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_kpis(df: pd.DataFrame) -> None:
    alerts = df[df["Statut"] == "Alerte"]
    clients_at_risk = alerts["Client"].nunique() if not alerts.empty else 0
    avg_score = alerts["Score"].mean() if not alerts.empty else 0.0
    alert_rate = (len(alerts) / len(df) * 100) if len(df) else 0

    cols = st.columns(4)
    kpis = [
        ("Volume analysé", str(len(df)), "transactions traitées"),
        ("Alertes actives", str(len(alerts)), f"{clients_at_risk} client(s) impacté(s)"),
        ("Taux d'alerte", f"{alert_rate:.1f}%", "sur le lot courant"),
        ("Score moyen alertes", f"{avg_score:.2f}" if not alerts.empty else "—", "risque 0 → 1"),
    ]
    for col, (label, value, sub) in zip(cols, kpis):
        with col:
            st.markdown(
                f"""
                <div class="kpi-card">
                    <div class="kpi-label">{label}</div>
                    <div class="kpi-value">{value}</div>
                    <div class="kpi-sub">{sub}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _render_charts(df: pd.DataFrame) -> None:
    left, right = st.columns(2)

    with left:
        st.markdown('<p class="section-title">Répartition des statuts</p>', unsafe_allow_html=True)
        status_counts = df["Statut"].value_counts().reset_index()
        status_counts.columns = ["Statut", "Nombre"]
        st.bar_chart(status_counts.set_index("Statut"), color="#0f766e", height=220)

    with right:
        st.markdown('<p class="section-title">Motifs d\'alerte</p>', unsafe_allow_html=True)
        alerts = df[df["Statut"] == "Alerte"]
        if alerts.empty:
            st.caption("Aucune alerte sur ce lot.")
        else:
            reason_counts = alerts["Motif"].value_counts().reset_index()
            reason_counts.columns = ["Motif", "Nombre"]
            st.bar_chart(reason_counts.set_index("Motif"), color="#dc2626", height=220)


def render_interface(transactions: list[dict], results: list[dict]) -> None:
    df = _build_dataframe(transactions, results)
    alerts = df[df["Statut"] == "Alerte"]

    _render_kpis(df)
    st.markdown("<br>", unsafe_allow_html=True)

    tab_overview, tab_alerts, tab_explorer, tab_rules = st.tabs(
        ["Vue d'ensemble", "Centre d'alertes", "Explorateur", "Moteur de règles"]
    )

    with tab_overview:
        _render_charts(df)
        st.markdown('<p class="section-title">Synthèse opérationnelle</p>', unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3)
        c1.metric("Clients uniques", df["Client"].nunique())
        c2.metric("Pays couverts", df[df["Pays"] != "—"]["Pays"].nunique())
        c3.metric("Transactions conformes", len(df) - len(alerts))

    with tab_alerts:
        if alerts.empty:
            st.success("Aucune anomalie détectée sur ce lot. Toutes les transactions sont conformes.")
        else:
            st.caption(f"{len(alerts)} alerte(s) nécessitent une revue analyste.")
            for _, row in alerts.iterrows():
                score = row["Score"]
                badge = _risk_badge_class(score)
                st.markdown(
                    f"""
                    <div class="alert-card" style="border-left: 4px solid {_risk_color(score)};">
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                            <strong style="font-size:1rem;">{row['ID']}</strong>
                            <span class="{badge}">{row['Niveau']} · {score:.2f}</span>
                        </div>
                        <div style="color:#475569; font-size:0.9rem; margin-bottom:6px;">
                            Client <strong>{row['Client']}</strong> ·
                            {row['Montant']} {row['Devise']} · {row['Commerçant']} · {row['Pays']}
                        </div>
                        <div style="color:#0f172a;">{row['Motif']}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    with tab_explorer:
        fc1, fc2, fc3 = st.columns([1, 1, 2])
        with fc1:
            status_filter = st.selectbox("Statut", ["Tous", "Alerte", "Conforme"])
        with fc2:
            clients = ["Tous"] + sorted(df["Client"].dropna().unique().tolist())
            client_filter = st.selectbox("Client", clients)
        with fc3:
            search = st.text_input("Recherche", placeholder="ID, commerçant, motif…")

        filtered = df.copy()
        if status_filter != "Tous":
            filtered = filtered[filtered["Statut"] == status_filter]
        if client_filter != "Tous":
            filtered = filtered[filtered["Client"] == client_filter]
        if search.strip():
            mask = filtered.apply(
                lambda r: search.lower() in " ".join(str(v).lower() for v in r.values),
                axis=1,
            )
            filtered = filtered[mask]

        st.dataframe(
            filtered,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Score": st.column_config.ProgressColumn(
                    "Score",
                    min_value=0,
                    max_value=1,
                    format="%.2f",
                ),
            },
        )

        csv_bytes = filtered.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Exporter les résultats (CSV)",
            data=csv_bytes,
            file_name="sentinel_analyse.csv",
            mime="text/csv",
        )

        if not filtered.empty:
            st.markdown('<p class="section-title">Fiche transaction</p>', unsafe_allow_html=True)
            selected_id = st.selectbox(
                "Sélectionner une transaction",
                options=filtered["ID"].tolist(),
            )
            row = filtered[filtered["ID"] == selected_id].iloc[0]
            d1, d2, d3, d4 = st.columns(4)
            d1.metric("Montant", f"{row['Montant']} {row['Devise']}")
            d2.metric("Score de risque", f"{row['Score']:.2f}")
            d3.metric("Statut", row["Statut"])
            d4.metric("Carte présente", row["Carte"])
            st.info(row["Motif"])

    with tab_rules:
        st.markdown(
            """
            ### Politique de détection

            Le moteur **Sentinel** évalue chaque transaction selon une chaîne de règles
            métier, conçue pour limiter les faux positifs tout en signalant les comportements à risque.

            | Priorité | Règle | Description |
            |:---:|---|---|
            | 1 | Montant invalide | Montant nul, négatif ou absent |
            | 2 | Intégrité des données | Champs obligatoires manquants |
            | 3 | Doublon | Identifiant de transaction déjà traité |
            | 4 | Anomalie géographique | Deux pays distincts en moins de 24 h |
            | 5 | Vélocité | Fréquence anormale (> 5 opérations / heure) |
            | 6 | Dépense atypique | Montant ≥ 10× la médiane historique client |
            | 7 | Paiement à distance | Opération sans carte physique inhabituelle |

            **Score de risque** : valeur continue entre 0 et 1, associée à un statut binaire
            (*Conforme* / *Alerte*) et à un motif lisible pour l'analyste.
            """
        )


def main() -> None:
    st.set_page_config(
        page_title=f"{BRAND} — Fraud Intelligence",
        page_icon="🛡️",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    with st.sidebar:
        st.markdown(f"### {BRAND}")
        st.caption("Console d'analyse transactionnelle")
        st.divider()

        source = st.radio(
            "Source des données",
            ["Jeu de démonstration", "Import CSV"],
            label_visibility="collapsed",
        )

        transactions: list[dict] = []
        if source == "Jeu de démonstration":
            transactions = load_transactions(str(SAMPLE_CSV))
            st.success(f"{len(transactions)} transactions chargées")
        else:
            uploaded = st.file_uploader("Fichier CSV", type=["csv"])
            if uploaded:
                tmp = Path(".streamlit_upload.csv")
                tmp.write_bytes(uploaded.getvalue())
                transactions = load_transactions(str(tmp))
                tmp.unlink(missing_ok=True)
                st.success(f"{len(transactions)} transactions importées")

        st.divider()
        auto_run = st.toggle("Analyse automatique", value=True)
        st.caption("Version 1.0 · Moteur de règles comportementales")

    _render_header()

    if not transactions:
        st.info("Sélectionnez une source de données dans la barre latérale.")
        return

    run = auto_run or st.button("Lancer l'analyse", type="primary", use_container_width=True)

    if run:
        try:
            results = detect_fraud(transactions)
            st.session_state["results"] = results
            st.session_state["tx_count"] = len(transactions)
        except NotImplementedError:
            st.error("Le moteur de détection n'est pas encore configuré.")
            return
        except Exception as exc:
            st.error(f"Erreur d'analyse : {exc}")
            return

    if (
        "results" in st.session_state
        and st.session_state.get("tx_count") == len(transactions)
    ):
        render_interface(transactions, st.session_state["results"])


if __name__ == "__main__":
    main()
