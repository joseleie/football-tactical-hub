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

tab_sb, tab_us = st.tabs(["🎯 Táctica (StatsBomb)", "🥅 Tiros recientes (Understat)"])


# =====================================================================
# PESTAÑA 1: STATSBOMB (datos abiertos, eventos completos)
# =====================================================================
@st.cache_data(show_spinner=False)
def get_competitions():
    return sb.competitions(creds={})


@st.cache_data(show_spinner=False)
def get_matches(c_id, s_id):
    return sb.matches(competition_id=c_id, season_id=s_id, creds={})


@st.cache_data(show_spinner=False)
def get_match_events(m_id):
    return sb.events(match_id=m_id, creds={})


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


with tab_sb:
    st.markdown(
        "Análisis táctico con filtrado por jugador y mapas de calor espaciales "
        "(datos abiertos de StatsBomb)."
    )
    comps_df = get_competitions()

    st.sidebar.header("StatsBomb · 1. Competición")
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

    st.sidebar.header("StatsBomb · 2. Partido")
    match_labels = {
        int(r["match_id"]): f"{r['home_team']} {r['home_score']} - {r['away_score']} {r['away_team']} ({r['match_date']})"
        for _, r in matches_df.iterrows()
    }
    match_id = st.sidebar.selectbox("Partido", list(match_labels.keys()), format_func=lambda k: match_labels[k])
    match_row = matches_df[matches_df["match_id"] == match_id].iloc[0]

    c1, c2, c3 = st.columns(3)
    c1.metric("Equipo Local", match_row["home_team"], int(match_row["home_score"]), delta_color="off")
    c2.metric("Equipo Visitante", match_row["away_team"], int(match_row["away_score"]), delta_color="off")
    c3.metric("Fecha del Encuentro", str(match_row["match_date"]))

    with st.spinner("Extrayendo eventos del partido..."):
        events_df = get_match_events(match_id)

    st.sidebar.header("StatsBomb · 3. Filtros")
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

    st.subheader(f"Análisis espacial: {selected_team}")
    st.markdown(f"Se han aislado **{len(filtered_events)}** acciones que cumplen los filtros.")

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


# =====================================================================
# PESTAÑA 2: UNDERSTAT (tiros y xG de temporadas recientes)
# =====================================================================
LEAGUES = {
    "La Liga (España)": "ESP-La Liga",
    "Premier League (Inglaterra)": "ENG-Premier League",
    "Serie A (Italia)": "ITA-Serie A",
    "Bundesliga (Alemania)": "GER-Bundesliga",
    "Ligue 1 (Francia)": "FRA-Ligue 1",
}
SEASONS = ["2025", "2024", "2023"]


@st.cache_data(ttl=3600, show_spinner="Descargando tiros de Understat (puede tardar un poco)...")
def load_shots(league: str, season: str) -> pd.DataFrame:
    import soccerdata as sd

    return sd.Understat(league, season).read_shot_events().reset_index()


with tab_us:
    st.markdown(
        "Tiros y **xG** de las grandes ligas con datos recientes. Fuente: Understat, "
        "leída con `soccerdata`. Las coordenadas vienen normalizadas (0 a 1)."
    )
    u1, u2 = st.columns(2)
    league_label = u1.selectbox("Liga", list(LEAGUES.keys()), key="us_league")
    us_season = u2.selectbox("Temporada (año de inicio)", SEASONS, key="us_season")

    try:
        shots = load_shots(LEAGUES[league_label], us_season)
    except Exception as e:
        shots = None
        st.error(
            "No se pudieron descargar los datos de Understat. Puede ser un bloqueo temporal del sitio "
            "hacia los servidores de Streamlit o un cambio en su web. Inténtalo más tarde."
        )
        st.caption(f"Detalle técnico: {type(e).__name__}: {e}")

    if shots is not None:
        needed = {"location_x", "location_y", "xg", "team", "player"}
        if not needed.issubset(shots.columns):
            st.warning("El formato de Understat ha cambiado. Columnas disponibles:")
            st.write(list(shots.columns))
        else:
            teams = sorted(shots["team"].dropna().unique())
            f1, f2 = st.columns(2)
            team_sel = f1.selectbox("Equipo", teams, key="us_team")
            team_shots = shots[shots["team"] == team_sel]

            players = sorted(team_shots["player"].dropna().unique())
            player_sel = f2.multiselect("Jugador(es)", players, key="us_players")
            if player_sel:
                team_shots = team_shots[team_shots["player"].isin(player_sel)]

            if "game" in team_shots.columns:
                games = ["Todos los partidos"] + sorted(team_shots["game"].dropna().astype(str).unique())
                game_sel = st.selectbox("Partido", games, key="us_game")
                if game_sel != "Todos los partidos":
                    team_shots = team_shots[team_shots["game"].astype(str) == game_sel]

            is_goal = team_shots["result"].astype(str).eq("Goal") if "result" in team_shots.columns else pd.Series(False, index=team_shots.index)
            m1, m2, m3 = st.columns(3)
            m1.metric("Tiros", len(team_shots))
            m2.metric("Goles", int(is_goal.sum()))
            m3.metric("xG total", f"{team_shots['xg'].astype(float).sum():.2f}")

            plot = team_shots.dropna(subset=["location_x", "location_y"])
            if len(plot) > 0:
                pitch = Pitch(pitch_type="opta", half=True, pitch_color="grass", line_color="white", line_zorder=2)
                fig, ax = pitch.draw(figsize=(9, 7))
                x = plot["location_x"].astype(float) * 100
                y = plot["location_y"].astype(float) * 100
                goal_mask = is_goal.loc[plot.index]
                sizes = 40 + plot["xg"].astype(float) * 600
                pitch.scatter(x[~goal_mask], y[~goal_mask], s=sizes[~goal_mask], ax=ax, color="white",
                              edgecolors="black", alpha=0.7, label="Tiro", zorder=3)
                pitch.scatter(x[goal_mask], y[goal_mask], s=sizes[goal_mask], ax=ax, color="red",
                              edgecolors="black", alpha=0.9, label="Gol", zorder=4)
                ax.legend(loc="lower right", facecolor="black", edgecolor="white", labelcolor="white")
                st.caption("El tamaño del círculo es proporcional al xG del tiro.")
                st.pyplot(fig)
                plt.close(fig)
            else:
                st.info("No hay tiros con coordenadas para este filtro.")

            with st.expander("📊 Tiros en bruto"):
                show = [c for c in ["game", "minute", "player", "xg", "result", "situation", "body_part"] if c in team_shots.columns]
                st.dataframe(team_shots[show].head(300), width="stretch")
