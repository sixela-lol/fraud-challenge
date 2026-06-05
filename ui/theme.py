"""Thème visuel paramétrable en direct — dashboard plein écran."""

from __future__ import annotations

APP_NAME = "Sentinel"
APP_TAGLINE = "Assistant anti-fraude"

# Presets sélectionnables dans l'interface.
THEME_PRESETS = {
    "nuit": {
        "label": "Nuit (centre opérationnel)",
        "bg": "#0b1220",
        "bg2": "#111c30",
        "panel": "#0f1b2e",
        "panel_border": "#1e3253",
        "text": "#e2e8f0",
        "muted": "#94a3b8",
        "accent": "#3b82f6",
        "sidebar1": "#0b1220",
        "sidebar2": "#111c30",
        "map_style": "dark",
    },
    "jour": {
        "label": "Jour (clair)",
        "bg": "#f1f5f9",
        "bg2": "#e2e8f0",
        "panel": "#ffffff",
        "panel_border": "#e2e8f0",
        "text": "#0f172a",
        "muted": "#64748b",
        "accent": "#2563eb",
        "sidebar1": "#0f172a",
        "sidebar2": "#1e293b",
        "map_style": "light",
    },
    "neon": {
        "label": "Néon (cyber)",
        "bg": "#05060f",
        "bg2": "#0a0f24",
        "panel": "#0b1030",
        "panel_border": "#1b2a6b",
        "text": "#d8f3ff",
        "muted": "#7aa2c2",
        "accent": "#22d3ee",
        "sidebar1": "#05060f",
        "sidebar2": "#0a0f24",
        "map_style": "dark",
    },
    "ambre": {
        "label": "Ambre (sécurité)",
        "bg": "#0f0a05",
        "bg2": "#1c1207",
        "panel": "#1a1206",
        "panel_border": "#3d2a0e",
        "text": "#fde9c8",
        "muted": "#c8a06a",
        "accent": "#f59e0b",
        "sidebar1": "#0f0a05",
        "sidebar2": "#1c1207",
        "map_style": "dark",
    },
}

DEFAULT_THEME = "nuit"


def get_theme(name: str) -> dict:
    return THEME_PRESETS.get(name, THEME_PRESETS[DEFAULT_THEME])


