import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st
from mplsoccer import Pitch
from statsbombpy import sb

warnings.filterwarnings("ignore")

st.set_page_config(page_title="Football Tactical Data Hub - Pro", page_icon="⚽", layout="wide")

st.title("⚽ Tactical Data Analyzer Hub (Pro Edition)")
st.markdown(
    "Plataforma de análisis táctico con filtrado por jugador y mapas de calor espaciales "
    "(datos abiertos de StatsBomb)."
)


# ---------- Carga de datos (con caché) ----------
@st.cache_data(show_spinner=False)
def get_competitions():
    return sb.competitions(creds={})


@st.cache_data(show_spinner=False)
def get_matches(c_id, s_id):
    return sb.matches(competition_id=c_id, season_id=s_id, creds={})


@st.cache_data(show_spinner=False)
def get_match_events(m_id):
    return sb.events(match_id=m_id, creds={})


comps_df = get_competitions()

# ---------- 1. Competición, torneo y temporada ----------
st.sidebar.header("1. Competición y Temporada")
selected_country = st.sidebar.selectbox("País / Categoría", sorted(comps_df["country_name"].unique()))
country_comps = comps_df[comps_df["country_name"] == selected_country]

competition_name = st.sidebar.selectbox("Torneo", sorted(country_comps["competition_name"].unique()))
comp_seasons = country_comps[country_comps["competition_name"] == competition_name].sort_values(
    "season_name", ascending=False
)
season_name = st.sidebar.selectbox("Temporada", comp_seasons["season_name"].tolist())
comp_row = comp_seasons[comp_seasons["season_name"] == season_name].iloc[0]

matches_df = get_matches(int(comp_row["competition_id"]), int(comp_row["season_id"]))
matches_df = matches_df.sort_values("match_date").reset_index(drop=True)

# ---------- 2. Partido ----------
st.sidebar.header("2. Selección de Partido")
match_labels = {
    int(r["match_id"]): f"{r['home_team']} {r['home_score']} - {r['away_score']} {r['away_team']} ({r['match_date']})"
    for _, r in matches_df.iterrows()
}
match_id = st.sidebar.selectbox("Partido", list(match_labels.keys()), format_func=lambda k: match_labels[k])
match_row = matches_df[matches_df["match_id"] == match_id].iloc[0]

col1, col2, col3 = st.columns(3)
col1.metric("Equipo Local", match_row["home_team"], int(match_row["home_score"]), delta_color="off")
col2.metric("Equipo Visitante", match_row["away_team"], int(match_row["away_score"]), delta_color="off")
col3.metric("Fecha del Encuentro", str(match_row["match_date"]))

with st.spinner("Extrayendo eventos del partido..."):
    events_df = get_match_events(match_id)

# ---------- 3. Filtros tácticos ----------
st.sidebar.header("3. Filtros Tácticos")
selected_team = st.sidebar.selectbox("Equipo a analizar", events_df["team"].dropna().unique())
team_events = events_df[events_df["team"] == selected_team]

selected_players = st.sidebar.multiselect(
    "Jugador(es)", sorted(team_events["player"].dropna().unique()), default=[]
)
event_types = sorted(team_events["type"].dropna().unique())
default_events = [e for e in ["Pass", "Carry"] if e in event_types]
selected_events = st.sidebar.multiselect("Tipos de evento", event_types, default=default_events)

filtered_events = team_events
if selected_players:
    filtered_events = filtered_events[filtered_events["player"].isin(selected_players)]
if selected_events:
    filtered_events = filtered_events[filtered_events["type"].isin(selected_events)]

st.subheader(f"🎯 Análisis Espacial: {selected_team}")
st.markdown(f"Se han aislado **{len(filtered_events)}** acciones que cumplen los filtros.")


# ---------- Extracción de coordenadas ----------
def extract_xy(df: pd.DataFrame) -> pd.DataFrame:
    if "location" not in df.columns:
        return pd.DataFrame(columns=["x", "y", "type", "player"])
    df = df.dropna(subset=["location"])
    valid = df["location"].apply(lambda l: isinstance(l, (list, tuple, np.ndarray)) and len(l) >= 2)
    df = df[valid]
    return pd.DataFrame(
        {
            "x": df["location"].apply(lambda l: float(l[0])),
            "y": df["location"].apply(lambda l: float(l[1])),
            "type": df["type"],
            "player": df["player"],
        }
    )


plot_df = extract_xy(filtered_events)

if len(plot_df) > 5:
    viz_mode = st.radio(
        "Tipo de representación táctica:",
        ["Mapa de Dispersión (Acciones)", "Mapa de Calor / Densidad (KDE)"],
        horizontal=True,
    )
    pitch = Pitch(pitch_type="statsbomb", pitch_color="grass", line_color="white", line_zorder=2)
    fig, ax = pitch.draw(figsize=(10, 7))

    if viz_mode.startswith("Mapa de Dispersión"):
        colors = {"Pass": "yellow", "Carry": "cyan", "Pressure": "orange", "Shot": "red", "Ball Recovery": "lime"}
        for ev_type in plot_df["type"].unique():
            subset = plot_df[plot_df["type"] == ev_type]
            pitch.scatter(
                subset["x"], subset["y"], ax=ax, color=colors.get(ev_type, "white"),
                edgecolors="black", s=90, alpha=0.85, label=ev_type, zorder=3,
            )
        ax.legend(loc="upper right", facecolor="black", edgecolor="white", labelcolor="white")
    else:
        try:
            pitch.kdeplot(plot_df["x"], plot_df["y"], ax=ax, cmap="hot", levels=50, thresh=0.05,
                          fill=True, alpha=0.65, zorder=3)
            pitch.scatter(plot_df["x"], plot_df["y"], ax=ax, color="white", s=15, alpha=0.3, zorder=4)
        except Exception:
            st.warning("Densidad insuficiente para el KDE con este filtro. Mostrando dispersión.")
            pitch.scatter(plot_df["x"], plot_df["y"], ax=ax, color="yellow", s=70, alpha=0.8, zorder=3)

    st.pyplot(fig)
    plt.close(fig)
else:
    st.info("No hay suficientes coordenadas espaciales para esta combinación de filtros.")

with st.expander("📊 Inspeccionar registros en bruto"):
    cols = [c for c in ["minute", "second", "type", "player", "position", "location"] if c in filtered_events.columns]
    st.dataframe(filtered_events[cols].head(200), width="stretch")
