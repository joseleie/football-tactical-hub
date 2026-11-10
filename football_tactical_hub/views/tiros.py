import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from mplsoccer import Pitch

st.title("🥅 Tiros recientes (Understat)")
st.markdown(
    "Tiros y **xG** de las grandes ligas con datos recientes. Fuente: Understat, leída con `soccerdata`. "
    "Es independiente de la competición elegida en la barra lateral."
)

LEAGUES = {
    "La Liga (España)": "ESP-La Liga",
    "Premier League (Inglaterra)": "ENG-Premier League",
    "Serie A (Italia)": "ITA-Serie A",
    "Bundesliga (Alemania)": "GER-Bundesliga",
    "Ligue 1 (Francia)": "FRA-Ligue 1",
}


@st.cache_data(ttl=3600, show_spinner="Descargando tiros de Understat (puede tardar un poco)...")
def load_shots(league: str, season: str) -> pd.DataFrame:
    import soccerdata as sd

    return sd.Understat(league, season).read_shot_events().reset_index()


u1, u2 = st.columns(2)
league_label = u1.selectbox("Liga", list(LEAGUES.keys()), key="us_league")
season = u2.selectbox("Temporada (año de inicio)", ["2025", "2024", "2023"], key="us_season")

try:
    shots = load_shots(LEAGUES[league_label], season)
except Exception as e:
    st.error("No se pudieron descargar los datos de Understat (bloqueo temporal del sitio o cambio en su web). Inténtalo más tarde.")
    st.caption(f"Detalle técnico: {type(e).__name__}: {e}")
    st.stop()

needed = {"location_x", "location_y", "xg", "team", "player"}
if not needed.issubset(shots.columns):
    st.warning("El formato de Understat ha cambiado. Columnas disponibles:")
    st.write(list(shots.columns))
    st.stop()

f1, f2 = st.columns(2)
team = f1.selectbox("Equipo", sorted(shots["team"].dropna().unique()), key="us_team")
d = shots[shots["team"] == team]
sel_players = f2.multiselect("Jugador(es)", sorted(d["player"].dropna().unique()), key="us_players")
if sel_players:
    d = d[d["player"].isin(sel_players)]
if "game" in d.columns:
    games = ["Todos los partidos"] + sorted(d["game"].dropna().astype(str).unique())
    g = st.selectbox("Partido", games, key="us_game")
    if g != "Todos los partidos":
        d = d[d["game"].astype(str) == g]

is_goal = d["result"].astype(str).eq("Goal") if "result" in d.columns else pd.Series(False, index=d.index)
m1, m2, m3 = st.columns(3)
m1.metric("Tiros", len(d))
m2.metric("Goles", int(is_goal.sum()))
m3.metric("xG total", f"{d['xg'].astype(float).sum():.2f}")

plot = d.dropna(subset=["location_x", "location_y"])
if len(plot):
    pitch = Pitch(pitch_type="opta", half=True, pitch_color="grass", line_color="white", line_zorder=2)
    fig, ax = pitch.draw(figsize=(9, 7))
    x = plot["location_x"].astype(float) * 100
    y = plot["location_y"].astype(float) * 100
    goal = is_goal.loc[plot.index]
    size = 40 + plot["xg"].astype(float) * 600
    pitch.scatter(x[~goal], y[~goal], s=size[~goal], ax=ax, color="white", edgecolors="black", alpha=0.7, label="Tiro", zorder=3)
    pitch.scatter(x[goal], y[goal], s=size[goal], ax=ax, color="red", edgecolors="black", alpha=0.9, label="Gol", zorder=4)
    ax.legend(loc="lower right", facecolor="black", edgecolor="white", labelcolor="white")
    st.caption("El tamaño del círculo es proporcional al xG del tiro.")
    st.pyplot(fig)
    plt.close(fig)
else:
    st.info("No hay tiros con coordenadas para este filtro.")

with st.expander("📊 Tiros en bruto"):
    show = [c for c in ["game", "minute", "player", "xg", "result", "situation", "body_part"] if c in d.columns]
    st.dataframe(d[show].head(300), width="stretch")