def build_css(theme: dict, accent: str | None = None, radius: int = 12, density: str = "confort") -> str:
    """Génère le CSS complet à partir d'un thème et d'options live."""
    accent = accent or theme["accent"]
    compact = density == "compact"
    pad = "0.55rem 0.85rem" if compact else "0.95rem 1.2rem"
    tile_h = 82 if compact else 104
    base_font = 14.5 if compact else 16.5
    nav_font = 0.84 if compact else 0.95
    tile_val = 1.6 if compact else 2.0

    return f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    :root {{
        --accent: {accent};
        --radius: {radius}px;
    }}

    html, body, [class*="css"] {{ font-family: 'Inter', sans-serif; }}
    .stApp {{ font-size: {base_font}px; }}
    .main p, .main li, .main label, .stMarkdown {{ font-size: {base_font}px; }}

    .stApp {{
        background:
            radial-gradient(1200px 600px at 80% -10%, {accent}22, transparent 60%),
            linear-gradient(180deg, {theme['bg']} 0%, {theme['bg2']} 100%);
        color: {theme['text']};
    }}

    header[data-testid="stHeader"] {{ background: transparent; }}

    .main .block-container {{ padding: 0.7rem 1.4rem 0.4rem 1.4rem; max-width: 100%; }}

    div[data-testid="stSidebar"] {{
        background: linear-gradient(180deg, {theme['sidebar1']} 0%, {theme['sidebar2']} 100%);
        border-right: 1px solid {accent}33;
    }}
    div[data-testid="stSidebar"] * {{ color: {theme['text']}; }}
    div[data-testid="stSidebar"] .stButton button[kind="primary"] {{
        background: {accent}; border: none; font-weight: 700; border-radius: var(--radius);
    }}

    .dash-header {{
        background: linear-gradient(90deg, {theme['panel']}, {accent}33);
        border: 1px solid {accent}44;
        color: {theme['text']};
        border-radius: var(--radius);
        padding: {pad};
        margin-bottom: 10px;
        display: flex; justify-content: space-between; align-items: center;
    }}
    .dash-header h1 {{ margin: 0; font-size: 1.6rem; font-weight: 800; }}
    .dash-header span {{ font-size: 0.9rem; color: {theme['muted']}; }}

    .pulse-dot {{
        display:inline-block; width:9px; height:9px; border-radius:50%;
        background:{accent}; margin-right:6px;
        box-shadow:0 0 0 0 {accent};
        animation: pulse 1.8s infinite;
    }}
    @keyframes pulse {{
        0% {{ box-shadow: 0 0 0 0 {accent}aa; }}
        70% {{ box-shadow: 0 0 0 12px {accent}00; }}
        100% {{ box-shadow: 0 0 0 0 {accent}00; }}
    }}

    .metric-tile {{
        background: {theme['panel']};
        border: 1px solid {theme['panel_border']};
        border-radius: var(--radius);
        padding: 12px 16px; text-align: center;
        height: {tile_h}px; display: flex; flex-direction: column; justify-content: center;
        transition: transform .15s ease, border-color .15s ease;
    }}
    .metric-tile:hover {{ transform: translateY(-2px); border-color: {accent}; }}
    .metric-tile .label {{ color: {theme['muted']}; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 6px; }}
    .metric-tile .value {{ font-size: {tile_val}rem; font-weight: 800; color: {theme['text']}; line-height: 1; }}
    .metric-tile .value.accent {{ color: {accent}; }}

    .panel {{
        background: {theme['panel']};
        border: 1px solid {theme['panel_border']};
        border-radius: var(--radius);
        padding: 18px 22px; height: 100%;
    }}
    .panel-title {{ font-size: 1.02rem; font-weight: 700; color: {theme['text']}; margin: 0 0 10px 0; }}

    .alert-panel {{
        background: linear-gradient(180deg, {theme['panel']}, #7f1d1d22);
        border: 1px solid #ef444466; border-left: 5px solid #ef4444;
        border-radius: var(--radius); padding: 16px 20px; height: 100%;
    }}
    .alert-panel h3 {{ margin: 0 0 8px 0; color: #fca5a5; font-size: 1.1rem; }}
    .alert-panel p {{ margin: 5px 0; color: {theme['text']}; font-size: 0.92rem; line-height: 1.45; }}

    .ok-panel {{
        background: linear-gradient(180deg, {theme['panel']}, #14532d22);
        border: 1px solid #22c55e55; border-radius: var(--radius);
        padding: 22px; text-align: center; color: #86efac; font-size: 1rem;
    }}

    .welcome-panel {{
        background: {theme['panel']}; border: 1px solid {theme['panel_border']};
        border-radius: var(--radius); padding: 38px; text-align: center;
        display: flex; flex-direction: column; align-items: center; justify-content: center;
        min-height: 60vh;
    }}
    .welcome-panel h2 {{ color: {theme['text']}; margin-bottom: 8px; }}
    .welcome-panel p {{ color: {theme['muted']}; max-width: 460px; line-height: 1.55; }}

    .chip {{
        display:inline-block; padding:3px 10px; border-radius:999px;
        font-size:0.72rem; font-weight:600; margin:2px;
        background:{accent}22; color:{accent}; border:1px solid {accent}55;
    }}

    .step-item {{ font-size: 0.82rem; padding: 5px 0; color: {theme['muted']}; }}
    .step-active {{ color: {accent} !important; font-weight: 700; }}
    .step-done {{ color: #34d399 !important; }}

    /* ---- Boutons façon pilule (navigation + actions) ---- */
    .stButton > button {{
        border-radius: 999px;
        font-weight: 600;
        font-size: {nav_font}rem;
        padding: 0.6rem 1.05rem;
        transition: transform .14s ease, border-color .14s ease, color .14s ease, box-shadow .14s ease;
        border: 1px solid {theme['panel_border']};
    }}
    .stButton > button[kind="secondary"] {{
        background: {theme['panel']}; color: {theme['muted']};
    }}
    .stButton > button[kind="secondary"]:hover {{
        border-color: {accent}; color: {accent}; transform: translateY(-1px);
    }}
    .stButton > button[kind="primary"] {{
        background: linear-gradient(90deg, {accent}, {accent}cc);
        border: 1px solid {accent}; color: #ffffff;
        box-shadow: 0 6px 18px {accent}55;
    }}

    /* ---- Barre de navigation horizontale ---- */
    .nav-wrap {{
        background: {theme['panel']}cc;
        border: 1px solid {theme['panel_border']};
        border-radius: 999px;
        padding: 6px;
        margin-bottom: 14px;
        backdrop-filter: blur(8px);
    }}
    .nav-wrap [data-testid="column"] {{ padding: 0 3px; }}
    .nav-wrap .stButton > button {{ width: 100%; border: none; background: transparent; }}
    .nav-wrap .stButton > button[kind="secondary"]:hover {{
        background: {accent}1a; transform: none;
    }}

    .section-label {{
        font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.08em;
        color: {theme['muted']}; font-weight: 700; margin: 6px 0 8px 4px;
    }}

    /* ---- Responsive ---- */
    @media (max-width: 900px) {{
        .dash-header {{ flex-direction: column; align-items: flex-start; gap: 6px; }}
        .dash-header h1 {{ font-size: 1.1rem; }}
        .metric-tile .value {{ font-size: 1.3rem; }}
        .main .block-container {{ padding: 0.6rem 0.8rem; }}
    }}
</style>
"""
